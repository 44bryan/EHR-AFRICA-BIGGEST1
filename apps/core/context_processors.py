"""
Global template context processors.
"""
from django.conf import settings
from django.core.cache import cache


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
    """Inject active-module flags into every template as `modules`.
    Cached for 60 s — HospitalConfig rarely changes mid-session.
    """
    cfg = cache.get('hospital_config_obj')
    if cfg is None:
        try:
            from apps.accounts.models import HospitalConfig
            cfg = HospitalConfig.get()
            cache.set('hospital_config_obj', cfg, 60)
        except Exception:
            cfg = None
    return {'modules': cfg}


def qms_active():
    """
    Returns True if the Queue Management System module is enabled.
    Import this anywhere in views: `from apps.core.context_processors import qms_active`
    When QMS is disabled, all token creation and queue reads should be skipped.
    Cached for 60 s to avoid a DB hit on every single view.
    """
    result = cache.get('qms_active_flag')
    if result is None:
        try:
            from apps.accounts.models import HospitalConfig
            result = HospitalConfig.get().module_qms
        except Exception:
            result = True  # default to enabled if config is unavailable
        cache.set('qms_active_flag', result, 60)
    return result


def session_slot(request):
    """Inject current session slot (1-9) and slot list for the topbar switcher."""
    slot = getattr(request, 'session_slot', '1')
    return {
        'session_slot': slot,
        'session_slots': [str(i) for i in range(1, 6)],
    }


def user_notifications(request):
    """Inject unread notification count for authenticated users.
    Cached per user for 30 s — badge updates are not real-time critical.
    """
    if not request.user.is_authenticated:
        return {'unread_notifications_count': 0}
    cache_key = f'notif_count_{request.user.pk}'
    count = cache.get(cache_key)
    if count is None:
        try:
            from apps.notifications.models import Notification
            count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        except Exception:
            count = 0
        cache.set(cache_key, count, 30)
    return {'unread_notifications_count': count}


def doctor_assigned_room(request):
    """
    Inject the consultation room currently assigned to the logged-in doctor.
    Available in every template as `my_room` (None if not a doctor or no room today).
    Cached per user for 60 s — room assignments don't change per-request.
    """
    if not request.user.is_authenticated:
        return {'my_room': None}
    try:
        from apps.accounts.models import UserRole
        clinical_roles = [
            UserRole.OPHTHALMOLOGIST, UserRole.MEDICAL_DIRECTOR,
            UserRole.RETINA_SPECIALIST, UserRole.GLAUCOMA_SPECIALIST,
            UserRole.PEDIATRIC_OPHTHALMOLOGIST, UserRole.CATARACT_SURGEON,
            UserRole.CORNEA_SPECIALIST, UserRole.OCULOPLASTICS_SURGEON,
            UserRole.NEURO_OPHTHALMOLOGIST, UserRole.UVEITIS_SPECIALIST,
            UserRole.OPTOMETRIST, UserRole.LOW_VISION_SPECIALIST,
            UserRole.ORTHOPTIST, UserRole.PEDIATRIC_REFRACTIONIST,
            UserRole.INTERN, UserRole.GENERAL_PHYSICIAN,
        ]
        if request.user.role not in clinical_roles:
            return {'my_room': None}
        cache_key = f'doctor_room_{request.user.pk}'
        room = cache.get(cache_key)
        if room is None:
            from apps.departments.models import ConsultationRoom
            room = ConsultationRoom.objects.filter(
                assigned_doctor=request.user, is_active=True
            ).select_related('department').first()
            # Cache None as a sentinel so we don't re-query for unassigned doctors
            cache.set(cache_key, room or 'NONE', 60)
        if room == 'NONE':
            room = None
        return {'my_room': room}
    except Exception:
        return {'my_room': None}
