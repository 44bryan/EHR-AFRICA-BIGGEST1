"""
Patient flow helpers — shared across lab, investigations, and other modules.
Do NOT import Django models at module level here (circular import risk).
"""
from apps.core.context_processors import qms_active as _qms_active
from apps.core.ws_notify import notify_queue as _ws_notify


# Map visit status → QMS service_type(s) to close when leaving that stage
_STATUS_TO_TOKEN_TYPES = {
    'PARAMETERS':       ['PARAMETERS', 'PARAMS_VIP'],
    'TRIAGE':           ['PARAMETERS', 'PARAMS_VIP'],
    'WAITING':          ['GENERAL', 'EXP_CONSULT', 'VIP_CONSULT', 'GEN_PHYS'],
    'IN_CONSULTATION':  ['GENERAL', 'EXP_CONSULT', 'VIP_CONSULT', 'GEN_PHYS'],
    'AT_CASHIER':       ['CASHIER'],
    'REFRACTION':       ['REFRACTION'],
    'AT_RETINA':        ['RETINA'],
    'AT_GLAUCOMA':      ['GLAUCOMA'],
    'AT_CATARACT':      ['CATARACT'],
    'AT_PEDIATRIC':     ['PEDIATRIC'],
    'AT_NEURO':         ['NEURO'],
    'AT_OCULOPLASTY':   ['OCULOPLASTY'],
    'AT_CORNEA':        ['CORNEA'],
    'UVEITIS':          ['UVEITIS'],
    'INVESTIGATION':    ['INVEST'],
    'LABORATORY':       ['LAB'],
    'PHARMACY':         ['PHARMACY'],
    'OPTICAL':          ['OPTICAL'],
    'BILLING':          ['CASHIER'],
}


def close_stage_token(patient, prev_status, today=None):
    """
    Close any active QMS token for the stage the patient is leaving.
    Call this BEFORE updating visit.status so prev_status is the old value.
    Safe to call even if QMS is off or no token exists.
    """
    if not _qms_active() or not patient or not prev_status:
        return
    service_types = _STATUS_TO_TOKEN_TYPES.get(prev_status)
    if not service_types:
        return
    try:
        from apps.qms.models import QueueToken, TokenStatus
        from django.utils import timezone as _tz
        _today = today or _tz.localdate()
        QueueToken.objects.filter(
            patient=patient,
            token_date=_today,
            service_type__in=service_types,
            status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
            is_deleted=False,
        ).update(status=TokenStatus.COMPLETED)
    except Exception:
        pass


# Map visit status → WebSocket room(s) to notify after routing
_STATUS_ROOMS = {
    # ── Entry ──────────────────────────────────────────────────────────
    'REGISTERED':        ['opd'],
    'AT_RECEPTIONIST':   ['opd'],
    'AT_CASHIER':        ['cashier'],
    # ── Triage ─────────────────────────────────────────────────────────
    'PARAMETERS':        ['opd'],
    'TRIAGE':            ['opd'],
    # ── Doctor queue ───────────────────────────────────────────────────
    'WAITING':           ['opd', 'workstation'],
    'IN_CONSULTATION':   ['workstation'],
    'INSURANCE_CONSULT': ['workstation'],
    # ── Specialties — all land on workstation ───────────────────────────
    'REFRACTION':        ['workstation'],
    'UVEITIS':           ['workstation'],
    'AT_RETINA':         ['workstation'],
    'AT_GLAUCOMA':       ['workstation'],
    'AT_CATARACT':       ['workstation'],
    'AT_PEDIATRIC':      ['workstation'],
    'AT_NEURO':          ['workstation'],
    'AT_OCULOPLASTY':    ['workstation'],
    'AT_CORNEA':         ['workstation'],
    # ── Diagnostics ────────────────────────────────────────────────────
    'LABORATORY':        ['lab'],
    'INVESTIGATION':     ['invest'],
    # ── Dispensing / optical ────────────────────────────────────────────
    'PHARMACY':          ['pharmacy'],
    'OPTICAL':           ['workstation'],
    # ── Surgical pathway ────────────────────────────────────────────────
    'COUNSELING':        ['workstation'],
    'WAITING_ADMISSION': ['workstation'],
    'ADMITTED':          ['workstation'],
    'PRE_OP':            ['workstation'],
    'IN_THEATRE':        ['workstation'],
    'POST_OP':           ['workstation'],
    # ── Billing / end ───────────────────────────────────────────────────
    'BILLING':           ['cashier'],
    'COMPLETED':         ['opd', 'workstation'],
    'DISCHARGED':        ['opd'],
}


