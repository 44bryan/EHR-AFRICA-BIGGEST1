from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q, Count, OuterRef, Subquery, CharField
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone
from .models import Patient, Visit, MedicalHistory, PatientMedication, PatientAllergy
from .forms import PatientRegistrationForm, NextOfKinForm, MedicalHistoryForm, VitalSignsForm
from apps.core.decorators import (
    clinical_staff_required, doctor_required,
    CAN_VIEW_PATIENT, CAN_MANAGE_VISIT,
)
from apps.core.context_processors import qms_active as _qms_active


@login_required
def patient_list_view(request):
    query = request.GET.get('q', '').strip()

    # Subqueries to pull last visit date and status in a single JOIN-free query
    _latest_visit = Visit.objects.filter(
        patient=OuterRef('pk'), is_deleted=False
    ).order_by('-visit_date')

    patients = (
        Patient.objects.filter(is_active=True)
        .select_related('registered_by', 'medical_history')
        .annotate(
            last_visit_date=Subquery(_latest_visit.values('visit_date')[:1]),
            last_visit_status=Subquery(
                _latest_visit.values('status')[:1],
                output_field=CharField(),
            ),
        )
        .order_by('-registration_date')
    )

    if query:
        from apps.core.utils import patient_search_q
        patients = patients.filter(patient_search_q(query))

    from django.core.paginator import Paginator
    paginator   = Paginator(patients, 50)
    page_number = request.GET.get('page', 1)
    patients_page = paginator.get_page(page_number)
    total_count = paginator.count

    return render(request, 'patients/list.html', {
        'patients': patients_page,
        'query': query,
        'total_count': total_count,
        'paginator': paginator,
        'page_obj': patients_page,
    })


@login_required
def patient_register_view(request):
    # QMS token ID passed when arriving from receptionist queue
    qms_token_id = (
        request.GET.get('qms_token_id') or request.GET.get('token')
        or request.POST.get('qms_token_id')
    )

    if request.method == 'POST':
        form = PatientRegistrationForm(request.POST, request.FILES)
        nok_form = NextOfKinForm(request.POST, prefix='nok')
        _dob_mode = request.POST.get('dob_mode', 'exact')
        _dob_computed = request.POST.get('dob_computed', '').strip()
        _form_valid = form.is_valid()
        if _form_valid and _dob_mode == 'exact' and not form.cleaned_data.get('date_of_birth'):
            form.add_error('date_of_birth', 'Please enter the date of birth, or choose an approximation mode.')
            _form_valid = False
        if _form_valid and _dob_mode != 'exact' and not _dob_computed:
            messages.error(request, 'Please complete the date of birth section.')
            _form_valid = False
        if _form_valid:
            from django.db import transaction
            # ── Hard duplicate check — prevent double registration ────────────
            _data = form.cleaned_data
            _dup_q = Q()
            if _data.get('phone_number'):
                _dup_q |= Q(phone_number=_data['phone_number'])
            if _data.get('first_name') and _data.get('last_name') and _data.get('date_of_birth'):
                _dup_q |= Q(
                    first_name__iexact=_data['first_name'],
                    last_name__iexact=_data['last_name'],
                    date_of_birth=_data['date_of_birth'],
                )
            _existing = Patient.objects.filter(_dup_q, is_deleted=False).first() if _dup_q else None
            if _existing:
                messages.error(
                    request,
                    f'A patient with this information already exists: '
                    f'{_existing.full_name} (ID: {_existing.patient_id}). '
                    f'Use their existing record instead of registering again.'
                )
                return render(request, 'patients/register.html', {
                    'form': form,
                    'nok_form': NextOfKinForm(prefix='nok'),
                    'duplicate': _existing,
                })
            # ─────────────────────────────────────────────────────────────────
            patient = form.save(commit=False)

            # ── Approximate DOB handling ──────────────────────────────────────
            dob_mode = request.POST.get('dob_mode', 'exact')
            if dob_mode != 'exact':
                dob_computed = request.POST.get('dob_computed', '').strip()
                if dob_computed:
                    try:
                        from datetime import date as _date
                        y, m, d = map(int, dob_computed.split('-'))
                        patient.date_of_birth = _date(y, m, d)
                        patient.dob_is_approximate = True
                    except (ValueError, TypeError):
                        pass
            # ─────────────────────────────────────────────────────────────────

            # Prepend country code to phone if present
            _phone_code = request.POST.get('phone_country_code', '')
            if _phone_code and patient.phone_number and not patient.phone_number.startswith('+'):
                patient.phone_number = _phone_code + patient.phone_number

            patient.registered_by = request.user
            patient.created_by = request.user
            patient.save()

            # ── Pre-populate MedicalHistory from intake assessment ────────────
            _allergy_parts = []
            if request.POST.get('intake_nkda'):
                _allergy_parts.append('NKDA (No Known Drug Allergies)')
            if request.POST.get('intake_drug_allergy', '').strip():
                _allergy_parts.append('Drug: ' + request.POST.get('intake_drug_allergy', '').strip())
            if request.POST.get('intake_food_allergy', '').strip():
                _allergy_parts.append('Food: ' + request.POST.get('intake_food_allergy', '').strip())
            if request.POST.get('intake_env_allergy', '').strip():
                _allergy_parts.append('Environmental: ' + request.POST.get('intake_env_allergy', '').strip())
            _allergy_text = '; '.join(_allergy_parts)
            _med_flags = request.POST.getlist('intake_medical_flags')
            _cond_text = ', '.join(_med_flags)
            mh = MedicalHistory.objects.create(patient=patient, created_by=request.user)
            if _allergy_text or _cond_text:
                if _allergy_text:
                    mh.known_allergies = _allergy_text
                if _cond_text:
                    mh.chronic_conditions = _cond_text
                mh.save(update_fields=['known_allergies', 'chronic_conditions'])
            # ─────────────────────────────────────────────────────────────────
            if nok_form.is_valid() and nok_form.cleaned_data.get('full_name'):
                nok = nok_form.save(commit=False)
                nok.patient = patient
                nok.save()

            # ── Create initial Visit with consultation/registration data ──
            def _parse_bool(val):
                if val == 'true':
                    return True
                if val == 'false':
                    return False
                return None

            # Validate posted tier is within what this receptionist is allowed to register
            _posted_tier = request.POST.get('service_tier', 'STANDARD')
            _u2 = request.user
            _u2_tier = (getattr(_u2, 'patient_tier', '') or '').strip()
            _all_tiers2 = ['STANDARD', 'FAST_TRACK', 'EXPRESS', 'VIP']
            _unrestricted2 = _u2.is_super_admin or _u2.is_medical_director or _u2.is_admin_director or _u2.is_ceo
            if not _unrestricted2 and _u2_tier and _u2_tier not in ('ALL', ''):
                _allowed2 = ['EXPRESS', 'FAST_TRACK'] if _u2_tier in ('EXPRESS', 'FAST_TRACK') else [_u2_tier]
            else:
                _allowed2 = _all_tiers2
            if _posted_tier not in _allowed2:
                _posted_tier = _allowed2[0]

            visit_kwargs = dict(
                patient=patient,
                chief_complaint=request.POST.get('chief_complaint', ''),
                service_tier=_posted_tier,
                billing_type=request.POST.get('billing_type', 'SELF_PAY'),
                insurance_company=request.POST.get('insurance_company', ''),
                has_referral_letter=_parse_bool(request.POST.get('has_referral_letter')),
                referral_hospital=request.POST.get('referral_hospital', ''),
                intake_disability=','.join(request.POST.getlist('intake_disability')),
                intake_eye_complaints=','.join(request.POST.getlist('intake_eye_complaints')),
                patient_signature=request.POST.get('patient_signature', ''),
                created_by=request.user,
            )
            referral_doc = request.FILES.get('referral_document')
            if referral_doc:
                visit_kwargs['referral_document'] = referral_doc
            # QMS token provides service_tier already; only create visit if no QMS flow
            # (QMS flow creates its own visit via walk-in); create here for direct registration
            if not qms_token_id:
                initial_visit = Visit.objects.create(**visit_kwargs)

            # ── QMS handoff: complete RECEPTIONIST token → create CASHIER token ──
            counter_redirect = None
            if qms_token_id:
                try:
                    from apps.qms.models import (
                        QueueToken, DailyTokenSequence,
                        ServiceType, TokenStatus, IssuancePoint, TIER_PRIORITY,
                    )
                    recep_token = QueueToken.objects.select_related('counter').get(
                        id=qms_token_id, is_deleted=False
                    )
                    # Link the newly registered patient to the entry token
                    recep_token.patient = patient
                    recep_token.patient_name = patient.full_name
                    recep_token.save(update_fields=['patient', 'patient_name', 'updated_at'])

                    # Complete the RECEPTIONIST token and free the counter
                    recep_token.complete()
                    if recep_token.counter:
                        counter_redirect = recep_token.counter_id
                        recep_token.counter.current_serving = None
                        recep_token.counter.save(update_fields=['current_serving', 'updated_at'])

                    # Create a CASHIER token for this patient (new patient → pay first)
                    today = timezone.localdate()
                    tier = recep_token.service_tier
                    with transaction.atomic():
                        cashier_number = DailyTokenSequence.next_dept_token(ServiceType.CASHIER)
                        QueueToken.objects.create(
                            token_number=cashier_number,
                            token_date=today,
                            patient=patient,
                            patient_name=patient.full_name,
                            service_type=ServiceType.CASHIER,
                            service_tier=tier,
                            issuance_point=IssuancePoint.SYSTEM,
                            priority=TIER_PRIORITY.get(tier, 0),
                            entry_token=recep_token,
                            issued_by=request.user,
                            notes='Auto-routed after new patient registration',
                        )
                    messages.success(
                        request,
                        f'Patient {patient.full_name} registered (ID: {patient.patient_id}). '
                        f'Automatically added to Cashier queue.'
                    )
                except Exception:
                    messages.success(
                        request,
                        f'Patient {patient.full_name} registered. ID: {patient.patient_id}'
                    )
            else:
                # No QMS entry token — check if QMS is active and auto-create cashier token
                from apps.core.context_processors import qms_active
                if qms_active():
                    try:
                        from apps.qms.models import (
                            QueueToken, DailyTokenSequence,
                            ServiceType, IssuancePoint, TIER_PRIORITY,
                        )
                        _reg_tier = initial_visit.service_tier if initial_visit else 'STANDARD'
                        with transaction.atomic():
                            cashier_number = DailyTokenSequence.next_dept_token(ServiceType.CASHIER)
                            cashier_tok = QueueToken.objects.create(
                                token_number=cashier_number,
                                token_date=timezone.localdate(),
                                patient=patient,
                                patient_name=patient.full_name,
                                service_type=ServiceType.CASHIER,
                                service_tier=_reg_tier,
                                issuance_point=IssuancePoint.SYSTEM,
                                priority=TIER_PRIORITY.get(_reg_tier, 0),
                                issued_by=request.user,
                                notes='Auto-created after direct registration',
                            )
                        messages.success(
                            request,
                            f'Patient {patient.full_name} registered (ID: {patient.patient_id}). '
                            f'Cashier queue token {cashier_tok.token_number} issued — ask patient to sit and wait for their number.'
                        )
                    except Exception:
                        messages.success(request, f'Patient {patient.full_name} registered. ID: {patient.patient_id}')
                else:
                    messages.success(request, f'Patient {patient.full_name} registered. ID: {patient.patient_id}')

            # Always redirect to General Consent form first — for all patients
            # regardless of tier or QMS path. After consent, resume the appropriate flow.
            from urllib.parse import quote
            from django.urls import reverse
            if counter_redirect:
                after_consent = reverse('qms:counter', kwargs={'counter_id': counter_redirect})
            elif qms_token_id:
                after_consent = reverse('qms:receptionist')
            else:
                after_consent = f'/patients/{patient.patient_id}/'
            return redirect(
                f'/patients/{patient.patient_id}/consents/new/'
                f'?type=GENERAL&next={quote(after_consent, safe="")}'
            )
    else:
        g = request.GET
        # Do NOT pre-fill first_name with the full patient name from the QMS token
        # (putting "John Doe" in the first_name field is wrong — leave fields blank
        # so staff enter first name and last name separately)
        prefill_name = ''
        # Pre-fill from pre-registration QR scan OR from name search
        form = PatientRegistrationForm(initial={
            'first_name':     g.get('first_name') or prefill_name,
            'middle_name':    g.get('middle_name', ''),
            'last_name':      g.get('last_name', ''),
            'phone_number':   g.get('phone_number', ''),
            'date_of_birth':  g.get('date_of_birth', '') or None,
            'gender':         g.get('gender', ''),
            'marital_status': g.get('marital_status', ''),
            'email':          g.get('email', ''),
            'post_address':   g.get('post_address', ''),
            'quarter':        g.get('quarter', ''),
            'village_town':   g.get('village_town', ''),
            'division':       g.get('division', ''),
            'region':         g.get('region', ''),
            'country':        g.get('country', 'Cameroon'),
            'nationality':    g.get('nationality', 'Cameroonian'),
            'occupation':     g.get('occupation', ''),
            'religion':       g.get('religion', ''),
        })
        nok_form = NextOfKinForm(prefix='nok', initial={
            'full_name':     g.get('nok_name', ''),
            'relationship':  g.get('nok_relationship', ''),
            'phone_number':  g.get('nok_phone', ''),
        })

    # ── Tier access: any staff locked to their assigned patient_tier ──────────
    _u = request.user
    _user_tier = (getattr(_u, 'patient_tier', '') or '').strip()
    _all_tiers = ['STANDARD', 'FAST_TRACK', 'EXPRESS', 'VIP']
    _is_unrestricted = _u.is_super_admin or _u.is_medical_director or _u.is_admin_director or _u.is_ceo
    if not _is_unrestricted and _user_tier and _user_tier not in ('ALL', ''):
        if _user_tier in ('EXPRESS', 'FAST_TRACK'):
            _allowed_tiers = ['EXPRESS', 'FAST_TRACK']
        else:
            _allowed_tiers = [_user_tier]
    else:
        _allowed_tiers = _all_tiers  # admins / staff with ALL tier → see all

    # For re-rendering after a POST error, preserve submitted values; for GET, use query params
    src = request.POST if request.method == 'POST' else request.GET
    _requested_tier = src.get('service_tier', 'STANDARD')
    # If the requested tier is not in allowed, force to first allowed
    _safe_tier = _requested_tier if _requested_tier in _allowed_tiers else _allowed_tiers[0]
    return render(request, 'patients/register.html', {
        'form': form,
        'nok_form': nok_form,
        'qms_token_id': qms_token_id,
        'allowed_tiers': _allowed_tiers,
        'init_service_tier':       _safe_tier,
        'init_billing_type':       src.get('billing_type', 'SELF_PAY'),
        'init_insurance_company':  src.get('insurance_company', ''),
        'init_chief_complaint':    src.get('chief_complaint', ''),
        'init_prev_registered':    src.get('previously_registered', ''),
        'init_has_referral':       src.get('has_referral_letter', ''),
        'init_nok_name':           src.get('nok_name', ''),
        'init_nok_relationship':   src.get('nok_relationship', ''),
        'init_nok_phone':          src.get('nok_phone', ''),
    })


