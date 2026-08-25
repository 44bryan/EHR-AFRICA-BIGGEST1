from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Q
from .models import Consultation, ConsultationDiagnosis, ConsultationNote, Diagnosis, ConsultationStatus
from apps.patients.models import Patient, Visit, VisitStatus
from apps.departments.models import Department
from .forms import ConsultationForm, ConsultationNoteForm, DiagnosisForm
from apps.core.decorators import clinical_staff_required, doctor_required, json_error_handler
from apps.core.context_processors import qms_active as _qms_active

# Maps department code → QMS service types handled by that dept
_DEPT_TO_SERVICE_TYPES = {
    'GEN_OPH':    ['GENERAL', 'VIP_CONSULT', 'EXP_CONSULT', 'INSUR_CONSULT'],
    'RETINA':     ['RETINA'],
    'GLAUC':      ['GLAUCOMA'],
    'PEDS_OPH':   ['PEDIATRIC'],
    'PEDS_REFRAC':['REFRACTION'],
    'REFRAC':     ['REFRACTION'],
    'CORNEA':     ['CORNEA'],
    'OCULOPLASTY':['OCULOPLASTY'],
    'NEURO_OPH':  ['NEURO'],
    'CATARACT':   ['CATARACT'],
    'UVEITIS':    ['UVEITIS'],
    'LOW_VIS':    ['LOW_VISION'],
    'GEN_PHYS':   ['GEN_PHYS', 'GENERAL'],
    'INVEST':     ['INVEST'],
}

# Maps department code → Visit statuses that mean "patient is waiting here" (used when QMS is OFF)
_DEPT_TO_VISIT_STATUSES = {
    'GEN_OPH':     ['WAITING', 'IN_CONSULTATION'],
    'RETINA':      ['AT_RETINA'],
    'GLAUC':       ['AT_GLAUCOMA'],
    'PEDS_OPH':    ['AT_PEDIATRIC'],
    'PEDS_REFRAC': ['REFRACTION'],
    'REFRAC':      ['REFRACTION'],
    'CORNEA':      ['AT_CORNEA'],
    'OCULOPLASTY': ['AT_OCULOPLASTY'],
    'NEURO_OPH':   ['AT_NEURO'],
    'CATARACT':    ['AT_CATARACT'],
    'UVEITIS':     ['UVEITIS'],
    'LOW_VIS':     ['WAITING', 'IN_CONSULTATION'],
    'GEN_PHYS':    ['WAITING', 'IN_CONSULTATION'],
}


