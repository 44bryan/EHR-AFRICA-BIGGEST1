import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Q
from django.views.decorators.http import require_POST

from apps.accounts.models import UserRole, User
from apps.patients.models import Patient
from .models import (
    TeleAppointment, TeleSessionNote, PreConsultationIntake,
    TelePrescription, TeleReferral,
    AppointmentStatus, AppointmentType,
)

# ── Role tiers (international standard) ──────────────────────────────────────
#
# CONDUCT  — licensed clinicians who start/end sessions & write SOAP notes
# SCHEDULE — can book/cancel appointments (doctors + front desk)
# VIEW     — read-only access: nurses (care coordination), admin oversight
#
# Excluded entirely: Anaesthetist, Orthoptist, Theatre Nurse, Counseling Nurse,
#                    Pharmacist, Lab Tech, Cashier, Finance roles

_CONDUCT_ROLES = [
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
    UserRole.NURSE_DIRECTOR,   # licensed to conduct independent consultations
]

_SCHEDULE_ROLES = _CONDUCT_ROLES + [
    UserRole.RECEPTIONIST,
    UserRole.ADMISSION_OFFICER,
]

_VIEW_ROLES = _SCHEDULE_ROLES + [
    UserRole.ADMIN_DIRECTOR,   # oversight only
    UserRole.CEO,              # oversight only
    UserRole.NURSE,            # care coordination — view schedule, no session control
    UserRole.CONSULTATION_NURSE,
    UserRole.WARD_NURSE,
    UserRole.MEDICAL_RECORDS,
]


def _can_view(user):
    return user.role in _VIEW_ROLES

def _can_schedule(user):
    return user.role in _SCHEDULE_ROLES

def _can_conduct(user):
    return user.role in _CONDUCT_ROLES


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
        'can_schedule': _can_schedule(request.user),
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
        'can_schedule': _can_schedule(request.user),
    }
    return render(request, 'telemedicine/appointment_list.html', context)