@login_required
@require_POST
def checkin_existing_patient(request):
    """
    When a duplicate is detected during registration, allow the receptionist to
    check-in the existing patient through the QMS flow instead of leaving the
    receptionist token stuck.

    POST params:
      - patient_id    : existing patient's patient_id string
      - qms_token_id  : the RECEPTIONIST QueueToken UUID that triggered registration
      - chief_complaint, service_tier, billing_type (optional — passed through from form)
    """
    from django.db import transaction as _tx
    patient_id_str = request.POST.get('patient_id', '').strip()
    qms_token_id   = request.POST.get('qms_token_id', '').strip()

    patient = get_object_or_404(Patient, patient_id=patient_id_str, is_deleted=False)

    counter_redirect = None
    if qms_token_id:
        try:
            from apps.qms.models import (
                QueueToken, DailyTokenSequence,
                ServiceType, TokenStatus, IssuancePoint, TIER_PRIORITY,
            )
            recep_token = QueueToken.objects.select_related('counter').get(
                id=qms_token_id, is_deleted=False
            )

            # Link the existing patient to the entry token
            recep_token.patient      = patient
            recep_token.patient_name = patient.full_name
            recep_token.save(update_fields=['patient', 'patient_name', 'updated_at'])

            # Free the counter
            if recep_token.counter:
                counter_redirect = recep_token.counter_id
                recep_token.counter.current_serving = None
                recep_token.counter.save(update_fields=['current_serving', 'updated_at'])

            # Complete the receptionist token
            recep_token.complete()

            # Apply 15-day rule:
            #   < 15 days → GENERAL queue (skip cashier, go straight to triage/clinic)
            #   ≥ 15 days → CASHIER queue (must pay for a new consultation)
            today = timezone.localdate()
            tier  = recep_token.service_tier or 'STANDARD'
            is_free_followup = patient.is_free_followup

            if is_free_followup:
                next_service = ServiceType.GENERAL
                dest_label   = 'clinic directly (FREE FOLLOW-UP — within 15 days, no payment needed)'
                token_notes  = f'Returning — {patient.consultation_visit_label} — skip cashier'
            else:
                next_service = ServiceType.CASHIER
                dest_label   = 'Cashier (consultation window expired — renewal required)'
                token_notes  = 'Returning patient — consultation expired, pay to renew'

            with _tx.atomic():
                next_number = DailyTokenSequence.next_dept_token(next_service)
                QueueToken.objects.create(
                    token_number   = next_number,
                    token_date     = today,
                    patient        = patient,
                    patient_name   = patient.full_name,
                    service_type   = next_service,
                    service_tier   = tier,
                    issuance_point = IssuancePoint.SYSTEM,
                    priority       = TIER_PRIORITY.get(tier, 0),
                    entry_token    = recep_token,
                    issued_by      = request.user,
                    issued_at      = recep_token.issued_at,  # preserve original arrival time
                    notes          = token_notes,
                )
            messages.success(
                request,
                f'{patient.full_name} checked in and routed to {dest_label}.'
            )
        except Exception as exc:
            messages.warning(request, f'Patient found but queue update failed: {exc}')
    else:
        # No QMS flow — just open the patient record
        messages.info(request, f'Opening existing record for {patient.full_name}.')

    if counter_redirect:
        return redirect('qms:counter', counter_id=counter_redirect)
    if qms_token_id:
        return redirect('qms:receptionist')
    return redirect('patients:detail', patient_id=patient.patient_id)


@login_required
@clinical_staff_required
def patient_detail_view(request, patient_id):
    from collections import defaultdict
    patient = get_object_or_404(Patient, patient_id=patient_id)
    visits = patient.visits.select_related('department', 'attending_doctor').order_by('-visit_date')[:20]
    medical_history = getattr(patient, 'medical_history', None)
    consultations = patient.consultations.filter(is_deleted=False).select_related(
        'department', 'consulting_doctor', 'visit'
    ).prefetch_related(
        'consultation_diagnoses__diagnosis',
        'optical_prescriptions',
        'drug_prescriptions__items',
        'lab_orders__items__test_type',
        'investigation_orders__investigation_type',
    ).order_by('-consultation_date')

    # Group consultations by department for tabbed display
    dept_order = [
        'General Ophthalmology', 'Retina Clinic', 'Glaucoma Clinic',
        'Cataract / Surgical', 'Refraction / Optometry', 'Pediatric Ophthalmology',
        'Cornea Clinic', 'Uveitis Clinic', 'Neuro-ophthalmology', 'Oculoplastics',
        'Eye Investigations', 'Surgical Counseling', 'VIP Consultation Room',
    ]
    dept_groups = defaultdict(list)
    for c in consultations:
        dept_name = c.department.name if c.department else 'General'
        dept_groups[dept_name].append(c)

    # Sort departments: known order first, then alphabetical remainder
    def dept_sort_key(name):
        try:
            return dept_order.index(name)
        except ValueError:
            return len(dept_order)

    consultations_by_dept = sorted(dept_groups.items(), key=lambda x: dept_sort_key(x[0]))

    # Latest optical prescription for the summary banner
    try:
        from apps.prescriptions.models import OpticalPrescription
        latest_rx = OpticalPrescription.objects.filter(
            consultation__patient=patient, is_deleted=False
        ).order_by('-prescription_date').first()
    except Exception:
        latest_rx = None

    # Surgical history
    try:
        from apps.ipd.models import SurgicalBooking, TheatreProcedure
        surgical_bookings = SurgicalBooking.objects.filter(
            patient=patient, is_deleted=False
        ).select_related('surgeon', 'consultation').order_by('-created_at')
        theatre_procedures = TheatreProcedure.objects.filter(
            patient=patient, is_deleted=False
        ).select_related('session', 'surgeon').order_by('-session__session_date')
    except Exception:
        surgical_bookings = []
        theatre_procedures = []

    # Admissions
    try:
        from apps.ipd.models import Admission
        admissions = Admission.objects.filter(
            patient=patient, is_deleted=False
        ).select_related('bed__ward', 'admitting_doctor').order_by('-admission_date')
    except Exception:
        admissions = []

    # Chronic medications
    chronic_medications = list(PatientMedication.objects.filter(
        patient=patient
    ).select_related('prescribed_by').order_by('-is_active', 'drug_name'))

    allergies = list(PatientAllergy.objects.filter(
        patient=patient, is_active=True
    ).order_by('severity', 'allergen'))

    ProblemStatus = None
    try:
        from .models import PatientProblem, ProblemStatus
        problems = list(PatientProblem.objects.filter(patient=patient).select_related('recorded_by'))
    except Exception:
        problems = []

    # Patient documents (uploaded scans / external records)
    try:
        from .models import PatientDocument
        documents = list(PatientDocument.objects.filter(
            patient=patient, is_deleted=False
        ).select_related('created_by').order_by('-created_at'))
    except Exception:
        documents = []

    # Consent records
    try:
        from .models import PatientConsent
        patient_consents = list(PatientConsent.objects.filter(
            patient=patient
        ).select_related('obtained_by').order_by('-signed_at'))
    except Exception:
        patient_consents = []

    # ── Billing history (for finance roles) ──────────────────────────────
    u = request.user
    billing_invoices = []
    billing_total_billed = 0
    billing_total_paid = 0
    billing_total_outstanding = 0
    is_finance_role = u.role in (
        'finance_director', 'billing_officer', 'accountant',
        'senior_accountant', 'chief_cashier',
    ) or u.is_super_admin or u.is_ceo or u.is_medical_director or u.is_admin_director
    if is_finance_role:
        try:
            from apps.billing.models import Invoice, InvoiceItem
            from django.db.models import Sum, F, ExpressionWrapper, DecimalField as BDec
            invoices_qs = Invoice.objects.filter(
                patient=patient, is_deleted=False
            ).prefetch_related('items').order_by('-issue_date')[:30]
            billing_invoices = list(invoices_qs)
            # Totals
            items_agg = InvoiceItem.objects.filter(
                invoice__patient=patient,
                invoice__is_deleted=False,
                is_deleted=False,
            ).aggregate(
                total=Sum(ExpressionWrapper(F('unit_price') * F('quantity'), output_field=BDec(max_digits=14, decimal_places=2)))
            )
            billing_total_billed = float(items_agg['total'] or 0)
            from apps.billing.models import Payment, Refund
            payments_agg = Payment.objects.filter(
                invoice__patient=patient, is_deleted=False
            ).aggregate(total=Sum('amount'))
            refunds_agg = Refund.objects.filter(
                invoice__patient=patient, is_deleted=False
            ).aggregate(total=Sum('amount'))
            billing_total_paid = float(payments_agg['total'] or 0) - float(refunds_agg['total'] or 0)
            billing_total_outstanding = max(0, billing_total_billed - billing_total_paid)
        except Exception:
            pass

    # Longitudinal vital signs history (last 10 visits with vitals)
    import json
    from django.core.serializers.json import DjangoJSONEncoder
    from apps.consultations.models import Consultation as _Consult
    _vs_qs = list(
        Visit.objects.filter(
            patient=patient, is_deleted=False
        ).order_by('-visit_date')[:10]
        .values('visit_date', 'visit_number', 'vital_signs', 'pk')
    )
    # Build IOP lookup from clinical consultation data (doctor-measured)
    _visit_pks = [v['pk'] for v in _vs_qs]
    _clinical_iop = {}
    for c in _Consult.objects.filter(
        visit_id__in=_visit_pks, is_deleted=False
    ).values('visit_id', 'department_specific_data'):
        dsd = c.get('department_specific_data') or {}
        iop_re = dsd.get('iop_re') or dsd.get('iop_od')
        iop_le = dsd.get('iop_le') or dsd.get('iop_os')
        if iop_re or iop_le:
            _clinical_iop[str(c['visit_id'])] = {
                'iop_re': iop_re, 'iop_le': iop_le
            }

    # Normalize: convert datetime → ISO date string so JS can parse it
    vital_signs_history = []
    for v in _vs_qs:
        vs = v['vital_signs'] or {}
        # Enrich triage vital_signs with clinical IOP if not already present
        clin = _clinical_iop.get(str(v['pk']), {})
        if clin.get('iop_re') and not vs.get('intraocular_pressure_right'):
            vs = dict(vs, intraocular_pressure_right=clin['iop_re'])
        if clin.get('iop_le') and not vs.get('intraocular_pressure_left'):
            vs = dict(vs, intraocular_pressure_left=clin['iop_le'])
        # Only include visits that have some clinical data
        if vs:
            vital_signs_history.append({
                'visit_date': v['visit_date'].date().isoformat() if v['visit_date'] else None,
                'visit_number': v['visit_number'],
                'vital_signs': vs,
            })
    vital_signs_history_json = json.dumps(vital_signs_history, cls=DjangoJSONEncoder)

    # ── Role-based permission flags for the template ─────────────────────
    is_doctor        = u.is_doctor or u.is_medical_director
    is_clinical_nurse = u.is_ward_nurse or u.is_theatre_nurse or u.is_opd_nurse or u.role == 'anaesthetist'
    is_pharma        = u.is_pharmacist or u.is_optical_dispenser
    is_admin_staff   = u.role in ('medical_records', 'receptionist') or u.is_admission_officer or u.is_super_admin
    # Billing-only staff: access patient record for invoice/insurance lookup only — no clinical tabs
    is_billing_only  = u.role == 'billing_officer' and not (is_doctor or u.is_super_admin or u.is_medical_director)

    pr = {
        # Action buttons in banner
        'can_new_consultation': u.can_create_consultation,
        'can_dispatch':         u.can_do_triage,
        'can_counsel':          u.is_counseling_nurse,
        'can_book_appointment': is_doctor or u.is_receptionist or u.is_medical_director or u.is_super_admin or u.is_ceo or u.is_admin_director,
        # JCI MOI.2: registration staff + cashiers can edit demographics (cashier corrects registration errors at POS)
        'can_edit_demographics': u.is_receptionist or u.is_cashier or u.role == 'medical_records' or u.is_super_admin or u.is_admin_director,
        'can_print_pdf':        is_doctor or u.is_medical_director or u.role == 'medical_records' or u.is_super_admin or u.is_ceo,
        'can_qr_card':          u.is_receptionist or u.is_super_admin,
        'can_full_history':     is_doctor or u.role == 'medical_records' or u.is_super_admin or u.is_medical_director,
        # Tabs — gated strictly per JCI MOI.2 / HIPAA minimum-necessary principle
        # Timeline/vitals: clinical staff only
        'tab_timeline':         is_doctor or is_clinical_nurse or u.is_opd_nurse or u.is_investigation_tech or u.is_lab_tech or u.role == 'medical_records' or u.is_super_admin or u.is_medical_director,
        'tab_dept_clinical':    is_doctor or u.role == 'medical_records' or u.is_super_admin or u.is_medical_director,
        'tab_problems':         is_doctor or u.role == 'medical_records' or u.is_super_admin or u.is_medical_director,
        # Allergies: doctors, nurses, pharmacist (drug safety), paramedicals
        'tab_allergies':        is_doctor or is_clinical_nurse or u.is_pharmacist or u.is_opd_nurse or u.role == 'medical_records' or u.is_super_admin or u.is_medical_director,
        # Medications: doctors, pharmacist, ward nurse only
        'tab_medications':      is_doctor or u.is_pharmacist or u.is_ward_nurse or u.role == 'medical_records' or u.is_super_admin or u.is_medical_director,
        # Prescriptions: doctors, pharmacist (drug dispensing), optical dispenser (spectacle Rx)
        'tab_prescriptions':    is_doctor or u.is_pharmacist or u.is_optical_dispenser or u.role == 'medical_records' or u.is_super_admin or u.is_medical_director,
        # Surgical: doctors, theatre/ward nurses, counseling nurse, anaesthetist, admission
        'tab_surgical':         is_doctor or u.is_theatre_nurse or u.is_ward_nurse or u.is_admission_officer or u.is_counseling_nurse or u.role == 'medical_records' or u.is_super_admin or u.is_medical_director,
        'tab_ipd':              is_doctor or u.is_ward_nurse or u.is_theatre_nurse or u.is_admission_officer or u.role == 'anaesthetist' or u.role == 'medical_records' or u.is_super_admin or u.is_medical_director,
        # Visit log: clinical + admin records only — NOT finance/billing (JCI MOI.2)
        'tab_visits':           is_doctor or is_clinical_nurse or u.is_opd_nurse or u.is_investigation_tech or u.is_lab_tech or u.is_pharmacist or u.is_optical_dispenser or u.is_receptionist or u.is_admission_officer or u.role == 'medical_records' or u.is_super_admin or u.is_medical_director,
        # Insurance: admin/reception/medical_records/billing officer only (billing workflow)
        'tab_insurance':        u.is_receptionist or u.role == 'medical_records' or u.is_super_admin or u.is_admin_director or u.role == 'billing_officer' or u.is_cashier,
        # Demographics: clinical + admin records — NOT CEO/admin director (aggregate reports only per JCI GLD)
        'tab_demographics':     u.is_receptionist or u.role == 'medical_records' or u.is_super_admin or is_doctor or u.is_medical_director or u.role == 'billing_officer' or u.is_cashier,
        # Billing tab: finance/billing roles only — NOT medical director or admin director (they use revenue reports)
        'tab_billing':          u.role in ('finance_director', 'billing_officer', 'accountant', 'senior_accountant', 'chief_cashier', 'cashier') or u.is_super_admin or u.is_ceo,
        # Documents: clinical + medical records only — CEO/admin director use aggregate reports (JCI MOI.2 / HIPAA)
        'tab_documents':        is_doctor or u.role == 'medical_records' or u.is_super_admin or u.is_medical_director or is_clinical_nurse,
        # Consents (JCI PFR.5): treating doctors + nurses (care continuity) + medical records (filing) + admin oversight
        'tab_consents':         is_doctor or is_clinical_nurse or u.role == 'medical_records' or u.is_super_admin or u.is_medical_director or u.role == 'admin' or u.is_admin_director or u.is_ceo,
        # Quick prescribe panel in patient record
        'show_quick_prescribe': u.can_create_consultation,
        # Inline nursing/ward actions
        'show_ward_actions':    u.is_ward_nurse or u.is_theatre_nurse or u.role == 'anaesthetist',
    }

    # ── Latest invoice payment status (shown as badge for all clinical staff) ─
    latest_invoice_status = None
    try:
        from apps.billing.models import Invoice as _Inv
        _inv = _Inv.objects.filter(
            patient=patient, is_deleted=False
        ).exclude(status__in=['CANCELLED', 'WAIVED']).order_by('-issue_date').first()
        if _inv:
            latest_invoice_status = _inv.status
    except Exception:
        pass

    # For counseling nurse: find the most recent open visit to counsel
    # (not limited by 15-day window — surgery referral may be older)
    counseling_visit = None
    if u.is_counseling_nurse:
        from apps.patients.models import Visit as _Visit
        counseling_visit = _Visit.objects.filter(
            patient=patient, is_deleted=False,
        ).exclude(status__in=['COMPLETED', 'DISCHARGED']).order_by('-visit_date').first()
        if not counseling_visit and visits:
            # All visits completed — use the most recent one anyway
            counseling_visit = visits[0] if len(visits) > 0 else None

    # Most recent active visit (or latest visit if all completed) for tier badge
    _active_visit = (
        patient.visits.filter(is_deleted=False)
        .exclude(status='COMPLETED').exclude(status='DISCHARGED')
        .order_by('-visit_date').first()
        or patient.visits.filter(is_deleted=False).order_by('-visit_date').first()
    )
    _patient_tier = _active_visit.service_tier if _active_visit else 'STANDARD'

    return render(request, 'patients/detail.html', {
        'patient': patient,
        'visits': visits,
        'active_visit': _active_visit,
        'patient_tier': _patient_tier,
        'counseling_visit': counseling_visit,
        'medical_history': medical_history,
        'next_of_kin': patient.next_of_kin.all(),
        'insurance': patient.insurance.filter(is_active=True).first(),
        'consultations': consultations,
        'consultations_by_dept': consultations_by_dept,
        'latest_rx': latest_rx,
        'surgical_bookings': surgical_bookings,
        'theatre_procedures': theatre_procedures,
        'admissions': admissions,
        'chronic_medications': chronic_medications,
        'allergies': allergies,
        'problems': problems,
        'problem_status_choices': ProblemStatus.choices if ProblemStatus else [],
        'vital_signs_history': vital_signs_history,
        'vital_signs_history_json': vital_signs_history_json,
        'allergy_severity_choices': PatientAllergy.Severity.choices,
        'allergy_type_choices': PatientAllergy.AllergyType.choices,
        'today': timezone.localdate(),
        'pr': pr,  # permission flags
        'billing_invoices': billing_invoices,
        'billing_total_billed': billing_total_billed,
        'billing_total_paid': billing_total_paid,
        'billing_total_outstanding': billing_total_outstanding,
        'latest_invoice_status': latest_invoice_status,
        'documents': documents,
        'patient_consents': patient_consents,
    })


