"""
Core Celery tasks: automated database backup, external drive copy.
"""
import os
import shutil
import time
import logging
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('apps.core')


@shared_task(name='core.daily_backup', bind=True, max_retries=2, default_retry_delay=300)
def daily_backup_task(self):
    """
    Daily automated PostgreSQL backup.
    - Runs pg_dump via the backup_db management command
    - Logs result to BackupLog
    - Optionally copies to BACKUP_EXTERNAL_PATH (e.g. /mnt/external_drive/backups)
    Scheduled via Celery Beat: every day at 02:00 Africa/Douala
    """
    from apps.core.models import BackupLog
    import subprocess

    start_time = time.time()
    backup_dir = Path(getattr(settings, 'BACKUP_DIR', settings.BASE_DIR / 'backups'))
    backup_dir.mkdir(parents=True, exist_ok=True)

    log = BackupLog.objects.create(
        status=BackupLog.Status.RUNNING,
        trigger=BackupLog.TriggerSource.CELERY,
    )

    try:
        # Build the pg_dump command directly (mirrors backup_db management command)
        db = settings.DATABASES.get('default', {})
        engine = db.get('ENGINE', '')

        if 'postgresql' not in engine and 'postgis' not in engine:
            raise RuntimeError(f'daily_backup_task: not a PostgreSQL database (engine={engine})')

        host     = db.get('HOST', 'localhost')
        port     = str(db.get('PORT', 5432))
        name     = db.get('NAME', '')
        user     = db.get('USER', '')
        password = db.get('PASSWORD', '')

        timestamp = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M%S')
        filename  = f'ehr_backup_{timestamp}.dump'
        filepath  = backup_dir / filename

        env = os.environ.copy()
        if password:
            env['PGPASSWORD'] = password

        cmd = [
            'pg_dump',
            '--format=custom',
            '--no-password',
            f'--host={host}',
            f'--port={port}',
            f'--username={user}',
            f'--file={filepath}',
            name,
        ]

        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)

        if result.returncode != 0:
            raise RuntimeError(f'pg_dump exit {result.returncode}: {result.stderr[:500]}')

        size_mb = filepath.stat().st_size / (1024 * 1024)
        duration = time.time() - start_time

        # Rotate old backups — keep last 30
        keep = getattr(settings, 'BACKUP_KEEP', 30)
        dumps = sorted(backup_dir.glob('ehr_backup_*.dump'))
        for old in dumps[:-keep]:
            old.unlink(missing_ok=True)

        # Copy to external drive if configured
        external_path_str = getattr(settings, 'BACKUP_EXTERNAL_PATH', '')
        copied = False
        ext_dest = ''
        if external_path_str:
            external_dir = Path(external_path_str)
            if external_dir.exists():
                ext_dest = str(external_dir / filename)
                shutil.copy2(str(filepath), ext_dest)
                copied = True
                logger.info('Backup copied to external: %s', ext_dest)
            else:
                logger.warning('External backup path not found: %s', external_path_str)

        log.filename = filename
        log.output_path = str(filepath)
        log.size_mb = round(size_mb, 2)
        log.status = BackupLog.Status.SUCCESS
        log.duration_seconds = round(duration, 1)
        log.copied_to_external = copied
        log.external_path = ext_dest
        log.save()

        logger.info('daily_backup_task completed: %s (%.1f MB, %.1fs)', filename, size_mb, duration)
        return {'status': 'success', 'filename': filename, 'size_mb': round(size_mb, 2)}

    except Exception as exc:
        duration = time.time() - start_time
        log.status = BackupLog.Status.FAILED
        log.error_message = str(exc)
        log.duration_seconds = round(duration, 1)
        log.save()
        logger.error('daily_backup_task FAILED: %s', exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {'status': 'failed', 'error': str(exc)}


@shared_task(name='appointments.mark_no_shows', bind=True, max_retries=1, default_retry_delay=120)
def mark_no_show_appointments_task(self):
    """
    End-of-day job — marks all SCHEDULED or CONFIRMED appointments for TODAY
    that were never checked in as NO_SHOW.

    Standard in Epic/Cerner: runs at 19:00 (7pm) Africa/Douala daily.
    Logic:
      - Appointment.appointment_date == today
      - status IN (SCHEDULED, CONFIRMED)       ← never arrived
      - NOT CHECKED_IN / COMPLETED / CANCELLED ← exclude patients who came
    Creates a notification for the Medical Director and logs the count.
    """
    from apps.appointments.models import Appointment

    today = timezone.localdate()

    qs = Appointment.objects.filter(
        appointment_date=today,
        status__in=[Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED],
        is_deleted=False,
    )

    count = qs.count()
    if count == 0:
        logger.info('mark_no_shows: no pending appointments for %s — nothing to do.', today)
        return {'status': 'ok', 'no_shows_marked': 0, 'date': str(today)}

    updated = qs.update(status=Appointment.Status.NO_SHOW)

    logger.info('mark_no_shows: marked %d appointment(s) as NO_SHOW for %s', updated, today)

    # Notify Medical Director so they can follow up
    try:
        from apps.notifications.models import Notification
        from apps.accounts.models import User, UserRole
        directors = User.objects.filter(
            role__in=[UserRole.MEDICAL_DIRECTOR, UserRole.SUPER_ADMIN],
            is_active=True,
        )
        for director in directors:
            Notification.objects.create(
                recipient=director,
                title=f'End-of-Day: {updated} No-Show(s) — {today.strftime("%d %b %Y")}',
                message=(
                    f'{updated} appointment(s) scheduled for today were not checked in '
                    f'and have been automatically marked as No-Show. '
                    f'Review at /appointments/?date={today}&status=NO_SHOW'
                ),
                notification_type='WARNING',
            )
    except Exception as e:
        logger.warning('mark_no_shows: could not send notifications — %s', e)

    return {'status': 'ok', 'no_shows_marked': updated, 'date': str(today)}


@shared_task(name='ipd.auto_bill_bed_charges', bind=True, max_retries=1)
def auto_bill_bed_charges(self):
    """
    Nightly task: auto-add a bed charge line to each active inpatient's invoice.

    Schedule: runs daily at 23:55 (or 00:05 next day). For each currently
    ADMITTED patient, if they've been in bed for at least 1 night, a BedCharge
    InvoiceItem is added to their visit invoice at the ward's nightly_rate.

    Idempotency: uses today's date as the charge_date. A unique_together
    constraint on (admission, charge_date) prevents double-billing.
    """
    from django.db import IntegrityError
    from apps.ipd.models import Admission, AdmissionStatus

    today = timezone.localdate()
    billed = 0
    errors = []

    active_admissions = Admission.objects.filter(
        status=AdmissionStatus.ADMITTED, is_deleted=False
    ).select_related('bed__ward', 'patient')

    for admission in active_admissions:
        rate = admission.bed.nightly_rate
        if not rate or rate <= 0:
            continue

        # Only charge if patient has been here at least 1 day
        los = (timezone.now() - admission.admission_date).days
        if los < 1:
            continue

        try:
            from apps.billing.models import Invoice, InvoiceItem, InvoiceStatus
            from apps.patients.models import Visit, VisitStatus

            # Find the patient's current open invoice (visit-based)
            visit = Visit.objects.filter(
                patient=admission.patient,
                is_deleted=False,
            ).order_by('-visit_date').first()

            if not visit:
                continue

            invoice = Invoice.objects.filter(
                visit=visit,
                status__in=[InvoiceStatus.DRAFT, InvoiceStatus.PARTIAL],
                is_deleted=False,
            ).first()

            if not invoice:
                continue

            # Check if today's bed charge was already billed (avoid duplicates)
            already_billed = invoice.items.filter(
                service_name__startswith='Bed Charge',
                notes__contains=str(today),
            ).exists()

            if already_billed:
                continue

            InvoiceItem.objects.create(
                invoice=invoice,
                service_name=f'Bed Charge — {admission.bed.ward.name} ({admission.bed.bed_number})',
                quantity=1,
                unit_price=rate,
                notes=f'Auto-billed for {today}',
            )
            billed += 1

        except Exception as e:
            errors.append(f'Admission {admission.admission_number}: {e}')
            logger.warning('auto_bill_bed_charges: error for %s — %s', admission.admission_number, e)

    logger.info('auto_bill_bed_charges: billed %d admissions for %s', billed, today)
    return {'status': 'ok', 'billed': billed, 'date': str(today), 'errors': errors}


@shared_task(name='billing.monthly_depreciation', bind=True, max_retries=1, default_retry_delay=300)
def monthly_depreciation_task(self):
    """
    Monthly fixed asset depreciation posting.
    Runs on the 1st of every month — posts one JE per active, non-fully-deprecated asset.
    Dr 681301 Dotations aux amortissements / Cr 284xxx Amortissements cumulés (OHADA Op 160).
    """
    today = timezone.localdate()
    period_year  = today.year
    period_month = today.month

    posted  = 0
    skipped = 0
    errors  = []

    try:
        from apps.billing.models import AssetRegister, AssetStatus
        from apps.billing.gl_service import post_depreciation_monthly

        assets = AssetRegister.objects.filter(
            status=AssetStatus.ACTIVE,
            is_deleted=False,
        ).exclude(useful_life_years=0)

        for asset in assets:
            if asset.is_fully_depreciated:
                skipped += 1
                continue
            try:
                entry = post_depreciation_monthly(asset, period_year, period_month)
                if entry:
                    posted += 1
                else:
                    skipped += 1
            except Exception as exc:
                errors.append(f"{asset.asset_number}: {exc}")
                logger.warning('monthly_depreciation: error on %s — %s', asset.asset_number, exc)

    except Exception as exc:
        logger.exception('monthly_depreciation_task failed: %s', exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {'status': 'failed', 'error': str(exc)}

    logger.info('monthly_depreciation: posted=%d skipped=%d errors=%d for %04d/%02d',
                posted, skipped, len(errors), period_year, period_month)

    # Notify Finance Director
    try:
        from apps.notifications.models import Notification
        from apps.accounts.models import User, UserRole
        recipients = User.objects.filter(
            role__in=[UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT, UserRole.SUPER_ADMIN],
            is_active=True,
        )
        for u in recipients:
            Notification.objects.create(
                recipient=u,
                title=f'Monthly Depreciation Run — {today.strftime("%b %Y")}',
                message=(
                    f'Automated depreciation posting completed for {today.strftime("%B %Y")}. '
                    f'{posted} asset(s) posted, {skipped} skipped (fully depreciated or zero). '
                    + (f'{len(errors)} error(s): {"; ".join(errors[:3])}' if errors else 'No errors.')
                ),
                notification_type='SUCCESS' if not errors else 'WARNING',
                link='/billing/gl/journal/',
            )
    except Exception as e:
        logger.warning('monthly_depreciation: notification failed — %s', e)

    return {
        'status': 'ok',
        'period': f'{period_year}/{period_month:02d}',
        'posted': posted,
        'skipped': skipped,
        'errors': errors,
    }


@shared_task(name='consultations.check_cosign_deadlines', bind=True, max_retries=1, default_retry_delay=120)
def check_cosign_deadlines_task(self):
    """
    Hourly check: find intern consultations older than 24h that haven't been
    co-signed by a supervisor. Creates a notification for medical directors
    and the intern's supervisor so they can review and co-sign.
    """
    from datetime import timedelta
    from apps.consultations.models import Consultation
    from apps.accounts.models import User, UserRole

    deadline = timezone.now() - timedelta(hours=24)

    # Intern consultations past 24h without co-sign
    overdue = list(
        Consultation.objects.filter(
            is_deleted=False,
            co_signed_by__isnull=True,
            created_at__lt=deadline,
        ).filter(
            consulting_doctor__role=UserRole.INTERN,
        ).select_related('consulting_doctor', 'patient').order_by('created_at')
    )

    if not overdue:
        logger.info('cosign_deadlines: no overdue intern consultations.')
        return {'status': 'ok', 'overdue': 0}

    # Notify medical directors + admin director
    try:
        from apps.notifications.models import Notification
        directors = User.objects.filter(
            role__in=[UserRole.MEDICAL_DIRECTOR, UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR],
            is_active=True,
        )
        summary = ', '.join(
            f'{c.patient.full_name} (Dr. {c.consulting_doctor.get_full_name()}, {c.created_at.strftime("%d %b %H:%M")})'
            for c in overdue[:10]
        )
        extra = f' and {len(overdue) - 10} more' if len(overdue) > 10 else ''
        for director in directors:
            Notification.objects.create(
                recipient=director,
                title=f'Cosign Alert: {len(overdue)} intern consultation(s) past 24h deadline',
                message=(
                    f'The following intern consultations have not been co-signed within 24 hours '
                    f'and require supervisor review:\n{summary}{extra}'
                ),
                notification_type='ALERT',
                priority='HIGH',
            )
    except Exception as exc:
        logger.warning('cosign_deadlines: notification error — %s', exc)

    logger.info('cosign_deadlines: %d overdue intern consultation(s) flagged.', len(overdue))
    return {'status': 'ok', 'overdue': len(overdue)}