@login_required
def consultation_list_view(request):
    user = request.user
    # Roles with read-only access to all consultations (oversight / records)
    _read_only_roles = ('medical_records', 'anaesthetist', 'ceo', 'admin_director', 'super_admin')
    if not user.can_create_consultation() and user.role not in _read_only_roles:
        return HttpResponseForbidden()

    consultations = Consultation.objects.select_related(
        'patient', 'department', 'consulting_doctor', 'visit'
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


def _close_triage_token(patient, today):
    """Close any open PARAMETERS/PARAMS_VIP token when a consultation starts.

    Ensures FT/follow-up patients or direct-access cases don't remain stuck
    on the triage nurse's queue after the doctor has opened a consultation.
    """
    if not _qms_active():
        return
    try:
        from apps.qms.models import QueueToken, TokenStatus
        QueueToken.objects.filter(
            patient=patient,
            token_date=today,
            service_type__in=['PARAMETERS', 'PARAMS_VIP'],
            status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
            is_deleted=False,
        ).update(status=TokenStatus.COMPLETED)
    except Exception:
        pass


@never_cache
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
        visit = patient.visits.filter(
            is_deleted=False,
        ).exclude(
            status__in=['COMPLETED', 'DISCHARGED', 'REGISTERED', 'AT_RECEPTIONIST']
        ).order_by('-visit_date').first()
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

    # ── Resume existing draft: if doctor already saved a draft for this visit, redirect to edit ──
    if visit and request.method == 'GET':
        existing_draft = Consultation.objects.filter(
            patient=patient,
            visit=visit,
            consulting_doctor=request.user,
            status=ConsultationStatus.IN_PROGRESS,
            is_deleted=False,
        ).order_by('-created_at').first()
        if existing_draft:
            messages.info(request, 'Resuming your saved draft consultation.')
            return redirect('consultations:edit', pk=existing_draft.pk)

    # ── Claim mechanic: soft-assign this visit to the doctor's room if it's unclaimed ──
    # Prevents two doctors from opening the same unassigned patient simultaneously.
    try:
        if visit and visit.consultation_room is None:
            from apps.departments.models import ConsultationRoom
            my_room = ConsultationRoom.objects.filter(
                assigned_doctor=request.user, is_active=True
            ).first()
            if my_room:
                visit.consultation_room = my_room
                visit.save(update_fields=['consultation_room'])
    except Exception:
        pass

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

    # Refractionist consultation for THIS visit — used by Gen Oph form to show
    # VA and refraction data as read-only (refractionist's work, not the doctor's)
    refraction_consult = Consultation.objects.filter(
        visit=visit,
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
        if _dept is None:
            from apps.departments.models import Department as _Dept
            _role_code = request.user.role_department_code
            if _role_code:
                _dept = _Dept.objects.filter(code=_role_code).first()

        # ── Draft mode: save minimal record so doctor can order tests first ──
        if request.POST.get('save_mode') == 'draft':
            # Prevent duplicates: reuse an existing IN_PROGRESS consultation for this visit+doctor
            consultation = Consultation.objects.filter(
                patient=patient, visit=visit,
                consulting_doctor=request.user,
                status=ConsultationStatus.IN_PROGRESS,
                is_deleted=False,
            ).first()
            if consultation is None:
                consultation = Consultation.objects.create(
                    patient=patient,
                    visit=visit,
                    department=_dept,
                    consulting_doctor=request.user,
                    status=ConsultationStatus.IN_PROGRESS,
                    created_by=request.user,
                )
            consultation.presenting_complaint = ', '.join(filter(None, request.POST.getlist('presenting_complaint')))
            consultation.history_of_presenting_complaint = ', '.join(filter(None, request.POST.getlist('history_of_presenting_complaint')))
            consultation.ocular_history = ', '.join(filter(None, request.POST.getlist('ocular_history')))
            consultation.systemic_history = ', '.join(filter(None, request.POST.getlist('systemic_history')))
            consultation.drug_history = ', '.join(filter(None, request.POST.getlist('drug_history')))
            consultation.save()
            visit.status = 'IN_CONSULTATION'
            visit.attending_doctor = request.user
            visit.save(update_fields=['status', 'attending_doctor'])
            _close_triage_token(patient, today=timezone.localdate())
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

            # Prevent duplicates: reuse existing IN_PROGRESS consultation for this visit+doctor
            # (same guard as draft mode and autosave — without this, autosave+full-submit creates two records)
            _existing_draft = Consultation.objects.filter(
                patient=patient, visit=visit,
                consulting_doctor=request.user,
                status=ConsultationStatus.IN_PROGRESS,
                is_deleted=False,
            ).first()
            if _existing_draft:
                # Switch to the DB-fetched object so auto_now_add fields
                # (created_at, consultation_date) are already set and kept.
                # Copy every non-PK, non-auto_now_add field from the form object.
                _orig_creator = _existing_draft.created_by
                for _f in consultation._meta.concrete_fields:
                    if _f.primary_key or getattr(_f, 'auto_now_add', False):
                        continue
                    setattr(_existing_draft, _f.attname, getattr(consultation, _f.attname))
                _existing_draft.created_by = _orig_creator  # keep original creator
                consultation = _existing_draft  # all subsequent assignments land here

            # Save dept_ prefixed exam fields from the same form submission
            dept_data = {
                k[5:]: ', '.join(filter(None, [v.strip() for v in request.POST.getlist(k)]))
                for k in request.POST
                if k.startswith('dept_') and any(v.strip() for v in request.POST.getlist(k))
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
            _close_triage_token(patient, today=timezone.localdate())

            # ── When refraction saves VA, push it back to visit.vital_signs ──
            # So VA is visible in the nurse strip, patient record, and everywhere.
            _dept_code = consultation.department.code if consultation.department else ''
            if _dept_code in ('REFRAC', 'PEDS_REFRAC'):
                _va_r = (dept_data.get('va_unaided_od') or dept_data.get('va_re_unaided') or
                         dept_data.get('sub_va_dist_od') or '')
                _va_l = (dept_data.get('va_unaided_os') or dept_data.get('va_le_unaided') or
                         dept_data.get('sub_va_dist_os') or '')
                _bcva_r = dept_data.get('va_corrected_od') or dept_data.get('sub_va_dist_od') or ''
                _bcva_l = dept_data.get('va_corrected_os') or dept_data.get('sub_va_dist_os') or ''
                _iop_r  = dept_data.get('iop_re') or dept_data.get('iop_od') or ''
                _iop_l  = dept_data.get('iop_le') or dept_data.get('iop_os') or ''
                _vs = dict(visit.vital_signs or {})
                if _va_r:
                    _vs['visual_acuity_right'] = _va_r
                if _va_l:
                    _vs['visual_acuity_left'] = _va_l
                if _bcva_r:
                    _vs['va_bcva_right'] = _bcva_r
                if _bcva_l:
                    _vs['va_bcva_left'] = _bcva_l
                if _iop_r:
                    _vs['intraocular_pressure_right'] = _iop_r
                if _iop_l:
                    _vs['intraocular_pressure_left'] = _iop_l
                visit.vital_signs = _vs
                visit.save(update_fields=['vital_signs', 'updated_at'])

            # ── GP pre-op clearance → write back to SurgicalBooking ────────────
            preop_clearance = dept_data.get('preop_clearance_status', '')
            if preop_clearance and visit:
                try:
                    from apps.ipd.models import SurgicalBooking
                    booking = SurgicalBooking.objects.filter(
                        patient=patient, is_deleted=False
                    ).exclude(status__in=['COMPLETED', 'CANCELLED']).order_by('-surgery_date').first()
                    if booking:
                        clearance_notes = dept_data.get('preop_clearance_notes', '')
                        clearance_date = dept_data.get('preop_clearance_valid_until', '')
                        booking.pre_op_requirements = (
                            f'[GP CLEARANCE: {preop_clearance}]\n'
                            f'{clearance_notes}\n'
                            f'Cleared by: Dr. {request.user.get_full_name()} on {consultation.consultation_date.strftime("%d/%m/%Y")}'
                            + (f'\nValid until: {clearance_date}' if clearance_date else '')
                        )
                        booking.save(update_fields=['pre_op_requirements', 'updated_at'])
                        messages.info(request, f'Pre-op clearance ({preop_clearance}) written to surgical booking {booking.booking_number}.')
                except Exception:
                    pass

            # ── Glasses/Contact Rx → auto-route to OPTICAL ──────────────────
            mgmt = dept_data.get('management_plan', '')
            has_glasses_rx = (
                'Prescribe corrective glasses' in mgmt or
                'Prescribe contact lenses' in mgmt or
                dept_data.get('sub_sph_dist_od') or dept_data.get('sub_sph_dist_os') or
                dept_data.get('final_sph_od') or dept_data.get('final_sph_os')
            )
            if has_glasses_rx and visit:
                try:
                    skip_opt = {'OPTICAL', 'BILLING', 'COMPLETED', 'DISCHARGED',
                                'COUNSELING', 'ADMITTED', 'IN_THEATRE'}
                    if visit.status not in skip_opt:
                        from apps.departments.models import Department as _Dept2
                        from apps.core.patient_flow import close_stage_token as _close_opt
                        _close_opt(visit.patient, prev_status=visit.status)
                        opt_dept = _Dept2.objects.filter(code='OPTICAL', is_active=True).first()
                        visit.status = 'OPTICAL'
                        _upd = ['status', 'updated_at']
                        if opt_dept:
                            visit.department = opt_dept
                            _upd.append('department')
                        visit.save(update_fields=_upd)
                        if _qms_active():
                            from apps.qms.models import (
                                QueueToken, DailyTokenSequence, IssuancePoint,
                                TokenStatus, TIER_PRIORITY,
                            )
                            from django.db import transaction as _opt_tx
                            tier = visit.service_tier or 'STANDARD'
                            with _opt_tx.atomic():
                                token_number = DailyTokenSequence.next_dept_token('OPTICAL')
                                QueueToken.objects.create(
                                    token_number=token_number,
                                    service_type='OPTICAL',
                                    patient=patient,
                                    visit=visit,
                                    service_tier=tier,
                                    issuance_point=IssuancePoint.SYSTEM,
                                    priority=TIER_PRIORITY.get(tier, 0),
                                    status=TokenStatus.WAITING,
                                    notes=f'Glasses Rx by Dr. {request.user.get_full_name()}',
                                    created_by=request.user,
                                )
                        messages.info(request, 'Glasses prescription detected — patient sent to Optical queue.')
                except Exception:
                    pass  # Never block the doctor

            # ── Surgery recommended → auto-create COUNSELING queue token ──────
            surgery_recommended = dept_data.get('surgery_recommended', '') == 'on'
            if surgery_recommended and visit:
                try:
                    if _qms_active():
                        from apps.qms.models import (
                            QueueToken, DailyTokenSequence, IssuancePoint,
                            TokenStatus, TIER_PRIORITY,
                        )
                        from django.db import transaction as _couns_tx
                        tier = visit.service_tier or 'STANDARD'
                        with _couns_tx.atomic():
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

            # ── Referral department set → route patient to that department ────
            if consultation.referral_department and visit:
                try:
                    ref_dept = consultation.referral_department
                    skip_ref = {'COMPLETED', 'DISCHARGED'}
                    if visit.status not in skip_ref:
                        # Map department code → QMS service type
                        _REF_SVC = {
                            'RETINA':    'RETINA',
                            'GLAUCOMA':  'GLAUCOMA',
                            'CORNEA':    'CORNEA',
                            'ORBIT':     'ORBIT',
                            'PEDIATRIC': 'GEN_OPH',
                            'NEURO_OPH': 'GEN_OPH',
                            'OCULOPLASTY': 'GEN_OPH',
                            'LOW_VISION': 'GEN_OPH',
                            'GEN_MED':   'GENERAL',
                            'REFRAC':    'REFRAC',
                            'OPTICAL':   'OPTICAL',
                        }
                        svc = _REF_SVC.get(ref_dept.code, 'GENERAL')
                        visit.department = ref_dept
                        visit.status = ref_dept.code if ref_dept.code in (
                            'RETINA', 'GLAUCOMA', 'OPTICAL', 'REFRAC', 'CORNEA',
                            'ORBIT', 'COUNSELING', 'PHARMACY', 'LAB',
                        ) else 'WAITING'
                        visit.save(update_fields=['department', 'status', 'updated_at'])
                        if _qms_active():
                            from apps.qms.models import (
                                QueueToken, DailyTokenSequence, IssuancePoint,
                                TokenStatus, TIER_PRIORITY,
                            )
                            from django.db import transaction as _ref_tx
                            tier = visit.service_tier or 'STANDARD'
                            with _ref_tx.atomic():
                                token_number = DailyTokenSequence.next_dept_token(svc)
                                QueueToken.objects.create(
                                    token_number=token_number,
                                    service_type=svc,
                                    patient=patient,
                                    visit=visit,
                                    service_tier=tier,
                                    issuance_point=IssuancePoint.SYSTEM,
                                    priority=TIER_PRIORITY.get(tier, 0),
                                    status=TokenStatus.WAITING,
                                    notes=(
                                        f'Referred by Dr. {request.user.get_full_name()} '
                                        f'({consultation.department.name if consultation.department else ""})'
                                        + (f': {consultation.referral_reason[:120]}' if consultation.referral_reason else '')
                                    ),
                                    created_by=request.user,
                                )
                        messages.info(
                            request,
                            f'Patient referred and routed to {ref_dept.name}.'
                        )
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

            messages.success(request, 'Consultation saved. Review and click Complete when ready.')
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
        'can_do_refraction': getattr(request.user, 'can_do_refraction', False),
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

    try:
        from apps.patients.models import ChronicMedication
        patient_medications = list(
            ChronicMedication.objects.filter(patient=consultation.patient, is_active=True)
        )
    except Exception:
        patient_medications = []

    # Active rooms for Room Board modal — all rooms with a doctor checked in today
    from apps.departments.models import ConsultationRoom as _DetailRoom
    from django.db.models import Count, Q as _DQ
    try:
        active_rooms = list(
            _DetailRoom.objects.filter(is_active=True, assigned_doctor__isnull=False)
            .select_related('assigned_doctor', 'department')
            .annotate(
                waiting_count=Count(
                    'assigned_doctor__attended_visits',
                    filter=_DQ(assigned_doctor__attended_visits__status='WAITING'),
                )
            )
            .order_by('department__name', 'room_number')
        )
    except Exception:
        active_rooms = []

    # Procedure records for this consultation
    from .models import ProcedureRecord
    procedures = list(
        ProcedureRecord.objects.filter(consultation=consultation, is_deleted=False)
        .select_related('performed_by').order_by('-procedure_date', '-created_at')
    )

    # Previous consultations for the patient — shown in Patient Record tab
    prev_consultations = list(
        Consultation.objects.filter(
            patient=consultation.patient,
            is_deleted=False,
            status=ConsultationStatus.COMPLETED,
        ).exclude(pk=consultation.pk).select_related('department', 'consulting_doctor')
        .order_by('-consultation_date')[:8]
    )

    return render(request, 'consultations/detail.html', {
        'consultation': consultation,
        'note_form': note_form,
        'departments': Department.get_clinical_departments(),
        'service_types': ServiceType.choices,
        'other_consultations': other_consultations,
        'patient_allergies': patient_allergies,
        'patient_medications': patient_medications,
        'visit': consultation.visit,
        'patient': consultation.patient,
        'active_rooms': active_rooms,
        'procedures': procedures,
        'prev_consultations': prev_consultations,
        'procedure_types': ProcedureRecord.ProcedureType.choices,
        'surgical_requests': list(consultation.surgical_requests.filter(is_deleted=False).select_related('requested_by').order_by('-created_at')),
        'surgery_types': __import__('apps.consultations.models', fromlist=['SurgicalRequest']).SurgicalRequest.SurgeryType.choices,
    })


@never_cache
@login_required
def consultation_edit_view(request, pk):
    consultation = get_object_or_404(Consultation, pk=pk, is_deleted=False)

    # Only the consulting doctor, medical director, or super admin can edit
    can_edit = (
        consultation.consulting_doctor == request.user or
        request.user.is_medical_director or
        request.user.is_super_admin
    )
    if not can_edit:
        messages.error(request, 'You can only edit your own consultation notes.')
        return redirect('consultations:detail', pk=pk)

    if consultation.status == ConsultationStatus.COMPLETED and not (
        request.user.is_medical_director or
        consultation.consulting_doctor == request.user
    ):
        messages.error(request, 'Completed consultations cannot be edited.')
        return redirect('consultations:detail', pk=pk)

    if request.method == 'POST':
        form = ConsultationForm(request.POST, instance=consultation)
        if form.is_valid():
            c = form.save(commit=False)
            c.updated_by = request.user
            # Also persist any dept_ exam fields submitted alongside
            dept_data = {
                k[5:]: ', '.join(filter(None, [v.strip() for v in request.POST.getlist(k)]))
                for k in request.POST
                if k.startswith('dept_') and any(v.strip() for v in request.POST.getlist(k))
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

            # ── Push refraction VA back to visit.vital_signs on edit too ────
            if dept_data:
                _dept_code2 = c.department.code if c.department else ''
                if _dept_code2 in ('REFRAC', 'PEDS_REFRAC') and c.visit:
                    _vst = c.visit
                    _va_r2 = (dept_data.get('va_unaided_od') or dept_data.get('va_re_unaided') or
                              dept_data.get('sub_va_dist_od') or '')
                    _va_l2 = (dept_data.get('va_unaided_os') or dept_data.get('va_le_unaided') or
                              dept_data.get('sub_va_dist_os') or '')
                    _bcva_r2 = dept_data.get('va_corrected_od') or dept_data.get('sub_va_dist_od') or ''
                    _bcva_l2 = dept_data.get('va_corrected_os') or dept_data.get('sub_va_dist_os') or ''
                    _vs2 = dict(_vst.vital_signs or {})
                    if _va_r2:
                        _vs2['visual_acuity_right'] = _va_r2
                    if _va_l2:
                        _vs2['visual_acuity_left'] = _va_l2
                    if _bcva_r2:
                        _vs2['va_bcva_right'] = _bcva_r2
                    if _bcva_l2:
                        _vs2['va_bcva_left'] = _bcva_l2
                    _vst.vital_signs = _vs2
                    _vst.save(update_fields=['vital_signs', 'updated_at'])

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

    # Most recent refractionist consultation for this patient — shown as read-only grey section
    refraction_consult = Consultation.objects.filter(
        patient=consultation.patient,
        is_deleted=False,
        department__code__in=['REFRAC', 'PEDS_REFRAC'],
    ).select_related('department', 'consulting_doctor').order_by('-consultation_date').first()
    refraction_data = refraction_consult.department_specific_data if refraction_consult else {}

    return render(request, 'consultations/edit.html', {
        'form': form,
        'consultation': consultation,
        'investigation_data': investigation_data,
        'investigation_orders': investigation_orders,
        'is_resuming': consultation.status == ConsultationStatus.IN_PROGRESS,
        'refraction_consult': refraction_consult,
        'refraction_data': refraction_data,
        'can_do_refraction': getattr(request.user, 'can_do_refraction', False),
    })


@login_required
@require_POST
def consultation_complete_view(request, pk):
    consultation = get_object_or_404(Consultation, pk=pk)
    if consultation.consulting_doctor != request.user and not request.user.is_medical_director:
        return HttpResponseForbidden()
    # Idempotency guard — already completed/referred, just redirect
    if consultation.status in (ConsultationStatus.COMPLETED, ConsultationStatus.REFERRED):
        return redirect('consultations:detail', pk=consultation.pk)
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
            'PEDS_REFRAC': ['REFRACTION'],
            'REFRAC':      ['REFRACTION'],
            'CORNEA':      ['CORNEA'],
            'OCULOPLASTY': ['OCULOPLASTY'],
            'NEURO_OPH':   ['NEURO'],
            'CATARACT':    ['CATARACT'],
            'UVEITIS':     ['UVEITIS'],
            'LOW_VIS':     ['LOW_VISION'],
            'GEN_PHYS':    ['GEN_PHYS', 'GENERAL'],
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

    # Route patient to next destination if selected by the doctor
    next_dest = request.POST.get('next_destination', '').strip().upper()
    _route_counter_id = request.POST.get('counter_id', '').strip() or None
    _route_room_id = request.POST.get('room_id', '').strip() or None
    if next_dest and visit:
        routed, label = _inline_route_visit(visit, next_dest, request.user, room_id=_route_room_id, counter_id=_route_counter_id)
        if routed:
            messages.success(request, f'Consultation complete — patient sent to {label}.')
        else:
            messages.success(request, 'Consultation marked as completed.')
    else:
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
def consultation_delete_view(request, pk):
    """Soft-delete a consultation so the doctor can start fresh."""
    consultation = get_object_or_404(Consultation, pk=pk, is_deleted=False)
    # Only the consulting doctor, medical director, or super admin can delete
    if (consultation.consulting_doctor != request.user
            and not request.user.is_medical_director
            and not request.user.is_super_admin):
        messages.error(request, 'You do not have permission to delete this consultation.')
        return redirect('consultations:detail', pk=pk)
    patient_id = consultation.patient.patient_id
    consultation.is_deleted = True
    consultation.save(update_fields=['is_deleted'])
    messages.success(request, 'Consultation deleted. You can start a new one.')
    return redirect('patients:detail', patient_id=patient_id)


@json_error_handler
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

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    messages.success(request, 'Clinical examination data saved.')
    return redirect('consultations:detail', pk=pk)


@login_required
@require_POST
def consultation_autosave_view(request):
    """
    AJAX endpoint — creates or updates a draft Consultation without closing the form.
    Called by section Save Draft buttons on the create form.

    POST params:
        patient_id  — patient's string ID (e.g. EHR-0001)
        visit_id    — Visit UUID (optional)
        draft_pk    — existing draft UUID (if returning to update)
        _section    — 'history' | 'clinical' (determines which fields to save)
    Returns: {ok: true, pk: "<uuid>"}
    Always returns JSON — never HTML 404/500.
    """
    try:
        patient_id = request.POST.get('patient_id', '').strip()
        visit_id   = request.POST.get('visit_id', '').strip()
        draft_pk   = request.POST.get('draft_pk', '').strip()
        section    = request.POST.get('_section', 'history')

        if draft_pk:
            consultation = Consultation.objects.filter(
                pk=draft_pk, consulting_doctor=request.user,
                status=ConsultationStatus.IN_PROGRESS, is_deleted=False
            ).first()
            if consultation is None:
                return JsonResponse({'ok': False, 'error': 'Draft not found or already completed.'}, status=404)
        else:
            if not patient_id:
                return JsonResponse({'ok': False, 'error': 'patient_id required'}, status=400)
            patient = Patient.objects.filter(patient_id=patient_id, is_deleted=False).first()
            if patient is None:
                return JsonResponse({'ok': False, 'error': 'Patient not found.'}, status=404)
            visit = None
            if visit_id:
                visit = Visit.objects.filter(pk=visit_id, is_deleted=False).first()
                if visit is None:
                    return JsonResponse({'ok': False, 'error': 'Visit not found.'}, status=404)

            _dept = request.user.department
            if _dept is None:
                from apps.departments.models import Department as _Dept
                _role_code = request.user.role_department_code
                if _role_code:
                    _dept = _Dept.objects.filter(code=_role_code).first()

            # Reuse existing IN_PROGRESS draft for this patient+visit+doctor rather than creating duplicates
            consultation = Consultation.objects.filter(
                patient=patient, visit=visit,
                consulting_doctor=request.user,
                status=ConsultationStatus.IN_PROGRESS,
                is_deleted=False,
            ).first()
            if consultation is None:
                consultation = Consultation.objects.create(
                    patient=patient,
                    visit=visit,
                    department=_dept,
                    consulting_doctor=request.user,
                    presenting_complaint=', '.join(filter(None, request.POST.getlist('presenting_complaint'))),
                    status=ConsultationStatus.IN_PROGRESS,
                    created_by=request.user,
                )
            if visit and visit.status not in ('IN_CONSULTATION', 'COMPLETED', 'DISCHARGED'):
                visit.status = 'IN_CONSULTATION'
                visit.attending_doctor = request.user
                visit.save(update_fields=['status', 'attending_doctor', 'updated_at'])
                _close_triage_token(patient, today=timezone.localdate())

        # Save history fields
        if section == 'history':
            history_fields = [
                'presenting_complaint', 'history_of_presenting_complaint',
                'ocular_history', 'systemic_history', 'drug_history',
                'family_history', 'social_history',
            ]
            changed = ['updated_by', 'updated_at']
            for f in history_fields:
                val = ', '.join(filter(None, request.POST.getlist(f)))
                if val:
                    setattr(consultation, f, val)
                    changed.append(f)
            consultation.updated_by = request.user
            consultation.save(update_fields=changed)

        # Save clinical dept_ fields
        elif section == 'clinical':
            dept_data = {
                k[5:]: v.strip()
                for k, v in request.POST.items()
                if k.startswith('dept_') and v.strip()
            }
            existing = consultation.department_specific_data or {}
            existing.update(dept_data)
            consultation.department_specific_data = existing
            consultation.updated_by = request.user
            consultation.save(update_fields=['department_specific_data', 'updated_by', 'updated_at'])

        return JsonResponse({'ok': True, 'pk': str(consultation.pk)})

    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception('consultation_autosave_view error')
        return JsonResponse({'ok': False, 'error': str(exc) or 'Server error during autosave.'}, status=500)


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
    queue_filter = request.GET.get('queue', '').upper()  # VIP|GENERAL|ALL|''
    _refrac_counter = None  # populated below for REFRAC/PEDS_REFRAC dept

    if _qms_active() and dept_code:
        try:
            from apps.qms.models import QueueToken, TokenStatus
            service_types = _DEPT_TO_SERVICE_TYPES.get(dept_code, [])
            # GEN_OPH doctors: support queue toggle (?queue=VIP|GENERAL|ALL)
            # falling back to their consultation_unit setting if no override
            if dept_code == 'GEN_OPH':
                if queue_filter == 'VIP':
                    service_types = ['VIP_CONSULT']
                elif queue_filter == 'GENERAL':
                    service_types = ['GENERAL']
                elif queue_filter == 'ALL':
                    service_types = ['GENERAL', 'VIP_CONSULT', 'EXP_CONSULT', 'INSUR_CONSULT']
                else:
                    _cu = (getattr(user, 'consultation_unit', '') or 'GENERAL').upper()
                    _unit_svc_map = {
                        'GENERAL':       ['GENERAL'],
                        'EXP_CONSULT':   ['EXP_CONSULT'],
                        'EXPRESS':       ['EXP_CONSULT'],   # legacy alias
                        'VIP_CONSULT':   ['VIP_CONSULT'],
                        'VIP':           ['VIP_CONSULT'],   # legacy alias
                        'INSUR_CONSULT': ['INSUR_CONSULT'],
                        'INSURANCE':     ['INSUR_CONSULT'],  # legacy alias
                        'ALL':           ['GENERAL', 'VIP_CONSULT', 'EXP_CONSULT', 'INSUR_CONSULT'],
                    }
                    service_types = _unit_svc_map.get(_cu, ['GENERAL'])
                # VIP doctor with can_do_refraction also sees REFRACTION queue
                if getattr(user, 'can_do_refraction', False) and 'REFRACTION' not in service_types:
                    service_types = service_types + ['REFRACTION']
            if service_types:
                from django.db.models import Q as _Q
                # Both assigned-doctor tokens AND pool tokens must match this doctor's
                # service_type list — prevents VIP tokens leaking into Express queues
                # and vice versa even when a doctor was explicitly assigned
                _token_qs = QueueToken.objects.filter(
                    _Q(assigned_doctor=user) |
                    _Q(assigned_doctor__isnull=True),
                    service_type__in=service_types,
                    token_date=today,
                    status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                    is_deleted=False,
                )
                # ── Tier filter per department ────────────────────────────
                if dept_code == 'GEN_OPH':
                    pass  # already narrowed above via service_types
                elif dept_code in ('REFRAC', 'PEDS_REFRAC'):
                    # Refractionist: only filter by tier when the counter EXPLICITLY
                    # restricts to specific tiers. Blank serves_tiers = all tiers,
                    # so both VIP and Standard patients are visible.
                    _refrac_counter = None
                    try:
                        from apps.qms.models import ServiceCounter as _SC
                        _refrac_counter = _SC.objects.filter(
                            staff_assigned=user, is_active=True
                        ).first()
                    except Exception:
                        pass
                    if _refrac_counter and _refrac_counter.serves_tiers:
                        # Counter has an explicit tier restriction — honour it
                        _ctiers = _refrac_counter.get_serves_tiers()
                        if len(_ctiers) == 1 and _ctiers[0] == 'VIP':
                            _token_qs = _token_qs.filter(service_tier='VIP')
                        elif len(_ctiers) == 1 and _ctiers[0] == 'STANDARD':
                            _token_qs = _token_qs.filter(service_tier='STANDARD')
                        elif len(_ctiers) == 1 and _ctiers[0] in ('EXPRESS', 'FAST_TRACK'):
                            _token_qs = _token_qs.filter(service_tier__in=['EXPRESS', 'FAST_TRACK'])
                        elif 'VIP' not in _ctiers:
                            _token_qs = _token_qs.exclude(service_tier='VIP')
                        elif 'STANDARD' not in _ctiers:
                            _token_qs = _token_qs.exclude(service_tier='STANDARD')
                    # else: no explicit tier restriction → show all refraction tokens
                else:
                    # All other departments: respect patient_tier on account
                    _pt = getattr(user, 'patient_tier', '') or ''
                    if _pt == 'VIP':
                        _token_qs = _token_qs.filter(service_tier='VIP')
                    else:
                        # Default (STANDARD or unset): never show VIP patients
                        _token_qs = _token_qs.exclude(service_tier='VIP')
                waiting_tokens = list(
                    _token_qs.select_related('patient', 'counter', 'assigned_doctor')
                    .order_by('-priority', 'issued_at')
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
        elif dept_code:
            # Department FK not set on account — fall back to role-based code
            qs = qs.filter(department__code=dept_code)
        else:
            # No department information at all — show nothing to avoid leaking all patients
            qs = qs.none()
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
                is_deleted=False,
            ).exclude(
                status__in=[VisitStatus.COMPLETED, VisitStatus.DISCHARGED]
            ).select_related('consultation_room', 'referring_doctor').order_by('-visit_date')
        }
        for token in waiting_tokens:
            _v = active_visits.get(token.patient_id) if token.patient_id else None
            token.ws_visit = _v
            token.ws_visit_type = getattr(_v, 'visit_type', None)

        # Detect existing IN_PROGRESS drafts by THIS doctor for each visit
        # so the workstation can show "Resume" instead of creating a new consultation.
        _visit_ids = [t.ws_visit.pk for t in waiting_tokens if getattr(t, 'ws_visit', None)]
        if _visit_ids:
            _drafts = {
                c.visit_id: c
                for c in Consultation.objects.filter(
                    consulting_doctor=user,
                    visit_id__in=_visit_ids,
                    status=ConsultationStatus.IN_PROGRESS,
                    is_deleted=False,
                ).only('id', 'visit_id', 'status')
            }
            for token in waiting_tokens:
                if getattr(token, 'ws_visit', None):
                    token.ws_draft = _drafts.get(token.ws_visit.pk)

    # ── Room filtering ────────────────────────────────────────────────────
    # Doctor can filter to their room only, or view all dept patients
    dept_rooms = []
    my_assigned_room = None
    selected_room = None

    if dept:
        from apps.departments.models import ConsultationRoom
        dept_rooms = list(
            ConsultationRoom.objects.filter(
                department=dept, is_active=True
            ).select_related('assigned_doctor').order_by('room_number')
        )
        # Room the doctor is currently assigned to today
        my_assigned_room = next((r for r in dept_rooms if r.assigned_doctor_id == user.pk), None)

    # URL param: ?room_id=<id> or ?room_id=all (show all dept patients)
    room_id_param = request.GET.get('room_id', '').strip()
    if room_id_param == 'all':
        selected_room = None  # Show all
    elif room_id_param:
        try:
            selected_room = next((r for r in dept_rooms if str(r.id) == room_id_param), None)
        except Exception:
            selected_room = None
    else:
        # Default: doctor's assigned room (if any), otherwise all
        selected_room = my_assigned_room

    # ── QMS counter-based room filter (new system) ─────────────────────────
    # When QMS is active, filter by token.counter (ServiceCounter) if the doctor
    # is checked into a room today. Tokens with no counter are visible to all.
    _ws_checked_in_counter = None
    if _qms_active():
        try:
            from apps.qms.models import ServiceCounter as _SC
            _ws_checked_in_counter = _SC.objects.filter(
                staff_assigned=user, checked_in_date=today, is_active=True
            ).first()
        except Exception:
            pass

    # Apply room/counter filter to queue.
    # Rule: a token dispatched to a specific counter belongs to that counter's doctor.
    #   - Doctor IS checked into counter X  → see their counter's tokens + pool tokens (no counter)
    #   - Doctor is NOT in any counter       → see pool tokens + tokens from unoccupied counters
    #     (prevents routed tokens leaking into ALL doctors' workstations)
    if _qms_active():
        if _ws_checked_in_counter:
            # I am in counter X — show only my counter's tokens + unassigned pool tokens
            waiting_tokens = [
                t for t in waiting_tokens
                if (
                    getattr(t, 'counter_id', None) is None
                    or getattr(t, 'counter_id', None) == _ws_checked_in_counter.id
                )
            ]
        else:
            # I am not checked into any counter — only see pool tokens (no counter)
            # and tokens from counters that have no active doctor today (fallback / orphan tokens)
            waiting_tokens = [
                t for t in waiting_tokens
                if (
                    getattr(t, 'counter_id', None) is None
                    or not (t.counter and t.counter.is_checked_in_today)
                )
            ]
    elif selected_room:
        # QMS OFF: filter by legacy ConsultationRoom assignment
        waiting_visits = [
            v for v in waiting_visits
            if (
                getattr(v, 'consultation_room_id', None) is None
                or getattr(v, 'consultation_room_id', None) == selected_room.id
            )
        ]

    # Recompute stats after any room/counter filter
    if _qms_active():
        waiting_count = sum(1 for t in waiting_tokens if t.status == 'WAITING')
        in_progress_count = sum(1 for t in waiting_tokens if t.status in ('CALLED', 'SERVING'))
    else:
        waiting_count = sum(1 for v in waiting_visits if v.status not in ('IN_CONSULTATION',))
        in_progress_count = sum(1 for v in waiting_visits if v.status == 'IN_CONSULTATION')

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

    # Consultations this doctor completed today where visit is still IN_CONSULTATION
    # (patient needs to be routed to next destination)
    _completed_ids = [c.id for c in my_consultations if c.status == ConsultationStatus.COMPLETED]
    if _completed_ids:
        _c_visit_ids = list(
            Consultation.objects.filter(id__in=_completed_ids).values_list('visit_id', flat=True)
        )
        ready_to_route_doctor = list(
            Visit.objects.filter(
                id__in=_c_visit_ids,
                status='IN_CONSULTATION',
                is_deleted=False,
            ).select_related('patient', 'attending_doctor')
        )
    else:
        ready_to_route_doctor = []

    # ── Active counters for routing picker ────────────────────────────────────
    # Show QMS counters checked in today so doctor can route patient to a specific doctor
    active_counters = []
    if _qms_active():
        try:
            from apps.qms.models import ServiceCounter as _SC_WS
            _consult_types = [
                'GENERAL', 'EXP_CONSULT', 'VIP_CONSULT', 'REFRACTION', 'GLAUCOMA',
                'RETINA', 'CORNEA', 'NEURO', 'CATARACT', 'UVEITIS', 'OCULOPLASTY',
                'PEDIATRIC', 'LOW_VISION', 'GEN_PHYS', 'INSUR_CONSULT',
            ]
            active_counters = list(
                _SC_WS.objects.filter(
                    service_type__in=_consult_types,
                    is_active=True,
                    checked_in_date=today,
                ).select_related('staff_assigned').order_by('service_type', 'name')
            )
        except Exception:
            pass

    # ── Incoming referrals to this doctor's department ───────────────────────
    # Consultations from another doctor that set referral_department = this dept
    incoming_referrals = []
    if dept:
        incoming_referrals = list(
            Consultation.objects.filter(
                referral_department=dept,
                is_deleted=False,
                visit__is_deleted=False,
            ).exclude(
                visit__status__in=['COMPLETED', 'DISCHARGED']
            ).select_related(
                'patient', 'consulting_doctor', 'department', 'visit'
            ).prefetch_related(
                'consultation_diagnoses__diagnosis'
            ).order_by('-consultation_date')[:15]
        )

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
        'dept_rooms': dept_rooms,
        'my_assigned_room': my_assigned_room,
        'selected_room': selected_room,
        'queue_filter': queue_filter if dept_code == 'GEN_OPH' else '',
        'is_refrac': dept_code in ('REFRAC', 'PEDS_REFRAC'),
        'can_do_refraction': getattr(user, 'can_do_refraction', False),
        'refrac_counter': _refrac_counter if dept_code in ('REFRAC', 'PEDS_REFRAC') else None,
        'checked_in_counter': _ws_checked_in_counter,
        'my_counter_id': _ws_checked_in_counter.id if _ws_checked_in_counter else None,
        'ready_to_route_doctor': ready_to_route_doctor,
        'incoming_referrals': incoming_referrals,
        'active_counters': active_counters,
    })


# ── Reject & Re-route (specialist sends patient back — wrong dept) ────────────

@login_required
@require_POST
def reject_and_reroute_view(request):
    """
    Specialist rejects a patient (wrong department) WITHOUT opening a consultation.
    Routes back to:
      destination='referring_doctor' → the doctor who originally sent the patient
      destination='triage'           → OPD nurse / triage queue
    POST params: visit_id, destination, reason (optional)
    """
    from apps.patients.models import Visit as _Visit
    from django.utils import timezone as _tz

    visit_id    = request.POST.get('visit_id', '').strip()
    destination = request.POST.get('destination', 'referring_doctor')
    reason      = request.POST.get('reason', '').strip()

    if not visit_id:
        return JsonResponse({'success': False, 'message': 'visit_id required'}, status=400)

    visit = get_object_or_404(_Visit, id=visit_id, is_deleted=False)

    rejector_name = request.user.get_full_name() or request.user.username
    dept_name     = request.user.department.name if request.user.department else ''
    note          = f'Rejected by Dr. {rejector_name}'
    if dept_name:
        note += f' ({dept_name})'
    if reason:
        note += f' — {reason}'

    referring_doc = visit.referring_doctor if destination == 'referring_doctor' else None
    # If no referring doctor on record, fall back to triage
    if destination == 'referring_doctor' and not referring_doc:
        destination = 'triage'

    if not _qms_active():
        visit.status = 'WAITING'
        visit.referring_doctor = None
        visit.save(update_fields=['status', 'referring_doctor', 'updated_at'])
        return JsonResponse({'success': True, 'message': f'Patient re-routed. {note}.'})

    from apps.qms.models import (
        QueueToken, DailyTokenSequence, IssuancePoint,
        TokenStatus, TIER_PRIORITY, ServiceTier,
    )
    from django.db import transaction

    tier  = visit.service_tier or ServiceTier.STANDARD
    today = _tz.localdate()

    # --- Determine target service type ---
    if referring_doc:
        _ROLE_SVC = {
            'ophthalmologist':           'GENERAL',
            'intern':                    'GENERAL',
            'retina_specialist':         'RETINA',
            'glaucoma_specialist':       'GLAUCOMA',
            'pediatric_ophthalmologist': 'PEDIATRIC',
            'cataract_surgeon':          'CATARACT',
            'cornea_specialist':         'CORNEA',
            'oculoplastics_surgeon':     'OCULOPLASTY',
            'neuro_ophthalmologist':     'NEURO',
            'uveitis_specialist':        'UVEITIS',
            'low_vision_specialist':     'LOW_VISION',
            'medical_director':          'GENERAL',
            'general_physician':         'GEN_PHYS',
        }
        target_service  = _ROLE_SVC.get(referring_doc.role, 'GENERAL')
        assigned_doctor = referring_doc
        if referring_doc.role in ('ophthalmologist', 'intern', 'medical_director'):
            _cu = (getattr(referring_doc, 'consultation_unit', '') or 'GENERAL').upper()
            _cu_svc = {
                'VIP_CONSULT': 'VIP_CONSULT', 'VIP': 'VIP_CONSULT',
                'EXP_CONSULT': 'EXP_CONSULT', 'EXPRESS': 'EXP_CONSULT',
                'INSUR_CONSULT': 'INSUR_CONSULT', 'INSURANCE': 'INSUR_CONSULT',
            }
            target_service = _cu_svc.get(_cu, target_service)
    else:
        target_service  = 'PARAMETERS'  # → OPD triage nurse
        assigned_doctor = None

    # --- Close this specialist's active tokens for the patient ---
    user_dept_code     = request.user.department.code if request.user.department else ''
    dept_service_types = _DEPT_TO_SERVICE_TYPES.get(user_dept_code, [])
    entry_token = QueueToken.objects.filter(
        patient=visit.patient, token_date=today,
        issuance_point__in=[
            IssuancePoint.GATE, IssuancePoint.CASHIER,
            IssuancePoint.VIP_RECEPTION, IssuancePoint.EXPRESS_DESK,
        ],
        is_deleted=False,
    ).first()

    with transaction.atomic():
        if dept_service_types:
            QueueToken.objects.filter(
                patient=visit.patient,
                service_type__in=dept_service_types,
                token_date=today,
                status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                is_deleted=False,
            ).update(status=TokenStatus.COMPLETED, completed_at=_tz.now())

        counter = None
        if assigned_doctor:
            from apps.qms.models import ServiceCounter as _SC
            counter = _SC.objects.filter(
                staff_assigned=assigned_doctor,
                checked_in_date=today,
                is_active=True,
            ).first()

        token_number = DailyTokenSequence.next_dept_token(target_service)
        new_token = QueueToken.objects.create(
            token_number=token_number,
            patient=visit.patient,
            visit=visit,
            patient_name=visit.patient.full_name if visit.patient else '',
            service_type=target_service,
            service_tier=tier,
            issuance_point=IssuancePoint.SYSTEM,
            priority=TIER_PRIORITY.get(tier, 0),
            status=TokenStatus.WAITING,
            counter=counter,
            entry_token=entry_token,
            assigned_doctor=assigned_doctor,
            notes=note,
            issued_by=request.user,
        )

        visit.status = 'WAITING'
        visit.referring_doctor = None
        visit.save(update_fields=['status', 'referring_doctor', 'updated_at'])

        try:
            from apps.core.ws_notify import notify_queue as _ws_nq
            _ws_nq('WAITING')
        except Exception:
            pass

    dest_label = f'Dr. {referring_doc.get_full_name()}' if referring_doc else 'Triage / OPD Nurse'
    return JsonResponse({
        'success': True,
        'token_number': new_token.token_number,
        'message': f'Patient re-routed to {dest_label}. Token {new_token.token_number}.',
    })



# route_patient_view removed — all routing now goes through smart_route_view + EhrRoute JS



# ── Return to Referring Doctor ────────────────────────────────────────────────

@login_required
@require_POST
def return_to_referring_doctor_view(request):
    """
    Refractionist clicks "Send back to Dr. [Name]".
    Creates a QMS token routed to the referring doctor's counter and clears
    the referring_doctor field on the visit so it cannot be re-used.
    """
    from apps.patients.models import Visit as _Visit, VisitStatus as _VS
    from django.utils import timezone as _tz

    visit_id = request.POST.get('visit_id', '').strip()
    if not visit_id:
        return JsonResponse({'success': False, 'message': 'visit_id required'}, status=400)

    visit = get_object_or_404(_Visit, id=visit_id, is_deleted=False)

    if not visit.referring_doctor_id:
        return JsonResponse({'success': False, 'message': 'No referring doctor recorded for this visit.'}, status=400)

    referring_doc = visit.referring_doctor

    # Map referring doctor's role → QMS service type
    _ROLE_SVC = {
        'ophthalmologist':           'GENERAL',
        'intern':                    'GENERAL',
        'retina_specialist':         'RETINA',
        'glaucoma_specialist':       'GLAUCOMA',
        'pediatric_ophthalmologist': 'PEDIATRIC',
        'cataract_surgeon':          'CATARACT',
        'cornea_specialist':         'CORNEA',
        'oculoplastics_surgeon':     'OCULOPLASTY',
        'neuro_ophthalmologist':     'NEURO',
        'uveitis_specialist':        'UVEITIS',
        'low_vision_specialist':     'LOW_VISION',
        'medical_director':          'GENERAL',
        'general_physician':         'GEN_PHYS',
    }
    service_type = _ROLE_SVC.get(referring_doc.role, 'GENERAL')

    # Also check consultation_unit for GEN_OPH doctors (VIP/Express/Insurance)
    if referring_doc.role in ('ophthalmologist', 'intern', 'medical_director'):
        _cu = (getattr(referring_doc, 'consultation_unit', '') or 'GENERAL').upper()
        _cu_svc_map = {
            'VIP_CONSULT': 'VIP_CONSULT',
            'VIP':         'VIP_CONSULT',
            'EXP_CONSULT': 'EXP_CONSULT',
            'EXPRESS':     'EXP_CONSULT',
            'INSUR_CONSULT': 'INSUR_CONSULT',
            'INSURANCE':   'INSUR_CONSULT',
        }
        service_type = _cu_svc_map.get(_cu, service_type)

    if not _qms_active():
        # QMS off — just update visit status and department
        from apps.departments.models import Department as _Dept
        gen_dept = _Dept.objects.filter(code='GEN_OPH', is_active=True).first()
        if gen_dept:
            visit.department = gen_dept
        visit.status = 'WAITING'
        visit.referring_doctor = None
        visit.save(update_fields=['status', 'department', 'referring_doctor', 'updated_at'])
        return JsonResponse({
            'success': True,
            'message': f'Patient sent back to Dr. {referring_doc.get_full_name()} (QMS is off — visit status updated).',
        })

    from apps.qms.models import (
        QueueToken, DailyTokenSequence, IssuancePoint,
        TokenStatus, TIER_PRIORITY, ServiceTier,
    )
    from django.db import transaction

    tier = visit.service_tier or ServiceTier.STANDARD
    today = _tz.localdate()

    # Find the entry token for zone/origin_zone inheritance
    entry_token = QueueToken.objects.filter(
        patient=visit.patient,
        token_date=today,
        issuance_point__in=[
            IssuancePoint.GATE, IssuancePoint.CASHIER,
            IssuancePoint.VIP_RECEPTION, IssuancePoint.EXPRESS_DESK,
        ],
        is_deleted=False,
    ).first()

    with transaction.atomic():
        token_number = DailyTokenSequence.next_dept_token(service_type)

        # Close active REFRACTION tokens for this patient
        QueueToken.objects.filter(
            patient=visit.patient,
            service_type='REFRACTION',
            token_date=today,
            status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
            is_deleted=False,
        ).update(status=TokenStatus.COMPLETED, completed_at=_tz.now())

        # Find the referring doctor's checked-in counter (so the token goes directly to them)
        from apps.qms.models import ServiceCounter as _SC
        dr_counter = _SC.objects.filter(
            staff_assigned=referring_doc,
            checked_in_date=today,
            is_active=True,
        ).first()

        dept_token = QueueToken.objects.create(
            token_number=token_number,
            patient=visit.patient,
            visit=visit,
            patient_name=visit.patient.full_name if visit.patient else '',
            service_type=service_type,
            service_tier=tier,
            issuance_point=IssuancePoint.SYSTEM,
            priority=TIER_PRIORITY.get(tier, 0),
            status=TokenStatus.WAITING,
            counter=dr_counter,
            entry_token=entry_token,
            assigned_doctor=referring_doc,
            notes=f'Returned from Refraction — {request.user.get_full_name()}',
            issued_by=request.user,
        )

        # Update visit status and department back to Gen Oph / original dept
        from apps.departments.models import Department as _Dept2
        _SVC_DEPT = {
            'GENERAL':      'GEN_OPH',
            'VIP_CONSULT':  'GEN_OPH',
            'EXP_CONSULT':  'GEN_OPH',
            'INSUR_CONSULT':'GEN_OPH',
            'RETINA':       'RETINA',
            'GLAUCOMA':     'GLAUC',
            'CATARACT':     'CATARACT',
            'PEDIATRIC':    'PEDS_OPH',
            'NEURO':        'NEURO_OPH',
            'CORNEA':       'CORNEA',
            'OCULOPLASTY':  'OCULOPLASTY',
            'UVEITIS':      'UVEITIS',
        }
        _upd = ['status', 'referring_doctor', 'updated_at']
        visit.status = 'WAITING'
        visit.referring_doctor = None   # consumed — clear it
        orig_dept_code = _SVC_DEPT.get(service_type)
        if orig_dept_code:
            orig_dept = _Dept2.objects.filter(code=orig_dept_code, is_active=True).first()
            if orig_dept:
                visit.department = orig_dept
                _upd.append('department')
        visit.save(update_fields=_upd)

        # WebSocket notify the doctor's queue
        try:
            from apps.core.ws_notify import notify_queue as _ws_nq
            _ws_nq('WAITING')
        except Exception:
            pass

    return JsonResponse({
        'success': True,
        'token_number': dept_token.token_number,
        'doctor': referring_doc.get_full_name(),
        'message': f'Patient sent back to Dr. {referring_doc.get_full_name()} — token {dept_token.token_number}.',
    })


# ── VIP Dashboard ─────────────────────────────────────────────────────────────

@login_required
def vip_dashboard_view(request):
    """
    Live VIP patient tracker — shows every VIP patient today with their
    current location/status across all departments.
    """
    from apps.patients.models import Visit, VisitStatus
    if not (request.user.can_create_consultation() or request.user.can_do_triage()
            or request.user.is_medical_director or request.user.is_super_admin
            or request.user.is_receptionist or request.user.role in ('cashier', 'chief_cashier')):
        return HttpResponseForbidden()

    today = timezone.localdate()

    active_vip = list(
        Visit.objects.filter(
            service_tier='VIP', visit_date__date=today, is_deleted=False,
        ).exclude(
            status__in=[VisitStatus.COMPLETED, VisitStatus.DISCHARGED]
        ).select_related('patient', 'department', 'attending_doctor', 'triage_nurse')
        .order_by('visit_date')
    )

    discharged_today = Visit.objects.filter(
        service_tier='VIP', visit_date__date=today, is_deleted=False,
        status__in=[VisitStatus.COMPLETED, VisitStatus.DISCHARGED]
    ).select_related('patient', 'attending_doctor').order_by('-updated_at')

    # Active QMS tokens for VIP visits to show current queue position
    vip_tokens = {}
    if _qms_active():
        try:
            from apps.qms.models import QueueToken, TokenStatus
            for tok in QueueToken.objects.filter(
                service_type='VIP_CONSULT', token_date=today, is_deleted=False,
            ).exclude(
                status__in=[TokenStatus.COMPLETED, TokenStatus.CANCELLED]
            ).select_related('patient', 'assigned_doctor'):
                if tok.patient_id:
                    vip_tokens[tok.patient_id] = tok
        except Exception:
            pass

    # Attach token to each visit for easy access in template
    for v in active_vip:
        v.current_token = vip_tokens.get(v.patient_id)

    _STATUS_LABEL = {
        'REGISTERED': ('Registration', 'secondary'),
        'AT_RECEPTIONIST': ('Reception', 'secondary'),
        'AT_CASHIER': ('Cashier — Payment', 'warning'),
        'PARAMETERS': ('Triage / Parameters', 'info'),
        'TRIAGE': ('Triage / Parameters', 'info'),
        'WAITING': ('Waiting for Doctor', 'primary'),
        'IN_CONSULTATION': ('In Consultation', 'success'),
        'INVESTIGATION': ('Eye Investigations', 'primary'),
        'LABORATORY': ('Laboratory', 'info'),
        'PHARMACY': ('Pharmacy', 'warning'),
        'BILLING': ('Cashier — Final Bill', 'warning'),
        'REFRACTION': ('Refraction / Optometry', 'primary'),
        'OPTICAL': ('Optical Shop', 'info'),
        'COUNSELING': ('Surgical Counseling', 'warning'),
        'ADMITTED': ('Admitted / IPD', 'danger'),
        'IN_THEATRE': ('In Theatre', 'danger'),
    }

    total_today = len(active_vip) + discharged_today.count()
    in_consult = sum(1 for v in active_vip if v.status == 'IN_CONSULTATION')
    in_triage = sum(1 for v in active_vip if v.status in ('PARAMETERS', 'TRIAGE'))
    waiting = sum(1 for v in active_vip if v.status == 'WAITING')

    if request.GET.get('partial') == '1':
        from django.template.loader import render_to_string
        from django.http import HttpResponse
        html = render_to_string('consultations/_vip_rows.html', {
            'active_vip': active_vip, 'status_label': _STATUS_LABEL,
        }, request=request)
        return HttpResponse(html)

    return render(request, 'consultations/vip_dashboard.html', {
        'active_vip': active_vip,
        'discharged_today': discharged_today,
        'today': today,
        'status_label': _STATUS_LABEL,
        'total_today': total_today,
        'in_consult': in_consult,
        'in_triage': in_triage,
        'waiting': waiting,
        'discharged_count': discharged_today.count(),
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

    # Manual override via URL param — only supervisors can freely switch tiers
    tier_filter = request.GET.get('tier', '').upper()
    _is_supervisor = (
        request.user.is_nurse_director
        or request.user.is_medical_director
        or request.user.is_super_admin
    )

    # Determine default view based on counter assignment or patient_tier field
    _nurse_pt = getattr(request.user, 'patient_tier', 'ALL')  # ALL/STANDARD/EXPRESS/VIP

    if tier_filter and _is_supervisor:
        show_mode = tier_filter  # supervisors only can freely switch via URL
    elif assigned_counter:
        # Use raw serves_tiers string — get_serves_tiers() expands blank→ALL which
        # causes a blank STANDARD counter to match 'VIP in tiers' incorrectly.
        _st = assigned_counter.serves_tiers  # blank = counter serves all tiers
        if not _st:
            show_mode = 'ALL'        # all-tier counter → supervisor-style view
        elif 'VIP' in _st:
            show_mode = 'VIP'        # explicitly VIP counter
        elif 'EXPRESS' in _st or 'FAST_TRACK' in _st:
            show_mode = 'EXPRESS'    # Express / Fast Track counter
        else:
            show_mode = 'STANDARD'   # Standard-only counter
    elif _nurse_pt == 'VIP':
        show_mode = 'VIP'           # VIP triage sector — PARAMS_VIP filtered to VIP only
    elif _nurse_pt in ('EXPRESS', 'FAST_TRACK'):
        show_mode = 'EXPRESS'       # Express/FastTrack sector — PARAMS_VIP filtered to EXPRESS+FT
    elif _nurse_pt == 'STANDARD':
        show_mode = 'STANDARD'      # Standard triage sector — PARAMETERS queue only
    elif _is_supervisor or _nurse_pt == 'ALL':
        show_mode = 'ALL'           # Supervisors and ALL-tier nurses see every tier
    else:
        show_mode = 'STANDARD'      # Unassigned nurses default to standard queue only

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
                        token_date=today,
                        service_type='PARAMETERS',
                        status__in=active_statuses,
                        is_deleted=False,
                    ).select_related('patient', 'counter').order_by('-priority', 'issued_at')
                )

            # ── VIP / Express Parameters queue ────────────────────────────────
            # show_mode='VIP'     → PARAMS_VIP tokens where service_tier=VIP only
            # show_mode='EXPRESS' → PARAMS_VIP tokens where service_tier=EXPRESS or FAST_TRACK
            # show_mode='ALL'     → all PARAMS_VIP tokens (supervisors)
            if show_mode in ('VIP', 'EXPRESS', 'ALL'):
                _pvip_qs = QueueToken.objects.filter(
                    token_date=today,
                    service_type='PARAMS_VIP',
                    status__in=active_statuses,
                    is_deleted=False,
                )
                if show_mode == 'VIP':
                    _pvip_qs = _pvip_qs.filter(service_tier='VIP')
                elif show_mode == 'EXPRESS':
                    _pvip_qs = _pvip_qs.filter(service_tier__in=['EXPRESS', 'FAST_TRACK'])
                # show_mode='ALL' → no additional filter (counter-assigned supervisors)
                vip_params_queue = list(
                    _pvip_qs.select_related('patient', 'counter').order_by('-priority', 'issued_at')
                )
        except Exception:
            pass
    else:
        # No QMS — show visits with PARAMETERS status, tier-isolated
        _tv_qs = Visit.objects.filter(
            visit_date__date=today,
            status='PARAMETERS',
            is_deleted=False,
        )
        if show_mode == 'VIP':
            _tv_qs = _tv_qs.filter(service_tier='VIP')
        elif show_mode == 'EXPRESS':
            _tv_qs = _tv_qs.filter(service_tier__in=['EXPRESS', 'FAST_TRACK'])
        elif show_mode == 'STANDARD':
            _tv_qs = _tv_qs.filter(service_tier='STANDARD')
        # show_mode == 'ALL' → no additional filter (supervisors see all)
        triage_visits = list(_tv_qs.select_related('patient').order_by('visit_date'))

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
    total_standard = total_express = total_vip_express = 0
    if _qms_active():
        try:
            from apps.qms.models import QueueToken as _QueueToken
            all_today = _QueueToken.objects.filter(
                token_date=today,
                service_type__in=['PARAMETERS', 'PARAMS_VIP'],
                is_deleted=False,
            )
            total_standard    = all_today.filter(service_type='PARAMETERS').count()
            total_vip_express = all_today.filter(service_type='PARAMS_VIP').count()
            total_express     = all_today.filter(
                service_type='PARAMS_VIP',
                service_tier__in=['EXPRESS', 'FAST_TRACK'],
            ).count()
            total_vip_only    = all_today.filter(
                service_type='PARAMS_VIP',
                service_tier='VIP',
            ).count()
        except Exception:
            total_vip_only = 0
    else:
        total_vip_only = 0

    # Head of triage (Nurse Director / Medical Director / Super Admin) can see
    # all patient statuses + locations, switch tiers freely.
    is_head_of_triage = _is_supervisor

    # ── Acuity counts: Emergency pathway + AI urgency breakdown ───────────────
    _base_vs = Visit.objects.filter(visit_date__date=today, is_deleted=False)
    if show_mode == 'VIP':
        _base_vs = _base_vs.filter(service_tier='VIP')
    elif show_mode == 'EXPRESS':
        _base_vs = _base_vs.filter(service_tier__in=['EXPRESS', 'FAST_TRACK'])
    elif show_mode == 'STANDARD':
        _base_vs = _base_vs.filter(service_tier='STANDARD')
    emergency_pathway_today = _base_vs.filter(visit_type='EMERGENCY').count()

    # AI urgency on this nurse's own triaged patients (bounded set, no extra DB hit)
    try:
        from apps.dashboard.views import _compute_ai_triage as _cai
        _ai_emerg = _ai_urgent = 0
        for _v in triaged_visits:
            _pri, _ = _cai(_v)
            if _pri == 'EMERGENCY':
                _ai_emerg += 1
            elif _pri == 'URGENT':
                _ai_urgent += 1
    except Exception:
        _ai_emerg = _ai_urgent = 0

    return render(request, 'consultations/triage_workstation.html', {
        'parameters_queue': parameters_queue,
        'vip_params_queue': vip_params_queue,
        'triage_visits': triage_visits,
        'triaged_today': triaged_today,
        'triaged_visits': triaged_visits,
        'today': today,
        'show_mode': show_mode,
        'nurse_patient_tier': _nurse_pt,
        'assigned_counter': assigned_counter,
        'is_head_of_triage': is_head_of_triage,
        'total_standard': total_standard,
        'total_express': total_express,
        'total_vip_only': total_vip_only,
        'total_vip_express': total_vip_express,
        'total_waiting': len(parameters_queue) + len(vip_params_queue),
        'qms_on': _qms_active(),
        'emergency_pathway_today': emergency_pathway_today,
        'ai_emergency_count': _ai_emerg,
        'ai_urgent_count': _ai_urgent,
    })


# ── Clinic Nurse Workstation ──────────────────────────────────────────────────

# Mapping dept code → visit statuses that mean "patient is waiting in THIS dept"
_DEPT_TO_WAITING_STATUSES = {
    'GEN_OPH':     ['WAITING'],
    'RETINA':      ['AT_RETINA'],
    'GLAUC':       ['AT_GLAUCOMA'],
    'PEDS_OPH':    ['AT_PEDIATRIC'],
    'PEDS_REFRAC': ['REFRACTION'],
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
    'PEDS_REFRAC': 'REFRACTION',
    'REFRAC':      'REFRACTION',
    'CORNEA':      'CORNEA',
    'OCULOPLASTY': 'OCULOPLASTY',
    'NEURO_OPH':   'NEURO',
    'CATARACT':    'CATARACT',
    'UVEITIS':     'UVEITIS',
    'LOW_VIS':     'GENERAL',
    'GEN_PHYS':    'GEN_PHYS',
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
    _nurse_tier = getattr(user, 'patient_tier', 'ALL')  # used in both QMS and no-QMS blocks

    if qms_on and dept_code:
        # ── QMS ON: show QMS queue tokens for this department ────────────────
        try:
            from apps.qms.models import QueueToken, TokenStatus
            svc_type = _DEPT_TO_QMS_SERVICE.get(dept_code)
            # GEN_OPH nurses serve only their tier's consultation queue
            if dept_code == 'GEN_OPH':
                _cu = (getattr(user, 'consultation_unit', '') or 'GENERAL').upper()
                svc_type = {
                    'GENERAL':       'GENERAL',
                    'EXP_CONSULT':   'EXP_CONSULT',
                    'EXPRESS':       'EXP_CONSULT',    # legacy alias
                    'VIP_CONSULT':   'VIP_CONSULT',
                    'VIP':           'VIP_CONSULT',    # legacy alias
                    'INSUR_CONSULT': 'INSUR_CONSULT',
                    'INSURANCE':     'INSUR_CONSULT',  # legacy alias
                }.get(_cu, 'GENERAL')
            if svc_type:
                waiting_tokens = list(
                    QueueToken.objects.filter(
                        token_date=today,
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
        _nq_qs = Visit.objects.filter(
            visit_date__date=today,
            status__in=waiting_statuses,
            is_deleted=False,
        ).select_related('patient', 'triage_nurse', 'attending_doctor')
        if dept:
            _nq_qs = _nq_qs.filter(department=dept)
        # Tier isolation for GEN_OPH — VIP nurses only see VIP visits, etc.
        if dept_code == 'GEN_OPH':
            if _nurse_tier == 'VIP':
                _nq_qs = _nq_qs.filter(service_tier='VIP')
            elif _nurse_tier in ('EXPRESS', 'FAST_TRACK'):
                _nq_qs = _nq_qs.filter(service_tier__in=['EXPRESS', 'FAST_TRACK'])
            elif _nurse_tier == 'STANDARD':
                _nq_qs = _nq_qs.filter(service_tier='STANDARD')
        waiting_visits = list(_nq_qs.order_by('visit_date'))

    # ── Patients currently IN_CONSULTATION in this dept today (both modes) ──
    if dept:
        _ic_qs = Visit.objects.filter(
            visit_date__date=today,
            status='IN_CONSULTATION',
            department=dept,
            is_deleted=False,
        )
        # Scope to nurse's tier — a VIP nurse only sees VIP patients in consultation
        if _nurse_tier == 'VIP':
            _ic_qs = _ic_qs.filter(service_tier='VIP')
        elif _nurse_tier == 'EXPRESS':
            _ic_qs = _ic_qs.filter(service_tier__in=['EXPRESS', 'FAST_TRACK'])
        elif _nurse_tier == 'STANDARD':
            _ic_qs = _ic_qs.filter(service_tier='STANDARD')
        # ALL / supervisor → no tier filter
        in_consult_visits = list(
            _ic_qs.select_related('patient', 'attending_doctor').order_by('-visit_date')
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
            _rtr_qs = Visit.objects.filter(
                id__in=done_visit_ids,
                status='IN_CONSULTATION',
                is_deleted=False,
            )
            if _nurse_tier == 'VIP':
                _rtr_qs = _rtr_qs.filter(service_tier='VIP')
            elif _nurse_tier == 'EXPRESS':
                _rtr_qs = _rtr_qs.filter(service_tier__in=['EXPRESS', 'FAST_TRACK'])
            elif _nurse_tier == 'STANDARD':
                _rtr_qs = _rtr_qs.filter(service_tier='STANDARD')
            ready_to_route = list(
                _rtr_qs.select_related('patient', 'attending_doctor').order_by('visit_date')
            )

    # Active rooms (all depts) — for the room picker on route buttons
    from apps.departments.models import ConsultationRoom as _NurseRoom
    active_rooms = list(
        _NurseRoom.objects.filter(is_active=True, assigned_doctor__isnull=False)
        .select_related('assigned_doctor', 'department')
        .order_by('department__name', 'room_number')
    )

    # ── Recent dispatches — nurse can fix routing errors within 2 hours ─────
    from apps.qms.models import QueueToken as _QT, TokenStatus as _TS, IssuancePoint as _IP
    from datetime import timedelta as _td
    _two_hours_ago = timezone.now() - _td(hours=2)
    # Find patients who had consultations in this dept today
    _dept_patient_ids = set(
        Consultation.objects.filter(
            consultation_date__date=today,
            department=dept,
            is_deleted=False,
        ).values_list('visit__patient_id', flat=True)
    ) if dept else set()
    recent_dispatches = list(
        _QT.objects.filter(
            patient_id__in=_dept_patient_ids,
            token_date=today,
            issuance_point=_IP.SYSTEM,
            status__in=[_TS.WAITING, _TS.CALLED],
            created_at__gte=_two_hours_ago,
            is_deleted=False,
        ).select_related('patient', 'visit')
        .order_by('-created_at')[:15]
    ) if _dept_patient_ids else []

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
        'nurse_tier': _nurse_tier,
        'today': today,
        'active_rooms': active_rooms,
        'recent_dispatches': recent_dispatches,
    })


@json_error_handler
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

    # Notify queue pages instantly via WebSocket
    from apps.core.ws_notify import notify_queue as _ws_notify
    _ws_notify('opd')
    _ws_notify('workstation')
    if visit.attending_doctor_id:
        _ws_notify(f'doctor-{visit.attending_doctor_id}')

    # QMS: mark the matching token as CALLED
    if _qms_active():
        try:
            from apps.qms.models import QueueToken, TokenStatus
            dept_code = user.role_department_code or (user.department.code if user.department else None)
            svc_type = _DEPT_TO_QMS_SERVICE.get(dept_code) if dept_code else None
            # GEN_OPH: resolve to the correct tier's service type
            if dept_code == 'GEN_OPH':
                _cu = (getattr(user, 'consultation_unit', '') or 'GENERAL').upper()
                svc_type = {'GENERAL': 'GENERAL', 'EXP_CONSULT': 'EXP_CONSULT', 'VIP_CONSULT': 'VIP_CONSULT', 'INSUR_CONSULT': 'INSUR_CONSULT'}.get(_cu, 'GENERAL')
            if svc_type:
                token = QueueToken.objects.filter(
                    patient=visit.patient,
                    service_type=svc_type,
                    token_date=timezone.localdate(),
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


# ── Shared routing helper — used by complete_consultation_view AND nurse_route_patient_view ──
def _inline_route_visit(visit, destination, routed_by, room_id=None, counter_id=None, routing_note=None, return_to_me=False):
    """
    Route a visit to its next destination.
    Returns (success: bool, label: str).
    Never raises — errors are swallowed so they never block a consultation save.
    """
    try:
        route = _NURSE_ROUTE_MAP.get(destination.upper())
        if not route:
            return False, ''
        new_status, qms_service, label = route

        # Tier-aware doctor queue
        if new_status == 'WAITING' and qms_service == 'GENERAL':
            _tier = getattr(visit, 'service_tier', 'STANDARD') or 'STANDARD'
            if _tier == 'VIP':
                qms_service = 'VIP_CONSULT'
            elif _tier in ('EXPRESS', 'FAST_TRACK'):
                qms_service = 'EXP_CONSULT'

        # Update visit status
        visit.status = new_status
        _save_fields = ['status', 'updated_at']

        # Return-to-me: set referring_doctor so destination shows "Return to Dr. X"
        if return_to_me:
            visit.referring_doctor = routed_by
            _save_fields.append('referring_doctor')
        elif not return_to_me and hasattr(visit, 'referring_doctor'):
            # Clear stale referring_doctor when not requested
            visit.referring_doctor = None
            _save_fields.append('referring_doctor')

        # Store routing note on the visit itself
        if routing_note:
            visit.routing_note = routing_note
            _save_fields.append('routing_note')
        elif hasattr(visit, 'routing_note') and visit.routing_note:
            visit.routing_note = ''
            _save_fields.append('routing_note')

        # When routing without a specific room/counter, clear attending_doctor so
        # the destination department's staff can see the patient on their dashboard.
        # (If a specific counter/room is given below, it will be set again there.)
        if not counter_id and not room_id:
            visit.attending_doctor = None
            if 'attending_doctor' not in _save_fields:
                _save_fields.append('attending_doctor')

        # Update department if routing to a clinical dept
        if qms_service and qms_service not in ('PHARMACY', 'CASHIER', 'COUNSEL'):
            _svc_to_dept = {
                'GEN_PHYS': 'GEN_PHYS', 'GENERAL': 'GEN_OPH', 'EXP_CONSULT': 'GEN_OPH',
                'VIP_CONSULT': 'GEN_OPH', 'RETINA': 'RETINA', 'GLAUCOMA': 'GLAUC',
                'PEDIATRIC': 'PEDS_OPH', 'REFRACTION': 'REFRAC', 'CORNEA': 'CORNEA',
                'UVEITIS': 'UVEITIS', 'NEURO': 'NEURO_OPH', 'OCULOPLASTY': 'OCULOPLASTY',
                'LOW_VISION': 'LOW_VIS', 'INSUR_CONSULT': 'GEN_OPH',
            }
            try:
                from apps.departments.models import Department as _RouteDept2
                _dept_code = _svc_to_dept.get(qms_service, qms_service)
                _dest_dept = _RouteDept2.objects.filter(code=_dept_code).first()
                if _dest_dept:
                    visit.department = _dest_dept
                    _save_fields.append('department')
            except Exception:
                pass
        visit.save(update_fields=_save_fields)

        # Notify queue pages instantly via WebSocket
        try:
            from apps.core.ws_notify import notify_queue as _ws_notify_ir
            from apps.core.patient_flow import _STATUS_ROOMS as _SR
            for _room in _SR.get(new_status, []):
                _ws_notify_ir(_room)
            if visit.attending_doctor_id and new_status == 'IN_CONSULTATION':
                _ws_notify_ir(f'doctor-{visit.attending_doctor_id}')
        except Exception:
            pass

        # Doctor/counter assignment
        _room_note = ''
        _assigned_counter = None
        if counter_id:
            try:
                from apps.qms.models import ServiceCounter as _SC_IR
                _assigned_counter = _SC_IR.objects.select_related('staff_assigned').get(
                    id=counter_id, is_active=True
                )
                if _assigned_counter.staff_assigned:
                    visit.attending_doctor = _assigned_counter.staff_assigned
                    visit.save(update_fields=['attending_doctor', 'updated_at'])
                    _room_note = f' → {_assigned_counter.name} (Dr. {_assigned_counter.staff_assigned.last_name})'
            except Exception:
                pass
        elif room_id:
            try:
                from apps.departments.models import ConsultationRoom as _CR2
                _room = _CR2.objects.select_related('assigned_doctor').get(id=room_id, is_active=True)
                if _room.assigned_doctor:
                    visit.attending_doctor = _room.assigned_doctor
                    visit.save(update_fields=['attending_doctor', 'updated_at'])
                    _room_note = f' → Room {_room.room_number} (Dr. {_room.assigned_doctor.last_name})'
            except Exception:
                pass

        # QMS token handling
        if _qms_active():
            try:
                from apps.qms.models import (
                    QueueToken, TokenStatus, IssuancePoint, TIER_PRIORITY, DailyTokenSequence,
                )
                from django.db import transaction as _tx2
                today = timezone.localdate()
                with _tx2.atomic():
                    # Complete ALL active tokens for this visit before routing to next stop
                    # Prevents stale tokens (e.g., old CASHIER token) lingering in queues
                    if visit.patient:
                        QueueToken.objects.filter(
                            patient=visit.patient,
                            token_date=today,
                            status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                            is_deleted=False,
                        ).update(status=TokenStatus.COMPLETED, completed_at=timezone.now())

                    # Issue new token for destination
                    if qms_service and visit.patient:
                        already_waiting = QueueToken.objects.filter(
                            patient=visit.patient,
                            service_type=qms_service,
                            token_date=today,
                            status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                            is_deleted=False,
                        ).exists()
                        if not already_waiting:
                            tier = visit.service_tier
                            token_number = DailyTokenSequence.next_dept_token(qms_service)
                            # Assign doctor from counter so only that doctor's workstation shows this token
                            _token_doctor = None
                            if _assigned_counter and _assigned_counter.staff_assigned:
                                _token_doctor = _assigned_counter.staff_assigned
                            QueueToken.objects.create(
                                token_number=token_number,
                                patient=visit.patient,
                                visit=visit,
                                patient_name=visit.patient.full_name,
                                service_type=qms_service,
                                service_tier=tier,
                                issuance_point=IssuancePoint.SYSTEM,
                                priority=TIER_PRIORITY.get(tier, 0),
                                counter=_assigned_counter,
                                assigned_doctor=_token_doctor,
                                notes=(
                                    f'Routed by {routed_by.get_full_name()} to {label}{_room_note}'
                                    + (f' | Note: {routing_note}' if routing_note else '')
                                ),
                                issued_by=routed_by,
                            )
            except Exception:
                pass

        return True, label
    except Exception:
        return False, ''


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
    'GLAUCOMA':    ('AT_GLAUCOMA',       'GLAUCOMA',   'Glaucoma Clinic'),
    'GENERAL':     ('WAITING',           'GENERAL',    'General Ophthalmology'),
    'DOCTOR':      ('WAITING',           'GENERAL',    'General Ophthalmology'),
    'PEDIATRIC':   ('AT_PEDIATRIC',      'PEDIATRIC',  'Pediatric Clinic'),
    'PEDS_OPH':    ('AT_PEDIATRIC',      'PEDIATRIC',  'Pediatric Clinic'),
    'REFRACTION':  ('REFRACTION',        'REFRACTION', 'Refraction / Optometry'),
    'CYCLO':       ('REFRACTION',        'REFRACTION', 'Cycloplegic Refraction (Pediatric)'),
    'CATARACT':    ('AT_CATARACT',       'CATARACT',   'Cataract Clinic'),
    'CORNEA':      ('AT_CORNEA',         'CORNEA',     'Cornea Clinic'),
    'UVEITIS':     ('UVEITIS',           'UVEITIS',    'Uveitis Clinic'),
    'NEURO':       ('AT_NEURO',          'NEURO',      'Neuro-Ophthalmology'),
    'OCULOPLASTY': ('AT_OCULOPLASTY',    'OCULOPLASTY','Oculoplastics'),
    'GEN_PHYS':    ('WAITING',           'GEN_PHYS',   'General Physician / Internist'),
    'LOW_VISION':  ('WAITING',           'LOW_VISION', 'Low Vision & Rehabilitation'),
    'INSUR_CONSULT':('WAITING',          'INSUR_CONSULT','Insurance Consultation'),
    'CONTACT_LENS':('WAITING',           'CONTACT_LENS','Contact Lens Clinic'),
    'LASER':       ('WAITING',           'LASER',      'Laser Clinic'),
    'INJECTION':   ('WAITING',           'INJECTION',  'Injection Clinic'),
    'DISCHARGE':   ('COMPLETED',         None,         'Discharge / Done'),
    # Aliases — service_type codes from ServiceCounter used as routing destinations
    'EXP_CONSULT':  ('WAITING',          'EXP_CONSULT',  'Express Consultation'),
    'VIP_CONSULT':  ('WAITING',          'VIP_CONSULT',  'VIP Consultation'),
    'INVEST':       ('INVESTIGATION',    'INVEST',       'Investigations'),
    'COUNSEL':      ('COUNSELING',       'COUNSEL',      'Surgical Counseling'),
}


@json_error_handler
@login_required
@require_POST
def nurse_route_patient_view(request, visit_pk):
    """
    Clinic Nurse routes a patient to the next department/service after consultation.
    Works with QMS ON (creates QMS token for destination) and QMS OFF (visit status only).
    """
    user = request.user
    if not (user.can_dispatch_patient() or user.is_medical_director or user.is_super_admin or user.is_doctor):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)
    destination = request.POST.get('destination', '').upper()
    referral_reason = request.POST.get('referral_reason', '').strip()

    # Optional: route to a specific counter (preferred) or room (legacy)
    counter_id = request.POST.get('counter_id', '').strip()
    room_id = request.POST.get('room_id', '').strip()
    _target_counter = None
    _target_room = None
    _room_note = ''
    if counter_id:
        try:
            from apps.qms.models import ServiceCounter as _SC_NR
            _target_counter = _SC_NR.objects.select_related('staff_assigned').get(id=counter_id, is_active=True)
            if _target_counter.staff_assigned:
                _room_note = f' → {_target_counter.name} (Dr. {_target_counter.staff_assigned.last_name})'
        except Exception:
            pass
    elif room_id:
        try:
            from apps.departments.models import ConsultationRoom as _CR
            _target_room = _CR.objects.select_related('assigned_doctor').get(id=room_id, is_active=True)
            if _target_room.assigned_doctor:
                _room_note = f' → Room {_target_room.room_number} (Dr. {_target_room.assigned_doctor.last_name})'
        except Exception:
            pass

    route = _NURSE_ROUTE_MAP.get(destination)
    if not route:
        return JsonResponse({'error': f'Unknown destination: {destination}'}, status=400)

    new_status, qms_service, label = route

    # Tier-aware routing: after triage, send patient to the correct tier's doctor queue
    # Standard → GENERAL, Express/FT → EXP_CONSULT, VIP → VIP_CONSULT
    if new_status == 'WAITING' and qms_service == 'GENERAL':
        _tier = getattr(visit, 'service_tier', 'STANDARD') or 'STANDARD'
        if _tier == 'VIP':
            qms_service = 'VIP_CONSULT'
        elif _tier in ('EXPRESS', 'FAST_TRACK'):
            qms_service = 'EXP_CONSULT'

    # ── VIP Specialist Invite ─────────────────────────────────────────────────
    # For VIP patients needing a specialist: the specialist comes TO the VIP room.
    # Instead of routing the patient out, notify the specialist and keep patient in VIP.
    _VIP_SPECIALIST_DESTS = {'RETINA', 'GLAUCOMA', 'PEDIATRIC', 'CORNEA', 'OCULOPLASTY', 'NEURO', 'UVEITIS', 'CATARACT'}
    _DEST_TO_ROLE = {
        'RETINA':      'RETINA_SPECIALIST',
        'GLAUCOMA':    'GLAUCOMA_SPECIALIST',
        'PEDIATRIC':   'PEDIATRIC_OPHTHALMOLOGIST',
        'CORNEA':      'CORNEA_SPECIALIST',
        'OCULOPLASTY': 'OCULOPLASTICS_SURGEON',
        'NEURO':       'NEURO_OPHTHALMOLOGIST',
        'UVEITIS':     'UVEITIS_SPECIALIST',
        'CATARACT':    'CATARACT_SURGEON',
    }
    if getattr(visit, 'service_tier', 'STANDARD') == 'VIP' and destination in _VIP_SPECIALIST_DESTS:
        specialist_role = _DEST_TO_ROLE.get(destination)
        if specialist_role:
            try:
                from apps.notifications.utils import notify_role
                from apps.notifications.models import NotificationPriority
                notify_role(
                    role=specialist_role,
                    title=f'VIP Specialist Request — {visit.patient.full_name}',
                    message=(
                        f'Dr. {user.get_full_name()} requests your consultation for '
                        f'VIP patient {visit.patient.full_name} (ID: {visit.patient.patient_id}). '
                        f'Please come to the VIP Consultation Room.'
                    ),
                    link=f'/patients/{visit.patient.patient_id}/',
                    priority=NotificationPriority.URGENT,
                )
            except Exception:
                pass
        return JsonResponse({
            'success': True,
            'patient': visit.patient.full_name,
            'destination': label,
            'message': f'Specialist notified. {visit.patient.full_name} remains in VIP Room.',
            'vip_invite': True,
        })

    # Save referral reason to the most recent consultation for this visit
    if referral_reason:
        try:
            _ref_consult = Consultation.objects.filter(
                visit=visit, is_deleted=False
            ).order_by('-created_at').first()
            if _ref_consult:
                _ref_consult.referral_reason = referral_reason
                _ref_consult.updated_by = user
                _ref_consult.save(update_fields=['referral_reason', 'updated_by', 'updated_at'])
        except Exception:
            pass

    # Update visit status + department so the destination doctor's dashboard shows the patient
    visit.status = new_status
    _save_fields = ['status', 'updated_at']
    if qms_service and qms_service not in ('PHARMACY', 'CASHIER', 'COUNSEL'):
        # Map QMS service type → department code (some differ e.g. GENERAL → GEN_OPH)
        _svc_to_dept = {
            'GEN_PHYS':   'GEN_PHYS',
            'GENERAL':    'GEN_OPH',
            'RETINA':     'RETINA',
            'GLAUCOMA':   'GLAUC',
            'PEDIATRIC':  'PEDS_OPH',
            'REFRACTION': 'REFRAC',
            'CORNEA':     'CORNEA',
            'UVEITIS':    'UVEITIS',
            'NEURO':      'NEURO_OPH',
            'OCULOPLASTY':'OCULOPLASTY',
            'LOW_VISION': 'LOW_VIS',
            'GEN_OPH':    'GEN_OPH',
        }
        try:
            from apps.departments.models import Department as _RouteDept
            _dept_code = _svc_to_dept.get(qms_service, qms_service)
            _dest_dept = _RouteDept.objects.filter(code=_dept_code).first()
            if _dest_dept:
                visit.department = _dest_dept
                _save_fields.append('department')
        except Exception:
            pass
    visit.save(update_fields=_save_fields)

    # Assign to specific counter (preferred) or legacy room
    if _target_counter and _target_counter.staff_assigned:
        visit.attending_doctor = _target_counter.staff_assigned
        visit.save(update_fields=['attending_doctor', 'updated_at'])
    elif _target_room and _target_room.assigned_doctor:
        visit.attending_doctor = _target_room.assigned_doctor
        visit.save(update_fields=['attending_doctor', 'updated_at'])

    # Complete the current QMS token for this dept (QMS ON only)
    if _qms_active():
        try:
            from apps.qms.models import QueueToken, TokenStatus, IssuancePoint, TIER_PRIORITY, DailyTokenSequence
            from django.db import transaction as _tx
            dept_code = user.role_department_code or (user.department.code if user.department else None)
            svc_type = _DEPT_TO_QMS_SERVICE.get(dept_code) if dept_code else None
            # GEN_OPH: resolve to the correct tier's service type
            if dept_code == 'GEN_OPH':
                _cu = (getattr(user, 'consultation_unit', '') or 'GENERAL').upper()
                svc_type = {'GENERAL': 'GENERAL', 'EXP_CONSULT': 'EXP_CONSULT', 'VIP_CONSULT': 'VIP_CONSULT', 'INSUR_CONSULT': 'INSUR_CONSULT'}.get(_cu, 'GENERAL')
            today = timezone.localdate()

            with _tx.atomic():
                # Complete the current token for this department
                if svc_type:
                    QueueToken.objects.filter(
                        patient=visit.patient,
                        service_type=svc_type,
                        token_date=today,
                        status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                        is_deleted=False,
                    ).update(status=TokenStatus.COMPLETED, completed_at=timezone.now())

                # Issue a new token for destination service (skip if already waiting there)
                if qms_service and visit.patient:
                    already_waiting = QueueToken.objects.filter(
                        patient=visit.patient,
                        service_type=qms_service,
                        token_date=today,
                        status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                        is_deleted=False,
                    ).exists()
                    if not already_waiting:
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
                            counter=_target_counter,
                            notes=f'Routed by {user.get_full_name()} to {label}{_room_note}' + (f' — {referral_reason[:120]}' if referral_reason else ''),
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


# ── Unified Smart Route system ────────────────────────────────────────────────

@csrf_exempt
@login_required
def route_rooms_view(request):
    """
    GET /consultations/route/rooms/?tier=VIP&service=GENERAL
    Returns checked-in consultation counters grouped: same-tier first, then others.
    Used by the unified EhrRoute JS modal to build the room board dynamically.
    """
    user = request.user
    if not (user.can_dispatch_patient() or user.is_doctor or
            user.is_medical_director or user.is_super_admin):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    patient_tier = request.GET.get('tier', 'STANDARD').upper()
    service_filter = request.GET.get('service', '').upper()

    from apps.qms.models import ServiceCounter as _SC, QueueToken as _QT, TokenStatus as _TS
    from django.db.models import Count as _Cnt, Q as _DQ

    _consult_types = [
        'GENERAL', 'EXP_CONSULT', 'VIP_CONSULT', 'REFRACTION', 'GLAUCOMA',
        'RETINA', 'CORNEA', 'NEURO', 'CATARACT', 'UVEITIS', 'OCULOPLASTY',
        'PEDIATRIC', 'LOW_VISION', 'GEN_PHYS', 'INSUR_CONSULT',
    ]
    if service_filter and service_filter in _consult_types:
        _types = [service_filter]
    else:
        _types = _consult_types

    counters_qs = (
        _SC.objects.filter(
            is_active=True,
            staff_assigned__isnull=False,
            checked_in_date=timezone.localdate(),
            service_type__in=_types,
        )
        .exclude(staff_assigned=user)
        .select_related('staff_assigned', 'zone')
        .order_by('service_type', 'name')
    )

    # Get waiting token counts per counter in one query
    waiting_counts = dict(
        _QT.objects.filter(
            token_date=timezone.localdate(),
            status__in=[_TS.WAITING, _TS.CALLED, _TS.SERVING],
            counter__isnull=False,
            is_deleted=False,
        ).values('counter_id').annotate(n=_Cnt('id')).values_list('counter_id', 'n')
    )

    _tier_labels = {
        'STANDARD': 'Standard', 'VIP': 'VIP', 'EXPRESS': 'Express',
        'FAST_TRACK': 'Fast Track', 'ALL': 'All Tiers', '': 'All Tiers',
    }

    same_tier = []
    other_tier = []
    for ctr in counters_qs:
        serves = ctr.serves_tiers or ''
        tier_label = _tier_labels.get(serves, serves or 'All Tiers')
        zone_name = ctr.zone.name if ctr.zone else ctr.service_type
        entry = {
            'id': str(ctr.id),
            'room_number': ctr.code or ctr.name,
            'label': ctr.name,
            'dept_name': zone_name,
            'dept_code': ctr.service_type,
            'tier': serves or 'ALL',
            'tier_label': tier_label,
            'doctor_name': f'Dr. {ctr.staff_assigned.last_name}',
            'doctor_full': ctr.staff_assigned.get_full_name(),
            'waiting_count': waiting_counts.get(ctr.id, 0),
        }
        # Same tier: counter serves all tiers (blank) OR explicitly includes patient_tier
        if not serves or patient_tier in serves:
            same_tier.append(entry)
        else:
            other_tier.append(entry)

    return JsonResponse({
        'patient_tier': patient_tier,
        'same_tier': same_tier,
        'other': other_tier,
    })


@csrf_exempt
@json_error_handler
@login_required
@require_POST
def smart_route_view(request):
    """
    POST /consultations/route/
    Unified routing endpoint used by EhrRoute JS singleton.
    Accepts: visit_pk, destination, room_id (opt), complete_pk (opt)
    If complete_pk is provided, marks that consultation COMPLETED before routing.
    """
    user = request.user
    if not (user.can_dispatch_patient() or user.is_medical_director or
            user.is_super_admin or user.is_doctor):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    visit_pk = request.POST.get('visit_pk', '').strip()
    destination = request.POST.get('destination', '').upper().strip()
    room_id = request.POST.get('room_id', '').strip() or None
    counter_id = request.POST.get('counter_id', '').strip() or None
    complete_pk = request.POST.get('complete_pk', '').strip() or None
    routing_note = request.POST.get('routing_note', '').strip() or None
    return_to_me = request.POST.get('return_to_me') == '1'

    if not visit_pk or not destination:
        return JsonResponse({'error': 'Missing visit_pk or destination'}, status=400)

    try:
        import uuid as _uuid
        visit = Visit.objects.get(pk=_uuid.UUID(visit_pk), is_deleted=False)
    except Exception:
        return JsonResponse({'error': 'Visit not found'}, status=404)

    # Optionally complete a consultation before routing
    redirect_url = None
    if complete_pk:
        try:
            consult = Consultation.objects.get(pk=complete_pk, is_deleted=False)
            if consult.status != ConsultationStatus.COMPLETED:
                consult.status = ConsultationStatus.COMPLETED
                if hasattr(consult, 'completed_at'):
                    consult.completed_at = timezone.now()
                    consult.save(update_fields=['status', 'completed_at', 'updated_at'])
                else:
                    consult.save(update_fields=['status', 'updated_at'])
            redirect_url = '/consultations/'
        except Exception:
            pass

    routed, label = _inline_route_visit(visit, destination, user, room_id=room_id, counter_id=counter_id, routing_note=routing_note, return_to_me=return_to_me)
    if not routed:
        return JsonResponse({'error': f'Unknown destination: {destination}'}, status=400)

    return JsonResponse({
        'success': True,
        'patient': visit.patient.full_name,
        'destination': destination,
        'label': label,
        'message': f'{visit.patient.full_name} sent to {label}.',
        'redirect_url': redirect_url,
    })


# ── Specialist Unit Nurse Queue ───────────────────────────────────────────────
# This is the "Rooming" workflow used in Epic Ophthalmology and similar systems.
# A CONSULTATION_NURSE assigned to a specialist unit (Glaucoma, Retina, etc.)
# sees only their unit's patients, enters pre-screening data (IOP, VA, notes),
# then clicks "Ready for Doctor" to route the patient into the doctor's queue.
#
# Returning-appointment flow for specialist units:
#   Reception check-in → Visit.status = AT_GLAUCOMA/AT_RETINA/etc.
#   → appears here (unit queue, bypasses general triage)
#   → nurse does pre-screen → sends to doctor
#   → doctor opens workstation with vital_signs already filled

# dept_code → VisitStatus values that indicate "waiting in this unit"
_UNIT_WAITING_STATUSES = {
    'GLAUC':       ['AT_GLAUCOMA'],
    'RETINA':      ['AT_RETINA'],
    'PEDS_OPH':    ['AT_PEDIATRIC'],
    'CORNEA':      ['AT_CORNEA'],
    'OCULOPLASTY': ['AT_OCULOPLASTY'],
    'NEURO_OPH':   ['AT_NEURO'],
    'UVEITIS':     ['UVEITIS'],
    'CATARACT':    ['AT_CATARACT'],
}


@login_required
def unit_nurse_queue_view(request):
    """
    Specialist Unit Nurse Queue — pre-screening workstation.

    Accessible to: CONSULTATION_NURSE, MEDICAL_DIRECTOR, SUPER_ADMIN.
    Scoped automatically to the nurse's assigned department.
    """
    user = request.user
    if not (user.is_consultation_nurse or user.is_medical_director or user.is_super_admin):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    today = timezone.localdate()
    dept = user.department
    dept_code = (user.role_department_code or (dept.code if dept else None))

    # Medical Director / Super Admin can switch departments via ?dept=
    dept_code_override = request.GET.get('dept', '').upper()
    if dept_code_override and (user.is_medical_director or user.is_super_admin):
        dept_code = dept_code_override
        from apps.departments.models import Department as _D
        dept = _D.objects.filter(code=dept_code).first()

    from apps.departments.models import Department as _Dept
    all_specialist_depts = list(
        _Dept.objects.filter(
            code__in=list(_UNIT_WAITING_STATUSES.keys()), is_active=True
        ).order_by('name')
    ) if (user.is_medical_director or user.is_super_admin) else []

    waiting_statuses = _UNIT_WAITING_STATUSES.get(dept_code, [])

    # Waiting: patients in the unit queue (returned from appointment check-in
    # or sent here by triage nurse)
    waiting_visits = []
    if waiting_statuses and dept:
        waiting_visits = list(
            Visit.objects.filter(
                visit_date__date=today,
                status__in=waiting_statuses,
                department=dept,
                is_deleted=False,
            ).select_related('patient', 'triage_nurse', 'appointment')
            .prefetch_related('patient__consents')
            .order_by('visit_date')
        )

    # In consultation: currently with doctor in this unit today
    in_consult_visits = []
    if dept:
        in_consult_visits = list(
            Visit.objects.filter(
                visit_date__date=today,
                status='IN_CONSULTATION',
                department=dept,
                is_deleted=False,
            ).select_related('patient', 'attending_doctor').order_by('-visit_date')
        )

    # Stats
    total_today = Visit.objects.filter(
        visit_date__date=today, department=dept, is_deleted=False
    ).count() if dept else 0
    done_today = Visit.objects.filter(
        visit_date__date=today, department=dept, is_deleted=False,
        status__in=['COMPLETED', 'DISCHARGED']
    ).count() if dept else 0

    # Pre-screen field definitions per unit — shown in the inline entry panel
    _UNIT_PRESCREEN_FIELDS = {
        'GLAUC': [
            ('iop_right', 'IOP Right (mmHg)', 'number'),
            ('iop_left',  'IOP Left (mmHg)',  'number'),
            ('va_right',  'VA Right',          'text'),
            ('va_left',   'VA Left',           'text'),
            ('vf_done',   'Visual Fields Done?','checkbox'),
            ('pachymetry_right', 'Pachymetry R (µm)', 'number'),
            ('pachymetry_left',  'Pachymetry L (µm)', 'number'),
        ],
        'RETINA': [
            ('va_right',  'VA Right',               'text'),
            ('va_left',   'VA Left',                'text'),
            ('oct_done',  'OCT Done?',              'checkbox'),
            ('ffa_done',  'FFA Done?',              'checkbox'),
            ('iop_right', 'IOP Right (mmHg)',       'number'),
            ('iop_left',  'IOP Left (mmHg)',        'number'),
        ],
        'PEDS_OPH': [
            ('va_right',      'VA Right',           'text'),
            ('va_left',       'VA Left',            'text'),
            ('cover_test',    'Cover Test Result',  'text'),
            ('iop_right',     'IOP Right',          'number'),
            ('iop_left',      'IOP Left',           'number'),
            ('cycloplegic',   'Cycloplegia done?',  'checkbox'),
        ],
        'CORNEA': [
            ('va_right',  'VA Right',               'text'),
            ('va_left',   'VA Left',                'text'),
            ('iop_right', 'IOP Right',              'number'),
            ('iop_left',  'IOP Left',               'number'),
            ('topo_done', 'Corneal Topo Done?',     'checkbox'),
        ],
        'CATARACT': [
            ('va_right',  'BCVA Right',             'text'),
            ('va_left',   'BCVA Left',              'text'),
            ('iop_right', 'IOP Right',              'number'),
            ('iop_left',  'IOP Left',               'number'),
            ('biometry',  'Biometry Done?',         'checkbox'),
        ],
    }
    prescreen_fields = _UNIT_PRESCREEN_FIELDS.get(dept_code, [
        ('iop_right', 'IOP Right (mmHg)', 'number'),
        ('iop_left',  'IOP Left (mmHg)',  'number'),
        ('va_right',  'VA Right',         'text'),
        ('va_left',   'VA Left',          'text'),
    ])

    return render(request, 'consultations/unit_queue.html', {
        'dept': dept,
        'dept_code': dept_code,
        'all_specialist_depts': all_specialist_depts,
        'waiting_visits': waiting_visits,
        'in_consult_visits': in_consult_visits,
        'waiting_count': len(waiting_visits),
        'in_consult_count': len(in_consult_visits),
        'total_today': total_today,
        'done_today': done_today,
        'today': today,
        'prescreen_fields': prescreen_fields,
    })


@json_error_handler
@login_required
@require_POST
def unit_prescreen_save_view(request, visit_pk):
    """
    AJAX: Save pre-screening data entered by unit nurse into Visit.vital_signs,
    then mark patient as ready for doctor (status → IN_CONSULTATION).
    """
    user = request.user
    if not (user.is_consultation_nurse or user.is_medical_director or user.is_super_admin):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)
    data = visit.vital_signs or {}

    # Merge incoming values into vital_signs JSON
    for key, val in request.POST.items():
        if key.startswith('_') or key == 'csrfmiddlewaretoken':
            continue
        if val == 'on':
            data[key] = True
        elif val.strip():
            # Try numeric coercion
            try:
                data[key] = float(val) if '.' in val else int(val)
            except ValueError:
                data[key] = val

    # Nurse notes go into a dedicated key
    nurse_notes = request.POST.get('nurse_notes', '').strip()
    if nurse_notes:
        data['nurse_notes'] = nurse_notes

    data['prescreened_by'] = user.get_full_name()
    data['prescreened_at'] = timezone.now().isoformat()

    visit.vital_signs = data
    visit.triage_nurse = user
    visit.status = 'IN_CONSULTATION'
    visit.save(update_fields=['vital_signs', 'triage_nurse', 'status', 'updated_at'])

    # QMS: mark any unit token as SERVING
    try:
        from apps.qms.models import QueueToken, TokenStatus
        dept = visit.department
        dept_code = dept.code if dept else None
        svc_type = _DEPT_TO_QMS_SERVICE.get(dept_code) if dept_code else None
        if svc_type:
            QueueToken.objects.filter(
                patient=visit.patient,
                service_type=svc_type,
                token_date=timezone.localdate(),
                status__in=[TokenStatus.WAITING, TokenStatus.CALLED],
                is_deleted=False,
            ).update(status=TokenStatus.SERVING)
    except Exception:
        pass

    return JsonResponse({
        'success': True,
        'visit_number': visit.visit_number,
        'patient': visit.patient.full_name,
        'message': f'{visit.patient.full_name} sent to doctor.',
    })


# ── Triage skip-queue audit ───────────────────────────────────────────────────

@login_required
@require_POST
def skip_queue_reason_view(request):
    """
    Record an audit reason when a triage nurse selects a patient that is NOT
    first in the queue.  Updates the QueueToken notes and returns the triage URL.
    """
    if not request.user.can_do_triage() and not request.user.is_super_admin:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    token_id    = request.POST.get('token_id', '').strip()
    reason      = request.POST.get('reason', '').strip()
    redirect_url = request.POST.get('redirect_url', '')

    if not reason:
        return JsonResponse({'error': 'A reason is required.'}, status=400)

    if token_id:
        try:
            from apps.qms.models import QueueToken
            token = QueueToken.objects.get(pk=token_id, is_deleted=False)
            note = (
                f'[QUEUE SKIP — {request.user.get_full_name()} — {timezone.localdate()}]: {reason}'
            )
            token.notes = (note + '\n' + token.notes) if token.notes else note
            token.save(update_fields=['notes'])
        except Exception:
            pass

    return JsonResponse({'success': True, 'redirect_url': redirect_url})


# ── Doctor self-service: assign themselves to a room ─────────────────────────

@login_required
@require_POST
def my_room_assign_view(request):
    """
    Doctor assigns themselves to a consultation room (or clears their assignment).
    POST data: room_id=<uuid>  or  room_id=''  (to clear)
    Redirects back to workstation with the selected room filter applied.
    """
    if not request.user.can_create_consultation():
        return HttpResponseForbidden()

    room_id = request.POST.get('room_id', '').strip()
    from apps.departments.models import ConsultationRoom

    # Clear previous assignment first (doctor can only be in one room at a time)
    ConsultationRoom.objects.filter(assigned_doctor=request.user).update(assigned_doctor=None)

    if room_id:
        try:
            import uuid as _uuid
            room = ConsultationRoom.objects.get(pk=_uuid.UUID(room_id), is_active=True)
            room.assigned_doctor = request.user
            room.save(update_fields=['assigned_doctor'])
            messages.success(
                request,
                f'You are now assigned to Room {room.room_number} ({room.department.name}).'
            )
            return redirect(f'{request.build_absolute_uri("/consultations/workstation/")}?room_id={room.id}')
        except Exception:
            messages.error(request, 'Room not found.')
    else:
        messages.info(request, 'Room assignment cleared. Showing all department patients.')

    return redirect('consultations:workstation')


# ── Diagnosis management (AJAX-friendly POST views) ──────────────────────────

@json_error_handler
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


@json_error_handler
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


# ══════════════════════════════════════════════════════════════════════════════
# PROCEDURE RECORD — clinical procedures logged against a consultation
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def procedure_add_view(request, pk):
    """Log a clinical procedure (laser, injection, minor surgery) against a consultation."""
    if not request.user.can_create_consultation():
        return HttpResponseForbidden()

    from .models import ProcedureRecord
    consultation = get_object_or_404(Consultation, pk=pk, is_deleted=False)

    proc_type = request.POST.get('procedure_type', '').strip()
    if not proc_type:
        messages.error(request, 'Procedure type is required.')
        return redirect('consultations:detail', pk=pk)

    ProcedureRecord.objects.create(
        consultation=consultation,
        patient=consultation.patient,
        procedure_type=proc_type,
        eye=request.POST.get('eye', 'NA'),
        urgency=request.POST.get('urgency', 'ROUTINE'),
        performed_by=request.user,
        pre_iop_re=request.POST.get('pre_iop_re') or None,
        pre_iop_le=request.POST.get('pre_iop_le') or None,
        post_iop_re=request.POST.get('post_iop_re') or None,
        post_iop_le=request.POST.get('post_iop_le') or None,
        laser_energy=request.POST.get('laser_energy', '').strip(),
        drug_used=request.POST.get('drug_used', '').strip(),
        notes=request.POST.get('notes', '').strip(),
        complications=request.POST.get('complications', '').strip(),
        created_by=request.user,
    )
    messages.success(request, 'Procedure recorded successfully.')
    return redirect('consultations:detail', pk=pk)


@login_required
@require_POST
def workstation_quick_va_view(request):
    """Save Visual Acuity (OD/OS) from the workstation queue to the active consultation exam findings."""
    visit_pk = request.POST.get('visit_pk', '').strip()
    va_re    = request.POST.get('va_re', '').strip()
    va_le    = request.POST.get('va_le', '').strip()

    if not visit_pk or (not va_re and not va_le):
        return JsonResponse({'error': 'Visit and at least one VA value required.'}, status=400)

    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)
    consultation = Consultation.objects.filter(
        visit=visit, is_deleted=False
    ).order_by('-created_at').first()

    if not consultation:
        return JsonResponse({'error': 'No active consultation found for this patient.'}, status=404)

    ef = consultation.examination_findings or consultation.get_default_examination_template()
    if va_re:
        ef['visual_acuity']['right_unaided'] = va_re
    if va_le:
        ef['visual_acuity']['left_unaided'] = va_le

    consultation.examination_findings = ef
    consultation.updated_by = request.user
    consultation.save(update_fields=['examination_findings', 'updated_by', 'updated_at'])

    od_display = f'OD {va_re}' if va_re else ''
    os_display = f'OS {va_le}' if va_le else ''
    return JsonResponse({
        'success': True,
        'message': f'VA saved — {", ".join(filter(None, [od_display, os_display]))}',
    })


