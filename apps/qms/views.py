"""
QMS Views — Multi-tier ophthalmology queue management (GLUDD Hospital).

Entry flow:
  gate_issue          → STANDARD patients only (mandatory main gate ticket)
  vip_reception_issue → VIP patients (back entrance, ticket optional)
  express_desk_issue  → EXPRESS / FAST_TRACK patients (side entrance, ticket optional)
                        Insured patients here → routed to Insurance Consultation Room
  cashier_issue       → Any tier arriving without a prior ticket (fallback)

Dept flow:   route_to_dept  → dept token auto-created (SYSTEM issuance)
Counter:     counter_view / call_next  → tier-priority aware
Display:     display_board  → TV board, auto-refresh
"""
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import Q

from .models import (
    QueueToken, ServiceCounter, DailyTokenSequence,
    ServiceType, ServiceTier, TokenStatus, IssuancePoint,
    TIER_PRIORITY, Zone, TierZoneMapping, StationType,
)
from apps.patients.models import Patient, Visit, VisitStatus, VisitType, VISIT_STATUS_TO_SERVICE_TYPE
from apps.core.context_processors import qms_active as _qms_active
from apps.core.decorators import json_error_handler


# ── Zone helpers ──────────────────────────────────────────────────────────────

# Service types that always route to the SHARED zone regardless of patient tier
_SHARED_SERVICE_TYPES = frozenset({
    'LAB', 'PHARMACY', 'INVEST', 'OPTICAL',
    'COUNSEL', 'BILLING', 'PRE_OP', 'ADMISSION',
})

_zone_cache = {}   # simple in-process cache; cleared by seed_zones / zone edits


def _resolve_zone(tier: str):
    """
    Return the Zone for a given ServiceTier code, or None if not configured.
    Uses a lightweight per-process cache — safe for tests and single-worker setups.
    """
    if tier in _zone_cache:
        return _zone_cache[tier]
    try:
        mapping = TierZoneMapping.objects.select_related('zone').get(tier=tier)
        zone = mapping.zone if mapping.zone.is_active else None
    except Exception:
        zone = None
    _zone_cache[tier] = zone
    return zone


def _get_zone(code: str):
    """Return a Zone by code, or None."""
    try:
        return Zone.objects.get(code=code, is_active=True)
    except Zone.DoesNotExist:
        return None


def _zone_for_service(tier: str, service_type: str):
    """
    Determine the current zone for a token:
    - Shared services (Lab, Pharmacy…) → SHARED zone
    - Everything else → tier's zone via TierZoneMapping
    """
    if service_type in _SHARED_SERVICE_TYPES:
        return _get_zone('SHARED')
    return _resolve_zone(tier)


def _clear_zone_cache():
    """Call after any TierZoneMapping update to flush the in-process cache."""
    _zone_cache.clear()


def _check_zone_scope(request, token):
    """
    Server-side zone-scope enforcement.

    Returns None if the staff member is allowed to act on this token.
    Returns an HttpResponse (403) if the zone does not match.

    Rules:
    - Supervisors (super_admin, medical_director, ceo, admin_director) see all zones.
    - Staff whose assigned counter has a zone can only act on tokens in that zone,
      OR in the SHARED zone (Lab/Pharmacy/etc. serve all tiers).
    - Staff without an assigned counter are not restricted (fallback).
    - A VIP token can NEVER be acted on by a non-VIP counter staff member.
    """
    from django.http import HttpResponseForbidden
    _UNRESTRICTED_ROLES = {'super_admin', 'medical_director', 'ceo', 'admin_director', 'admin'}
    if request.user.role in _UNRESTRICTED_ROLES or request.user.is_superuser:
        return None

    # Hard rule: VIP token must only be touched by VIP zone staff
    if token.service_tier == ServiceTier.VIP:
        counter = ServiceCounter.objects.filter(
            staff_assigned=request.user, is_active=True
        ).select_related('zone').first()
        # No counter assigned OR counter has no zone OR counter zone is not VIP → block
        if not counter or not counter.zone or counter.zone.code != 'VIP':
            return HttpResponseForbidden(
                'Zone access denied: VIP patients can only be managed by VIP zone staff.'
            )

    # General zone check: staff counter zone must match token zone
    # (SHARED zone is accessible to all staff — it is a shared service point)
    if token.zone and token.zone.code != 'SHARED':
        counter = ServiceCounter.objects.filter(
            staff_assigned=request.user, is_active=True
        ).select_related('zone').first()
        if counter and counter.zone and counter.zone.id != token.zone_id:
            return HttpResponseForbidden(
                f'Zone access denied: this token belongs to {token.zone.name} '
                f'but your counter is in {counter.zone.name}.'
            )

    return None


def _shared_priority_queue(service_type: str, today=None):
    """
    Return the waiting queue for a shared-service station ordered by
    effective anti-starvation priority (VIP first, but long-waiting Standard
    patients get boosted so they are never stuck forever).

    The ordering is: effective_priority DESC, issued_at ASC.
    Because effective_priority requires Python-level calculation per token,
    we fetch waiting tokens and sort in Python (shared queues are typically < 60 patients).
    """
    from django.utils import timezone as _tz
    today = today or _tz.localdate()
    tokens = list(
        QueueToken.objects.filter(
            service_type=service_type,
            status=TokenStatus.WAITING,
            token_date=today,
            is_deleted=False,
        ).select_related('patient', 'zone').order_by('-priority', 'issued_at')
    )
    # Get anti_starvation_minutes from the first active counter for this service type
    _anti_min = 45
    try:
        ctr = ServiceCounter.objects.filter(
            service_type=service_type, is_active=True
        ).values('anti_starvation_minutes').first()
        if ctr:
            _anti_min = ctr['anti_starvation_minutes']
    except Exception:
        pass
    # Sort by effective (anti-starvation boosted) priority
    tokens.sort(key=lambda t: (-t.effective_priority(_anti_min), t.issued_at))
    return tokens


# ── General helpers ────────────────────────────────────────────────────────────

def _slip_layout(user):
    """Return the correct base layout for ticket slips based on issuer role."""
    if user.role == 'gatekeeper':
        return 'layouts/base_gatekeeper.html'
    return 'layouts/base_authenticated.html'


def _active_tokens_today():
    today = timezone.localdate()
    return QueueToken.objects.filter(
        token_date=today, is_deleted=False
    )


# ── Main dashboard ────────────────────────────────────────────────────────────

@login_required
def queue_dashboard(request):
    """
    Main QMS dashboard.
    - Supervisors / admins: see all counters and full queue.
    - Counter staff (receptionist, cashier, nurse, etc.):
      redirected straight to their own counter — they have no business
      on the global overview page.
    """
    if not _qms_active():
        return redirect('dashboard:home')

    user = request.user

    # Gatekeeper — always goes to gate entry (no counter for them)
    if user.role == 'gatekeeper':
        return redirect('qms:gate_issue')

    # Doctors — go to their specialty queue
    if user.is_doctor:
        return redirect('qms:doctor_queue')

    # Counter staff — go straight to their own counter
    _COUNTER_ROLES = {
        'receptionist', 'medical_records',
        'cashier', 'chief_cashier', 'billing_officer',
        'nurse', 'consultation_nurse',
        'pharmacist', 'optical_dispenser',
        'counseling_nurse', 'investigation_technician', 'lab_technician',
        'admission_officer', 'cssd_technician',
    }
    if user.role in _COUNTER_ROLES:
        my = ServiceCounter.objects.filter(
            staff_assigned=user, is_active=True
        ).first()
        if my:
            return redirect('qms:counter', counter_id=my.id)
        # Counter staff with no counter assigned → tell them
        return redirect('qms:no_counter')

    # Global QMS dashboard is ONLY for admin / management roles
    _ADMIN_ROLES = {
        'super_admin', 'medical_director', 'admin_director', 'ceo',
        'admin', 'admission_officer',
    }
    if user.role not in _ADMIN_ROLES and not user.is_executive and not user.is_admin_staff:
        # Any other role with no counter → show no-counter message
        return redirect('qms:no_counter')

    today = timezone.localdate()
    tokens = _active_tokens_today().exclude(
        status__in=[TokenStatus.COMPLETED, TokenStatus.CANCELLED, TokenStatus.NO_SHOW]
    ).select_related('patient', 'counter').order_by('-priority', 'issued_at')

    counters = ServiceCounter.objects.filter(is_active=True).select_related(
        'current_serving', 'staff_assigned'
    )

    # Single aggregate for all status+service_type counts — avoids N+1 count() calls
    from django.db.models import Count as _Cnt, Case as _Case, When as _When, IntegerField as _IF
    status_agg = tokens.aggregate(
        waiting_count=_Cnt(_Case(_When(status=TokenStatus.WAITING, then=1), output_field=_IF())),
        serving_count=_Cnt(_Case(_When(status=TokenStatus.SERVING, then=1), output_field=_IF())),
    )
    dept_raw = (
        tokens.filter(status=TokenStatus.WAITING)
        .values('service_type').annotate(waiting=_Cnt('id'))
    )
    dept_waiting_map = {row['service_type']: row['waiting'] for row in dept_raw}

    dept_counts = {
        code: {'label': label, 'waiting': dept_waiting_map.get(code, 0)}
        for code, label in ServiceType.choices
    }

    all_today = _active_tokens_today()
    context = {
        'tokens': tokens,
        'counters': counters,
        'waiting_count': status_agg['waiting_count'],
        'serving_count': status_agg['serving_count'],
        'dept_counts': dept_counts,
        'service_types': ServiceType.choices,
        'service_tiers': ServiceTier.choices,
        'today': today,
        'total_today': all_today.count(),
    }
    return render(request, 'qms/dashboard.html', context)


# ── Entry ticket issuance ─────────────────────────────────────────────────────

