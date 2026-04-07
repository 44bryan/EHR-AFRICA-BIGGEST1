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
from apps.qms.models import QueueToken, DailyTokenSequence, ServiceType, TokenStatus


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

    # Active QMS queue
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
            patients = Patient.objects.filter(
                is_active=True
            ).filter(
                Q(patient_id__icontains=q) |
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q) |
                Q(phone_number__icontains=q)
            ).order_by('last_name')[:20]

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

        # Determine QMS service type from department code
        dept_code = department.code if department else 'GEN_OPH'
        service_map = {
            'LAB': ServiceType.LABORATORY,
            'INVEST': ServiceType.INVESTIGATION,
            'REFRAC': ServiceType.OPTICAL,
        }
        service_type = service_map.get(dept_code, ServiceType.GENERAL)

        # QMS priority from tier
        priority = TIER_META.get(tier, {}).get('priority', 0)

        # Issue QMS token
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

        # Auto-create visit
        visit = Visit.objects.create(
            patient=patient,
            department=department,
            appointment=appt,
            visit_type=appt_type if appt_type in ['NEW', 'FOLLOW_UP', 'EMERGENCY', 'REVIEW', 'PROCEDURE'] else 'NEW',
            chief_complaint=chief_complaint,
            status='WAITING',
            created_by=request.user,
        )

        return redirect('reception:confirmation', token_pk=token.pk)

    # action == 'register_new' → redirect to patient registration with return_url
    return redirect('patients:register')


@login_required
def confirmation(request, token_pk):
    """Show confirmation screen with token slip after successful walk-in."""
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
    """Check in an existing appointment from the reception desk."""
    appt = get_object_or_404(Appointment, pk=pk, is_deleted=False)
    tier = appt.service_tier
    priority = TIER_META.get(tier, {}).get('priority', 0)

    # Issue QMS token
    service_type = ServiceType.GENERAL
    token_number = DailyTokenSequence.next_token(service_type)
    token = QueueToken.objects.create(
        token_number=token_number,
        patient=appt.patient,
        patient_name=appt.patient.full_name,
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
            'patient': appt.patient,
            'department': appt.department,
            'visit_type': 'FOLLOW_UP' if appt.appointment_type == 'FOLLOW_UP' else 'NEW',
            'chief_complaint': appt.reason,
            'status': 'WAITING',
            'created_by': request.user,
        }
    )

    return redirect('reception:confirmation', token_pk=token.pk)
