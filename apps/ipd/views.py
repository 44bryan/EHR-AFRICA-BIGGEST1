import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.utils import timezone
from .models import (
    Ward, Bed, Admission, NursingNote, MAREntry, BedStatus, AdmissionStatus,
    SurgicalBooking, SurgicalBookingStatus, SurgeryType,
    TheatreSession, TheatreSessionStatus, TheatreProcedure, ProcedureOutcome, WardRound,
    WardType, VitalSigns, FluidBalance, FluidEntryType,
    SurgicalOutcome, OutcomeGrade,
)
from apps.core.context_processors import qms_active as _qms_active


@login_required
def ipd_dashboard(request):
    today = timezone.localdate()
    current_admissions = Admission.objects.filter(
        status=AdmissionStatus.ADMITTED, is_deleted=False
    ).select_related('patient', 'bed__ward', 'admitting_doctor')

    today_sessions = TheatreSession.objects.filter(
        session_date=today, is_deleted=False
    ).select_related('lead_surgeon').prefetch_related('procedures')

    context = {
        'current_admissions': current_admissions,
        'total_admitted': current_admissions.count(),
        'available_beds': Bed.objects.filter(status=BedStatus.AVAILABLE, is_deleted=False).count(),
        'wards': Ward.objects.filter(is_active=True, is_deleted=False),
        'today_sessions': today_sessions,
        'today': today,
    }
    return render(request, 'ipd/dashboard.html', context)


@login_required
def ward_list(request):
    wards = Ward.objects.filter(is_active=True, is_deleted=False).prefetch_related('beds')
    return render(request, 'ipd/ward_list.html', {'wards': wards})


@login_required
def admission_detail(request, admission_id):
    admission = get_object_or_404(
        Admission.objects.select_related(
            'patient', 'bed__ward', 'admitting_doctor', 'surgical_booking'
        ),
        id=admission_id, is_deleted=False
    )
    nursing_notes = admission.nursing_notes.order_by('-note_time')[:20]
    mar_entries = admission.mar_entries.order_by('scheduled_time')
    ward_rounds = admission.ward_rounds.select_related('doctor').order_by('-round_date', '-round_time')
    return render(request, 'ipd/admission_detail.html', {
        'admission': admission,
        'nursing_notes': nursing_notes,
        'mar_entries': mar_entries,
        'ward_rounds': ward_rounds,
    })


@login_required
def add_nursing_note(request, admission_id):
    admission = get_object_or_404(Admission, id=admission_id, is_deleted=False)
    if request.method == 'POST':
        NursingNote.objects.create(
            admission=admission,
            note_type=request.POST.get('note_type', 'OBSERVATION'),
            content=request.POST.get('content', ''),
            vital_signs={
                'bp': request.POST.get('bp', ''),
                'pulse': request.POST.get('pulse', ''),
                'temp': request.POST.get('temp', ''),
                'spo2': request.POST.get('spo2', ''),
                'rr': request.POST.get('rr', ''),
            },
            nurse=request.user,
            created_by=request.user,
        )
        messages.success(request, 'Nursing note added.')
        return redirect('ipd:admission_detail', admission_id=admission.id)
    return render(request, 'ipd/add_nursing_note.html', {'admission': admission})


@login_required
def admit_patient(request):
    """Admit a patient to a ward bed."""
    from apps.patients.models import Patient

    available_beds = Bed.objects.filter(
        status=BedStatus.AVAILABLE, is_deleted=False
    ).select_related('ward').order_by('ward__name', 'bed_number')

    if request.method == 'POST':
        patient_id = request.POST.get('patient_id', '').strip()
        bed_id = request.POST.get('bed_id')
        diagnosis = request.POST.get('diagnosis_on_admission', '').strip()

        if not patient_id or not bed_id or not diagnosis:
            messages.error(request, 'Patient, bed, and diagnosis are all required.')
        else:
            try:
                patient = Patient.objects.get(patient_id=patient_id, is_active=True)
                bed = Bed.objects.get(id=bed_id, status=BedStatus.AVAILABLE)
            except Patient.DoesNotExist:
                messages.error(request, f'Patient "{patient_id}" not found.')
                return render(request, 'ipd/admit.html', {'beds': available_beds})
            except Bed.DoesNotExist:
                messages.error(request, 'Selected bed is no longer available.')
                return render(request, 'ipd/admit.html', {'beds': available_beds})

            admission = Admission.objects.create(
                patient=patient,
                bed=bed,
                admitting_doctor=request.user,
                diagnosis_on_admission=diagnosis,
                notes=request.POST.get('notes', ''),
                created_by=request.user,
            )
            bed.status = BedStatus.OCCUPIED
            bed.save()
            messages.success(
                request,
                f'{patient.full_name} admitted — {admission.admission_number}.'
            )
            return redirect('ipd:admission_detail', admission_id=admission.id)

    return render(request, 'ipd/admit.html', {'beds': available_beds})


@login_required
def counseling_queue(request):
    """
    Counseling Nurse dashboard — shows patients waiting in the COUNSEL QMS queue.
    Each patient here has been referred by a specialist who recommended surgery.
    The counseling nurse opens the patient's record, records counseling notes and
    consent, then routes the patient to ADMISSION (Admission Officer queue).
    """
    if not (request.user.is_counseling_nurse or request.user.is_super_admin
            or request.user.is_medical_director):
        return HttpResponseForbidden()

    today = timezone.localdate()
    waiting = []
    completed_today = 0
    if _qms_active():
        try:
            from apps.qms.models import QueueToken, TokenStatus
            waiting = QueueToken.objects.filter(
                service_type='COUNSEL',
                status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                token_date=today,
                is_deleted=False,
            ).select_related('patient', 'visit').order_by('-priority', 'issued_at')
            completed_today = QueueToken.objects.filter(
                service_type='COUNSEL',
                status=TokenStatus.COMPLETED,
                token_date=today,
                is_deleted=False,
            ).count()
        except Exception:
            pass

    return render(request, 'ipd/counseling_queue.html', {
        'waiting': waiting,
        'completed_today': completed_today,
    })


@login_required
def counseling_record(request, visit_id):
    """
    Counseling Nurse — record surgical counseling for a patient.
    Reads the doctor's surgical plan from the consultation's department_specific_data.
    Saves counseling notes and consent to a SurgicalBooking (pending payment).
    On completion, routes patient to ADMISSION queue.
    """
    if not (request.user.is_counseling_nurse or request.user.is_super_admin
            or request.user.is_medical_director):
        return HttpResponseForbidden()

    from apps.patients.models import Visit
    from apps.consultations.models import Consultation

    visit = get_object_or_404(Visit, pk=visit_id, is_deleted=False)
    patient = visit.patient

    # Find the consultation that has surgery_recommended in dept data
    consultation = Consultation.objects.filter(
        visit=visit, is_deleted=False
    ).order_by('-consultation_date').first()

    # Extract surgical plan from dept-specific data
    dept_data = (consultation.department_specific_data or {}) if consultation else {}
    surgical_procedure = dept_data.get('surgical_procedure', '')
    surgery_eye = dept_data.get('surgery_eye', '')
    anaesthesia_type = dept_data.get('anaesthesia_type', '')
    surgical_notes = dept_data.get('surgical_notes', '')

    # Existing booking (if counselor is editing)
    existing_booking = SurgicalBooking.objects.filter(
        patient=patient, consultation=consultation, is_deleted=False
    ).first()

    if request.method == 'POST':
        counseling_notes = request.POST.get('counseling_notes', '').strip()
        consent_signed = request.POST.get('consent_signed') == 'yes'
        procedure = request.POST.get('procedure', surgical_procedure).strip()
        eye = request.POST.get('eye', surgery_eye).strip()
        anaesthesia = request.POST.get('anaesthesia', anaesthesia_type).strip()
        pre_op = request.POST.get('pre_op_requirements', '').strip()

        if existing_booking:
            existing_booking.counseling_notes = counseling_notes
            existing_booking.consent_signed = consent_signed
            existing_booking.consent_date = timezone.now() if consent_signed else None
            existing_booking.procedure = procedure or 'To be determined'
            existing_booking.eye_laterality = eye
            existing_booking.anaesthesia_type = anaesthesia
            existing_booking.pre_op_requirements = pre_op
            existing_booking.save()
            booking = existing_booking
        else:
            booking = SurgicalBooking.objects.create(
                patient=patient,
                consultation=consultation,
                procedure=procedure or 'To be determined',
                eye_laterality=eye,
                anaesthesia_type=anaesthesia,
                pre_op_requirements=pre_op,
                counseling_notes=counseling_notes,
                consent_signed=consent_signed,
                consent_date=timezone.now() if consent_signed else None,
                status=SurgicalBookingStatus.PENDING_PAYMENT,
                created_by=request.user,
            )

        # Mark COUNSEL token as completed and route to Admission (QMS only)
        today = timezone.localdate()
        if _qms_active():
            try:
                from apps.qms.models import QueueToken, TokenStatus, IssuancePoint, TIER_PRIORITY, DailyTokenSequence
                counsel_token = QueueToken.objects.filter(
                    visit=visit,
                    service_type='COUNSEL',
                    status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                    token_date=today,
                    is_deleted=False,
                ).first()
                if counsel_token:
                    counsel_token.status = TokenStatus.COMPLETED
                    counsel_token.completed_at = timezone.now()
                    counsel_token.save()

                if consent_signed:
                    tier = visit.service_tier
                    token_number = DailyTokenSequence.next_dept_token('ADMISSION')
                    QueueToken.objects.create(
                        token_number=token_number,
                        patient=patient,
                        visit=visit,
                        patient_name=patient.full_name,
                        service_type='ADMISSION',
                        service_tier=tier,
                        issuance_point=IssuancePoint.SYSTEM,
                        priority=TIER_PRIORITY.get(tier, 0),
                        notes=f'Consent signed — {booking.procedure} | Booking: {booking.booking_number}',
                        issued_by=request.user,
                    )
            except Exception:
                pass

        if consent_signed:
            visit.status = 'WAITING_ADMISSION'
            visit.save(update_fields=['status', 'updated_at'])
            messages.success(
                request,
                f'Consent recorded for {patient.full_name}. '
                f'Booking {booking.booking_number} created. Patient sent to Admission.'
            )
        else:
            # Patient needs more time — leave at COUNSELING status, no admission token
            booking.status = SurgicalBookingStatus.PENDING_PAYMENT
            booking.save(update_fields=['status', 'updated_at'])
            messages.info(
                request,
                f'Counseling recorded for {patient.full_name}. '
                f'Patient needs more time — not yet sent to Admission. '
                f'Follow-up appointment recommended.'
            )
        return redirect('ipd:counseling_queue')

    from .models import SurgeryType as ST
    counseling_topics = [
        'Purpose and benefits of surgery',
        'Risks and possible complications',
        'Alternative treatments',
        'Anaesthesia explanation',
        'Pre-operative fasting and medication instructions',
        'Post-operative care and restrictions',
        'Follow-up schedule',
        'Signs of complications to watch for',
        'What to bring on surgery day',
        'Cost and payment explained',
    ]
    return render(request, 'ipd/counseling_record.html', {
        'visit': visit,
        'patient': patient,
        'consultation': consultation,
        'surgical_procedure': surgical_procedure,
        'surgery_eye': surgery_eye,
        'anaesthesia_type': anaesthesia_type,
        'surgical_notes': surgical_notes,
        'existing_booking': existing_booking,
        'surgery_type_choices': ST.choices,
        'counseling_topics': counseling_topics,
    })


