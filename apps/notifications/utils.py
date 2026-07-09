"""
Notification creation helpers — call these from clinical event handlers.

Outbound channels:
  1. In-app  → notify() / notify_role()
  2. SMS     → send_sms(phone, message)
  3. WhatsApp→ send_whatsapp(phone, message)

Twilio is used for SMS and WhatsApp.
Set SMS_ENABLED=True and TWILIO_* env vars to activate outbound messages.
When SMS_ENABLED=False the functions log the message instead of sending it
(safe default for development and staging).
"""
import logging
from django.conf import settings
from .models import Notification, NotificationType, NotificationPriority

logger = logging.getLogger(__name__)


# ── Outbound SMS / WhatsApp ────────────────────────────────────────────────────

def _twilio_client():
    """Return a Twilio REST client, or None if not configured."""
    sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
    token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
    if not sid or not token or sid.startswith('AC' + 'x'):
        return None
    try:
        from twilio.rest import Client
        return Client(sid, token)
    except ImportError:
        logger.warning('twilio package not installed. Run: pip install twilio')
        return None


def send_sms(to_number: str, message: str) -> bool:
    """
    Send an SMS via Twilio.
    Returns True if sent, False if disabled or failed.
    `to_number` should be E.164 format, e.g. '+237600000000'
    """
    if not getattr(settings, 'SMS_ENABLED', False):
        logger.info(f'[SMS disabled] To={to_number}: {message[:80]}')
        return False
    client = _twilio_client()
    if not client:
        logger.warning(f'[SMS] Twilio not configured. Would send to {to_number}')
        return False
    try:
        msg = client.messages.create(
            body=message,
            from_=settings.TWILIO_FROM_NUMBER,
            to=to_number,
        )
        logger.info(f'[SMS] Sent SID={msg.sid} to={to_number}')
        return True
    except Exception as exc:
        logger.error(f'[SMS] Failed to send to {to_number}: {exc}')
        return False


def send_whatsapp(to_number: str, message: str) -> bool:
    """
    Send a WhatsApp message via Twilio.
    `to_number` can be '+237600000000' (prefix is added automatically).
    """
    if not getattr(settings, 'SMS_ENABLED', False):
        logger.info(f'[WhatsApp disabled] To={to_number}: {message[:80]}')
        return False
    client = _twilio_client()
    if not client:
        logger.warning(f'[WhatsApp] Twilio not configured. Would send to {to_number}')
        return False
    wa_to = f'whatsapp:{to_number}' if not to_number.startswith('whatsapp:') else to_number
    wa_from = getattr(settings, 'TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886')
    try:
        msg = client.messages.create(body=message, from_=wa_from, to=wa_to)
        logger.info(f'[WhatsApp] Sent SID={msg.sid} to={wa_to}')
        return True
    except Exception as exc:
        logger.error(f'[WhatsApp] Failed to send to {wa_to}: {exc}')
        return False


def notify_patient_sms(patient, message: str):
    """
    Send an SMS to a patient using their phone number.
    Silently skips if patient has no phone number.
    """
    phone = getattr(patient, 'phone_number', None)
    if not phone:
        return
    phone_str = str(phone)
    send_sms(phone_str, message)


def notify_patient_whatsapp(patient, message: str):
    """
    Send a WhatsApp message to a patient using their phone number.
    """
    phone = getattr(patient, 'phone_number', None)
    if not phone:
        return
    send_whatsapp(str(phone), message)


def notify(recipient, title, message='', link='',
           notification_type=NotificationType.GENERAL,
           priority=NotificationPriority.NORMAL):
    """Create a notification for a single user."""
    return Notification.objects.create(
        recipient=recipient,
        title=title,
        message=message,
        link=link,
        notification_type=notification_type,
        priority=priority,
    )


def notify_role(role, title, message='', link='',
                notification_type=NotificationType.GENERAL,
                priority=NotificationPriority.NORMAL):
    """Create a notification for all active users with the given role."""
    from apps.accounts.models import User
    users = User.objects.filter(role=role, is_active=True)
    notifications = [
        Notification(
            recipient=u, title=title, message=message, link=link,
            notification_type=notification_type, priority=priority,
        )
        for u in users
    ]
    Notification.objects.bulk_create(notifications)


def notify_lab_result_ready(lab_order):
    """Notify the ordering doctor that a lab result is ready."""
    doctor = getattr(lab_order, 'ordered_by', None)
    if doctor:
        notify(
            recipient=doctor,
            title=f'Lab result ready: {lab_order.patient.full_name}',
            message=f'Lab order #{lab_order.order_number} results are now available.',
            link=f'/laboratory/{lab_order.id}/',
            notification_type=NotificationType.LAB_RESULT,
            priority=NotificationPriority.NORMAL,
        )


def notify_critical_lab_result(lab_result):
    """Notify ordering doctor + medical directors when a critical lab result is saved."""
    order = lab_result.order_item.order
    doctor = getattr(order, 'ordered_by', None)
    test_name = lab_result.order_item.test_type.name
    patient_name = order.patient.full_name
    link = f'/laboratory/{order.id}/'
    title = f'CRITICAL LAB RESULT — {patient_name}'
    message = (f'{test_name}: {lab_result.result_value} {lab_result.result_unit} '
               f'[{lab_result.reference_range}] — CRITICAL VALUE')
    if doctor:
        notify(
            recipient=doctor,
            title=title,
            message=message,
            link=link,
            notification_type=NotificationType.LAB_RESULT,
            priority=NotificationPriority.URGENT,
        )
    from apps.accounts.models import UserRole
    notify_role(
        role=UserRole.MEDICAL_DIRECTOR,
        title=title,
        message=message,
        link=link,
        notification_type=NotificationType.LAB_RESULT,
        priority=NotificationPriority.URGENT,
    )


def notify_low_stock(drug):
    """Notify pharmacists when drug stock falls to reorder level."""
    from apps.accounts.models import UserRole
    notify_role(
        role=UserRole.PHARMACIST,
        title=f'Low stock: {drug.name}',
        message=f'{drug.name} has only {drug.current_stock} units remaining (reorder level: {drug.reorder_level}).',
        link='/pharmacy/drugs/',
        notification_type=NotificationType.LOW_STOCK,
        priority=NotificationPriority.HIGH,
    )
