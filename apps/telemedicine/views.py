from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count

from apps.accounts.models import UserRole, User
from apps.patients.models import Patient
from .models import TeleAppointment, TeleSessionNote, AppointmentStatus, AppointmentType


def _can_view(user):
    return user.role in [
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR, UserRole.MEDICAL_DIRECTOR,
        UserRole.CEO, UserRole.OPHTHALMOLOGIST, UserRole.RETINA_SPECIALIST,
        UserRole.GLAUCOMA_SPECIALIST, UserRole.PEDIATRIC_OPHTHALMOLOGIST,
        UserRole.PEDIATRIC_REFRACTIONIST, UserRole.CATARACT_SURGEON,
        UserRole.CORNEA_SPECIALIST, UserRole.OCULOPLASTICS_SURGEON,
        UserRole.NEURO_OPHTHALMOLOGIST, UserRole.UVEITIS_SPECIALIST,
        UserRole.OPTOMETRIST, UserRole.LOW_VISION_SPECIALIST,
        UserRole.INTERN, UserRole.GENERAL_PHYSICIAN,
        UserRole.NURSE, UserRole.WARD_NURSE, UserRole.NURSE_DIRECTOR,
        UserRole.RECEPTIONIST, UserRole.ADMISSION_OFFICER, UserRole.MEDICAL_RECORDS,
    ]


def _can_conduct(user):
    """Roles that can start/end sessions and write SOAP notes."""
    return user.role in [
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR, UserRole.MEDICAL_DIRECTOR,
        UserRole.OPHTHALMOLOGIST, UserRole.RETINA_SPECIALIST,
        UserRole.GLAUCOMA_SPECIALIST, UserRole.PEDIATRIC_OPHTHALMOLOGIST,
        UserRole.PEDIATRIC_REFRACTIONIST, UserRole.CATARACT_SURGEON,
        UserRole.CORNEA_SPECIALIST, UserRole.OCULOPLASTICS_SURGEON,
        UserRole.NEURO_OPHTHALMOLOGIST, UserRole.UVEITIS_SPECIALIST,
        UserRole.OPTOMETRIST, UserRole.LOW_VISION_SPECIALIST,
        UserRole.INTERN, UserRole.GENERAL_PHYSICIAN, UserRole.NURSE_DIRECTOR,
    ]


@login_required
def dashboard(request):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    today = timezone.localdate()
    today_appts = TeleAppointment.objects.filter(
        is_deleted=False,
        scheduled_at__date=today,
    ).select_related('patient', 'doctor').order_by('scheduled_at')

    upcoming = TeleAppointment.objects.filter(
        is_deleted=False,
        status=AppointmentStatus.SCHEDULED,
        scheduled_at__date__gt=today,
    ).select_related('patient', 'doctor').order_by('scheduled_at')[:10]

    active = TeleAppointment.objects.filter(
        is_deleted=False,
        status__in=[AppointmentStatus.WAITING, AppointmentStatus.IN_SESSION],
    ).select_related('patient', 'doctor')

    stats = {
        'today_total': today_appts.count(),
        'today_completed': today_appts.filter(status=AppointmentStatus.COMPLETED).count(),
        'active_sessions': active.count(),
        'total_completed': TeleAppointment.objects.filter(
            is_deleted=False, status=AppointmentStatus.COMPLETED
        ).count(),
    }

    context = {
        'today_appts': today_appts,
        'upcoming': upcoming,
        'active': active,
        'stats': stats,
        'can_conduct': _can_conduct(request.user),
    }
    return render(request, 'telemedicine/dashboard.html', context)