@login_required
def surgical_booking_queue(request):
    """
    Admission Officer — shows patients waiting to schedule surgery.
    Officer reviews doctor's plan, sets surgery date, calculates payment.
    """
    if not (request.user.is_admission_officer or request.user.is_super_admin
            or request.user.is_medical_director):
        return HttpResponseForbidden()

    from django.db.models import Q as _Q

    today = timezone.localdate()
    waiting = []
    if _qms_active():
        try:
            from apps.qms.models import QueueToken, TokenStatus
            waiting = QueueToken.objects.filter(
                service_type='ADMISSION',
                status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                token_date=today,
                is_deleted=False,
            ).select_related('patient', 'visit').order_by('-priority', 'issued_at')
        except Exception:
            pass

    # ── Search ──────────────────────────────────────────────────────────────
    q = request.GET.get('q', '').strip()
    search_results = None
    if q:
        search_results = SurgicalBooking.objects.filter(
            is_deleted=False
        ).filter(
            _Q(patient__first_name__icontains=q) |
            _Q(patient__last_name__icontains=q) |
            _Q(patient__patient_id__icontains=q) |
            _Q(booking_number__icontains=q)
        ).select_related('patient', 'surgeon').order_by('-created_at')[:40]

    # ── Today's scheduled surgeries ─────────────────────────────────────────
    today_surgeries = SurgicalBooking.objects.filter(
        is_deleted=False,
        surgery_date__date=today,
    ).exclude(status=SurgicalBookingStatus.CANCELLED).select_related(
        'patient', 'surgeon'
    ).order_by('surgery_date')

    # ── Recent bookings (all statuses, last 20) ─────────────────────────────
    status_filter = request.GET.get('status', '').strip()
    recent_qs = SurgicalBooking.objects.filter(is_deleted=False).select_related('patient', 'surgeon')
    if status_filter:
        recent_qs = recent_qs.filter(status=status_filter)
    recent_bookings = recent_qs.order_by('-created_at')[:20]

    return render(request, 'ipd/surgical_booking_queue.html', {
        'waiting': waiting,
        'recent_bookings': recent_bookings,
        'search_results': search_results,
        'today_surgeries': today_surgeries,
        'q': q,
        'status_filter': status_filter,
        'booking_statuses': SurgicalBookingStatus.choices,
        'today': today,
    })


@login_required
def surgical_booking_create(request, visit_id):
    """
    Admission Officer creates / finalises a SurgicalBooking.
    Sets surgery date, payment amount, pre-op checklist, assigns surgeon.
    """
    if not (request.user.is_admission_officer or request.user.is_super_admin
            or request.user.is_medical_director):
        return HttpResponseForbidden()

    from apps.patients.models import Visit
    from apps.accounts.models import User, UserRole
    from apps.consultations.models import Consultation

    visit = get_object_or_404(Visit, pk=visit_id, is_deleted=False)
    patient = visit.patient

    consultation = Consultation.objects.filter(
        visit=visit, is_deleted=False
    ).order_by('-consultation_date').first()

    # Get existing booking from counseling nurse
    booking = SurgicalBooking.objects.filter(
        patient=patient,
        is_deleted=False,
        status=SurgicalBookingStatus.PENDING_PAYMENT,
    ).order_by('-created_at').first()

    # Surgeons list
    surgeons = User.objects.filter(
        role__in=[
            UserRole.CATARACT_SURGEON, UserRole.OPHTHALMOLOGIST,
            UserRole.RETINA_SPECIALIST, UserRole.GLAUCOMA_SPECIALIST,
            UserRole.CORNEA_SPECIALIST, UserRole.OCULOPLASTICS_SURGEON,
            UserRole.NEURO_OPHTHALMOLOGIST, UserRole.MEDICAL_DIRECTOR,
        ],
        is_active=True,
    ).order_by('last_name')

    if request.method == 'POST':
        procedure = request.POST.get('procedure', '').strip()
        eye = request.POST.get('eye_laterality', '').strip()
        anaesthesia = request.POST.get('anaesthesia_type', '').strip()
        surgery_category = request.POST.get('surgery_category', '').strip()
        surgeon_id = request.POST.get('surgeon_id')
        surgery_date_str = request.POST.get('surgery_date', '').strip()
        theatre = request.POST.get('theatre', '').strip()
        # grand_total includes surgery + room cost; falls back to surgery-only total_amount
        grand_total = request.POST.get('grand_total', '').strip()
        surgery_cost = request.POST.get('total_amount', '0').strip() or '0'
        total_amount = grand_total if grand_total else surgery_cost
        deposit_required = request.POST.get('deposit_required', '0').strip() or '0'
        pre_op = request.POST.get('pre_op_requirements', '').strip()
        payment_notes = request.POST.get('payment_notes', '').strip()
        # Ward/room info for notes (stored as text; bed assigned at actual admission)
        ward_id = request.POST.get('ward_id', '').strip()
        bed_id = request.POST.get('bed_id', '').strip()
        room_nights = request.POST.get('room_nights', '').strip()

        surgeon = None
        if surgeon_id:
            try:
                surgeon = User.objects.get(pk=surgeon_id)
            except User.DoesNotExist:
                pass

        surgery_date = None
        if surgery_date_str:
            from django.utils.dateparse import parse_datetime, parse_date
            surgery_date = parse_datetime(surgery_date_str) or (
                timezone.make_aware(
                    timezone.datetime.combine(
                        parse_date(surgery_date_str), timezone.datetime.min.time()
                    )
                ) if parse_date(surgery_date_str) else None
            )

        # Build ward/room note if selected
        ward_note = ''
        if ward_id or bed_id:
            try:
                from .models import Ward, Bed
                ward_obj = Ward.objects.filter(pk=ward_id).first() if ward_id else None
                bed_obj = Bed.objects.filter(pk=bed_id).first() if bed_id else None
                parts = []
                if ward_obj:
                    parts.append(f"Ward: {ward_obj.name}")
                if bed_obj:
                    parts.append(f"Bed: {bed_obj.bed_number}")
                if room_nights:
                    parts.append(f"Nights: {room_nights}")
                ward_note = ' | '.join(parts)
            except Exception:
                pass

        if booking:
            booking.procedure = procedure or booking.procedure
            booking.eye_laterality = eye or booking.eye_laterality
            booking.anaesthesia_type = anaesthesia or booking.anaesthesia_type
            booking.surgery_category = surgery_category or booking.surgery_category
            booking.surgeon = surgeon
            booking.surgery_date = surgery_date
            booking.theatre = theatre
            booking.total_amount = total_amount
            booking.deposit_required = deposit_required
            booking.pre_op_requirements = pre_op
            booking.payment_notes = payment_notes
            if ward_note:
                booking.notes = ward_note
            booking.status = SurgicalBookingStatus.CONFIRMED
            booking.admission_officer = request.user
            booking.save()
        else:
            booking = SurgicalBooking.objects.create(
                patient=patient,
                consultation=consultation,
                procedure=procedure or 'To be determined',
                eye_laterality=eye,
                anaesthesia_type=anaesthesia,
                surgery_category=surgery_category,
                surgeon=surgeon,
                surgery_date=surgery_date,
                theatre=theatre,
                total_amount=total_amount,
                deposit_required=deposit_required,
                pre_op_requirements=pre_op,
                payment_notes=payment_notes,
                notes=ward_note,
                status=SurgicalBookingStatus.CONFIRMED,
                admission_officer=request.user,
                created_by=request.user,
            )

        # Mark ADMISSION token complete (QMS only)
        today = timezone.localdate()
        if _qms_active():
            try:
                from apps.qms.models import QueueToken, TokenStatus
                adm_token = QueueToken.objects.filter(
                    visit=visit,
                    service_type='ADMISSION',
                    status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                    token_date=today,
                    is_deleted=False,
                ).first()
                if adm_token:
                    adm_token.status = TokenStatus.COMPLETED
                    adm_token.completed_at = timezone.now()
                    adm_token.save()
            except Exception:
                pass

        visit.status = 'WAITING_ADMISSION'
        visit.save(update_fields=['status', 'updated_at'])

        # ── Auto-generate Proforma (cost estimate given to patient) ──────────
        # Patient takes proforma to Cashier who converts it to a real invoice.
        surgery_category = request.POST.get('surgery_category', '').strip()
        bed_id = request.POST.get('bed_id', '').strip()
        room_nights = int(request.POST.get('room_nights', 1) or 1)
        if surgery_category:
            booking.surgery_category = surgery_category
            booking.save(update_fields=['surgery_category', 'updated_at'])

        try:
            from apps.billing.models import Proforma, ProformaItem, ServiceCategory
            existing_proforma = Proforma.objects.filter(
                patient=patient,
                notes__icontains=booking.booking_number,
                is_deleted=False,
            ).exclude(status='CANCELLED').first()
            if not existing_proforma:
                proforma = Proforma.objects.create(
                    patient=patient,
                    issued_by=request.user,
                    status='ISSUED',
                    valid_days=7,
                    notes=f'Surgical booking {booking.booking_number}',
                    created_by=request.user,
                )
                if float(total_amount) > 0:
                    ProformaItem.objects.create(
                        proforma=proforma,
                        category=ServiceCategory.SURGICAL,
                        description=f'{procedure} ({booking.get_eye_laterality_display() if booking.eye_laterality else ""})',
                        quantity=1,
                        unit_price=total_amount,
                        created_by=request.user,
                    )
                if bed_id:
                    try:
                        bed_obj = Bed.objects.get(pk=bed_id)
                        room_rate = bed_obj.nightly_rate
                        if room_rate > 0 and room_nights > 0:
                            ProformaItem.objects.create(
                                proforma=proforma,
                                category=ServiceCategory.ADMISSION,
                                description=f'{bed_obj} — {room_nights} night(s)',
                                quantity=room_nights,
                                unit_price=room_rate,
                                created_by=request.user,
                            )
                    except Bed.DoesNotExist:
                        pass
        except Exception:
            pass  # Billing not blocking surgical flow

        # ── Route patient to Cashier (QMS) ─────────────────────────────────────
        if _qms_active():
            try:
                from apps.qms.models import QueueToken, TokenStatus, IssuancePoint, TIER_PRIORITY, DailyTokenSequence
                # Mark ADMISSION token complete
                adm_token2 = QueueToken.objects.filter(
                    visit=visit,
                    service_type='ADMISSION',
                    status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                    token_date=timezone.localdate(),
                    is_deleted=False,
                ).first()
                if adm_token2:
                    adm_token2.status = TokenStatus.COMPLETED
                    adm_token2.completed_at = timezone.now()
                    adm_token2.save()

                # Create Cashier token
                tier = visit.service_tier
                cash_token = DailyTokenSequence.next_dept_token('CASHIER')
                QueueToken.objects.create(
                    token_number=cash_token,
                    patient=patient,
                    visit=visit,
                    patient_name=patient.full_name,
                    service_type='CASHIER',
                    service_tier=tier,
                    issuance_point=IssuancePoint.SYSTEM,
                    priority=TIER_PRIORITY.get(tier, 0),
                    notes=(
                        f'Surgery payment — {booking.procedure} | '
                        f'Total: {booking.total_amount:,.0f} XAF | '
                        f'Deposit: {booking.deposit_required:,.0f} XAF | '
                        f'Booking: {booking.booking_number}'
                    ),
                    issued_by=request.user,
                )
            except Exception:
                pass

        messages.success(
            request,
            f'Surgical booking {booking.booking_number} confirmed for {patient.full_name}. '
            f'Deposit required: {booking.deposit_required:,.0f} XAF. Invoice generated. Patient sent to Cashier.'
        )
        return redirect('ipd:surgical_booking_detail', booking_id=booking.pk)

    dept_data = (consultation.department_specific_data or {}) if consultation else {}

    # Available wards/beds for room assignment
    wards = Ward.objects.filter(is_deleted=False).prefetch_related('beds')
    beds_by_ward = {}
    for w in wards:
        beds_by_ward[str(w.pk)] = [
            {'id': str(b.pk), 'number': b.bed_number, 'rate': float(b.nightly_rate)}
            for b in w.beds.filter(status=BedStatus.AVAILABLE, is_deleted=False)
        ]

    # Finance-set surgical procedure prices
    from apps.billing.models import ServicePrice, ServiceCategory
    surgical_prices = list(
        ServicePrice.objects.filter(
            category=ServiceCategory.SURGICAL, is_active=True, is_deleted=False
        ).order_by('name').values('id', 'name', 'price', 'code')
    )

    return render(request, 'ipd/surgical_booking_create.html', {
        'visit': visit,
        'patient': patient,
        'consultation': consultation,
        'booking': booking,
        'surgeons': surgeons,
        'dept_data': dept_data,
        'surgery_type_choices': SurgeryType.choices,
        'wards': wards,
        'beds_by_ward_json': json.dumps(beds_by_ward),
        'surgical_prices_json': json.dumps(surgical_prices),
        'has_surgical_prices': bool(surgical_prices),
    })


