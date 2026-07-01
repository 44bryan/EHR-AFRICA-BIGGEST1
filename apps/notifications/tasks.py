"""
Celery tasks for notifications.

WHY CELERY:
When a doctor saves a consultation or a lab result comes in, the system
needs to notify multiple staff. Doing this synchronously means the page
waits until all notifications are created before responding — slow.

With Celery these tasks run in a background worker process:
- The page responds instantly to the user
- Notifications are created a second or two later in the background
- Under heavy load (300 users), this prevents web workers from being
  blocked by notification logic
"""
from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def send_notification(self, recipient_id, title, message,
                      notification_type='GENERAL', priority='NORMAL', link=None):
    """
    Create a single in-app notification in the background.
    Safe to retry up to 3 times if the DB is temporarily unavailable.
    """
    try:
        from apps.notifications.models import Notification
        from apps.accounts.models import User
        recipient = User.objects.get(pk=recipient_id)
        Notification.objects.create(
            recipient=recipient,
            title=title,
            message=message,
            notification_type=notification_type,
            priority=priority,
            link=link or '',
        )
    except Exception as exc:
        logger.error(f'send_notification failed for user {recipient_id}: {exc}')
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def send_bulk_notifications(self, recipient_ids, title, message,
                             notification_type='GENERAL', priority='NORMAL', link=None):
    """
    Create notifications for multiple recipients at once using bulk_create.
    Much faster than calling send_notification() N times — 1 DB INSERT
    instead of N inserts.
    """
    try:
        from apps.notifications.models import Notification
        from apps.accounts.models import User
        recipients = User.objects.filter(pk__in=recipient_ids, is_active=True)
        Notification.objects.bulk_create([
            Notification(
                recipient=r,
                title=title,
                message=message,
                notification_type=notification_type,
                priority=priority,
                link=link or '',
            )
            for r in recipients
        ])
    except Exception as exc:
        logger.error(f'send_bulk_notifications failed: {exc}')
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def notify_low_stock(self, drug_name, current_quantity, threshold, drug_id=None):
    """
    Alert pharmacy and admin staff when a drug stock falls below threshold.
    Runs as a background task so stock checks don't slow down dispensing.
    """
    try:
        from apps.accounts.models import User
        from apps.notifications.models import NotificationType, NotificationPriority

        # Notify all pharmacy staff and admins
        staff = User.objects.filter(
            is_active=True,
            role__in=['PHARMACIST', 'SUPER_ADMIN', 'ADMIN'],
        )
        link = f'/pharmacy/drugs/{drug_id}/' if drug_id else '/pharmacy/'
        Notification.objects.bulk_create([
            __import__('apps.notifications.models', fromlist=['Notification']).Notification(
                recipient=u,
                title=f'Low Stock: {drug_name}',
                message=f'{drug_name} has only {current_quantity} units remaining (threshold: {threshold}).',
                notification_type=NotificationType.LOW_STOCK,
                priority=NotificationPriority.HIGH,
                link=link,
            )
            for u in staff
        ])
    except Exception as exc:
        logger.error(f'notify_low_stock failed: {exc}')
        raise self.retry(exc=exc)


# ── SMS / WhatsApp outbound tasks ─────────────────────────────────────────────

