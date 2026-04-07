"""
Global template context processors.
"""
from django.conf import settings


def hospital_settings(request):
    """Inject hospital branding into every template."""
    return {
        'HOSPITAL_NAME': settings.HOSPITAL_NAME,
        'HOSPITAL_ADDRESS': settings.HOSPITAL_ADDRESS,
        'HOSPITAL_PHONE': settings.HOSPITAL_PHONE,
        'HOSPITAL_EMAIL': settings.HOSPITAL_EMAIL,
        'HOSPITAL_WEBSITE': settings.HOSPITAL_WEBSITE,
        'HOSPITAL_COUNTRY': getattr(settings, 'HOSPITAL_COUNTRY', 'Cameroon'),
        'HOSPITAL_CITY': getattr(settings, 'HOSPITAL_CITY', 'Yaoundé'),
        'CURRENCY': 'FCFA',
        'CURRENCY_CODE': 'XAF',
    }


def user_notifications(request):
    """Inject unread notification count for authenticated users."""
    if not request.user.is_authenticated:
        return {'unread_notifications_count': 0}
    try:
        from apps.notifications.models import Notification
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    except Exception:
        count = 0
    return {'unread_notifications_count': count}
