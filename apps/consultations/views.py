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
    'INVEST':     ['INVEST'],
}


@login_required
def consultation_list_view(request):
    if not request.user.can_create_consultation():
        return HttpResponseForbidden()

    consultations = Consultation.objects.select_related(
        'patient', 'department', 'consulting_doctor'
    ).filter(is_deleted=False)

    # Doctors only see their own; medical director sees all
    if not request.user.is_medical_director:
        consultations = consultations.filter(consulting_doctor=request.user)

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

    # Get or auto-create today's visit — never block the doctor
    visit_id = request.GET.get('visit_id')
    if visit_id:
        visit = get_object_or_404(Visit, pk=visit_id, patient=patient)
    else:
        visit = patient.visits.filter(status__in=['WAITING', 'TRIAGE', 'IN_CONSULTATION']).first()
        if not visit:
            # Auto-create a walk-in visit so the doctor is never blocked
            from apps.core.utils import generate_visit_number
            visit = Visit.objects.create(
                patient=patient,
                visit_type='NEW' if not patient.visits.exists() else 'FOLLOW_UP',
                chief_complaint='Walk-in consultation',
                status='WAITING',
                attending_doctor=request.user,
                department=request.user.department,
                created_by=request.user,
            )
            messages.info(request, f'Visit {visit.visit_number} created automatically.')

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
        form = ConsultationForm(request.POST)
        if form.is_valid():
            consultation = form.save(commit=False)
            consultation.patient = patient
            consultation.visit = visit
            consultation.consulting_doctor = request.user
            consultation.created_by = request.user
            if not consultation.examination_findings:
                consultation.examination_findings = consultation.get_default_examination_template()
            # Save dept_ prefixed exam fields from the same form submission
            dept_data = {
                k[5:]: v.strip()
                for k, v in request.POST.items()
                if k.startswith('dept_') and v.strip()
            }
            if dept_data:
                consultation.department_specific_data = dept_data
            consultation.status = ConsultationStatus.COMPLETED
            consultation.save()
            visit.status = 'IN_CONSULTATION'
            visit.attending_doctor = request.user
            visit.save(update_fields=['status', 'attending_doctor'])

            # Complete the QueueToken so patient leaves this doctor's waiting queue
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
                'LOW_VIS':     ['GENERAL'],
            }
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

            # ── Surgery recommended → auto-create COUNSELING queue token ──────
            surgery_recommended = dept_data.get('surgery_recommended', '') == 'on'
            if surgery_recommended and visit:
                try:
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
                    visit.status = 'COUNSELING'
                    visit.save(update_fields=['status', 'updated_at'])
                    messages.info(request, 'Patient sent to Surgical Counseling queue.')
                except Exception:
                    pass  # Never block the doctor

            messages.success(request, 'Consultation saved and completed.')
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

    return render(request, 'consultations/detail.html', {
        'consultation': consultation,
        'note_form': note_form,
        'departments': Department.get_clinical_departments(),
        'service_types': ServiceType.choices,
        'other_consultations': other_consultations,
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
            c.save()
            messages.success(request, 'Consultation updated.')
            return redirect('consultations:detail', pk=pk)
    else:
        form = ConsultationForm(instance=consultation)

    return render(request, 'consultations/edit.html', {
        'form': form,
        'consultation': consultation,
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
    messages.success(request, 'Consultation marked as completed.')
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
    consultation.updated_by = request.user
    consultation.save(update_fields=['department_specific_data', 'updated_by', 'updated_at'])

    messages.success(request, 'Clinical examination data saved.')
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
    from apps.qms.models import QueueToken, TokenStatus
    waiting_tokens = []
    if dept_code:
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

    # ── Today's consultations for this doctor ──────────────────────────────
    my_consultations = list(
        Consultation.objects.filter(
            consulting_doctor=user,
            consultation_date__date=today,
            is_deleted=False,
        ).select_related('patient', 'department').order_by('-consultation_date')
    )

    # ── Stats ──────────────────────────────────────────────────────────────
    waiting_count = sum(1 for t in waiting_tokens if t.status == TokenStatus.WAITING)
    in_progress_count = sum(1 for t in waiting_tokens if t.status in [TokenStatus.CALLED, TokenStatus.SERVING])
    completed_today = Consultation.objects.filter(
        consulting_doctor=user,
        consultation_date__date=today,
        status=ConsultationStatus.COMPLETED,
        is_deleted=False,
    ).count()

    # ── Patients waiting for doctor that have active visits ──────────────
    # Enrich tokens with visit data for "Start Consultation" links
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
            token.active_visit = active_visits.get(token.patient_id) if token.patient_id else None
            # Tag each token so the template can show NEW vs FOLLOW-UP
            visit = active_visits.get(token.patient_id) if token.patient_id else None
            token.visit_type_label = getattr(visit, 'visit_type', None)

    from apps.qms.models import ServiceType
    return render(request, 'consultations/workstation.html', {
        'waiting_tokens': waiting_tokens,
        'my_consultations': my_consultations,
        'waiting_count': waiting_count,
        'in_progress_count': in_progress_count,
        'completed_today': completed_today,
        'dept': dept,
        'dept_code': dept_code,
        'today': today,
        'service_types': ServiceType.choices,
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
    from apps.qms.models import QueueToken, TokenStatus, ServiceCounter

    # ── Detect nurse's assigned counter and its tiers ─────────────────────────
    assigned_counter = ServiceCounter.objects.filter(
        staff_assigned=request.user, is_active=True
    ).first()

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

    active_statuses = [TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING]

    # ── Standard Parameters queue ─────────────────────────────────────────────
    parameters_queue = []
    if show_mode in ('STANDARD', 'ALL'):
        parameters_queue = list(
            QueueToken.objects.filter(
                issued_at__date=today,
                service_type='PARAMETERS',
                status__in=active_statuses,
                is_deleted=False,
            ).select_related('patient', 'counter').order_by('-priority', 'issued_at')
        )

    # ── VIP / Express Parameters queue ────────────────────────────────────────
    vip_params_queue = []
    if show_mode in ('VIP', 'ALL'):
        vip_params_queue = list(
            QueueToken.objects.filter(
                issued_at__date=today,
                service_type='PARAMS_VIP',
                status__in=active_statuses,
                is_deleted=False,
            ).select_related('patient', 'counter').order_by('-priority', 'issued_at')
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
            token.active_visit = active_visits.get(token.patient_id) if token.patient_id else None

    # ── Nurse's personal stats + history ─────────────────────────────────────
    triaged_visits = Visit.objects.filter(
        visit_date__date=today,
        triage_nurse=request.user,
        is_deleted=False,
    ).select_related('patient').order_by('-visit_date')
    triaged_today = triaged_visits.count()

    # ── Tier breakdown for stats strip ────────────────────────────────────────
    all_today = QueueToken.objects.filter(
        issued_at__date=today,
        service_type__in=['PARAMETERS', 'PARAMS_VIP'],
        is_deleted=False,
    )
    total_standard = all_today.filter(service_type='PARAMETERS').count()
    total_vip_express = all_today.filter(service_type='PARAMS_VIP').count()

    return render(request, 'consultations/triage_workstation.html', {
        'parameters_queue': parameters_queue,
        'vip_params_queue': vip_params_queue,
        'triaged_today': triaged_today,
        'triaged_visits': triaged_visits,
        'today': today,
        'show_mode': show_mode,
        'assigned_counter': assigned_counter,
        'total_standard': total_standard,
        'total_vip_express': total_vip_express,
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