@login_required
def patient_edit_view(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id)
    if request.method == 'POST':
        form = PatientRegistrationForm(request.POST, request.FILES, instance=patient)
        if form.is_valid():
            p = form.save(commit=False)
            p.updated_by = request.user
            p.save()
            messages.success(request, 'Patient record updated.')
            return redirect('patients:detail', patient_id=patient.patient_id)
    else:
        form = PatientRegistrationForm(instance=patient)

    return render(request, 'patients/edit.html', {'form': form, 'patient': patient})


@login_required
def medical_history_view(request, patient_id):
    patient = get_object_or_404(Patient, patient_id=patient_id)
    history, _ = MedicalHistory.objects.get_or_create(
        patient=patient,
        defaults={'created_by': request.user}
    )
    if request.method == 'POST':
        form = MedicalHistoryForm(request.POST, instance=history)
        if form.is_valid():
            h = form.save(commit=False)
            h.updated_by = request.user
            h.save()
            messages.success(request, 'Medical history updated.')
            return redirect('patients:detail', patient_id=patient.patient_id)
    else:
        form = MedicalHistoryForm(instance=history)

    return render(request, 'patients/medical_history.html', {
        'patient': patient,
        'form': form,
    })


@login_required
@clinical_staff_required
def visit_detail_view(request, visit_number):
    """9-step patient pathway journey for a single visit."""
    visit = get_object_or_404(Visit, visit_number=visit_number)
    patient = visit.patient

    consultations = visit.consultations.select_related(
        'department', 'consulting_doctor'
    ).prefetch_related(
        'consultation_diagnoses__diagnosis',
        'investigation_orders',
        'lab_orders',
        'drug_prescriptions',
        'optical_prescriptions',
    ).all()

    # ── Compute pathway step completions ──────────────────────────────────
    has_vitals = bool(
        visit.vital_signs and
        any(str(v).strip() for v in visit.vital_signs.values() if v)
    )
    has_investigations = any(
        c.investigation_orders.exists() for c in consultations
    )
    has_lab = any(c.lab_orders.exists() for c in consultations)
    has_exam = has_investigations or has_lab
    completed_consultations = [c for c in consultations if c.status == 'COMPLETED']
    has_completed_consult = len(completed_consultations) > 0
    has_prescriptions = any(c.drug_prescriptions.exists() or c.optical_prescriptions.exists() for c in consultations)

    from apps.billing.models import Invoice, InvoiceStatus
    invoices = Invoice.objects.filter(
        patient=patient, is_deleted=False
    ).filter(
        created_at__date=visit.visit_date.date()
    ).order_by('-created_at')
    has_invoice = invoices.exists()
    has_paid = invoices.filter(status__in=[InvoiceStatus.PAID, InvoiceStatus.WAIVED]).exists()

    is_discharged = visit.status == 'DISCHARGED'

    # Determine current step (1-9)
    if is_discharged:
        current_step = 9
    elif has_paid:
        current_step = 9
    elif has_invoice:
        current_step = 8
    elif has_prescriptions:
        current_step = 7
    elif has_completed_consult:
        current_step = 6
    elif len(list(consultations)) > 0:
        current_step = 5
    elif has_exam:
        current_step = 4
    elif has_vitals:
        current_step = 4
    elif visit.status == 'TRIAGE':
        current_step = 3
    else:
        current_step = 2

    steps = [
        {'n': 1, 'name': 'Reception & Orientation',     'icon': 'bi-door-open',          'done': True},
        {'n': 2, 'name': 'Registration & Identification','icon': 'bi-person-badge',        'done': True},
        {'n': 3, 'name': 'Pre-consultation / Triage',   'icon': 'bi-heart-pulse',         'done': has_vitals or current_step > 3},
        {'n': 4, 'name': 'Complementary Examinations',  'icon': 'bi-search-heart',        'done': has_exam or current_step > 4},
        {'n': 5, 'name': 'Specialized Consultation',    'icon': 'bi-clipboard2-pulse',    'done': has_completed_consult or current_step > 5},
        {'n': 6, 'name': 'Therapeutic Management',      'icon': 'bi-capsule',             'done': has_prescriptions or current_step > 6},
        {'n': 7, 'name': 'Pharmacy / Optical Service',  'icon': 'bi-bag-heart',           'done': current_step > 7},
        {'n': 8, 'name': 'Billing & Payment',           'icon': 'bi-receipt',             'done': has_paid},
        {'n': 9, 'name': 'Discharge & Follow-up',       'icon': 'bi-box-arrow-right',     'done': is_discharged},
    ]

    from apps.qms.models import ServiceType
    return render(request, 'patients/visit_detail.html', {
        'visit': visit,
        'patient': patient,
        'consultations': consultations,
        'steps': steps,
        'current_step': current_step,
        'has_vitals': has_vitals,
        'has_exam': has_exam,
        'has_completed_consult': has_completed_consult,
        'has_prescriptions': has_prescriptions,
        'invoices': invoices,
        'has_paid': has_paid,
        'is_discharged': is_discharged,
        'service_types': ServiceType.choices,
    })


@login_required
def vip_slip_view(request, visit_number):
    """Printable VIP welcome slip — shown at reception after VIP registration."""
    visit = get_object_or_404(Visit, visit_number=visit_number)
    patient = visit.patient
    return render(request, 'patients/vip_slip.html', {
        'visit': visit,
        'patient': patient,
    })


@login_required
def tier_change_log_view(request, visit_number):
    """Audit trail of all tier changes for a visit — JCI governance view."""
    u = request.user
    if not (u.is_chief_cashier or u.is_medical_director or u.is_super_admin
            or u.is_admin_director or u.is_ceo or u.is_finance_director):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    visit = get_object_or_404(Visit, visit_number=visit_number)
    from .models import VisitTierChange
    changes = VisitTierChange.objects.filter(visit=visit).select_related('changed_by')
    return render(request, 'patients/tier_change_log.html', {
        'visit': visit,
        'patient': visit.patient,
        'changes': changes,
    })


@login_required
@require_POST
def change_visit_tier_view(request, visit_number):
    """Allow cashiers, Chief Cashier or Medical Director to change the service tier of an open visit."""
    u = request.user
    _next = request.POST.get('next', '').strip()
    if not (u.is_cashier or u.is_chief_cashier or u.is_medical_director or u.is_super_admin
            or u.is_admin_director or u.is_ceo or u.is_finance_director):
        messages.error(request, "You do not have permission to change a patient's service tier.")
        return redirect(_next) if _next else redirect('patients:visit_detail', visit_number=visit_number)

    visit = get_object_or_404(Visit, visit_number=visit_number)

    from .models import ServiceTier
    new_tier = request.POST.get('service_tier', '').strip()
    if new_tier not in dict(ServiceTier.choices):
        messages.error(request, "Invalid service tier selected.")
        return redirect('patients:visit_detail', visit_number=visit_number)

    if visit.status == 'DISCHARGED':
        messages.error(request, "Cannot change tier on a discharged visit.")
        return redirect('patients:visit_detail', visit_number=visit_number)

    old_tier = visit.service_tier
    if old_tier == new_tier:
        messages.info(request, "Tier unchanged.")
        return redirect('patients:visit_detail', visit_number=visit_number)

    visit.service_tier = new_tier
    visit.save(update_fields=['service_tier'])

    # ── Audit log ─────────────────────────────────────────────────────────────
    from .models import VisitTierChange
    reason = request.POST.get('reason', '').strip()
    VisitTierChange.objects.create(
        visit=visit,
        old_tier=old_tier,
        new_tier=new_tier,
        changed_by=u,
        reason=reason,
    )

    # ── Auto-void WAITING QMS tokens for this visit and issue a new one ───────
    if _qms_active():
        try:
            from apps.qms.models import (
                QueueToken, TokenStatus, DailyTokenSequence, IssuancePoint, TIER_PRIORITY,
            )
            _TIER_TO_SERVICE = {
                'VIP':        'VIP_CONSULT',
                'EXPRESS':    'EXP_CONSULT',
                'FAST_TRACK': 'EXP_CONSULT',
                'STANDARD':   'GENERAL',
            }
            from django.db import transaction as _tier_tx
            with _tier_tx.atomic():
                # Cancel any WAITING tokens for this visit
                cancelled = QueueToken.objects.filter(
                    visit=visit,
                    status=TokenStatus.WAITING,
                ).update(status=TokenStatus.CANCELLED, notes='Tier changed — re-queued at new tier')

                # Create a new token at the correct service_type
                new_service_type = _TIER_TO_SERVICE.get(new_tier, 'GENERAL')
                token_number = DailyTokenSequence.next_dept_token(new_service_type)
                QueueToken.objects.create(
                    token_number=token_number,
                    service_type=new_service_type,
                    patient=visit.patient,
                    visit=visit,
                    service_tier=new_tier,
                    issuance_point=IssuancePoint.SYSTEM,
                    priority=TIER_PRIORITY.get(new_tier, 0),
                    status=TokenStatus.WAITING,
                    notes=f'Re-queued after tier change ({old_tier} → {new_tier}) by {u.get_full_name()}',
                    created_by=u,
                )
            if cancelled:
                messages.info(request, f'{cancelled} previous queue token(s) cancelled and re-issued at {new_tier} tier.')
        except Exception as exc:
            messages.warning(request, f'Tier updated but QMS re-queue failed: {exc}')

    messages.success(
        request,
        f"Service tier changed from {old_tier} to {new_tier} for visit {visit.visit_number}."
    )
    _next = request.POST.get('next', '').strip()
    return redirect(_next) if _next else redirect('patients:visit_detail', visit_number=visit_number)