@login_required
def appointment_list(request):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    appts = TeleAppointment.objects.filter(is_deleted=False).select_related('patient', 'doctor')

    status_filter = request.GET.get('status', '')
    q = request.GET.get('q', '')
    date_filter = request.GET.get('date', '')

    if status_filter:
        appts = appts.filter(status=status_filter)
    if date_filter:
        appts = appts.filter(scheduled_at__date=date_filter)
    if q:
        appts = appts.filter(
            Q(patient__first_name__icontains=q)
            | Q(patient__last_name__icontains=q)
            | Q(patient__patient_id__icontains=q)
        )

    context = {
        'appts': appts[:100],
        'status_choices': AppointmentStatus.choices,
        'status_filter': status_filter,
        'q': q,
        'date_filter': date_filter,
        'can_conduct': _can_conduct(request.user),
    }
    return render(request, 'telemedicine/appointment_list.html', context)


@login_required
def appointment_create(request):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    patients = Patient.objects.filter(is_deleted=False).order_by('last_name', 'first_name')

    # Doctors only for selection (clinical staff who conduct sessions)
    doctors = User.objects.filter(
        is_active=True,
        role__in=[
            UserRole.OPHTHALMOLOGIST, UserRole.RETINA_SPECIALIST,
            UserRole.GLAUCOMA_SPECIALIST, UserRole.PEDIATRIC_OPHTHALMOLOGIST,
            UserRole.PEDIATRIC_REFRACTIONIST, UserRole.CATARACT_SURGEON,
            UserRole.CORNEA_SPECIALIST, UserRole.OCULOPLASTICS_SURGEON,
            UserRole.NEURO_OPHTHALMOLOGIST, UserRole.UVEITIS_SPECIALIST,
            UserRole.OPTOMETRIST, UserRole.LOW_VISION_SPECIALIST,
            UserRole.INTERN, UserRole.GENERAL_PHYSICIAN,
            UserRole.MEDICAL_DIRECTOR,
        ]
    ).order_by('last_name', 'first_name')

    if request.method == 'POST':
        patient_id = request.POST.get('patient')
        doctor_id = request.POST.get('doctor')
        scheduled_at = request.POST.get('scheduled_at')
        appt_type = request.POST.get('appointment_type', AppointmentType.FOLLOW_UP)
        duration = request.POST.get('duration_minutes', 20)
        complaint = request.POST.get('chief_complaint', '')

        patient = get_object_or_404(Patient, pk=patient_id, is_deleted=False)
        doctor = get_object_or_404(User, pk=doctor_id)

        appt = TeleAppointment(
            patient=patient,
            doctor=doctor,
            appointment_type=appt_type,
            scheduled_at=scheduled_at,
            duration_minutes=int(duration) if duration else 20,
            chief_complaint=complaint,
            created_by=request.user,
        )
        appt.save()
        messages.success(request, f'Tele-appointment scheduled for {patient.full_name}.')
        return redirect('telemedicine:appointment_detail', pk=appt.pk)

    context = {
        'patients': patients,
        'doctors': doctors,
        'type_choices': AppointmentType.choices,
    }
    return render(request, 'telemedicine/appointment_form.html', context)


@login_required
def appointment_detail(request, pk):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    appt = get_object_or_404(TeleAppointment, pk=pk, is_deleted=False)
    note = getattr(appt, 'session_note', None)

    context = {
        'appt': appt,
        'note': note,
        'can_conduct': _can_conduct(request.user),
        'join_link': request.build_absolute_uri(
            f"/telemedicine/join/{appt.session_room_id}/{appt.patient_join_token}/"
        ),
    }
    return render(request, 'telemedicine/appointment_detail.html', context)


