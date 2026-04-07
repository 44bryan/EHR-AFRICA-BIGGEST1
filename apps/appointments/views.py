from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Q, Count
from .models import Appointment
from .forms import AppointmentForm
from apps.patients.models import Patient


@login_required
def appointment_list_view(request):
    today = timezone.localdate()
    appointments = Appointment.objects.select_related(
        'patient', 'department', 'doctor'
    ).filter(is_deleted=False)

    date_filter = request.GET.get('date', str(today))
    dept_filter = request.GET.get('department', '')
    status_filter = request.GET.get('status', '')

    if date_filter:
        appointments = appointments.filter(appointment_date=date_filter)
    if dept_filter:
        appointments = appointments.filter(department_id=dept_filter)
    if status_filter:
        appointments = appointments.filter(status=status_filter)

    from apps.departments.models import Department
    return render(request, 'appointments/list.html', {
        'appointments': appointments,
        'departments': Department.objects.filter(is_active=True),
        'status_choices': Appointment.Status.choices,
        'date_filter': date_filter,
        'dept_filter': dept_filter,
        'status_filter': status_filter,
        'today': today,
    })


@login_required
def appointment_book_view(request):
    patient_id = request.GET.get('patient')
    patient = None
    if patient_id:
        patient = get_object_or_404(Patient, patient_id=patient_id)

    if request.method == 'POST':
        form = AppointmentForm(request.POST)
        if form.is_valid():
            appt = form.save(commit=False)
            appt.booked_by = request.user
            appt.created_by = request.user
            appt.save()
            messages.success(request, f'Appointment booked: {appt.appointment_number}')
            return redirect('appointments:detail', pk=appt.pk)
    else:
        initial = {}
        if patient:
            initial['patient'] = patient
        form = AppointmentForm(initial=initial)

    return render(request, 'appointments/book.html', {
        'form': form,
        'patient': patient,
    })


@login_required
def appointment_detail_view(request, pk):
    appt = get_object_or_404(Appointment, pk=pk, is_deleted=False)
    return render(request, 'appointments/detail.html', {'appointment': appt})


@login_required
def appointment_check_in_view(request, pk):
    appt = get_object_or_404(Appointment, pk=pk)
    appt.status = Appointment.Status.CHECKED_IN
    appt.save(update_fields=['status'])
    # Create a visit for this appointment
    from apps.patients.models import Visit
    visit, created = Visit.objects.get_or_create(
        appointment=appt,
        defaults={
            'patient': appt.patient,
            'department': appt.department,
            'visit_type': 'FOLLOW_UP' if appt.appointment_type == 'FOLLOW_UP' else 'NEW',
            'chief_complaint': appt.reason,
            'created_by': request.user,
        }
    )
    messages.success(request, f'Patient checked in. Visit: {visit.visit_number}')
    return redirect('patients:detail', patient_id=appt.patient.patient_id)


@login_required
def appointment_cancel_view(request, pk):
    appt = get_object_or_404(Appointment, pk=pk)
    if request.method == 'POST':
        appt.status = Appointment.Status.CANCELLED
        appt.cancellation_reason = request.POST.get('reason', '')
        appt.save(update_fields=['status', 'cancellation_reason'])
        messages.success(request, 'Appointment cancelled.')
        return redirect('appointments:list')
    return render(request, 'appointments/cancel.html', {'appointment': appt})


@login_required
def clinic_board_view(request):
    """Today's clinic board — all booked appointments grouped by department with live status."""
    today = timezone.localdate()
    from apps.departments.models import Department

    dept_filter = request.GET.get('dept', '')
    appts = Appointment.objects.filter(
        appointment_date=today, is_deleted=False
    ).select_related('patient', 'department', 'doctor').order_by('appointment_time')

    if dept_filter:
        appts = appts.filter(department_id=dept_filter)

    # Stats
    stats = {
        'total': appts.count(),
        'scheduled': appts.filter(status__in=[Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED]).count(),
        'checked_in': appts.filter(status=Appointment.Status.CHECKED_IN).count(),
        'completed': appts.filter(status=Appointment.Status.COMPLETED).count(),
        'no_show': appts.filter(status=Appointment.Status.NO_SHOW).count(),
    }

    # Group by department
    dept_groups = {}
    for appt in appts:
        dept_name = str(appt.department) if appt.department else 'Unassigned'
        dept_groups.setdefault(dept_name, []).append(appt)

    departments = Department.objects.filter(is_active=True)

    return render(request, 'appointments/clinic_board.html', {
        'dept_groups': dept_groups,
        'stats': stats,
        'today': today,
        'departments': departments,
        'dept_filter': dept_filter,
        'status_choices': Appointment.Status.choices,
    })


@login_required
@require_POST
def update_status_view(request, pk):
    """Quick status update from clinic board."""
    appt = get_object_or_404(Appointment, pk=pk, is_deleted=False)
    new_status = request.POST.get('status')
    valid = [s[0] for s in Appointment.Status.choices]
    if new_status not in valid:
        return JsonResponse({'error': 'Invalid status'}, status=400)

    appt.status = new_status
    if new_status == Appointment.Status.CHECKED_IN:
        appt.save(update_fields=['status'])
        # Auto-create a patient visit on check-in
        from apps.patients.models import Visit
        Visit.objects.get_or_create(
            appointment=appt,
            defaults={
                'patient': appt.patient,
                'department': appt.department,
                'visit_type': 'FOLLOW_UP' if appt.appointment_type == 'FOLLOW_UP' else 'NEW',
                'chief_complaint': appt.reason,
                'created_by': request.user,
            }
        )
    else:
        appt.save(update_fields=['status'])

    return JsonResponse({'status': appt.status, 'display': appt.get_status_display()})