@login_required
def triage_view(request, visit_number):
    """OPD Nurses and Medical Director record vitals and dispatch patients."""
    if not request.user.can_do_triage() and not request.user.is_super_admin:
        from django.contrib import messages as _msg
        _msg.error(request, 'Only nursing staff can record patient vitals. Check your account role.')
        return redirect('dashboard:home')

    visit = get_object_or_404(Visit, visit_number=visit_number)

    # ── Cross-tier detection ─────────────────────────────────────────────────
    _nurse_tier = getattr(request.user, 'patient_tier', 'ALL')
    _nurse_is_supervisor = (
        request.user.is_super_admin or request.user.is_medical_director
        or request.user.is_ceo or getattr(request.user, 'role', '') == 'nurse_director'
        or _nurse_tier == 'ALL'
    )
    _NURSE_COMPAT = {
        'VIP': ('VIP',), 'EXPRESS': ('EXPRESS', 'FAST_TRACK'),
        'FAST_TRACK': ('EXPRESS', 'FAST_TRACK'), 'STANDARD': ('STANDARD',),
    }
    _cross_tier = (
        not _nurse_is_supervisor
        and visit.service_tier not in _NURSE_COMPAT.get(_nurse_tier, ('VIP', 'EXPRESS', 'FAST_TRACK', 'STANDARD'))
    )

    from apps.departments.models import Department
    from apps.qms.models import ServiceType
    departments = Department.objects.filter(is_active=True).order_by('name')

    # GEN_OPH doctors for VIP/Express dispatch picker (serialized for JS)
    import json as _json
    from apps.accounts.models import User as _User, UserRole as _UserRole
    _gph_qs = list(
        _User.objects.filter(
            role=_UserRole.OPHTHALMOLOGIST,
            is_active=True,
        ).order_by('consultation_unit', 'last_name')
        .values('id', 'first_name', 'last_name', 'consultation_unit')
    )
    gph_doctors = _gph_qs
    gph_doctors_json = _json.dumps([
        {'id': str(d['id']), 'first_name': d['first_name'], 'last_name': d['last_name'],
         'consultation_unit': d['consultation_unit'] or 'GENERAL'}
        for d in _gph_qs
    ])

    # All routable destinations: departments + direct service queues
    # Nurse can pick ANY of these regardless of patient tier or path
    direct_routes = [
        {'code': 'REFRACTION',  'label': 'Refraction / TSO'},
        {'code': 'INVEST',      'label': 'Eye Investigations'},
        {'code': 'LAB',         'label': 'Laboratory'},
        {'code': 'PHARMACY',    'label': 'Pharmacy'},
        {'code': 'CASHIER',     'label': 'Cashier / Payment'},
        {'code': 'VIP_CONSULT', 'label': 'VIP Consultation Room'},
        {'code': 'EXP_CONSULT', 'label': 'Express Consultation Room'},
    ]

    # ── Payment check: patient must have paid before triage starts ──────────
    from apps.billing.models import Invoice, InvoiceStatus as _IS
    visit_date = visit.visit_date.date()
    today_invoices = Invoice.objects.filter(
        patient=visit.patient,
        is_deleted=False,
        created_at__date=visit_date,
    )
    payment_paid = today_invoices.filter(
        status__in=[_IS.PAID, _IS.WAIVED, _IS.PARTIALLY_PAID]
    ).exists()
    # Free follow-up: patient is within the 15-day consultation window — skip payment gate
    is_free_followup = visit.patient.is_free_followup
    # Payment is blocked unless they paid today OR they are within the free follow-up window
    payment_blocked = not payment_paid and not is_free_followup

    if request.method == 'POST':
        # Emergency override: nurse ticks "Emergency" checkbox to bypass payment
        is_emergency = bool(request.POST.get('emergency_override'))
        if payment_blocked and not is_emergency:
            messages.error(
                request,
                f'{visit.patient.full_name} has not paid yet. '
                'Direct the patient to the cashier first, or tick "Emergency" to override.'
            )
            form = VitalSignsForm(initial=visit.vital_signs)
            patient = visit.patient
            med_history = getattr(patient, 'medical_history', None)
            prev_visit = Visit.objects.filter(
                patient=patient, is_deleted=False,
            ).exclude(pk=visit.pk).exclude(vital_signs={}).order_by('-visit_date').first()
            return render(request, 'patients/triage.html', {
                'visit': visit, 'patient': patient, 'form': form,
                'departments': departments, 'direct_routes': direct_routes,
                'gph_doctors_json': gph_doctors_json,
                'med_history': med_history, 'prev_visit': prev_visit,
                'recent_consultations': [],
                'payment_blocked': True,
            })
        if is_emergency and payment_blocked:
            # Flag the visit as emergency-bypassed for audit
            existing_notes = visit.nursing_notes or ''
            if 'EMERGENCY OVERRIDE' not in existing_notes:
                visit.nursing_notes = (
                    f'[EMERGENCY OVERRIDE — triage started without payment by '
                    f'{request.user.get_full_name()} on {timezone.localdate()}]\n' + existing_notes
                )
                visit.save(update_fields=['nursing_notes', 'updated_at'])

        form = VitalSignsForm(request.POST)
        dept_id        = request.POST.get('dispatch_department', '').strip()
        _direct_raw    = request.POST.get('dispatch_direct', '').strip()
        # Room number may be appended as "GENERAL|ROOM:2" by the JS room picker
        _room_num = ''
        if '|ROOM:' in _direct_raw:
            _parts = _direct_raw.split('|ROOM:', 1)
            direct_service = _parts[0]
            _room_num = _parts[1].strip()
        else:
            direct_service = _direct_raw
        priority       = request.POST.get('priority', 'NORMAL')

        if form.is_valid():
            cd = form.cleaned_data

            # ── Cross-tier audit guard ───────────────────────────────────────
            if _cross_tier:
                _ct_reason = request.POST.get('cross_tier_reason', '').strip()
                if len(_ct_reason) < 10:
                    messages.error(
                        request,
                        'A reason (minimum 10 characters) is required to triage a patient '
                        'outside your assigned tier.'
                    )
                    return redirect('patients:triage', visit_number=visit.visit_number)
                _ct_change_tier = request.POST.get('change_patient_tier') == '1'
                from apps.accounts.models import UserAuditLog as _UAL
                _UAL.log(
                    user=request.user,
                    action=_UAL.Action.UPDATE_RECORD,
                    target_model='Visit',
                    target_id=str(visit.pk),
                    extra_data={
                        'action_type': 'CROSS_TIER_TRIAGE',
                        'nurse_tier': _nurse_tier,
                        'patient_tier': visit.service_tier,
                        'reason': _ct_reason,
                        'tier_changed': _ct_change_tier,
                        'new_tier': _nurse_tier if _ct_change_tier else None,
                    },
                    request=request,
                )
                if _ct_change_tier:
                    visit.service_tier = _nurse_tier
            else:
                _ct_change_tier = False

            vitals = {k: str(v) for k, v in cd.items() if v not in (None, '', 'None')}
            visit.vital_signs = vitals
            visit.status = 'TRIAGE'
            visit.triage_nurse = request.user
            nursing_notes = request.POST.get('nursing_notes', '').strip()
            if _room_num:
                room_note = f'[Dispatched to Room {_room_num}]'
                nursing_notes = (room_note + '\n' + nursing_notes).strip() if nursing_notes else room_note
            if nursing_notes:
                visit.nursing_notes = nursing_notes
            pre_auth = request.POST.get('pre_auth_status', '').strip()
            if pre_auth:
                visit.pre_auth_status = pre_auth

            dept = None
            # Map service type → visit status (used for both dept and direct routes)
            _SERVICE_TO_VISIT_STATUS = {
                'GENERAL':    'WAITING',
                'REFRACTION': 'REFRACTION',
                'RETINA':     'AT_RETINA',
                'GLAUCOMA':   'AT_GLAUCOMA',
                'PEDIATRIC':  'AT_PEDIATRIC',
                'CORNEA':     'AT_CORNEA',
                'OCULOPLASTY':'AT_OCULOPLASTY',
                'NEURO':      'NEURO',
                'CATARACT':   'CATARACT',
                'UVEITIS':    'UVEITIS',
                'INVEST':     'INVESTIGATION',
                'LAB':        'WAITING',
                'PHARMACY':   'WAITING',
                'CASHIER':    'WAITING',
                'GEN_PHYS':   'WAITING',
                'VIP_CONSULT':'WAITING',
                'EXP_CONSULT':'WAITING',
            }
            _SERVICE_TO_DEPT_CODE = {
                'REFRACTION':  'REFRAC',
                'GENERAL':     'GEN_OPH',
                'VIP_CONSULT': 'GEN_OPH',   # VIP consultation → General Ophthalmology dept
                'EXP_CONSULT': 'GEN_OPH',   # Express consultation → General Ophthalmology dept
                'RETINA':      'RETINA',
                'GLAUCOMA':    'GLAUC',
                'PEDIATRIC':   'PEDS_OPH',
                'CORNEA':      'CORNEA',
                'OCULOPLASTY': 'OCULOPLASTY',
                'NEURO':       'NEURO_OPH',
                'CATARACT':    'CATARACT',
                'UVEITIS':     'UVEITIS',
                'INVEST':      'INVEST',
                'LAB':         'LAB',
                'PHARMACY':    'PHARMACY',
                'GEN_PHYS':    'GEN_PHYS',
            }

            # Dispatch: assign to the selected department
            if dept_id:
                try:
                    dept = Department.objects.get(pk=dept_id)
                    visit.department = dept
                    # Derive appropriate visit status from dept code
                    svc = {v: k for k, v in _SERVICE_TO_DEPT_CODE.items()}.get(dept.code)
                    visit.status = _SERVICE_TO_VISIT_STATUS.get(svc, 'WAITING')
                except Department.DoesNotExist:
                    pass

            # If dispatched via direct service, resolve dept + status from service type
            if not dept and direct_service:
                dept_code = _SERVICE_TO_DEPT_CODE.get(direct_service)
                if dept_code:
                    resolved = Department.objects.filter(code=dept_code).first()
                    if resolved:
                        dept = resolved
                        visit.department = dept
                visit.status = _SERVICE_TO_VISIT_STATUS.get(direct_service, 'WAITING')

            # Store priority in vital_signs JSON for queue ordering
            if priority != 'NORMAL':
                vitals['priority'] = priority
                visit.vital_signs = vitals

            # ── Doctor assignment and service_type — init BEFORE room block ────────
            _assigned_doctor_id = request.POST.get('assigned_doctor_id', '').strip()
            _assigned_doctor = None
            if _assigned_doctor_id:
                from apps.accounts.models import User as _DocUser
                _assigned_doctor = _DocUser.objects.filter(pk=_assigned_doctor_id, is_active=True).first()
            # service_type starts as direct_service; room block may refine for ALL-tier rooms
            service_type = direct_service or None
            # Tier-override: if dispatching a VIP/Express patient to a consultation
            # queue that is marked as GENERAL, promote the service_type so the token
            # lands in the correct tier queue instead of the general doctor queue.
            _TIER_SVC_OVERRIDE = {
                'VIP':        'VIP_CONSULT',
                'EXPRESS':    'EXP_CONSULT',
                'FAST_TRACK': 'EXP_CONSULT',
            }
            if service_type == 'GENERAL' and visit.service_tier in _TIER_SVC_OVERRIDE:
                service_type = _TIER_SVC_OVERRIDE[visit.service_tier]

            # Resolve QMS counter/room (nurse selected via live room board — UUID)
            _dispatched_counter = None
            if _room_num:
                try:
                    import uuid as _uuid_mod
                    _uuid_mod.UUID(_room_num)  # validates it's a UUID, not an old room number
                    from apps.qms.models import ServiceCounter as _SC
                    _dispatched_counter = _SC.objects.filter(
                        id=_room_num, is_active=True
                    ).select_related('staff_assigned').first()
                except (ValueError, AttributeError):
                    pass
                if _dispatched_counter:
                    # Auto-assign the checked-in doctor from the counter
                    if not _assigned_doctor and _dispatched_counter.is_checked_in_today:
                        _assigned_doctor = _dispatched_counter.staff_assigned
                    # Use the counter's canonical service type for the token
                    _skip_svc = {'CASHIER', 'PARAMETERS', 'PARAMS_VIP', 'RECEPTIONIST'}
                    if _dispatched_counter.service_type not in _skip_svc:
                        service_type = _dispatched_counter.service_type

            # If routing to a specific doctor's room, stamp attending_doctor on the visit
            # so the dashboard queue only shows the visit to that doctor (not the whole dept).
            # If no specific room chosen, clear attending_doctor so destination dept staff
            # can see the patient — prevents stale attending_doctor from hiding the visit.
            if _assigned_doctor:
                visit.attending_doctor = _assigned_doctor
            else:
                visit.attending_doctor = None
            _save_fields = ['vital_signs', 'status', 'triage_nurse', 'department',
                            'nursing_notes', 'pre_auth_status', 'attending_doctor', 'updated_at']
            if _ct_change_tier:
                _save_fields.append('service_tier')
            visit.save(update_fields=_save_fields)
            _notif_status = visit.status  # capture before any further changes

            # ── QMS Integration: flexible routing ─────────────────────────────
            # Priority 1: nurse picked a direct service (REFRACTION, LAB, etc.)
            # Priority 2: dept has a known service type mapping
            # Priority 3: use dept code as service type (covers future depts)

            _DEPT_TO_SERVICE_TYPE = {
                'GEN_OPH':    'GENERAL',
                'RETINA':     'RETINA',
                'GLAUC':      'GLAUCOMA',
                'PEDS_OPH':   'PEDIATRIC',
                'REFRAC':     'REFRACTION',
                'CORNEA':     'CORNEA',
                'OCULOPLASTY':'OCULOPLASTY',
                'NEURO_OPH':  'NEURO',
                'LOW_VIS':    'GENERAL',
                'CATARACT':   'CATARACT',
                'INVEST':     'INVEST',
                'LAB':        'LAB',
                'PHARMACY':   'PHARMACY',
                'CASHIER':    'CASHIER',
            }

            # Finalize service_type: if not already set by direct_service or room block,
            # derive from department code
            if service_type is None and dept:
                service_type = _DEPT_TO_SERVICE_TYPE.get(dept.code, dept.code[:12].upper())
            # (_assigned_doctor already resolved above before room block)

            if service_type:
                from apps.qms.models import (
                    QueueToken, DailyTokenSequence, IssuancePoint,
                    TIER_PRIORITY, TokenStatus,
                )
                from django.utils import timezone as _tz
                from django.db import transaction as _tx
                today = _tz.localdate()
                entry_token = QueueToken.objects.filter(
                    patient=visit.patient,
                    token_date=today,
                    issuance_point__in=[
                        IssuancePoint.GATE, IssuancePoint.VIP_RECEPTION,
                        IssuancePoint.EXPRESS_DESK, IssuancePoint.CASHIER,
                    ],
                    is_deleted=False,
                ).first()

                base_priority = TIER_PRIORITY.get(visit.service_tier, 0)
                if priority == 'EMERGENCY':
                    base_priority += 100
                elif priority == 'URGENT':
                    base_priority += 50

                dest_label = direct_service or (dept.name if dept else service_type)
                with _tx.atomic():
                    # Mark the patient's PARAMETERS / PARAMS_VIP token as SERVED
                    # so they no longer appear in the triage nurse's queue
                    QueueToken.objects.filter(
                        patient=visit.patient,
                        token_date=today,
                        service_type__in=['PARAMETERS', 'PARAMS_VIP'],
                        status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                        is_deleted=False,
                    ).update(status=TokenStatus.COMPLETED)

                    # Idempotency guard: if a dispatch token already exists for
                    # this visit today, cancel it before re-dispatching.
                    # This prevents double-tap on tablet from creating two tokens.
                    QueueToken.objects.filter(
                        visit=visit,
                        token_date=today,
                        is_deleted=False,
                    ).exclude(
                        service_type__in=['PARAMETERS', 'PARAMS_VIP']
                    ).update(status=TokenStatus.CANCELLED)

                    token_number = DailyTokenSequence.next_dept_token(service_type)
                    _doctor_note = f' → Dr. {_assigned_doctor.get_full_name()}' if _assigned_doctor else ''
                    _room_note = f' → {_dispatched_counter.name}' if _dispatched_counter else ('')
                    QueueToken.objects.create(
                        token_number=token_number,
                        patient=visit.patient,
                        visit=visit,
                        patient_name=visit.patient.full_name if visit.patient else '',
                        service_type=service_type,
                        service_tier=visit.service_tier,
                        issuance_point=IssuancePoint.SYSTEM,
                        priority=base_priority,
                        entry_token=entry_token,
                        assigned_doctor=_assigned_doctor,
                        counter=_dispatched_counter,
                        notes=f'Dispatched to {dest_label}{_doctor_note}{_room_note} by {request.user.get_full_name()}. Priority: {priority}',
                        issued_by=request.user,
                    )

            # Notify WebSocket rooms AFTER QMS token is committed to DB
            # so the receiving queue page fetches data that already exists.
            try:
                from apps.core.ws_notify import notify_queue as _ws_nq
                from apps.core.patient_flow import _STATUS_ROOMS as _SR
                _ws_nq('opd')  # remove patient from triage queue
                for _rm in _SR.get(_notif_status, []):
                    _ws_nq(_rm)  # notify target department queue
            except Exception:
                pass

            dept_name = dept.name if dept else (direct_service or 'department')
            messages.success(
                request,
                f'✓ {visit.patient.full_name} — vitals saved & dispatched to {dept_name}.'
            )
            return redirect('consultations:triage_workstation')
    else:
        form = VitalSignsForm(initial=visit.vital_signs)

    patient = visit.patient

    # ── Patient history context for nurse ───────────────────────────���────────
    med_history = getattr(patient, 'medical_history', None) if patient else None

    # Last visit (excluding this one) with vitals
    prev_visit = None
    if patient:
        prev_visit = Visit.objects.filter(
            patient=patient,
            is_deleted=False,
        ).exclude(pk=visit.pk).exclude(
            vital_signs={}
        ).order_by('-visit_date').first()

    # Last 3 consultations with diagnoses
    recent_consultations = []
    if patient:
        from apps.consultations.models import Consultation
        recent_consultations = list(
            Consultation.objects.filter(
                patient=patient,
                is_deleted=False,
                status='COMPLETED',
            ).select_related(
                'department', 'consulting_doctor'
            ).prefetch_related(
                'consultation_diagnoses__diagnosis'
            ).order_by('-consultation_date')[:3]
        )

    return render(request, 'patients/triage.html', {
        'visit': visit,
        'patient': patient,
        'form': form,
        'departments': departments,
        'direct_routes': direct_routes,
        'gph_doctors_json': gph_doctors_json,
        'med_history': med_history,
        'prev_visit': prev_visit,
        'recent_consultations': recent_consultations,
        'payment_blocked': payment_blocked,
        'is_free_followup': is_free_followup,
        # Nurse's assigned tier — used by room picker to show same-tier rooms first
        'nurse_patient_tier': _nurse_tier,
        # Cross-tier audit
        'cross_tier': _cross_tier,
        'nurse_tier_display': request.user.get_patient_tier_display(),
    })