@login_required
def gate_issue(request):
    """
    Main Gate — Standard patients ONLY.
    Standard patients MUST take a ticket here before entering.
    VIP → VIP Reception.  Express/FastTrack → Express Desk.
    """
    if request.method == 'POST':
        tier = request.POST.get('service_tier', ServiceTier.STANDARD)
        patient_id = request.POST.get('patient_id', '').strip()
        patient_name = request.POST.get('patient_name', '').strip()
        visit_id = request.POST.get('visit_id', '').strip()

        # Redirect non-standard tiers unless staff explicitly overrides
        if tier != ServiceTier.STANDARD and not request.POST.get('override_tier'):
            tier_name = dict(ServiceTier.choices).get(tier, tier)
            messages.warning(
                request,
                f'{tier_name} patients should use their dedicated entry point. '
                'VIP → VIP Reception (back entrance). '
                'Express / Fast Track → Express Desk (side entrance). '
                'Tick "Override" below if the patient insists on entering via the main gate.'
            )
            return render(request, 'qms/gate_issue.html', {
                'tiers': ServiceTier.choices,
                'default_tier': ServiceTier.STANDARD,
                'tier_warning': tier,
                'post_data': request.POST,
                'today_count': _active_tokens_today().count(),
            })

        patient = None
        visit = None
        patient_uuid = request.POST.get('patient_uuid', '').strip()
        # Fallback: the search box text (submitted via name="patient_search_text")
        search_text = request.POST.get('patient_search_text', '').strip()

        # Try UUID first, then readable patient_id
        if patient_uuid:
            try:
                patient = Patient.objects.filter(id=patient_uuid, is_deleted=False).first()
            except Exception:
                pass  # invalid UUID format — fall through to patient_id lookup
        if not patient and patient_id:
            try:
                patient = Patient.objects.filter(patient_id=patient_id, is_deleted=False).first()
            except Exception:
                pass
        if patient:
            patient_name = patient.full_name  # always use the real name from DB

        # patient_name is the walk-in field value — already populated in JS via walkinInput
        # when the user selected a patient from the dropdown. If it's non-empty here,
        # the ticket will issue (either linked to patient record or as a named walk-in).

        if visit_id:
            visit = Visit.objects.filter(id=visit_id).first()

        is_new_patient = request.POST.get('patient_type') == 'NEW'

        # NEW patients don't need a name yet — reception will register them.
        # RETURNING walk-ins must have either a linked record or a typed name.
        if not is_new_patient and not patient and not patient_name:
            messages.error(request, 'Please search and select a patient or enter a walk-in name.')
            return redirect('qms:gate_issue')
        is_insured = request.POST.get('is_insured') == '1'
        insurance_company = request.POST.get('insurance_company', '').strip()

        # Determine visit category based on consultation window:
        #   NEW            → RECEPTIONIST queue (register first)
        #   FREE FOLLOW-UP (within 15 days since last consultation) → TRIAGE (skip cashier)
        #   RETURNING past window → CASHIER queue (pay new consultation)
        #   EXPIRED        → CASHIER queue (pay new consultation)
        is_free_followup = (not is_new_patient) and patient and patient.is_free_followup

        if is_new_patient:
            first_service = ServiceType.RECEPTIONIST
            base_notes = 'NEW PATIENT — register first'
            if not patient_name:
                patient_name = 'New Patient'  # placeholder until receptionist registers
        elif is_free_followup:
            first_service = ServiceType.PARAMETERS
            base_notes = f'FREE FOLLOW-UP — {patient.consultation_visit_label} — go directly to Triage'
        else:
            first_service = ServiceType.CASHIER
            base_notes = ''

        if is_insured:
            ins_note = f'Insured: {insurance_company}' if insurance_company else 'Insured patient'
            base_notes = f'{base_notes} | {ins_note}'.strip(' |')

        with transaction.atomic():
            token_number = DailyTokenSequence.next_entry_token(tier)
            token = QueueToken.objects.create(
                token_number=token_number,
                patient=patient,
                visit=visit,
                patient_name=patient_name,
                service_type=first_service,
                service_tier=tier,
                issuance_point=IssuancePoint.GATE,
                priority=TIER_PRIORITY.get(tier, 0),
                is_insured=is_insured,
                insurance_company=insurance_company,
                issued_by=request.user,
                notes=base_notes,
                zone=_zone_for_service(tier, first_service),
                origin_zone=_resolve_zone(tier),
            )
            # Auto-check-in any appointment booked for today
            # so the receptionist dashboard shows accurate checked-in counts
            if patient and not is_new_patient:
                from apps.appointments.models import Appointment
                Appointment.objects.filter(
                    patient=patient,
                    appointment_date=timezone.localdate(),
                    status__in=[Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED],
                    is_deleted=False,
                ).update(status=Appointment.Status.CHECKED_IN)

        if is_new_patient:
            dest = 'Receptionist (new patient registration)'
        elif is_free_followup:
            dest = 'Triage directly — FREE FOLLOW-UP (no cashier payment required)'
        else:
            dest = 'Cashier'
        messages.success(request, f'Standard ticket {token_number} issued. Patient directed to: {dest}.')
        return render(request, 'qms/ticket_slip.html', {
            'token': token,
            'printed': True,
            'is_new_patient': is_new_patient,
            'is_free_followup': is_free_followup,
            'base_layout': _slip_layout(request.user),
            'today_count': _active_tokens_today().count(),
        })

    tickets_today = (
        _active_tokens_today()
        .filter(issuance_point__in=[
            IssuancePoint.GATE,
            IssuancePoint.VIP_RECEPTION,
            IssuancePoint.EXPRESS_DESK,
        ])
        .select_related('patient')
        .order_by('-issued_at')
    )
    # Expected pre-registrations for today — gatekeeper confirms arrivals here
    from apps.patients.models import PreRegistration
    expected_today = PreRegistration.objects.filter(
        visit_date=timezone.localdate(),
        status__in=['PENDING', 'ARRIVED'],
    ).order_by('status', 'created_at')

    return render(request, 'qms/gate_issue.html', {
        'tiers': ServiceTier.choices,
        'default_tier': ServiceTier.STANDARD,
        'today_count': _active_tokens_today().count(),
        'tickets_today': tickets_today,
        'expected_today': expected_today,
    })


@login_required
@require_POST
def prereg_mark_arrived(request, code):
    """
    Gatekeeper confirms pre-registered patient has physically arrived.
    Marks as ARRIVED and auto-issues a gate ticket in one step.
    Renders the ticket slip immediately so it can be printed.
    """
    from apps.patients.models import PreRegistration, Patient
    prereg = get_object_or_404(PreRegistration, code=code.upper())

    first_name = prereg.data.get('first_name', '')
    last_name  = prereg.data.get('last_name', '')
    full_name  = f'{first_name} {last_name}'.strip()

    if prereg.status == PreRegistration.Status.ARRIVED:
        messages.info(request, f'{full_name} already confirmed as arrived.')
        return redirect('qms:gate_issue')

    if prereg.status != PreRegistration.Status.PENDING:
        messages.warning(request, f'Pre-registration status: {prereg.get_status_display()} — cannot process.')
        return redirect('qms:gate_issue')

    # Mark arrived
    prereg.mark_arrived(confirmed_by_user=request.user)

    # Check if patient already has a patient record (returning pre-reg)
    phone = prereg.data.get('phone_number', '').strip()
    patient = None
    if phone:
        patient = Patient.objects.filter(phone_number=phone, is_deleted=False).first()

    # Determine routing: if patient exists check follow-up, else new patient → Reception
    is_insured    = str(prereg.data.get('is_insured', '')).upper() in ('1', 'TRUE', 'YES')
    insurance_co  = prereg.data.get('insurance_company', '').strip()
    tier_raw      = prereg.data.get('service_tier', 'STANDARD').upper()
    tier          = tier_raw if tier_raw in dict(ServiceTier.choices) else ServiceTier.STANDARD

    if patient and patient.is_free_followup:
        first_service = ServiceType.PARAMETERS
        route_note    = 'FREE FOLLOW-UP — go directly to Triage (skip cashier)'
    elif patient:
        first_service = ServiceType.CASHIER
        route_note    = 'Returning patient — go to Cashier'
    else:
        first_service = ServiceType.RECEPTIONIST
        route_note    = 'Pre-registered new patient — go to Reception for full registration'

    notes = f'PRE-REG {prereg.code} | {route_note}'
    if is_insured:
        ins_note = f'Insured: {insurance_co}' if insurance_co else 'Insured patient'
        notes = f'{notes} | {ins_note}'

    with transaction.atomic():
        token_number = DailyTokenSequence.next_entry_token(tier)
        token = QueueToken.objects.create(
            token_number=token_number,
            patient=patient,
            patient_name=full_name,
            service_type=first_service,
            service_tier=tier,
            issuance_point=IssuancePoint.GATE,
            priority=TIER_PRIORITY.get(tier, 0),
            is_insured=is_insured,
            insurance_company=insurance_co,
            issued_by=request.user,
            notes=notes,
        )

    messages.success(
        request,
        f'Arrival confirmed + ticket {token_number} issued for {full_name}.'
    )
    return render(request, 'qms/ticket_slip.html', {
        'token': token,
        'printed': True,
        'is_new_patient': first_service == ServiceType.RECEPTIONIST,
        'is_free_followup': first_service == ServiceType.PARAMETERS,
        'base_layout': _slip_layout(request.user),
        'today_count': _active_tokens_today().count(),
        'prereg': prereg,
    })


@login_required
def vip_reception_issue(request):
    """
    VIP Reception — Back Entrance.
    VIP patients are NOT obliged to take a gate ticket.
    They enter here and are fast-tracked with highest priority.
    """
    if request.method == 'POST':
        patient_id   = request.POST.get('patient_id', '').strip()
        patient_uuid = request.POST.get('patient_uuid', '').strip()
        patient_name = request.POST.get('patient_name', '').strip()
        visit_id     = request.POST.get('visit_id', '').strip()

        patient = None
        visit = None

        if patient_uuid:
            try:
                patient = Patient.objects.filter(id=patient_uuid, is_deleted=False).first()
            except Exception:
                pass
        if not patient and patient_id:
            patient = Patient.objects.filter(patient_id=patient_id, is_deleted=False).first()
        if patient:
            patient_name = patient.full_name

        if visit_id:
            visit = Visit.objects.filter(id=visit_id).first()

        if not patient and not patient_name:
            messages.error(request, 'Please search for the patient or enter a name.')
            return redirect('qms:vip_reception')

        today = timezone.localdate()
        if patient:
            existing = QueueToken.objects.filter(
                patient=patient,
                token_date=today,
                issuance_point__in=[
                    IssuancePoint.GATE, IssuancePoint.VIP_RECEPTION,
                    IssuancePoint.EXPRESS_DESK, IssuancePoint.CASHIER,
                ],
                is_deleted=False,
            ).first()
            if existing:
                messages.info(request, f'Patient already has ticket {existing.token_number} today.')
                return render(request, 'qms/ticket_slip.html', {
                    'token': existing, 'printed': False,
                    'base_layout': _slip_layout(request.user),
                    'today_count': _active_tokens_today().count(),
                })

        is_insured = request.POST.get('is_insured') == '1'
        insurance_company = request.POST.get('insurance_company', '').strip()
        ins_note = ''
        if is_insured:
            ins_note = f'Insured: {insurance_company}' if insurance_company else 'Insured patient'

        with transaction.atomic():
            token_number = DailyTokenSequence.next_entry_token(ServiceTier.VIP)
            token = QueueToken.objects.create(
                token_number=token_number,
                patient=patient,
                visit=visit,
                patient_name=patient_name,
                service_type=ServiceType.CASHIER,
                service_tier=ServiceTier.VIP,
                issuance_point=IssuancePoint.VIP_RECEPTION,
                priority=TIER_PRIORITY[ServiceTier.VIP],
                is_insured=is_insured,
                insurance_company=insurance_company,
                issued_by=request.user,
                notes=ins_note,
                zone=_resolve_zone(ServiceTier.VIP),
                origin_zone=_resolve_zone(ServiceTier.VIP),
            )

        messages.success(request, f'VIP ticket {token_number} issued. Directing to VIP Cashier.')
        return render(request, 'qms/ticket_slip.html', {
            'token': token, 'printed': True,
            'base_layout': _slip_layout(request.user),
            'today_count': _active_tokens_today().count(),
        })

    return render(request, 'qms/vip_reception.html', {
        'today_count': _active_tokens_today().count(),
    })


