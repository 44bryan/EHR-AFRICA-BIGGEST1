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