@login_required
def discharge_view(request, visit_number):
    """Step 9: Discharge patient and record follow-up instructions."""
    visit = get_object_or_404(Visit, visit_number=visit_number)
    patient = visit.patient

    from django.utils import timezone as tz
    from apps.billing.models import Invoice, InvoiceStatus

    # Check billing status
    today_invoices = Invoice.objects.filter(
        patient=patient, is_deleted=False,
        created_at__date=visit.visit_date.date()
    )
    has_unpaid = today_invoices.filter(
        status__in=[InvoiceStatus.DRAFT, InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID]
    ).exists()
    invoices = today_invoices.order_by('-created_at')
    balance_due = sum(inv.balance_due for inv in invoices)

    if request.method == 'POST':
        force_discharge = request.POST.get('force_discharge') == '1'

        # Warn if unpaid but allow override by admin/director
        if has_unpaid and not force_discharge and not (
            request.user.is_medical_director or request.user.is_admin_staff or request.user.is_super_admin
        ):
            messages.error(
                request,
                f'Cannot discharge: outstanding balance of {balance_due:,.0f} FCFA. '
                'Please settle billing first.'
            )
            return redirect('patients:discharge', visit_number=visit_number)

        discharge_notes = request.POST.get('discharge_notes', '')
        follow_up = request.POST.get('follow_up', '')
        visit.status = 'DISCHARGED'
        visit.discharge_date = tz.now()
        visit.discharge_notes = discharge_notes
        if follow_up:
            visit.discharge_notes += f'\n\nFollow-up: {follow_up}'
        visit.save(update_fields=['status', 'discharge_date', 'discharge_notes'])
        messages.success(request, f'Patient {patient.full_name} discharged successfully.')
        return redirect('patients:visit_detail', visit_number=visit.visit_number)

    return render(request, 'patients/discharge.html', {
        'visit': visit,
        'patient': patient,
        'has_unpaid': has_unpaid,
        'balance_due': balance_due,
        'invoices': invoices,
        'can_force': request.user.is_medical_director or request.user.is_admin_staff or request.user.is_super_admin,
    })


@login_required
@require_GET
def duplicate_check_api(request):
    """
    AJAX endpoint: check for potential duplicate patients before registration.
    Searches by phone number OR (first_name + last_name + DOB).
    Returns up to 5 matches so the receptionist can decide whether to proceed.
    """
    phone     = request.GET.get('phone', '').strip()
    first     = request.GET.get('first_name', '').strip()
    last      = request.GET.get('last_name', '').strip()
    dob       = request.GET.get('dob', '').strip()

    if not phone and not (first and last):
        return JsonResponse({'duplicates': []})

    qs = Patient.objects.filter(is_active=True)
    conditions = Q()
    if phone:
        conditions |= Q(phone_number=phone)
    if first and last:
        conditions |= Q(first_name__iexact=first, last_name__iexact=last)
        if dob:
            conditions |= Q(first_name__iexact=first, last_name__iexact=last, date_of_birth=dob)

    matches = qs.filter(conditions).values(
        'patient_id', 'first_name', 'last_name', 'date_of_birth', 'phone_number', 'gender'
    )[:5]

    from apps.core.utils import calculate_age
    results = []
    for p in matches:
        results.append({
            'patient_id': p['patient_id'],
            'name': f"{p['first_name']} {p['last_name']}",
            'dob': str(p['date_of_birth']),
            'age': calculate_age(p['date_of_birth']),
            'phone': p['phone_number'],
            'gender': p['gender'],
            'url': f"/patients/{p['patient_id']}/",
        })
    return JsonResponse({'duplicates': results})


@login_required
@require_GET
def patient_search_api(request):
    """AJAX endpoint: returns JSON list of matching patients for autocomplete."""
    query = request.GET.get('q', '').strip()
    exact = request.GET.get('exact', '0') == '1'
    if len(query) < 2:
        return JsonResponse({'results': []})

    from apps.core.utils import calculate_age
    from django.utils import timezone

    if exact:
        patients = Patient.objects.filter(
            is_active=True
        ).filter(
            Q(patient_id__iexact=query) |
            Q(phone_number__iexact=query)
        ).prefetch_related('visits')[:5]
    else:
        from apps.core.utils import patient_search_q
        from django.db.models import Prefetch
        from datetime import date as _date
        _today_date = _date.today()
        patients = Patient.objects.filter(
            is_active=True
        ).filter(patient_search_q(query)).prefetch_related(
            Prefetch(
                'visits',
                queryset=Visit.objects.filter(is_deleted=False).order_by('-visit_date'),
                to_attr='_prefetched_visits',
            )
        )[:10]
        # Force evaluation so prefetch runs once for all patients
        patients = list(patients)

    today = timezone.localdate()

    # Prefetch today's appointments for all matched patients in one query
    try:
        from apps.appointments.models import Appointment
        appt_map = {}
        patient_ids = [p.id for p in patients]
        for appt in Appointment.objects.filter(
            patient_id__in=patient_ids,
            appointment_date=today,
        ).select_related('doctor', 'department').order_by('appointment_time'):
            if appt.patient_id not in appt_map:
                appt_map[appt.patient_id] = appt
    except Exception:
        appt_map = {}

    # Prefetch today's pre-registrations by phone
    try:
        from apps.patients.models import PreRegistration
        prereg_phones = {
            pr.data.get('phone_number', '').strip(): pr
            for pr in PreRegistration.objects.filter(
                visit_date=today,
                status__in=[PreRegistration.Status.PENDING, PreRegistration.Status.ARRIVED],
            )
        }
    except Exception:
        prereg_phones = {}

    # ── VIP isolation: exclude VIP patients from non-VIP staff search ────────
    # Staff whose counter is in the VIP zone (or supervisors) can see VIP patients.
    # Everyone else must not see patients with an active VIP visit today.
    _SEARCH_UNRESTRICTED_ROLES = {'super_admin', 'medical_director', 'ceo', 'admin_director', 'admin'}
    _hide_vip = False
    if request.user.role not in _SEARCH_UNRESTRICTED_ROLES:
        try:
            from apps.qms.models import ServiceCounter as _SC
            _counter = _SC.objects.filter(
                staff_assigned=request.user, is_active=True
            ).select_related('zone').first()
            _in_vip_zone = _counter and _counter.zone and _counter.zone.code == 'VIP'
            _hide_vip = not _in_vip_zone
        except Exception:
            pass

    _vip_patient_ids = set()
    if _hide_vip:
        try:
            from apps.patients.models import Visit as _Visit
            _vip_visits = _Visit.objects.filter(
                service_tier='VIP',
                visit_date=today,
                status__in=['WAITING', 'IN_CONSULTATION', 'PARAMETERS', 'CASHIER'],
                is_deleted=False,
            ).values_list('patient_id', flat=True)
            _vip_patient_ids = set(_vip_visits)
        except Exception:
            pass

    results = []
    for p in patients:
        # Skip VIP patients if staff is not in VIP zone
        if _hide_vip and p.id in _vip_patient_ids:
            continue
        # Use prefetch cache — avoids per-patient DB queries
        cached_visits = getattr(p, '_prefetched_visits', None)
        if cached_visits is None:
            # exact=True path: no prefetch, fall back to queryset
            cached_visits = list(p.visits.filter(is_deleted=False).order_by('-visit_date'))
        has_any_visit = bool(cached_visits)
        # Check free follow-up using cached visits (no DB hit)
        active_visit = next(
            (v for v in cached_visits if v.consultation_valid_until and v.consultation_valid_until >= _today_date),
            None,
        )
        is_free = active_visit is not None
        if not has_any_visit:
            status = 'NEW'
            status_label = 'New Patient'
        elif is_free:
            status = 'FREE_FOLLOWUP'
            # Build label from cached visit — no DB hit
            from apps.accounts.models import HospitalConfig as _HC
            _cfg = _HC.get()
            _days_remaining = (active_visit.consultation_valid_until - _today_date).days
            _days_ago = _cfg.consultation_days - _days_remaining
            status_label = (
                f'FREE FOLLOW-UP ({_days_ago} day{"s" if _days_ago != 1 else ""} ago'
                f' — {_days_remaining} day{"s" if _days_remaining != 1 else ""} remaining)'
            )
        else:
            status = 'RETURNING'
            status_label = 'Returning — pay consultation'

        # Today's appointment info
        appt = appt_map.get(p.id)
        appt_info = None
        if appt:
            doctor_name = appt.doctor.get_full_name() if appt.doctor else 'Doctor'
            dept_name   = appt.department.name if appt.department else ''
            time_str    = appt.appointment_time.strftime('%H:%M') if appt.appointment_time else ''
            appt_info   = {
                'id': str(appt.id),
                'doctor': doctor_name,
                'department': dept_name,
                'time': time_str,
                'label': f'Appointment {time_str} — {doctor_name}' + (f' ({dept_name})' if dept_name else ''),
            }

        # Pre-registration info
        prereg = prereg_phones.get(p.phone_number, None)
        prereg_info = None
        if prereg:
            prereg_info = {
                'code': prereg.code,
                'status': prereg.status,
                'status_label': prereg.get_status_display(),
            }

        results.append({
            'id': str(p.id),
            'patient_id': p.patient_id,
            'name': p.full_name,
            'full_name': p.full_name,
            'age': calculate_age(p.date_of_birth),
            'gender': p.gender,
            'phone': p.phone_number,
            'url': f"/patients/{p.patient_id}/",
            'status': status,
            'status_label': status_label,
            'appointment_today': appt_info,
            'prereg_today': prereg_info,
        })

    return JsonResponse({'results': results})