@login_required
def express_desk_issue(request):
    """
    Express / Fast Track Desk — Side Entrance.
    Express and Fast Track patients are NOT obliged to take a gate ticket.
    Insured patients in this section → Insurance Consultation Room directly.
    """
    if request.method == 'POST':
        tier = request.POST.get('service_tier', ServiceTier.EXPRESS)
        patient_id = request.POST.get('patient_id', '').strip()
        patient_name = request.POST.get('patient_name', '').strip()
        visit_id = request.POST.get('visit_id', '').strip()
        is_insured = request.POST.get('is_insured') == '1'
        insurance_company = request.POST.get('insurance_company', '').strip()

        if tier not in [ServiceTier.EXPRESS, ServiceTier.FAST_TRACK]:
            messages.error(request, 'This desk serves Express and Fast Track patients only.')
            return redirect('qms:express_desk')

        patient = None
        visit = None
        patient_uuid = request.POST.get('patient_uuid', '').strip()

        if patient_uuid:
            try:
                patient = Patient.objects.filter(id=patient_uuid, is_deleted=False).first()
            except Exception:
                pass
        if not patient and patient_id:
            patient = Patient.objects.filter(patient_id=patient_id, is_deleted=False).first()
        if patient:
            patient_name = patient.full_name

        if visit_id:
            visit = Visit.objects.filter(id=visit_id).first()

        if not patient and not patient_name:
            messages.error(request, 'Please search for the patient or enter a name.')
            return redirect('qms:express_desk')

        today = timezone.localdate()
        if patient:
            existing = QueueToken.objects.filter(
                patient=patient,
                token_date=today,
                issuance_point__in=[
                    IssuancePoint.GATE, IssuancePoint.VIP_RECEPTION,
                    IssuancePoint.EXPRESS_DESK, IssuancePoint.CASHIER,
                ],
                is_deleted=False,
            ).first()
            if existing:
                messages.info(request, f'Patient already has ticket {existing.token_number} today.')
                return render(request, 'qms/ticket_slip.html', {
                    'token': existing, 'printed': False,
                    'base_layout': _slip_layout(request.user),
                    'today_count': _active_tokens_today().count(),
                })

        # All patients proceed to Cashier first; insurance is a billing flag only
        first_service = ServiceType.CASHIER
        notes = f'Insured: {insurance_company}' if is_insured and insurance_company else (
            'Insured patient' if is_insured else ''
        )

        with transaction.atomic():
            token_number = DailyTokenSequence.next_entry_token(tier)
            token = QueueToken.objects.create(
                token_number=token_number,
                patient=patient,
                visit=visit,
                patient_name=patient_name,
                service_type=first_service,
                service_tier=tier,
                issuance_point=IssuancePoint.EXPRESS_DESK,
                priority=TIER_PRIORITY.get(tier, 10),
                is_insured=is_insured,
                insurance_company=insurance_company,
                notes=notes,
                issued_by=request.user,
                zone=_zone_for_service(tier, first_service),
                origin_zone=_resolve_zone(tier),
            )

        tier_label = 'Fast Track' if tier == ServiceTier.FAST_TRACK else 'Express'
        dest = f'{tier_label} Cashier'
        messages.success(request, f'Ticket {token_number} issued. Directing to {dest}.')
        return render(request, 'qms/ticket_slip.html', {
            'token': token,
            'printed': True,
            'base_layout': _slip_layout(request.user),
            'today_count': _active_tokens_today().count(),
        })

    return render(request, 'qms/express_desk.html', {
        'tiers': [(ServiceTier.EXPRESS, 'Express'), (ServiceTier.FAST_TRACK, 'Fast Track')],
        'default_tier': ServiceTier.EXPRESS,
        'today_count': _active_tokens_today().count(),
    })


@login_required
def cashier_issue(request):
    """
    Cashier issues an entry ticket (VIP/Express/FastTrack via back entrance).
    Shares the same daily sequence counter as gate — no duplicate numbers.
    """
    if request.method == 'POST':
        tier = request.POST.get('service_tier', ServiceTier.STANDARD)
        patient_id = request.POST.get('patient_id', '').strip()
        patient_name = request.POST.get('patient_name', '').strip()
        visit_id = request.POST.get('visit_id', '').strip()
        is_insured = request.POST.get('is_insured') == '1'
        insurance_company = request.POST.get('insurance_company', '').strip()

        patient = None
        visit = None

        if patient_id:
            patient = Patient.objects.filter(patient_id=patient_id, is_deleted=False).first()
            if patient:
                patient_name = patient.full_name

        if visit_id:
            visit = Visit.objects.filter(id=visit_id).first()

        if not patient and not patient_name:
            messages.error(request, 'Please search and select a patient.')
            return redirect('qms:cashier_issue')

        # Check if patient already has an entry ticket today
        today = timezone.localdate()
        existing = None
        if patient:
            existing = QueueToken.objects.filter(
                patient=patient,
                token_date=today,
                issuance_point__in=[IssuancePoint.GATE, IssuancePoint.CASHIER],
                is_deleted=False,
            ).first()

        if existing:
            messages.warning(
                request,
                f'Patient already has entry ticket {existing.token_number} today. '
                'Use existing ticket or issue a department token instead.'
            )
            return render(request, 'qms/cashier_issue.html', {
                'tiers': ServiceTier.choices,
                'existing_token': existing,
            })

        ins_note = ''
        if is_insured:
            ins_note = f'Insured: {insurance_company}' if insurance_company else 'Insured patient'

        with transaction.atomic():
            token_number = DailyTokenSequence.next_entry_token(tier)
            token = QueueToken.objects.create(
                token_number=token_number,
                patient=patient,
                visit=visit,
                patient_name=patient_name,
                service_type=ServiceType.CASHIER,
                service_tier=tier,
                issuance_point=IssuancePoint.CASHIER,
                priority=TIER_PRIORITY.get(tier, 0),
                is_insured=is_insured,
                insurance_company=insurance_company,
                notes=ins_note,
                issued_by=request.user,
                zone=_resolve_zone(tier),
                origin_zone=_resolve_zone(tier),
            )

        messages.success(request, f'Entry ticket {token_number} issued at cashier.')
        return render(request, 'qms/ticket_slip.html', {
            'token': token, 'printed': True,
            'base_layout': 'layouts/base_authenticated.html',
        })

    return render(request, 'qms/cashier_issue.html', {
        'tiers': ServiceTier.choices,
    })


# ── Receptionist view — new patient registration ──────────────────────────────

@login_required
def receptionist_queue(request):
    """
    Receptionist counter view.
    Shows NEW patients waiting to be registered, filtered by tier if ?tier= is set.
    Each registration desk can bookmark their tier:
      /qms/receptionist/          → all tiers
      /qms/receptionist/?tier=STANDARD    → standard desk
      /qms/receptionist/?tier=VIP         → VIP desk
      /qms/receptionist/?tier=EXPRESS     → express/fast-track desk
    """
    today = timezone.localdate()
    selected_tier = request.GET.get('tier', '').upper().strip()

    # Map shorthand: EXPRESS covers both EXPRESS and FAST_TRACK
    TIER_GROUPS = {
        'STANDARD':  [ServiceTier.STANDARD],
        'VIP':       [ServiceTier.VIP],
        'EXPRESS':   [ServiceTier.EXPRESS, ServiceTier.FAST_TRACK],
    }

    qs = QueueToken.objects.filter(
        service_type=ServiceType.RECEPTIONIST,
        status=TokenStatus.WAITING,
        token_date=today,
        is_deleted=False,
    ).select_related('patient')

    if selected_tier in TIER_GROUPS:
        qs = qs.filter(service_tier__in=TIER_GROUPS[selected_tier])

    waiting = qs.order_by('-priority', 'issued_at')

    # Counts per tier for the filter buttons
    def _count(tiers):
        return QueueToken.objects.filter(
            service_type=ServiceType.RECEPTIONIST,
            status=TokenStatus.WAITING,
            token_date=today,
            is_deleted=False,
            service_tier__in=tiers,
        ).count()

    tier_counts = {
        'ALL':      QueueToken.objects.filter(service_type=ServiceType.RECEPTIONIST, status=TokenStatus.WAITING, token_date=today, is_deleted=False).count(),
        'STANDARD': _count([ServiceTier.STANDARD]),
        'VIP':      _count([ServiceTier.VIP]),
        'EXPRESS':  _count([ServiceTier.EXPRESS, ServiceTier.FAST_TRACK]),
    }

    return render(request, 'qms/receptionist.html', {
        'waiting': waiting,
        'waiting_count': waiting.count(),
        'selected_tier': selected_tier,
        'tier_counts': tier_counts,
        'today': today,
    })


@json_error_handler
@login_required
@require_POST
def receptionist_complete_registration(request, token_id):
    """
    Called when receptionist finishes registering a new patient.

    Position-aware cashier insertion:
      - Find all waiting cashier tokens ordered by priority + issued_at
      - Insert the new patient AFTER the 3rd waiting patient
        (so the patient does not go to the very end despite arriving early)
      - If fewer than 3 patients are waiting, insert at the end (normal queue)

    Why position 4 (after 3)?
      A new patient was early enough to register, so they deserve to be called
      soon but after the next few patients who arrived before them finished
      at the receptionist. This prevents newly-registered patients jumping
      everyone who was already waiting at cashier.
    """
    token = get_object_or_404(QueueToken, id=token_id, service_type=ServiceType.RECEPTIONIST)
    patient_id_str = request.POST.get('patient_id', '').strip()
    visit_id_str = request.POST.get('visit_id', '').strip()
    INSERT_AFTER_POSITION = 3  # Insert after this many waiting cashier patients

    today = timezone.localdate()

    # Update patient / visit links if registration just completed
    if patient_id_str:
        patient = Patient.objects.filter(patient_id=patient_id_str, is_deleted=False).first()
        if patient:
            token.patient = patient
            token.patient_name = patient.full_name

    if visit_id_str:
        visit = Visit.objects.filter(id=visit_id_str).first()
        if visit:
            token.visit = visit

    with transaction.atomic():
        # ── Fair queue positioning using ORIGINAL ARRIVAL TIME ────────────
        # The patient arrived at the gate at token.issued_at.
        # We move them to the CASHIER queue but keep their original arrival
        # time so they are placed fairly among returning patients who also
        # arrived at that time — NOT sent to the back of the queue.
        #
        # Example:
        #   08:00 — Returning patient P1 → straight to cashier (position 1)
        #   08:05 — New patient P2 → goes to receptionist first
        #   08:08 — Returning patient P3 → straight to cashier (position 2)
        #   08:20 — P2 finishes registration → enters cashier at 08:05 slot
        #           Cashier queue: P1(08:00), P2(08:05), P3(08:08) — FAIR ✓
        original_arrival = token.issued_at  # Gate arrival time — preserved

        token.service_type = ServiceType.CASHIER
        token.status = TokenStatus.WAITING
        token.issued_at = original_arrival  # Use gate time, not registration completion time

        # Count cashier patients who arrived BEFORE this patient
        cashier_before = QueueToken.objects.filter(
            service_type=ServiceType.CASHIER,
            status=TokenStatus.WAITING,
            token_date=today,
            issued_at__lte=original_arrival,
            service_tier=token.service_tier,
            is_deleted=False,
        ).count()

        token.notes = (token.notes or '') + ' [Registered — cashier position by original arrival time]'
        token.save()

    return JsonResponse({
        'success': True,
        'token_number': token.display_token_number,
        'cashier_position': cashier_before + 1,
        'message': (
            f'Patient placed in cashier queue at position {cashier_before + 1} '
            f'based on their original arrival time — completely fair to all patients.'
        ),
    })


# ── Department routing (doctor/nurse action) ──────────────────────────────────