@login_required
def surgical_booking_detail(request, booking_id):
    booking = get_object_or_404(SurgicalBooking, pk=booking_id, is_deleted=False)

    # Standard pre-op checklist items
    preop_items = [
        ('consent_signed',     'Informed consent signed by patient'),
        ('id_verified',        'Patient identity verified (ID + wristband)'),
        ('fasting_confirmed',  'Fasting confirmed (min 6h food, 2h clear fluids)'),
        ('blood_results',      'Blood results received (FBC, RBG, if required)'),
        ('ecg_done',           'ECG done (if required for GA)'),
        ('chest_xray',         'Chest X-ray done (if required)'),
        ('iv_access',          'IV access established'),
        ('allergies_checked',  'Allergies double-checked with patient'),
        ('meds_stopped',       'Anticoagulants/aspirin stopped as instructed'),
        ('eye_marked',         'Operative eye marked / site verification done'),
        ('pupil_dilated',      'Pupil dilated (if required for procedure)'),
        ('theatre_briefed',    'Theatre team briefed — WHO surgical safety checklist'),
        ('anaesthetist_seen',  'Anaesthetist pre-op review completed'),
    ]

    if request.method == 'POST' and request.POST.get('action') == 'save_checklist':
        checklist = {}
        for item, label in preop_items:
            checklist[item] = request.POST.get(f'chk_{item}') == 'on'
        booking.pre_op_checklist = checklist
        booking.save(update_fields=['pre_op_checklist', 'updated_at'])
        messages.success(request, 'Pre-op checklist saved.')
        return redirect('ipd:surgical_booking_detail', booking_id=booking.pk)

    checklist = booking.pre_op_checklist or {}
    preop_items_with_state = [
        (item, label, bool(checklist.get(item, False)))
        for item, label in preop_items
    ]
    # Find proforma issued for this booking (cost estimate given to patient)
    proforma = None
    try:
        from apps.billing.models import Proforma
        proforma = Proforma.objects.filter(
            patient=booking.patient,
            notes__icontains=booking.booking_number,
            is_deleted=False,
        ).exclude(status='CANCELLED').first()
    except Exception:
        pass
    return render(request, 'ipd/surgical_booking_detail.html', {
        'booking': booking,
        'preop_items': preop_items_with_state,
        'proforma': proforma,
    })


@login_required
def surgical_booking_slip_pdf(request, booking_id):
    """Print-ready booking confirmation slip."""
    booking = get_object_or_404(SurgicalBooking, pk=booking_id, is_deleted=False)
    from django.conf import settings
    from apps.reports.views import render_pdf
    context = {
        'booking': booking,
        'hospital_name': settings.HOSPITAL_NAME,
        'hospital_address': settings.HOSPITAL_ADDRESS,
        'hospital_phone': settings.HOSPITAL_PHONE,
        'pdf_filename': f'surgical_booking_{booking.booking_number}.pdf',
    }
    return render_pdf('ipd/surgical_booking_slip.html', context)


@login_required
def discharge_patient(request, admission_id):
    from apps.appointments.models import Appointment
    from apps.departments.models import Department
    admission = get_object_or_404(Admission, id=admission_id, is_deleted=False)

    if request.method == 'POST':
        # Discharge the patient
        admission.discharge(summary=request.POST.get('discharge_summary', ''))

        # Gap 1: Auto follow-up appointment booking
        followup_date = request.POST.get('followup_date', '').strip()
        followup_time = request.POST.get('followup_time', '').strip()
        followup_doctor_id = request.POST.get('followup_doctor', '').strip()
        followup_dept_id = request.POST.get('followup_department', '').strip()
        followup_reason = request.POST.get('followup_reason', '').strip()

        if followup_date and followup_time:
            from apps.accounts.models import User
            followup_doctor = None
            if followup_doctor_id:
                try:
                    followup_doctor = User.objects.get(pk=followup_doctor_id)
                except User.DoesNotExist:
                    pass

            followup_dept = None
            if followup_dept_id:
                try:
                    followup_dept = Department.objects.get(pk=followup_dept_id)
                except Department.DoesNotExist:
                    pass

            appt = Appointment.objects.create(
                patient=admission.patient,
                department=followup_dept,
                doctor=followup_doctor,
                appointment_date=followup_date,
                appointment_time=followup_time,
                appointment_type=Appointment.AppointmentType.FOLLOW_UP,
                service_tier=Appointment.ServiceTier.STANDARD,
                reason=followup_reason or f'Post-operative follow-up after {admission.diagnosis_on_admission}',
                booked_by=request.user,
                notes=f'Auto-booked at discharge from admission {admission.admission_number}.',
                created_by=request.user,
            )
            messages.success(
                request,
                f'{admission.patient.full_name} discharged and follow-up appointment {appt.appointment_number} booked for {followup_date}.'
            )
        else:
            messages.success(request, f'{admission.patient.full_name} discharged successfully.')

        return redirect('ipd:dashboard')

    # Doctors for follow-up dropdown
    from apps.accounts.models import User as AccountUser
    from apps.departments.models import Department
    doctors = AccountUser.objects.filter(role__in=AccountUser.DOCTOR_ROLES, is_active=True, is_deleted=False).order_by('first_name')
    departments = Department.objects.filter(is_active=True, is_deleted=False).order_by('name')

    return render(request, 'ipd/discharge.html', {
        'admission': admission,
        'doctors': doctors,
        'departments': departments,
    })


# ─────────────────────────────────────────────────────────────────────────────
# admit_from_booking  — admit a patient from a confirmed SurgicalBooking
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def admit_from_booking(request, booking_id):
    """Admit a patient to IPD directly from a confirmed SurgicalBooking."""
    if not (request.user.is_admission_officer or request.user.is_super_admin
            or request.user.is_medical_director):
        return HttpResponseForbidden()

    booking = get_object_or_404(SurgicalBooking, pk=booking_id, is_deleted=False)
    available_beds = Bed.objects.filter(
        status=BedStatus.AVAILABLE, is_deleted=False
    ).select_related('ward').order_by('ward__name', 'bed_number')

    if request.method == 'POST':
        bed_id = request.POST.get('bed_id')
        diagnosis = request.POST.get('diagnosis_on_admission', '').strip() or booking.procedure
        bed = get_object_or_404(Bed, pk=bed_id, status=BedStatus.AVAILABLE)

        admission = Admission.objects.create(
            patient=booking.patient,
            bed=bed,
            admitting_doctor=booking.surgeon or request.user,
            surgical_booking=booking,
            diagnosis_on_admission=diagnosis,
            notes=f'Admitted for: {booking.procedure}',
            created_by=request.user,
        )
        bed.status = BedStatus.OCCUPIED
        bed.save(update_fields=['status', 'updated_at'])

        booking.status = SurgicalBookingStatus.SCHEDULED
        booking.save(update_fields=['status', 'updated_at'])

        messages.success(
            request,
            f'{booking.patient.full_name} admitted to {bed} — Admission {admission.admission_number}.'
        )
        return redirect('ipd:admission_detail', admission_id=admission.pk)

    return render(request, 'ipd/admit_from_booking.html', {
        'booking': booking,
        'available_beds': available_beds,
    })