@login_required
def patient_register_ajax(request):
    """
    AJAX endpoint for the Quick Register modal on the receptionist counter.

    Accepts POST with minimal patient fields.
    If qms_token_id is supplied, completes the RECEPTIONIST token and
    creates a CASHIER token for the new patient (same as the full register flow).

    Returns JSON: {success, patient_id, patient_name, message}
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required.'}, status=405)

    from django.db import transaction

    first_name  = request.POST.get('first_name', '').strip()
    last_name   = request.POST.get('last_name', '').strip()
    date_of_birth = request.POST.get('date_of_birth', '').strip()
    gender      = request.POST.get('gender', '').strip()
    phone       = request.POST.get('phone_number', '').strip()
    address     = request.POST.get('address', 'Not provided').strip() or 'Not provided'
    qms_token_id = request.POST.get('qms_token_id', '').strip()

    if not all([first_name, last_name, date_of_birth, gender, phone]):
        return JsonResponse({'success': False, 'message': 'First name, last name, DOB, gender, and phone are required.'}, status=400)

    try:
        patient = Patient.objects.create(
            first_name=first_name,
            last_name=last_name,
            date_of_birth=date_of_birth,
            gender=gender,
            phone_number=phone,
            address=address,
            registered_by=request.user,
            created_by=request.user,
        )
        MedicalHistory.objects.create(patient=patient, created_by=request.user)
    except Exception as exc:
        return JsonResponse({'success': False, 'message': str(exc)}, status=400)

    message = f'Automatically added to Cashier queue.'

    # QMS handoff — same logic as patient_register_view
    if qms_token_id:
        try:
            from apps.qms.models import (
                QueueToken, DailyTokenSequence,
                ServiceType, TokenStatus, IssuancePoint, TIER_PRIORITY,
            )
            recep_token = QueueToken.objects.select_related('counter').get(
                id=qms_token_id, is_deleted=False
            )
            recep_token.patient = patient
            recep_token.patient_name = patient.full_name
            recep_token.save(update_fields=['patient', 'patient_name', 'updated_at'])

            recep_token.complete()
            if recep_token.counter:
                recep_token.counter.current_serving = None
                recep_token.counter.save(update_fields=['current_serving', 'updated_at'])

            today = timezone.localdate()
            tier  = recep_token.service_tier
            with transaction.atomic():
                cashier_number = DailyTokenSequence.next_dept_token(ServiceType.CASHIER)
                QueueToken.objects.create(
                    token_number=cashier_number,
                    token_date=today,
                    patient=patient,
                    patient_name=patient.full_name,
                    service_type=ServiceType.CASHIER,
                    service_tier=tier,
                    issuance_point=IssuancePoint.SYSTEM,
                    priority=TIER_PRIORITY.get(tier, 0),
                    entry_token=recep_token,
                    issued_by=request.user,
                    notes='Auto-routed after quick registration at receptionist counter',
                )
        except Exception as exc:
            message = f'Patient registered but QMS routing failed: {exc}'

    return JsonResponse({
        'success': True,
        'patient_id': patient.patient_id,
        'patient_name': patient.full_name,
        'message': message,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Virtual Receptionist — QR Check-in
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def qr_generate_view(request, patient_id):
    """Staff generates a QR code for an existing patient to self-check-in."""
    patient = get_object_or_404(Patient, patient_id=patient_id, is_deleted=False)
    import qrcode, base64
    from io import BytesIO

    checkin_url = request.build_absolute_uri(
        f'/patients/checkin/?pid={patient.patient_id}'
    )
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(checkin_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = BytesIO()
    img.save(buf, format='PNG')
    qr_data_url = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()

    return render(request, 'patients/qr_code.html', {
        'patient': patient,
        'qr_data_url': qr_data_url,
        'checkin_url': checkin_url,
    })


@login_required
def registration_card_view(request, patient_id):
    """
    Printable registration card shown immediately after new patient registration.
    Contains patient ID, name, DOB, phone and a QR code.
    Staff prints this and hands it to the patient before sending them to cashier.
    """
    patient = get_object_or_404(Patient, patient_id=patient_id, is_deleted=False)
    import qrcode as _qr, base64 as _b64
    from io import BytesIO as _BIO
    from django.conf import settings as _s
    import os as _os

    # QR encodes the patient_id so any scanner can look them up
    qr = _qr.QRCode(box_size=8, border=2, error_correction=_qr.constants.ERROR_CORRECT_M)
    qr.add_data(patient.patient_id)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = _BIO()
    img.save(buf, format='PNG')
    qr_data_url = 'data:image/png;base64,' + _b64.b64encode(buf.getvalue()).decode()

    # Embed hospital logo for offline printing
    logo_data = ''
    for _sd in getattr(_s, 'STATICFILES_DIRS', []):
        for _ext, _mime in [('svg', 'image/svg+xml'), ('png', 'image/png')]:
            _p = _os.path.join(str(_sd), 'img', f'gludd_logo.{_ext}')
            if _os.path.exists(_p):
                try:
                    with open(_p, 'rb') as _f:
                        logo_data = f'data:{_mime};base64,' + _b64.b64encode(_f.read()).decode()
                    break
                except OSError:
                    pass
        if logo_data:
            break

    # Look up the most recent cashier token created for this patient today (auto-created on registration)
    from apps.core.context_processors import qms_active
    cashier_token = None
    if qms_active():
        try:
            from apps.qms.models import QueueToken, ServiceType
            cashier_token = QueueToken.objects.filter(
                patient=patient,
                service_type=ServiceType.CASHIER,
                token_date=timezone.localdate(),
                is_deleted=False,
            ).order_by('-issued_at').first()
        except Exception:
            pass

    return render(request, 'patients/registration_card.html', {
        'patient': patient,
        'qr_data_url': qr_data_url,
        'logo_data': logo_data,
        'hospital_name': getattr(_s, 'HOSPITAL_NAME', 'EHR Africa'),
        'today': timezone.localdate(),
        'cashier_token': cashier_token,
    })


def qr_checkin_view(request):
    """
    Public self-check-in page (no login).
    GET  → show form pre-filled with patient info (if pid supplied)
    POST → create Visit + QueueToken, show confirmation with token number
    """
    pid = request.GET.get('pid', '').strip()
    patient = None
    if pid:
        patient = Patient.objects.filter(patient_id=pid, is_deleted=False, is_active=True).first()

    if request.method == 'POST':
        action = request.POST.get('action', 'existing')

        if action == 'existing':
            # returning patient check-in
            lookup = request.POST.get('lookup', '').strip()
            patient = Patient.objects.filter(
                Q(patient_id__iexact=lookup) | Q(phone_number=lookup),
                is_deleted=False, is_active=True
            ).first()
            if not patient:
                return render(request, 'patients/qr_checkin.html', {
                    'error': 'Patient not found. Please check your ID or phone number.',
                    'lookup': lookup,
                })
        else:
            # new patient self-registration
            first_name = request.POST.get('first_name', '').strip()
            last_name  = request.POST.get('last_name', '').strip()
            phone      = request.POST.get('phone_number', '').strip()
            dob        = request.POST.get('date_of_birth', '') or None
            gender     = request.POST.get('gender', 'M')
            if not first_name or not last_name or not phone:
                return render(request, 'patients/qr_checkin.html', {
                    'error': 'First name, last name, and phone number are required.',
                    'new_patient': True,
                })
            from apps.core.utils import generate_patient_id
            patient = Patient.objects.create(
                patient_id=generate_patient_id(),
                first_name=first_name,
                last_name=last_name,
                phone_number=phone,
                date_of_birth=dob,
                gender=gender,
                nationality='Cameroonian',
            )
            MedicalHistory.objects.create(patient=patient)

        # Create today's visit
        today = timezone.localdate()
        visit_type = request.POST.get('visit_type', 'NEW')
        complaint  = request.POST.get('chief_complaint', '').strip()

        existing_visit = Visit.objects.filter(
            patient=patient, visit_date=today, is_deleted=False
        ).first()

        if existing_visit:
            visit = existing_visit
            already_checked_in = True
        else:
            from apps.core.utils import generate_visit_number
            visit = Visit.objects.create(
                patient=patient,
                visit_number=generate_visit_number(),
                visit_date=today,
                visit_type=visit_type,
                chief_complaint=complaint,
                status='WAITING',
                service_tier='STANDARD',
                billing_type='SELF_PAY',
            )
            already_checked_in = False

        # Create QueueToken in REGISTRATION queue
        token = None
        if _qms_active():
            try:
                from apps.qms.models import QueueToken, ServiceType, ServiceTier as QMSTier
                if not already_checked_in:
                    token = QueueToken.objects.create(
                        patient=patient,
                        visit=visit,
                        service_type=ServiceType.REGISTRATION,
                        service_tier=QMSTier.STANDARD,
                        token_date=today,
                        priority=0,
                    )
            except Exception:
                pass

        return render(request, 'patients/qr_checkin_confirm.html', {
            'patient': patient,
            'visit': visit,
            'token': token,
            'already_checked_in': already_checked_in,
        })

    return render(request, 'patients/qr_checkin.html', {
        'patient': patient,
        'pid': pid,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Triage Start — nurse finds any patient and begins triage directly
# Creates today's visit if none exists, then redirects to triage form
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def triage_start_view(request, patient_id):
    """
    Triage nurse shortcut: given a patient_id, find today's visit and redirect
    to the triage form.  A visit is NEVER created silently on GET — the nurse
    must explicitly confirm walk-in details (POST) before a visit is created.
    """
    if not request.user.can_do_triage() and not request.user.is_super_admin:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    patient = get_object_or_404(Patient, patient_id=patient_id, is_active=True)
    today = timezone.localdate()

    # Find today's active visit
    visit = Visit.objects.filter(
        patient=patient,
        visit_date__date=today,
        is_deleted=False,
    ).exclude(status__in=['COMPLETED', 'DISCHARGED']).order_by('-visit_date').first()

    if visit:
        # Patient already has an active visit today — go straight to triage
        return redirect('patients:triage', visit_number=visit.visit_number)

    # No visit today — ask nurse to confirm walk-in before creating one
    if request.method == 'POST' and request.POST.get('walkin_confirm'):
        chief = request.POST.get('chief_complaint', '').strip()
        if not chief:
            messages.error(request, 'Chief complaint is required to create a walk-in visit.')
            return render(request, 'patients/triage_walkin_confirm.html', {'patient': patient})
        from apps.core.utils import generate_visit_number
        visit = Visit.objects.create(
            patient=patient,
            visit_number=generate_visit_number(),
            visit_date=timezone.now(),
            visit_type='NEW' if not patient.visits.filter(is_deleted=False).exists() else 'RETURN',
            chief_complaint=chief,
            status='WAITING',
            service_tier='STANDARD',
            billing_type='SELF_PAY',
            created_by=request.user,
        )
        messages.info(request, f'Walk-in visit created for {patient.full_name}.')
        return redirect('patients:triage', visit_number=visit.visit_number)

    # GET with no active visit — show confirmation form
    return render(request, 'patients/triage_walkin_confirm.html', {'patient': patient})


# ─────────────────────────────────────────────────────────────────────────────
# Online Pre-Registration (patient fills form at home, prints slip with QR code)
# ─────────────────────────────────────────────────────────────────────────────

import uuid as _uuid
import base64 as _base64
from io import BytesIO as _BytesIO


def _qr_b64(code_str):
    """Generate a QR code as a base64 PNG data URL."""
    try:
        import qrcode
        qr = qrcode.QRCode(box_size=6, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(code_str)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buf = _BytesIO()
        img.save(buf, format='PNG')
        return 'data:image/png;base64,' + _base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ''


def preregistration_view(request):
    """
    Public page — patient fills in basic info before coming to hospital.
    On submit: saves a PreRegistration record, redirects to print slip with QR code.
    No login required.
    """
    from django.conf import settings

    if request.method == 'POST':
        p = request.POST
        first_name        = p.get('first_name', '').strip()
        last_name         = p.get('last_name', '').strip()
        phone             = p.get('phone_number', '').strip()
        dob               = p.get('date_of_birth', '') or None
        gender            = p.get('gender', 'M')
        middle_name       = p.get('middle_name', '').strip()
        marital_status    = p.get('marital_status', '').strip()
        email             = p.get('email', '').strip()
        post_address      = p.get('post_address', '').strip()
        quarter           = p.get('quarter', '').strip()
        village_town      = p.get('village_town', '').strip()
        division          = p.get('division', '').strip()
        region            = p.get('region', '').strip()
        country           = p.get('country', 'Cameroon').strip()
        nationality       = p.get('nationality', 'Cameroonian').strip()
        occupation        = p.get('occupation', '').strip()
        religion          = p.get('religion', '').strip()
        blood_group       = p.get('blood_group', 'Unknown').strip()
        genotype          = p.get('genotype', 'Unknown').strip()
        nok_name          = p.get('nok_name', '').strip()
        nok_relationship  = p.get('nok_relationship', '').strip()
        nok_phone         = p.get('nok_phone', '').strip()
        complaint         = p.get('chief_complaint', '').strip()
        service_tier      = p.get('service_tier', 'STANDARD').strip()
        billing_type      = p.get('billing_type', 'SELF_PAY').strip()
        insurance_company = p.get('insurance_company', '').strip()
        previously_registered = p.get('previously_registered', '')
        has_referral_letter   = p.get('has_referral_letter', '')
        visit_date_str        = p.get('visit_date', '').strip()

        if not first_name or not last_name or not phone or not dob:
            from .forms import CAMEROON_REGIONS
            return render(request, 'patients/prereg.html', {
                'error': 'First Name, Last Name, Phone Number, and Date of Birth are required.',
                'form_data': p,
                'hospital_name':    getattr(settings, 'HOSPITAL_NAME', 'EHR Africa'),
                'hospital_address': getattr(settings, 'HOSPITAL_ADDRESS', ''),
                'hospital_phone':   getattr(settings, 'HOSPITAL_PHONE', ''),
                'regions':          CAMEROON_REGIONS[1:],
            })

        # Generate a unique pre-reg code
        code = str(_uuid.uuid4()).upper()[:12].replace('-', '')

        # Handle referral document upload — save to temp folder
        import os
        referral_doc_path = ''
        referral_doc = request.FILES.get('referral_document')
        if referral_doc and has_referral_letter == 'true':
            ext = os.path.splitext(referral_doc.name)[1].lower()
            safe_name = f'prereg_{code}{ext}'
            temp_dir = os.path.join(settings.MEDIA_ROOT, 'prereg_referrals')
            os.makedirs(temp_dir, exist_ok=True)
            temp_path = os.path.join(temp_dir, safe_name)
            with open(temp_path, 'wb+') as dest:
                for chunk in referral_doc.chunks():
                    dest.write(chunk)
            referral_doc_path = f'prereg_referrals/{safe_name}'

        # Save ALL fields to DB — any receptionist can look it up by code
        from django.utils import timezone as _tz
        import datetime as _dt
        prereg_data = {
            'code':                  code,
            'first_name':            first_name,
            'middle_name':           middle_name,
            'last_name':             last_name,
            'phone_number':          phone,
            'date_of_birth':         dob,
            'gender':                gender,
            'marital_status':        marital_status,
            'email':                 email,
            'post_address':          post_address,
            'quarter':               quarter,
            'village_town':          village_town,
            'division':              division,
            'region':                region,
            'country':               country,
            'nationality':           nationality,
            'occupation':            occupation,
            'religion':              religion,
            'blood_group':           blood_group,
            'genotype':              genotype,
            'nok_name':              nok_name,
            'nok_relationship':      nok_relationship,
            'nok_phone':             nok_phone,
            'chief_complaint':       complaint,
            'service_tier':          service_tier,
            'billing_type':          billing_type,
            'insurance_company':     insurance_company,
            'previously_registered': previously_registered,
            'has_referral_letter':   has_referral_letter,
            'referral_doc_path':     referral_doc_path,
        }
        import datetime as _dt2
        visit_date_obj = None
        try:
            visit_date_obj = _dt.date.fromisoformat(visit_date_str) if visit_date_str else None
        except ValueError:
            pass
        from .models import PreRegistration
        PreRegistration.objects.create(
            code=code,
            data=prereg_data,
            visit_date=visit_date_obj,
            expires_at=_tz.now() + _dt.timedelta(days=7),  # expires 7 days after submission
        )
        return redirect(f'/patients/prereg/{code}/slip/')

    from django.conf import settings
    from .forms import CAMEROON_REGIONS
    from .models import BloodGroup, Genotype
    return render(request, 'patients/prereg.html', {
        'hospital_name':      getattr(settings, 'HOSPITAL_NAME', 'EHR Africa'),
        'hospital_address':   getattr(settings, 'HOSPITAL_ADDRESS', ''),
        'hospital_phone':     getattr(settings, 'HOSPITAL_PHONE', ''),
        'regions':            CAMEROON_REGIONS[1:],
        'blood_group_choices': BloodGroup.choices,
        'genotype_choices':    Genotype.choices,
    })


def preregistration_slip_view(request, code):
    """
    Print slip page — shows pre-reg details + QR code.
    Patient prints this and brings to hospital.
    """
    from django.conf import settings
    import datetime
    from .models import PreRegistration

    try:
        prereg = PreRegistration.objects.get(code=code.upper())
        data = prereg.data
    except PreRegistration.DoesNotExist:
        # Fallback to session for backwards compatibility
        data = request.session.get(f'prereg_{code}')

    if not data:
        from .forms import CAMEROON_REGIONS
        return render(request, 'patients/prereg.html', {
            'error': 'Pre-registration not found or expired. Please fill the form again.',
            'hospital_name': getattr(settings, 'HOSPITAL_NAME', 'EHR Africa'),
            'regions': CAMEROON_REGIONS[1:],
        })

    qr_img = _qr_b64(code)

    # Embed logo as base64 so the slip works offline / cross-device
    import base64 as _b64, os as _os
    logo_data = ''
    static_dirs = getattr(settings, 'STATICFILES_DIRS', [])
    if static_dirs:
        for _ext, _mime in [('svg', 'image/svg+xml'), ('png', 'image/png')]:
            _logo_path = _os.path.join(str(static_dirs[0]), 'img', f'gludd_logo.{_ext}')
            if _os.path.exists(_logo_path):
                try:
                    with open(_logo_path, 'rb') as _f:
                        logo_data = f'data:{_mime};base64,' + _b64.b64encode(_f.read()).decode()
                    break
                except OSError:
                    pass

    return render(request, 'patients/prereg_slip.html', {
        'data': data,
        'code': code,
        'qr_img': qr_img,
        'hospital_name':    getattr(settings, 'HOSPITAL_NAME', 'EHR Africa'),
        'hospital_address': getattr(settings, 'HOSPITAL_ADDRESS', ''),
        'hospital_phone':   getattr(settings, 'HOSPITAL_PHONE', ''),
        'hospital_email':   getattr(settings, 'HOSPITAL_EMAIL', ''),
        'pdf_logo_url':     logo_data,
        'generated_at': datetime.datetime.now().strftime('%d %B %Y, %H:%M'),
    })


@login_required
def preregistration_lookup_view(request):
    """
    Receptionist scans / types barcode code → auto-fills registration form.
    """
    from .models import PreRegistration

    def _get_prereg_data(code):
        """Fetch from DB first, fallback to session."""
        if not code:
            return None
        try:
            prereg = PreRegistration.objects.get(code=code, is_used=False)
            if prereg.is_expired:
                return None
            return prereg.data
        except PreRegistration.DoesNotExist:
            return request.session.get(f'prereg_{code}')

    code = request.GET.get('code', '').strip().upper()
    data = _get_prereg_data(code)

    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        data = _get_prereg_data(code)
        if not data:
            messages.error(request, f'Pre-registration code "{code}" not found or expired.')
            return render(request, 'patients/prereg_lookup.html', {'code': code})

        # Check if patient already exists (by phone)
        existing = Patient.objects.filter(
            phone_number=data['phone_number'], is_deleted=False
        ).first()

        if existing:
            messages.info(
                request,
                f'Returning patient found: {existing.full_name} ({existing.patient_id}). '
                f'Pre-registration data loaded.'
            )
            return redirect(f'/patients/{existing.patient_id}/')

        # Redirect to register page with ALL pre-filled fields from pre-registration
        from urllib.parse import urlencode
        params = urlencode({k: v for k, v in {
            'first_name':           data.get('first_name', ''),
            'middle_name':          data.get('middle_name', ''),
            'last_name':            data.get('last_name', ''),
            'phone_number':         data.get('phone_number', ''),
            'date_of_birth':        data.get('date_of_birth', ''),
            'gender':               data.get('gender', 'M'),
            'marital_status':       data.get('marital_status', ''),
            'email':                data.get('email', ''),
            'post_address':         data.get('post_address', ''),
            'quarter':              data.get('quarter', ''),
            'village_town':         data.get('village_town', ''),
            'division':             data.get('division', ''),
            'region':               data.get('region', ''),
            'country':              data.get('country', 'Cameroon'),
            'nationality':          data.get('nationality', 'Cameroonian'),
            'occupation':           data.get('occupation', ''),
            'religion':             data.get('religion', ''),
            'nok_name':             data.get('nok_name', ''),
            'nok_relationship':     data.get('nok_relationship', ''),
            'nok_phone':            data.get('nok_phone', ''),
            'chief_complaint':      data.get('chief_complaint', ''),
            'billing_type':         data.get('billing_type', 'SELF_PAY'),
            'insurance_company':    data.get('insurance_company', ''),
            'previously_registered': data.get('previously_registered', ''),
            'has_referral_letter':  data.get('has_referral_letter', ''),
            'prereg_code':          code,
        }.items() if v})
        # Mark as used in DB
        try:
            PreRegistration.objects.filter(code=code).update(is_used=True)
        except Exception:
            pass
        messages.success(request, f'Pre-registration found for {data["first_name"]} {data["last_name"]}. Verify details and click Register.')
        return redirect(f'/patients/register/?{params}')

    return render(request, 'patients/prereg_lookup.html', {
        'data': data,
        'code': code,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Chronic / Long-term Medications (Medication Reconciliation)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@clinical_staff_required
def medication_add_view(request, patient_id):
    """Add a chronic medication to a patient's long-term medication list."""
    patient = get_object_or_404(Patient, patient_id=patient_id, is_active=True)
    if request.method == 'POST':
        drug_name = request.POST.get('drug_name', '').strip()
        if not drug_name:
            messages.error(request, 'Drug name is required.')
            return redirect('patients:detail', patient_id=patient_id)
        PatientMedication.objects.create(
            patient=patient,
            drug_name=drug_name,
            dose=request.POST.get('dose', '').strip(),
            frequency=request.POST.get('frequency', '').strip(),
            route=request.POST.get('route', '').strip(),
            indication=request.POST.get('indication', '').strip(),
            notes=request.POST.get('notes', '').strip(),
            is_active=True,
            prescribed_by=request.user,
        )
        messages.success(request, f'Medication "{drug_name}" added to {patient.full_name}\'s record.')
    return redirect('patients:detail', patient_id=patient_id)