@json_error_handler
@login_required
@require_POST
def route_to_dept(request):
    """
    Route a patient to the next department.
    Called by doctor/nurse after consultation/triage.
    Creates a department token and updates the Visit status.

    POST params:
        visit_id        — UUID of the Visit
        service_type    — target department code
        entry_token_id  — (optional) UUID of the entry ticket token
        notes           — (optional) routing notes
    """
    visit_id = request.POST.get('visit_id')
    service_type = request.POST.get('service_type')
    entry_token_id = request.POST.get('entry_token_id')
    notes = request.POST.get('notes', '')

    if not visit_id or not service_type:
        return JsonResponse({'success': False, 'message': 'visit_id and service_type required'}, status=400)

    visit = get_object_or_404(Visit, id=visit_id)
    tier = visit.service_tier

    # Find entry token if not provided
    entry_token = None
    if entry_token_id:
        entry_token = QueueToken.objects.filter(id=entry_token_id).first()
    elif visit.patient:
        today = timezone.localdate()
        entry_token = QueueToken.objects.filter(
            patient=visit.patient,
            token_date=today,
            issuance_point__in=[IssuancePoint.GATE, IssuancePoint.CASHIER],
            is_deleted=False,
        ).first()

    # Determine base priority from tier
    base_priority = TIER_PRIORITY.get(tier, 0)

    # ── Priority insertion for specialist queues ───────────────────────────
    # Priority patients referred to a specialist are inserted near the front
    # of the waiting queue — they do not join the end of the line.
    #
    # Insertion positions (patients left ahead):
    #   Fast Track → position 2 (skip 1 patient)  — highest priority tier
    #   Express    → position 4 (skip 3 patients)  — mid priority
    #   Insurance  → position 4 (same as Express)
    #   VIP        → specialist is summoned to VIP room (no insertion needed)
    #   Standard   → end of queue (no insertion)
    #
    # How it works:
    #   The queue is ordered by (-priority, issued_at).
    #   We find the Nth token's issued_at and set the new token's issued_at
    #   to (Nth.issued_at + 1 second), placing them right after position N.
    _SPECIALIST_QUEUES = frozenset({
        'GENERAL', 'RETINA', 'GLAUCOMA', 'CATARACT', 'NEURO',
        'OCULOPLASTY', 'CORNEA', 'PEDIATRIC', 'VIP_CONSULT',
        'EXP_CONSULT', 'INSUR_CONSULT', 'UVEITIS',
    })
    # Tier → how many patients to leave ahead in the specialist queue
    _TIER_INSERT_AFTER = {
        ServiceTier.FAST_TRACK: 1,   # position 2 — skip only 1 patient
        ServiceTier.EXPRESS:    3,   # position 4 — skip 3 patients
        ServiceTier.VIP:        3,   # VIP is handled separately (summons) below
    }

    issued_at_override = None
    insert_after = _TIER_INSERT_AFTER.get(tier)
    if insert_after is not None and service_type in _SPECIALIST_QUEUES:
        today = timezone.localdate()
        waiting = list(
            QueueToken.objects.filter(
                service_type=service_type,
                status=TokenStatus.WAITING,
                token_date=today,
                is_deleted=False,
            ).order_by('-priority', 'issued_at')
            .values('issued_at', 'priority')[:insert_after]
        )
        if len(waiting) >= insert_after:
            anchor_time = waiting[insert_after - 1]['issued_at']
            issued_at_override = anchor_time + timedelta(seconds=1)
        # If fewer than insert_after patients waiting, normal join

    # ── VIP specialist summons — detect early so we skip visit status update ─
    _VIP_SPECIALIST_QUEUES_EARLY = frozenset({
        'RETINA', 'GLAUCOMA', 'CATARACT', 'NEURO',
        'OCULOPLASTY', 'CORNEA', 'PEDIATRIC', 'UVEITIS',
    })
    _is_vip_call_early = (tier == ServiceTier.VIP and service_type in _VIP_SPECIALIST_QUEUES_EARLY)

    with transaction.atomic():
        token_number = DailyTokenSequence.next_dept_token(service_type)
        token_notes = notes
        if issued_at_override:
            _pos_label = f'position ~{insert_after + 1}' if insert_after else 'priority position'
            token_notes = (notes + f' [Priority insertion — {_pos_label}]').strip()
        if _is_vip_call_early:
            vip_note = 'VIP CALL \u2014 Patient is in VIP Room. Please attend the VIP Consultation Room.'
            token_notes = f'{vip_note} | {notes}'.strip(' |') if notes else vip_note

        create_kwargs = dict(
            token_number=token_number,
            patient=visit.patient,
            visit=visit,
            patient_name=visit.patient.full_name if visit.patient else '',
            service_type=service_type,
            service_tier=tier,
            issuance_point=IssuancePoint.SYSTEM,
            priority=base_priority,
            entry_token=entry_token,
            notes=token_notes,
            issued_by=request.user,
            zone=_zone_for_service(tier, service_type),
            # origin_zone: inherit from entry_token if available, otherwise resolve from tier
            origin_zone=(entry_token.origin_zone if entry_token and entry_token.origin_zone_id
                         else _resolve_zone(tier)),
        )
        if issued_at_override:
            create_kwargs['issued_at'] = issued_at_override

        # Dedup: if patient already has an active token for this service today,
        # reuse it instead of creating a duplicate (prevents stacking on retries).
        _existing_token = None
        if visit.patient:
            _existing_token = QueueToken.objects.filter(
                patient=visit.patient,
                service_type=service_type,
                token_date=timezone.localdate(),
                status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                is_deleted=False,
            ).first()
        if _existing_token:
            dept_token = _existing_token
        else:
            dept_token = QueueToken.objects.create(**create_kwargs)

        # Complete the calling user's existing active token so the patient
        # leaves the originating queue (e.g. REFRACTION token when PEDS_REFRAC
        # routes to GENERAL).  Only complete if it's a different service type.
        _ROLE_TO_QMS_SVC = {
            'ophthalmologist':           'GENERAL',
            'intern':                    'GENERAL',
            'retina_specialist':         'RETINA',
            'glaucoma_specialist':       'GLAUCOMA',
            'pediatric_ophthalmologist': 'PEDIATRIC',
            'pediatric_refractionist':   'REFRACTION',
            'optometrist':               'REFRACTION',
            'cataract_surgeon':          'CATARACT',
            'cornea_specialist':         'CORNEA',
            'oculoplastics_surgeon':     'OCULOPLASTY',
            'neuro_ophthalmologist':     'NEURO',
            'uveitis_specialist':        'UVEITIS',
            'low_vision_specialist':     'LOW_VISION',
            'general_physician':         'GEN_PHYS',
        }
        _user_svc = _ROLE_TO_QMS_SVC.get(getattr(request.user, 'role', ''))
        if _user_svc and _user_svc != service_type and visit.patient:
            QueueToken.objects.filter(
                patient=visit.patient,
                service_type=_user_svc,
                token_date=timezone.localdate(),
                status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                is_deleted=False,
            ).update(status=TokenStatus.COMPLETED, completed_at=timezone.now())

        # Update visit status and department — SKIP for VIP specialist calls
        # (VIP patient stays in the VIP room; only the specialist moves)
        if not _is_vip_call_early:
            # Build reverse map — for service types that map to multiple visit
            # statuses (e.g. GENERAL → WAITING and IN_CONSULTATION), prefer WAITING.
            _prefer_status = {'GENERAL': 'WAITING'}
            reverse_map = {v: k for k, v in VISIT_STATUS_TO_SERVICE_TYPE.items()}
            reverse_map.update(_prefer_status)
            new_status = reverse_map.get(service_type)
            update_fields = ['updated_at']
            if new_status:
                visit.status = new_status
                update_fields.append('status')
            # Update visit department to the target department so the receiving
            # doctor's queue (which filters by department) picks up the patient.
            from apps.departments.models import Department as _Dept
            _SERVICE_TO_DEPT_CODE = {
                'REFRACTION':   'REFRAC',
                'RETINA':       'RETINA',
                'GLAUCOMA':     'GLAUC',
                'CATARACT':     'CATARACT',
                'PEDIATRIC':    'PEDS_OPH',
                'NEURO':        'NEURO_OPH',
                'OCULOPLASTY':  'OCULOPLASTY',
                'CORNEA':       'CORNEA',
                'GENERAL':      'GEN_OPH',
                'VIP_CONSULT':  'GEN_OPH',
                'EXP_CONSULT':  'GEN_OPH',
                'INSUR_CONSULT':'GEN_OPH',
                'INVEST':       'INVEST',
                'UVEITIS':      'UVEITIS',
                'LAB':          'LAB',
                'PHARMACY':     'PHARMACY',
            }
            target_dept_code = _SERVICE_TO_DEPT_CODE.get(service_type)
            if target_dept_code:
                target_dept = _Dept.objects.filter(code=target_dept_code, is_active=True).first()
                if target_dept:
                    visit.department = target_dept
                    update_fields.append('department')
            visit.save(update_fields=update_fields)
            if new_status:
                try:
                    from apps.core.ws_notify import notify_queue as _ws_nq
                    from apps.core.patient_flow import _STATUS_ROOMS as _SR
                    for _rm in _SR.get(new_status, []):
                        _ws_nq(_rm)
                except Exception:
                    pass

    is_vip_call = _is_vip_call_early
    dept_label = dict(ServiceType.choices).get(service_type, service_type)
    priority_inserted = issued_at_override is not None

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('HX-Request'):
        return JsonResponse({
            'success': True,
            'token_number': dept_token.token_number,
            'department': dept_label,
            'tier': tier,
            'priority': base_priority,
            'priority_inserted': priority_inserted,
            'is_vip_call': is_vip_call,
        })

    if is_vip_call:
        msg = (f'VIP specialist call sent to {dept_label}. '
               f'Token: {dept_token.token_number} — specialist will come to VIP Room.')
    else:
        msg = f'Patient routed to {dept_label}. Token: {dept_token.token_number}'
        if priority_inserted:
            msg += f' — inserted at position ~{_INSERT_AFTER + 1} (priority queue).'
    messages.success(request, msg)
    return redirect(request.POST.get('next', 'qms:dashboard'))


# ── Counter staff views ───────────────────────────────────────────────────────

@login_required
def counter_view(request, counter_id):
    """Counter staff view — waiting list, call next, complete."""
    if not _qms_active():
        return redirect('dashboard:home')
    counter = get_object_or_404(ServiceCounter, id=counter_id, is_active=True)
    today = timezone.localdate()

    # Respect tier filtering if counter has serves_tiers set
    served_tiers = counter.get_serves_tiers()

    # ── Room-based queue (new system) ────────────────────────────────────────
    # If this counter has a checked-in doctor today, show only tokens assigned
    # to this specific counter. Otherwise fall back to shared service-type pool.
    if counter.is_checked_in_today:
        waiting = QueueToken.objects.filter(
            counter=counter,
            status=TokenStatus.WAITING,
            token_date=today,
            is_deleted=False,
        ).select_related('patient', 'visit').order_by('-priority', 'issued_at')
    else:
        # Fallback: shared pool by service type (old behaviour, no doctor checked in)
        waiting = QueueToken.objects.filter(
            service_type=counter.service_type,
            status=TokenStatus.WAITING,
            token_date=today,
            is_deleted=False,
            service_tier__in=served_tiers,
        ).select_related('patient', 'visit').order_by('-priority', 'issued_at')

    context = {
        'counter': counter,
        'waiting': waiting,
        'waiting_count': waiting.count(),
        'tier_choices': ServiceTier.choices,
        'is_checked_in': counter.is_checked_in_today,
    }
    return render(request, 'qms/counter.html', context)


@json_error_handler
@login_required
@require_POST
def call_next(request, counter_id):
    """Call the next waiting token for a counter (tier-priority aware)."""
    counter = get_object_or_404(ServiceCounter, id=counter_id, is_active=True)
    today = timezone.localdate()

    served_tiers = counter.get_serves_tiers()

    with transaction.atomic():
        # Auto-complete current serving token if still open
        if counter.current_serving and counter.current_serving.status in (
            TokenStatus.CALLED, TokenStatus.SERVING
        ):
            counter.current_serving.complete()
            counter.current_serving = None
            counter.save(update_fields=['current_serving', 'updated_at'])

        # Room-based: if doctor checked in, only call their counter's patients
        if counter.is_checked_in_today:
            next_token = QueueToken.objects.select_for_update().filter(
                counter=counter,
                status=TokenStatus.WAITING,
                token_date=today,
                is_deleted=False,
            ).order_by('-priority', 'issued_at').first()
        else:
            next_token = QueueToken.objects.select_for_update().filter(
                service_type=counter.service_type,
                status=TokenStatus.WAITING,
                token_date=today,
                is_deleted=False,
                service_tier__in=served_tiers,
            ).order_by('-priority', 'issued_at').first()

        if next_token:
            next_token.call(counter)
            next_token.start_serving()
            counter.current_serving = next_token
            counter.save(update_fields=['current_serving', 'updated_at'])

            tier_label, tier_color = next_token.tier_label
            return JsonResponse({
                'success': True,
                'token': next_token.display_token_number,
                'patient': next_token.display_name,
                'counter': counter.name,
                'tier': tier_label,
                'tier_color': tier_color,
            })

    return JsonResponse({'success': False, 'message': 'No waiting patients'})