def _auto_route_to_dept(visit, visit_status, qms_service_type, dept_code, triggered_by, notes=''):
    """
    Generic helper: update visit.status and create a QMS token for a department.
    Safe to call multiple times — skips if visit is already at target or beyond
    COMPLETED/DISCHARGED.
    """
    if not visit:
        return
    terminal = {'BILLING', 'COMPLETED', 'DISCHARGED', 'CANCELLED'}
    if visit.status in terminal:
        return

    from apps.departments.models import Department
    dept = Department.objects.filter(code=dept_code, is_active=True).first()

    # Close token for the stage the patient is leaving before advancing
    close_stage_token(visit.patient, prev_status=visit.status)

    visit.status = visit_status
    update_fields = ['status', 'updated_at']
    if dept:
        visit.department = dept
        update_fields.append('department')
    visit.save(update_fields=update_fields)

    if _qms_active():
        try:
            from apps.qms.models import (
                QueueToken, DailyTokenSequence, IssuancePoint, TokenStatus
            )
            from django.db import transaction as _pf_tx
            with _pf_tx.atomic():
                token_number = DailyTokenSequence.next_dept_token(qms_service_type)
                QueueToken.objects.create(
                    token_number=token_number,
                    service_type=qms_service_type,
                    patient=visit.patient,
                    visit=visit,
                    service_tier=getattr(visit, 'service_tier', 'STANDARD'),
                    issuance_point=IssuancePoint.SYSTEM,
                    status=TokenStatus.WAITING,
                    notes=notes,
                    issued_by=triggered_by,
                )
        except Exception:
            pass

    # Notify AFTER QMS token is committed — browser fetch will find the token
    for _room in _STATUS_ROOMS.get(visit_status, []):
        _ws_notify(_room)


def auto_route_to_lab(consultation, ordered_by):
    """
    After a lab order is placed, route the patient to the LAB queue.
    If patient is already at LABORATORY (multiple orders), skip.
    """
    try:
        visit = getattr(consultation, 'visit', None)
        if not visit:
            return
        if visit.status == 'LABORATORY':
            return  # Already routed — multiple orders, don't double-queue
        _auto_route_to_dept(
            visit=visit,
            visit_status='LABORATORY',
            qms_service_type='LAB',
            dept_code='LAB',
            triggered_by=ordered_by,
            notes='Auto-routed after lab order placed.',
        )
    except Exception:
        pass


def auto_route_to_investigation(consultation, ordered_by, category=None):
    """
    After an investigation order is placed, route patient to the correct queue.
    Optometry exams (REFRACTION, ORTHOPTICS, LOW_VISION) → optometrist's own queue.
    All other investigations → generic INVESTIGATION queue.
    """
    _OPTOMETRY_CATS = {'REFRACTION', 'ORTHOPTICS', 'LOW_VISION'}
    try:
        visit = getattr(consultation, 'visit', None)
        if not visit:
            return

        if category and category in _OPTOMETRY_CATS:
            # Route to the optometrist's queue — same as consultation routing
            if visit.status == 'REFRACTION':
                return
            _auto_route_to_dept(
                visit=visit,
                visit_status='REFRACTION',
                qms_service_type='REFRACTION',
                dept_code='REFRAC',
                triggered_by=ordered_by,
                notes=f'Auto-routed for {category.lower()} exam.',
            )
        else:
            if visit.status == 'INVESTIGATION':
                return
            _auto_route_to_dept(
                visit=visit,
                visit_status='INVESTIGATION',
                qms_service_type='INVEST',
                dept_code='INVEST',
                triggered_by=ordered_by,
                notes='Auto-routed after investigation order placed.',
            )
    except Exception:
        pass


