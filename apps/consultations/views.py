from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Q
from .models import Consultation, ConsultationDiagnosis, ConsultationNote, Diagnosis, ConsultationStatus
from apps.patients.models import Patient, Visit, VisitStatus
from apps.departments.models import Department
from .forms import ConsultationForm, ConsultationNoteForm, DiagnosisForm
from apps.core.decorators import clinical_staff_required, doctor_required
from apps.core.context_processors import qms_active as _qms_active

# Maps department code → QMS service types handled by that dept
_DEPT_TO_SERVICE_TYPES = {
    'GEN_OPH':    ['GENERAL', 'VIP_CONSULT', 'EXP_CONSULT', 'INSUR_CONSULT'],
    'RETINA':     ['RETINA'],
    'GLAUC':      ['GLAUCOMA'],
    'PEDS_OPH':   ['PEDIATRIC'],
    'PEDS_REFRAC':['PEDIATRIC'],
    'REFRAC':     ['REFRACTION'],
    'CORNEA':     ['CORNEA'],
    'OCULOPLASTY':['OCULOPLASTY'],
    'NEURO_OPH':  ['NEURO'],
    'CATARACT':   ['CATARACT'],
    'UVEITIS':    ['UVEITIS'],
    'LOW_VIS':    ['LOW_VISION'],
    'INVEST':     ['INVEST'],
}

# Maps department code → Visit statuses that mean "patient is waiting here" (used when QMS is OFF)
_DEPT_TO_VISIT_STATUSES = {
    'GEN_OPH':     ['WAITING', 'IN_CONSULTATION'],
    'RETINA':      ['AT_RETINA'],
    'GLAUC':       ['AT_GLAUCOMA'],
    'PEDS_OPH':    ['AT_PEDIATRIC'],
    'PEDS_REFRAC': ['AT_PEDIATRIC'],
    'REFRAC':      ['REFRACTION'],
    'CORNEA':      ['AT_CORNEA'],
    'OCULOPLASTY': ['AT_OCULOPLASTY'],
    'NEURO_OPH':   ['AT_NEURO'],
    'CATARACT':    ['AT_CATARACT'],
    'UVEITIS':     ['UVEITIS'],
    'LOW_VIS':     ['WAITING', 'IN_CONSULTATION'],
}


@login_required
def consultation_list_view(request):
    user = request.user
    # Roles with read-only access to all consultations (oversight / records)
    _read_only_roles = ('medical_records', 'anaesthetist', 'ceo', 'admin_director', 'super_admin')
    if not user.can_create_consultation() and user.role not in _read_only_roles:
        return HttpResponseForbidden()

    consultations = Consultation.objects.select_related(
        'patient', 'department', 'consulting_doctor'
    ).filter(is_deleted=False)

    # Medical director and read-only roles see all; doctors see their own only
    if not user.is_medical_director and user.role not in _read_only_roles:
        consultations = consultations.filter(consulting_doctor=user)

    status_filter = request.GET.get('status', '')
    dept_filter = request.GET.get('department', '')
    if status_filter:
        consultations = consultations.filter(status=status_filter)
    if dept_filter:
        consultations = consultations.filter(department_id=dept_filter)

    return render(request, 'consultations/list.html', {
        'consultations': consultations[:50],
        'departments': Department.objects.filter(is_active=True),
        'status_choices': ConsultationStatus.choices,
        'status_filter': status_filter,
        'dept_filter': dept_filter,
    })