@json_error_handler
@login_required
@require_POST
def complete_token(request, token_id):
    """Mark a token as completed and free the counter."""
    token = get_object_or_404(QueueToken, id=token_id)
    scope_err = _check_zone_scope(request, token)
    if scope_err:
        return scope_err
    token.complete()
    if token.counter:
        token.counter.current_serving = None
        token.counter.save(update_fields=['current_serving', 'updated_at'])
    return JsonResponse({'success': True})


@json_error_handler
@login_required
@require_POST
def clear_counter(request, counter_id):
    """Manually clear current_serving from a counter (staff resets their desk)."""
    counter = get_object_or_404(ServiceCounter, id=counter_id, is_active=True)
    if counter.current_serving and counter.current_serving.status in (
        TokenStatus.CALLED, TokenStatus.SERVING
    ):
        counter.current_serving.complete()
    counter.current_serving = None
    counter.save(update_fields=['current_serving', 'updated_at'])
    return JsonResponse({'success': True})


@json_error_handler
@login_required
@require_POST
def skip_token(request, token_id):
    """Skip/re-queue a token (moves to back of queue)."""
    token = get_object_or_404(QueueToken, id=token_id)
    scope_err = _check_zone_scope(request, token)
    if scope_err:
        return scope_err
    token.status = TokenStatus.SKIPPED
    # Re-issue with same priority but new issued_at so it goes to back
    token.issued_at = timezone.now()
    token.status = TokenStatus.WAITING
    token.save(update_fields=['status', 'issued_at'])
    return JsonResponse({'success': True})


@json_error_handler
@login_required
@require_POST
def no_show(request, token_id):
    """Mark a token as no-show."""
    token = get_object_or_404(QueueToken, id=token_id)
    scope_err = _check_zone_scope(request, token)
    if scope_err:
        return scope_err
    token.status = TokenStatus.NO_SHOW
    token.save(update_fields=['status'])
    return JsonResponse({'success': True})


# ── My Counter — role-aware redirect for counter staff ───────────────────────

@login_required
def my_counter(request):
    """
    Redirect staff directly to their own assigned ServiceCounter.
    Counter staff should never need to see the global QMS dashboard.
    """
    counter = ServiceCounter.objects.filter(
        staff_assigned=request.user, is_active=True
    ).first()
    if counter:
        return redirect('qms:counter', counter_id=counter.id)
    return redirect('qms:no_counter')


@login_required
def no_counter_view(request):
    """Shown when a staff member has no counter assigned yet."""
    return render(request, 'qms/no_counter.html', {'user': request.user})


# ── Doctor queue — specialist sees their waiting patients ─────────────────────

@login_required
def doctor_queue(request):
    """
    Dedicated queue view for doctors/specialists.
    Shows WAITING patients in the doctor's specialty service type.
    Doctor can call next and proceed to open a consultation.
    """
    if not _qms_active():
        return redirect('consultations:list')

    today = timezone.localdate()
    user = request.user

    # Map doctor role → QMS ServiceType
    # Ophthalmologists use consultation_unit to determine their specific desk.
    _ROLE_TO_SERVICE = {
        'retina_specialist':         'RETINA',
        'glaucoma_specialist':       'GLAUCOMA',
        'pediatric_ophthalmologist': 'PEDIATRIC',
        'cataract_surgeon':          'CATARACT',
        'cornea_specialist':         'CORNEA',
        'oculoplastics_surgeon':     'OCULOPLASTY',
        'neuro_ophthalmologist':     'NEURO',
        'uveitis_specialist':        'UVEITIS',
        'optometrist':               'REFRACTION',
        'pediatric_refractionist':   'PEDIATRIC',
        'low_vision_specialist':     'LOW_VISION',
        'intern':                    'GENERAL',
        'medical_director':          'GENERAL',
        'general_physician':         'GEN_PHYS',
    }
    if user.role == 'ophthalmologist':
        # Map consultation_unit to canonical service_type (include legacy aliases)
        _cu = (getattr(user, 'consultation_unit', '') or 'GENERAL').upper()
        _cu_svc = {
            'GENERAL':       'GENERAL',
            'VIP_CONSULT':   'VIP_CONSULT',
            'VIP':           'VIP_CONSULT',
            'EXP_CONSULT':   'EXP_CONSULT',
            'EXPRESS':       'EXP_CONSULT',
            'INSUR_CONSULT': 'INSUR_CONSULT',
            'INSURANCE':     'INSUR_CONSULT',
            'ALL':           'GENERAL',  # ALL-tier doctors see GENERAL pool by default here
        }
        service_type = _cu_svc.get(_cu, 'GENERAL')
    else:
        service_type = _ROLE_TO_SERVICE.get(user.role)

    # ── Room-based queue: if doctor is checked in today, use their counter ───
    checked_in_counter = ServiceCounter.objects.filter(
        staff_assigned=user, checked_in_date=today, is_active=True
    ).select_related('zone').first()

    waiting = QueueToken.objects.none()
    dept_name = 'Your Clinic'

    if checked_in_counter:
        # New system: show only this doctor's counter patients
        waiting = QueueToken.objects.filter(
            counter=checked_in_counter,
            status=TokenStatus.WAITING,
            token_date=today,
            is_deleted=False,
        ).select_related('patient', 'visit').order_by('-priority', 'issued_at')
        dept_name = checked_in_counter.name
    elif service_type:
        waiting = QueueToken.objects.filter(
            service_type=service_type,
            status=TokenStatus.WAITING,
            token_date=today,
            is_deleted=False,
        ).select_related('patient', 'visit').order_by('-priority', 'issued_at')
        dept_name = dict(ServiceType.choices).get(service_type, service_type)

    counter = checked_in_counter

    return render(request, 'qms/doctor_queue.html', {
        'waiting': waiting,
        'waiting_count': waiting.count(),
        'dept_name': dept_name,
        'service_type': service_type,
        'counter': counter,
        'today': today,
    })


# ── Cashier: confirm payment → create Visit → route to Triage ────────────────

@login_required
@require_POST
def cashier_complete(request, token_id):
    """
    Cashier confirms payment has been received.
    Zone-scope enforced: a Standard cashier cannot complete a VIP patient's token.

    1. Completes / frees the CASHIER token.
    2. Gets or creates today's Visit for the patient (so triage has a visit to work with).
    3. Creates a PARAMETERS (Standard) or PARAMS_VIP (VIP/Express/FT) token
       so the patient appears in the triage nurse's queue immediately.
    4. Redirects back to the cashier's counter.

    This is the ONLY moment a Visit is created for new patients — it represents
    the start of today's clinical encounter (payment confirmed = encounter open).
    """
    token = get_object_or_404(QueueToken, id=token_id, is_deleted=False)
    scope_err = _check_zone_scope(request, token)
    if scope_err:
        return scope_err
    counter_id = token.counter_id

    if not token.patient:
        messages.error(request, 'No patient record linked to this token. Cannot auto-route to triage.')
        if counter_id:
            return redirect('qms:counter', counter_id=counter_id)
        return redirect('qms:dashboard')

    today = timezone.localdate()

    with transaction.atomic():
        # 1 — Complete cashier token & free counter
        token.complete()
        if token.counter:
            token.counter.current_serving = None
            token.counter.save(update_fields=['current_serving', 'updated_at'])

        # 2 — Get or create today's Visit
        visit = Visit.objects.filter(
            patient=token.patient,
            visit_date__date=today,
            is_deleted=False,
        ).first()

        if not visit:
            has_prior = Visit.objects.filter(
                patient=token.patient, is_deleted=False
            ).exclude(id=None).exists()
            visit = Visit.objects.create(
                patient=token.patient,
                visit_type=VisitType.FOLLOW_UP if has_prior else VisitType.NEW,
                chief_complaint='',
                status=VisitStatus.PARAMETERS,
                service_tier=token.service_tier,
                created_by=request.user,
            )
        else:
            visit.status = VisitStatus.PARAMETERS
            visit.save(update_fields=['status', 'updated_at'])
            try:
                from apps.core.ws_notify import notify_queue as _ws_nq_qms
                _ws_nq_qms('opd')
            except Exception:
                pass

        # 3 — Create triage token (tier-aware)
        triage_stype = (
            ServiceType.PARAMETERS
            if token.service_tier == ServiceTier.STANDARD
            else ServiceType.PARAMETERS_VIP
        )
        triage_num = DailyTokenSequence.next_dept_token(triage_stype)
        QueueToken.objects.create(
            token_number=triage_num,
            token_date=today,
            patient=token.patient,
            visit=visit,
            patient_name=token.patient.full_name,
            service_type=triage_stype,
            service_tier=token.service_tier,
            issuance_point=IssuancePoint.SYSTEM,
            priority=TIER_PRIORITY.get(token.service_tier, 0),
            entry_token=token.entry_token or token,
            issued_by=request.user,
            notes='Auto-routed after payment confirmation at cashier',
            zone=_resolve_zone(token.service_tier),
            origin_zone=token.origin_zone or _resolve_zone(token.service_tier),
        )

    messages.success(
        request,
        f'Payment confirmed. {token.patient.full_name} added to Triage queue.'
    )
    if counter_id:
        return redirect('qms:counter', counter_id=counter_id)
    return redirect('qms:dashboard')


# ── Display board (TV) ────────────────────────────────────────────────────────

