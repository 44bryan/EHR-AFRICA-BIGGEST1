from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone
from django.db import models
from django.db.models import Count, Q, Sum, Avg
from datetime import timedelta
import json


# Keywords that indicate an ophthalmic emergency or urgency
_EMERGENCY_KW = [
    'sudden vision loss', 'sudden loss', 'no vision', 'cannot see', 'blind',
    'chemical', 'acid', 'alkali', 'trauma', 'injury', 'penetrating', 'burst',
    'retinal detachment', 'detachment', 'flashes', 'severe pain', 'central vision',
    'vomiting', 'halos', 'angle closure', 'acute glaucoma',
]
_URGENT_KW = [
    'red eye', 'pain', 'discharge', 'swelling', 'decreased vision',
    'blurred', 'double vision', 'diplopia', 'floaters', 'photophobia',
    'post-op', 'post op', 'after surgery', 'inflammation',
]


def _compute_ai_triage(visit):
    """
    Rule-based ophthalmology triage scoring.
    Returns ('EMERGENCY'|'URGENT'|'ROUTINE', reason_str).
    """
    vs = getattr(visit, 'vital_signs', None) or {}
    if hasattr(vs, 'get'):
        iop_re = vs.get('intraocular_pressure_right') or 0
        iop_le = vs.get('intraocular_pressure_left') or 0
        va_re = str(vs.get('visual_acuity_right') or '').upper()
        va_le = str(vs.get('visual_acuity_left') or '').upper()
    else:
        iop_re = iop_le = 0
        va_re = va_le = ''

    cc = str(visit.chief_complaint or '').lower()

    # Try parsing IOP values
    try:
        iop_re = float(str(iop_re).split('/')[0].strip())
    except (ValueError, AttributeError):
        iop_re = 0
    try:
        iop_le = float(str(iop_le).split('/')[0].strip())
    except (ValueError, AttributeError):
        iop_le = 0

    max_iop = max(iop_re, iop_le)

    # Check for NPL/PL/HM/CF vision (very poor VA)
    poor_va = any(x in va_re or x in va_le for x in ['NPL', 'PL ', 'HM', 'CF'])

    # Emergency
    if max_iop >= 40 or poor_va or any(kw in cc for kw in _EMERGENCY_KW):
        if max_iop >= 40:
            return 'EMERGENCY', f'IOP {int(max_iop)} mmHg'
        if poor_va:
            return 'EMERGENCY', 'Very poor VA'
        kw = next((kw for kw in _EMERGENCY_KW if kw in cc), '')
        return 'EMERGENCY', f'CC: {kw}'

    # Urgent
    if max_iop >= 22 or any(kw in cc for kw in _URGENT_KW):
        if max_iop >= 22:
            return 'URGENT', f'IOP {int(max_iop)} mmHg'
        kw = next((kw for kw in _URGENT_KW if kw in cc), '')
        return 'URGENT', f'CC: {kw}'

    return 'ROUTINE', ''