@shared_task(name='notifications.send_appointment_reminders')
def send_appointment_reminders_task():
    """
    Send SMS reminders for appointments tomorrow.
    Schedule via Celery Beat: every day at 07:00 Africa/Douala.
    """
    from datetime import timedelta
    from django.utils import timezone
    from apps.appointments.models import Appointment
    from .utils import notify_patient_sms, notify_patient_whatsapp

    tomorrow = timezone.localdate() + timedelta(days=1)
    upcoming = Appointment.objects.filter(
        appointment_date=tomorrow,
        status__in=['SCHEDULED', 'CONFIRMED'],
        reminder_sent=False,
        is_deleted=False,
    ).select_related('patient', 'doctor', 'department')

    sent = 0
    for appt in upcoming:
        doctor_name = appt.doctor.get_full_name() if appt.doctor else 'your doctor'
        dept = appt.department.name if appt.department else 'the clinic'
        time_str = appt.appointment_time.strftime('%I:%M %p')
        msg = (
            f"Reminder: You have an appointment at {dept} tomorrow "
            f"{tomorrow.strftime('%d %b %Y')} at {time_str} with {doctor_name}. "
            f"Please arrive 15 min early. Ref: {appt.appointment_number}."
        )
        notify_patient_sms(appt.patient, msg)
        notify_patient_whatsapp(appt.patient, msg)
        appt.reminder_sent = True
        appt.save(update_fields=['reminder_sent'])
        sent += 1

    logger.info(f'[appointment_reminders] {sent} reminders sent for {tomorrow}')
    return sent


@shared_task(name='notifications.notify_invoice_ready_sms')
def notify_invoice_ready_sms(invoice_id):
    """SMS patient when invoice is generated."""
    from apps.billing.models import Invoice
    from .utils import notify_patient_sms

    try:
        invoice = Invoice.objects.select_related('patient').get(id=invoice_id, is_deleted=False)
    except Invoice.DoesNotExist:
        return

    total = f"{invoice.total:,.0f}"
    share = f"{invoice.patient_amount:,.0f}"
    if invoice.insurance_amount > 0:
        msg = (
            f"Invoice {invoice.invoice_number} ready. "
            f"Total: {total} FCFA | Your share: {share} FCFA. "
            f"Please proceed to the cashier."
        )
    else:
        msg = (
            f"Invoice {invoice.invoice_number} ready. "
            f"Amount due: {total} FCFA. Please proceed to the cashier."
        )
    notify_patient_sms(invoice.patient, msg)


@shared_task(name='notifications.notify_lab_result_sms')
def notify_lab_result_sms(order_id):
    """SMS patient when lab results are ready for collection."""
    from apps.laboratory.models import LabOrder
    from .utils import notify_patient_sms

    try:
        order = LabOrder.objects.select_related('patient').get(id=order_id, is_deleted=False)
    except Exception:
        return

    msg = (
        f"Your lab results (Order: {order.order_number}) are ready. "
        f"Please collect at the laboratory with your receipt."
    )
    notify_patient_sms(order.patient, msg)


@shared_task(name='notifications.notify_prescription_ready_sms')
def notify_prescription_ready_sms(patient_id, ref=''):
    """SMS patient when prescription is dispensed and ready."""
    from apps.patients.models import Patient
    from .utils import notify_patient_sms

    try:
        patient = Patient.objects.get(id=patient_id, is_deleted=False)
    except Patient.DoesNotExist:
        return

    ref_text = f" (Ref: {ref})" if ref else ''
    msg = f"Your prescription{ref_text} is ready at the pharmacy counter."
    notify_patient_sms(patient, msg)


@shared_task(name='notifications.daily_inventory_alerts')
def daily_inventory_alerts():
    """
    Check inventory and alert admin if items are below reorder level.
    Schedule via Celery Beat: every day at 08:00 Africa/Douala.
    """
    from apps.inventory.models import InventoryItem
    from apps.accounts.models import User, UserRole
    from apps.notifications.models import Notification, NotificationType, NotificationPriority

    low_items = [
        i for i in InventoryItem.objects.filter(is_active=True, is_deleted=False)
        if i.needs_reorder
    ]
    if not low_items:
        return 0

    managers = User.objects.filter(
        role__in=[UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR],
        is_active=True,
    )
    names = ', '.join(f"{i.name} ({i.current_stock} left)" for i in low_items[:8])
    Notification.objects.bulk_create([
        Notification(
            recipient=u,
            title=f'{len(low_items)} inventory items need reordering',
            message=names,
            notification_type=NotificationType.LOW_STOCK,
            priority=NotificationPriority.HIGH,
            link='/inventory/items/?low_stock=1',
        )
        for u in managers
    ])
    return len(low_items)