# ─────────────────────────────────────────────────────────────────────────────
# IPD Nursing Statistics Dashboard
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def ipd_nursing_stats(request):
    """
    Inpatient Nurse Statistics / Surgical Bookings Register:
    - All surgical bookings (prescribed by doctors)
    - Which ones have paid (deposit >= deposit_required)
    - Which ones came back and were admitted
    - Surgery type breakdown
    Supports date range and status filtering via GET params.
    """
    from datetime import timedelta
    from django.db.models import Count, Sum, Q
    from django.utils.dateparse import parse_date

    today = timezone.localdate()
    month_start = today.replace(day=1)

    if not (request.user.is_super_admin or request.user.is_medical_director
            or request.user.is_admin_staff or request.user.is_ceo
            or request.user.is_admin_director
            or request.user.role in ['ipd_nurse', 'admission_officer']):
        return HttpResponseForbidden()

    # ── Date range + status filters ─────────────────────────────────────────
    date_from_str = request.GET.get('date_from', '').strip()
    date_to_str   = request.GET.get('date_to', '').strip()
    status_filter = request.GET.get('status', '').strip()
    show_all      = request.GET.get('all', '').strip()

    if date_from_str:
        date_from = parse_date(date_from_str) or month_start
    elif show_all:
        date_from = None  # no lower bound
    else:
        date_from = month_start

    if date_to_str:
        date_to = parse_date(date_to_str) or today
    else:
        date_to = today

    bookings_qs = SurgicalBooking.objects.filter(is_deleted=False)
    if date_from:
        bookings_qs = bookings_qs.filter(created_at__date__gte=date_from)
    bookings_qs = bookings_qs.filter(created_at__date__lte=date_to)
    if status_filter:
        bookings_qs = bookings_qs.filter(status=status_filter)

    bookings = bookings_qs.select_related(
        'patient', 'surgeon', 'consultation__department'
    ).order_by('-created_at')

    # ── Statistics (always over the filtered range) ─────────────────────────
    total_prescribed = bookings.count()
    paid = bookings.filter(deposit_paid__gte=models.F('deposit_required'), deposit_required__gt=0).count()
    confirmed = bookings.filter(status=SurgicalBookingStatus.CONFIRMED).count()
    scheduled = bookings.filter(status=SurgicalBookingStatus.SCHEDULED).count()
    completed = bookings.filter(status=SurgicalBookingStatus.COMPLETED).count()
    cancelled = bookings.filter(status=SurgicalBookingStatus.CANCELLED).count()
    pending_payment = bookings.filter(status=SurgicalBookingStatus.PENDING_PAYMENT).count()

    # Patients actually admitted in the same period
    admit_qs = Admission.objects.filter(surgical_booking__isnull=False, is_deleted=False)
    if date_from:
        admit_qs = admit_qs.filter(admission_date__date__gte=date_from)
    admitted_count = admit_qs.filter(admission_date__date__lte=date_to).count()

    # Surgery category breakdown
    category_breakdown = (
        bookings.filter(surgery_category__gt='')
        .values('surgery_category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # Current IPD census (always live)
    current_admissions = Admission.objects.filter(
        status=AdmissionStatus.ADMITTED, is_deleted=False
    ).select_related('patient', 'bed__ward', 'surgical_booking', 'admitting_doctor')

    context = {
        'bookings': bookings,
        'total_prescribed': total_prescribed,
        'paid': paid,
        'confirmed': confirmed,
        'scheduled': scheduled,
        'completed': completed,
        'cancelled': cancelled,
        'pending_payment': pending_payment,
        'admitted_count': admitted_count,
        'category_breakdown': category_breakdown,
        'current_admissions': current_admissions,
        # filter state
        'date_from': date_from,
        'date_to': date_to,
        'date_from_str': date_from_str or (month_start.isoformat() if not show_all else ''),
        'date_to_str': date_to_str or today.isoformat(),
        'status_filter': status_filter,
        'show_all': show_all,
        'booking_statuses': SurgicalBookingStatus.choices,
        'month_start': month_start,
        'today': today,
    }
    return render(request, 'ipd/nursing_stats.html', context)


import django.db.models as models  # noqa — needed for models.F in ipd_nursing_stats


# ─────────────────────────────────────────────────────────────────────────────
# MAR — Medication Administration Record
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def mar_add(request, admission_id):
    """Ward/Theatre nurse adds a medication schedule to the MAR."""
    from django.utils.dateparse import parse_datetime
    from apps.accounts.models import UserRole
    admission = get_object_or_404(Admission, id=admission_id, is_deleted=False)

    allowed = (
        UserRole.NURSE, UserRole.WARD_NURSE, UserRole.THEATRE_NURSE,
        UserRole.COUNSELING_NURSE, UserRole.MEDICAL_DIRECTOR,
    )
    if request.user.role not in allowed and not request.user.is_super_admin:
        return HttpResponseForbidden()

    if request.method == 'POST':
        scheduled_raw = request.POST.get('scheduled_time', '')
        scheduled_time = parse_datetime(scheduled_raw)
        if not scheduled_time:
            messages.error(request, 'Invalid scheduled date/time.')
            return redirect('ipd:admission_detail', admission_id=admission.id)

        MAREntry.objects.create(
            admission=admission,
            drug_name=request.POST.get('drug_name', '').strip(),
            dose=request.POST.get('dose', '').strip(),
            route=request.POST.get('route', '').strip(),
            frequency=request.POST.get('frequency', '').strip(),
            scheduled_time=scheduled_time,
            notes=request.POST.get('notes', '').strip(),
            created_by=request.user,
        )
        messages.success(request, 'Medication added to MAR.')
    return redirect('ipd:admission_detail', admission_id=admission.id)


@login_required
def mar_administer(request, mar_id):
    """Nurse records that a scheduled dose was given/missed/refused/held."""
    from apps.accounts.models import UserRole
    entry = get_object_or_404(MAREntry, id=mar_id)

    allowed = (
        UserRole.NURSE, UserRole.WARD_NURSE, UserRole.THEATRE_NURSE,
        UserRole.COUNSELING_NURSE, UserRole.MEDICAL_DIRECTOR,
    )
    if request.user.role not in allowed and not request.user.is_super_admin:
        return HttpResponseForbidden()

    if request.method == 'POST':
        new_status = request.POST.get('status', 'GIVEN')
        entry.status = new_status
        if new_status == 'GIVEN':
            entry.administered_time = timezone.now()
            entry.administered_by = request.user
        entry.notes = request.POST.get('notes', entry.notes)
        entry.save()
        messages.success(request, f'MAR entry marked as {entry.get_status_display()}.')
    return redirect('ipd:admission_detail', admission_id=entry.admission_id)


# ─────────────────────────────────────────────────────────────────────────────
# Theatre Scheduling Board
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def theatre_board(request):
    """
    Theatre scheduling board — shows all booked surgeries grouped by theatre
    for the selected date (default: today).
    Accessible to all clinical staff.
    """
    from datetime import date, timedelta
    from django.http import JsonResponse

    # Date navigation
    date_str = request.GET.get('date', '')
    try:
        board_date = date.fromisoformat(date_str)
    except ValueError:
        board_date = timezone.localdate()

    prev_date = board_date - timedelta(days=1)
    next_date = board_date + timedelta(days=1)

    # All confirmed/scheduled bookings for this date
    bookings = SurgicalBooking.objects.filter(
        surgery_date__date=board_date,
        is_deleted=False,
    ).exclude(
        status__in=[SurgicalBookingStatus.CANCELLED]
    ).select_related(
        'patient', 'surgeon', 'consultation__visit'
    ).prefetch_related('anaesthetic_records').order_by('surgery_date', 'theatre')

    # Group by theatre
    theatre_groups = {}
    for b in bookings:
        theatre = b.theatre or 'Unassigned'
        theatre_groups.setdefault(theatre, []).append(b)

    # Status colour map for template
    status_colours = {
        'PENDING_PAYMENT': 'warning',
        'CONFIRMED': 'primary',
        'SCHEDULED': 'info',
        'COMPLETED': 'success',
        'CANCELLED': 'danger',
        'RESCHEDULED': 'secondary',
    }

    return render(request, 'ipd/theatre_board.html', {
        'board_date': board_date,
        'prev_date': prev_date,
        'next_date': next_date,
        'theatre_groups': theatre_groups,
        'total_cases': bookings.count(),
        'status_colours': status_colours,
        'booking_statuses': SurgicalBookingStatus.choices,
    })


@login_required
def theatre_update_status(request):
    """AJAX: update a surgical booking status from the theatre board."""
    from django.http import JsonResponse
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=400)
    if not _can_manage_anaesthetics(request.user) and not (
        request.user.is_theatre_nurse or request.user.is_ward_nurse
    ):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    booking_id = request.POST.get('booking_id')
    new_status = request.POST.get('status')

    booking = get_object_or_404(SurgicalBooking, id=booking_id)
    if new_status in dict(SurgicalBookingStatus.choices):
        booking.status = new_status
        booking.save(update_fields=['status', 'updated_at'])
        return JsonResponse({'success': True, 'status': new_status, 'label': booking.get_status_display()})
    return JsonResponse({'error': 'Invalid status'}, status=400)


# ══════════════════════════════════════════════════════════════════════════════
# THEATRE SESSION VIEWS
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def theatre_session_list(request):
    """All theatre sessions — filterable by date and status."""
    from django.db.models import Count
    date_filter = request.GET.get('date', '')
    status_filter = request.GET.get('status', '')

    qs = TheatreSession.objects.select_related(
        'lead_surgeon', 'scrub_nurse'
    ).prefetch_related('procedures__patient').order_by('-session_date', 'start_time')

    if date_filter:
        qs = qs.filter(session_date=date_filter)
    if status_filter:
        qs = qs.filter(status=status_filter)

    today = timezone.localdate()
    return render(request, 'ipd/theatre_session_list.html', {
        'sessions': qs[:100],
        'status_choices': TheatreSessionStatus.choices,
        'date_filter': date_filter,
        'status_filter': status_filter,
        'today': today,
    })


@login_required
def theatre_session_create(request):
    """Create a new theatre session for a given date."""
    from apps.accounts.models import User, UserRole
    doctors = User.objects.filter(is_active=True, role__in=[
        UserRole.OPHTHALMOLOGIST, UserRole.RETINA_SPECIALIST,
        UserRole.GLAUCOMA_SPECIALIST, UserRole.PEDIATRIC_OPHTHALMOLOGIST,
        UserRole.CATARACT_SURGEON, UserRole.CORNEA_SPECIALIST,
        UserRole.OCULOPLASTICS_SURGEON, UserRole.NEURO_OPHTHALMOLOGIST,
        UserRole.MEDICAL_DIRECTOR, UserRole.SUPER_ADMIN,
    ]).order_by('last_name')
    nurses = User.objects.filter(is_active=True, role__in=[
        UserRole.NURSE, UserRole.THEATRE_NURSE, UserRole.WARD_NURSE,
    ]).order_by('last_name')

    if request.method == 'POST':
        p = request.POST
        session = TheatreSession.objects.create(
            session_date=p.get('session_date') or timezone.localdate(),
            theatre_name=p.get('theatre_name', 'Main Theatre').strip(),
            start_time=p.get('start_time') or None,
            end_time=p.get('end_time') or None,
            lead_surgeon_id=p.get('lead_surgeon') or None,
            anaesthetist_name=p.get('anaesthetist_name', '').strip(),
            scrub_nurse_id=p.get('scrub_nurse') or None,
            circulating_nurse_id=p.get('circulating_nurse') or None,
            notes=p.get('notes', '').strip(),
            created_by=request.user,
        )
        # Add booked surgeries to this session
        booking_ids = request.POST.getlist('bookings')
        for bid in booking_ids:
            try:
                booking = SurgicalBooking.objects.get(pk=bid)
                TheatreProcedure.objects.create(
                    session=session,
                    surgical_booking=booking,
                    patient=booking.patient,
                    surgeon=booking.surgeon,
                    procedure=booking.procedure,
                    procedure_notes=booking.procedure_notes,
                    eye_laterality=booking.eye_laterality,
                    anaesthesia_type=booking.anaesthesia_type,
                    position_on_list=TheatreProcedure.objects.filter(session=session).count() + 1,
                    created_by=request.user,
                )
                booking.status = SurgicalBookingStatus.SCHEDULED
                booking.save(update_fields=['status', 'updated_at'])
            except SurgicalBooking.DoesNotExist:
                pass

        messages.success(request, f'Theatre session {session.session_number} created.')
        return redirect('ipd:theatre_session_detail', session_id=session.pk)

    # Available confirmed bookings (not yet in a session)
    confirmed_bookings = SurgicalBooking.objects.filter(
        status=SurgicalBookingStatus.CONFIRMED, is_deleted=False
    ).select_related('patient', 'surgeon').order_by('surgery_date')

    return render(request, 'ipd/theatre_session_create.html', {
        'doctors': doctors,
        'nurses': nurses,
        'confirmed_bookings': confirmed_bookings,
        'today': timezone.localdate(),
        'theatre_choices': ['Main Theatre', 'Minor Theatre', 'Laser Suite', 'EUA Room'],
    })


@login_required
def theatre_session_detail(request, session_id):
    """Detail view for one theatre session — shows all procedures."""
    session = get_object_or_404(
        TheatreSession.objects.select_related(
            'lead_surgeon', 'scrub_nurse', 'circulating_nurse'
        ).prefetch_related('procedures__patient', 'procedures__surgeon'),
        pk=session_id
    )
    from apps.accounts.models import User, UserRole
    doctors = User.objects.filter(is_active=True, role__in=[
        UserRole.OPHTHALMOLOGIST, UserRole.RETINA_SPECIALIST, UserRole.GLAUCOMA_SPECIALIST,
        UserRole.PEDIATRIC_OPHTHALMOLOGIST, UserRole.CATARACT_SURGEON, UserRole.CORNEA_SPECIALIST,
        UserRole.OCULOPLASTICS_SURGEON, UserRole.NEURO_OPHTHALMOLOGIST, UserRole.MEDICAL_DIRECTOR,
        UserRole.SUPER_ADMIN,
    ]).order_by('last_name')

    # Available confirmed bookings to add ad-hoc
    confirmed_bookings = SurgicalBooking.objects.filter(
        status=SurgicalBookingStatus.CONFIRMED, is_deleted=False
    ).exclude(theatre_procedures__session=session).select_related('patient')

    return render(request, 'ipd/theatre_session_detail.html', {
        'session': session,
        'procedures': session.procedures.order_by('position_on_list'),
        'doctors': doctors,
        'confirmed_bookings': confirmed_bookings,
        'outcome_choices': ProcedureOutcome.choices,
        'surgery_type_choices': SurgeryType.choices,
    })


@login_required
def theatre_session_update_status(request, session_id):
    """Update a theatre session status (AJAX or form)."""
    from django.http import JsonResponse
    session = get_object_or_404(TheatreSession, pk=session_id)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(TheatreSessionStatus.choices):
            session.status = new_status
            session.save(update_fields=['status', 'updated_at'])
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            messages.success(request, f'Session status updated to {session.get_status_display()}.')
    return redirect('ipd:theatre_session_detail', session_id=session_id)


@login_required
def theatre_procedure_record(request, procedure_id):
    """
    Record intraoperative details for one procedure:
    WHO checklist, IOL data, findings, complications, outcome.
    """
    proc = get_object_or_404(
        TheatreProcedure.objects.select_related('session', 'patient', 'surgeon'),
        pk=procedure_id
    )

    if request.method == 'POST':
        p = request.POST

        # WHO Sign In
        proc.sign_in_done              = 'sign_in_done' in p
        proc.sign_in_time              = p.get('sign_in_time') or None
        proc.sign_in_identity_confirmed= 'sign_in_identity_confirmed' in p
        proc.sign_in_site_marked       = 'sign_in_site_marked' in p
        proc.sign_in_anaesthesia_safe  = 'sign_in_anaesthesia_safe' in p
        proc.sign_in_pulse_oximeter    = 'sign_in_pulse_oximeter' in p
        proc.sign_in_allergies         = 'sign_in_allergies' in p

        # WHO Time Out
        proc.time_out_done             = 'time_out_done' in p
        proc.time_out_time             = p.get('time_out_time') or None
        proc.time_out_team_introduced  = 'time_out_team_introduced' in p
        proc.time_out_site_confirmed   = 'time_out_site_confirmed' in p
        proc.time_out_antibiotics      = 'time_out_antibiotics' in p
        proc.time_out_imaging_displayed= 'time_out_imaging_displayed' in p

        # WHO Sign Out
        proc.sign_out_done                      = 'sign_out_done' in p
        proc.sign_out_time                      = p.get('sign_out_time') or None
        proc.sign_out_instrument_count_correct  = 'sign_out_instrument_count_correct' in p
        proc.sign_out_specimen_labelled         = 'sign_out_specimen_labelled' in p
        proc.sign_out_equipment_issues          = 'sign_out_equipment_issues' in p
        proc.sign_out_recovery_plan             = 'sign_out_recovery_plan' in p

        # IOL
        proc.iol_model      = p.get('iol_model', '').strip()
        proc.iol_power      = p.get('iol_power', '').strip()
        proc.iol_lot_number = p.get('iol_lot_number', '').strip()
        proc.iol_type       = p.get('iol_type', '').strip()

        # Timing
        proc.knife_time   = p.get('knife_time') or None
        proc.closure_time = p.get('closure_time') or None

        # Surgeon
        surgeon_id = p.get('surgeon')
        if surgeon_id:
            from apps.accounts.models import User
            proc.surgeon = User.objects.filter(pk=surgeon_id).first()

        # Intraop & Outcome
        proc.intraop_findings      = p.get('intraop_findings', '').strip()
        proc.complications         = p.get('complications', '').strip()
        proc.outcome               = p.get('outcome', '')
        proc.post_op_notes         = p.get('post_op_notes', '').strip()
        proc.post_op_medications   = p.get('post_op_medications', '').strip()
        proc.save()

        # Mark surgical booking as completed if outcome is set
        if proc.outcome and proc.surgical_booking:
            proc.surgical_booking.status = SurgicalBookingStatus.COMPLETED
            proc.surgical_booking.save(update_fields=['status', 'updated_at'])

        # ── Gap 1: Auto DrugPrescription from post_op_medications ────────────
        post_op_meds = proc.post_op_medications
        if post_op_meds and proc.surgical_booking and proc.surgical_booking.consultation:
            try:
                from apps.prescriptions.models import DrugPrescription, DrugPrescriptionItem, DrugForm, RouteOfAdmin, EyeChoice
                rx = DrugPrescription.objects.create(
                    consultation=proc.surgical_booking.consultation,
                    patient=proc.patient,
                    prescribed_by=request.user,
                    notes=f'Post-op — {proc.get_procedure_display()} [{proc.session.session_date}]',
                    created_by=request.user,
                )
                for line in post_op_meds.splitlines():
                    line = line.strip().lstrip('-•* ').strip()
                    if line:
                        DrugPrescriptionItem.objects.create(
                            prescription=rx,
                            drug_name=line,
                            drug_form=DrugForm.EYE_DROPS,
                            dose='As directed',
                            frequency='As directed',
                            duration='As directed',
                            route=RouteOfAdmin.TOPICAL,
                            eye=EyeChoice.NA,
                            quantity=1,
                        )
            except Exception:
                pass

        # Route to Pharmacy QMS after surgery if post-op meds are prescribed
        if post_op_meds and _qms_active():
            try:
                from apps.qms.models import (
                    QueueToken, DailyTokenSequence,
                    IssuancePoint, TIER_PRIORITY,
                )
                from apps.patients.models import Visit
                today = timezone.localdate()
                visit = Visit.objects.filter(
                    patient=proc.patient, visit_date__date=today, is_deleted=False,
                ).order_by('-visit_date').first()
                tier = visit.service_tier if visit else 'STANDARD'
                ph_token = DailyTokenSequence.next_dept_token('PHARMACY')
                QueueToken.objects.create(
                    token_number=ph_token,
                    patient=proc.patient,
                    visit=visit,
                    patient_name=proc.patient.full_name,
                    service_type='PHARMACY',
                    service_tier=tier,
                    issuance_point=IssuancePoint.SYSTEM,
                    priority=TIER_PRIORITY.get(tier, 0),
                    notes=f'Post-op medications — {proc.get_procedure_display()}',
                    issued_by=request.user,
                )
            except Exception:
                pass

        messages.success(request, f'Procedure record saved for {proc.patient.full_name}.')
        return redirect('ipd:theatre_session_detail', session_id=proc.session.pk)

    from apps.accounts.models import User, UserRole
    doctors = User.objects.filter(is_active=True, role__in=[
        UserRole.OPHTHALMOLOGIST, UserRole.RETINA_SPECIALIST, UserRole.GLAUCOMA_SPECIALIST,
        UserRole.PEDIATRIC_OPHTHALMOLOGIST, UserRole.CATARACT_SURGEON, UserRole.CORNEA_SPECIALIST,
        UserRole.OCULOPLASTICS_SURGEON, UserRole.NEURO_OPHTHALMOLOGIST,
        UserRole.MEDICAL_DIRECTOR, UserRole.SUPER_ADMIN,
    ]).order_by('last_name')

    return render(request, 'ipd/theatre_procedure_form.html', {
        'proc': proc,
        'session': proc.session,
        'outcome_choices': ProcedureOutcome.choices,
        'surgery_types': SurgeryType.choices,
        'doctors': doctors,
        'iol_types': ['Monofocal', 'Toric', 'Multifocal', 'Multifocal Toric',
                      'PMMA', 'Hydrophilic Acrylic', 'Hydrophobic Acrylic', 'Phakic IOL'],
    })


@login_required
def theatre_add_procedure(request, session_id):
    """Add an ad-hoc procedure to an existing session."""
    session = get_object_or_404(TheatreSession, pk=session_id)
    if request.method == 'POST':
        p = request.POST
        from apps.patients.models import Patient
        patient_id = p.get('patient_id')
        patient = get_object_or_404(Patient, patient_id=patient_id)

        booking_id = p.get('booking_id')
        booking = SurgicalBooking.objects.filter(pk=booking_id).first() if booking_id else None

        pos = session.procedures.count() + 1
        proc = TheatreProcedure.objects.create(
            session=session,
            surgical_booking=booking,
            patient=patient,
            procedure=p.get('procedure', 'OTHER'),
            procedure_notes=p.get('procedure_notes', '').strip(),
            eye_laterality=p.get('eye_laterality', ''),
            anaesthesia_type=p.get('anaesthesia_type', ''),
            position_on_list=pos,
            created_by=request.user,
        )
        messages.success(request, f'Procedure added for {patient.full_name}.')
    return redirect('ipd:theatre_session_detail', session_id=session_id)


# ══════════════════════════════════════════════════════════════════════════════
# WARD ROUND VIEWS
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def ward_round_add(request, admission_id):
    """Add a ward round note (SOAP) for an admitted patient."""
    admission = get_object_or_404(Admission, pk=admission_id, is_deleted=False)

    if request.method == 'POST':
        p = request.POST
        WardRound.objects.create(
            admission=admission,
            round_date=p.get('round_date') or timezone.localdate(),
            round_time=p.get('round_time') or timezone.localtime().time(),
            doctor=request.user,
            subjective=p.get('subjective', '').strip(),
            objective=p.get('objective', '').strip(),
            assessment=p.get('assessment', '').strip(),
            plan=p.get('plan', '').strip(),
            va_re=p.get('va_re', '').strip(),
            va_le=p.get('va_le', '').strip(),
            iop_re=p.get('iop_re', '').strip(),
            iop_le=p.get('iop_le', '').strip(),
            vital_signs={
                'bp': p.get('bp', '').strip(),
                'pulse': p.get('pulse', '').strip(),
                'temp': p.get('temp', '').strip(),
                'spo2': p.get('spo2', '').strip(),
                'rr': p.get('rr', '').strip(),
            },
            is_discharge_ready='is_discharge_ready' in p,
            discharge_plan=p.get('discharge_plan', '').strip(),
            created_by=request.user,
        )
        messages.success(request, 'Ward round note saved.')
        return redirect('ipd:admission_detail', admission_id=admission_id)

    return render(request, 'ipd/ward_round_form.html', {
        'admission': admission,
        'today': timezone.localdate(),
        'now_time': timezone.localtime().strftime('%H:%M'),
    })


@login_required
def discharge_summary_pdf(request, admission_id):
    """Generate a discharge summary PDF for a completed admission."""
    from apps.reports.views import render_pdf
    from django.conf import settings
    admission = get_object_or_404(
        Admission.objects.select_related(
            'patient', 'bed__ward', 'admitting_doctor'
        ).prefetch_related(
            'ward_rounds__doctor',
            'nursing_notes',
            'mar_entries',
        ),
        pk=admission_id
    )
    ward_rounds = admission.ward_rounds.order_by('round_date', 'round_time')
    last_round = ward_rounds.last()

    context = {
        'admission': admission,
        'patient': admission.patient,
        'ward_rounds': ward_rounds,
        'last_round': last_round,
        'hospital_name': settings.HOSPITAL_NAME,
        'hospital_address': settings.HOSPITAL_ADDRESS,
        'hospital_phone': settings.HOSPITAL_PHONE,
        'pdf_filename': f'discharge_summary_{admission.patient.patient_id}_{admission.admission_number}.pdf',
    }
    return render_pdf('reports/pdf/discharge_summary.html', context)


# ══════════════════════════════════════════════════════════════════════════════
# WARD & BED MANAGEMENT  (Super Admin only)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def ward_manage(request):
    """Super Admin — view all wards with their beds and manage them."""
    if not request.user.is_super_admin:
        return HttpResponseForbidden()
    wards = Ward.objects.filter(is_deleted=False).prefetch_related('beds').order_by('name')
    return render(request, 'ipd/ward_manage.html', {
        'wards': wards,
        'ward_types': WardType.choices,
    })


@login_required
def ward_create(request):
    """Super Admin — create a new ward."""
    if not request.user.is_super_admin:
        return HttpResponseForbidden()
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        ward_type = request.POST.get('ward_type', 'GENERAL')
        floor = request.POST.get('floor', '').strip()
        price_per_night = request.POST.get('price_per_night', '0').strip() or '0'
        description = request.POST.get('description', '').strip()
        if not name:
            messages.error(request, 'Ward name is required.')
        else:
            Ward.objects.create(
                name=name, ward_type=ward_type, floor=floor,
                price_per_night=price_per_night, description=description,
                created_by=request.user,
            )
            messages.success(request, f'Ward "{name}" created.')
    return redirect('ipd:ward_manage')


@login_required
def bed_add(request, ward_id):
    """Super Admin — add beds to a ward (comma-separated numbers)."""
    if not request.user.is_super_admin:
        return HttpResponseForbidden()
    ward = get_object_or_404(Ward, pk=ward_id, is_deleted=False)
    if request.method == 'POST':
        bed_numbers_raw = request.POST.get('bed_numbers', '').strip()
        price_raw = request.POST.get('price_override', '').strip()
        price_override = price_raw if price_raw else None
        created = skipped = 0
        for num in [b.strip() for b in bed_numbers_raw.replace('\n', ',').split(',') if b.strip()]:
            if Bed.objects.filter(ward=ward, bed_number=num, is_deleted=False).exists():
                skipped += 1
            else:
                Bed.objects.create(
                    ward=ward, bed_number=num,
                    price_override=price_override,
                    created_by=request.user,
                )
                created += 1
        ward.total_beds = ward.beds.filter(is_deleted=False).count()
        ward.save(update_fields=['total_beds', 'updated_at'])
        msg = f'{created} bed(s) added to {ward.name}.'
        if skipped:
            msg += f' {skipped} skipped (already exist).'
        messages.success(request, msg)
    return redirect('ipd:ward_manage')


@login_required
def bed_toggle_status(request, bed_id):
    """Super Admin — toggle bed between AVAILABLE and MAINTENANCE."""
    if not request.user.is_super_admin:
        return HttpResponseForbidden()
    bed = get_object_or_404(Bed, pk=bed_id, is_deleted=False)
    if request.method == 'POST':
        if bed.status == BedStatus.OCCUPIED:
            messages.warning(request, f'Bed {bed.bed_number} is occupied — cannot change status.')
        elif bed.status == BedStatus.AVAILABLE:
            bed.status = BedStatus.MAINTENANCE
            bed.save(update_fields=['status', 'updated_at'])
            messages.success(request, f'Bed {bed.bed_number} set to Maintenance.')
        else:
            bed.status = BedStatus.AVAILABLE
            bed.save(update_fields=['status', 'updated_at'])
            messages.success(request, f'Bed {bed.bed_number} set to Available.')
    return redirect('ipd:ward_manage')


@login_required
def ward_delete(request, ward_id):
    """Super Admin — soft-delete a ward (only if no beds are occupied)."""
    if not request.user.is_super_admin:
        return HttpResponseForbidden()
    ward = get_object_or_404(Ward, pk=ward_id, is_deleted=False)
    if request.method == 'POST':
        occupied = ward.beds.filter(status=BedStatus.OCCUPIED, is_deleted=False).count()
        if occupied:
            messages.error(request, f'Cannot delete "{ward.name}" — {occupied} bed(s) currently occupied.')
        else:
            ward.beds.filter(is_deleted=False).update(is_deleted=True)
            ward.is_deleted = True
            ward.save(update_fields=['is_deleted', 'updated_at'])
            messages.success(request, f'Ward "{ward.name}" deleted.')
    return redirect('ipd:ward_manage')


@login_required
def bed_delete(request, bed_id):
    """Super Admin — soft-delete a bed (only if not occupied)."""
    if not request.user.is_super_admin:
        return HttpResponseForbidden()
    bed = get_object_or_404(Bed, pk=bed_id, is_deleted=False)
    if request.method == 'POST':
        if bed.status == BedStatus.OCCUPIED:
            messages.error(request, f'Cannot delete bed {bed.bed_number} — currently occupied.')
        else:
            ward = bed.ward
            bed.is_deleted = True
            bed.save(update_fields=['is_deleted', 'updated_at'])
            ward.total_beds = ward.beds.filter(is_deleted=False).count()
            ward.save(update_fields=['total_beds', 'updated_at'])
            messages.success(request, f'Bed {bed.bed_number} removed from {ward.name}.')
    return redirect('ipd:ward_manage')


# ── Anaesthetic Record (JCI ASC.5 / ASC.6) ───────────────────────────────────

def _can_manage_anaesthetics(user):
    return (user.is_super_admin or user.is_medical_director or
            user.role == 'anaesthetist' or
            user.role in ('doctor', 'specialist', 'ophthalmologist'))


@login_required
def anaesthetic_record_create(request, booking_id):
    """Create a pre-operative anaesthetic assessment for a surgical booking."""
    from .models import AnaestheticRecord, ASAGrade
    booking = get_object_or_404(SurgicalBooking, pk=booking_id, is_deleted=False)

    if not _can_manage_anaesthetics(request.user):
        return HttpResponseForbidden()

    existing = AnaestheticRecord.objects.filter(
        surgical_booking=booking, is_deleted=False
    ).first()
    if existing:
        return redirect('ipd:anaesthetic_record_detail', record_id=existing.pk)

    if request.method == 'POST':
        from django.utils.dateparse import parse_datetime
        pre_op_dt = parse_datetime(request.POST.get('pre_op_assessment_completed', '') or '')
        last_oral = parse_datetime(request.POST.get('last_oral_intake', '') or '')

        fasting_val = request.POST.get('fasting_adequate')
        fasting_adequate = True if fasting_val == 'on' else (False if fasting_val == 'off' else None)

        record = AnaestheticRecord.objects.create(
            surgical_booking=booking,
            patient=booking.patient,
            anaesthetist=request.user,
            asa_grade=request.POST.get('asa_grade', ''),
            weight_kg=request.POST.get('weight_kg') or None,
            height_cm=request.POST.get('height_cm') or None,
            mallampati_score=request.POST.get('mallampati_score', ''),
            mouth_opening=request.POST.get('mouth_opening', ''),
            neck_mobility=request.POST.get('neck_mobility', ''),
            thyromental_distance=request.POST.get('thyromental_distance', ''),
            difficult_airway_predicted=request.POST.get('difficult_airway_predicted') == 'on',
            airway_notes=request.POST.get('airway_notes', ''),
            last_oral_intake=last_oral,
            fasting_adequate=fasting_adequate,
            allergies_reviewed=request.POST.get('allergies_reviewed') == 'on',
            anaesthetic_allergies=request.POST.get('anaesthetic_allergies', ''),
            current_medications_reviewed=request.POST.get('current_medications_reviewed') == 'on',
            medications_to_continue=request.POST.get('medications_to_continue', ''),
            medications_to_stop=request.POST.get('medications_to_stop', ''),
            premedication_given=request.POST.get('premedication_given', ''),
            anaesthetic_consent_obtained=request.POST.get('anaesthetic_consent_obtained') == 'on',
            pre_op_assessment_completed=pre_op_dt or timezone.now(),
            anaesthesia_type=request.POST.get('anaesthesia_type', ''),
            planned_agents=request.POST.get('planned_agents', ''),
            created_by=request.user,
        )
        messages.success(request, 'Pre-operative anaesthetic assessment saved.')
        return redirect('ipd:anaesthetic_record_detail', record_id=record.pk)

    from .models import ASAGrade
    return render(request, 'ipd/anaesthetic_chart.html', {
        'booking': booking,
        'patient': booking.patient,
        'asa_grades': ASAGrade.choices,
        'mode': 'create',
    })


@login_required
def anaesthetic_record_detail(request, record_id):
    """View / update an anaesthetic record (add intraop + postop data)."""
    from .models import AnaestheticRecord
    record = get_object_or_404(AnaestheticRecord, pk=record_id, is_deleted=False)

    if not _can_manage_anaesthetics(request.user):
        return HttpResponseForbidden()

    if request.method == 'POST':
        fields_to_update = [
            'induction_agent', 'induction_dose', 'maintenance_agent',
            'airway_management', 'analgesics_used', 'muscle_relaxants_used',
            'reversal_agents', 'monitoring_notes', 'intraoperative_complications',
            'post_op_instructions', 'post_op_complications', 'iv_fluids_given',
        ]
        for f in fields_to_update:
            val = request.POST.get(f)
            if val is not None:
                setattr(record, f, val)
        for int_field in [
            'total_duration_minutes', 'estimated_blood_loss_ml',
            'recovery_time_mins', 'pain_score_on_discharge',
        ]:
            val = request.POST.get(int_field)
            setattr(record, int_field, int(val) if val else None)
        record.post_op_nausea_vomiting = request.POST.get('post_op_nausea_vomiting') == 'on'
        record.updated_by = request.user
        record.save()
        messages.success(request, 'Anaesthetic record updated.')
        return redirect('ipd:anaesthetic_record_detail', record_id=record.pk)

    from .models import ASAGrade
    return render(request, 'ipd/anaesthetic_chart.html', {
        'record': record,
        'patient': record.patient,
        'booking': record.surgical_booking,
        'asa_grades': ASAGrade.choices,
        'mode': 'detail',
    })


@login_required
def anaesthetic_record_list(request):
    """List all anaesthetic records — for anaesthetists and medical directors."""
    from .models import AnaestheticRecord
    if not _can_manage_anaesthetics(request.user):
        return HttpResponseForbidden()

    qs = AnaestheticRecord.objects.filter(is_deleted=False).select_related(
        'patient', 'anaesthetist', 'surgical_booking'
    ).order_by('-created_at')

    date_from = request.GET.get('date_from')
    date_to   = request.GET.get('date_to')
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    return render(request, 'ipd/anaesthetic_list.html', {
        'records': qs[:200],
        'date_from': date_from or '',
        'date_to':   date_to   or '',
        'today': timezone.localdate(),
    })


# ── Nursing Care Plan (JCI COP.8) ─────────────────────────────────────────────

def _can_manage_care_plan(user):
    return (user.is_super_admin or user.is_medical_director or
            user.is_nurse or user.role == 'nurse_director')


@login_required
def care_plan_create(request, admission_id):
    """Create a nursing care plan for an inpatient admission."""
    from .models import NursingCarePlan
    admission = get_object_or_404(Admission, pk=admission_id, is_deleted=False)

    if not _can_manage_care_plan(request.user):
        return HttpResponseForbidden()

    existing = NursingCarePlan.objects.filter(
        admission=admission, is_active=True, is_deleted=False
    ).first()
    if existing:
        return redirect('ipd:care_plan_detail', plan_id=existing.pk)

    if request.method == 'POST':
        plan = NursingCarePlan.objects.create(
            admission=admission,
            nurse=request.user,
            nursing_diagnoses=request.POST.get('nursing_diagnoses', ''),
            short_term_goals=request.POST.get('short_term_goals', ''),
            long_term_goals=request.POST.get('long_term_goals', ''),
            hygiene_mobility_care=request.POST.get('hygiene_mobility_care', ''),
            medication_eye_drop_schedule=request.POST.get('medication_eye_drop_schedule', ''),
            wound_eye_dressing_care=request.POST.get('wound_eye_dressing_care', ''),
            nutrition_hydration_plan=request.POST.get('nutrition_hydration_plan', ''),
            vital_signs_monitoring=request.POST.get('vital_signs_monitoring', ''),
            patient_family_education=request.POST.get('patient_family_education', ''),
            psychological_support=request.POST.get('psychological_support', ''),
            discharge_planning=request.POST.get('discharge_planning', ''),
            safety_measures=request.POST.get('safety_measures', ''),
            evaluation_notes=request.POST.get('evaluation_notes', ''),
            next_review_date=request.POST.get('next_review_date') or None,
            created_by=request.user,
        )
        messages.success(request, 'Nursing care plan created.')
        return redirect('ipd:care_plan_detail', plan_id=plan.pk)

    return render(request, 'ipd/care_plan.html', {
        'admission': admission,
        'patient': admission.patient,
        'mode': 'create',
    })


@login_required
def care_plan_detail(request, plan_id):
    """View / update a nursing care plan."""
    from .models import NursingCarePlan
    plan = get_object_or_404(NursingCarePlan, pk=plan_id, is_deleted=False)

    if not _can_manage_care_plan(request.user):
        return HttpResponseForbidden()

    if request.method == 'POST':
        for field in [
            'nursing_diagnoses', 'short_term_goals', 'long_term_goals',
            'hygiene_mobility_care', 'medication_eye_drop_schedule',
            'wound_eye_dressing_care', 'nutrition_hydration_plan',
            'vital_signs_monitoring', 'patient_family_education',
            'psychological_support', 'discharge_planning',
            'safety_measures', 'evaluation_notes',
        ]:
            setattr(plan, field, request.POST.get(field, getattr(plan, field)))
        plan.next_review_date = request.POST.get('next_review_date') or plan.next_review_date
        plan.updated_by = request.user
        plan.save()
        messages.success(request, 'Care plan updated.')
        return redirect('ipd:care_plan_detail', plan_id=plan.pk)

    return render(request, 'ipd/care_plan.html', {
        'plan': plan,
        'admission': plan.admission,
        'patient': plan.admission.patient,
        'mode': 'detail',
    })


# ══════════════════════════════════════════════════════════════════════════════
# PRE-OP CHECK-IN  (Gap 2)
# Theatre / pre-op nurse checks in patients arriving for surgery day.
# Issues a PRE_OP QMS token and marks booking as SCHEDULED.
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def pre_op_checkin(request):
    """
    Theatre / pre-op nurse: list of today's surgical bookings.
    One-click check-in issues a PRE_OP QMS token and marks the patient as arrived.
    """
    if not (request.user.is_theatre_nurse or request.user.is_anaesthetist
            or request.user.is_super_admin or request.user.is_medical_director
            or request.user.is_admission_officer):
        return HttpResponseForbidden()

    today = timezone.localdate()
    bookings = SurgicalBooking.objects.filter(
        surgery_date__date=today,
        is_deleted=False,
    ).exclude(status=SurgicalBookingStatus.CANCELLED).select_related(
        'patient', 'surgeon'
    ).order_by('surgery_date')

    if request.method == 'POST':
        booking_id = request.POST.get('booking_id')
        booking = get_object_or_404(SurgicalBooking, pk=booking_id, is_deleted=False)
        patient = booking.patient

        # Issue PRE_OP QMS token
        if _qms_active():
            try:
                from apps.qms.models import (
                    QueueToken, DailyTokenSequence,
                    IssuancePoint, TIER_PRIORITY,
                )
                from apps.patients.models import Visit
                visit = Visit.objects.filter(
                    patient=patient,
                    visit_date__date=today,
                    is_deleted=False,
                ).order_by('-visit_date').first()
                tier = visit.service_tier if visit else 'STANDARD'
                token_number = DailyTokenSequence.next_dept_token('PRE_OP')
                QueueToken.objects.create(
                    token_number=token_number,
                    patient=patient,
                    visit=visit,
                    patient_name=patient.full_name,
                    service_type='PRE_OP',
                    service_tier=tier,
                    issuance_point=IssuancePoint.SYSTEM,
                    priority=TIER_PRIORITY.get(tier, 0),
                    notes=f'Surgery: {booking.get_procedure_display()} | {booking.booking_number}',
                    issued_by=request.user,
                )
            except Exception:
                pass

        booking.status = SurgicalBookingStatus.SCHEDULED
        booking.save(update_fields=['status', 'updated_at'])
        messages.success(request, f'{patient.full_name} checked in for surgery. PRE_OP token issued.')
        return redirect('ipd:pre_op_checkin')

    return render(request, 'ipd/pre_op_checkin.html', {
        'bookings': bookings,
        'today': today,
    })


# ══════════════════════════════════════════════════════════════════════════════
# ADMISSION / SURGICAL STATS  (CEO, Medical Director, Admin Director, Super Admin)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def admission_stats(request):
    """Admission Officer / leadership statistics for surgical bookings."""
    from apps.accounts.models import UserRole
    allowed = [
        UserRole.SUPER_ADMIN, UserRole.MEDICAL_DIRECTOR, UserRole.CEO,
        UserRole.ADMIN_DIRECTOR, UserRole.ADMISSION_OFFICER,
    ]
    if request.user.role not in allowed:
        return HttpResponseForbidden()

    from django.db.models import Count, Q, Sum
    from django.db.models.functions import TruncMonth

    # ── Date range filter ─────────────────────────────────────────────────
    period = request.GET.get('period', '30')
    if period == 'all':
        qs = SurgicalBooking.objects.filter(is_deleted=False)
    else:
        try:
            days = int(period)
        except ValueError:
            days = 30
        cutoff = timezone.localdate() - timezone.timedelta(days=days)
        qs = SurgicalBooking.objects.filter(is_deleted=False, created_at__date__gte=cutoff)

    total = qs.count()

    # By status
    by_status = dict(qs.values('status').annotate(n=Count('id')).values_list('status', 'n'))

    # By surgery type (procedure)
    by_procedure = list(
        qs.values('procedure').annotate(n=Count('id')).order_by('-n')[:10]
    )

    # By service tier
    from apps.patients.models import Visit
    tier_data = {}
    for booking in qs.select_related('patient'):
        visit = Visit.objects.filter(
            patient=booking.patient,
            visit_date__date=booking.created_at.date() if booking.created_at else timezone.localdate(),
            is_deleted=False,
        ).order_by('-visit_date').first()
        tier = visit.service_tier if visit else 'STANDARD'
        tier_data[tier] = tier_data.get(tier, 0) + 1

    # By gender
    by_gender = dict(
        qs.select_related('patient').values('patient__gender').annotate(n=Count('id')).values_list('patient__gender', 'n')
    )

    # Revenue
    revenue = qs.aggregate(
        total_invoiced=Sum('total_amount'),
        total_deposited=Sum('deposit_paid'),
    )

    # Monthly trend (last 6 months)
    monthly = list(
        qs.annotate(month=TruncMonth('created_at'))
        .values('month').annotate(n=Count('id')).order_by('month')
    )

    # Top surgeons
    top_surgeons = list(
        qs.filter(surgeon__isnull=False)
        .values('surgeon__first_name', 'surgeon__last_name')
        .annotate(n=Count('id')).order_by('-n')[:5]
    )

    return render(request, 'ipd/admission_stats.html', {
        'total': total,
        'by_status': by_status,
        'by_procedure': by_procedure,
        'tier_data': tier_data,
        'by_gender': by_gender,
        'revenue': revenue,
        'monthly': monthly,
        'top_surgeons': top_surgeons,
        'period': period,
        'booking_statuses': SurgicalBookingStatus.choices,
    })


# ══════════════════════════════════════════════════════════════════════════════
# PRE-OP INSTRUCTION SHEET  (printable)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def preop_instruction_sheet(request, booking_id):
    """Printable pre-operative instruction sheet for the patient."""
    booking = get_object_or_404(SurgicalBooking, pk=booking_id, is_deleted=False)
    return render(request, 'ipd/preop_instruction_sheet.html', {
        'booking': booking,
        'patient': booking.patient,
    })


# ── Vital Signs Flowsheet ─────────────────────────────────────────────────────

def _can_chart_vitals(user):
    from apps.accounts.models import UserRole
    return user.role in {
        UserRole.WARD_NURSE, UserRole.THEATRE_NURSE, UserRole.NURSE_DIRECTOR,
        UserRole.MEDICAL_DIRECTOR, UserRole.SUPER_ADMIN,
        UserRole.ANAESTHETIST,
    } or user.is_doctor


@login_required
def vital_signs_flowsheet(request, admission_id):
    """View and add vital signs for an admitted patient."""
    admission = get_object_or_404(Admission, pk=admission_id, is_deleted=False)
    if not _can_chart_vitals(request.user):
        return HttpResponseForbidden()

    if request.method == 'POST':
        def int_or_none(val):
            try: return int(val) if val else None
            except: return None

        def decimal_or_none(val):
            if not val: return None
            try:
                from decimal import Decimal
                return Decimal(val)
            except: return None

        recorded_at_raw = request.POST.get('recorded_at')
        try:
            from django.utils.dateparse import parse_datetime
            recorded_at = parse_datetime(recorded_at_raw) if recorded_at_raw else timezone.now()
            if recorded_at and timezone.is_naive(recorded_at):
                recorded_at = timezone.make_aware(recorded_at)
        except Exception:
            recorded_at = timezone.now()

        VitalSigns.objects.create(
            admission=admission,
            recorded_by=request.user,
            recorded_at=recorded_at or timezone.now(),
            temperature=decimal_or_none(request.POST.get('temperature')),
            pulse=int_or_none(request.POST.get('pulse')),
            respiratory_rate=int_or_none(request.POST.get('respiratory_rate')),
            spo2=int_or_none(request.POST.get('spo2')),
            bp_systolic=int_or_none(request.POST.get('bp_systolic')),
            bp_diastolic=int_or_none(request.POST.get('bp_diastolic')),
            blood_glucose=decimal_or_none(request.POST.get('blood_glucose')),
            pain_score=int_or_none(request.POST.get('pain_score')),
            visual_acuity_re=request.POST.get('visual_acuity_re', ''),
            visual_acuity_le=request.POST.get('visual_acuity_le', ''),
            iop_re=decimal_or_none(request.POST.get('iop_re')),
            iop_le=decimal_or_none(request.POST.get('iop_le')),
            gcs=int_or_none(request.POST.get('gcs')),
            notes=request.POST.get('notes', ''),
        )
        messages.success(request, 'Vital signs recorded.')
        return redirect('ipd:vital_signs', admission_id=admission_id)

    entries = admission.vital_signs.select_related('recorded_by').order_by('-recorded_at')

    # Build chart series data (last 24 entries, chronological)
    chart_data = []
    for v in reversed(list(entries[:24])):
        chart_data.append({
            'time': v.recorded_at.strftime('%d/%m %H:%M'),
            'pulse': v.pulse,
            'bp_sys': v.bp_systolic,
            'bp_dia': v.bp_diastolic,
            'spo2': v.spo2,
            'temp': float(v.temperature) if v.temperature else None,
        })

    import json as _json
    return render(request, 'ipd/vital_signs_flowsheet.html', {
        'admission': admission,
        'entries': entries,
        'chart_data_json': _json.dumps(chart_data),
        'now': timezone.now(),
        'can_add': _can_chart_vitals(request.user),
    })


# ── Fluid Balance Chart ───────────────────────────────────────────────────────

@login_required
def fluid_balance_chart(request, admission_id):
    """View and add fluid balance entries for an admitted patient."""
    admission = get_object_or_404(Admission, pk=admission_id, is_deleted=False)
    if not _can_chart_vitals(request.user):
        return HttpResponseForbidden()

    if request.method == 'POST':
        entry_type = request.POST.get('entry_type', '')
        volume_ml = request.POST.get('volume_ml', '0')
        description = request.POST.get('description', '')
        notes = request.POST.get('notes', '')

        try:
            vol = int(volume_ml)
        except ValueError:
            messages.error(request, 'Invalid volume.')
            return redirect('ipd:fluid_balance', admission_id=admission_id)

        FluidBalance.objects.create(
            admission=admission,
            recorded_by=request.user,
            entry_type=entry_type,
            volume_ml=vol,
            description=description,
            notes=notes,
        )
        messages.success(request, 'Fluid entry recorded.')
        return redirect('ipd:fluid_balance', admission_id=admission_id)

    entries = admission.fluid_entries.select_related('recorded_by').order_by('-recorded_at')

    from django.db.models import Sum, Case, When, IntegerField, Value
    totals = admission.fluid_entries.aggregate(
        total_in=Sum(Case(When(is_intake=True, then='volume_ml'), default=Value(0), output_field=IntegerField())),
        total_out=Sum(Case(When(is_intake=False, then='volume_ml'), default=Value(0), output_field=IntegerField())),
    )
    total_in = totals['total_in'] or 0
    total_out = totals['total_out'] or 0
    balance = total_in - total_out

    return render(request, 'ipd/fluid_balance_chart.html', {
        'admission': admission,
        'entries': entries,
        'total_in': total_in,
        'total_out': total_out,
        'balance': balance,
        'entry_types': FluidEntryType.choices,
        'can_add': _can_chart_vitals(request.user),
        'now': timezone.now(),
    })


# ── Bed Map ───────────────────────────────────────────────────────────────────

@login_required
def bed_map_view(request):
    """Real-time visual bed occupancy grid grouped by ward."""
    from django.db.models import Prefetch, Count, Q
    wards = (
        Ward.objects
        .filter(is_deleted=False, is_active=True)
        .prefetch_related(
            Prefetch(
                'beds',
                queryset=Bed.objects.filter(is_deleted=False).select_related(
                    'admissions__patient'
                ).prefetch_related(
                    Prefetch(
                        'admissions',
                        queryset=Admission.objects.filter(
                            status=AdmissionStatus.ADMITTED, is_deleted=False
                        ).select_related('patient'),
                        to_attr='active_admissions'
                    )
                ),
                to_attr='bed_list'
            )
        )
        .order_by('name')
    )

    ward_data = []
    total_beds = total_occupied = total_available = total_maintenance = 0
    for ward in wards:
        beds = ward.bed_list
        occupied = [b for b in beds if b.status == BedStatus.OCCUPIED]
        available = [b for b in beds if b.status == BedStatus.AVAILABLE]
        maintenance = [b for b in beds if b.status == BedStatus.MAINTENANCE]
        reserved = [b for b in beds if b.status == BedStatus.RESERVED]
        occ_rate = round(len(occupied) / len(beds) * 100) if beds else 0
        ward_data.append({
            'ward': ward,
            'beds': beds,
            'occupied_count': len(occupied),
            'available_count': len(available),
            'maintenance_count': len(maintenance),
            'reserved_count': len(reserved),
            'total_count': len(beds),
            'occupancy_rate': occ_rate,
        })
        total_beds += len(beds)
        total_occupied += len(occupied)
        total_available += len(available)
        total_maintenance += len(maintenance)

    overall_rate = round(total_occupied / total_beds * 100) if total_beds else 0
    return render(request, 'ipd/bed_map.html', {
        'ward_data': ward_data,
        'total_beds': total_beds,
        'total_occupied': total_occupied,
        'total_available': total_available,
        'total_maintenance': total_maintenance,
        'overall_rate': overall_rate,
        'now': timezone.now(),
    })


# ── Surgical Outcome Tracking ─────────────────────────────────────────────────

def _can_record_outcome(user):
    return user.role in (
        'super_admin', 'medical_director', 'admin_director',
        'ophthalmologist', 'retina_specialist', 'glaucoma_specialist',
        'cataract_surgeon', 'cornea_specialist', 'oculoplastics_surgeon',
        'neuro_ophthalmologist', 'uveitis_specialist', 'pediatric_ophthalmologist',
        'admission_officer',
    )


@login_required
def surgical_outcome_list(request):
    """List all surgical outcomes — searchable, filterable by procedure/grade."""
    if not _can_record_outcome(request.user):
        return HttpResponseForbidden()

    qs = SurgicalOutcome.objects.filter(is_deleted=False).select_related(
        'patient', 'surgeon', 'booking'
    )
    q = request.GET.get('q', '').strip()
    grade = request.GET.get('grade', '')
    if q:
        from django.db.models import Q
        qs = qs.filter(
            Q(patient__first_name__icontains=q) |
            Q(patient__last_name__icontains=q) |
            Q(booking__procedure__icontains=q)
        )
    if grade:
        qs = qs.filter(outcome_grade=grade)

    return render(request, 'ipd/surgical_outcome_list.html', {
        'outcomes': qs[:200],
        'grade_choices': OutcomeGrade.choices,
        'q': q,
        'grade': grade,
    })


@login_required
def surgical_outcome_create(request, booking_id):
    """Create or edit surgical outcome for a booking."""
    if not _can_record_outcome(request.user):
        return HttpResponseForbidden()

    booking = get_object_or_404(SurgicalBooking, id=booking_id, is_deleted=False)
    outcome, _ = SurgicalOutcome.objects.get_or_create(
        booking=booking,
        defaults={'patient': booking.patient, 'surgeon': booking.surgeon}
    )

    if request.method == 'POST':
        outcome.surgery_date = request.POST.get('surgery_date') or None
        outcome.pre_va_right = request.POST.get('pre_va_right', '').strip()
        outcome.pre_va_left = request.POST.get('pre_va_left', '').strip()
        outcome.pre_iop_right = request.POST.get('pre_iop_right') or None
        outcome.pre_iop_left = request.POST.get('pre_iop_left') or None
        outcome.post_va_right = request.POST.get('post_va_right', '').strip()
        outcome.post_va_left = request.POST.get('post_va_left', '').strip()
        outcome.post_iop_right = request.POST.get('post_iop_right') or None
        outcome.post_iop_left = request.POST.get('post_iop_left') or None
        outcome.outcome_grade = request.POST.get('outcome_grade', '').strip()
        outcome.intraoperative_complications = request.POST.get('intraoperative_complications', '').strip()
        outcome.postoperative_complications = request.POST.get('postoperative_complications', '').strip()
        outcome.follow_up_date = request.POST.get('follow_up_date') or None
        outcome.notes = request.POST.get('notes', '').strip()
        outcome.recorded_by = request.user
        outcome.save()
        messages.success(request, f'Surgical outcome recorded for {booking.patient.full_name}.')
        return redirect('ipd:surgical_outcome_list')

    va_choices = ['6/6','6/9','6/12','6/18','6/24','6/36','6/60','3/60','1/60','CF','HM','PL','NPL']
    return render(request, 'ipd/surgical_outcome_form.html', {
        'booking': booking,
        'outcome': outcome,
        'outcome_grade_choices': OutcomeGrade.choices,
        'va_choices': va_choices,
        'today': timezone.localdate(),
    })


@login_required
def surgical_outcome_report(request):
    """Statistics: outcomes by grade, procedure, surgeon, month."""
    if not _can_record_outcome(request.user):
        return HttpResponseForbidden()

    from django.db.models import Count
    from django.db.models.functions import TruncMonth

    outcomes = SurgicalOutcome.objects.filter(is_deleted=False)
    by_grade = (
        outcomes.exclude(outcome_grade='').values('outcome_grade')
        .annotate(total=Count('id')).order_by('outcome_grade')
    )
    by_procedure = (
        outcomes.values('booking__procedure')
        .annotate(total=Count('id')).order_by('-total')[:10]
    )
    by_surgeon = (
        outcomes.filter(surgeon__isnull=False)
        .values('surgeon__first_name', 'surgeon__last_name')
        .annotate(total=Count('id')).order_by('-total')[:10]
    )
    by_month = (
        outcomes.filter(surgery_date__isnull=False)
        .annotate(month=TruncMonth('surgery_date'))
        .values('month').annotate(total=Count('id')).order_by('-month')[:12]
    )
    grade_map = dict(OutcomeGrade.choices)
    grade_data = [{'grade': grade_map.get(r['outcome_grade'], r['outcome_grade']), 'total': r['total']} for r in by_grade]
    complications = outcomes.exclude(
        intraoperative_complications='', postoperative_complications=''
    ).count()

    return render(request, 'ipd/surgical_outcome_report.html', {
        'total_outcomes': outcomes.count(),
        'by_grade': grade_data,
        'by_procedure': by_procedure,
        'by_surgeon': by_surgeon,
        'by_month': list(by_month),
        'complications_count': complications,
    })


# ── Theatre Utilization Report ────────────────────────────────────────────────

@login_required
def theatre_utilization_report(request):
    """Surgery volume by type, surgeon, session, and month."""
    if not _can_record_outcome(request.user):
        return HttpResponseForbidden()

    from django.db.models import Count, Q
    from django.db.models.functions import TruncMonth

    bookings = SurgicalBooking.objects.filter(
        is_deleted=False, status=SurgicalBookingStatus.COMPLETED
    )

    # Filter by date range
    from_date = request.GET.get('from_date', '')
    to_date = request.GET.get('to_date', '')
    if from_date:
        bookings = bookings.filter(surgery_date__date__gte=from_date)
    if to_date:
        bookings = bookings.filter(surgery_date__date__lte=to_date)

    by_procedure = (
        bookings.values('procedure').annotate(total=Count('id')).order_by('-total')
    )
    by_surgeon = (
        bookings.filter(surgeon__isnull=False)
        .values('surgeon__first_name', 'surgeon__last_name')
        .annotate(total=Count('id')).order_by('-total')
    )
    by_category = (
        bookings.exclude(surgery_category='').values('surgery_category')
        .annotate(total=Count('id')).order_by('-total')
    )
    by_month = (
        bookings.filter(surgery_date__isnull=False)
        .annotate(month=TruncMonth('surgery_date'))
        .values('month').annotate(total=Count('id')).order_by('-month')[:12]
    )
    by_anaesthesia = (
        bookings.exclude(anaesthesia_type='').values('anaesthesia_type')
        .annotate(total=Count('id')).order_by('-total')
    )

    surgery_type_map = dict(SurgeryType.choices)
    category_labels = dict([
        ('CATARACT', 'Cataract'), ('RETINA', 'Retina/VR'), ('GLAUCOMA', 'Glaucoma'),
        ('CORNEA', 'Cornea'), ('OCULOPLASTY', 'Oculoplasty'), ('STRABISMUS', 'Strabismus'),
        ('PTERYGIUM', 'Pterygium'), ('LACRIMAL', 'Lacrimal'), ('CHALAZION', 'Chalazion'),
        ('TRAUMA', 'Trauma'), ('TUMOUR', 'Tumour/Orbital'), ('OTHER', 'Other'),
    ])

    return render(request, 'ipd/theatre_utilization.html', {
        'total_surgeries': bookings.count(),
        'by_procedure': [{'label': surgery_type_map.get(r['procedure'], r['procedure']), 'total': r['total']} for r in by_procedure],
        'by_surgeon': list(by_surgeon),
        'by_category': [{'label': category_labels.get(r['surgery_category'], r['surgery_category']), 'total': r['total']} for r in by_category],
        'by_month': list(by_month),
        'by_anaesthesia': list(by_anaesthesia),
        'from_date': from_date,
        'to_date': to_date,
    })