@login_required
def consultation_create_view(request, patient_id):
    if not request.user.can_create_consultation():
        return HttpResponseForbidden()

    # Investigation Technicians must use the Investigations Workstation — not this form
    from apps.accounts.models import UserRole
    if request.user.role == UserRole.INVESTIGATION_TECHNICIAN:
        messages.info(
            request,
            'Investigation results are recorded in the Investigations Workstation, not via Consultation.'
        )
        return redirect('investigations:workstation')

    patient = get_object_or_404(Patient, patient_id=patient_id)

    # Get active visit — require explicit confirmation for walk-ins (no silent billing bypass)
    visit_id = request.GET.get('visit_id')
    if visit_id:
        visit = get_object_or_404(Visit, pk=visit_id, patient=patient)
    else:
        visit = patient.visits.filter(status__in=['WAITING', 'TRIAGE', 'IN_CONSULTATION']).first()
        if not visit:
            # No active visit — require doctor to explicitly confirm walk-in details
            if request.method == 'POST' and request.POST.get('walkin_confirm'):
                chief = request.POST.get('chief_complaint', '').strip()
                reason = request.POST.get('walkin_reason', '').strip()
                if not chief or not reason:
                    messages.error(request, 'Chief complaint and reason are both required.')
                    return render(request, 'consultations/walkin_confirm.html', {'patient': patient})
                visit = Visit.objects.create(
                    patient=patient,
                    visit_type='EMERGENCY' if reason == 'EMERGENCY' else (
                        'NEW' if not patient.visits.exists() else 'FOLLOW_UP'
                    ),
                    chief_complaint=chief,
                    status='WAITING',
                    attending_doctor=request.user,
                    department=request.user.department,
                    created_by=request.user,
                )
                messages.info(request, f'Walk-in visit {visit.visit_number} created. Complete the consultation below.')
                return redirect(f"{request.path}?visit_id={visit.pk}")
            else:
                return render(request, 'consultations/walkin_confirm.html', {'patient': patient})

    # Stub passed to the template so specialty form partials can render
    # with empty data (they do: {% with d=consultation.department_specific_data %})
    class _Stub:
        department_specific_data = {}
    consultation_stub = _Stub()

    # Previous consultations for this patient — shown as read-only history sidebar
    prev_consultations = list(
        Consultation.objects.filter(
            patient=patient,
            is_deleted=False,
            status=ConsultationStatus.COMPLETED,
        ).exclude(visit=visit).select_related(
            'department', 'consulting_doctor'
        ).order_by('-consultation_date')[:5]
    )

    # Most recent investigation results for this patient — used by Glaucoma/Retina forms
    # to show VF, OCT, B-scan as read-only. Reads from InvestigationResult.result_data.
    from apps.investigations.models import InvestigationOrder, InvestigationResult
    investigation_consult = None  # kept for template compatibility
    investigation_data = {}
    recent_results = InvestigationResult.objects.filter(
        order__patient=patient,
        order__is_deleted=False,
    ).select_related('order__investigation_type', 'performed_by').order_by('-result_date')[:10]
    for res in recent_results:
        # Merge all recent result_data into one dict (newer results win)
        for k, v in res.result_data.items():
            if k not in investigation_data and v:
                investigation_data[k] = v
    # Store most recent result for "recorded by" display
    investigation_consult = recent_results.first() if recent_results else None

    # Most recent refractionist consultation — used by Gen Oph form to show
    # VA and refraction data as read-only (refractionist's work, not the doctor's)
    refraction_consult = Consultation.objects.filter(
        patient=patient,
        is_deleted=False,
        department__code__in=['REFRAC', 'PEDS_REFRAC'],
    ).select_related('department', 'consulting_doctor').order_by('-consultation_date').first()
    refraction_data = refraction_consult.department_specific_data if refraction_consult else {}

    # Most recent consultation from THIS visit by another doctor — used to pre-fill
    # history fields so referred specialists don't have to re-enter what was already taken
    referring_consult = Consultation.objects.filter(
        visit=visit,
        is_deleted=False,
    ).select_related('department', 'consulting_doctor').order_by('-consultation_date').first()

    if request.method == 'POST':
        _dept = request.user.department

        # ── Draft mode: save minimal record so doctor can order tests first ──
        if request.POST.get('save_mode') == 'draft':
            consultation = Consultation.objects.create(
                patient=patient,
                visit=visit,
                department=_dept,
                consulting_doctor=request.user,
                presenting_complaint=request.POST.get('presenting_complaint', '').strip(),
                history_of_presenting_complaint=request.POST.get('history_of_presenting_complaint', '').strip(),
                ocular_history=request.POST.get('ocular_history', '').strip(),
                systemic_history=request.POST.get('systemic_history', '').strip(),
                drug_history=request.POST.get('drug_history', '').strip(),
                status=ConsultationStatus.IN_PROGRESS,
                created_by=request.user,
            )
            visit.status = 'IN_CONSULTATION'
            visit.attending_doctor = request.user
            visit.save(update_fields=['status', 'attending_doctor'])
            messages.success(
                request,
                'Consultation draft saved. Order investigations, then return here to complete the notes.'
            )
            return redirect('consultations:detail', pk=consultation.pk)

        form = ConsultationForm(request.POST)
        # Inject the doctor's department so the hidden field never fails validation
        if not form.data.get('department') and _dept:
            _mutable = form.data.copy()
            _mutable['department'] = str(_dept.pk)
            form.data = _mutable
        if form.is_valid():
            consultation = form.save(commit=False)
            consultation.patient = patient
            consultation.visit = visit
            consultation.consulting_doctor = request.user
            consultation.created_by = request.user

            # Save dept_ prefixed exam fields from the same form submission
            dept_data = {
                k[5:]: v.strip()
                for k, v in request.POST.items()
                if k.startswith('dept_') and v.strip()
            }
            if dept_data:
                consultation.department_specific_data = dept_data

            # Populate standardised examination_findings from dept_ fields
            # Each department uses different naming — normalise them all here
            ef = consultation.get_default_examination_template()
            # Visual Acuity — resolve across all naming conventions
            ef['visual_acuity']['right_unaided'] = (
                dept_data.get('va_re_unaided') or dept_data.get('va_od_un') or
                dept_data.get('va_od') or dept_data.get('va_unaided_od') or ''
            )
            ef['visual_acuity']['left_unaided'] = (
                dept_data.get('va_le_unaided') or dept_data.get('va_os_un') or
                dept_data.get('va_os') or dept_data.get('va_unaided_os') or ''
            )
            ef['visual_acuity']['right_pinhole'] = dept_data.get('va_re_ph', '')
            ef['visual_acuity']['left_pinhole'] = dept_data.get('va_le_ph', '')
            ef['visual_acuity']['right_best_corrected'] = (
                dept_data.get('va_re_bcva') or dept_data.get('va_od_rx') or
                dept_data.get('va_corrected_od') or ''
            )
            ef['visual_acuity']['left_best_corrected'] = (
                dept_data.get('va_le_bcva') or dept_data.get('va_os_rx') or
                dept_data.get('va_corrected_os') or ''
            )
            # IOP — resolve OD/OE → right, OS/LE → left
            ef['intraocular_pressure']['right'] = (
                dept_data.get('iop_re') or dept_data.get('iop_od') or ''
            )
            ef['intraocular_pressure']['left'] = (
                dept_data.get('iop_le') or dept_data.get('iop_os') or ''
            )
            ef['intraocular_pressure']['method'] = dept_data.get('iop_method', 'Non-Contact Tonometry')
            # Anterior / Posterior segment and Slit Lamp
            ef['anterior_segment']['right'] = dept_data.get('anterior_re', '')
            ef['anterior_segment']['left'] = dept_data.get('anterior_le', '')
            ef['posterior_segment']['right'] = dept_data.get('posterior_re', '')
            ef['posterior_segment']['left'] = dept_data.get('posterior_le', '')
            ef['slit_lamp']['cornea'] = dept_data.get('sl_cornea', '')
            ef['slit_lamp']['anterior_chamber'] = dept_data.get('sl_ac', '')
            ef['slit_lamp']['lens'] = dept_data.get('sl_lens', '')
            ef['slit_lamp']['conjunctiva'] = dept_data.get('sl_conj', '')
            ef['pupils'] = dept_data.get('pupils', '')
            ef['ocular_motility'] = dept_data.get('ocular_motility', '')
            consultation.examination_findings = ef
            consultation.status = ConsultationStatus.IN_PROGRESS
            consultation.save()
            visit.status = 'IN_CONSULTATION'
            visit.attending_doctor = request.user
            visit.save(update_fields=['status', 'attending_doctor'])

            # ── Surgery recommended → auto-create COUNSELING queue token ──────
            surgery_recommended = dept_data.get('surgery_recommended', '') == 'on'
            if surgery_recommended and visit:
                try:
                    if _qms_active():
                        from apps.qms.models import (
                            QueueToken, DailyTokenSequence, IssuancePoint,
                            TokenStatus, TIER_PRIORITY,
                        )
                        tier = visit.service_tier or 'STANDARD'
                        token_number = DailyTokenSequence.next_dept_token('COUNSEL')
                        QueueToken.objects.create(
                            token_number=token_number,
                            service_type='COUNSEL',
                            patient=patient,
                            visit=visit,
                            service_tier=tier,
                            issuance_point=IssuancePoint.SYSTEM,
                            priority=TIER_PRIORITY.get(tier, 0),
                            status=TokenStatus.WAITING,
                            notes=f'Surgery referral by Dr. {request.user.get_full_name()} — '
                                  f'{dept_data.get("surgical_procedure", "")}',
                            created_by=request.user,
                        )
                        messages.info(request, 'Patient sent to Surgical Counseling queue.')
                    visit.status = 'COUNSELING'
                    visit.save(update_fields=['status', 'updated_at'])
                except Exception:
                    pass  # Never block the doctor

            # ── Auto-create follow-up appointment if follow_up_date set ───────
            if consultation.follow_up_date:
                try:
                    from apps.appointments.models import Appointment
                    import datetime
                    Appointment.objects.create(
                        patient=patient,
                        department=consultation.department,
                        doctor=request.user,
                        appointment_date=consultation.follow_up_date,
                        appointment_time=datetime.time(8, 0),
                        appointment_type=Appointment.AppointmentType.FOLLOW_UP,
                        reason=(consultation.follow_up_instructions or
                                f'Follow-up for {consultation.primary_diagnosis or "consultation"}'),
                        status=Appointment.Status.SCHEDULED,
                        booked_by=request.user,
                        created_by=request.user,
                    )
                    messages.info(request,
                        f'Follow-up appointment auto-scheduled for {consultation.follow_up_date:%d %b %Y}.')
                except Exception:
                    pass  # Never block the doctor

            messages.success(request, 'Consultation saved. Click "Complete" on the detail page when you are done.')
            return redirect('consultations:detail', pk=consultation.pk)
    else:
        dept = request.user.department
        initial = {'department': dept}
        # Pre-fill history fields from the referring doctor's consultation in this visit
        if referring_consult:
            for field in ['presenting_complaint', 'history_of_presenting_complaint',
                          'ocular_history', 'systemic_history', 'drug_history',
                          'family_history', 'social_history']:
                val = getattr(referring_consult, field, '')
                if val:
                    initial[field] = val
        form = ConsultationForm(initial=initial)

    from apps.patients.models import PatientMedication, PatientAllergy
    patient_medications = list(
        PatientMedication.objects.filter(patient=patient, is_active=True).order_by('drug_name')
    )
    patient_allergies = list(
        PatientAllergy.objects.filter(patient=patient, is_active=True).order_by('severity', 'allergen')
    )

    return render(request, 'consultations/create.html', {
        'form': form,
        'patient': patient,
        'visit': visit,
        'consultation_stub': consultation_stub,
        'prev_consultations': prev_consultations,
        'refraction_consult': refraction_consult,
        'refraction_data': refraction_data,
        'referring_consult': referring_consult,
        'investigation_consult': investigation_consult,
        'investigation_data': investigation_data,
        'patient_medications': patient_medications,
        'patient_allergies': patient_allergies,
    })


