"""
Reception Desk — unified front-desk workflow.
Gate issues QMS token → Reception searches/registers patient →
Selects consultation tier (Standard/Express/Fast Track/VIP) →
Appointment + Visit auto-created → Patient directed to department.
"""
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q, Count
from django.utils import timezone
from django.http import JsonResponse

from apps.patients.models import Patient, Visit, MedicalHistory
from apps.appointments.models import Appointment
from apps.departments.models import Department
from apps.core.context_processors import qms_active
# QMS models are imported lazily inside functions so this file
# works correctly when QMS is toggled off (module_qms = False).


# ── Tier meta: colour, icon, QMS priority ────────────────────────────────────
TIER_META = {
    'STANDARD':   {'color': 'secondary', 'icon': 'bi-person',         'priority': 0},
    'EXPRESS':    {'color': 'info',      'icon': 'bi-lightning',       'priority': 1},
    'FAST_TRACK': {'color': 'warning',   'icon': 'bi-lightning-charge','priority': 1},
    'VIP':        {'color': 'danger',    'icon': 'bi-star-fill',       'priority': 2},
}


@login_required
def desk(request):
    """Main reception dashboard — today's queue and quick actions."""
    today = timezone.localdate()

    # Today's appointments
    appointments = Appointment.objects.filter(
        appointment_date=today, is_deleted=False
    ).select_related('patient', 'department').order_by('appointment_time')

    stats = {
        'total': appointments.count(),
        'waiting': appointments.filter(status__in=[
            Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED
        ]).count(),
        'checked_in': appointments.filter(status=Appointment.Status.CHECKED_IN).count(),
        'completed': appointments.filter(status=Appointment.Status.COMPLETED).count(),
    }

    # Active QMS queue — only populated when QMS module is on
    queue = []
    if qms_active():
        from apps.qms.models import QueueToken, TokenStatus
        queue = QueueToken.objects.filter(
            issued_at__date=today,
            is_deleted=False,
        ).exclude(
            status__in=[TokenStatus.COMPLETED, TokenStatus.CANCELLED]
        ).order_by('-priority', 'issued_at').select_related('patient')[:30]

    return render(request, 'reception/desk.html', {
        'appointments': appointments,
        'stats': stats,
        'queue': queue,
        'qms_active': qms_active(),
        'today': today,
        'tier_meta': TIER_META,
    })


@login_required
def walk_in(request):
    """
    Unified walk-in flow:
    1. Search for existing patient OR register new one
    2. Select department + service tier
    3. One click → QMS token + Appointment + Visit created
    4. Confirmation screen with token slip
    """
    departments = Department.objects.filter(is_active=True).order_by('name')
    tier_choices = Appointment.ServiceTier.choices
    today = timezone.localdate()
    now = timezone.localtime()

    # ── Step 1: patient search ─────────────────────────────────────────────
    if request.method == 'GET':
        q = request.GET.get('q', '').strip()
        patient_id = request.GET.get('patient', '')
        patients = []
        selected_patient = None

        if patient_id:
            selected_patient = get_object_or_404(Patient, patient_id=patient_id, is_active=True)

        elif q:
            from apps.core.utils import patient_search_q
            patients = Patient.objects.filter(
                is_active=True
            ).filter(patient_search_q(q)).order_by('last_name')[:20]

        # Check if selected patient has an active consultation (no payment needed)
        active_consult_visit = None
        if selected_patient:
            active_consult_visit = selected_patient.active_consultation_visit

        return render(request, 'reception/walk_in.html', {
            'q': q,
            'patients': patients,
            'selected_patient': selected_patient,
            'departments': departments,
            'tier_choices': tier_choices,
            'tier_meta': TIER_META,
            'today': today,
            'active_consult_visit': active_consult_visit,
        })

    # ── Step 2: process walk-in ────────────────────────────────────────────
    action = request.POST.get('action', '')

    if action == 'checkin':
        patient_id = request.POST.get('patient_id')
        patient = get_object_or_404(Patient, patient_id=patient_id)

        dept_id = request.POST.get('department')
        tier = request.POST.get('service_tier', 'STANDARD')
        chief_complaint = request.POST.get('chief_complaint', 'Walk-in consultation')
        appt_type = request.POST.get('appointment_type', 'NEW')

        department = get_object_or_404(Department, pk=dept_id) if dept_id else None

        # ── 15-day consultation validity check ────────────────────────────────
        active_visit = patient.active_consultation_visit  # None if expired / never paid
        consultation_valid = active_visit is not None

        if consultation_valid:
            messages.success(
                request,
                f"Walk-in check-in — consultation valid until "
                f"{active_visit.consultation_valid_until.strftime('%d %b %Y')}. "
                f"Patient directed to {department.name if department else 'department'} (no payment required)."
            )
        else:
            messages.warning(
                request,
                "No active consultation found. Patient directed to cashier for payment."
            )

        # QMS priority from tier
        priority = TIER_META.get(tier, {}).get('priority', 0)

        # Issue QMS token (only when QMS module is active)
        token = None
        if qms_active():
            from apps.qms.models import ServiceType, QueueToken, DailyTokenSequence
            dept_code = department.code if department else 'GEN_OPH'
            if consultation_valid:
                service_map = {
                    'LAB': ServiceType.LABORATORY,
                    'INVEST': ServiceType.INVESTIGATION,
                    'REFRAC': ServiceType.OPTICAL,
                }
                service_type = service_map.get(dept_code, ServiceType.GENERAL)
            else:
                service_type = ServiceType.CASHIER
            token_number = DailyTokenSequence.next_token(service_type)
            token = QueueToken.objects.create(
                token_number=token_number,
                patient=patient,
                patient_name=patient.full_name,
                service_type=service_type,
                priority=priority,
                issued_by=request.user,
            )

        # Create appointment (CHECKED_IN immediately since patient is here)
        appt = Appointment.objects.create(
            patient=patient,
            department=department,
            appointment_date=today,
            appointment_time=now.time(),
            appointment_type=appt_type,
            service_tier=tier,
            reason=chief_complaint,
            status=Appointment.Status.CHECKED_IN,
            booked_by=request.user,
            created_by=request.user,
        )

        # Correct OPD flow:
        #   New / expired consultation → AT_CASHIER (pays first, then goes to triage)
        #   Follow-up within 15 days  → PARAMETERS  (skip cashier, go straight to triage)
        # In BOTH cases triage records vitals before the doctor sees the patient.
        initial_visit_status = 'PARAMETERS' if consultation_valid else 'AT_CASHIER'
        visit = Visit.objects.create(
            patient=patient,
            department=department,
            appointment=appt,
            visit_type=appt_type if appt_type in ['NEW', 'FOLLOW_UP', 'EMERGENCY', 'REVIEW', 'PROCEDURE'] else 'NEW',
            chief_complaint=chief_complaint,
            status=initial_visit_status,
            created_by=request.user,
        )

        if token:
            return redirect('reception:confirmation', token_pk=token.pk)
        # QMS off — redirect to patient detail
        if consultation_valid:
            messages.success(request, "Patient checked in. Direct them to Triage/Parameters for vitals.")
        else:
            messages.warning(request, "Patient checked in. Direct them to the Cashier first, then Triage.")
        return redirect('patients:detail', patient_id=patient.patient_id)

    # action == 'register_new' → redirect to patient registration with return_url
    return redirect('patients:register')