@login_required
@clinical_staff_required
def medication_toggle_view(request, patient_id, med_id):
    """Toggle a chronic medication active/inactive (stop/restart)."""
    patient = get_object_or_404(Patient, patient_id=patient_id, is_active=True)
    med = get_object_or_404(PatientMedication, pk=med_id, patient=patient)
    if request.method == 'POST':
        med.is_active = not med.is_active
        med.save(update_fields=['is_active', 'updated_at'])
        status = 'restarted' if med.is_active else 'stopped'
        messages.success(request, f'Medication "{med.drug_name}" {status}.')
    return redirect('patients:detail', patient_id=patient_id)


# ─────────────────────────────────────────────────────────────────────────────
# Emergency Quick-Registration
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def emergency_register_view(request):
    """
    Fast-track registration for emergency patients.
    Requires minimal info (name + presenting complaint), immediately creates
    a Visit with EMERGENCY status and routes to triage.
    """
    if not (request.user.can_dispatch_patient() or request.user.can_create_consultation()
            or request.user.is_super_admin or request.user.is_admin_staff):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        gender = request.POST.get('gender', 'Other').strip()
        phone = request.POST.get('phone_number', '').strip()
        chief_complaint = request.POST.get('chief_complaint', '').strip()

        if not first_name or not last_name or not chief_complaint:
            messages.error(request, 'First name, last name, and chief complaint are required.')
            return render(request, 'patients/emergency_register.html', {'post': request.POST})

        from django.db import transaction
        from apps.core.utils import generate_patient_id
        from datetime import date

        with transaction.atomic():
            # Create minimal patient record
            patient = Patient.objects.create(
                first_name=first_name,
                last_name=last_name,
                gender=gender,
                phone_number=phone or 'EMERGENCY',
                date_of_birth=date(1900, 1, 1),  # placeholder — update later
                registered_by=request.user,
            )
            patient.notes = 'EMERGENCY REGISTRATION — demographics to be completed after stabilisation.'
            patient.save(update_fields=['notes'])

            visit = Visit.objects.create(
                patient=patient,
                visit_type='EMERGENCY',
                chief_complaint=chief_complaint,
                status='PARAMETERS',
                service_tier='STANDARD',
                billing_type='SELF_PAY',
                attending_doctor=request.user,
                department=request.user.department,
                created_by=request.user,
            )

        messages.success(
            request,
            f'Emergency registration complete. Visit {visit.visit_number} created. '
            'Patient sent to triage — update demographics later.'
        )
        return redirect('patients:triage', visit_number=visit.visit_number)

    return render(request, 'patients/emergency_register.html', {})