@login_required
@clinical_staff_required
def consultation_detail_view(request, pk):
    consultation = get_object_or_404(
        Consultation.objects.select_related(
            'patient', 'department', 'consulting_doctor', 'visit'
        ).prefetch_related(
            'consultation_diagnoses__diagnosis',
            'notes',
            'drug_prescriptions',
            'optical_prescriptions',
            'investigation_orders',
            'lab_orders',
        ),
        pk=pk,
        is_deleted=False
    )
    note_form = ConsultationNoteForm()
    from apps.qms.models import ServiceType

    # All OTHER consultations from the same visit — shown read-only in the
    # "Patient Record" tab so every doctor can see what colleagues have written.
    other_consultations = []
    if consultation.visit:
        other_consultations = list(
            Consultation.objects.filter(
                visit=consultation.visit,
                is_deleted=False
            ).exclude(pk=consultation.pk).select_related(
                'department', 'consulting_doctor'
            ).prefetch_related('consultation_diagnoses__diagnosis').order_by('consultation_date')
        )

    from apps.patients.models import PatientAllergy
    patient_allergies = list(
        PatientAllergy.objects.filter(patient=consultation.patient, is_active=True)
        .order_by('severity', 'allergen')
    )

    return render(request, 'consultations/detail.html', {
        'consultation': consultation,
        'note_form': note_form,
        'departments': Department.get_clinical_departments(),
        'service_types': ServiceType.choices,
        'other_consultations': other_consultations,
        'patient_allergies': patient_allergies,
    })


@login_required
def consultation_edit_view(request, pk):
    consultation = get_object_or_404(Consultation, pk=pk, is_deleted=False)

    # Only the consulting doctor or medical director can edit
    if consultation.consulting_doctor != request.user and not request.user.is_medical_director:
        return HttpResponseForbidden()

    if consultation.status == ConsultationStatus.COMPLETED and not request.user.is_medical_director:
        messages.error(request, 'Completed consultations cannot be edited.')
        return redirect('consultations:detail', pk=pk)

    if request.method == 'POST':
        form = ConsultationForm(request.POST, instance=consultation)
        if form.is_valid():
            c = form.save(commit=False)
            c.updated_by = request.user
            # Also persist any dept_ exam fields submitted alongside
            dept_data = {
                k[5:]: v.strip()
                for k, v in request.POST.items()
                if k.startswith('dept_') and v.strip()
            }
            if dept_data:
                existing = c.department_specific_data or {}
                existing.update(dept_data)
                c.department_specific_data = existing
                # Sync standardised examination_findings with the updated dept_data
                ef = c.examination_findings or c.get_default_examination_template()
                combined = {**existing}  # full merged dept_data
                ef['visual_acuity']['right_unaided'] = (
                    combined.get('va_re_unaided') or combined.get('va_od_un') or
                    combined.get('va_od') or combined.get('va_unaided_od') or
                    ef['visual_acuity'].get('right_unaided', ''))
                ef['visual_acuity']['left_unaided'] = (
                    combined.get('va_le_unaided') or combined.get('va_os_un') or
                    combined.get('va_os') or combined.get('va_unaided_os') or
                    ef['visual_acuity'].get('left_unaided', ''))
                ef['visual_acuity']['right_pinhole'] = combined.get('va_re_ph') or ef['visual_acuity'].get('right_pinhole', '')
                ef['visual_acuity']['left_pinhole'] = combined.get('va_le_ph') or ef['visual_acuity'].get('left_pinhole', '')
                ef['visual_acuity']['right_best_corrected'] = (
                    combined.get('va_re_bcva') or combined.get('va_od_rx') or
                    combined.get('va_corrected_od') or ef['visual_acuity'].get('right_best_corrected', ''))
                ef['visual_acuity']['left_best_corrected'] = (
                    combined.get('va_le_bcva') or combined.get('va_os_rx') or
                    combined.get('va_corrected_os') or ef['visual_acuity'].get('left_best_corrected', ''))
                ef['intraocular_pressure']['right'] = (
                    combined.get('iop_re') or combined.get('iop_od') or
                    ef['intraocular_pressure'].get('right', ''))
                ef['intraocular_pressure']['left'] = (
                    combined.get('iop_le') or combined.get('iop_os') or
                    ef['intraocular_pressure'].get('left', ''))
                c.examination_findings = ef
            c.save()

            # Auto-create follow-up appointment if follow_up_date was set
            if c.follow_up_date:
                from apps.appointments.models import Appointment
                already = Appointment.objects.filter(
                    patient=c.patient,
                    appointment_date=c.follow_up_date,
                    appointment_type='FOLLOW_UP',
                    is_deleted=False,
                ).exists()
                if not already:
                    Appointment.objects.create(
                        patient=c.patient,
                        department=c.department,
                        appointment_date=c.follow_up_date,
                        appointment_type='FOLLOW_UP',
                        reason=f"Follow-up from consultation {c.consultation_date.strftime('%d/%m/%Y')}",
                        status='SCHEDULED',
                        booked_by=request.user,
                        created_by=request.user,
                    )
                    messages.info(request, f'Follow-up appointment auto-created for {c.follow_up_date.strftime("%d %b %Y")}.')

            # If doctor clicks "Save & Complete", mark as completed now
            if request.POST.get('save_mode') == 'complete':
                c.status = ConsultationStatus.COMPLETED
                c.save(update_fields=['status', 'updated_at'])
                # Complete the QMS token so patient leaves this queue
                if _qms_active():
                    try:
                        from apps.qms.models import QueueToken, TokenStatus
                        dept_code = request.user.role_department_code
                        svc_types = _DEPT_TO_SERVICE_TYPES.get(dept_code, [])
                        if svc_types:
                            active_token = QueueToken.objects.filter(
                                visit=c.visit,
                                service_type__in=svc_types,
                                status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                                is_deleted=False,
                            ).first()
                            if active_token:
                                active_token.complete()
                    except Exception:
                        pass
                messages.success(request, 'Consultation completed.')
            else:
                messages.success(request, 'Consultation saved. Open the consultation and click "Complete" when you are done.')
            return redirect('consultations:detail', pk=pk)
    else:
        form = ConsultationForm(instance=consultation)

    # Load latest investigation results so doctor can reference them while filling clinical form
    from apps.investigations.models import InvestigationResult
    investigation_data = {}
    recent_results = InvestigationResult.objects.filter(
        order__patient=consultation.patient,
        order__is_deleted=False,
    ).select_related('order__investigation_type', 'performed_by').order_by('-result_date')[:10]
    for res in recent_results:
        for k, v in res.result_data.items():
            if k not in investigation_data and v:
                investigation_data[k] = v

    # Latest investigation orders for this consultation — shown as a results panel
    from apps.investigations.models import InvestigationOrder
    investigation_orders = list(
        InvestigationOrder.objects.filter(
            consultation=consultation, is_deleted=False
        ).select_related('investigation_type', 'result').order_by('-created_at')
    )

    return render(request, 'consultations/edit.html', {
        'form': form,
        'consultation': consultation,
        'investigation_data': investigation_data,
        'investigation_orders': investigation_orders,
        'is_resuming': consultation.status == ConsultationStatus.IN_PROGRESS,
    })