@login_required
def confirmation(request, token_pk):
    """Show confirmation screen with token slip after successful walk-in."""
    from apps.qms.models import QueueToken
    token = get_object_or_404(QueueToken, pk=token_pk)
    # Get the visit created in this session
    visit = None
    appt = None
    if token.patient:
        appt = Appointment.objects.filter(
            patient=token.patient,
            appointment_date=timezone.localdate(),
            status=Appointment.Status.CHECKED_IN,
        ).order_by('-created_at').first()
        if appt and hasattr(appt, 'visit'):
            visit = appt.visit

    return render(request, 'reception/confirmation.html', {
        'token': token,
        'appt': appt,
        'visit': visit,
        'tier_meta': TIER_META,
    })


@login_required
def quick_checkin(request, pk):
    """
    Check in an existing appointment from the reception desk.

    Consultation validity rule (15-day window):
    - If patient has an active, paid consultation within 15 days → follow-up,
      issue DEPARTMENT token directly (no cashier stop).
    - If consultation has expired or this is a new episode → route through
      CASHIER first so payment is collected.
    """
    from apps.billing.models import ServiceType as BillingServiceType
    appt = get_object_or_404(Appointment, pk=pk, is_deleted=False)
    patient = appt.patient
    tier = appt.service_tier
    priority = TIER_META.get(tier, {}).get('priority', 0)

    # ── Check 15-day consultation validity ───────────────────────────────────
    active_visit = patient.active_consultation_visit  # None if expired / never paid
    consultation_valid = active_visit is not None

    if consultation_valid:
        visit_type   = 'FOLLOW_UP'
        visit_status = 'WAITING'
        messages.success(
            request,
            f"Follow-up check-in — consultation valid until "
            f"{active_visit.consultation_valid_until.strftime('%d %b %Y')}. "
            f"Patient directed to {appt.department.name if appt.department else 'department'}."
        )
    else:
        visit_type   = 'FOLLOW_UP' if appt.appointment_type == 'FOLLOW_UP' else 'NEW'
        visit_status = 'WAITING'
        messages.warning(
            request,
            "Consultation period has expired. Patient directed to cashier for payment."
        )

    # Issue QMS token (only when QMS module is active)
    token = None
    if qms_active():
        from apps.qms.models import ServiceType, QueueToken, DailyTokenSequence
        service_type = ServiceType.GENERAL if consultation_valid else ServiceType.CASHIER
        token_number = DailyTokenSequence.next_token(service_type)
        token = QueueToken.objects.create(
            token_number=token_number,
            patient=patient,
            patient_name=patient.full_name,
            service_type=service_type,
            priority=priority,
            issued_by=request.user,
        )

    appt.status = Appointment.Status.CHECKED_IN
    appt.save(update_fields=['status'])

    # Auto-create visit
    Visit.objects.get_or_create(
        appointment=appt,
        defaults={
            'patient': patient,
            'department': appt.department,
            'visit_type': visit_type,
            'chief_complaint': appt.reason,
            'status': visit_status,
            'created_by': request.user,
        }
    )

    if token:
        return redirect('reception:confirmation', token_pk=token.pk)
    messages.success(request, f"Patient checked in successfully.")
    return redirect('patients:detail', patient_id=patient.patient_id)