def _ceo_dashboard(request, user, today, ctx):
    """
    CEO / Admin Director executive dashboard.
    Top-level KPIs only — no clinical detail. Click-through to Leadership tabs.
    """
    from apps.patients.models import Patient, Visit
    from apps.appointments.models import Appointment

    month_start = today.replace(day=1)
    year_start  = today.replace(month=1, day=1)
    last_30     = today - timedelta(days=30)

    total_patients  = Patient.objects.filter(is_deleted=False).count()
    new_month       = Patient.objects.filter(created_at__date__gte=month_start, is_deleted=False).count()
    today_visits    = Visit.objects.filter(visit_date__date=today, is_deleted=False).count()
    today_appts     = Appointment.objects.filter(appointment_date=today, is_deleted=False).count()

    try:
        from apps.billing.models import Payment, Invoice, InvoiceStatus
        rev_today = Payment.objects.filter(payment_date__date=today, is_deleted=False).aggregate(t=Sum('amount'))['t'] or 0
        rev_month = Payment.objects.filter(payment_date__date__gte=month_start, is_deleted=False).aggregate(t=Sum('amount'))['t'] or 0
        rev_year  = Payment.objects.filter(payment_date__date__gte=year_start, is_deleted=False).aggregate(t=Sum('amount'))['t'] or 0
        outstanding = sum(
            inv.balance_due for inv in
            Invoice.objects.filter(status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID], is_deleted=False)
            .prefetch_related('items', 'payments')
        )
        # 7-day revenue spark
        rev_7d = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            amt = Payment.objects.filter(payment_date__date=d, is_deleted=False).aggregate(t=Sum('amount'))['t'] or 0
            rev_7d.append({'date': d.strftime('%d %b'), 'amount': float(amt)})
    except Exception:
        rev_today = rev_month = rev_year = outstanding = 0
        rev_7d = [{'date': '', 'amount': 0}]

    try:
        from apps.qms.models import QueueToken, TokenStatus
        queue_now = QueueToken.objects.filter(token_date=today, status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING], is_deleted=False).count()
        served_today = QueueToken.objects.filter(token_date=today, status=TokenStatus.COMPLETED, is_deleted=False).count()
    except Exception:
        queue_now = served_today = 0

    try:
        from apps.ipd.models import Bed, Admission, AdmissionStatus
        total_beds    = Bed.objects.filter(is_deleted=False).count()
        occupied_beds = Bed.objects.filter(status='OCCUPIED', is_deleted=False).count()
        bed_occupancy = round((occupied_beds / total_beds * 100), 1) if total_beds else 0
        admissions    = Admission.objects.filter(status=AdmissionStatus.ADMITTED, is_deleted=False).count()
    except Exception:
        total_beds = occupied_beds = bed_occupancy = admissions = 0

    from apps.accounts.models import User as StaffUser
    total_staff = StaffUser.objects.filter(is_active=True).count()

    try:
        from apps.feedback.models import PatientFeedback
        fb = PatientFeedback.objects.filter(nps_score__isnull=False, is_deleted=False)
        total_fb = fb.count()
        promo = fb.filter(nps_score__gte=9).count()
        detr  = fb.filter(nps_score__lte=6).count()
        nps   = round(((promo - detr) / total_fb) * 100) if total_fb else 0
        open_complaints = PatientFeedback.objects.filter(
            status__in=['NEW', 'ACKNOWLEDGED', 'INVESTIGATING'], is_deleted=False
        ).count()
    except Exception:
        nps = open_complaints = 0

    ctx.update({
        'total_patients': total_patients,
        'new_month': new_month,
        'today_visits': today_visits,
        'today_appts': today_appts,
        'rev_today': rev_today,
        'rev_month': rev_month,
        'rev_year': rev_year,
        'outstanding': outstanding,
        'rev_7d_json': json.dumps(rev_7d),
        'queue_now': queue_now,
        'served_today': served_today,
        'bed_occupancy': bed_occupancy,
        'occupied_beds': occupied_beds,
        'total_beds': total_beds,
        'admissions': admissions,
        'total_staff': total_staff,
        'nps': nps,
        'open_complaints': open_complaints,
    })
    return render(request, 'dashboard/ceo.html', ctx)