@login_required
@require_POST
def consultation_complete_view(request, pk):
    consultation = get_object_or_404(Consultation, pk=pk)
    if consultation.consulting_doctor != request.user and not request.user.is_medical_director:
        return HttpResponseForbidden()
    consultation.status = ConsultationStatus.COMPLETED
    consultation.updated_by = request.user
    consultation.save(update_fields=['status', 'updated_by', 'updated_at'])

    # Complete the QueueToken so patient leaves this doctor's waiting queue
    visit = consultation.visit
    if visit and _qms_active():
        _doctor_service_types = {
            'GEN_OPH':     ['GENERAL', 'VIP_CONSULT', 'EXP_CONSULT', 'INSUR_CONSULT'],
            'RETINA':      ['RETINA'],
            'GLAUC':       ['GLAUCOMA'],
            'PEDS_OPH':    ['PEDIATRIC'],
            'PEDS_REFRAC': ['PEDIATRIC'],
            'REFRAC':      ['REFRACTION'],
            'CORNEA':      ['CORNEA'],
            'OCULOPLASTY': ['OCULOPLASTY'],
            'NEURO_OPH':   ['NEURO'],
            'CATARACT':    ['CATARACT'],
            'UVEITIS':     ['UVEITIS'],
            'LOW_VIS':     ['LOW_VISION'],
        }
        try:
            from apps.qms.models import QueueToken, TokenStatus
            dept_code = request.user.role_department_code
            svc_types = _doctor_service_types.get(dept_code, [])
            if svc_types:
                active_token = QueueToken.objects.filter(
                    visit=visit,
                    service_type__in=svc_types,
                    status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                    is_deleted=False,
                ).first()
                if active_token:
                    active_token.complete()
                    if (active_token.counter and
                            active_token.counter.current_serving_id == active_token.pk):
                        active_token.counter.current_serving = None
                        active_token.counter.save(update_fields=['current_serving', 'updated_at'])
        except Exception:
            pass

    messages.success(request, 'Consultation marked as completed.')
    return redirect('consultations:detail', pk=pk)


@login_required
@require_POST
def cosign_consultation_view(request, pk):
    """Supervisor co-signs an intern's consultation (JCI ACC.3 / COP)."""
    from django.utils import timezone as tz
    consultation = get_object_or_404(Consultation, pk=pk)
    # Only doctors (non-intern) and medical director can co-sign
    u = request.user
    can_cosign = (u.is_doctor or u.is_medical_director) and getattr(u, 'role', None) != 'intern'
    if not can_cosign:
        messages.error(request, 'Only supervising doctors can co-sign intern consultations.')
        return redirect('consultations:detail', pk=pk)
    if not consultation.needs_cosign:
        messages.warning(request, 'This consultation does not require co-signature.')
        return redirect('consultations:detail', pk=pk)
    consultation.co_signed_by = u
    consultation.co_signed_at = tz.now()
    consultation.updated_by = u
    consultation.save(update_fields=['co_signed_by', 'co_signed_at', 'updated_by', 'updated_at'])
    messages.success(request, f'Consultation co-signed. Intern note countersigned by Dr. {u.get_full_name()}.')
    return redirect('consultations:detail', pk=pk)


@login_required
@require_POST
def add_note_view(request, pk):
    consultation = get_object_or_404(Consultation, pk=pk)
    form = ConsultationNoteForm(request.POST)
    if form.is_valid():
        note = form.save(commit=False)
        note.consultation = consultation
        note.created_by = request.user
        note.save()
        messages.success(request, 'Note added.')
    return redirect('consultations:detail', pk=pk)


@login_required
@require_POST
def save_dept_clinical_view(request, pk):
    """Save department-specific clinical data from the clinical exam tab."""
    consultation = get_object_or_404(Consultation, pk=pk, is_deleted=False)
    if consultation.consulting_doctor != request.user and not request.user.is_medical_director:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    # Extract all dept_ prefixed fields from POST
    dept_data = {}
    for key, value in request.POST.items():
        if key.startswith('dept_'):
            field = key[5:]  # strip 'dept_' prefix
            if value.strip():
                dept_data[field] = value.strip()

    # Merge into existing data (preserve any existing keys not submitted)
    existing = consultation.department_specific_data or {}
    existing.update(dept_data)
    consultation.department_specific_data = existing

    # Sync examination_findings with updated dept_data
    combined = existing
    ef = consultation.examination_findings or consultation.get_default_examination_template()
    ef['visual_acuity']['right_unaided'] = (
        combined.get('va_re_unaided') or combined.get('va_od_un') or
        combined.get('va_od') or combined.get('va_unaided_od') or ef['visual_acuity'].get('right_unaided', ''))
    ef['visual_acuity']['left_unaided'] = (
        combined.get('va_le_unaided') or combined.get('va_os_un') or
        combined.get('va_os') or combined.get('va_unaided_os') or ef['visual_acuity'].get('left_unaided', ''))
    ef['visual_acuity']['right_pinhole'] = combined.get('va_re_ph') or ef['visual_acuity'].get('right_pinhole', '')
    ef['visual_acuity']['left_pinhole'] = combined.get('va_le_ph') or ef['visual_acuity'].get('left_pinhole', '')
    ef['visual_acuity']['right_best_corrected'] = (
        combined.get('va_re_bcva') or combined.get('va_od_rx') or
        combined.get('va_corrected_od') or ef['visual_acuity'].get('right_best_corrected', ''))
    ef['visual_acuity']['left_best_corrected'] = (
        combined.get('va_le_bcva') or combined.get('va_os_rx') or
        combined.get('va_corrected_os') or ef['visual_acuity'].get('left_best_corrected', ''))
    ef['intraocular_pressure']['right'] = (
        combined.get('iop_re') or combined.get('iop_od') or ef['intraocular_pressure'].get('right', ''))
    ef['intraocular_pressure']['left'] = (
        combined.get('iop_le') or combined.get('iop_os') or ef['intraocular_pressure'].get('left', ''))
    consultation.examination_findings = ef

    consultation.updated_by = request.user
    consultation.save(update_fields=['department_specific_data', 'examination_findings', 'updated_by', 'updated_at'])

    messages.success(request, 'Clinical examination data saved.')
    return redirect('consultations:detail', pk=pk)