@login_required
def session_start(request, pk):
    if not _can_conduct(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    appt = get_object_or_404(TeleAppointment, pk=pk, is_deleted=False)
    if request.method == 'POST':
        if appt.can_start:
            appt.status = AppointmentStatus.IN_SESSION
            appt.started_at = timezone.now()
            appt.updated_by = request.user
            appt.save()
        return redirect('telemedicine:session_room', pk=pk)

    return redirect('telemedicine:appointment_detail', pk=pk)


@login_required
def session_end(request, pk):
    if not _can_conduct(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    appt = get_object_or_404(TeleAppointment, pk=pk, is_deleted=False)
    if request.method == 'POST':
        if appt.status == AppointmentStatus.IN_SESSION:
            appt.status = AppointmentStatus.COMPLETED
            appt.ended_at = timezone.now()
            if appt.started_at:
                delta = appt.ended_at - appt.started_at
                appt.actual_duration_minutes = int(delta.total_seconds() // 60)
            appt.updated_by = request.user
            appt.save()
            messages.success(request, 'Session ended. Please add session notes.')
    return redirect('telemedicine:session_notes', pk=pk)


@login_required
def session_room(request, pk):
    """Full-screen video room view (doctor side)."""
    if not _can_conduct(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    appt = get_object_or_404(TeleAppointment, pk=pk, is_deleted=False)
    join_link = request.build_absolute_uri(
        f"/telemedicine/join/{appt.session_room_id}/{appt.patient_join_token}/"
    )
    return render(request, 'telemedicine/session_room.html', {'appt': appt, 'join_link': join_link})


@login_required
def session_notes(request, pk):
    if not _can_conduct(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    appt = get_object_or_404(TeleAppointment, pk=pk, is_deleted=False)
    note = getattr(appt, 'session_note', None)

    if request.method == 'POST':
        if note:
            note.subjective = request.POST.get('subjective', note.subjective)
            note.objective = request.POST.get('objective', note.objective)
            note.assessment = request.POST.get('assessment', note.assessment)
            note.plan = request.POST.get('plan', note.plan)
            note.follow_up_days = request.POST.get('follow_up_days') or None
            note.updated_by = request.user
            note.save()
        else:
            note = TeleSessionNote(
                appointment=appt,
                subjective=request.POST.get('subjective', ''),
                objective=request.POST.get('objective', ''),
                assessment=request.POST.get('assessment', ''),
                plan=request.POST.get('plan', ''),
                follow_up_days=request.POST.get('follow_up_days') or None,
                created_by=request.user,
            )
            note.save()
            # Mark appointment completed if it isn't already
            if appt.status not in (AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED):
                appt.status = AppointmentStatus.COMPLETED
                appt.ended_at = appt.ended_at or timezone.now()
                appt.updated_by = request.user
                appt.save()

        messages.success(request, 'Session notes saved.')
        return redirect('telemedicine:appointment_detail', pk=pk)

    context = {'appt': appt, 'note': note}
    return render(request, 'telemedicine/session_notes_form.html', context)


@login_required
def cancel_appointment(request, pk):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    appt = get_object_or_404(TeleAppointment, pk=pk, is_deleted=False)
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        appt.status = AppointmentStatus.CANCELLED
        appt.cancellation_reason = reason
        appt.updated_by = request.user
        appt.save()
        messages.warning(request, 'Appointment cancelled.')
        return redirect('telemedicine:appointment_list')

    return render(request, 'telemedicine/cancel_form.html', {'appt': appt})


def patient_join(request, room_id, token):
    """No-auth page for patient to join a tele-session via shared link."""
    try:
        appt = TeleAppointment.objects.get(
            session_room_id=room_id,
            is_deleted=False,
        )
    except TeleAppointment.DoesNotExist:
        return render(request, 'telemedicine/join_error.html', {
            'error': 'Appointment not found.'
        })

    # Validate token
    if token != appt.patient_join_token:
        return render(request, 'telemedicine/join_error.html', {
            'error': 'Invalid session link.'
        })

    if appt.status == AppointmentStatus.CANCELLED:
        return render(request, 'telemedicine/join_error.html', {
            'error': 'This appointment has been cancelled.'
        })

    # Mark patient as joined
    if not appt.patient_joined:
        appt.patient_joined = True
        if appt.status == AppointmentStatus.SCHEDULED:
            appt.status = AppointmentStatus.WAITING
        appt.save(update_fields=['patient_joined', 'status'])

    return render(request, 'telemedicine/patient_join.html', {'appt': appt})