def _admin_director_dashboard(request, user, today, ctx):
    """
    Admin Director — operations & administration dashboard.
    Focuses on staff, scheduling, inventory, patient flow, complaints.
    No clinical detail, no financial deep-dive.
    """
    from apps.patients.models import Patient, Visit
    from apps.appointments.models import Appointment

    month_start = today.replace(day=1)

    # Patient registrations
    new_today  = Patient.objects.filter(created_at__date=today, is_deleted=False).count()
    new_month  = Patient.objects.filter(created_at__date__gte=month_start, is_deleted=False).count()
    total_pts  = Patient.objects.filter(is_deleted=False).count()

    # Appointments
    today_appts   = Appointment.objects.filter(appointment_date=today, is_deleted=False).count()
    pending_appts = Appointment.objects.filter(
        appointment_date=today, status__in=['SCHEDULED', 'CONFIRMED'], is_deleted=False
    ).count()

    # Queue
    try:
        from apps.qms.models import QueueToken, TokenStatus
        queue_waiting = QueueToken.objects.filter(
            token_date=today, status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
            is_deleted=False
        ).count()
        served_today  = QueueToken.objects.filter(
            token_date=today, status=TokenStatus.COMPLETED, is_deleted=False
        ).count()
    except Exception:
        queue_waiting = served_today = 0

    # Beds / IPD
    try:
        from apps.ipd.models import Bed, Admission, AdmissionStatus
        total_beds    = Bed.objects.filter(is_deleted=False).count()
        occupied_beds = Bed.objects.filter(status='OCCUPIED', is_deleted=False).count()
        bed_occupancy = round((occupied_beds / total_beds * 100), 1) if total_beds else 0
    except Exception:
        total_beds = occupied_beds = bed_occupancy = 0

    # Staff
    from apps.accounts.models import User as StaffUser
    total_staff  = StaffUser.objects.filter(is_active=True).count()

    # Inventory alerts
    try:
        from apps.inventory.models import InventoryItem
        low_stock = InventoryItem.objects.filter(
            quantity__lte=models.F('reorder_level'), is_deleted=False
        ).count()
    except Exception:
        low_stock = 0

    # Service recovery / complaints
    try:
        from apps.feedback.models import PatientFeedback
        open_complaints = PatientFeedback.objects.filter(
            status__in=['NEW', 'ACKNOWLEDGED', 'INVESTIGATING'], is_deleted=False
        ).count()
        nps_data = PatientFeedback.objects.filter(nps_score__isnull=False, is_deleted=False)
        total_fb = nps_data.count()
        promo    = nps_data.filter(nps_score__gte=9).count()
        detr     = nps_data.filter(nps_score__lte=6).count()
        nps      = round(((promo - detr) / total_fb) * 100) if total_fb else 0
    except Exception:
        open_complaints = nps = 0

    # Leads
    try:
        from apps.leads.models import Lead
        new_leads = Lead.objects.filter(created_at__date=today, is_deleted=False).count()
    except Exception:
        new_leads = 0

    ctx.update({
        'new_today': new_today,
        'new_month': new_month,
        'total_pts': total_pts,
        'today_appts': today_appts,
        'pending_appts': pending_appts,
        'queue_waiting': queue_waiting,
        'served_today': served_today,
        'total_beds': total_beds,
        'occupied_beds': occupied_beds,
        'bed_occupancy': bed_occupancy,
        'total_staff': total_staff,
        'low_stock': low_stock,
        'open_complaints': open_complaints,
        'nps': nps,
        'new_leads': new_leads,
    })
    return render(request, 'dashboard/admin_director.html', ctx)