@login_required
@require_POST
def update_exam_findings_view(request, pk):
    """
    Quick-update the standardised examination_findings from the detail page.
    Accepts a flat set of fields (va_re_unaided, va_le_unaided, iop_re, iop_le,
    iop_method, pupils, anterior_re, anterior_le, posterior_re, posterior_le).
    """
    consultation = get_object_or_404(Consultation, pk=pk, is_deleted=False)
    if consultation.consulting_doctor != request.user and not request.user.is_medical_director:
        return HttpResponseForbidden()

    ef = consultation.examination_findings or consultation.get_default_examination_template()
    p = request.POST

    def g(key, fallback=''):
        return p.get(key, '').strip() or fallback

    ef['visual_acuity']['right_unaided']      = g('va_re_unaided', ef['visual_acuity'].get('right_unaided', ''))
    ef['visual_acuity']['left_unaided']       = g('va_le_unaided', ef['visual_acuity'].get('left_unaided', ''))
    ef['visual_acuity']['right_pinhole']      = g('va_re_ph', ef['visual_acuity'].get('right_pinhole', ''))
    ef['visual_acuity']['left_pinhole']       = g('va_le_ph', ef['visual_acuity'].get('left_pinhole', ''))
    ef['visual_acuity']['right_best_corrected'] = g('va_re_bcva', ef['visual_acuity'].get('right_best_corrected', ''))
    ef['visual_acuity']['left_best_corrected']  = g('va_le_bcva', ef['visual_acuity'].get('left_best_corrected', ''))
    ef['intraocular_pressure']['right']  = g('iop_re', ef['intraocular_pressure'].get('right', ''))
    ef['intraocular_pressure']['left']   = g('iop_le', ef['intraocular_pressure'].get('left', ''))
    ef['intraocular_pressure']['method'] = g('iop_method', ef['intraocular_pressure'].get('method', ''))
    ef['anterior_segment']['right']  = g('anterior_re', ef['anterior_segment'].get('right', ''))
    ef['anterior_segment']['left']   = g('anterior_le', ef['anterior_segment'].get('left', ''))
    ef['posterior_segment']['right'] = g('posterior_re', ef['posterior_segment'].get('right', ''))
    ef['posterior_segment']['left']  = g('posterior_le', ef['posterior_segment'].get('left', ''))
    ef['slit_lamp']['cornea']             = g('sl_cornea', ef['slit_lamp'].get('cornea', ''))
    ef['slit_lamp']['anterior_chamber']   = g('sl_ac', ef['slit_lamp'].get('anterior_chamber', ''))
    ef['slit_lamp']['lens']               = g('sl_lens', ef['slit_lamp'].get('lens', ''))
    ef['slit_lamp']['conjunctiva']        = g('sl_conj', ef['slit_lamp'].get('conjunctiva', ''))
    ef['pupils']         = g('pupils', ef.get('pupils', ''))
    ef['ocular_motility'] = g('ocular_motility', ef.get('ocular_motility', ''))
    ef['cover_test']     = g('cover_test', ef.get('cover_test', ''))
    ef['color_vision']   = g('color_vision', ef.get('color_vision', ''))

    consultation.examination_findings = ef
    consultation.updated_by = request.user
    consultation.save(update_fields=['examination_findings', 'updated_by', 'updated_at'])

    messages.success(request, 'Examination findings updated.')
    return redirect('consultations:detail', pk=pk)


@login_required
def diagnosis_search_view(request):
    """AJAX: search ICD-10 diagnoses."""
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})
    diagnoses = Diagnosis.objects.filter(
        is_active=True
    ).filter(
        Q(icd10_code__icontains=q) | Q(description__icontains=q)
    ).values('id', 'icd10_code', 'description')[:15]
    return JsonResponse({'results': list(diagnoses)})


# ── Doctor's Workstation ──────────────────────────────────────────────────────

@login_required
def workstation_view(request):
    """
    Doctor's daily workstation:
      - QMS waiting queue for the doctor's department
      - Today's consultations (their own)
      - Stats
    """
    if not request.user.can_create_consultation():
        return HttpResponseForbidden()

    today = timezone.localdate()
    user = request.user

    # Department the doctor belongs to
    dept = user.department
    dept_code = user.role_department_code or (dept.code if dept else None)

    # ── QMS waiting queue for this doctor's speciality ─────────────────────
    waiting_tokens = []
    waiting_visits = []  # used when QMS is OFF

    if _qms_active() and dept_code:
        try:
            from apps.qms.models import QueueToken, TokenStatus
            service_types = _DEPT_TO_SERVICE_TYPES.get(dept_code, [])
            if service_types:
                waiting_tokens = list(
                    QueueToken.objects.filter(
                        issued_at__date=today,
                        service_type__in=service_types,
                        status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                        is_deleted=False,
                    ).select_related('patient', 'counter').order_by('-priority', 'issued_at')
                )
        except Exception:
            pass
    else:
        # No QMS — show today's active Visits in the doctor's department
        visit_statuses = _DEPT_TO_VISIT_STATUSES.get(dept_code, ['WAITING', 'IN_CONSULTATION'])
        qs = Visit.objects.filter(
            visit_date__date=today,
            status__in=visit_statuses,
            is_deleted=False,
        ).exclude(
            status__in=[VisitStatus.COMPLETED, VisitStatus.DISCHARGED]
        ).select_related('patient', 'department', 'attending_doctor').order_by('visit_date')
        if dept:
            qs = qs.filter(department=dept)
        waiting_visits = list(qs)

    # ── Today's consultations for this doctor ──────────────────────────────
    my_consultations = list(
        Consultation.objects.filter(
            consulting_doctor=user,
            consultation_date__date=today,
            is_deleted=False,
        ).select_related('patient', 'department').order_by('-consultation_date')
    )

    # ── Stats ──────────────────────────────────────────────────────────────
    if _qms_active():
        waiting_count = sum(1 for t in waiting_tokens if t.status == 'WAITING')
        in_progress_count = sum(1 for t in waiting_tokens if t.status in ('CALLED', 'SERVING'))
    else:
        waiting_count = sum(1 for v in waiting_visits if v.status not in ('IN_CONSULTATION',))
        in_progress_count = sum(1 for v in waiting_visits if v.status == 'IN_CONSULTATION')

    completed_today = Consultation.objects.filter(
        consulting_doctor=user,
        consultation_date__date=today,
        status=ConsultationStatus.COMPLETED,
        is_deleted=False,
    ).count()

    # ── Patients waiting for doctor that have active visits (QMS mode) ────
    if waiting_tokens:
        token_patient_ids = [t.patient_id for t in waiting_tokens if t.patient_id]
        active_visits = {
            v.patient_id: v
            for v in Visit.objects.filter(
                patient_id__in=token_patient_ids,
                visit_date__date=today,
                is_deleted=False,
            ).exclude(
                status__in=[VisitStatus.COMPLETED, VisitStatus.DISCHARGED]
            ).order_by('-visit_date')
        }
        for token in waiting_tokens:
            # Use ws_visit / ws_visit_type to avoid overwriting read-only properties
            _v = active_visits.get(token.patient_id) if token.patient_id else None
            token.ws_visit = _v
            token.ws_visit_type = getattr(_v, 'visit_type', None)

    service_type_choices = []
    if _qms_active():
        try:
            from apps.qms.models import ServiceType
            service_type_choices = ServiceType.choices
        except Exception:
            pass

    # ── IN_PROGRESS consultations — awaiting test results, needs resume ───────
    in_progress_consultations = [
        c for c in my_consultations if c.status == ConsultationStatus.IN_PROGRESS
    ]

    # ── Investigation orders for today's consultations ────────────────────────
    from apps.investigations.models import InvestigationOrder
    my_consultation_ids = [c.id for c in my_consultations]
    investigation_orders_today = list(
        InvestigationOrder.objects.filter(
            consultation_id__in=my_consultation_ids,
            is_deleted=False,
        ).select_related(
            'patient', 'investigation_type', 'consultation',
        ).prefetch_related('result__files').order_by('-created_at')
    ) if my_consultation_ids else []

    # Attach results-ready status to each IN_PROGRESS consultation
    if in_progress_consultations and investigation_orders_today:
        completed_by_consult = {}
        pending_by_consult = {}
        for order in investigation_orders_today:
            cid = str(order.consultation_id)
            if order.status == InvestigationOrder.Status.COMPLETED:
                completed_by_consult.setdefault(cid, []).append(order)
            else:
                pending_by_consult.setdefault(cid, []).append(order)
        for c in in_progress_consultations:
            cid = str(c.id)
            c.invest_completed = completed_by_consult.get(cid, [])
            c.invest_pending = pending_by_consult.get(cid, [])
            # results_ready = at least one result done AND no more pending
            c.results_ready = bool(c.invest_completed) and not pending_by_consult.get(cid)

    # ── Lab orders for this doctor's today consultations ─────────────────────
    from apps.laboratory.models import LabOrder
    lab_orders_today = list(
        LabOrder.objects.filter(
            consultation_id__in=my_consultation_ids,
            is_deleted=False,
        ).select_related(
            'patient', 'consultation',
        ).prefetch_related(
            'items__test_type', 'items__result',
        ).order_by('-created_at')
    ) if my_consultation_ids else []

    return render(request, 'consultations/workstation.html', {
        'waiting_tokens': waiting_tokens,
        'waiting_visits': waiting_visits,
        'my_consultations': my_consultations,
        'in_progress_consultations': in_progress_consultations,
        'waiting_count': waiting_count,
        'in_progress_count': in_progress_count,
        'completed_today': completed_today,
        'dept': dept,
        'dept_code': dept_code,
        'today': today,
        'service_types': service_type_choices,
        'qms_on': _qms_active(),
        'investigation_orders_today': investigation_orders_today,
        'lab_orders_today': lab_orders_today,
    })