@login_required
def appointment_create(request):
    if not _can_schedule(request.user):
        messages.error(request, 'Access denied. Only clinical staff and reception can schedule appointments.')
        return redirect('dashboard:home')

    patients = Patient.objects.filter(is_deleted=False).order_by('last_name', 'first_name')

    doctors = User.objects.filter(
        is_active=True,
        role__in=_CONDUCT_ROLES,
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
    intake = getattr(appt, 'intake', None)

    context = {
        'appt': appt,
        'note': note,
        'intake': intake,
        'can_conduct': _can_conduct(request.user),
        'can_schedule': _can_schedule(request.user),
        'join_link': request.build_absolute_uri(
            f"/telemedicine/join/{appt.session_room_id}/{appt.patient_join_token}/"
        ),
    }
    return render(request, 'telemedicine/appointment_detail.html', context)


@login_required
def session_start(request, pk):
    if not _can_conduct(request.user):
        messages.error(request, 'Only licensed clinicians can start sessions.')
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
        messages.error(request, 'Only licensed clinicians can end sessions.')
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
            # Auto-create billing invoice for the teleconsultation
            _create_tele_invoice(appt, request.user)
            messages.success(request, 'Session ended. Please add session notes.')
    return redirect('telemedicine:session_notes', pk=pk)


def _create_tele_invoice(appt, user):
    """Auto-generate an invoice for a completed teleconsultation."""
    try:
        from apps.accounts.models import HospitalConfig
        from apps.billing.models import Invoice, InvoiceItem
        cfg = HospitalConfig.get()
        fee = cfg.teleconsultation_fee
        if not fee or fee <= 0:
            return  # billing disabled

        # Don't create duplicate invoices
        existing = Invoice.objects.filter(
            patient=appt.patient,
            notes__startswith=f'[TELE-{appt.pk}]',
        ).exists()
        if existing:
            return

        invoice = Invoice(
            patient=appt.patient,
            notes=f'[TELE-{appt.pk}] Teleconsultation — {appt.get_appointment_type_display()} with Dr. {appt.doctor.get_full_name()}',
            created_by=user,
        )
        invoice.save()

        InvoiceItem.objects.create(
            invoice=invoice,
            description=f'Teleconsultation ({appt.get_appointment_type_display()})',
            quantity=1,
            unit_price=fee,
            created_by=user,
        )
    except Exception:
        pass  # never crash session end due to billing failure


@login_required
def session_room(request, pk):
    """Live video room — clinicians only."""
    if not _can_conduct(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    appt = get_object_or_404(TeleAppointment, pk=pk, is_deleted=False)
    intake = getattr(appt, 'intake', None)
    join_link = request.build_absolute_uri(
        f"/telemedicine/join/{appt.session_room_id}/{appt.patient_join_token}/"
    )
    return render(request, 'telemedicine/session_room.html', {
        'appt': appt,
        'join_link': join_link,
        'intake': intake,
    })


@login_required
def session_notes(request, pk):
    if not _can_conduct(request.user):
        messages.error(request, 'Only licensed clinicians can write session notes.')
        return redirect('dashboard:home')

    appt = get_object_or_404(TeleAppointment, pk=pk, is_deleted=False)
    note = getattr(appt, 'session_note', None)
    intake = getattr(appt, 'intake', None)

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
            if appt.status not in (AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED):
                appt.status = AppointmentStatus.COMPLETED
                appt.ended_at = appt.ended_at or timezone.now()
                appt.updated_by = request.user
                appt.save()

        messages.success(request, 'Session notes saved.')
        return redirect('telemedicine:appointment_detail', pk=pk)

    context = {'appt': appt, 'note': note, 'intake': intake}
    return render(request, 'telemedicine/session_notes_form.html', context)


@login_required
def cancel_appointment(request, pk):
    if not _can_schedule(request.user):
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
    """No-auth page for patient to join — shows intake form if not yet submitted."""
    try:
        appt = TeleAppointment.objects.get(session_room_id=room_id, is_deleted=False)
    except TeleAppointment.DoesNotExist:
        return render(request, 'telemedicine/join_error.html', {'error': 'Appointment not found.'})

    if token != appt.patient_join_token:
        return render(request, 'telemedicine/join_error.html', {'error': 'Invalid session link.'})

    if appt.status == AppointmentStatus.CANCELLED:
        return render(request, 'telemedicine/join_error.html', {'error': 'This appointment has been cancelled.'})

    intake = getattr(appt, 'intake', None)
    show_intake_form = not (intake and intake.submitted_at)

    if not show_intake_form and not appt.patient_joined:
        appt.patient_joined = True
        if appt.status == AppointmentStatus.SCHEDULED:
            appt.status = AppointmentStatus.WAITING
        appt.save(update_fields=['patient_joined', 'status'])

    return render(request, 'telemedicine/patient_join.html', {
        'appt': appt,
        'intake': intake,
        'show_intake_form': show_intake_form,
        'intake_url': f"/telemedicine/join/{room_id}/{token}/intake/",
    })


def patient_intake_submit(request, room_id, token):
    """Patient submits pre-consultation intake form (no auth required)."""
    try:
        appt = TeleAppointment.objects.get(session_room_id=room_id, is_deleted=False)
    except TeleAppointment.DoesNotExist:
        return render(request, 'telemedicine/join_error.html', {'error': 'Appointment not found.'})

    if token != appt.patient_join_token:
        return render(request, 'telemedicine/join_error.html', {'error': 'Invalid session link.'})

    if appt.status == AppointmentStatus.CANCELLED:
        return render(request, 'telemedicine/join_error.html', {'error': 'Appointment cancelled.'})

    if request.method == 'POST':
        intake, _ = PreConsultationIntake.objects.get_or_create(appointment=appt)
        intake.symptoms = request.POST.get('symptoms', '').strip()
        intake.duration = request.POST.get('duration', '').strip()
        try:
            intake.severity_score = max(1, min(10, int(request.POST.get('severity_score', 5))))
        except (ValueError, TypeError):
            intake.severity_score = 5
        intake.worsening = request.POST.get('worsening') == 'on'
        intake.current_medications = request.POST.get('current_medications', '').strip()
        intake.known_allergies = request.POST.get('known_allergies', '').strip()
        intake.other_symptoms = request.POST.get('other_symptoms', '').strip()
        intake.blood_pressure = request.POST.get('blood_pressure', '').strip()
        intake.temperature = request.POST.get('temperature', '').strip()
        intake.submitted_at = timezone.now()

        if intake.symptoms:
            try:
                from apps.ai_assistant.groq_client import tele_triage_summary
                ai_result = tele_triage_summary(
                    symptoms=intake.symptoms,
                    duration=intake.duration,
                    severity=intake.severity_score,
                    medications=intake.current_medications,
                    allergies=intake.known_allergies,
                    other=intake.other_symptoms,
                )
                if ai_result.get('success') and ai_result.get('data'):
                    d = ai_result['data']
                    intake.ai_triage_summary = d.get('summary', '')
                    intake.ai_urgency = d.get('urgency', 'low')
                    intake.ai_key_concerns = d.get('key_concerns', [])
                    intake.ai_doctor_notes = d.get('doctor_notes', '')
            except Exception:
                pass

        intake.save()

        if not appt.patient_joined:
            appt.patient_joined = True
        if appt.status == AppointmentStatus.SCHEDULED:
            appt.status = AppointmentStatus.WAITING
        appt.save(update_fields=['patient_joined', 'status'])

    return redirect('telemedicine:patient_join', room_id=room_id, token=token)


@login_required
@require_POST
def ai_soap_generate(request, pk):
    """AJAX: generate SOAP note — clinicians only."""
    if not _can_conduct(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

    appt = get_object_or_404(TeleAppointment, pk=pk, is_deleted=False)
    intake = getattr(appt, 'intake', None)

    try:
        body = json.loads(request.body)
    except Exception:
        body = {}

    try:
        from apps.ai_assistant.groq_client import tele_generate_soap
        result = tele_generate_soap(
            chief_complaint=appt.chief_complaint,
            intake_symptoms=intake.symptoms if intake else '',
            duration=intake.duration if intake else '',
            severity=intake.severity_score if intake else 5,
            medications=intake.current_medications if intake else '',
            doctor_notes=body.get('doctor_notes', ''),
            assessment_hint=body.get('assessment_hint', ''),
        )
        if result.get('success') and result.get('data'):
            d = result['data']
            return JsonResponse({
                'success': True,
                'subjective': d.get('subjective', ''),
                'objective': d.get('objective', ''),
                'assessment': d.get('assessment', ''),
                'plan': d.get('plan', ''),
                'follow_up_days': d.get('follow_up_days', ''),
            })
        return JsonResponse({'success': False, 'error': result.get('error', 'AI generation failed')})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def ai_diagnose(request, pk):
    """AJAX: differential diagnosis suggestions — clinicians only."""
    if not _can_conduct(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

    appt = get_object_or_404(TeleAppointment, pk=pk, is_deleted=False)
    intake = getattr(appt, 'intake', None)

    try:
        from apps.ai_assistant.groq_client import suggest_diagnosis_groq
        result = suggest_diagnosis_groq(
            chief_complaint=appt.chief_complaint or (intake.symptoms if intake else 'Not specified'),
            exam_data={
                'patient_reported_severity': f"{intake.severity_score}/10" if intake else '',
                'duration': intake.duration if intake else '',
                'current_medications': intake.current_medications if intake else '',
                'allergies': intake.known_allergies if intake else '',
                'other_symptoms': intake.other_symptoms if intake else '',
                'worsening': 'Yes' if (intake and intake.worsening) else 'Not indicated',
            },
            history=appt.chief_complaint or '',
        )
        if result.get('success') and result.get('data'):
            return JsonResponse({'success': True, **result['data']})
        return JsonResponse({'success': False, 'error': result.get('error', 'AI failed')})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ── Prescriptions ─────────────────────────────────────────────────────────────

@login_required
@require_POST
def add_prescription(request, pk):
    """Add one drug to this appointment's prescription list."""
    if not _can_conduct(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

    appt = get_object_or_404(TeleAppointment, pk=pk, is_deleted=False)
    drug_name = request.POST.get('drug_name', '').strip()
    dose      = request.POST.get('dose', '').strip()
    if not drug_name or not dose:
        return JsonResponse({'success': False, 'error': 'Drug name and dose are required.'})

    rx = TelePrescription.objects.create(
        appointment=appt,
        drug_name=drug_name,
        dose=dose,
        frequency=request.POST.get('frequency', '').strip(),
        duration=request.POST.get('duration', '').strip(),
        route=request.POST.get('route', '').strip(),
        instructions=request.POST.get('instructions', '').strip(),
        prescribed_by=request.user,
        created_by=request.user,
    )
    return JsonResponse({
        'success': True,
        'rx': {
            'id': rx.pk,
            'drug_name': rx.drug_name,
            'dose': rx.dose,
            'frequency': rx.frequency,
            'duration': rx.duration,
            'route': rx.route,
            'instructions': rx.instructions,
        },
    })


@login_required
@require_POST
def delete_prescription(request, pk, rx_pk):
    """Remove a prescription line."""
    if not _can_conduct(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

    rx = get_object_or_404(TelePrescription, pk=rx_pk, appointment_id=pk)
    rx.delete()
    return JsonResponse({'success': True})


@login_required
def print_prescription(request, pk):
    """Printable prescription sheet."""
    if not _can_conduct(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    appt = get_object_or_404(TeleAppointment, pk=pk, is_deleted=False)
    prescriptions = appt.prescriptions.filter(is_deleted=False)
    from apps.accounts.models import HospitalConfig
    return render(request, 'telemedicine/prescription_print.html', {
        'appt': appt,
        'prescriptions': prescriptions,
        'config': HospitalConfig.get(),
    })


# ── Referral ──────────────────────────────────────────────────────────────────

@login_required
@require_POST
def save_referral(request, pk):
    """Create or update the referral for this appointment."""
    if not _can_conduct(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

    appt = get_object_or_404(TeleAppointment, pk=pk, is_deleted=False)
    referral_to = request.POST.get('referral_to', '').strip()
    reason      = request.POST.get('reason', '').strip()
    if not referral_to or not reason:
        return JsonResponse({'success': False, 'error': 'Refer to and reason are required.'})

    ref, created = TeleReferral.objects.get_or_create(
        appointment=appt,
        defaults={'created_by': request.user},
    )
    ref.referral_to       = referral_to
    ref.urgency           = request.POST.get('urgency', TeleReferral.Urgency.ROUTINE)
    ref.reason            = reason
    ref.clinical_summary  = request.POST.get('clinical_summary', '').strip()
    ref.notes             = request.POST.get('notes', '').strip()
    ref.updated_by        = request.user
    ref.save()
    return JsonResponse({
        'success': True,
        'referral': {
            'id': ref.pk,
            'referral_to': ref.referral_to,
            'urgency': ref.get_urgency_display(),
            'reason': ref.reason,
        },
    })


@login_required
def print_referral(request, pk):
    """Printable referral letter."""
    if not _can_conduct(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    appt = get_object_or_404(TeleAppointment, pk=pk, is_deleted=False)
    referral = appt.referrals.filter(is_deleted=False).first()
    from apps.accounts.models import HospitalConfig
    return render(request, 'telemedicine/referral_print.html', {
        'appt': appt,
        'referral': referral,
        'config': HospitalConfig.get(),
    })