def display_board(request):  # noqa: C901
    """
    Public TV display board — no login required.
    Routes to either the token board or names board based on HospitalConfig.queue_board_type.
    Use ?zone=ZONE to show only the counters relevant to that TV location.

    Zone mode: unified chronological call log — all calls in this zone,
    oldest row at top, newest at bottom, auto-scrolls, NOW SERVING highlighted.

    Overview (no zone): compact card grid — one card per active counter.

    Zones
    -----
    entry        → Standard Registration + Standard Cashier (one log)
    triage       → Standard Parameters / Triage
    general      → General OPH + Refraction + Cataract (one log, door numbers shown)
    retina       → Retina Clinic
    glaucoma     → Glaucoma Clinic
    pediatric    → Paediatric Ophthalmology
    investigation→ Eye Investigations
    laboratory   → Laboratory
    express      → ALL Express/FT/Insurance (cashier, params, consult, pharmacy = one log)
    vip          → ALL VIP services (one log)
    pharmacy     → General Pharmacy (Standard tier only)
    optical      → Optical Shop + Optical Cashier (one log)
    admission    → Surgical Counseling + Billing + Admission
    (blank)      → Full overview card grid
    """
    # Check which board type is configured — route accordingly
    try:
        from apps.accounts.models import HospitalConfig
        board_type = HospitalConfig.get().queue_board_type
        if board_type == 'names':
            return names_board(request)
    except Exception:
        pass

    today = timezone.localdate()
    zone  = request.GET.get('zone', '').strip().lower()

    # Zone definitions — token-level Q filters (not counter-level)
    ZONE_CONFIGS = {
        'entry': {
            'label': 'Registration & Cashier',
            'color': '#0ea5e9',
            'q': (
                Q(service_type__in=['RECEPTIONIST', 'CASHIER'])
                & Q(service_tier='STANDARD')
            ),
        },
        'triage': {
            'label': 'Parameters / Triage',
            'color': '#ef4444',
            'q': Q(service_type='PARAMETERS') & Q(service_tier='STANDARD'),
        },
        'general': {
            'label': 'General Clinic · Refraction · Cataract',
            'color': '#3b82f6',
            'q': Q(service_type__in=['GENERAL', 'REFRACTION', 'CATARACT']),
        },
        'retina': {
            'label': 'Retina Clinic',
            'color': '#f97316',
            'q': Q(service_type='RETINA'),
        },
        'glaucoma': {
            'label': 'Glaucoma Clinic',
            'color': '#06b6d4',
            'q': Q(service_type='GLAUCOMA'),
        },
        'pediatric': {
            'label': 'Paediatric Ophthalmology',
            'color': '#ec4899',
            'q': Q(service_type='PEDIATRIC'),
        },
        'investigation': {
            'label': 'Eye Investigations',
            'color': '#f59e0b',
            'q': Q(service_type='INVEST'),
        },
        'laboratory': {
            'label': 'Laboratory',
            'color': '#14b8a6',
            'q': Q(service_type='LAB'),
        },
        'express': {
            'label': 'Express · Fast Track · Insurance',
            'color': '#22d3ee',
            'q': (
                Q(service_tier__in=['EXPRESS', 'FAST_TRACK'])
                | Q(service_type='INSUR_CONSULT')
            ),
        },
        'vip': {
            'label': 'VIP Services',
            'color': '#a78bfa',
            'q': Q(service_tier='VIP'),
        },
        'pharmacy': {
            'label': 'General Pharmacy',
            'color': '#22c55e',
            'q': Q(service_type='PHARMACY') & Q(service_tier='STANDARD'),
        },
        'optical': {
            'label': 'Optical Shop',
            'color': '#8b5cf6',
            'q': Q(service_type='OPTICAL'),
        },
        'admission': {
            'label': 'Admission & Counseling',
            'color': '#64748b',
            'q': Q(service_type__in=['COUNSEL', 'BILLING', 'ADMISSION']),
        },
        'laser': {
            'label': 'Laser Clinic',
            'color': '#dc2626',
            'q': Q(service_type='LASER'),
        },
        'injection': {
            'label': 'Intravitreal Injection Clinic',
            'color': '#7c3aed',
            'q': Q(service_type='INJECTION'),
        },
        'emergency': {
            'label': 'Emergency / Casualty Eye',
            'color': '#ef4444',
            'q': Q(service_type='EMERGENCY'),
        },
        'low_vision': {
            'label': 'Low Vision & Rehabilitation',
            'color': '#0891b2',
            'q': Q(service_type='LOW_VISION'),
        },
        'uveitis': {
            'label': 'Uveitis Clinic',
            'color': '#7c3aed',
            'q': Q(service_type='UVEITIS'),
        },
    }

    ZONE_LABELS = {k: v['label'] for k, v in ZONE_CONFIGS.items()}

    if zone and zone in ZONE_CONFIGS:
        zone_cfg   = ZONE_CONFIGS[zone]
        zone_label = zone_cfg['label']
        zone_color = zone_cfg['color']
        zone_q     = zone_cfg['q']

        # Last 30 called/serving/completed tokens for this zone, newest at bottom
        raw_qs = QueueToken.objects.filter(
            zone_q,
            token_date=today,
            is_deleted=False,
            status__in=[TokenStatus.CALLED, TokenStatus.SERVING, TokenStatus.COMPLETED],
            called_at__isnull=False,
        ).select_related('counter', 'entry_token', 'patient').order_by('-called_at')[:30]

        call_log = list(reversed(list(raw_qs)))
        for tok in call_log:
            tok.is_now = tok.status in (TokenStatus.CALLED, TokenStatus.SERVING)

        waiting_count = QueueToken.objects.filter(
            zone_q,
            token_date=today,
            is_deleted=False,
            status=TokenStatus.WAITING,
        ).count()

        counters_all = []

    else:
        zone          = ''
        zone_label    = 'All Departments — Overview'
        zone_color    = '#334155'
        call_log      = []
        waiting_count = 0
        counters_all  = list(
            ServiceCounter.objects.filter(is_active=True).select_related(
                'current_serving', 'current_serving__entry_token', 'staff_assigned',
            ).order_by('service_type', 'name')
        )
        for counter in counters_all:
            counter.waiting_count = QueueToken.objects.filter(
                service_type=counter.service_type,
                status=TokenStatus.WAITING,
                token_date=today,
                is_deleted=False,
            ).count()

    # Priority banner — global, shows on every TV
    last_priority_call = QueueToken.objects.filter(
        token_date=today,
        status__in=[TokenStatus.CALLED, TokenStatus.SERVING],
        service_tier__in=[ServiceTier.VIP, ServiceTier.FAST_TRACK, ServiceTier.EXPRESS],
        is_deleted=False,
    ).select_related('counter', 'entry_token').order_by('-called_at').first()

    context = {
        'zone':               zone,
        'zone_label':         zone_label,
        'zone_color':         zone_color,
        'call_log':           call_log,
        'waiting_count':      waiting_count,
        'counters':           counters_all,
        'last_priority_call': last_priority_call,
        'all_zones':          ZONE_LABELS,
        'today':              today,
    }
    return render(request, 'qms/display_board.html', context)


def names_board(request):
    """
    Display Board 2 — Live patient names queue board.
    Shows all waiting/serving patients ranked by position.
    Names animate upward as patients move through the queue.
    No login required (public TV display).
    """
    today = timezone.localdate()
    zone  = request.GET.get('zone', '').strip().lower()

    ZONE_CONFIGS = {
        'entry':         {'label': 'Registration & Cashier',           'serving_label': 'At Reception / Cashier',     'color': '#0ea5e9', 'q': Q(service_type__in=['RECEPTIONIST','CASHIER'], service_tier='STANDARD')},
        'triage':        {'label': 'Parameters / Triage',              'serving_label': 'At Triage / Parameters',     'color': '#ef4444', 'q': Q(service_type='PARAMETERS', service_tier='STANDARD')},
        'general':       {'label': 'General Ophthalmology',            'serving_label': 'Currently with Doctor',      'color': '#3b82f6', 'q': Q(service_type__in=['GENERAL','REFRACTION','CATARACT'])},
        'retina':        {'label': 'Retina Clinic',                    'serving_label': 'Currently with Doctor',      'color': '#f97316', 'q': Q(service_type='RETINA')},
        'glaucoma':      {'label': 'Glaucoma Clinic',                  'serving_label': 'Currently with Doctor',      'color': '#06b6d4', 'q': Q(service_type='GLAUCOMA')},
        'pediatric':     {'label': 'Paediatric Ophthalmology',         'serving_label': 'Currently with Doctor',      'color': '#ec4899', 'q': Q(service_type='PEDIATRIC')},
        'investigation': {'label': 'Eye Investigations',               'serving_label': 'At Investigations',          'color': '#f59e0b', 'q': Q(service_type='INVEST')},
        'laboratory':    {'label': 'Laboratory',                       'serving_label': 'At Laboratory',              'color': '#14b8a6', 'q': Q(service_type='LAB')},
        'express':       {'label': 'Express · Fast Track · Insurance', 'serving_label': 'Currently Serving',          'color': '#8b5cf6', 'q': Q(service_tier__in=['EXPRESS','FAST_TRACK','INSURANCE'])},
        'vip':           {'label': 'VIP Services',                     'serving_label': 'Currently Serving — VIP',    'color': '#d97706', 'q': Q(service_tier='VIP')},
        'pharmacy':      {'label': 'Pharmacy',                         'serving_label': 'At Pharmacy',                'color': '#10b981', 'q': Q(service_type='PHARMACY', service_tier='STANDARD')},
    }

    ZONE_LABELS = {k: v['label'] for k, v in ZONE_CONFIGS.items()}

    if zone and zone in ZONE_CONFIGS:
        cfg = ZONE_CONFIGS[zone]
        zone_label = cfg['label']
        zone_color = cfg['color']
        base_q = cfg['q'] & Q(token_date=today, is_deleted=False)

        # Currently being served (top of board, highlighted)
        serving = QueueToken.objects.filter(
            base_q, status__in=[TokenStatus.CALLED, TokenStatus.SERVING]
        ).select_related('entry_token').order_by('-called_at')[:3]

        # Waiting — ordered by token number (position in queue)
        waiting = QueueToken.objects.filter(
            base_q, status=TokenStatus.WAITING
        ).select_related('entry_token').order_by('token_number')[:30]

        # Recently completed (last 5, shown dimmed at bottom)
        completed = QueueToken.objects.filter(
            base_q, status=TokenStatus.COMPLETED
        ).select_related('entry_token').order_by('-completed_at')[:5]

        patients_serving = []
        for t in serving:
            name = '—'
            if t.entry_token and hasattr(t.entry_token, 'patient'):
                p = t.entry_token.patient if hasattr(t.entry_token, 'patient') else None
                if p:
                    name = p.full_name
            elif hasattr(t, 'patient_name') and t.patient_name:
                name = t.patient_name
            patients_serving.append({'token': t, 'name': name})

        patients_waiting = []
        for i, t in enumerate(waiting):
            name = '—'
            if t.entry_token and hasattr(t.entry_token, 'patient'):
                p = getattr(t.entry_token, 'patient', None)
                if p:
                    name = p.full_name
            elif hasattr(t, 'patient_name') and t.patient_name:
                name = t.patient_name
            patients_waiting.append({'token': t, 'name': name, 'position': i + 1})

        context = {
            'zone': zone,
            'zone_label': zone_label,
            'zone_color': zone_color,
            'serving_label': cfg.get('serving_label', 'Currently Serving'),
            'patients_serving': patients_serving,
            'patients_waiting': patients_waiting,
            'waiting_count': waiting.count(),
            'today': today,
            'all_zones': ZONE_LABELS,
        }
    else:
        # Overview: show all active zones with their counts
        zone_summaries = []
        for key, cfg in ZONE_CONFIGS.items():
            base_q = cfg['q'] & Q(token_date=today, is_deleted=False)
            waiting_count = QueueToken.objects.filter(base_q, status=TokenStatus.WAITING).count()
            serving_count = QueueToken.objects.filter(base_q, status__in=[TokenStatus.CALLED, TokenStatus.SERVING]).count()
            if waiting_count + serving_count > 0:
                zone_summaries.append({
                    'key': key,
                    'label': cfg['label'],
                    'color': cfg['color'],
                    'waiting': waiting_count,
                    'serving': serving_count,
                })
        context = {
            'zone': '',
            'zone_summaries': zone_summaries,
            'today': today,
            'all_zones': ZONE_LABELS,
        }

    return render(request, 'qms/names_board.html', context)


def consult_room_display(request):
    """
    Consultation room call display — for TV/screen mounted outside consultation rooms.
    Shows which token number is NOW SERVING in each room.
    No login required (public display inside facility).
    """
    today = timezone.localdate()

    # All consultation tokens called or serving today that have a room assigned
    CONSULT_TYPES = [
        'GENERAL', 'VIP_CONSULT', 'EXP_CONSULT',
        'RETINA', 'GLAUCOMA', 'PEDIATRIC', 'CORNEA',
        'OCULOPLASTY', 'NEURO', 'CATARACT', 'UVEITIS',
    ]
    active_tokens = (
        QueueToken.objects
        .filter(
            token_date=today,
            service_type__in=CONSULT_TYPES,
            status__in=[TokenStatus.CALLED, TokenStatus.SERVING],
            is_deleted=False,
        )
        .select_related('visit__consultation_room', 'assigned_doctor', 'entry_token')
        .order_by('-called_at')
    )

    # Build room cards — keyed by room label
    rooms = {}
    no_room_tokens = []
    for token in active_tokens:
        room = getattr(getattr(token, 'visit', None), 'consultation_room', None)
        if room:
            key = str(room.pk)
            if key not in rooms:
                rooms[key] = {
                    'room': room,
                    'tokens': [],
                }
            rooms[key]['tokens'].append(token)
        else:
            no_room_tokens.append(token)

    room_cards = sorted(rooms.values(), key=lambda r: str(r['room'].room_number))

    # Recent completions (last 5, for "just served" row)
    recent_done = (
        QueueToken.objects
        .filter(
            token_date=today,
            service_type__in=CONSULT_TYPES,
            status=TokenStatus.COMPLETED,
            is_deleted=False,
        )
        .select_related('visit__consultation_room', 'assigned_doctor')
        .order_by('-completed_at')[:5]
    )

    context = {
        'room_cards':     room_cards,
        'no_room_tokens': no_room_tokens,
        'recent_done':    recent_done,
        'today':          today,
    }
    return render(request, 'qms/consult_room_display.html', context)