def check_and_autoreturn_to_doctor(visit, triggered_by=None):
    """
    Called after a lab or investigation result is verified.
    Checks if ALL pending lab + investigation orders/results for this visit are done.
    If so, automatically routes patient back to the doctor's queue.

    Smart return logic:
      - If visit.referring_doctor is set → return to THAT specific doctor's queue
      - Otherwise → return to general doctor queue (tier-aware)

    Only triggers when visit.status is LABORATORY or INVESTIGATION.
    """
    try:
        if not visit:
            return
        if visit.status not in ('LABORATORY', 'INVESTIGATION', 'REFRACTION'):
            return

        from apps.laboratory.models import LabOrder, LabResult
        from apps.investigations.models import InvestigationOrder, InvestigationResult

        # Unfinished lab orders (no result yet)
        pending_lab = LabOrder.objects.filter(
            consultation__visit=visit,
            is_deleted=False,
            status__in=['ORDERED', 'SAMPLE_COLLECTED', 'PROCESSING'],
        ).count()

        # Unverified lab results
        unverified_lab = LabResult.objects.filter(
            order_item__order__consultation__visit=visit,
            order_item__order__is_deleted=False,
            is_verified=False,
            is_deleted=False,
        ).count()

        # Unfinished investigation orders (visit FK, with fallback for legacy orders)
        from django.db.models import Q as _ARQ
        from django.utils import timezone as _ar_tz
        _ar_today = _ar_tz.localdate()
        pending_invest = InvestigationOrder.objects.filter(
            _ARQ(visit=visit) |
            _ARQ(visit__isnull=True, patient=visit.patient, created_at__date=_ar_today),
            is_deleted=False,
            status__in=['ORDERED', 'SCHEDULED', 'IN_PROGRESS'],
        ).count()

        # Unverified investigation results
        unverified_invest = InvestigationResult.objects.filter(
            _ARQ(order__visit=visit) |
            _ARQ(order__visit__isnull=True, order__patient=visit.patient, order__created_at__date=_ar_today),
            order__is_deleted=False,
            is_verified=False,
            is_deleted=False,
        ).count()

        total_pending = pending_lab + unverified_lab + pending_invest + unverified_invest

        if total_pending > 0:
            return  # More results still expected

        # ── Smart return: same doctor if referring_doctor is set ──────────
        referring_doc = getattr(visit, 'referring_doctor', None)
        tier = getattr(visit, 'service_tier', 'STANDARD') or 'STANDARD'

        # Determine the right QMS service type based on tier
        if tier == 'VIP':
            qms_service = 'VIP_CONSULT'
        elif tier == 'EXPRESS':
            qms_service = 'EXP_CONSULT'
        else:
            qms_service = 'GENERAL'

        notes = 'Auto-returned after all results verified.'
        if referring_doc:
            notes = f'Auto-returned to Dr. {referring_doc.last_name} after all results verified.'

        # Close token for current stage
        close_stage_token(visit.patient, prev_status=visit.status)

        # Update visit status
        from apps.departments.models import Department
        dept = Department.objects.filter(code='OPD', is_active=True).first() or \
               Department.objects.filter(code='GEN_OPH', is_active=True).first()

        visit.status = 'WAITING'
        update_fields = ['status', 'updated_at']
        if dept:
            visit.department = dept
            update_fields.append('department')
        # Set attending_doctor to the referring doctor so workstation shows them
        if referring_doc:
            visit.attending_doctor = referring_doc
            update_fields.append('attending_doctor')
        visit.save(update_fields=update_fields)

        # Create QMS token — assign to referring doctor's counter if possible
        if _qms_active():
            try:
                from apps.qms.models import (
                    QueueToken, DailyTokenSequence, IssuancePoint,
                    TokenStatus, ServiceCounter
                )
                from django.db import transaction as _pf_tx
                from django.utils import timezone as _tz

                # Try to find the referring doctor's active counter
                target_counter = None
                if referring_doc:
                    target_counter = ServiceCounter.objects.filter(
                        staff_assigned=referring_doc,
                        is_active=True,
                        checked_in_date=_tz.localdate(),
                    ).first()

                with _pf_tx.atomic():
                    token_number = DailyTokenSequence.next_dept_token(qms_service)
                    QueueToken.objects.create(
                        token_number=token_number,
                        service_type=qms_service,
                        patient=visit.patient,
                        visit=visit,
                        service_tier=tier,
                        issuance_point=IssuancePoint.SYSTEM,
                        status=TokenStatus.WAITING,
                        counter=target_counter,
                        notes=notes,
                        issued_by=triggered_by,
                    )
            except Exception:
                pass

        # Notify workstation + OPD
        for _room in _STATUS_ROOMS.get('WAITING', []):
            _ws_notify(_room)
        # Also notify the specific doctor if we know them
        if referring_doc:
            _ws_notify(f'doctor-{referring_doc.pk}')

    except Exception:
        pass
