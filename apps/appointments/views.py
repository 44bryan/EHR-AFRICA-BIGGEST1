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
from apps.core.context_processors import qms_active as _qms_active


@login_required
def appointment_list_view(request):
    today = timezone.localdate()
    user = request.user
    appointments = Appointment.objects.select_related(
        'patient', 'department', 'doctor'
    ).filter(is_deleted=False)

    # Doctors only see their own appointments; admin/oversight roles see all
    _oversight = ('medical_director', 'super_admin', 'ceo', 'admin_director', 'receptionist', 'medical_records')
    if user.is_doctor and user.role not in _oversight:
        appointments = appointments.filter(doctor=user)

    # Tier isolation for non-supervisors: nurses/cashiers only see their tier's appointments
    _is_appt_supervisor = user.role in _oversight or user.is_nurse_director
    _appt_tier = (getattr(user, 'patient_tier', '') or '').strip()
    if not _is_appt_supervisor and not user.is_doctor and _appt_tier and _appt_tier not in ('ALL', ''):
        appointments = appointments.filter(service_tier=_appt_tier)

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

    # Today's stats — scoped to doctor if applicable
    today_qs = Appointment.objects.filter(appointment_date=today, is_deleted=False)
    if user.is_doctor and user.role not in _oversight:
        today_qs = today_qs.filter(doctor=user)
    today_stats = {
        'total':     today_qs.count(),
        'scheduled': today_qs.filter(status='SCHEDULED').count(),
        'confirmed': today_qs.filter(status='CONFIRMED').count(),
        'checked_in':today_qs.filter(status='CHECKED_IN').count(),
        'completed': today_qs.filter(status='COMPLETED').count(),
        'no_show':   today_qs.filter(status='NO_SHOW').count(),
        'cancelled': today_qs.filter(status='CANCELLED').count(),
    }

    return render(request, 'appointments/list.html', {
        'appointments': appointments,
        'departments': Department.objects.filter(is_active=True),
        'status_choices': Appointment.Status.choices,
        'date_filter': date_filter,
        'dept_filter': dept_filter,
        'status_filter': status_filter,
        'today': today,
        'today_stats': today_stats,
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
            appt_date = form.cleaned_data.get('appointment_date')
            doctor    = form.cleaned_data.get('doctor')

            # ── Slot availability check ───────────────────────────────────────
            slot_error = None
            if doctor and appt_date:
                from .models import DoctorSchedule
                day_of_week = appt_date.weekday()  # 0=Monday … 6=Sunday
                schedule = DoctorSchedule.objects.filter(
                    doctor=doctor, day_of_week=day_of_week, is_active=True
                ).first()
                if schedule:
                    booked = Appointment.objects.filter(
                        doctor=doctor,
                        appointment_date=appt_date,
                        is_deleted=False,
                    ).exclude(
                        status__in=[Appointment.Status.CANCELLED, Appointment.Status.NO_SHOW]
                    ).count()
                    if booked >= schedule.max_patients:
                        # Find next available day for this doctor
                        from datetime import timedelta
                        next_slot_msg = ''
                        for delta in range(1, 14):
                            check_date = appt_date + timedelta(days=delta)
                            check_day  = check_date.weekday()
                            next_sched = DoctorSchedule.objects.filter(
                                doctor=doctor, day_of_week=check_day, is_active=True
                            ).first()
                            if next_sched:
                                next_booked = Appointment.objects.filter(
                                    doctor=doctor,
                                    appointment_date=check_date,
                                    is_deleted=False,
                                ).exclude(
                                    status__in=[Appointment.Status.CANCELLED, Appointment.Status.NO_SHOW]
                                ).count()
                                if next_booked < next_sched.max_patients:
                                    remaining = next_sched.max_patients - next_booked
                                    next_slot_msg = (
                                        f' Next available: {check_date.strftime("%A %d %b")} '
                                        f'({remaining} slot{"s" if remaining != 1 else ""} remaining).'
                                    )
                                    break
                        slot_error = (
                            f"{doctor.full_name}'s clinic on "
                            f"{appt_date.strftime('%A %d %b')} is full "
                            f"({booked}/{schedule.max_patients} slots taken).{next_slot_msg}"
                        )

            if slot_error:
                form.add_error('appointment_date', slot_error)
            else:
                appt = form.save(commit=False)
                appt.booked_by = request.user
                appt.created_by = request.user
                if not appt.service_tier:
                    appt.service_tier = 'STANDARD'
                appt.save()
                # ── Audit log ─────────────────────────────────────────────────
                try:
                    from apps.accounts.models import UserAuditLog
                    UserAuditLog.log(
                        user=request.user,
                        action=UserAuditLog.Action.CREATE_RECORD,
                        target_model='Appointment',
                        target_id=str(appt.pk),
                        extra_data={
                            'appointment_number': appt.appointment_number,
                            'patient': appt.patient.full_name,
                            'patient_id': appt.patient.patient_id,
                            'doctor': doctor.full_name if doctor else '—',
                            'date': str(appt_date),
                            'department': str(appt.department) if appt.department else '—',
                        },
                        request=request,
                    )
                except Exception:
                    pass
                messages.success(request, f'Appointment booked: {appt.appointment_number}')
                return redirect('appointments:detail', pk=appt.pk)
    else:
        initial = {}
        if patient:
            initial['patient'] = patient
        # Pre-fill reason when coming from a consultation referral
        ref_pk = request.GET.get('ref')
        if ref_pk:
            try:
                from apps.consultations.models import Consultation
                ref_consult = Consultation.objects.get(pk=ref_pk)
                initial['reason'] = (
                    f"Referred by Dr. {ref_consult.consulting_doctor.full_name} "
                    f"on {ref_consult.consultation_date.strftime('%d %b %Y')}."
                )
            except Exception:
                pass
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
    from apps.patients.models import Visit

    appt = get_object_or_404(Appointment, pk=pk)
    patient = appt.patient

    appt.status = Appointment.Status.CHECKED_IN
    appt.save(update_fields=['status'])

    # ── 15-day consultation validity check ────────────────────────────────────
    active_visit = patient.active_consultation_visit  # None if expired / never paid
    consultation_valid = active_visit is not None

    if consultation_valid:
        visit_type = 'FOLLOW_UP'
        messages.success(
            request,
            f"Checked in — consultation valid until "
            f"{active_visit.consultation_valid_until.strftime('%d %b %Y')}. "
            f"Patient directed to {appt.department.name if appt.department else 'department'} (no payment required)."
        )
    else:
        visit_type = 'FOLLOW_UP' if appt.appointment_type == 'FOLLOW_UP' else 'NEW'
        messages.warning(
            request,
            "Consultation period has expired or no prior payment found. Patient directed to cashier."
        )

    # ── Determine correct Visit status based on appointment department ──────────
    # Specialist-unit returning patients bypass general triage and go straight
    # to their unit nurse queue (AT_GLAUCOMA, AT_RETINA, etc.).
    # Generalist / unrecognised departments → WAITING (normal triage dispatch).
    _SPECIALIST_UNIT_STATUS = {
        'GLAUC':       'AT_GLAUCOMA',
        'RETINA':      'AT_RETINA',
        'PEDS_OPH':    'AT_PEDIATRIC',
        'CORNEA':      'AT_CORNEA',
        'OCULOPLASTY': 'AT_OCULOPLASTY',
        'NEURO_OPH':   'AT_NEURO',
        'UVEITIS':     'UVEITIS',
        'CATARACT':    'AT_CATARACT',
    }
    dept_code = appt.department.code if appt.department else None
    unit_status = _SPECIALIST_UNIT_STATUS.get(dept_code) if dept_code else None
    if consultation_valid and unit_status:
        initial_visit_status = unit_status   # → goes directly to unit nurse queue
    elif consultation_valid:
        initial_visit_status = 'WAITING'     # → generalist triage dispatch
    else:
        initial_visit_status = 'AT_CASHIER'  # → pay first

    # Create visit
    visit, created = Visit.objects.get_or_create(
        appointment=appt,
        defaults={
            'patient': patient,
            'department': appt.department,
            'visit_type': visit_type,
            'chief_complaint': appt.reason,
            'status': initial_visit_status,
            'service_tier': appt.service_tier or 'STANDARD',
            'created_by': request.user,
        }
    )

    if _qms_active():
        try:
            from apps.qms.models import QueueToken, DailyTokenSequence, ServiceType
            tier = appt.service_tier or 'STANDARD'
            TIER_PRIORITY = {'STANDARD': 0, 'EXPRESS': 1, 'VIP': 2}

            # ── Tier-aware QMS routing ─────────────────────────────────────────
            _unit_to_qms = {
                'AT_GLAUCOMA':    'GLAUCOMA',  'AT_RETINA':      'RETINA',
                'AT_PEDIATRIC':   'PEDIATRIC', 'AT_CORNEA':      'CORNEA',
                'AT_OCULOPLASTY': 'OCULOPLASTY','AT_NEURO':      'NEURO',
                'UVEITIS':        'UVEITIS',   'AT_CATARACT':    'CATARACT',
            }
            if not consultation_valid:
                service_type = ServiceType.CASHIER
            elif unit_status:
                # Specialist appointment → bypass triage → unit nurse queue
                service_type = _unit_to_qms.get(unit_status, 'GENERAL')
            elif tier == 'EXPRESS':
                service_type = 'EXP_CONSULT'
            elif tier == 'VIP':
                service_type = 'VIP_CONSULT'
            else:
                service_type = ServiceType.GENERAL  # STANDARD → general doctor queue

            token_number = DailyTokenSequence.next_token(service_type)
            _assigned_doc = appt.doctor if tier == 'VIP' and appt.doctor else None
            token = QueueToken.objects.create(
                token_number=token_number,
                patient=patient,
                patient_name=patient.full_name,
                service_type=service_type,
                service_tier=tier,
                priority=TIER_PRIORITY.get(tier, 0),
                issued_by=request.user,
                assigned_doctor=_assigned_doc,
                visit=visit,
            )
            messages.success(request, f'Patient checked in. Token: {token.token_number} | Visit: {visit.visit_number}')
            return redirect('reception:confirmation', token_pk=token.pk)
        except Exception:
            pass

    messages.success(request, f'Patient {patient.full_name} checked in. Visit: {visit.visit_number}')
    return redirect('patients:detail', patient_id=patient.patient_id)


@login_required
def appointment_cancel_view(request, pk):
    appt = get_object_or_404(Appointment, pk=pk)
    if request.method == 'POST':
        appt.status = Appointment.Status.CANCELLED
        appt.cancellation_reason = request.POST.get('reason', '')
        appt.save(update_fields=['status', 'cancellation_reason'])
        try:
            from apps.accounts.models import UserAuditLog
            UserAuditLog.log(
                user=request.user,
                action=UserAuditLog.Action.DELETE_RECORD,
                target_model='Appointment',
                target_id=str(appt.pk),
                extra_data={
                    'appointment_number': appt.appointment_number,
                    'patient': appt.patient.full_name,
                    'patient_id': appt.patient.patient_id,
                    'reason': appt.cancellation_reason,
                    'date': str(appt.appointment_date),
                },
                request=request,
            )
        except Exception:
            pass
        messages.success(request, 'Appointment cancelled.')
        return redirect('appointments:list')
    return render(request, 'appointments/cancel.html', {'appointment': appt})


@login_required
def clinic_board_view(request):
    """Today's clinic board — all booked appointments grouped by department with live status."""
    today = timezone.localdate()
    user = request.user
    from apps.departments.models import Department

    dept_filter = request.GET.get('dept', '')
    appts = Appointment.objects.filter(
        appointment_date=today, is_deleted=False
    ).select_related('patient', 'department', 'doctor').order_by('appointment_time')

    # Specialists auto-scoped to their own department (can override via ?dept=)
    _oversight = ('medical_director', 'super_admin', 'ceo', 'admin_director', 'receptionist')
    if user.is_doctor and user.role not in _oversight and not dept_filter:
        if user.department:
            appts = appts.filter(department=user.department)
        else:
            # General ophthalmologist with no dept assigned — filter to their own appointments
            appts = appts.filter(doctor=user)

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
def appointment_no_show_view(request, pk):
    """Mark appointment as No Show — AJAX endpoint used from receptionist dashboard."""
    from django.http import JsonResponse
    appt = get_object_or_404(Appointment, pk=pk)
    appt.status = Appointment.Status.NO_SHOW
    appt.save(update_fields=['status'])
    try:
        from apps.accounts.models import UserAuditLog
        UserAuditLog.log(
            user=request.user,
            action=UserAuditLog.Action.UPDATE_RECORD,
            target_model='Appointment',
            target_id=str(appt.pk),
            extra_data={'patient': appt.patient.full_name, 'status': 'NO_SHOW'},
            request=request,
        )
    except Exception:
        pass
    return JsonResponse({'success': True})


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
        # Auto-create a patient visit with correct unit routing (same logic as
        # appointment_check_in_view so specialist patients go to unit nurse queue)
        from apps.patients.models import Visit
        patient = appt.patient
        active_visit = patient.active_consultation_visit
        consultation_valid = active_visit is not None

        _SPECIALIST_UNIT_STATUS = {
            'GLAUC':       'AT_GLAUCOMA',
            'RETINA':      'AT_RETINA',
            'PEDS_OPH':    'AT_PEDIATRIC',
            'CORNEA':      'AT_CORNEA',
            'OCULOPLASTY': 'AT_OCULOPLASTY',
            'NEURO_OPH':   'AT_NEURO',
            'UVEITIS':     'UVEITIS',
            'CATARACT':    'AT_CATARACT',
        }
        dept_code = appt.department.code if appt.department else None
        unit_status = _SPECIALIST_UNIT_STATUS.get(dept_code) if dept_code else None

        if consultation_valid and unit_status:
            initial_status = unit_status
        elif consultation_valid:
            initial_status = 'WAITING'
        else:
            initial_status = 'AT_CASHIER'

        Visit.objects.get_or_create(
            appointment=appt,
            defaults={
                'patient': patient,
                'department': appt.department,
                'visit_type': 'FOLLOW_UP' if appt.appointment_type == 'FOLLOW_UP' else 'NEW',
                'chief_complaint': appt.reason,
                'status': initial_status,
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
            old_date = str(appt.appointment_date)
            old_time = str(appt.appointment_time)
            appt.appointment_date = new_date
            appt.appointment_time = new_time
            appt.status = Appointment.Status.SCHEDULED
            appt.save(update_fields=['appointment_date', 'appointment_time', 'status'])
            try:
                from apps.accounts.models import UserAuditLog
                UserAuditLog.log(
                    user=request.user,
                    action=UserAuditLog.Action.UPDATE_RECORD,
                    target_model='Appointment',
                    target_id=str(appt.pk),
                    extra_data={
                        'appointment_number': appt.appointment_number,
                        'patient': appt.patient.full_name,
                        'patient_id': appt.patient.patient_id,
                        'from_date': old_date,
                        'from_time': old_time,
                        'to_date': new_date,
                        'to_time': new_time,
                    },
                    request=request,
                )
            except Exception:
                pass
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
                  'optometrist','intern','pediatric_refractionist']
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
                  'optometrist','intern','pediatric_refractionist']
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