# ── JSON / HTMX endpoints ─────────────────────────────────────────────────────

@login_required
def queue_stats(request):
    """Live queue stats per department — for HTMX polling."""
    today = timezone.localdate()
    stats = {}
    for code, label in ServiceType.choices:
        waiting = QueueToken.objects.filter(
            service_type=code,
            status=TokenStatus.WAITING,
            token_date=today,
            is_deleted=False,
        ).count()
        stats[code] = {'label': label, 'waiting': waiting}
    return JsonResponse({'stats': stats, 'timestamp': timezone.now().isoformat()})


@login_required
def patient_queue_status(request, patient_id):
    """Return today's queue tokens for a patient (for consultation views)."""
    patient = get_object_or_404(Patient, patient_id=patient_id, is_deleted=False)
    today = timezone.localdate()
    tokens = QueueToken.objects.filter(
        patient=patient,
        token_date=today,
        is_deleted=False,
    ).select_related('counter').order_by('issued_at')

    data = [{
        'token_number': t.token_number,
        'service_type': t.service_type,
        'service_type_label': dict(ServiceType.choices).get(t.service_type, t.service_type),
        'service_tier': t.service_tier,
        'status': t.status,
        'counter': t.counter.name if t.counter else None,
        'issuance_point': t.issuance_point,
    } for t in tokens]

    return JsonResponse({'tokens': data})


@login_required
def daily_census(request):
    """Daily census summary — entry tickets issued per tier."""
    today = timezone.localdate()
    from django.db.models import Count

    entry_tokens = QueueToken.objects.filter(
        token_date=today,
        issuance_point__in=[
            IssuancePoint.GATE, IssuancePoint.CASHIER,
            IssuancePoint.VIP_RECEPTION, IssuancePoint.EXPRESS_DESK,
        ],
        is_deleted=False,
    )

    census = entry_tokens.values('service_tier', 'issuance_point').annotate(
        count=Count('id')
    ).order_by('service_tier')

    totals = {tier: 0 for tier, _ in ServiceTier.choices}
    for row in census:
        totals[row['service_tier']] = totals.get(row['service_tier'], 0) + row['count']

    context = {
        'census': list(census),
        'totals': totals,
        'grand_total': entry_tokens.count(),
        'today': today,
        'tier_choices': ServiceTier.choices,
        'base_layout': _slip_layout(request.user),
        'today_count': entry_tokens.count(),
    }
    return render(request, 'qms/daily_census.html', context)


# ── Counter assignment (admin only) ───────────────────────────────────────────

@login_required
def counter_assign_view(request):
    """Replaced by roster_view — redirect for backwards compatibility."""
    return redirect('qms:roster')


# ── Counter Management (CRUD) ─────────────────────────────────────────────────
_COUNTER_MANAGE_ROLES = {'super_admin', 'medical_director', 'admin', 'admin_director', 'ceo'}


def _counter_manage_guard(request):
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    if request.user.role not in _COUNTER_MANAGE_ROLES:
        from django.contrib import messages as _msg
        _msg.error(request, 'You do not have permission to manage counters.')
        return redirect('qms:dashboard')
    return None


def counter_manage_view(request):
    """List all service counters (active + inactive) with create/edit/toggle links."""
    guard = _counter_manage_guard(request)
    if guard:
        return guard
    counters = ServiceCounter.objects.select_related('staff_assigned', 'zone').order_by('service_type', 'name')
    return render(request, 'qms/counter_manage.html', {
        'counters': counters,
        'service_types': ServiceType.choices,
    })


def counter_create_view(request):
    """Create a new ServiceCounter."""
    from apps.accounts.models import User as _User
    guard = _counter_manage_guard(request)
    if guard:
        return guard

    error = None
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        service_type = request.POST.get('service_type', '')
        serves_tiers = ','.join(request.POST.getlist('serves_tiers'))
        is_active = request.POST.get('is_active') == '1'
        staff_id = request.POST.get('staff_id') or None
        zone_id = request.POST.get('zone_id') or None
        station_type = request.POST.get('station_type', '').strip()
        anti_min = int(request.POST.get('anti_starvation_minutes', 45) or 45)

        if not name or not code or not service_type:
            error = 'Name, Code, and Service Type are required.'
        elif ServiceCounter.objects.filter(code=code).exists():
            error = f'A counter with code "{code}" already exists.'
        else:
            staff = None
            if staff_id:
                staff = get_object_or_404(_User, id=staff_id)
            zone = Zone.objects.filter(id=zone_id).first() if zone_id else None
            ServiceCounter.objects.create(
                name=name, code=code, service_type=service_type,
                serves_tiers=serves_tiers, is_active=is_active,
                staff_assigned=staff, zone=zone,
                station_type=station_type,
                anti_starvation_minutes=anti_min,
                checked_in_date=timezone.localdate() if staff else None,
            )
            messages.success(request, f'Counter "{name}" created.')
            return redirect('qms:counter_manage')

    staff_users = _User.objects.filter(is_active=True).order_by('role', 'last_name')
    zones = Zone.objects.filter(is_active=True).order_by('name')
    return render(request, 'qms/counter_form.html', {
        'form_title': 'Create Counter',
        'service_type_choices': ServiceType.choices,
        'tier_choices': ServiceTier.choices,
        'station_type_choices': StationType.choices,
        'staff_users': staff_users,
        'zones': zones,
        'counter': None,
        'error': error,
    })


def counter_edit_view(request, counter_id):
    """Edit an existing ServiceCounter."""
    from apps.accounts.models import User as _User
    guard = _counter_manage_guard(request)
    if guard:
        return guard

    counter = get_object_or_404(ServiceCounter, id=counter_id)
    error = None

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        service_type = request.POST.get('service_type', '')
        serves_tiers = ','.join(request.POST.getlist('serves_tiers'))
        is_active = request.POST.get('is_active') == '1'
        staff_id = request.POST.get('staff_id') or None
        zone_id = request.POST.get('zone_id') or None
        station_type = request.POST.get('station_type', '').strip()
        anti_min = int(request.POST.get('anti_starvation_minutes', 45) or 45)

        if not name or not code or not service_type:
            error = 'Name, Code, and Service Type are required.'
        elif ServiceCounter.objects.filter(code=code).exclude(id=counter.id).exists():
            error = f'A counter with code "{code}" already exists.'
        else:
            staff = None
            if staff_id:
                staff = get_object_or_404(_User, id=staff_id)
            zone = Zone.objects.filter(id=zone_id).first() if zone_id else None
            counter.name = name
            counter.code = code
            counter.service_type = service_type
            counter.serves_tiers = serves_tiers
            counter.is_active = is_active
            counter.staff_assigned = staff
            counter.zone = zone
            counter.station_type = station_type
            counter.anti_starvation_minutes = anti_min
            # If staff is being assigned, mark them as checked-in today so the roster reflects it immediately
            if staff:
                counter.checked_in_date = timezone.localdate()
            elif not staff:
                counter.checked_in_date = None
            counter.save(update_fields=['name', 'code', 'service_type', 'serves_tiers',
                                        'is_active', 'staff_assigned', 'zone',
                                        'station_type', 'anti_starvation_minutes',
                                        'checked_in_date', 'updated_at'])
            messages.success(request, f'Counter "{name}" updated.')
            return redirect('qms:counter_manage')

    staff_users = _User.objects.filter(is_active=True).order_by('role', 'last_name')
    zones = Zone.objects.filter(is_active=True).order_by('name')
    return render(request, 'qms/counter_form.html', {
        'form_title': f'Edit Counter — {counter.name}',
        'service_type_choices': ServiceType.choices,
        'tier_choices': ServiceTier.choices,
        'station_type_choices': StationType.choices,
        'staff_users': staff_users,
        'zones': zones,
        'counter': counter,
        'selected_tiers': counter.get_serves_tiers() if counter.serves_tiers else [],
        'error': error,
    })


def counter_toggle_view(request, counter_id):
    """Toggle is_active on a ServiceCounter (POST only)."""
    guard = _counter_manage_guard(request)
    if guard:
        return guard
    if request.method != 'POST':
        return redirect('qms:counter_manage')
    counter = get_object_or_404(ServiceCounter, id=counter_id)
    counter.is_active = not counter.is_active
    counter.save(update_fields=['is_active', 'updated_at'])
    state = 'activated' if counter.is_active else 'deactivated'
    messages.success(request, f'Counter "{counter.name}" {state}.')
    return redirect('qms:counter_manage')


def counter_delete_view(request, counter_id):
    """Delete a ServiceCounter (POST only). Blocked if currently serving a token."""
    guard = _counter_manage_guard(request)
    if guard:
        return guard
    if request.method != 'POST':
        return redirect('qms:counter_manage')
    counter = get_object_or_404(ServiceCounter, id=counter_id)
    if counter.current_serving_id:
        messages.error(request, f'Cannot delete "{counter.name}" — it is currently serving a patient.')
        return redirect('qms:counter_manage')
    name = counter.name
    counter.delete()
    messages.success(request, f'Counter "{name}" deleted.')
    return redirect('qms:counter_manage')


# ════════════════════════════════════════════════════════════════════════════════
# TODAY'S ROSTER  —  Admin assigns doctors to rooms each morning.
# Doctor-centric routing: patient token follows the DOCTOR, room is just a label.
# ════════════════════════════════════════════════════════════════════════════════

# Roles that can be assigned to counters (doctors / clinical staff)
_CLINICAL_CHECKIN_ROLES = {
    'ophthalmologist', 'retina_specialist', 'glaucoma_specialist',
    'pediatric_ophthalmologist', 'cataract_surgeon', 'cornea_specialist',
    'oculoplastics_surgeon', 'neuro_ophthalmologist', 'uveitis_specialist',
    'optometrist', 'pediatric_refractionist', 'low_vision_specialist',
    'general_physician', 'intern', 'anaesthetist', 'orthoptist',
}

# Map role → eligible service_types for room selection
_ROLE_SERVICE_TYPES = {
    'ophthalmologist':           ['GENERAL', 'VIP_CONSULT', 'EXP_CONSULT', 'INSUR_CONSULT',
                                  'RETINA', 'GLAUCOMA', 'CATARACT', 'PEDIATRIC', 'CORNEA',
                                  'OCULOPLASTY', 'NEURO', 'UVEITIS'],
    'retina_specialist':         ['RETINA'],
    'glaucoma_specialist':       ['GLAUCOMA'],
    'pediatric_ophthalmologist': ['PEDIATRIC'],
    'cataract_surgeon':          ['CATARACT'],
    'cornea_specialist':         ['CORNEA'],
    'oculoplastics_surgeon':     ['OCULOPLASTY'],
    'neuro_ophthalmologist':     ['NEURO'],
    'uveitis_specialist':        ['UVEITIS'],
    'optometrist':               ['REFRACTION'],
    'pediatric_refractionist':   ['REFRACTION', 'PEDIATRIC'],
    'low_vision_specialist':     ['LOW_VISION'],
    'general_physician':         ['GEN_PHYS'],
    'intern':                    ['GENERAL'],
    'anaesthetist':              ['THEATRE', 'COUNSEL', 'PRE_OP'],
    'orthoptist':                ['GENERAL', 'PEDIATRIC'],
}