# ── Triage / Parameters Workstation (Nurses) ──────────────────────────────────

@login_required
def triage_workstation_view(request):
    """
    Nurse's triage workstation.
    Auto-detects the nurse's assigned counter and filters the queue to their tier:
      - Gate / Standard counter → shows PARAMETERS queue (Standard only)
      - VIP/Express counter    → shows PARAMS_VIP queue (VIP + Express + Fast Track)
      - No counter assigned / Medical Director / Super Admin → shows ALL queues
    A manual tier filter in the URL (?tier=ALL|STANDARD|VIP) overrides this.
    """
    if not request.user.can_do_triage() and not request.user.is_super_admin:
        return HttpResponseForbidden()

    today = timezone.localdate()
    assigned_counter = None
    if _qms_active():
        try:
            from apps.qms.models import ServiceCounter
            assigned_counter = ServiceCounter.objects.filter(
                staff_assigned=request.user, is_active=True
            ).first()
        except Exception:
            pass

    # Manual override via URL param
    tier_filter = request.GET.get('tier', '').upper()

    # Determine default view based on counter assignment
    if tier_filter:
        show_mode = tier_filter  # 'STANDARD', 'VIP', or 'ALL'
    elif assigned_counter:
        tiers = assigned_counter.get_serves_tiers()
        if 'VIP' in tiers or 'EXPRESS' in tiers or 'FAST_TRACK' in tiers:
            show_mode = 'VIP'
        else:
            show_mode = 'STANDARD'
    else:
        show_mode = 'ALL'  # Medical director / no counter = see everything

    active_statuses = ['WAITING', 'CALLED', 'SERVING']

    # ── Standard Parameters queue ─────────────────────────────────────────────
    parameters_queue = []
    vip_params_queue = []
    triage_visits = []  # used when QMS is OFF

    if _qms_active():
        try:
            from apps.qms.models import QueueToken
            if show_mode in ('STANDARD', 'ALL'):
                parameters_queue = list(
                    QueueToken.objects.filter(
                        issued_at__date=today,
                        service_type='PARAMETERS',
                        status__in=active_statuses,
                        is_deleted=False,
                    ).select_related('patient', 'counter').order_by('-priority', 'issued_at')
                )

            # ── VIP / Express Parameters queue ────────────────────────────────
            if show_mode in ('VIP', 'ALL'):
                vip_params_queue = list(
                    QueueToken.objects.filter(
                        issued_at__date=today,
                        service_type='PARAMS_VIP',
                        status__in=active_statuses,
                        is_deleted=False,
                    ).select_related('patient', 'counter').order_by('-priority', 'issued_at')
                )
        except Exception:
            pass
    else:
        # No QMS — show visits with PARAMETERS status (patients waiting for triage)
        triage_visits = list(
            Visit.objects.filter(
                visit_date__date=today,
                status='PARAMETERS',
                is_deleted=False,
            ).select_related('patient').order_by('visit_date')
        )

    # ── Enrich tokens with today's active visit ───────────────────────────────
    all_tokens = parameters_queue + vip_params_queue
    if all_tokens:
        patient_ids = [t.patient_id for t in all_tokens if t.patient_id]
        active_visits = {
            v.patient_id: v
            for v in Visit.objects.filter(
                patient_id__in=patient_ids,
                visit_date__date=today,
                is_deleted=False,
            ).exclude(
                status__in=[VisitStatus.COMPLETED, VisitStatus.DISCHARGED]
            ).order_by('-visit_date')
        }
        for token in all_tokens:
            # Use ws_visit (not active_visit) to avoid overwriting the read-only property
            token.ws_visit = active_visits.get(token.patient_id) if token.patient_id else None

    # ── Nurse's personal stats + history ─────────────────────────────────────
    triaged_visits = Visit.objects.filter(
        visit_date__date=today,
        triage_nurse=request.user,
        is_deleted=False,
    ).select_related('patient').order_by('-visit_date')
    triaged_today = triaged_visits.count()

    # ── Tier breakdown for stats strip ────────────────────────────────────────
    total_standard = total_vip_express = 0
    if _qms_active():
        try:
            from apps.qms.models import QueueToken as _QueueToken
            all_today = _QueueToken.objects.filter(
                issued_at__date=today,
                service_type__in=['PARAMETERS', 'PARAMS_VIP'],
                is_deleted=False,
            )
            total_standard = all_today.filter(service_type='PARAMETERS').count()
            total_vip_express = all_today.filter(service_type='PARAMS_VIP').count()
        except Exception:
            pass

    return render(request, 'consultations/triage_workstation.html', {
        'parameters_queue': parameters_queue,
        'vip_params_queue': vip_params_queue,
        'triage_visits': triage_visits,
        'triaged_today': triaged_today,
        'triaged_visits': triaged_visits,
        'today': today,
        'show_mode': show_mode,
        'assigned_counter': assigned_counter,
        'total_standard': total_standard,
        'total_vip_express': total_vip_express,
        'total_waiting': len(parameters_queue) + len(vip_params_queue),
        'qms_on': _qms_active(),
    })


