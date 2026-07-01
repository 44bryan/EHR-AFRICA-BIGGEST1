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


def hospital_modules(request):
    """Inject active-module flags into every template as `modules`."""
    try:
        from apps.accounts.models import HospitalConfig
        cfg = HospitalConfig.get()
    except Exception:
        cfg = None
    return {'modules': cfg}


def qms_active():
    """
    Returns True if the Queue Management System module is enabled.
    Import this anywhere in views: `from apps.core.context_processors import qms_active`
    When QMS is disabled, all token creation and queue reads should be skipped.
    """
    try:
        from apps.accounts.models import HospitalConfig
        return HospitalConfig.get().module_qms
    except Exception:
        return True  # default to enabled if config is unavailable


def session_slot(request):
    """Inject current session slot (1-9) and slot list for the topbar switcher."""
    slot = getattr(request, 'session_slot', '1')
    return {
        'session_slot': slot,
        'session_slots': [str(i) for i in range(1, 6)],
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