@login_required
def reschedule_view(request, pk):
    appt = get_object_or_404(Appointment, pk=pk, is_deleted=False)
    if request.method == 'POST':
        new_date = request.POST.get('appointment_date')
        new_time = request.POST.get('appointment_time')
        if new_date and new_time:
            appt.appointment_date = new_date
            appt.appointment_time = new_time
            appt.status = Appointment.Status.SCHEDULED
            appt.save(update_fields=['appointment_date', 'appointment_time', 'status'])
            messages.success(request, f'Appointment rescheduled to {new_date} at {new_time}.')
        return redirect('appointments:detail', pk=appt.pk)
    return render(request, 'appointments/reschedule.html', {'appointment': appt})


# ─────────────────────────────────────────────────────────────────────────────
# Doctor Schedule Management
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def schedule_list_view(request):
    """List all doctor schedules. Admin / Medical Director can manage; others read-only."""
    from .models import DoctorSchedule
    from apps.accounts.models import User
    from apps.departments.models import Department

    doctor_filter = request.GET.get('doctor', '')
    dept_filter = request.GET.get('dept', '')

    schedules = DoctorSchedule.objects.select_related('doctor', 'department').filter(is_active=True)
    if doctor_filter:
        schedules = schedules.filter(doctor_id=doctor_filter)
    if dept_filter:
        schedules = schedules.filter(department_id=dept_filter)
    schedules = schedules.order_by('doctor__last_name', 'day_of_week')

    doctors = User.objects.filter(is_active=True).filter(
        role__in=['medical_director','ophthalmologist','retina_specialist','glaucoma_specialist',
                  'pediatric_ophthalmologist','cataract_surgeon','cornea_specialist',
                  'oculoplastics_surgeon','neuro_ophthalmologist','uveitis_specialist',
                  'optometrist','express_ophthalmologist','insurance_ophthalmologist',
                  'intern','pediatric_refractionist']
    ).order_by('last_name')

    return render(request, 'appointments/schedule_list.html', {
        'schedules': schedules,
        'doctors': doctors,
        'departments': Department.objects.filter(is_active=True),
        'doctor_filter': doctor_filter,
        'dept_filter': dept_filter,
        'weekdays': DoctorSchedule.WEEKDAY_CHOICES,
        'can_edit': request.user.is_super_admin or request.user.is_medical_director,
    })


@login_required
def schedule_create_view(request):
    """Create a new doctor schedule slot."""
    if not (request.user.is_super_admin or request.user.is_medical_director):
        messages.error(request, 'Only the Medical Director can manage doctor schedules.')
        return redirect('appointments:schedule_list')

    from .models import DoctorSchedule
    from apps.accounts.models import User
    from apps.departments.models import Department

    if request.method == 'POST':
        p = request.POST
        try:
            doctor = User.objects.get(pk=p.get('doctor'))
            department = Department.objects.get(pk=p.get('department'))
            sched, created = DoctorSchedule.objects.get_or_create(
                doctor=doctor,
                department=department,
                day_of_week=int(p.get('day_of_week', 0)),
                defaults={
                    'start_time': p.get('start_time', '08:00'),
                    'end_time': p.get('end_time', '17:00'),
                    'slot_duration_minutes': int(p.get('slot_duration_minutes', 30)),
                    'max_patients': int(p.get('max_patients', 20)),
                    'is_active': True,
                }
            )
            if not created:
                sched.start_time = p.get('start_time', sched.start_time)
                sched.end_time = p.get('end_time', sched.end_time)
                sched.slot_duration_minutes = int(p.get('slot_duration_minutes', sched.slot_duration_minutes))
                sched.max_patients = int(p.get('max_patients', sched.max_patients))
                sched.is_active = True
                sched.save()
                messages.success(request, f'Schedule updated for {doctor.full_name}.')
            else:
                messages.success(request, f'Schedule created for {doctor.full_name}.')
        except (User.DoesNotExist, Department.DoesNotExist, ValueError) as e:
            messages.error(request, f'Error: {e}')
        return redirect('appointments:schedule_list')

    doctors = User.objects.filter(is_active=True).filter(
        role__in=['medical_director','ophthalmologist','retina_specialist','glaucoma_specialist',
                  'pediatric_ophthalmologist','cataract_surgeon','cornea_specialist',
                  'oculoplastics_surgeon','neuro_ophthalmologist','uveitis_specialist',
                  'optometrist','express_ophthalmologist','insurance_ophthalmologist',
                  'intern','pediatric_refractionist']
    ).order_by('last_name')

    return render(request, 'appointments/schedule_form.html', {
        'doctors': doctors,
        'departments': Department.objects.filter(is_active=True),
        'weekdays': DoctorSchedule.WEEKDAY_CHOICES,
    })


@login_required
def schedule_delete_view(request, pk):
    """Deactivate (soft-delete) a schedule slot."""
    if not (request.user.is_super_admin or request.user.is_medical_director):
        messages.error(request, 'Permission denied.')
        return redirect('appointments:schedule_list')
    from .models import DoctorSchedule
    sched = get_object_or_404(DoctorSchedule, pk=pk)
    sched.is_active = False
    sched.save(update_fields=['is_active'])
    messages.success(request, 'Schedule slot removed.')
    return redirect('appointments:schedule_list')
