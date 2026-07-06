"""
Role-based access control decorators for GLUDD EHR views.

Usage:
    @role_required('doctor')           # any doctor role
    @role_required('clinical')         # doctors + nurses
    @role_required(['super_admin', 'medical_director'])  # explicit list
    @clinical_staff_required           # shorthand: doctors + nurses + allied health
    @doctor_required                   # shorthand: doctors only
    @admin_staff_required              # shorthand: admin roles
"""
import logging
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.http import HttpResponseForbidden

from apps.accounts.models import UserRole

security_logger = logging.getLogger('ehr.security')

# Groups that map to role sets
_ROLE_GROUPS = {
    'doctor': list(UserRole) and None,   # resolved dynamically below
    'nurse':  None,
    'admin':  None,
    'clinical': None,
    'all_staff': None,
}

# ── Roles that can VIEW patient records (read-only access) ───────────────────
CAN_VIEW_PATIENT = (
    # Leadership / admin oversight
    UserRole.SUPER_ADMIN,
    UserRole.CEO,
    UserRole.ADMIN_DIRECTOR,
    UserRole.MEDICAL_DIRECTOR,
    # Clinical — doctors
    UserRole.OPHTHALMOLOGIST,
    UserRole.RETINA_SPECIALIST,
    UserRole.GLAUCOMA_SPECIALIST,
    UserRole.PEDIATRIC_OPHTHALMOLOGIST,
    UserRole.PEDIATRIC_REFRACTIONIST,
    UserRole.CATARACT_SURGEON,
    UserRole.CORNEA_SPECIALIST,
    UserRole.OCULOPLASTICS_SURGEON,
    UserRole.NEURO_OPHTHALMOLOGIST,
    UserRole.UVEITIS_SPECIALIST,
    UserRole.OPTOMETRIST,
    UserRole.LOW_VISION_SPECIALIST,
    UserRole.INTERN,
    UserRole.ANAESTHETIST,
    UserRole.ORTHOPTIST,
    UserRole.GENERAL_PHYSICIAN,
    # Clinical — nursing & paramedical
    UserRole.NURSE,
    UserRole.THEATRE_NURSE,
    UserRole.WARD_NURSE,
    UserRole.COUNSELING_NURSE,
    UserRole.CONSULTATION_NURSE,
    UserRole.INVESTIGATION_TECHNICIAN,
    UserRole.LAB_TECHNICIAN,
    # Clinical — dispensing (tab-restricted to prescriptions/medications only)
    UserRole.PHARMACIST,
    UserRole.OPTICAL_DISPENSER,
    # Admin — patient-facing (tab-restricted to demographics/insurance)
    UserRole.RECEPTIONIST,
    UserRole.ADMISSION_OFFICER,
    UserRole.MEDICAL_RECORDS,
    # Billing — invoice/patient lookup
    UserRole.BILLING_OFFICER,
    UserRole.CASHIER,
    UserRole.CHIEF_CASHIER,
    UserRole.ACCOUNTANT,
    UserRole.SENIOR_ACCOUNTANT,
    UserRole.FINANCE_DIRECTOR,
)

# ── Roles that can CREATE consultations ─────────────────────────────────────
CAN_CREATE_CONSULTATION = (
    UserRole.SUPER_ADMIN,
    UserRole.MEDICAL_DIRECTOR,
    UserRole.OPHTHALMOLOGIST,
    UserRole.RETINA_SPECIALIST,
    UserRole.GLAUCOMA_SPECIALIST,
    UserRole.PEDIATRIC_OPHTHALMOLOGIST,
    UserRole.PEDIATRIC_REFRACTIONIST,
    UserRole.CATARACT_SURGEON,
    UserRole.CORNEA_SPECIALIST,
    UserRole.OCULOPLASTICS_SURGEON,
    UserRole.NEURO_OPHTHALMOLOGIST,
    UserRole.UVEITIS_SPECIALIST,
    UserRole.OPTOMETRIST,
    UserRole.LOW_VISION_SPECIALIST,
    UserRole.INTERN,
    UserRole.GENERAL_PHYSICIAN,
)

# ── Roles that can EDIT / MANAGE visits ─────────────────────────────────────
CAN_MANAGE_VISIT = (
    UserRole.SUPER_ADMIN,
    UserRole.MEDICAL_DIRECTOR,
    UserRole.NURSE,
    UserRole.THEATRE_NURSE,
    UserRole.WARD_NURSE,
    UserRole.COUNSELING_NURSE,
    UserRole.RECEPTIONIST,
    UserRole.CASHIER,
    UserRole.ADMISSION_OFFICER,
    UserRole.OPHTHALMOLOGIST,
    UserRole.RETINA_SPECIALIST,
    UserRole.GLAUCOMA_SPECIALIST,
    UserRole.PEDIATRIC_OPHTHALMOLOGIST,
    UserRole.PEDIATRIC_REFRACTIONIST,
    UserRole.CATARACT_SURGEON,
    UserRole.CORNEA_SPECIALIST,
    UserRole.OCULOPLASTICS_SURGEON,
    UserRole.NEURO_OPHTHALMOLOGIST,
    UserRole.UVEITIS_SPECIALIST,
    UserRole.OPTOMETRIST,
    UserRole.LOW_VISION_SPECIALIST,
    UserRole.INTERN,
    UserRole.GENERAL_PHYSICIAN,
)

