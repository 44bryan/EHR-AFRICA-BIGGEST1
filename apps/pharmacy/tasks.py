"""
Pharmacy Celery tasks — scheduled and on-demand.
"""
from celery import shared_task
from django.utils import timezone


@shared_task
def send_chronic_rx_refill_reminders():
    """
    Send SMS/WhatsApp reminders to patients with chronic prescriptions
    due for refill within the next 3 days.
    Runs daily via Celery Beat.
    """
    import datetime
    from .models import ChronicPrescription

    today = timezone.localdate()
    upcoming = today + datetime.timedelta(days=3)

    due_rxs = ChronicPrescription.objects.filter(
        is_active=True,
        is_deleted=False,
        next_refill_date__range=(today, upcoming),
    ).select_related('patient', 'drug')

    sent = 0
    for rx in due_rxs:
        patient = rx.patient
        phone = getattr(patient, 'phone_number', None) or getattr(patient, 'phone', '')
        if not phone:
            continue

        days_left = (rx.next_refill_date - today).days
        if days_left == 0:
            msg = (
                f"Reminder: Your prescription for {rx.drug.name} is due for refill TODAY. "
                f"Please visit the pharmacy at your earliest convenience."
            )
        else:
            msg = (
                f"Reminder: Your prescription for {rx.drug.name} is due for refill "
                f"in {days_left} day(s) ({rx.next_refill_date.strftime('%d %b %Y')}). "
                f"Please visit the pharmacy for your refill."
            )

        try:
            from apps.notifications.models import PatientMessage, MessageTemplate
            PatientMessage.objects.create(
                patient=patient,
                channel='SMS',
                phone_number=str(phone),
                subject='Medication Refill Reminder',
                body=msg,
                status='PENDING',
            )
            sent += 1
        except Exception:
            # Notifications module may not be installed or PatientMessage may not exist
            pass

    return f'{sent} refill reminder(s) queued'


@shared_task
def calculate_dynamic_reorder_points():
    """
    Recalculate reorder levels based on average daily consumption over the last 90 days.
    Formula: reorder_level = avg_daily_consumption * lead_time_days * safety_factor
    Default lead_time=14 days, safety_factor=1.5
    """
    import datetime
    from decimal import Decimal
    from django.db.models import Sum
    from .models import Drug, DispensingItem

    cutoff = timezone.localdate() - datetime.timedelta(days=90)
    lead_time = 14  # days
    safety_factor = Decimal('1.5')

    # Aggregate total dispensed per drug in last 90 days
    consumption = dict(
        DispensingItem.objects.filter(
            dispensing__dispensed_at__date__gte=cutoff,
            dispensing__status='DISPENSED',
            drug__isnull=False,
        ).values_list('drug_id').annotate(
            total=Sum('quantity_dispensed')
        ).values_list('drug_id', 'total')
    )

    updated = 0
    for drug in Drug.objects.filter(is_active=True, is_deleted=False):
        total_dispensed = consumption.get(drug.pk, 0)
        if total_dispensed == 0:
            continue
        avg_daily = Decimal(str(total_dispensed)) / Decimal('90')
        new_reorder = int((avg_daily * lead_time * safety_factor).quantize(Decimal('1')))
        new_reorder = max(new_reorder, 5)  # minimum reorder level of 5
        if new_reorder != drug.reorder_level:
            drug.reorder_level = new_reorder
            drug.save(update_fields=['reorder_level'])
            updated += 1

    return f'{updated} reorder level(s) updated'
