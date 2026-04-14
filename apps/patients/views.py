from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q, Count
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.utils import timezone
from .models import Patient, Visit, MedicalHistory
from .forms import PatientRegistrationForm, NextOfKinForm, MedicalHistoryForm, VitalSignsForm
from apps.core.decorators import (
    clinical_staff_required, doctor_required,
    CAN_VIEW_PATIENT, CAN_MANAGE_VISIT,
)


@login_required
def patient_list_view(request):
    query = request.GET.get('q', '').strip()
    patients = Patient.objects.filter(is_active=True).order_by('-registration_date')

    if query:
        patients = patients.filter(
            Q(patient_id__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(phone_number__icontains=query)
        )

    return render(request, 'patients/list.html', {
        'patients': patients[:100],
        'query': query,
        'total_count': patients.count(),
    })


@login_required
def patient_register_view(request):
    # QMS token ID passed when arriving from receptionist counter
    qms_token_id = request.GET.get('token') or request.POST.get('qms_token_id')

    if request.method == 'POST':
        form = PatientRegistrationForm(request.POST, request.FILES)
        nok_form = NextOfKinForm(request.POST, prefix='nok')
        if form.is_valid():
            from django.db import transaction
            patient = form.save(commit=False)
            patient.registered_by = request.user
            patient.created_by = request.user
            patient.save()
            MedicalHistory.objects.create(patient=patient, created_by=request.user)
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

            visit_kwargs = dict(
                patient=patient,
                chief_complaint=request.POST.get('chief_complaint', ''),
                service_tier=request.POST.get('service_tier', 'STANDARD'),
                billing_type=request.POST.get('billing_type', 'SELF_PAY'),
                insurance_company=request.POST.get('insurance_company', ''),
                previously_registered=_parse_bool(request.POST.get('previously_registered')),
                has_referral_letter=_parse_bool(request.POST.get('has_referral_letter')),
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
                messages.success(request, f'Patient {patient.full_name} registered. ID: {patient.patient_id}')

            if counter_redirect:
                return redirect('qms:counter', counter_id=counter_redirect)
            return redirect('patients:detail', patient_id=patient.patient_id)
    else:
        g = request.GET
        # Pre-fill from pre-registration QR scan OR from name search
        form = PatientRegistrationForm(initial={
            'first_name':     g.get('first_name') or g.get('name', ''),
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

    # For re-rendering after a POST error, preserve submitted values; for GET, use query params
    src = request.POST if request.method == 'POST' else request.GET
    return render(request, 'patients/register.html', {
        'form': form,
        'nok_form': nok_form,
        'qms_token_id': qms_token_id,
        'init_service_tier':       src.get('service_tier', 'STANDARD'),
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

    return render(request, 'patients/detail.html', {
        'patient': patient,
        'visits': visits,
        'medical_history': medical_history,
        'next_of_kin': patient.next_of_kin.all(),
        'insurance': patient.insurance.filter(is_active=True).first(),
        'consultations': consultations,
        'consultations_by_dept': consultations_by_dept,
        'latest_rx': latest_rx,
        'surgical_bookings': surgical_bookings,
        'theatre_procedures': theatre_procedures,
        'admissions': admissions,
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
def triage_view(request, visit_number):
    """OPD Nurse records vitals and dispatches patient to a department — Step 3."""
    visit = get_object_or_404(Visit, visit_number=visit_number)

    from apps.departments.models import Department
    departments = Department.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        form = VitalSignsForm(request.POST)
        dept_id = request.POST.get('dispatch_department')
        priority = request.POST.get('priority', 'NORMAL')

        if form.is_valid():
            cd = form.cleaned_data
            vitals = {k: str(v) for k, v in cd.items() if v not in (None, '', 'None')}
            visit.vital_signs = vitals
            visit.status = 'TRIAGE'
            visit.triage_nurse = request.user

            dept = None
            # Dispatch: assign to the selected department
            if dept_id:
                try:
                    dept = Department.objects.get(pk=dept_id)
                    visit.department = dept
                    visit.status = 'WAITING'  # now in department queue
                except Department.DoesNotExist:
                    pass

            # Store priority in vital_signs JSON for queue ordering
            if priority != 'NORMAL':
                vitals['priority'] = priority
                visit.vital_signs = vitals

            visit.save(update_fields=['vital_signs', 'status', 'triage_nurse', 'department', 'updated_at'])

            # ── QMS Integration: create department queue token ────────────────
            # Tier-aware routing:
            #   GEN_OPH → VIP gets VIP_CONSULT room, Express/FT gets EXP_CONSULT room,
            #             Standard gets GENERAL queue
            #   Specialist depts (RETINA, GLAUCOMA, etc.) → shared queue but tier
            #             priority ensures Express/FT/VIP go ahead of Standard patients
            _TIER_CONSULT_MAP = {
                'VIP':        'VIP_CONSULT',
                'EXPRESS':    'EXP_CONSULT',
                'FAST_TRACK': 'EXP_CONSULT',
            }
            # Departments where VIP/Express get their own room
            _TIER_SEPARATED_DEPTS = {'GEN_OPH', 'LOW_VIS', 'REFRAC'}

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
            }
            if dept:
                base_service_type = _DEPT_TO_SERVICE_TYPE.get(dept.code)
                # VIP/Express get dedicated consultation rooms for GEN_OPH
                if dept.code in _TIER_SEPARATED_DEPTS and visit.service_tier in _TIER_CONSULT_MAP:
                    service_type = _TIER_CONSULT_MAP[visit.service_tier]
                else:
                    service_type = base_service_type
                if service_type:
                    from apps.qms.models import (
                        QueueToken, DailyTokenSequence, IssuancePoint,
                        TIER_PRIORITY, TokenStatus,
                    )
                    from django.utils import timezone as _tz
                    # Find entry token so display_token_number works correctly
                    today = _tz.localdate()
                    entry_token = QueueToken.objects.filter(
                        patient=visit.patient,
                        issued_at__date=today,
                        issuance_point__in=[
                            IssuancePoint.GATE, IssuancePoint.VIP_RECEPTION,
                            IssuancePoint.EXPRESS_DESK, IssuancePoint.CASHIER,
                        ],
                        is_deleted=False,
                    ).first()

                    # Priority boost for URGENT/EMERGENCY
                    base_priority = TIER_PRIORITY.get(visit.service_tier, 0)
                    if priority == 'EMERGENCY':
                        base_priority += 100
                    elif priority == 'URGENT':
                        base_priority += 50

                    token_number = DailyTokenSequence.next_dept_token(service_type)
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
                        notes=f'Dispatched from triage by {request.user.get_full_name()}. Priority: {priority}',
                        issued_by=request.user,
                    )

            dept_name = dept.name if dept else 'department'
            messages.success(
                request,
                f'Vitals recorded. {visit.patient.full_name} dispatched to {dept_name}.'
            )
            return redirect('opd:dashboard')
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
        'med_history': med_history,
        'prev_visit': prev_visit,
        'recent_consultations': recent_consultations,
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
def patient_search_api(request):
    """AJAX endpoint: returns JSON list of matching patients for autocomplete."""
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})

    patients = Patient.objects.filter(
        is_active=True
    ).filter(
        Q(patient_id__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query) |
        Q(phone_number__icontains=query)
    ).values('id', 'patient_id', 'first_name', 'last_name', 'date_of_birth', 'phone_number', 'gender')[:10]

    results = []
    for p in patients:
        from apps.core.utils import calculate_age
        age = calculate_age(p['date_of_birth'])
        full_name = f"{p['first_name']} {p['last_name']}"
        results.append({
            'id': str(p['id']),
            'patient_id': p['patient_id'],
            'name': full_name,
            'full_name': full_name,
            'age': age,
            'gender': p['gender'],
            'phone': p['phone_number'],
            'url': f"/patients/{p['patient_id']}/",
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
    Triage nurse shortcut: given a patient_id, find or create today's visit
    and redirect straight to the triage form. No queue token required.
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

    if not visit:
        # Create a new visit on the spot
        from apps.core.utils import generate_visit_number
        visit = Visit.objects.create(
            patient=patient,
            visit_number=generate_visit_number(),
            visit_date=timezone.now(),
            visit_type='RETURN',
            chief_complaint='',
            status='WAITING',
            service_tier='STANDARD',
            billing_type='SELF_PAY',
        )
        messages.info(request, f'New visit created for {patient.full_name} — please record chief complaint during triage.')

    return redirect('patients:triage', visit_number=visit.visit_number)


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
        from .models import PreRegistration
        PreRegistration.objects.create(
            code=code,
            data=prereg_data,
            expires_at=_tz.now() + _dt.timedelta(days=30),
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
    return render(request, 'patients/prereg_slip.html', {
        'data': data,
        'code': code,
        'qr_img': qr_img,
        'hospital_name': getattr(settings, 'HOSPITAL_NAME', 'EHR Africa'),
        'hospital_address': getattr(settings, 'HOSPITAL_ADDRESS', ''),
        'hospital_phone': getattr(settings, 'HOSPITAL_PHONE', ''),
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