# ── Roles that can access billing ────────────────────────────────────────────
CAN_MANAGE_BILLING = (
    UserRole.SUPER_ADMIN,
    UserRole.MEDICAL_DIRECTOR,
    UserRole.BILLING_OFFICER,
    UserRole.CASHIER,
    UserRole.CHIEF_CASHIER,
    UserRole.ACCOUNTANT,
    UserRole.SENIOR_ACCOUNTANT,
    UserRole.RECEPTIONIST,
    UserRole.ADMIN,
    UserRole.ADMIN_DIRECTOR,
    UserRole.CEO,
    UserRole.FINANCE_DIRECTOR,
)

# ── Roles that can access QMS / queue management ─────────────────────────────
CAN_MANAGE_QMS = (
    UserRole.SUPER_ADMIN,
    UserRole.MEDICAL_DIRECTOR,
    UserRole.NURSE,
    UserRole.RECEPTIONIST,
    UserRole.CASHIER,
    UserRole.GATEKEEPER,
    UserRole.ADMIN,
    UserRole.OPHTHALMOLOGIST,
    UserRole.RETINA_SPECIALIST,
    UserRole.GLAUCOMA_SPECIALIST,
    UserRole.PEDIATRIC_OPHTHALMOLOGIST,
    UserRole.CATARACT_SURGEON,
    UserRole.CORNEA_SPECIALIST,
    UserRole.OCULOPLASTICS_SURGEON,
    UserRole.NEURO_OPHTHALMOLOGIST,
    UserRole.UVEITIS_SPECIALIST,
    UserRole.OPTOMETRIST,
    UserRole.INTERN,
    UserRole.INVESTIGATION_TECHNICIAN,
    UserRole.LAB_TECHNICIAN,
    UserRole.PHARMACIST,
    UserRole.OPTICAL_DISPENSER,
    UserRole.ADMISSION_OFFICER,
    UserRole.THEATRE_NURSE,
    UserRole.WARD_NURSE,
    UserRole.COUNSELING_NURSE,
)


def _forbidden_response(request, message=None):
    """Return 403 for AJAX; redirect + flash message for normal requests."""
    msg = message or "You do not have permission to access this page."
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        from django.http import JsonResponse
        return JsonResponse({'error': msg}, status=403)
    messages.error(request, msg)
    return redirect('dashboard:home')


def role_required(allowed_roles):
    """
    Decorator that restricts view access to specific roles.

    allowed_roles can be:
    - a tuple/list of UserRole values: ('super_admin', 'medical_director')
    - one of the shorthand strings: 'doctor', 'nurse', 'admin', 'clinical'
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('accounts:login')

            user = request.user
            role = getattr(user, 'role', None)

            # Resolve shorthand
            if allowed_roles == 'doctor':
                permitted = set(CAN_CREATE_CONSULTATION)
            elif allowed_roles == 'clinical':
                permitted = set(CAN_VIEW_PATIENT)
            elif allowed_roles == 'admin':
                permitted = set(CAN_MANAGE_BILLING)
            elif allowed_roles == 'billing':
                permitted = set(CAN_MANAGE_BILLING)
            elif allowed_roles == 'qms':
                permitted = set(CAN_MANAGE_QMS)
            else:
                permitted = set(allowed_roles)

            if role not in permitted:
                security_logger.warning(
                    'ACCESS_DENIED user=%s role=%s path=%s',
                    getattr(user, 'employee_id', user.pk),
                    role,
                    request.path,
                )
                return _forbidden_response(
                    request,
                    f"Your role ({user.get_role_display()}) does not permit access to this area."
                )

            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


# ── Shorthand decorators ─────────────────────────────────────────────────────

def doctor_required(view_func):
    """Only clinical staff who create consultations."""
    return role_required(CAN_CREATE_CONSULTATION)(view_func)


def clinical_staff_required(view_func):
    """Anyone who can view patient records."""
    return role_required(CAN_VIEW_PATIENT)(view_func)


def admin_staff_required(view_func):
    """Admin / billing / front-desk staff."""
    return role_required(CAN_MANAGE_BILLING)(view_func)


def billing_required(view_func):
    return role_required(CAN_MANAGE_BILLING)(view_func)


def qms_required(view_func):
    return role_required(CAN_MANAGE_QMS)(view_func)
