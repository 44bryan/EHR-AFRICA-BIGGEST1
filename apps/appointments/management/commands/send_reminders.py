"""
Management command: send_reminders
Sends appointment reminders for tomorrow's appointments.

Usage:
    python manage.py send_reminders
    python manage.py send_reminders --days-ahead 2

Run via cron (e.g. daily at 8am):
    0 8 * * * /path/to/venv/bin/python /path/to/manage.py send_reminders >> /var/log/ehr_reminders.log 2>&1
"""
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger('apps.appointments')


class Command(BaseCommand):
    help = 'Send appointment reminders for upcoming appointments (default: tomorrow)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days-ahead',
            type=int,
            default=1,
            help='How many days ahead to look for appointments (default: 1 = tomorrow)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print reminders without actually sending them',
        )

    def handle(self, *args, **options):
        from apps.appointments.models import Appointment

        days_ahead = options['days_ahead']
        dry_run = options['dry_run']
        target_date = timezone.localdate() + timedelta(days=days_ahead)

        appointments = Appointment.objects.filter(
            appointment_date=target_date,
            status__in=[Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED],
            reminder_sent=False,
        ).select_related('patient', 'doctor', 'department')

        total = appointments.count()
        sent = 0
        failed = 0

        self.stdout.write(
            self.style.NOTICE(
                f'Processing {total} appointment(s) for {target_date} '
                f'({"DRY RUN" if dry_run else "LIVE"})'
            )
        )

        for appt in appointments:
            patient = appt.patient
            success = False

            # --- Email reminder ---
            if patient.email:
                subject = f'Appointment Reminder — {settings.HOSPITAL_NAME}'
                body = _build_email_body(appt)
                if not dry_run:
                    try:
                        send_mail(
                            subject=subject,
                            message=body,
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[patient.email],
                            fail_silently=False,
                        )
                        success = True
                        logger.info('Email reminder sent to %s for appt %s', patient.email, appt.appointment_number)
                    except Exception as e:
                        logger.warning('Email failed for %s: %s', appt.appointment_number, e)
                        failed += 1
                else:
                    self.stdout.write(f'  [DRY] Email → {patient.email}: {subject}')
                    success = True

            # --- SMS reminder (placeholder — integrate Termii/Twilio here) ---
            if patient.phone_number:
                sms_text = _build_sms_body(appt)
                if not dry_run:
                    _send_sms(str(patient.phone_number), sms_text)
                    success = True
                else:
                    self.stdout.write(f'  [DRY] SMS → {patient.phone_number}: {sms_text[:80]}...')
                    success = True

            if success:
                if not dry_run:
                    appt.reminder_sent = True
                    appt.save(update_fields=['reminder_sent'])
                sent += 1

        summary = f'Done. Sent: {sent}/{total}. Failed: {failed}.'
        self.stdout.write(self.style.SUCCESS(summary))
        logger.info('send_reminders: %s', summary)


def _build_email_body(appt):
    doctor_name = appt.doctor.get_full_name() if appt.doctor else 'Our Doctor'
    return f"""Dear {appt.patient.full_name},

This is a reminder of your appointment at {settings.HOSPITAL_NAME}.

  Date:        {appt.appointment_date.strftime('%A, %d %B %Y')}
  Time:        {appt.appointment_time.strftime('%I:%M %p')}
  Department:  {appt.department.name if appt.department else 'General'}
  Doctor:      Dr. {doctor_name}
  Ref:         {appt.appointment_number}

Please arrive 15 minutes before your scheduled time. Bring your hospital card and any relevant documents.

To reschedule or cancel, please call our reception.

{settings.HOSPITAL_NAME}
{getattr(settings, 'HOSPITAL_PHONE', '')}
"""


def _build_sms_body(appt):
    hospital = settings.HOSPITAL_NAME
    date_str = appt.appointment_date.strftime('%d/%m/%Y')
    time_str = appt.appointment_time.strftime('%I:%M%p')
    dept = appt.department.name if appt.department else 'Clinic'
    return (
        f"Reminder: {appt.patient.first_name}, your appt at {hospital} "
        f"is {date_str} at {time_str} ({dept}). "
        f"Ref: {appt.appointment_number}. Arrive 15min early. Call us to reschedule."
    )


def _send_sms(phone: str, message: str):
    """
    Placeholder for SMS sending.
    Integrate with Twilio, Africa's Talking, or a local Cameroon SMS gateway.

    Example Termii integration:
        import requests
        requests.post('https://api.ng.termii.com/api/sms/send', json={
            'to': phone,
            'from': settings.SMS_SENDER_ID,
            'sms': message,
            'type': 'plain',
            'channel': 'generic',
            'api_key': settings.TERMII_API_KEY,
        })
    """
    logger.info('SMS would be sent to %s: %s', phone, message[:60])