@login_required
@require_POST
def surgical_request_add_view(request, pk):
    """Create a surgical theatre request from an OPD consultation."""
    from .models import SurgicalRequest
    if not request.user.can_create_consultation():
        return HttpResponseForbidden()

    consultation = get_object_or_404(Consultation, pk=pk, is_deleted=False)
    surgery_type = request.POST.get('surgery_type', '').strip()
    if not surgery_type:
        messages.error(request, 'Surgery type is required.')
        return redirect('consultations:detail', pk=pk)

    SurgicalRequest.objects.create(
        consultation=consultation,
        patient=consultation.patient,
        surgery_type=surgery_type,
        eye=request.POST.get('eye', 'NA'),
        urgency=request.POST.get('urgency', 'ELECTIVE'),
        requested_by=request.user,
        pre_op_notes=request.POST.get('pre_op_notes', '').strip(),
        theatre_notes=request.POST.get('theatre_notes', '').strip(),
        created_by=request.user,
    )
    messages.success(request, 'Surgical request submitted to theatre coordinator.')
    return redirect('consultations:detail', pk=pk)


@login_required
@require_POST
def surgical_request_cancel_view(request, pk, sr_pk):
    """Cancel a surgical request (own requests, or medical director)."""
    from .models import SurgicalRequest
    sr = get_object_or_404(SurgicalRequest, pk=sr_pk, consultation__pk=pk, is_deleted=False)
    if sr.requested_by != request.user and not request.user.is_medical_director:
        return HttpResponseForbidden()
    sr.status = 'CANCELLED'
    sr.save(update_fields=['status', 'updated_at'])
    messages.success(request, 'Surgical request cancelled.')
    return redirect('consultations:detail', pk=pk)


