"""
Auto-routing: programmatic patient routing triggered by service completion.

Called from signal handlers when:
  - Investigation result is verified      → route back to doctor
  - Lab order is fully completed          → route back to doctor
  - Drug prescription is dispensed        → route back to doctor
  - Optical prescription is dispensed     → route back to doctor

Safe to call from any context — swallows all exceptions so it never
blocks a save operation.
"""
import logging

logger = logging.getLogger('ehr.auto_routing')

# ── Visit statuses that mean "patient is at a downstream service" ──────────────
_DOWNSTREAM_STATUSES = {
    'INVESTIGATION': 'investigation',
    'LABORATORY':    'laboratory',
    'PHARMACY':      'pharmacy',
    'OPTICAL':       'optical',
}

# Map doctor department code → QMS service type for their queue
_DOCTOR_DEPT_TO_QMS = {
    'GEN_OPH':    'GENERAL',
    'RETINA':     'RETINA',
    'GLAUC':      'GLAUCOMA',
    'PEDS_OPH':   'PEDIATRIC',
    'PEDS_REFRAC':'REFRACTION',
    'REFRAC':     'REFRACTION',
    'CORNEA':     'CORNEA',
    'UVEITIS':    'UVEITIS',
    'NEURO_OPH':  'NEURO',
    'OCULOPLASTY':'OCULOPLASTY',
    'LOW_VIS':    'LOW_VISION',
    'ORTHO':      'GENERAL',
    'CATARACT':   'CATARACT',
    'GEN_PHYS':   'GEN_PHYS',
}


def _qms_active():
    try:
        from apps.core.context_processors import qms_active as _qa
        from django.http import HttpRequest
        return _qa(HttpRequest()).get('qms_active', False)
    except Exception:
        try:
            from apps.patients.models import HospitalConfig
            return HospitalConfig.get().module_qms
        except Exception:
            return False


def _get_doctor_qms_service(doctor, visit):
    """
    Determine which QMS service type the doctor's queue belongs to.
    Respects consultation_unit for GEN_OPH (Standard / Express / VIP / Insurance).
    """
    dept = getattr(doctor, 'department', None)
    dept_code = (
        getattr(doctor, 'role_department_code', None)
        or (dept.code if dept else None)
    )
    service = _DOCTOR_DEPT_TO_QMS.get(dept_code, 'GENERAL')

    # For GEN_OPH doctors, use consultation_unit to pick the right tier queue
    if service == 'GENERAL':
        cu = (getattr(doctor, 'consultation_unit', '') or 'GENERAL').upper()
        service = {
            'GENERAL':      'GENERAL',
            'EXP_CONSULT':  'EXP_CONSULT',
            'VIP_CONSULT':  'VIP_CONSULT',
            'INSUR_CONSULT':'INSUR_CONSULT',
        }.get(cu, 'GENERAL')

        # Also honour the patient's service tier
        tier = getattr(visit, 'service_tier', 'STANDARD') or 'STANDARD'
        if service == 'GENERAL' and tier == 'VIP':
            service = 'VIP_CONSULT'
        elif service == 'GENERAL' and tier in ('EXPRESS', 'FAST_TRACK'):
            service = 'EXP_CONSULT'

    return service


def route_back_to_doctor(visit, reason='Results ready'):
    """
    Route the patient back to their doctor's queue after a downstream
    service (investigation, lab, pharmacy, optical) is complete.

    Args:
        visit:  The active Visit object.
        reason: Human-readable reason string (shown in QMS token notes).

    Returns True if routing was performed, False if skipped/failed.
    """
    try:
        if visit is None:
            return False

        # Find the doctor — use attending_doctor if set, else the most
        # recent IN_PROGRESS consultation's consulting_doctor for today.
        from django.utils import timezone
        today = timezone.localdate()

        doctor = getattr(visit, 'attending_doctor', None)
        if not doctor:
            from apps.consultations.models import Consultation
            consult = (
                Consultation.objects
                .filter(visit=visit, is_deleted=False)
                .select_related('consulting_doctor')
                .order_by('-consultation_date')
                .first()
            )
            if consult:
                doctor = consult.consulting_doctor

        if not doctor:
            logger.warning('auto_routing: no doctor found for visit %s', visit.pk)
            return False

        # Determine target QMS service
        qms_service = _get_doctor_qms_service(doctor, visit)

        # Map QMS service back to a visit status
        _svc_to_visit_status = {
            'GENERAL':       'WAITING',
            'EXP_CONSULT':   'WAITING',
            'VIP_CONSULT':   'WAITING',
            'INSUR_CONSULT': 'WAITING',
            'RETINA':        'AT_RETINA',
            'GLAUCOMA':      'AT_GLAUCOMA',
            'PEDIATRIC':     'AT_PEDIATRIC',
            'REFRACTION':    'REFRACTION',
            'CORNEA':        'AT_CORNEA',
            'UVEITIS':       'UVEITIS',
            'NEURO':         'AT_NEURO',
            'OCULOPLASTY':   'AT_OCULOPLASTY',
            'LOW_VISION':    'WAITING',
            'CATARACT':      'AT_CATARACT',
            'GEN_PHYS':      'WAITING',
        }
        new_visit_status = _svc_to_visit_status.get(qms_service, 'WAITING')

        # Update visit status + route department back to the doctor's dept
        visit.status = new_visit_status
        save_fields = ['status', 'updated_at']

        dept = getattr(doctor, 'department', None)
        if dept:
            visit.department = dept
            save_fields.append('department')

        visit.save(update_fields=save_fields)

        # Issue a QMS token if QMS is active
        if _qms_active():
            try:
                from apps.qms.models import (
                    QueueToken, TokenStatus, IssuancePoint,
                    TIER_PRIORITY, DailyTokenSequence,
                )
                from django.db import transaction as _tx

                tier = getattr(visit, 'service_tier', 'STANDARD') or 'STANDARD'

                with _tx.atomic():
                    already_waiting = QueueToken.objects.filter(
                        patient=visit.patient,
                        service_type=qms_service,
                        token_date=today,
                        status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                        is_deleted=False,
                    ).exists()

                    if not already_waiting:
                        token_number = DailyTokenSequence.next_dept_token(qms_service)
                        QueueToken.objects.create(
                            token_number=token_number,
                            patient=visit.patient,
                            visit=visit,
                            patient_name=visit.patient.full_name,
                            service_type=qms_service,
                            service_tier=tier,
                            issuance_point=IssuancePoint.SYSTEM,
                            priority=TIER_PRIORITY.get(tier, 0),
                            assigned_doctor=doctor,
                            notes=f'Auto-routed: {reason}',
                        )
            except Exception:
                logger.exception('auto_routing: QMS token creation failed for visit %s', visit.pk)

        logger.info(
            'auto_routing: visit=%s patient=%s → %s (%s)',
            visit.pk, visit.patient.full_name, qms_service, reason,
        )
        return True

    except Exception:
        logger.exception('auto_routing: unexpected error for visit %s', getattr(visit, 'pk', '?'))
        return False