# ── Clinic Nurse Workstation ──────────────────────────────────────────────────

# Mapping dept code → visit statuses that mean "patient is waiting in THIS dept"
_DEPT_TO_WAITING_STATUSES = {
    'GEN_OPH':     ['WAITING'],
    'RETINA':      ['AT_RETINA'],
    'GLAUC':       ['AT_GLAUCOMA'],
    'PEDS_OPH':    ['AT_PEDIATRIC'],
    'PEDS_REFRAC': ['AT_PEDIATRIC'],
    'REFRAC':      ['REFRACTION'],
    'CORNEA':      ['AT_CORNEA'],
    'OCULOPLASTY': ['AT_OCULOPLASTY'],
    'NEURO_OPH':   ['AT_NEURO'],
    'CATARACT':    ['AT_CATARACT'],
    'UVEITIS':     ['UVEITIS'],
    'LOW_VIS':     ['WAITING'],
}

# Mapping dept code → QMS service type
_DEPT_TO_QMS_SERVICE = {
    'GEN_OPH':     'GENERAL',
    'RETINA':      'RETINA',
    'GLAUC':       'GLAUCOMA',
    'PEDS_OPH':    'PEDIATRIC',
    'PEDS_REFRAC': 'PEDIATRIC',
    'REFRAC':      'REFRACTION',
    'CORNEA':      'CORNEA',
    'OCULOPLASTY': 'OCULOPLASTY',
    'NEURO_OPH':   'NEURO',
    'CATARACT':    'CATARACT',
    'UVEITIS':     'UVEITIS',
    'LOW_VIS':     'GENERAL',
}


@login_required
def clinic_nurse_view(request):
    """
    Clinic Nurse Workstation — per-department queue management.

    Works with QMS ON or OFF:
      QMS ON  → Shows QMS tokens for this dept. Nurse clicks "Call" → token.status = CALLED,
                 visit.status = IN_CONSULTATION. Doctor only sees IN_CONSULTATION patients.
      QMS OFF → Shows Visits with dept-specific waiting status (AT_RETINA, AT_GLAUCOMA, etc.)
                 Nurse clicks "Call" → visit.status = IN_CONSULTATION directly.

    Access: OPD Nurse, Ward Nurse, Theatre Nurse, Medical Director, Super Admin.
    """
    user = request.user
    if not (user.can_do_triage() or user.is_medical_director or user.is_super_admin):
        return HttpResponseForbidden()

    today = timezone.localdate()

    # Determine which department's queue to show
    # Allow override via ?dept=GEN_OPH etc. (for Medical Director who roams all depts)
    dept_code_override = request.GET.get('dept', '').upper()
    dept = user.department
    dept_code = dept_code_override or (user.role_department_code or (dept.code if dept else None))

    # Build department options for the switcher (Medical Director / Super Admin see all)
    from apps.departments.models import Department as _Dept
    all_clinical_depts = list(
        _Dept.get_clinical_departments().order_by('name')
    ) if (user.is_medical_director or user.is_super_admin) else []

    qms_on = _qms_active()
    waiting_tokens = []    # QMS mode
    waiting_visits = []    # No-QMS mode
    in_consult_visits = [] # Patients currently being seen by doctor (both modes)

    if qms_on and dept_code:
        # ── QMS ON: show QMS queue tokens for this department ────────────────
        try:
            from apps.qms.models import QueueToken, TokenStatus
            svc_type = _DEPT_TO_QMS_SERVICE.get(dept_code)
            if svc_type:
                waiting_tokens = list(
                    QueueToken.objects.filter(
                        issued_at__date=today,
                        service_type=svc_type,
                        status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                        is_deleted=False,
                    ).select_related('patient', 'counter').order_by('-priority', 'issued_at')
                )
                # Enrich with active visit
                patient_ids = [t.patient_id for t in waiting_tokens if t.patient_id]
                visit_map = {
                    v.patient_id: v
                    for v in Visit.objects.filter(
                        patient_id__in=patient_ids,
                        visit_date__date=today,
                        is_deleted=False,
                    ).exclude(
                        status__in=[VisitStatus.COMPLETED, VisitStatus.DISCHARGED]
                    ).select_related('patient').order_by('-visit_date')
                }
                for tok in waiting_tokens:
                    tok.active_visit = visit_map.get(tok.patient_id) if tok.patient_id else None
        except Exception:
            pass
    elif not qms_on and dept_code:
        # ── QMS OFF: show Visits with dept-specific waiting statuses ─────────
        waiting_statuses = _DEPT_TO_WAITING_STATUSES.get(dept_code, ['WAITING'])
        waiting_visits = list(
            Visit.objects.filter(
                visit_date__date=today,
                status__in=waiting_statuses,
                is_deleted=False,
            ).select_related('patient', 'triage_nurse', 'attending_doctor')
            .order_by('visit_date')  # first in, first out
        )
        if dept:
            waiting_visits = [v for v in waiting_visits if v.department_id == dept.id]

    # ── Patients currently IN_CONSULTATION in this dept today (both modes) ──
    if dept:
        in_consult_visits = list(
            Visit.objects.filter(
                visit_date__date=today,
                status='IN_CONSULTATION',
                department=dept,
                is_deleted=False,
            ).select_related('patient', 'attending_doctor').order_by('-visit_date')
        )

    # ── Today's stats for this dept ────────────────────────────────────────
    completed_today = Visit.objects.filter(
        visit_date__date=today,
        is_deleted=False,
    )
    if dept:
        completed_today = completed_today.filter(department=dept)
    completed_today = completed_today.filter(
        status__in=[VisitStatus.COMPLETED, VisitStatus.DISCHARGED]
    ).count()

    # ── Patients whose consultation is DONE but not yet routed onward ────────
    # Doctor marked consultation complete → nurse routes to pharmacy/cashier/etc.
    ready_to_route = []
    if dept:
        done_visit_ids = set(
            Consultation.objects.filter(
                status=ConsultationStatus.COMPLETED,
                consultation_date__date=today,
                department=dept,
                is_deleted=False,
            ).values_list('visit_id', flat=True)
        )
        if done_visit_ids:
            ready_to_route = list(
                Visit.objects.filter(
                    id__in=done_visit_ids,
                    status='IN_CONSULTATION',
                    is_deleted=False,
                ).select_related('patient', 'attending_doctor').order_by('visit_date')
            )

    return render(request, 'consultations/clinic_nurse.html', {
        'qms_on': qms_on,
        'dept': dept,
        'dept_code': dept_code,
        'all_clinical_depts': all_clinical_depts,
        'waiting_tokens': waiting_tokens,
        'waiting_visits': waiting_visits,
        'in_consult_visits': in_consult_visits,
        'ready_to_route': ready_to_route,
        'waiting_count': len(waiting_tokens) if qms_on else len(waiting_visits),
        'in_consult_count': len(in_consult_visits),
        'completed_today': completed_today,
        'today': today,
    })