@login_required
@clinical_staff_required
def discharge_summary_view(request, pk):
    """Printable one-page discharge summary for the patient to take home."""
    consultation = get_object_or_404(
        Consultation.objects.select_related(
            'patient', 'department', 'consulting_doctor', 'visit'
        ).prefetch_related(
            'consultation_diagnoses__diagnosis',
            'drug_prescriptions__items',
            'optical_prescriptions',
        ),
        pk=pk,
        is_deleted=False,
    )
    from apps.accounts.models import HospitalConfig
    hospital = HospitalConfig.get()

    diagnoses = list(consultation.consultation_diagnoses.select_related('diagnosis').all())
    drug_rxs   = list(consultation.drug_prescriptions.filter(is_deleted=False).prefetch_related('items'))
    optical_rxs = list(consultation.optical_prescriptions.filter(is_deleted=False))

    return render(request, 'consultations/discharge_summary.html', {
        'consultation': consultation,
        'hospital': hospital,
        'diagnoses': diagnoses,
        'drug_rxs': drug_rxs,
        'optical_rxs': optical_rxs,
        'patient': consultation.patient,
    })


@login_required
@require_POST
def workstation_quick_iop_view(request):
    """Save IOP (OD/OS) from the workstation queue to the active consultation exam findings."""
    visit_pk = request.POST.get('visit_pk', '').strip()
    iop_re   = request.POST.get('iop_re', '').strip()
    iop_le   = request.POST.get('iop_le', '').strip()

    if not visit_pk or (not iop_re and not iop_le):
        return JsonResponse({'error': 'Visit and at least one IOP value required.'}, status=400)

    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)

    consultation = Consultation.objects.filter(
        visit=visit, is_deleted=False
    ).order_by('-created_at').first()

    if not consultation:
        return JsonResponse({'error': 'No active consultation found for this patient.'}, status=404)

    ef = consultation.examination_findings or consultation.get_default_examination_template()
    if iop_re:
        ef['intraocular_pressure']['right'] = iop_re
    if iop_le:
        ef['intraocular_pressure']['left'] = iop_le

    consultation.examination_findings = ef
    consultation.updated_by = request.user
    consultation.save(update_fields=['examination_findings', 'updated_by', 'updated_at'])

    od_display = f'OD {iop_re} mmHg' if iop_re else ''
    os_display = f'OS {iop_le} mmHg' if iop_le else ''
    return JsonResponse({
        'success': True,
        'message': f'IOP saved — {", ".join(filter(None, [od_display, os_display]))}',
    })


@login_required
@require_POST
def procedure_delete_view(request, pk, proc_pk):
    """Delete a procedure record (own records only, or medical director)."""
    from .models import ProcedureRecord
    proc = get_object_or_404(ProcedureRecord, pk=proc_pk, consultation__pk=pk, is_deleted=False)
    if proc.performed_by != request.user and not request.user.is_medical_director:
        return HttpResponseForbidden()
    proc.is_deleted = True
    proc.save(update_fields=['is_deleted'])
    messages.success(request, 'Procedure removed.')
    return redirect('consultations:detail', pk=pk)