@login_required
def roster_view(request):
    """
    Admin page: assign doctors to counters for today (doctor-centric routing).
    GET  → show all active clinical counters with current assignments.
    POST → assign or remove a doctor from a counter.
    """
    if not _qms_active():
        return redirect('dashboard:home')
    if request.user.role not in _COUNTER_MANAGE_ROLES:
        messages.error(request, 'You do not have permission to manage the daily roster.')
        return redirect('qms:dashboard')

    today = timezone.localdate()

    # Build the allowlist of clinical service types from the role map —
    # only rooms where a doctor can actually be assigned appear on the roster.
    _clinical_types = set()
    for _types in _ROLE_SERVICE_TYPES.values():
        _clinical_types.update(_types)

    counters = (
        ServiceCounter.objects
        .filter(is_active=True, is_deleted=False, service_type__in=_clinical_types)
        .select_related('staff_assigned', 'zone')
        .order_by('zone__name', 'name')
    )

    # Clinical doctors available for assignment
    from apps.accounts.models import User as _User
    doctors = (
        _User.objects
        .filter(role__in=_CLINICAL_CHECKIN_ROLES, is_active=True)
        .order_by('last_name', 'first_name')
    )

    if request.method == 'POST':
        action     = request.POST.get('action', '')
        counter_id = request.POST.get('counter_id', '').strip()

        # activate/deactivate don't need an active counter — handle before the guard
        if action in ('activate', 'deactivate'):
            counter_obj = ServiceCounter.objects.filter(id=counter_id, is_deleted=False).first()
            if counter_obj:
                counter_obj.is_active = (action == 'activate')
                counter_obj.save(update_fields=['is_active', 'updated_at'])
                label = 'restored to' if counter_obj.is_active else 'hidden from'
                messages.success(request, f'{counter_obj.name} {label} roster.')
            else:
                messages.error(request, 'Counter not found.')
            return redirect('qms:roster')

        try:
            counter = ServiceCounter.objects.get(id=counter_id, is_active=True)
        except (ServiceCounter.DoesNotExist, ValueError):
            messages.error(request, 'Counter not found.')
            return redirect('qms:roster')

        if action == 'assign':
            doctor_id = request.POST.get('doctor_id', '').strip()
            try:
                doctor = _User.objects.get(id=doctor_id, is_active=True)
            except (_User.DoesNotExist, ValueError):
                messages.error(request, 'Doctor not found.')
                return redirect('qms:roster')
            # If doctor is already in another counter today → move them
            prev = ServiceCounter.objects.filter(
                staff_assigned=doctor, checked_in_date=today, is_active=True
            ).exclude(id=counter.id).first()
            if prev:
                prev.staff_assigned = None
                prev.checked_in_date = None
                prev.save(update_fields=['staff_assigned', 'checked_in_date', 'updated_at'])
            counter.staff_assigned = doctor
            counter.checked_in_date = today
            counter.save(update_fields=['staff_assigned', 'checked_in_date', 'updated_at'])
            messages.success(request, f'{doctor.get_full_name()} assigned to {counter.name}.')

        elif action == 'remove':
            removed_name = counter.staff_assigned.get_full_name() if counter.staff_assigned else counter.name
            counter.staff_assigned = None
            counter.checked_in_date = None
            counter.save(update_fields=['staff_assigned', 'checked_in_date', 'updated_at'])
            messages.success(request, f'{removed_name} removed from {counter.name}.')

        return redirect('qms:roster')

    # Annotate counters: waiting count + assignment status
    from django.db.models import Count as _Count
    count_map = dict(
        QueueToken.objects.filter(
            counter__in=counters, token_date=today, is_deleted=False,
            status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING]
        ).values('counter_id').annotate(n=_Count('id')).values_list('counter_id', 'n')
    )
    counters = list(counters)
    for c in counters:
        c.today_count = count_map.get(c.id, 0)
        c.is_assigned_today = (c.checked_in_date == today and c.staff_assigned_id is not None)

    assigned_count   = sum(1 for c in counters if c.is_assigned_today)
    unassigned_count = len(counters) - assigned_count

    # Inactive clinical rooms — shown collapsed so admin can restore them to the roster
    inactive_counters = (
        ServiceCounter.objects
        .filter(is_active=False, is_deleted=False, service_type__in=_clinical_types)
        .select_related('zone')
        .order_by('zone__name', 'name')
    )

    return render(request, 'qms/roster.html', {
        'counters':          counters,
        'doctors':           doctors,
        'today':             today,
        'assigned_count':    assigned_count,
        'unassigned_count':  unassigned_count,
        'inactive_counters': inactive_counters,
    })


@login_required
def room_checkin_view(request):
    """
    Doctor's 'My Room Today' — shows their admin-assigned room (read-only).
    Admin/manager roles are redirected to the full roster page.
    """
    if not _qms_active():
        return redirect('dashboard:home')

    user = request.user
    today = timezone.localdate()

    if user.role in _COUNTER_MANAGE_ROLES:
        return redirect('qms:roster')

    if user.role not in _CLINICAL_CHECKIN_ROLES:
        messages.error(request, 'This page is not available for your role.')
        return redirect('dashboard:home')

    current = ServiceCounter.objects.filter(
        staff_assigned=user, checked_in_date=today, is_active=True
    ).select_related('zone').first()

    waiting_count = 0
    if current:
        waiting_count = QueueToken.objects.filter(
            counter=current, token_date=today,
            status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
            is_deleted=False
        ).count()

    return render(request, 'qms/my_room_today.html', {
        'current': current,
        'waiting_count': waiting_count,
        'today': today,
    })


@login_required
def room_board_ajax(request):
    """
    AJAX — live room board for triage dispatch.
    Returns zones → rooms with doctor name, waiting count, estimated wait time.
    """
    if not _qms_active():
        return JsonResponse({'zones': []})

    today = timezone.localdate()
    svc_filter = request.GET.get('service_types', '')
    svc_types  = [s.strip() for s in svc_filter.split(',') if s.strip()] if svc_filter else []

    qs = ServiceCounter.objects.filter(is_active=True).select_related('staff_assigned', 'zone')
    if svc_types:
        qs = qs.filter(service_type__in=svc_types)

    # Waiting counts per counter
    from django.db.models import Count as _Count
    counts = dict(
        QueueToken.objects.filter(
            counter__in=qs, status=TokenStatus.WAITING,
            token_date=today, is_deleted=False
        ).values('counter_id').annotate(n=_Count('id')).values_list('counter_id', 'n')
    )

    # Avg consultation duration per counter (from today's completed tokens)
    completed = QueueToken.objects.filter(
        counter__in=qs, token_date=today,
        status=TokenStatus.COMPLETED,
        served_at__isnull=False, completed_at__isnull=False,
        is_deleted=False
    ).values('counter_id', 'served_at', 'completed_at')

    _durations = {}
    for t in completed:
        if t['served_at'] and t['completed_at']:
            mins = (t['completed_at'] - t['served_at']).total_seconds() / 60
            if 1 <= mins <= 120:
                _durations.setdefault(t['counter_id'], []).append(mins)
    avg_consult = {cid: sum(d) / len(d) for cid, d in _durations.items()}

    zones_map = {}
    for c in qs.order_by('zone__name', 'name'):
        zone_name  = c.zone.name  if c.zone else 'Unassigned'
        zone_color = c.zone.color if c.zone else 'secondary'
        if zone_name not in zones_map:
            zones_map[zone_name] = {'name': zone_name, 'color': zone_color, 'rooms': []}
        waiting = counts.get(c.id, 0)
        avg_mins = avg_consult.get(c.id, 15)
        zones_map[zone_name]['rooms'].append({
            'id':              str(c.id),
            'name':            c.name,
            'service_type':    c.service_type,
            'serves_tiers':    c.get_serves_tiers(),  # list of tier codes, empty = all
            'doctor':          c.staff_assigned.get_full_name() if c.is_checked_in_today else None,
            'doctor_id':       str(c.staff_assigned.pk) if c.is_checked_in_today else None,
            'waiting':         waiting,
            'available':       c.is_checked_in_today,
            'estimated_wait':  round(avg_mins * waiting) if waiting else 0,
        })

    return JsonResponse({'zones': list(zones_map.values())})


# ════════════════════════════════════════════════════════════════════════════════
# ZONE MANAGEMENT — System Admin / Medical Director / CEO / Admin Director
# ════════════════════════════════════════════════════════════════════════════════

_ZONE_MANAGE_ROLES = {'super_admin', 'medical_director', 'admin_director', 'ceo'}

_ZONE_COLOR_CHOICES = [
    ('secondary', 'Grey — Standard'),
    ('info',      'Cyan — Fast Track / Express'),
    ('warning',   'Yellow — VIP'),
    ('primary',   'Blue — Shared Services'),
    ('success',   'Green'),
    ('danger',    'Red'),
    ('dark',      'Dark'),
]


def _zone_guard(request):
    if request.user.role not in _ZONE_MANAGE_ROLES and not request.user.is_superuser:
        messages.error(request, 'You do not have permission to manage zones.')
        return redirect('qms:dashboard')
    return None


@login_required
def zone_manage_view(request):
    """
    Zone management dashboard.
    Shows all zones, their tier mappings, station counts and lets admin
    reassign tiers to different zones with a single form submit.
    """
    guard = _zone_guard(request)
    if guard:
        return guard

    zones = Zone.objects.prefetch_related('tier_mappings', 'counters').order_by('name')
    tier_mappings = {m.tier: m for m in TierZoneMapping.objects.select_related('zone')}

    return render(request, 'qms/zone_manage.html', {
        'zones': zones,
        'tier_mappings': tier_mappings,
        'tier_choices': ServiceTier.choices,
    })


@login_required
@require_POST
def tier_remap_view(request):
    """POST: reassign one tier to a different zone."""
    guard = _zone_guard(request)
    if guard:
        return guard

    tier = request.POST.get('tier', '').strip()
    zone_id = request.POST.get('zone_id', '').strip()
    valid_tiers = dict(ServiceTier.choices)

    if tier not in valid_tiers:
        messages.error(request, 'Invalid tier.')
        return redirect('qms:zone_manage')

    zone = get_object_or_404(Zone, id=zone_id)
    mapping, _ = TierZoneMapping.objects.get_or_create(tier=tier)
    old_zone = mapping.zone.name if mapping.zone_id else '—'
    mapping.zone = zone
    mapping.updated_by = request.user
    mapping.save()
    _clear_zone_cache()

    messages.success(
        request,
        f'{valid_tiers[tier]} tier moved from {old_zone} → {zone.name}. '
        'All future tokens for this tier will be placed in the new zone.'
    )
    return redirect('qms:zone_manage')


@login_required
def zone_create_view(request):
    """Create a new hospital zone."""
    guard = _zone_guard(request)
    if guard:
        return guard

    error = None
    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        color = request.POST.get('color', 'secondary').strip()

        if not code or not name:
            error = 'Zone code and name are required.'
        elif Zone.objects.filter(code=code).exists():
            error = f'A zone with code "{code}" already exists.'
        else:
            Zone.objects.create(code=code, name=name, description=description, color=color)
            messages.success(request, f'Zone "{name}" created.')
            return redirect('qms:zone_manage')

    return render(request, 'qms/zone_form.html', {
        'form_title': 'New Zone',
        'zone': None,
        'color_choices': _ZONE_COLOR_CHOICES,
        'error': error,
    })


@login_required
def zone_edit_view(request, zone_id):
    """Edit an existing zone (name, description, colour, active status)."""
    guard = _zone_guard(request)
    if guard:
        return guard

    zone = get_object_or_404(Zone, id=zone_id)
    error = None

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        color = request.POST.get('color', zone.color).strip()
        is_active = request.POST.get('is_active') == '1'

        if not name:
            error = 'Zone name is required.'
        else:
            zone.name = name
            zone.description = description
            zone.color = color
            zone.is_active = is_active
            zone.save()
            _clear_zone_cache()
            messages.success(request, f'Zone "{name}" updated.')
            return redirect('qms:zone_manage')

    return render(request, 'qms/zone_form.html', {
        'form_title': f'Edit Zone — {zone.name}',
        'zone': zone,
        'color_choices': _ZONE_COLOR_CHOICES,
        'error': error,
    })