@login_required
@require_POST
def clinic_call_patient_view(request, visit_pk):
    """
    Nurse calls the next patient.
    QMS ON:  marks the matching QMS token as CALLED (announced on display board)
             and sets visit.status = IN_CONSULTATION
    QMS OFF: sets visit.status = IN_CONSULTATION directly
    Returns JSON for HTMX / JS update.
    """
    user = request.user
    if not (user.can_do_triage() or user.is_medical_director or user.is_super_admin):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)

    if visit.status in [VisitStatus.IN_CONSULTATION, VisitStatus.COMPLETED, VisitStatus.DISCHARGED]:
        return JsonResponse({'error': 'Patient is already in consultation or completed.'}, status=400)

    # Mark visit as IN_CONSULTATION
    visit.status = VisitStatus.IN_CONSULTATION
    visit.save(update_fields=['status', 'updated_at'])

    # QMS: mark the matching token as CALLED
    if _qms_active():
        try:
            from apps.qms.models import QueueToken, TokenStatus
            dept_code = user.role_department_code or (user.department.code if user.department else None)
            svc_type = _DEPT_TO_QMS_SERVICE.get(dept_code) if dept_code else None
            if svc_type:
                token = QueueToken.objects.filter(
                    patient=visit.patient,
                    service_type=svc_type,
                    issued_at__date=timezone.localdate(),
                    status__in=[TokenStatus.WAITING, TokenStatus.CALLED],
                    is_deleted=False,
                ).first()
                if token:
                    token.status = TokenStatus.SERVING
                    token.save(update_fields=['status', 'updated_at'])
        except Exception:
            pass

    return JsonResponse({
        'success': True,
        'patient': visit.patient.full_name,
        'visit_number': visit.visit_number,
        'message': f'{visit.patient.full_name} has been called — status updated to In Consultation.',
    })


# ── Nurse: route patient after consultation ────────────────────────────────────

# Maps destination key → (VisitStatus, QMS service_type, label)
_NURSE_ROUTE_MAP = {
    'PHARMACY':    ('PHARMACY',          'PHARMACY',   'Pharmacy'),
    'CASHIER':     ('BILLING',           'CASHIER',    'Cashier / Billing'),
    'LAB':         ('LABORATORY',        'LAB',        'Laboratory'),
    'IMAGING':     ('INVESTIGATION',     'INVEST',     'Imaging / Investigations'),
    'OPTICAL':     ('OPTICAL',           'OPTICAL',    'Optical Shop'),
    'COUNSELING':  ('COUNSELING',        'COUNSEL',    'Surgical Counseling'),
    'RETINA':      ('AT_RETINA',         'RETINA',     'Retina Clinic'),
    'GLAUCOMA':    ('AT_GLAUCOMA',       'GLAUC',      'Glaucoma Clinic'),
    'DISCHARGE':   ('COMPLETED',         None,         'Discharge / Done'),
}


@login_required
@require_POST
def nurse_route_patient_view(request, visit_pk):
    """
    Clinic Nurse routes a patient to the next department/service after consultation.
    Works with QMS ON (creates QMS token for destination) and QMS OFF (visit status only).
    """
    user = request.user
    if not (user.can_dispatch_patient() or user.is_medical_director or user.is_super_admin):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)
    destination = request.POST.get('destination', '').upper()

    route = _NURSE_ROUTE_MAP.get(destination)
    if not route:
        return JsonResponse({'error': f'Unknown destination: {destination}'}, status=400)

    new_status, qms_service, label = route

    # Update visit status
    visit.status = new_status
    visit.save(update_fields=['status', 'updated_at'])

    # Complete the current QMS token for this dept (QMS ON only)
    if _qms_active():
        try:
            from apps.qms.models import QueueToken, TokenStatus, IssuancePoint, TIER_PRIORITY, DailyTokenSequence
            dept_code = user.role_department_code or (user.department.code if user.department else None)
            svc_type = _DEPT_TO_QMS_SERVICE.get(dept_code) if dept_code else None
            today = timezone.localdate()

            # Complete the current token for this department
            if svc_type:
                current_token = QueueToken.objects.filter(
                    patient=visit.patient,
                    service_type=svc_type,
                    issued_at__date=today,
                    status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                    is_deleted=False,
                ).first()
                if current_token:
                    current_token.status = TokenStatus.COMPLETED
                    current_token.completed_at = timezone.now()
                    current_token.save(update_fields=['status', 'completed_at', 'updated_at'])

            # Issue a new token for destination service
            if qms_service and visit.patient:
                tier = visit.service_tier
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
                    notes=f'Routed by Nurse {user.get_full_name()} → {label}',
                    issued_by=user,
                )
        except Exception:
            pass

    return JsonResponse({
        'success': True,
        'patient': visit.patient.full_name,
        'destination': label,
        'message': f'{visit.patient.full_name} routed to {label}.',
    })


# ── Diagnosis management (AJAX-friendly POST views) ──────────────────────────

@login_required
@require_POST
def diagnosis_add_view(request, pk):
    """Add a diagnosis to a consultation from the detail page."""
    consultation = get_object_or_404(Consultation, pk=pk, is_deleted=False)
    if consultation.consulting_doctor != request.user and not request.user.is_medical_director:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    diagnosis_id = request.POST.get('diagnosis_id')
    is_primary = request.POST.get('is_primary') == '1'
    laterality = request.POST.get('laterality', 'NA')
    notes = request.POST.get('notes', '').strip()

    if not diagnosis_id:
        messages.error(request, 'No diagnosis selected.')
        return redirect('consultations:detail', pk=pk)

    diagnosis = get_object_or_404(Diagnosis, pk=diagnosis_id, is_active=True)

    # If marking as primary, demote any existing primary
    if is_primary:
        ConsultationDiagnosis.objects.filter(
            consultation=consultation, is_primary=True
        ).update(is_primary=False)

    ConsultationDiagnosis.objects.get_or_create(
        consultation=consultation,
        diagnosis=diagnosis,
        defaults={
            'is_primary': is_primary,
            'laterality': laterality,
            'notes': notes,
        }
    )
    messages.success(request, f'Diagnosis "{diagnosis.description}" added.')
    return redirect('consultations:detail', pk=pk)


@login_required
@require_POST
def diagnosis_remove_view(request, pk, cd_pk):
    """Remove a diagnosis from a consultation."""
    consultation = get_object_or_404(Consultation, pk=pk, is_deleted=False)
    if consultation.consulting_doctor != request.user and not request.user.is_medical_director:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    ConsultationDiagnosis.objects.filter(pk=cd_pk, consultation=consultation).delete()
    messages.success(request, 'Diagnosis removed.')
    return redirect('consultations:detail', pk=pk)
