"""
Notification creation helpers — call these from clinical event handlers.
"""
from .models import Notification, NotificationType, NotificationPriority


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
            link=f'/lab/{lab_order.id}/',
            notification_type=NotificationType.LAB_RESULT,
            priority=NotificationPriority.NORMAL,
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