@login_required
def home_view(request):
    """Route each user to their role-specific work dashboard."""
    user = request.user
    if user.must_change_password:
        return redirect('accounts:password_change')

    today = timezone.localdate()
    ctx = {'today': today, 'user': user}

    from apps.patients.models import Patient, Visit, VisitStatus
    from apps.appointments.models import Appointment
    from apps.consultations.models import Consultation

    role = user.role

    # ── Gatekeeper → Gate Entry directly ─────────────────────────────────
    if user.is_gatekeeper:
        return redirect('qms:gate_issue')

    # ── Super Admin → Staff Management Hub ───────────────────────────────
    if user.is_super_admin:
        return redirect('accounts:staff_hub')

    # ── Finance Director → Finance Dashboard ─────────────────────────────
    if user.is_finance_director:
        return redirect('leadership:finance_dashboard')

    # ── CEO → Full Executive Dashboard ───────────────────────────────────
    if user.is_ceo:
        return _ceo_dashboard(request, user, today, ctx)

    # ── Admin Director → Operations & Administration Dashboard ───────────
    if user.is_admin_director:
        return _admin_director_dashboard(request, user, today, ctx)

    # ── Medical Director ──────────────────────────────────────────────────
    # If assigned to a department, they practice as a specialist → doctor queue.
    # If no department assigned, show the clinical oversight dashboard.
    if user.is_medical_director and not user.department:
        month_start = today.replace(day=1)
        last_30    = today - timedelta(days=30)

        # ── TODAY: live patient flow ──────────────────────────────────────
        today_visits_qs = Visit.objects.filter(visit_date__date=today, is_deleted=False)
        today_visits        = today_visits_qs.count()
        currently_inhouse   = today_visits_qs.filter(
            status__in=['WAITING', 'TRIAGE', 'IN_CONSULTATION', 'INVESTIGATION']
        ).count()
        waiting_triage      = today_visits_qs.filter(status__in=['WAITING', 'TRIAGE']).count()
        with_doctor         = today_visits_qs.filter(status='IN_CONSULTATION').count()
        discharged_today    = today_visits_qs.filter(
            status__in=['COMPLETED', 'DISCHARGED']
        ).count()

        # ── TODAY: appointments ───────────────────────────────────────────
        today_appts_qs      = Appointment.objects.filter(appointment_date=today, is_deleted=False)
        today_appointments  = today_appts_qs.filter(
            status__in=['SCHEDULED', 'CONFIRMED', 'CHECKED_IN']
        ).count()
        today_no_shows      = today_appts_qs.filter(status='NO_SHOW').count()
        today_new_patients  = today_appts_qs.filter(
            appointment_type='NEW'
        ).count()

        # ── PHARMACY ──────────────────────────────────────────────────────
        try:
            from apps.pharmacy.models import Dispensing, Drug
            dispensing_qs    = Dispensing.objects.filter(
                dispensed_at__date__gte=month_start, is_deleted=False
            )
            pharmacy_revenue = dispensing_qs.aggregate(total=Sum('amount_paid'))['total'] or 0
            dispensing_count = dispensing_qs.count()
            low_stock_count  = Drug.objects.filter(
                is_active=True, is_deleted=False,
                stock_batches__quantity_remaining__lte=10
            ).distinct().count()
        except Exception:
            pharmacy_revenue = dispensing_count = low_stock_count = 0

        # ── IPD / INPATIENT ───────────────────────────────────────────────
        try:
            from apps.ipd.models import Admission, AdmissionStatus
            current_admitted = Admission.objects.filter(
                status=AdmissionStatus.ADMITTED, is_deleted=False
            ).count()
        except Exception:
            current_admitted = 0

        # ── STAFF ──────────────────────────────────────────────────────────
        try:
            from apps.hrms.models import AttendanceRecord, LeaveRequest, LeaveRequestStatus
            staff_present     = AttendanceRecord.objects.filter(
                date=today, status__in=['PRESENT', 'LATE']
            ).count()
            pending_leaves    = LeaveRequest.objects.filter(
                status=LeaveRequestStatus.PENDING, is_deleted=False
            ).count()
        except Exception:
            staff_present = pending_leaves = 0

        # ── PATIENTS ──────────────────────────────────────────────────────
        total_patients  = Patient.objects.filter(is_active=True).count()
        new_this_month  = Patient.objects.filter(
            created_at__date__gte=month_start, is_deleted=False
        ).count()

        # ── CONSULTATIONS ─────────────────────────────────────────────────
        pending_consultations = Consultation.objects.filter(
            status='IN_PROGRESS', is_deleted=False
        ).count()

        # new vs follow-up this month
        new_consults      = Appointment.objects.filter(
            appointment_date__gte=month_start,
            appointment_type='NEW', is_deleted=False
        ).count()
        followup_consults = Appointment.objects.filter(
            appointment_date__gte=month_start,
            appointment_type='FOLLOW_UP', is_deleted=False
        ).count()

        # ── CLINICAL ANALYTICS ────────────────────────────────────────────
        dept_breakdown = list(Consultation.objects.filter(
            created_at__date__gte=last_30, is_deleted=False
        ).values('department__name').annotate(count=Count('id')).order_by('-count')[:8])

        doctor_stats = list(Consultation.objects.filter(
            created_at__date__gte=last_30, is_deleted=False
        ).values(
            'consulting_doctor__first_name', 'consulting_doctor__last_name'
        ).annotate(count=Count('id')).order_by('-count')[:8])

        from apps.consultations.models import ConsultationDiagnosis
        top_diagnoses = list(ConsultationDiagnosis.objects.filter(
            consultation__created_at__date__gte=last_30,
            consultation__is_deleted=False,
        ).values('diagnosis__description').annotate(count=Count('id')).order_by('-count')[:10])

        # ── PATIENT VOLUME TREND (6 months) ───────────────────────────────
        monthly_trend = []
        for i in range(5, -1, -1):
            m_start = (today.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
            m_end   = (m_start.replace(day=28) + timedelta(days=4)).replace(day=1)
            count = Visit.objects.filter(
                visit_date__date__gte=m_start,
                visit_date__date__lt=m_end,
                is_deleted=False,
            ).count()
            monthly_trend.append({'month': m_start.strftime('%b'), 'count': count})

        # ── FEEDBACK / NPS ────────────────────────────────────────────────
        try:
            from apps.feedback.models import PatientFeedback
            total_nps    = PatientFeedback.objects.filter(
                nps_score__isnull=False, is_deleted=False
            ).count()
            promoters    = PatientFeedback.objects.filter(nps_score__gte=9, is_deleted=False).count()
            detractors   = PatientFeedback.objects.filter(nps_score__lte=6, is_deleted=False).count()
            passives     = total_nps - promoters - detractors
            nps          = round(((promoters - detractors) / total_nps) * 100) if total_nps else 0
            avg_satisfaction = PatientFeedback.objects.filter(
                overall_rating__isnull=False, is_deleted=False
            ).aggregate(avg=Avg('overall_rating'))['avg'] or 0
            open_complaints  = PatientFeedback.objects.filter(
                feedback_type='COMPLAINT', status='OPEN', is_deleted=False
            ).count()
        except Exception:
            nps = promoters = passives = detractors = open_complaints = 0
            avg_satisfaction = 0

        ctx.update({
            # Today's pulse
            'today_visits':       today_visits,
            'currently_inhouse':  currently_inhouse,
            'waiting_triage':     waiting_triage,
            'with_doctor':        with_doctor,
            'discharged_today':   discharged_today,
            'today_appointments': today_appointments,
            'today_no_shows':     today_no_shows,
            'today_new_patients': today_new_patients,
            # Pharmacy (clinical only — no revenue)
            'dispensing_count':   dispensing_count,
            # Patients
            'total_patients':     total_patients,
            'new_this_month':     new_this_month,
            'new_consults':       new_consults,
            'followup_consults':  followup_consults,
            # Clinical
            'pending_consultations': pending_consultations,
            'current_admitted':   current_admitted,
            'dept_breakdown':     dept_breakdown,
            'doctor_stats':       doctor_stats,
            'top_diagnoses':      top_diagnoses,
            'monthly_trend':      json.dumps(monthly_trend),
            # Staff
            'staff_present':      staff_present,
            'pending_leaves':     pending_leaves,
            # Quality
            'nps':                nps,
            'avg_satisfaction':   round(float(avg_satisfaction), 1),
            'promoters':          promoters,
            'passives':           passives,
            'detractors':         detractors,
            'open_complaints':    open_complaints,
            # Alerts (pharmacy drug stock only — clinical concern)
            'low_stock_count':    low_stock_count,
            # Live queue for quick view
            'live_queue': Visit.objects.select_related(
                'patient', 'department', 'attending_doctor'
            ).filter(
                visit_date__date=today,
                status__in=['WAITING', 'TRIAGE', 'IN_CONSULTATION'],
                is_deleted=False,
            ).order_by('visit_date')[:15],
        })
        return render(request, 'dashboard/medical_director.html', ctx)

    # ── Doctors (all specialist types) ───────────────────────────────────
    if user.is_doctor:
        # Build the patient queue for this doctor's department/unit
        # Include all active visit statuses including specialist-routed ones
        queue_qs = Visit.objects.select_related(
            'patient', 'department'
        ).filter(
            visit_date__date=today,
            status__in=[
                'WAITING', 'TRIAGE', 'IN_CONSULTATION',
                'REFRACTION', 'RETINA', 'GLAUCOMA', 'CATARACT',
                'NEURO', 'OCULOPLASTY', 'CORNEA', 'PEDIATRIC',
                'INVESTIGATION', 'PARAMETERS', 'UVEITIS',
            ],
        ).order_by('visit_date')

        # Filter queue by department:
        # - Specialists and Medical Director (who has a dept) → their dept only
        # - General ophthalmologist with no dept → sees all unassigned + general
        if user.department:
            if user.is_specialist or user.is_medical_director:
                queue_qs = queue_qs.filter(department=user.department)
            else:
                queue_qs = queue_qs.filter(
                    Q(department=user.department) | Q(department__isnull=True)
                )

        # Annotate each queued visit with AI triage priority
        queue_list = list(queue_qs)
        for v in queue_list:
            v.ai_priority, v.ai_priority_reason = _compute_ai_triage(v)
        # Sort: EMERGENCY first, then URGENT, then ROUTINE
        _order = {'EMERGENCY': 0, 'URGENT': 1, 'ROUTINE': 2}
        queue_list.sort(key=lambda v: _order.get(v.ai_priority, 3))

        ctx.update({
            'patient_queue': queue_list,
            'queue_count': len(queue_list),
            'my_consultations_today': Consultation.objects.filter(
                consulting_doctor=user,
                consultation_date__date=today,
                is_deleted=False,
            ).count(),
            'my_pending': Consultation.objects.select_related(
                'patient', 'department'
            ).filter(
                consulting_doctor=user,
                status='IN_PROGRESS',
                is_deleted=False,
            ).order_by('-consultation_date')[:8],
            'my_today_appointments': Appointment.objects.select_related(
                'patient'
            ).filter(
                doctor=user,
                appointment_date=today,
            ).order_by('appointment_time'),
        })
        return render(request, 'dashboard/doctor.html', ctx)

    # ── OPD Nurse (triage + dispatch) ─────────────────────────────────────
    if user.is_opd_nurse:
        # Patients at the parameters/triage station (waiting to have vitals recorded)
        waiting = Visit.objects.select_related(
            'patient', 'department'
        ).filter(
            visit_date__date=today,
            status='PARAMETERS',
        ).order_by('visit_date')

        # Patients dispatched to doctor (post-triage, waiting for consultation)
        dispatched_today = Visit.objects.select_related(
            'patient', 'department'
        ).filter(
            visit_date__date=today,
            status=VisitStatus.WAITING,
        ).count()

        ctx.update({
            'waiting': waiting,
            'waiting_count': waiting.count(),
            'dispatched_today': dispatched_today,
            'today_count': Visit.objects.filter(visit_date__date=today).count(),
        })
        return render(request, 'dashboard/nurse.html', ctx)

    # ── Counseling Nurse ─────────────────────────────────────────────────
    if user.is_counseling_nurse:
        from apps.qms.models import QueueToken, TokenStatus
        today = timezone.localdate()
        waiting = QueueToken.objects.filter(
            service_type='COUNSEL',
            status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
            issued_at__date=today,
            is_deleted=False,
        ).select_related('patient', 'visit').order_by('-priority', 'issued_at')
        ctx.update({'waiting': waiting, 'waiting_count': waiting.count()})
        return redirect('ipd:counseling_queue')

    # ── Ward Nurse (IPD) ─────────────────────────────────────────────────
    if user.is_ward_nurse:
        from apps.ipd.models import Admission
        admissions = Admission.objects.select_related(
            'patient', 'bed__ward'
        ).filter(
            status__in=['ADMITTED', 'POST_OP']
        ).order_by('-admission_date')[:20]
        ctx.update({'admissions': admissions, 'admissions_count': admissions.count()})
        return render(request, 'dashboard/ward_nurse.html', ctx)

    # ── Theatre Nurse ────────────────────────────────────────────────────
    if user.is_theatre_nurse:
        from apps.ipd.models import Admission, AdmissionStatus, WardType
        # Day-case / surgical patients admitted or post-op
        theatre_cases = Admission.objects.select_related(
            'patient', 'bed__ward', 'admitting_doctor'
        ).filter(
            status__in=[AdmissionStatus.ADMITTED, 'POST_OP'],
            bed__ward__ward_type=WardType.DAY_CASE,
            is_deleted=False,
        ).order_by('admission_date')

        # All patients admitted today (any ward) for surgical prep count
        today_admits = Admission.objects.filter(
            admission_date__date=today, is_deleted=False,
            status=AdmissionStatus.ADMITTED
        ).count()

        ctx.update({
            'theatre_cases': theatre_cases,
            'theatre_count': theatre_cases.count(),
            'today_admits': today_admits,
        })
        return render(request, 'dashboard/theatre_nurse.html', ctx)

    # ── Investigation Technician ─────────────────────────────────────────
    if user.is_investigation_tech:
        from apps.investigations.models import InvestigationOrder
        pending = InvestigationOrder.objects.select_related(
            'patient', 'investigation_type', 'consultation__department'
        ).filter(status__in=['ORDERED', 'IN_PROGRESS']).order_by('-created_at')
        ctx.update({
            'pending': pending,
            'pending_count': pending.count(),
        })
        return render(request, 'dashboard/investigation_tech.html', ctx)

    # ── Lab Technician ───────────────────────────────────────────────────
    if user.is_lab_tech:
        from apps.investigations.models import InvestigationOrder
        from apps.laboratory.models import LabOrder
        pending_inv = InvestigationOrder.objects.select_related(
            'patient', 'investigation_type'
        ).filter(status__in=['ORDERED', 'IN_PROGRESS']).order_by('-created_at')
        pending_lab = LabOrder.objects.select_related(
            'patient'
        ).filter(status__in=['ORDERED', 'SAMPLE_COLLECTED', 'PROCESSING']).order_by('-created_at')
        ctx.update({
            'pending_investigations': pending_inv,
            'pending_labs': pending_lab,
            'pending_inv_count': pending_inv.count(),
            'pending_lab_count': pending_lab.count(),
        })
        return render(request, 'dashboard/lab_technician.html', ctx)

    # ── Pharmacist ────────────────────────────────────────────────────────
    if user.is_pharmacist:
        from apps.prescriptions.models import DrugPrescription
        pending_rx = DrugPrescription.objects.select_related(
            'patient', 'consultation'
        ).filter(is_dispensed=False, is_deleted=False).order_by('-prescription_date')[:20]
        ctx.update({'pending_rx': pending_rx, 'pending_count': pending_rx.count()})
        return render(request, 'dashboard/pharmacist.html', ctx)

    # ── Optical Dispenser ─────────────────────────────────────────────────
    if user.is_optical_dispenser:
        from apps.prescriptions.models import OpticalPrescription
        pending_optical = OpticalPrescription.objects.select_related(
            'patient', 'consultation'
        ).order_by('-prescription_date')[:20]
        ctx.update({'pending_optical': pending_optical})
        return render(request, 'dashboard/optical_dispenser.html', ctx)

    # ── Cashier → go straight to their assigned counter ──────────────────
    if user.role == 'cashier':
        from apps.qms.models import ServiceCounter, QueueToken, TokenStatus
        from apps.billing.models import Invoice, InvoiceStatus, Payment

        counter = ServiceCounter.objects.filter(
            staff_assigned=user, is_active=True
        ).first()
        if counter:
            return redirect('qms:counter', counter_id=counter.id)

        # No counter assigned yet — show a minimal cashier workstation
        try:
            cashier_queue = list(QueueToken.objects.select_related('patient').filter(
                service_type='CASHIER',
                status=TokenStatus.WAITING,
                token_date=today,
                is_deleted=False,
            ).order_by('-priority', 'issued_at')[:20])
        except Exception:
            cashier_queue = []

        revenue_today = Payment.objects.filter(
            payment_date__date=today, is_deleted=False
        ).aggregate(total=Sum('amount'))['total'] or 0

        unpaid = Invoice.objects.select_related('patient').filter(
            status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
            is_deleted=False
        ).order_by('-created_at')[:15]

        ctx.update({
            'cashier_queue': cashier_queue,
            'revenue_today': revenue_today,
            'unpaid_invoices': unpaid,
            'unpaid_count': unpaid.count(),
        })
        return render(request, 'dashboard/cashier.html', ctx)

    # ── Billing Officer ────────────────────────────────────────────────────
    if user.is_billing_officer:
        from apps.billing.models import Invoice, InvoiceStatus
        unpaid = Invoice.objects.select_related(
            'patient'
        ).filter(
            status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
            is_deleted=False
        ).order_by('-created_at')[:20]
        ctx.update({'unpaid_invoices': unpaid, 'unpaid_count': unpaid.count()})
        return render(request, 'dashboard/billing.html', ctx)

    # ── Receptionist ──────────────────────────────────────────────────────
    if user.is_receptionist:
        from apps.qms.models import QueueToken, TokenStatus, ServiceType

        # Get patients waiting at RECEPTIONIST counter (new patient registrations)
        queue_patients = QueueToken.objects.filter(
            issued_at__date=today,
            service_type=ServiceType.RECEPTIONIST,
            status__in=[TokenStatus.WAITING, TokenStatus.CALLED],
            is_deleted=False
        ).select_related('patient').order_by('priority', 'issued_at')[:30]
        
        # Format queue data
        queue_data = []
        for idx, token in enumerate(queue_patients, 1):
            queue_data.append({
                'queue_number': token.token_number,
                'name': token.display_name,
                'patient_id': token.patient.patient_id if token.patient else 'N/A',
                'visit_type': token.get_service_tier_display(),
                'arrival_time': token.issued_at,
                'status': 'REGISTERED',
                'pk': token.pk,
            })
        
        ctx.update({
            'queue_patients': queue_data,
            'waiting_count': len(queue_data),
            'today_appointments': Appointment.objects.select_related(
                'patient', 'department', 'doctor'
            ).filter(appointment_date=today).order_by('appointment_time'),
            'checked_in_count': Appointment.objects.filter(
                appointment_date=today, status='CHECKED_IN'
            ).count(),
            'scheduled_count': Appointment.objects.filter(
                appointment_date=today,
                status__in=['SCHEDULED', 'CONFIRMED']
            ).count(),
        })
        return render(request, 'dashboard/receptionist.html', ctx)

    # ── Admission Officer ─────────────────────────────────────────────────
    if user.is_admission_officer:
        # Route directly to surgical booking queue (primary task)
        return redirect('ipd:surgical_booking_queue')

    # Fallback
    return render(request, 'dashboard/medical_director.html', ctx)