# ─────────────────────────────────────────────────────────────────────────────
# Patient Allergies
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@clinical_staff_required
def allergy_add_view(request, patient_id):
    """Record a new allergy for a patient."""
    patient = get_object_or_404(Patient, patient_id=patient_id, is_active=True)
    if request.method == 'POST':
        allergen = request.POST.get('allergen', '').strip()
        if not allergen:
            messages.error(request, 'Allergen name is required.')
            return redirect('patients:detail', patient_id=patient_id)
        PatientAllergy.objects.create(
            patient=patient,
            allergen=allergen,
            allergy_type=request.POST.get('allergy_type', 'DRUG'),
            severity=request.POST.get('severity', 'MODERATE'),
            reaction=request.POST.get('reaction', '').strip(),
            recorded_by=request.user,
        )
        messages.success(request, f'Allergy to "{allergen}" recorded.')
    return redirect('patients:detail', patient_id=patient_id)


@login_required
@clinical_staff_required
@require_POST
def allergy_delete_view(request, patient_id, allergy_id):
    """Mark an allergy as inactive (soft-delete)."""
    patient = get_object_or_404(Patient, patient_id=patient_id, is_active=True)
    PatientAllergy.objects.filter(pk=allergy_id, patient=patient).update(is_active=False)
    messages.info(request, 'Allergy removed.')
    return redirect('patients:detail', patient_id=patient_id)


# ─────────────────────────────────────────────────────────────────────────────
# Insurance Info
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def insurance_add_view(request, patient_id):
    """Add or update insurance information for a patient."""
    patient = get_object_or_404(Patient, patient_id=patient_id, is_active=True)
    if request.method == 'POST':
        provider      = request.POST.get('provider', '').strip()
        policy_number = request.POST.get('policy_number', '').strip()
        if not provider or not policy_number:
            messages.error(request, 'Provider and policy number are required.')
            return redirect('patients:detail', patient_id=patient_id)
        from .models import InsuranceInfo
        InsuranceInfo.objects.create(
            patient=patient,
            provider=provider,
            policy_number=policy_number,
            group_number=request.POST.get('group_number', '').strip(),
            plan_name=request.POST.get('plan_name', '').strip(),
            expiry_date=request.POST.get('expiry_date') or None,
            notes=request.POST.get('notes', '').strip(),
            is_active=True,
        )
        messages.success(request, f'Insurance ({provider}) added.')
    return redirect('patients:detail', patient_id=patient_id)


@login_required
@require_POST
def insurance_deactivate_view(request, patient_id, ins_id):
    """Mark an insurance record as inactive."""
    patient = get_object_or_404(Patient, patient_id=patient_id, is_active=True)
    from .models import InsuranceInfo
    InsuranceInfo.objects.filter(pk=ins_id, patient=patient).update(is_active=False)
    messages.info(request, 'Insurance record deactivated.')
    return redirect('patients:detail', patient_id=patient_id)


# ── Problem List ─────────────────────────────────────────────────────────────

@clinical_staff_required
def problem_add_view(request, patient_id):
    """Add a new problem to the patient's persistent problem list."""
    patient = get_object_or_404(Patient, patient_id=patient_id, is_active=True)
    if request.method == 'POST':
        from .models import PatientProblem, ProblemStatus
        problem_text = request.POST.get('problem', '').strip()
        if not problem_text:
            messages.error(request, 'Problem description is required.')
            return redirect('patients:detail', patient_id=patient_id)
        PatientProblem.objects.create(
            patient=patient,
            problem=problem_text,
            icd10_code=request.POST.get('icd10_code', '').strip(),
            status=request.POST.get('status', ProblemStatus.ACTIVE),
            onset_date=request.POST.get('onset_date') or None,
            notes=request.POST.get('notes', '').strip(),
            recorded_by=request.user,
        )
        messages.success(request, f'Problem "{problem_text}" added to problem list.')
    return redirect('patients:detail', patient_id=patient_id)


@clinical_staff_required
@require_POST
def problem_update_status_view(request, patient_id, problem_id):
    """Update the status of a problem (e.g., mark as resolved)."""
    from .models import PatientProblem
    patient = get_object_or_404(Patient, patient_id=patient_id, is_active=True)
    problem = get_object_or_404(PatientProblem, pk=problem_id, patient=patient)
    new_status = request.POST.get('status', '').strip()
    if new_status:
        problem.status = new_status
        if new_status == 'resolved' and not problem.resolved_date:
            from django.utils import timezone
            problem.resolved_date = timezone.now().date()
        problem.save(update_fields=['status', 'resolved_date'])
        messages.success(request, f'Problem status updated to {problem.get_status_display()}.')
    return redirect('patients:detail', patient_id=patient_id)


@clinical_staff_required
@require_POST
def problem_delete_view(request, patient_id, problem_id):
    """Remove a problem from the problem list."""
    from .models import PatientProblem
    patient = get_object_or_404(Patient, patient_id=patient_id, is_active=True)
    PatientProblem.objects.filter(pk=problem_id, patient=patient).delete()
    messages.info(request, 'Problem removed from problem list.')
    return redirect('patients:detail', patient_id=patient_id)


# ── Patient Consent (JCI PFR.5) ──────────────────────────────────────────────

@login_required
def consent_list_view(request, patient_id):
    """List all consent records for a patient — doctors, nurses, medical records, super admin, medical director."""
    u = request.user
    _allowed_roles = {
        'admin', 'consultation_nurse', 'receptionist',
        'cashier', 'admission_officer', 'medical_records', 'billing_officer',
    }
    _allowed = (u.is_doctor or u.is_medical_director or u.is_super_admin
                or u.role in _allowed_roles
                or u.is_ward_nurse or u.is_theatre_nurse or u.is_counseling_nurse
                or u.is_opd_nurse or u.is_admin_director or u.is_ceo)
    if not _allowed:
        messages.error(request, 'Access denied — consent records are restricted to authorised staff.')
        return redirect('patients:detail', patient_id=patient_id)
    patient = get_object_or_404(Patient, patient_id=patient_id, is_active=True)
    from .models import PatientConsent
    consents = PatientConsent.objects.filter(patient=patient).select_related(
        'obtained_by', 'consultation'
    ).order_by('-created_at')
    return render(request, 'patients/consent_list.html', {
        'patient': patient,
        'consents': consents,
    })


@login_required
def consent_create_view(request, patient_id):
    """Create a new informed consent record.
    General/registration consent: any front-desk or clinical staff.
    Procedure/surgical/anaesthesia consent: doctors only (JCI PFR.5).
    """
    u = request.user
    requested_type = request.GET.get('type', '') or request.POST.get('consent_type', '')
    # GENERAL consent can be taken by front-desk staff at registration.
    # All clinical consents require a doctor (JCI PFR.5).
    _front_desk_roles = {'receptionist', 'cashier', 'admission_officer', 'medical_records', 'billing_officer'}
    _is_front_desk = u.role in _front_desk_roles
    _is_clinical = u.is_doctor or u.is_medical_director or u.is_super_admin or u.role in ('admin', 'consultation_nurse') or u.is_admin_director
    if _is_front_desk and requested_type not in ('GENERAL', ''):
        messages.error(request, 'Access denied — clinical consent must be obtained by a doctor (JCI PFR.5).')
        return redirect('patients:detail', patient_id=patient_id)
    if not (_is_clinical or _is_front_desk):
        messages.error(request, 'Access denied — consent records are restricted to authorised staff.')
        return redirect('patients:detail', patient_id=patient_id)
    patient = get_object_or_404(Patient, patient_id=patient_id, is_active=True)
    from .models import PatientConsent, ConsentType

    if request.method == 'POST':
        signed_at_str = request.POST.get('signed_at', '').strip()
        signed_at = None
        if signed_at_str:
            from django.utils.dateparse import parse_datetime
            _dt = parse_datetime(signed_at_str)
            if _dt is not None:
                if timezone.is_naive(_dt):
                    _dt = timezone.make_aware(_dt)
                signed_at = _dt
        if signed_at is None:
            signed_at = timezone.now()

        consent = PatientConsent.objects.create(
            patient=patient,
            consent_type=request.POST.get('consent_type', ConsentType.GENERAL),
            procedure_name=request.POST.get('procedure_name', '').strip(),
            obtained_by=request.user,
            signed_at=signed_at or timezone.now(),
            patient_has_capacity=request.POST.get('patient_has_capacity') == 'on',
            patient_representative=request.POST.get('patient_representative', '').strip(),
            relationship_to_patient=request.POST.get('relationship_to_patient', '').strip(),
            risks_explained=request.POST.get('risks_explained', '').strip(),
            benefits_explained=request.POST.get('benefits_explained', '').strip(),
            alternatives_explained=request.POST.get('alternatives_explained', '').strip(),
            questions_answered=request.POST.get('questions_answered') == 'on',
            interpreter_used=request.POST.get('interpreter_used') == 'on',
            interpreter_name=request.POST.get('interpreter_name', '').strip(),
            witness_name=request.POST.get('witness_name', '').strip(),
            notes=request.POST.get('notes', '').strip(),
            patient_signature=request.POST.get('patient_signature', '').strip(),
            created_by=request.user,
        )
        if 'consent_document' in request.FILES:
            consent.consent_document = request.FILES['consent_document']
            consent.save(update_fields=['consent_document'])

        messages.success(request, f'Consent recorded for {patient.full_name}.')

        # Honour ?next= redirect (used by registration flow)
        next_url = request.POST.get('next', '').strip()
        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        return redirect('patients:consent_list', patient_id=patient_id)

    # GET — collect context
    prefill_type = request.GET.get('type', ConsentType.GENERAL)
    next_url = request.GET.get('next', '')
    is_registration_flow = bool(next_url)

    now = timezone.localtime(timezone.now())

    return render(request, 'patients/consent_form.html', {
        'patient': patient,
        'consent_types': ConsentType.choices,
        'prefill_type': prefill_type,
        'prefill_procedure': '',
        'prefill_text': '',
        'next_url': next_url,
        'is_registration_flow': is_registration_flow,
        'now_iso': now.strftime('%Y-%m-%dT%H:%M'),
    })


@login_required
def consent_detail_view(request, patient_id, consent_id):
    """View consent detail / handle revocation — doctors + nurses + medical records."""
    u = request.user
    _can_view = u.is_doctor or u.is_medical_director or u.is_super_admin or u.role in ('medical_records', 'admin', 'consultation_nurse') or u.is_ward_nurse or u.is_theatre_nurse or u.is_counseling_nurse or u.is_opd_nurse or u.is_admin_director or u.is_ceo
    if not _can_view:
        messages.error(request, 'Access denied.')
        return redirect('patients:detail', patient_id=patient_id)
    patient = get_object_or_404(Patient, patient_id=patient_id, is_active=True)
    from .models import PatientConsent
    consent = get_object_or_404(PatientConsent, pk=consent_id, patient=patient)

    if request.method == 'POST' and request.POST.get('action') == 'revoke':
        # Only the treating doctor or medical director can revoke (JCI PFR.5)
        if not (u.is_doctor or u.is_medical_director or u.is_super_admin or u.role == 'admin' or u.is_admin_director):
            messages.error(request, 'Only doctors can revoke a consent (JCI PFR.5).')
            return redirect('patients:consent_detail', patient_id=patient_id, consent_id=consent_id)
        reason = request.POST.get('revocation_reason', '').strip()
        consent.revoke(reason=reason)
        messages.warning(request, 'Consent revoked.')
        return redirect('patients:consent_list', patient_id=patient_id)

    return render(request, 'patients/consent_detail.html', {
        'patient': patient,
        'consent': consent,
    })


@login_required
def consent_print_view(request, patient_id, consent_id):
    """Render consent form PDF — doctors, nurses, medical records only."""
    u = request.user
    _can_print = u.is_doctor or u.is_medical_director or u.is_super_admin or u.role == 'medical_records' or u.is_ward_nurse or u.is_theatre_nurse or u.is_counseling_nurse
    if not _can_print:
        messages.error(request, 'Access denied.')
        return redirect('patients:consent_list', patient_id=patient_id)
    from apps.reports.views import render_pdf
    from django.utils import timezone as tz
    patient = get_object_or_404(Patient, patient_id=patient_id, is_active=True)
    from .models import PatientConsent
    consent = get_object_or_404(PatientConsent, pk=consent_id, patient=patient)
    context = {
        'patient': patient,
        'consent': consent,
        'issue_date': tz.localdate(),
        'pdf_filename': f'consent_{patient.patient_id}_{consent.pk.hex[:8]}.pdf',
    }
    return render_pdf('reports/pdf/consent_form.html', context)


# ── Patient Documents / Scanned Records ───────────────────────────────────────

@login_required
def document_upload_view(request, patient_id):
    """Upload a scanned or digital document to a patient's record."""
    from .models import PatientDocument
    from django.contrib import messages
    patient = get_object_or_404(Patient, patient_id=patient_id)

    if request.method == 'POST':
        title    = request.POST.get('title', '').strip()
        doc_type = request.POST.get('document_type', 'OTHER')
        source   = request.POST.get('source', 'SCAN')
        desc     = request.POST.get('description', '').strip()
        doc_date = request.POST.get('document_date') or None
        file_obj = request.FILES.get('file')

        if not title or not file_obj:
            messages.error(request, 'Title and file are required.')
        else:
            PatientDocument.objects.create(
                patient=patient,
                title=title,
                document_type=doc_type,
                source=source,
                description=desc,
                document_date=doc_date,
                file=file_obj,
                created_by=request.user,
            )
            messages.success(request, f'Document "{title}" uploaded successfully.')
        return redirect('patients:detail', patient_id=patient_id)

    return render(request, 'patients/document_upload.html', {
        'patient': patient,
        'doc_types': PatientDocument.DocType.choices,
        'source_types': PatientDocument.Source.choices,
    })


@login_required
def document_delete_view(request, patient_id, doc_id):
    """Soft-delete a patient document."""
    from .models import PatientDocument
    from django.contrib import messages
    patient  = get_object_or_404(Patient, patient_id=patient_id)
    document = get_object_or_404(PatientDocument, pk=doc_id, patient=patient, is_deleted=False)

    if request.method == 'POST':
        document.is_deleted = True
        document.save()
        messages.success(request, 'Document removed.')
    return redirect('patients:detail', patient_id=patient_id)
