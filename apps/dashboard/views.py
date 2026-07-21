from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db import models
from django.db.models import Count, Q, Sum, Avg
from django.core.cache import cache
from datetime import timedelta
import json
from apps.core.context_processors import qms_active as _qms_active


def _cached(key, builder_fn, timeout=60):
    """
    Cache helper for dashboard stats. Falls back to direct DB query if Redis
    is unavailable (connection refused, timeout, etc.) so dashboards never
    return 500 just because the cache server is down.
    """
    try:
        result = cache.get(key)
        if result is None:
            result = builder_fn()
            try:
                cache.set(key, result, timeout)
            except Exception:
                pass  # Cache write failure is non-fatal
    except Exception:
        # Redis is down or misconfigured — compute directly from DB
        result = builder_fn()
    return result


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

    # ── Cached patient / visit counts (refresh every 60s) ──────────────────
    # These are the most-hit queries. Cache key includes the date so stats
    # auto-reset at midnight without any manual invalidation.
    cache_date = today.strftime('%Y%m%d')

    total_patients = _cached(f'ceo_total_pts_{cache_date}',
        lambda: Patient.objects.filter(is_deleted=False).count(), 120)
    new_month = _cached(f'ceo_new_month_{cache_date}',
        lambda: Patient.objects.filter(created_at__date__gte=month_start, is_deleted=False).count(), 120)
    today_visits = _cached(f'ceo_today_visits_{cache_date}',
        lambda: Visit.objects.filter(visit_date__date=today, is_deleted=False).count(), 60)
    today_appts = _cached(f'ceo_today_appts_{cache_date}',
        lambda: Appointment.objects.filter(appointment_date=today, is_deleted=False).count(), 60)

    # ── Revenue (cached 2 min — financial data doesn't need to be instant) ─
    try:
        from apps.billing.models import Payment, Invoice, InvoiceStatus

        def _billing():
            r_today = Payment.objects.filter(payment_date__date=today, is_deleted=False).aggregate(t=Sum('amount'))['t'] or 0
            r_month = Payment.objects.filter(payment_date__date__gte=month_start, is_deleted=False).aggregate(t=Sum('amount'))['t'] or 0
            r_year  = Payment.objects.filter(payment_date__date__gte=year_start, is_deleted=False).aggregate(t=Sum('amount'))['t'] or 0
            out = sum(
                inv.balance_due for inv in
                Invoice.objects.filter(status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID], is_deleted=False)
                .prefetch_related('items', 'payments')
            )
            spark = []
            for i in range(6, -1, -1):
                d = today - timedelta(days=i)
                amt = Payment.objects.filter(payment_date__date=d, is_deleted=False).aggregate(t=Sum('amount'))['t'] or 0
                spark.append({'date': d.strftime('%d %b'), 'amount': float(amt)})
            return r_today, r_month, r_year, out, spark

        rev_today, rev_month, rev_year, outstanding, rev_7d = _cached(
            f'ceo_billing_{cache_date}', _billing, 120)
    except Exception:
        rev_today = rev_month = rev_year = outstanding = 0
        rev_7d = [{'date': '', 'amount': 0}]

    # ── Queue (cached 30s — queue changes fast) ─────────────────────────────
    try:
        if _qms_active():
            from apps.qms.models import QueueToken, TokenStatus
            def _queue():
                waiting = QueueToken.objects.filter(token_date=today, status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING], is_deleted=False).count()
                served  = QueueToken.objects.filter(token_date=today, status=TokenStatus.COMPLETED, is_deleted=False).count()
                return waiting, served
            queue_now, served_today = _cached(f'ceo_queue_{cache_date}', _queue, 30)
        else:
            queue_now = served_today = 0
    except Exception:
        queue_now = served_today = 0

    # ── Beds / IPD (cached 60s) ─────────────────────────────────────────────
    try:
        from apps.ipd.models import Bed, Admission, AdmissionStatus
        def _beds():
            t = Bed.objects.filter(is_deleted=False).count()
            o = Bed.objects.filter(status='OCCUPIED', is_deleted=False).count()
            occ = round((o / t * 100), 1) if t else 0
            adm = Admission.objects.filter(status=AdmissionStatus.ADMITTED, is_deleted=False).count()
            return t, o, occ, adm
        total_beds, occupied_beds, bed_occupancy, admissions = _cached(f'ceo_beds_{cache_date}', _beds, 60)
    except Exception:
        total_beds = occupied_beds = bed_occupancy = admissions = 0

    # ── Staff & NPS (cached 5 min — very slow-changing) ────────────────────
    from apps.accounts.models import User as StaffUser
    total_staff = _cached('ceo_total_staff', lambda: StaffUser.objects.filter(is_active=True).count(), 300)

    try:
        from apps.feedback.models import PatientFeedback
        def _nps():
            fb = PatientFeedback.objects.filter(nps_score__isnull=False, is_deleted=False)
            total_fb = fb.count()
            promo = fb.filter(nps_score__gte=9).count()
            detr  = fb.filter(nps_score__lte=6).count()
            n = round(((promo - detr) / total_fb) * 100) if total_fb else 0
            oc = PatientFeedback.objects.filter(status__in=['NEW', 'ACKNOWLEDGED', 'INVESTIGATING'], is_deleted=False).count()
            return n, oc
        nps, open_complaints = _cached(f'ceo_nps_{cache_date}', _nps, 300)
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
    today = timezone.localdate()
    ctx = {'today': today, 'user': user}

    from apps.patients.models import Patient, Visit, VisitStatus
    from apps.appointments.models import Appointment
    from apps.consultations.models import Consultation

    role = user.role

    # ── Gatekeeper → Gate Entry directly ─────────────────────────────────
    if user.is_gatekeeper:
        if _qms_active():
            return redirect('qms:gate_issue')
        return redirect('patients:list')

    # ── Super Admin → Dedicated IT Admin Panel ───────────────────────────
    if user.is_super_admin:
        return redirect('dashboard:sysadmin')

    # ── Finance Director → Billing Dashboard (operational home) ──────────
    if user.is_finance_director:
        return redirect('billing:dashboard')

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
        # Exclude phantom visits: REGISTERED with no triage nurse and empty vitals
        # (created by old bug when browsing a patient record; never actually processed)
        today_visits_qs = Visit.objects.filter(visit_date__date=today, is_deleted=False).exclude(
            status='REGISTERED', triage_nurse__isnull=True, vital_signs={}
        )
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
                'INVESTIGATION', 'UVEITIS',
                # 'PARAMETERS' excluded — triage patients not dispatched yet
            ],
        ).order_by('visit_date')

        # Filter queue strictly by department — every doctor sees ONLY patients
        # explicitly dispatched to their unit. No NULL-department fallback.
        dept_obj = user.department
        if not dept_obj and user.role_department_code:
            from apps.departments.models import Department as _Dept
            dept_obj = _Dept.objects.filter(code=user.role_department_code).first()
        if dept_obj:
            queue_qs = queue_qs.filter(department=dept_obj)
        else:
            queue_qs = queue_qs.none()

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
        _nurse_tier = getattr(user, 'patient_tier', 'ALL')
        _NURSE_TIER_COMPAT = {
            'VIP':        ['VIP'],
            'EXPRESS':    ['EXPRESS', 'FAST_TRACK'],
            'FAST_TRACK': ['EXPRESS', 'FAST_TRACK'],
            'STANDARD':   ['STANDARD'],
        }
        _waiting_qs = Visit.objects.select_related(
            'patient', 'department'
        ).filter(
            visit_date__date=today,
            status='PARAMETERS',
        ).order_by('visit_date')
        if _nurse_tier != 'ALL':
            _waiting_qs = _waiting_qs.filter(
                service_tier__in=_NURSE_TIER_COMPAT.get(_nurse_tier, [])
            )
        waiting = _waiting_qs

        # Patients dispatched to doctor (post-triage, waiting for consultation)
        dispatched_today = Visit.objects.select_related(
            'patient', 'department'
        ).filter(
            visit_date__date=today,
            status=VisitStatus.WAITING,
        ).count()

        # Full today's patient flow (all statuses) for the queue overview
        # Exclude phantom visits (REGISTERED, no triage nurse, empty vitals)
        all_today = Visit.objects.select_related(
            'patient', 'department', 'attending_doctor'
        ).filter(
            visit_date__date=today,
            is_deleted=False,
        ).exclude(
            status='REGISTERED', triage_nurse__isnull=True, vital_signs={}
        ).order_by('visit_date')

        completed_today = all_today.filter(status=VisitStatus.COMPLETED).count()

        ctx.update({
            'waiting': waiting,
            'waiting_count': waiting.count(),
            'dispatched_today': dispatched_today,
            'today_count': all_today.count(),
            'all_today': all_today,
            'completed_today': completed_today,
        })
        return render(request, 'dashboard/nurse.html', ctx)

    # ── Consultation Room Nurse ───────────────────────────────────────────
    if user.is_consultation_nurse:
        dept = user.department
        dept_code = dept.code if dept else None

        # Build dept → service_types map (same as consultation workstation)
        _DEPT_TO_SVC = {
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
        }

        waiting_tokens = []
        if _qms_active() and dept_code:
            try:
                from apps.qms.models import QueueToken, TokenStatus
                service_types = _DEPT_SVC = _DEPT_TO_SVC.get(dept_code, [])
                if service_types:
                    waiting_tokens = list(
                        QueueToken.objects.filter(
                            token_date=today,
                            service_type__in=service_types,
                            status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                            is_deleted=False,
                        ).select_related('patient', 'counter').order_by('-priority', 'issued_at')
                    )
            except Exception:
                pass

        # Attach today's active visit to each token
        if waiting_tokens:
            patient_ids = [t.patient_id for t in waiting_tokens if t.patient_id]
            active_visits = {
                v.patient_id: v
                for v in Visit.objects.filter(
                    patient_id__in=patient_ids,
                    visit_date__date=today,
                    is_deleted=False,
                ).exclude(status__in=[VisitStatus.COMPLETED, VisitStatus.DISCHARGED])
                .order_by('-visit_date')
            }
            for token in waiting_tokens:
                token.active_visit = active_visits.get(token.patient_id)

        from apps.consultations.models import Consultation, ConsultationStatus
        completed_today = Consultation.objects.filter(
            department=dept,
            consultation_date__date=today,
            status=ConsultationStatus.COMPLETED,
            is_deleted=False,
        ).count() if dept else 0

        waiting_count = sum(1 for t in waiting_tokens if t.status == 'WAITING')
        in_progress_count = sum(1 for t in waiting_tokens if t.status in ('CALLED', 'SERVING'))

        ctx.update({
            'waiting_tokens': waiting_tokens,
            'waiting_count': waiting_count,
            'in_progress_count': in_progress_count,
            'completed_today': completed_today,
            'dept': dept,
            'qms_on': _qms_active(),
        })
        return render(request, 'dashboard/consultation_nurse.html', ctx)

    # ── Counseling Nurse ─────────────────────────────────────────────────
    if user.is_counseling_nurse:
        return redirect('ipd:counseling_queue')

    # ── Ward Nurse (IPD) ─────────────────────────────────────────────────
    if user.is_ward_nurse:
        from apps.ipd.models import Admission
        admissions = Admission.objects.select_related(
            'patient', 'bed__ward'
        ).filter(
            status__in=['ADMITTED', 'POST_OP']
        ).order_by('-admission_date')[:20]
        postop_count = sum(1 for a in admissions if a.status == 'POST_OP')
        ctx.update({
            'admissions': admissions,
            'admissions_count': admissions.count(),
            'postop_count': postop_count,
        })
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

    # ── Lab Technician — blood/urine/micro only, no eye investigations ──
    if user.is_lab_tech:
        return redirect('laboratory:dashboard')

    # ── Pharmacist ────────────────────────────────────────────────────────
    if user.is_pharmacist:
        from apps.prescriptions.models import DrugPrescription
        from apps.patients.models import Visit
        from apps.pharmacy.models import Drug, DrugStock

        today = timezone.localdate()

        # Patients physically waiting at the pharmacy counter today
        waiting_visits = list(
            Visit.objects.filter(
                visit_date__date=today,
                status='PHARMACY',
                is_deleted=False,
            ).select_related('patient', 'attending_doctor').order_by('visit_date')
        )
        # Attach latest prescription to each visit
        if waiting_visits:
            patient_ids = [v.patient_id for v in waiting_visits]
            latest_rx_map = {
                rx.patient_id: rx
                for rx in DrugPrescription.objects.filter(
                    patient_id__in=patient_ids,
                    is_deleted=False,
                ).select_related('prescribed_by').prefetch_related('items')
                .order_by('-created_at')
            }
            for v in waiting_visits:
                v.latest_rx = latest_rx_map.get(v.patient_id)

        # All undispensed prescriptions (not just today) — pharmacist needs backlog too
        pending_rx = list(
            DrugPrescription.objects.select_related(
                'patient', 'prescribed_by',
            ).prefetch_related('items').filter(
                is_dispensed=False, is_deleted=False,
            ).order_by('-prescription_date')[:30]
        )

        # Stock alerts
        all_drugs = list(Drug.objects.filter(is_active=True, is_deleted=False))
        low_stock_count = sum(1 for d in all_drugs if d.needs_reorder)
        expiring_critical_count = DrugStock.objects.filter(
            is_deleted=False,
            expiry_date__gte=today,
            expiry_date__lte=today + timezone.timedelta(days=30),
            quantity_remaining__gt=0,
        ).count()

        # Patient name / ID quick search
        from apps.patients.models import Patient
        from django.db.models import Q as DQ
        search_q = request.GET.get('q', '').strip()
        search_results = []
        if search_q:
            matched_patients = list(
                Patient.objects.filter(
                    DQ(first_name__icontains=search_q) |
                    DQ(last_name__icontains=search_q) |
                    DQ(patient_id__icontains=search_q),
                    is_deleted=False,
                ).order_by('last_name', 'first_name')[:10]
            )
            if matched_patients:
                p_ids = [p.id for p in matched_patients]
                # Get latest prescription (including already dispensed) for context
                rx_map = {}
                for rx in DrugPrescription.objects.filter(
                    patient_id__in=p_ids,
                    is_deleted=False,
                ).select_related('prescribed_by').prefetch_related('items').order_by('-created_at'):
                    if rx.patient_id not in rx_map:
                        rx_map[rx.patient_id] = rx
                for p in matched_patients:
                    search_results.append({
                        'patient': p,
                        'latest_rx': rx_map.get(p.id),
                    })

        ctx.update({
            'waiting_visits': waiting_visits,
            'pending_rx': pending_rx,
            'pending_count': len(pending_rx),
            'low_stock_count': low_stock_count,
            'expiring_critical_count': expiring_critical_count,
            'today': today,
            'search_q': search_q,
            'search_results': search_results,
        })
        return render(request, 'dashboard/pharmacist.html', ctx)

    # ── Optical Dispenser ─────────────────────────────────────────────────
    if user.is_optical_dispenser:
        from apps.prescriptions.models import OpticalPrescription
        from apps.opticals.models import OpticalOrder, OpticalOrderStatus
        from apps.patients.models import Visit

        today = timezone.localdate()

        pending_optical = list(OpticalPrescription.objects.select_related(
            'patient', 'prescribed_by'
        ).filter(is_dispensed=False, is_deleted=False).order_by('-prescription_date')[:30])

        # Waiting patients at optical today
        waiting_visits = list(
            Visit.objects.filter(
                visit_date__date=today,
                status='OPTICAL',
                is_deleted=False,
            ).select_related('patient', 'attending_doctor').order_by('visit_date')
        )
        # Attach latest optical prescription to each waiting visit
        for v in waiting_visits:
            v.latest_rx = OpticalPrescription.objects.filter(
                patient=v.patient, is_deleted=False
            ).order_by('-prescription_date').first()

        ready_orders = list(OpticalOrder.objects.filter(
            status=OpticalOrderStatus.READY, is_deleted=False
        ).select_related('patient', 'frame').order_by('-ordered_date'))

        lab_orders = list(OpticalOrder.objects.filter(
            status=OpticalOrderStatus.LAB_PROCESSING, is_deleted=False
        ).select_related('patient', 'lens').order_by('-ordered_date'))

        new_orders_count = OpticalOrder.objects.filter(
            status=OpticalOrderStatus.ORDERED, is_deleted=False
        ).count()

        ctx.update({
            'pending_optical': pending_optical,
            'waiting_visits': waiting_visits,
            'ready_orders': ready_orders,
            'lab_orders': lab_orders,
            'new_orders_count': new_orders_count,
            'lab_orders_count': len(lab_orders),
        })
        return render(request, 'dashboard/optical_dispenser.html', ctx)

    # ── Cashier → cashier workstation dashboard ───────────────────────────
    if user.role == 'cashier':
        from apps.billing.models import Invoice, InvoiceStatus, Payment

        # First-time login: redirect to desk selection if no station chosen yet
        from apps.accounts.models import CashierStation
        _station_val = getattr(user, 'cashier_station', None)
        if not _station_val:
            return redirect('dashboard:cashier_select_desk')

        if _qms_active():
            from apps.qms.models import ServiceCounter, QueueToken, TokenStatus
            counter = ServiceCounter.objects.filter(
                staff_assigned=user, is_active=True
            ).first()

        # No counter assigned or QMS disabled — show cashier workstation filtered by station
        try:
            if _qms_active():
                from apps.qms.models import QueueToken, TokenStatus
                from apps.accounts.models import CashierStation
                station = getattr(user, 'cashier_station', CashierStation.ALL)
                _tier_map = {
                    CashierStation.STANDARD:   ['STANDARD'],
                    CashierStation.FAST_TRACK: ['EXPRESS', 'FAST_TRACK'],
                    CashierStation.VIP:        ['VIP'],
                }
                qs = QueueToken.objects.select_related('patient').filter(
                    service_type='CASHIER',
                    status=TokenStatus.WAITING,
                    token_date=today,
                    is_deleted=False,
                )
                if station in _tier_map:
                    qs = qs.filter(service_tier__in=_tier_map[station])
                elif station == CashierStation.INSURED:
                    qs = qs.filter(is_insured=True)
                cashier_queue = list(qs.order_by('-priority', 'issued_at')[:20])
            else:
                cashier_queue = []
        except Exception:
            cashier_queue = []

        # Without QMS: show visits with AT_CASHIER status filtered by cashier's station/tier
        from apps.patients.models import Visit
        from apps.accounts.models import CashierStation as _CS
        pending_payment_visits = []
        if not _qms_active():
            _pv_qs = Visit.objects.filter(
                visit_date__date=today,
                status='AT_CASHIER',
                is_deleted=False,
            ).select_related('patient').order_by('visit_date')
            _station = getattr(user, 'cashier_station', _CS.ALL)
            _tier_map_visits = {
                _CS.STANDARD:   ['STANDARD'],
                _CS.FAST_TRACK: ['EXPRESS', 'FAST_TRACK'],
                _CS.VIP:        ['VIP'],
            }
            if _station in _tier_map_visits:
                _pv_qs = _pv_qs.filter(service_tier__in=_tier_map_visits[_station])
            elif _station == _CS.INSURED:
                _pv_qs = _pv_qs.filter(billing_type__in=['HMO', 'INSURANCE'])
            # _CS.ALL → no filter, show everything
            pending_payment_visits = list(_pv_qs)

        # Only this cashier's own collections today — 0 if no shift open yet
        revenue_today = Payment.objects.filter(
            received_by=user,
            payment_date__date=today,
            is_deleted=False,
        ).aggregate(total=Sum('amount'))['total'] or 0

        # Only invoices THIS cashier issued — own tracking + audit trail
        _unpaid_qs = Invoice.objects.select_related('patient').filter(
            created_by=user,
            status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
            is_deleted=False
        ).order_by('-created_at')
        unpaid_count = _unpaid_qs.count()
        unpaid = list(_unpaid_qs[:20])

        _invoices_today_qs = Invoice.objects.filter(
            created_by=user,
            issue_date=today,
            is_deleted=False,
        ).select_related('patient').order_by('-created_at')
        invoices_today = _invoices_today_qs.count()
        invoices_today_list = list(_invoices_today_qs)

        # My shift today — shows cashier their own running balance
        from apps.billing.models import CashierShift
        my_shift = CashierShift.objects.filter(
            cashier=user, shift_date=today, is_deleted=False
        ).first()

        ctx.update({
            'cashier_queue': cashier_queue,
            'pending_payment_visits': pending_payment_visits,
            'revenue_today': my_shift.total_collected if my_shift else revenue_today,
            'my_shift': my_shift,
            'unpaid_invoices': unpaid,
            'unpaid_count': unpaid_count,
            'invoices_today': invoices_today,
            'invoices_today_list': invoices_today_list,
            'cashier_station_label': user.get_cashier_station_display() if hasattr(user, 'get_cashier_station_display') else 'All',
        })
        return render(request, 'dashboard/cashier.html', ctx)

    # ── Chief Cashier ──────────────────────────────────────────────────────
    if user.role == 'chief_cashier':
        from apps.billing.models import Invoice, InvoiceStatus, CashierShift, ShiftStatus, Payment
        unpaid = Invoice.objects.select_related('patient').filter(
            status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
            is_deleted=False
        ).order_by('-created_at')[:20]
        today_shifts = CashierShift.objects.filter(
            shift_date=today, is_deleted=False
        ).select_related('cashier').order_by('cashier__first_name')
        today_total = sum(float(s.total_collected) for s in today_shifts)
        submitted_shifts = [s for s in today_shifts if s.status == ShiftStatus.SUBMITTED]
        stale_open_shifts = CashierShift.objects.filter(
            shift_date__lt=today, status=ShiftStatus.OPEN, is_deleted=False
        ).select_related('cashier').order_by('shift_date', 'cashier__first_name')
        revenue_today = Payment.objects.filter(
            payment_date__date=today, is_deleted=False
        ).aggregate(total=Sum('amount'))['total'] or 0
        ctx.update({
            'unpaid_invoices': unpaid,
            'unpaid_count': unpaid.count(),
            'today_shifts': today_shifts,
            'today_total': today_total,
            'submitted_shifts': submitted_shifts,
            'stale_open_shifts': stale_open_shifts,
            'revenue_today': revenue_today,
        })
        return render(request, 'dashboard/chief_cashier.html', ctx)

    # ── Accountant / Senior Accountant ────────────────────────────────────
    if user.role in ('accountant', 'senior_accountant'):
        from apps.billing.models import Invoice, InvoiceStatus, Payment
        unpaid = Invoice.objects.select_related('patient').filter(
            status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
            is_deleted=False
        ).order_by('-created_at')[:20]
        revenue_today = Payment.objects.filter(
            payment_date__date=today, is_deleted=False
        ).aggregate(total=Sum('amount'))['total'] or 0
        revenue_month = Payment.objects.filter(
            payment_date__date__gte=today.replace(day=1), is_deleted=False
        ).aggregate(total=Sum('amount'))['total'] or 0
        ctx.update({
            'unpaid_invoices': unpaid,
            'unpaid_count': unpaid.count(),
            'revenue_today': revenue_today,
            'revenue_month': revenue_month,
        })
        return render(request, 'dashboard/accountant.html', ctx)

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
        # Get patients waiting at RECEPTIONIST counter (new patient registrations)
        queue_data = []
        if _qms_active():
            try:
                from apps.qms.models import QueueToken, TokenStatus, ServiceType
                queue_patients = QueueToken.objects.filter(
                    token_date=today,
                    service_type=ServiceType.RECEPTIONIST,
                    status__in=[TokenStatus.WAITING, TokenStatus.CALLED],
                    is_deleted=False
                ).select_related('patient').order_by('priority', 'issued_at')[:30]
                for token in queue_patients:
                    queue_data.append({
                        'queue_number': token.display_token_number,
                        'name': token.display_name,
                        'patient_id': token.patient.patient_id if token.patient else '—',
                        'visit_type': token.get_service_tier_display(),
                        'arrival_time': token.issued_at,
                        'status': token.status,   # WAITING / CALLED / SERVING
                        'pk': token.pk,
                    })
            except Exception:
                pass
        
        from apps.patients.models import PreRegistration
        pre_regs = PreRegistration.objects.filter(
            status__in=[PreRegistration.Status.PENDING, PreRegistration.Status.ARRIVED]
        ).order_by('-created_at')[:20]

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
            'registered_today': Patient.objects.filter(
                created_at__date=today, is_active=True
            ).count(),
            'pre_registrations': pre_regs,
        })
        return render(request, 'dashboard/receptionist.html', ctx)

    # ── Admission Officer ─────────────────────────────────────────────────
    if user.is_admission_officer:
        # Route directly to surgical booking queue (primary task)
        return redirect('ipd:surgical_booking_queue')

    # ── System Administrator ──────────────────────────────────────────────
    if user.role == 'admin':
        return redirect('accounts:staff_hub')

    # ── Medical Records Officer ───────────────────────────────────────────
    if user.role == 'medical_records':
        try:
            from apps.patients.models import Patient
            from apps.appointments.models import Appointment
            today = timezone.now().date()
            ctx = {
                'today_registrations': _cached(
                    'mro_reg_today',
                    lambda: Patient.objects.filter(is_deleted=False, registration_date=today).count()
                ),
                'today_appointments': _cached(
                    'mro_appt_today',
                    lambda: Appointment.objects.filter(appointment_date=today).count()
                ),
                'total_patients': _cached(
                    'mro_total_patients',
                    lambda: Patient.objects.filter(is_deleted=False).count()
                ),
                'recent_registrations': Patient.objects.filter(
                    is_deleted=False
                ).order_by('-created_at')[:10],
            }
        except Exception:
            ctx = {}
        return render(request, 'dashboard/medical_records.html', ctx)

    # ── Nurse Director → IPD Nursing Overview ────────────────────────────
    if user.is_nurse_director:
        from apps.ipd.models import Admission
        try:
            admissions = Admission.objects.select_related(
                'patient', 'bed__ward'
            ).filter(
                status__in=['ADMITTED', 'POST_OP']
            ).order_by('-admission_date')[:20]
            postop_count = sum(1 for a in admissions if a.status == 'POST_OP')
            ctx.update({
                'admissions': admissions,
                'admissions_count': admissions.count(),
                'postop_count': postop_count,
            })
        except Exception:
            ctx.update({'admissions': [], 'admissions_count': 0, 'postop_count': 0})
        return render(request, 'dashboard/ward_nurse.html', ctx)

    # ── Quality Officer → Leadership Reports Dashboard ────────────────────
    if user.is_quality_officer:
        return redirect('leadership:dashboard')

    # ── CSSD Technician → CSSD module directly ───────────────────────────
    if user.is_cssd_technician:
        return redirect('cssd:dashboard')

    # ── Anaesthetist — reuses theatre dashboard (same workspace) ─────────
    if user.role == 'anaesthetist':
        try:
            from apps.ipd.models import Admission, AdmissionStatus, WardType
            theatre_cases = Admission.objects.select_related(
                'patient', 'bed__ward', 'admitting_doctor'
            ).filter(
                status__in=[AdmissionStatus.ADMITTED, 'POST_OP'],
                bed__ward__ward_type=WardType.DAY_CASE,
                is_deleted=False,
            ).order_by('admission_date')
            today_admits = Admission.objects.filter(
                admission_date__date=today, is_deleted=False,
                status=AdmissionStatus.ADMITTED,
            ).count()
        except Exception:
            theatre_cases = []
            today_admits = 0
        ctx.update({
            'theatre_cases': theatre_cases,
            'theatre_count': len(list(theatre_cases)) if not hasattr(theatre_cases, 'count') else theatre_cases.count(),
            'today_admits': today_admits,
        })
        return render(request, 'dashboard/theatre_nurse.html', ctx)

    # Fallback
    return render(request, 'dashboard/medical_director.html', ctx)


# ── Cashier: self-select their desk/tier ──────────────────────────────────────

@login_required
def cashier_select_desk(request):
    """
    Cashier chooses their own workstation tier (Standard / VIP / Express / All).
    POST: {'station': 'STANDARD'|'FAST_TRACK'|'VIP'|'INSURED'|'ALL'}
    GET:  renders the desk selection page.
    """
    from django.http import JsonResponse
    from django.views.decorators.http import require_http_methods
    from apps.accounts.models import CashierStation

    if request.user.role not in ('cashier', 'chief_cashier') and not request.user.is_super_admin:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    if request.method == 'POST':
        from django.contrib import messages
        station = request.POST.get('station', '').strip().upper()
        valid = [c for c, _ in CashierStation.choices]
        if station not in valid:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest('Invalid station.')
        request.user.cashier_station = station
        request.user.save(update_fields=['cashier_station'])
        messages.success(request, f'Desk set to: {dict(CashierStation.choices).get(station, station)}')
        return redirect('dashboard:home')

    # GET — show selection UI
    from apps.accounts.models import CashierStation
    if _qms_active():
        from apps.qms.models import ServiceCounter
        counters = list(ServiceCounter.objects.filter(
            service_type='CASHIER', is_active=True
        ).order_by('name'))
    else:
        counters = []
    return render(request, 'dashboard/cashier_select_desk.html', {
        'stations': CashierStation.choices,
        'current_station': getattr(request.user, 'cashier_station', 'ALL'),
        'counters': counters,
    })


# ── Super Admin Panel ─────────────────────────────────────────────────────────

@login_required
def sysadmin_view(request):
    """
    Super Admin IT panel.
    User management, backup history, module config, active sessions, AI status.
    """
    if not request.user.is_super_admin:
        return redirect('dashboard:home')

    from apps.accounts.models import User, UserRole
    from apps.core.models import BackupLog
    from django.contrib.sessions.models import Session

    today = timezone.localdate()

    # User stats
    all_users = User.objects.all().order_by('role', 'first_name')
    active_users = all_users.filter(is_active=True)
    locked_users = all_users.filter(is_active=False)

    # Role breakdown
    role_counts = {}
    for role_val, role_label in UserRole.choices:
        cnt = all_users.filter(role=role_val, is_active=True).count()
        if cnt:
            role_counts[role_label] = cnt

    # Backup history
    backups = BackupLog.objects.all()[:20]
    last_backup = BackupLog.objects.filter(status=BackupLog.Status.SUCCESS).first()

    # Active sessions (rough count)
    from django.utils import timezone as tz
    active_sessions_count = Session.objects.filter(expire_date__gte=tz.now()).count()

    # Module config
    try:
        from apps.accounts.models import HospitalConfig
        config = HospitalConfig.get()
    except Exception:
        config = None

    # AI engine status
    from django.conf import settings as djsettings
    engine = getattr(djsettings, 'AI_ENGINE_REASONING', 'groq')
    ollama_status = None
    if engine == 'ollama':
        try:
            from apps.ai_assistant.ollama_client import ollama_health_check
            ollama_status = ollama_health_check()
        except Exception as e:
            ollama_status = {'online': False, 'error': str(e), 'models': []}

    ctx = {
        'all_users': all_users,
        'active_count': active_users.count(),
        'locked_count': locked_users.count(),
        'total_users': all_users.count(),
        'role_counts': role_counts,
        'backups': backups,
        'last_backup': last_backup,
        'active_sessions': active_sessions_count,
        'config': config,
        'ai_engine': engine,
        'ollama_status': ollama_status,
        'today': today,
        'all_roles': UserRole.choices,
    }
    return render(request, 'dashboard/super_admin.html', ctx)


@login_required
def sysadmin_trigger_backup(request):
    """Trigger a manual backup via Celery task."""
    if not request.user.is_super_admin:
        return redirect('dashboard:home')
    if request.method == 'POST':
        from apps.core.tasks import daily_backup_task
        from apps.core.models import BackupLog
        # Trigger async
        daily_backup_task.delay()
        from django.contrib import messages
        messages.success(request, 'Backup started in background. Check the backup log in a moment.')
    return redirect('dashboard:sysadmin')


@login_required
def health_check_view(request):
    """
    System health check page for IT staff.
    Shows CPU, RAM, disk, DB size, last backup, Redis, Celery, active sessions.
    """
    if not request.user.is_super_admin and request.user.role != 'admin':
        return redirect('dashboard:home')

    import shutil
    import platform

    # ── Disk ─────────────────────────────────────────────────────────────
    try:
        disk = shutil.disk_usage('/')
        disk_total_gb = round(disk.total / (1024 ** 3), 1)
        disk_used_gb  = round(disk.used  / (1024 ** 3), 1)
        disk_free_gb  = round(disk.free  / (1024 ** 3), 1)
        disk_pct      = round(disk.used / disk.total * 100, 1)
    except Exception:
        disk_total_gb = disk_used_gb = disk_free_gb = disk_pct = 0

    # ── CPU & RAM (psutil optional) ───────────────────────────────────────
    try:
        import psutil
        cpu_pct  = psutil.cpu_percent(interval=0.5)
        ram      = psutil.virtual_memory()
        ram_total_gb = round(ram.total  / (1024 ** 3), 1)
        ram_used_gb  = round(ram.used   / (1024 ** 3), 1)
        ram_pct      = ram.percent
        psutil_ok    = True
    except ImportError:
        cpu_pct = ram_pct = ram_total_gb = ram_used_gb = 0
        psutil_ok = False

    # ── Database size ─────────────────────────────────────────────────────
    db_size_mb = None
    db_name = ''
    try:
        from django.db import connection
        db_name = connection.settings_dict.get('NAME', '')
        if 'postgresql' in connection.settings_dict.get('ENGINE', ''):
            with connection.cursor() as cur:
                cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
                db_size_mb = cur.fetchone()[0]
    except Exception:
        pass

    # ── Redis ping ────────────────────────────────────────────────────────
    redis_ok = False
    try:
        from django.core.cache import cache
        cache.set('__health_ping__', 1, 5)
        redis_ok = cache.get('__health_ping__') == 1
    except Exception:
        pass

    # ── Last backup ───────────────────────────────────────────────────────
    from apps.core.models import BackupLog
    last_backup = BackupLog.objects.filter(status=BackupLog.Status.SUCCESS).first()
    recent_backups = BackupLog.objects.all()[:5]

    # ── Active sessions ───────────────────────────────────────────────────
    from django.contrib.sessions.models import Session
    from django.utils import timezone as tz
    active_sessions = Session.objects.filter(expire_date__gte=tz.now()).count()

    # ── Celery — check if any worker is alive via ping ────────────────────
    celery_ok = False
    try:
        from ehr_project.celery import app as celery_app
        ping = celery_app.control.ping(timeout=1.5)
        celery_ok = bool(ping)
    except Exception:
        pass

    # ── NIC / Network stats ───────────────────────────────────────────────
    nic_stats = []
    try:
        import psutil as _ps
        _net_io   = _ps.net_io_counters(pernic=True)
        _addrs    = _ps.net_if_addrs()
        for _nic, _c in _net_io.items():
            if _nic == 'lo':
                continue
            _ip = next((a.address for a in _addrs.get(_nic, []) if a.family == 2), '')
            nic_stats.append({
                'name': _nic, 'ip': _ip,
                'rx_mb': round(_c.bytes_recv / (1024 ** 2), 1),
                'tx_mb': round(_c.bytes_sent / (1024 ** 2), 1),
                'rx_errors': _c.errin, 'tx_errors': _c.errout,
            })
    except Exception:
        try:
            with open('/proc/net/dev') as _f:
                for _line in _f.readlines()[2:]:
                    _p = _line.split()
                    _n = _p[0].rstrip(':')
                    if _n == 'lo':
                        continue
                    nic_stats.append({
                        'name': _n, 'ip': '',
                        'rx_mb': round(int(_p[1]) / (1024 ** 2), 1),
                        'tx_mb': round(int(_p[9]) / (1024 ** 2), 1),
                        'rx_errors': int(_p[3]), 'tx_errors': int(_p[11]),
                    })
        except Exception:
            pass

    # ── Uptime & load average ─────────────────────────────────────────────
    uptime_str = 'N/A'
    load_avg   = (0, 0, 0)
    try:
        import time as _time
        import psutil as _ps
        _secs = _time.time() - _ps.boot_time()
        uptime_str = f"{int(_secs//86400)}d {int((_secs%86400)//3600)}h {int((_secs%3600)//60)}m"
    except Exception:
        try:
            with open('/proc/uptime') as _f:
                _secs = float(_f.read().split()[0])
            uptime_str = f"{int(_secs//86400)}d {int((_secs%86400)//3600)}h {int((_secs%3600)//60)}m"
        except Exception:
            pass
    try:
        import os as _os
        load_avg = tuple(round(x, 2) for x in _os.getloadavg())
    except Exception:
        pass

    # ── Process count & Gunicorn workers ──────────────────────────────────
    process_count   = 0
    gunicorn_workers = 0
    try:
        import psutil as _ps
        _procs = list(_ps.process_iter(['name']))
        process_count    = len(_procs)
        gunicorn_workers = sum(1 for p in _procs if 'gunicorn' in (p.info.get('name') or '').lower())
    except Exception:
        try:
            import subprocess as _sub
            _r = _sub.run(['pgrep', '-c', 'gunicorn'], capture_output=True, text=True)
            gunicorn_workers = int(_r.stdout.strip()) if _r.returncode == 0 else 0
        except Exception:
            pass

    # ── AI engine ─────────────────────────────────────────────────────────
    from django.conf import settings as djsettings
    ai_engine = getattr(djsettings, 'AI_ENGINE_REASONING', 'groq')
    groq_key = getattr(djsettings, 'GROQ_API_KEY', '')
    groq_configured = bool(groq_key and groq_key != 'your-groq-api-key-here')
    ollama_status = None
    if ai_engine == 'ollama':
        try:
            from apps.ai_assistant.ollama_client import ollama_health_check
            ollama_status = ollama_health_check()
        except Exception as e:
            ollama_status = {'online': False, 'error': str(e)}

    ctx = {
        # System
        'platform': platform.platform(),
        'python_version': platform.python_version(),
        # CPU/RAM
        'psutil_ok': psutil_ok,
        'cpu_pct': cpu_pct,
        'ram_pct': ram_pct,
        'ram_used_gb': ram_used_gb,
        'ram_total_gb': ram_total_gb,
        # Disk
        'disk_total_gb': disk_total_gb,
        'disk_used_gb': disk_used_gb,
        'disk_free_gb': disk_free_gb,
        'disk_pct': disk_pct,
        # Services
        'db_name': db_name,
        'db_size': db_size_mb,
        'redis_ok': redis_ok,
        'celery_ok': celery_ok,
        # Backup
        'last_backup': last_backup,
        'recent_backups': recent_backups,
        # Sessions
        'active_sessions': active_sessions,
        # AI
        'ai_engine': ai_engine,
        'groq_configured': groq_configured,
        'ollama_status': ollama_status,
        # NIC / Network
        'nic_stats': nic_stats,
        # Uptime & system
        'uptime_str': uptime_str,
        'load_avg': load_avg,
        'process_count': process_count,
        'gunicorn_workers': gunicorn_workers,
        'today': timezone.localdate(),
        'now': timezone.localtime(timezone.now()),
    }
    return render(request, 'dashboard/health_check.html', ctx)


# ── Sysadmin User Management ──────────────────────────────────────────────────

def _sysadmin_guard(user):
    return user.is_authenticated and user.is_super_admin


@login_required
def sysadmin_user_create(request):
    """Create a new staff account from the sysadmin panel."""
    if not _sysadmin_guard(request.user):
        return redirect('dashboard:home')

    from apps.accounts.forms import UserCreateForm
    from apps.departments.models import Department

    if request.method == 'POST':
        form = UserCreateForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            from django.contrib import messages
            messages.success(request, f'Account created for {user.get_full_name()}. They will be prompted to set a password on first login.')
            return redirect('dashboard:sysadmin')
    else:
        form = UserCreateForm(initial={'role': request.GET.get('role', '')})

    return render(request, 'sysadmin/user_form.html', {
        'form': form,
        'title': 'Create Staff Account',
        'departments': Department.objects.filter(is_active=True).order_by('name'),
    })


@login_required
def sysadmin_user_edit(request, pk):
    """Edit an existing staff account from the sysadmin panel."""
    if not _sysadmin_guard(request.user):
        return redirect('dashboard:home')

    from apps.accounts.models import User
    from apps.accounts.forms import UserEditForm
    from apps.departments.models import Department

    staff = get_object_or_404(User, pk=pk)

    if request.method == 'POST':
        form = UserEditForm(request.POST, request.FILES, instance=staff)
        if form.is_valid():
            form.save()
            from django.contrib import messages
            messages.success(request, f'{staff.get_full_name()} updated successfully.')
            return redirect('dashboard:sysadmin')
    else:
        form = UserEditForm(instance=staff)

    return render(request, 'sysadmin/user_form.html', {
        'form': form,
        'title': 'Edit Staff Account',
        'edit_user': staff,
        'departments': Department.objects.filter(is_active=True).order_by('name'),
    })


@login_required
def sysadmin_user_reset_password(request, pk):
    """Reset a staff member's password from the sysadmin panel."""
    if not _sysadmin_guard(request.user):
        return redirect('dashboard:home')

    from apps.accounts.models import User
    from django.contrib.auth.forms import SetPasswordForm

    staff = get_object_or_404(User, pk=pk)

    if request.method == 'POST':
        form = SetPasswordForm(staff, request.POST)
        if form.is_valid():
            form.save()
            staff.must_change_password = True
            staff.save(update_fields=['must_change_password'])
            from django.contrib import messages
            messages.success(request, f'Password reset for {staff.get_full_name()}. They must change it on next login.')
            return redirect('dashboard:sysadmin')
    else:
        form = SetPasswordForm(staff)

    return render(request, 'sysadmin/reset_password.html', {
        'form': form,
        'staff': staff,
    })


@login_required
def sysadmin_user_toggle(request, pk):
    """Lock or unlock a staff account."""
    if not _sysadmin_guard(request.user):
        return redirect('dashboard:home')
    if request.method != 'POST':
        return redirect('dashboard:sysadmin')

    from apps.accounts.models import User
    staff = get_object_or_404(User, pk=pk)
    if staff == request.user:
        from django.contrib import messages
        messages.error(request, 'You cannot lock your own account.')
        return redirect('dashboard:sysadmin')

    staff.is_active = not staff.is_active
    staff.save(update_fields=['is_active'])
    action = 'unlocked' if staff.is_active else 'locked'
    from django.contrib import messages
    messages.success(request, f'{staff.get_full_name()} has been {action}.')
    return redirect('dashboard:sysadmin')


# ── Sysadmin System Tools ─────────────────────────────────────────────────────

@login_required
def sysadmin_tools(request):
    """System tools: clear cache, flush expired sessions, module config."""
    if not _sysadmin_guard(request.user):
        return redirect('dashboard:home')

    from apps.accounts.models import HospitalConfig
    from django.conf import settings as djsettings
    from django.db import connection

    result_msg = None

    if request.method == 'POST':
        action = request.POST.get('action')
        from django.contrib import messages

        if action == 'clear_cache':
            from django.core.cache import cache
            cache.clear()
            messages.success(request, 'Cache cleared successfully.')

        elif action == 'flush_sessions':
            from django.contrib.sessions.models import Session
            from django.utils import timezone as tz
            deleted, _ = Session.objects.filter(expire_date__lt=tz.now()).delete()
            messages.success(request, f'{deleted} expired session(s) deleted.')

        elif action == 'save_modules':
            config = HospitalConfig.get()
            for field in config._meta.get_fields():
                if hasattr(field, 'get_internal_type') and field.get_internal_type() == 'BooleanField' and field.name.startswith('module_'):
                    setattr(config, field.name, request.POST.get(field.name) == 'on')
            config.save()
            messages.success(request, 'Module settings saved.')

        return redirect('dashboard:sysadmin_tools')

    # DB stats
    db_size = None
    db_engine = connection.settings_dict.get('ENGINE', '')
    if 'postgresql' in db_engine:
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT pg_size_pretty(pg_database_size(current_database())), pg_database_size(current_database())")
                row = cur.fetchone()
                db_size = row[0]
        except Exception:
            pass

    from django.contrib.sessions.models import Session
    from django.utils import timezone as tz
    expired_sessions = Session.objects.filter(expire_date__lt=tz.now()).count()
    active_sessions = Session.objects.filter(expire_date__gte=tz.now()).count()

    config = HospitalConfig.get()

    ctx = {
        'db_size': db_size,
        'db_engine': db_engine,
        'expired_sessions': expired_sessions,
        'active_sessions': active_sessions,
        'config': config,
        'module_flags': config.get_module_flags(),
        'today': timezone.localdate(),
    }
    return render(request, 'sysadmin/tools.html', ctx)


# ── Sysadmin Audit Log ────────────────────────────────────────────────────────

@login_required
def sysadmin_audit_log(request):
    """Paginated audit log viewer."""
    if not _sysadmin_guard(request.user):
        return redirect('dashboard:home')

    from apps.accounts.models import UserAuditLog, User
    from django.core.paginator import Paginator

    logs = UserAuditLog.objects.select_related('user').order_by('-timestamp')

    # Filters
    user_filter = request.GET.get('user', '')
    action_filter = request.GET.get('action', '')
    if user_filter:
        logs = logs.filter(user_id=user_filter)
    if action_filter:
        logs = logs.filter(action=action_filter)

    paginator = Paginator(logs, 50)
    page = paginator.get_page(request.GET.get('page', 1))

    ctx = {
        'page': page,
        'logs': page,
        'all_users': User.objects.filter(is_active=True).order_by('first_name'),
        'all_actions': UserAuditLog.Action.choices,
        'user_filter': user_filter,
        'action_filter': action_filter,
        'today': timezone.localdate(),
    }
    return render(request, 'sysadmin/audit_log.html', ctx)


# ── Leadership Audit Log ──────────────────────────────────────────────────────

_LEADERSHIP_AUDIT_ROLES = {
    'ceo', 'medical_director', 'finance_director',
    'admin_director', 'super_admin',
}

@login_required
def leadership_audit_log(request):
    """
    Full system audit trail accessible to CEO, Medical Director,
    Finance Director, Admin Director and Super Admin.
    Shows every significant action with filters by user, role, action type, and date.
    """
    if request.user.role not in _LEADERSHIP_AUDIT_ROLES:
        return redirect('dashboard:home')

    from apps.accounts.models import UserAuditLog, User
    from django.core.paginator import Paginator

    logs = UserAuditLog.objects.select_related('user').order_by('-timestamp')

    user_filter   = request.GET.get('user', '')
    action_filter = request.GET.get('action', '')
    role_filter   = request.GET.get('role', '')
    date_filter   = request.GET.get('date', '')

    if user_filter:
        logs = logs.filter(user_id=user_filter)
    if action_filter:
        logs = logs.filter(action=action_filter)
    if role_filter:
        logs = logs.filter(user__role=role_filter)
    if date_filter:
        logs = logs.filter(timestamp__date=date_filter)

    paginator = Paginator(logs, 50)
    page = paginator.get_page(request.GET.get('page', 1))

    # All active roles for the role filter dropdown
    from apps.accounts.models import UserRole
    all_roles = UserRole.choices

    return render(request, 'dashboard/audit_log.html', {
        'logs': page,
        'all_users': User.objects.filter(is_active=True).order_by('last_name'),
        'all_actions': UserAuditLog.Action.choices,
        'all_roles': all_roles,
        'user_filter': user_filter,
        'action_filter': action_filter,
        'role_filter': role_filter,
        'date_filter': date_filter,
        'today': timezone.localdate(),
        'total_count': logs.count(),
    })


# ── Recycle Bin (Super Admin only) ────────────────────────────────────────────

@login_required
def recycle_bin(request):
    """
    Show all soft-deleted records across key models.
    Super Admin can restore (un-delete) or permanently hard-delete them.
    Financial records (Invoice, Payment, Refund) are excluded — they are never
    permanently deleted; voids/cancellations create an audit trail instead.
    """
    if not _sysadmin_guard(request.user):
        return redirect('dashboard:home')

    from apps.patients.models import Patient
    from apps.consultations.models import Consultation
    from apps.appointments.models import Appointment
    from apps.accounts.models import User as StaffUser, UserAuditLog

    deleted_patients      = Patient.objects.filter(is_deleted=True).order_by('-updated_at')
    deleted_consultations = Consultation.objects.filter(is_deleted=True).order_by('-updated_at')
    deleted_appointments  = Appointment.objects.filter(is_deleted=True).order_by('-updated_at')
    deleted_staff         = StaffUser.objects.filter(is_active=False).order_by('-updated_at')

    return render(request, 'sysadmin/recycle_bin.html', {
        'deleted_patients':      deleted_patients,
        'deleted_consultations': deleted_consultations,
        'deleted_appointments':  deleted_appointments,
        'deleted_staff':         deleted_staff,
        'today': timezone.localdate(),
    })


@login_required
def recycle_bin_restore(request, model, pk):
    """Restore a single soft-deleted record."""
    if not _sysadmin_guard(request.user) or request.method != 'POST':
        return redirect('dashboard:recycle_bin')

    from apps.accounts.models import UserAuditLog
    obj = _get_recyclable(model, pk)
    if obj:
        obj.is_deleted = False
        obj.save(update_fields=['is_deleted'])
        UserAuditLog.log(
            user=request.user,
            action=UserAuditLog.Action.UPDATE_RECORD,
            target_model=model,
            target_id=str(pk),
            extra_data={'action': 'restored_from_recycle_bin'},
            request=request,
        )
        from django.contrib import messages
        messages.success(request, f'{model} record restored successfully.')
    return redirect('dashboard:recycle_bin')


@login_required
def recycle_bin_delete(request, model, pk):
    """Permanently hard-delete a soft-deleted record. Super Admin only."""
    if not _sysadmin_guard(request.user) or request.method != 'POST':
        return redirect('dashboard:recycle_bin')

    from apps.accounts.models import UserAuditLog
    from django.contrib import messages
    obj = _get_recyclable(model, pk)
    if obj:
        UserAuditLog.log(
            user=request.user,
            action=UserAuditLog.Action.DELETE_RECORD,
            target_model=model,
            target_id=str(pk),
            extra_data={'action': 'permanent_hard_delete', 'name': str(obj)},
            request=request,
        )
        obj.delete()
        messages.warning(request, f'{model} record permanently deleted.')
    return redirect('dashboard:recycle_bin')


def _get_recyclable(model, pk):
    """Helper: return the soft-deleted object for the given model name and pk."""
    _MAP = {}
    try:
        from apps.patients.models import Patient
        from apps.consultations.models import Consultation
        from apps.appointments.models import Appointment
        from apps.accounts.models import User as StaffUser
        _MAP = {
            'Patient':       Patient,
            'Consultation':  Consultation,
            'Appointment':   Appointment,
            'Staff':         StaffUser,
        }
    except Exception:
        return None

    model_cls = _MAP.get(model)
    if not model_cls:
        return None
    try:
        return model_cls.objects.get(pk=pk, is_deleted=True)
    except model_cls.DoesNotExist:
        return None


# ── System Settings (Super Admin) ─────────────────────────────────────────────

@login_required
def sysadmin_settings(request):
    """Custom system settings page — replaces Django admin for configuration."""
    if not _sysadmin_guard(request.user):
        return redirect('dashboard:home')

    from apps.accounts.models import HospitalConfig
    config = HospitalConfig.get()

    EDITABLE_FIELDS = [
        # (field_name, label, input_type, help)
        ('hospital_name',    'Hospital Name',        'text',   ''),
        ('hospital_address', 'Address',              'textarea',''),
        ('hospital_phone',   'Phone',                'text',   ''),
        ('hospital_email',   'Email',                'email',  ''),
        ('hospital_website', 'Website',              'url',    ''),
        ('hospital_tax_id',  'Tax ID / NIU',         'text',   'Numéro d\'Identification Unique'),
        ('consultation_days','Consultation Validity (days)','number','Days before patient must pay new consult fee'),
        ('session_timeout_hours',   'Session Timeout (hours)',   'number','How long before idle users are logged out'),
        ('max_failed_logins',       'Max Failed Login Attempts', 'number','Account locks after this many failures'),
        ('account_lockout_minutes', 'Account Lockout (minutes)', 'number','How long account stays locked'),
        ('backup_keep_days',        'Keep Backups (days)',       'number','Old backups beyond this age are deleted'),
    ]

    if request.method == 'POST':
        from django.contrib import messages
        action = request.POST.get('action', 'save_general')

        if action == 'save_general':
            for field, label, itype, _ in EDITABLE_FIELDS:
                val = request.POST.get(field, '').strip()
                if val != '':
                    field_obj = config._meta.get_field(field)
                    if field_obj.get_internal_type() in ('PositiveSmallIntegerField', 'IntegerField'):
                        try:
                            setattr(config, field, int(val))
                        except ValueError:
                            pass
                    else:
                        setattr(config, field, val)
                else:
                    setattr(config, field, val)
            config.save()
            messages.success(request, 'System settings saved.')

        elif action == 'save_modules':
            for f in config._meta.get_fields():
                if hasattr(f, 'get_internal_type') and f.get_internal_type() == 'BooleanField' and f.name.startswith('module_'):
                    setattr(config, f.name, f.name in request.POST)
            config.save()
            messages.success(request, 'Module settings saved.')

        elif action == 'save_appearance':
            config.system_theme    = request.POST.get('system_theme', config.system_theme)
            config.queue_board_type = request.POST.get('queue_board_type', config.queue_board_type)
            config.save()
            messages.success(request, 'Appearance settings saved.')

        elif action == 'seed_qms':
            try:
                from apps.qms.models import ServiceCounter, ServiceType
                counters = [
                    ('Cashier 1 (Standard)',     'CASH-01',  ServiceType.CASHIER,          'STANDARD'),
                    ('Cashier 2 (Standard)',     'CASH-02',  ServiceType.CASHIER,          'STANDARD'),
                    ('VIP Cashier',              'CASH-VIP', ServiceType.CASHIER,          'VIP'),
                    ('Express / FT Cashier',     'CASH-03',  ServiceType.CASHIER,          'FAST_TRACK,EXPRESS'),
                    ('Optical Cashier',          'CASH-OPT', ServiceType.CASHIER,          ''),
                    ('Receptionist 1',           'RECEP-01', ServiceType.RECEPTIONIST,     'STANDARD'),
                    ('Receptionist 2',           'RECEP-02', ServiceType.RECEPTIONIST,     'STANDARD'),
                    ('Parameters Standard',      'PARAM-01', ServiceType.PARAMETERS,       'STANDARD'),
                    ('Parameters VIP / Express', 'PVIP-01',  ServiceType.PARAMETERS_VIP,   'VIP,FAST_TRACK,EXPRESS'),
                    ('Insurance Consultation',   'INS-01',   ServiceType.INSURANCE_CONSULT,'EXPRESS,FAST_TRACK'),
                    ('VIP Consultation Room',    'VIP-CONS', ServiceType.VIP_CONSULT,      'VIP'),
                    ('Express Consultation',     'EXP-CONS', ServiceType.EXPRESS_CONSULT,  'FAST_TRACK,EXPRESS'),
                    ('General Ophthalmology',    'GEN-01',   ServiceType.GENERAL,          'STANDARD'),
                    ('Retina Clinic',            'RET-01',   ServiceType.RETINA,           ''),
                    ('Glaucoma Clinic',          'GLAUC-01', ServiceType.GLAUCOMA,         ''),
                    ('Cataract / Surgical',      'CAT-01',   ServiceType.CATARACT,         ''),
                    ('Pediatric Ophthalmology',  'PEDS-01',  ServiceType.PEDIATRIC,        ''),
                    ('Neuro-ophthalmology',      'NEURO-01', ServiceType.NEURO,            ''),
                    ('Oculoplastics',            'OCUP-01',  ServiceType.OCULOPLASTY,      ''),
                    ('Cornea Clinic',            'CORN-01',  ServiceType.CORNEA,           ''),
                    ('Uveitis Clinic',           'UVE-01',   ServiceType.UVEITIS,          ''),
                    ('Refraction / Optometry',   'REF-01',   ServiceType.REFRACTION,       ''),
                    ('Eye Investigations',       'INV-01',   ServiceType.INVESTIGATION,    ''),
                    ('Laboratory',               'LAB-01',   ServiceType.LABORATORY,       ''),
                    ('Pharmacy',                 'RX-01',    ServiceType.PHARMACY,         ''),
                    ('Optical Shop',             'OPT-01',   ServiceType.OPTICAL,          ''),
                    ('Surgical Counseling',      'COUNS-01', ServiceType.COUNSELING,       ''),
                    ('Billing',                  'BILL-01',  ServiceType.BILLING,          ''),
                ]
                count = 0
                for name, code, stype, tiers in counters:
                    _, created = ServiceCounter.objects.update_or_create(
                        code=code,
                        defaults={'name': name, 'service_type': stype, 'serves_tiers': tiers, 'is_active': True}
                    )
                    if created:
                        count += 1
                messages.success(request, f'QMS counters seeded — {count} new, {len(counters)-count} updated.')
            except Exception as e:
                messages.error(request, f'QMS seed failed: {e}')

        return redirect('dashboard:sysadmin_settings')

    from apps.accounts.models import SystemTheme, QueueBoardType
    return render(request, 'sysadmin/settings.html', {
        'config': config,
        'editable_fields': EDITABLE_FIELDS,
        'theme_choices': SystemTheme.choices,
        'board_choices': QueueBoardType.choices,
        'today': timezone.localdate(),
    })


# ── Export Views ──────────────────────────────────────────────────────────────

@login_required
def export_audit_log(request):
    """Export the full audit log as CSV."""
    from apps.accounts.models import UserAuditLog
    import csv
    from django.http import HttpResponse

    if not (request.user.is_super_admin or request.user.role in ('admin', 'ceo', 'medical_director', 'finance_director')):
        return redirect('dashboard:home')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="audit_log.csv"'
    writer = csv.writer(response)
    writer.writerow(['Timestamp', 'User', 'Role', 'Action', 'Patient', 'IP Address', 'Notes'])

    qs = UserAuditLog.objects.select_related('user', 'patient').order_by('-timestamp')
    date_from = request.GET.get('date_from')
    date_to   = request.GET.get('date_to')
    if date_from:
        qs = qs.filter(timestamp__date__gte=date_from)
    if date_to:
        qs = qs.filter(timestamp__date__lte=date_to)

    for log in qs[:10000]:
        writer.writerow([
            log.timestamp.strftime('%Y-%m-%d %H:%M'),
            log.user.get_full_name() if log.user else '',
            log.user.get_role_display() if log.user else '',
            log.get_action_display(),
            str(log.patient) if log.patient else '',
            log.ip_address or '',
            log.notes or '',
        ])
    return response


@login_required
def export_patient_list(request):
    """Export patient list as CSV."""
    from apps.patients.models import Patient
    import csv
    from django.http import HttpResponse

    if not (request.user.is_super_admin or request.user.role in ('admin', 'ceo', 'medical_director', 'medical_records')):
        return redirect('dashboard:home')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="patient_list.csv"'
    writer = csv.writer(response)
    writer.writerow(['Patient ID', 'Full Name', 'Date of Birth', 'Gender', 'Phone', 'Tier', 'Registered'])

    qs = Patient.objects.filter(is_deleted=False).order_by('-created_at')
    for p in qs:
        writer.writerow([
            p.patient_id,
            p.full_name,
            p.date_of_birth.strftime('%Y-%m-%d') if p.date_of_birth else '',
            p.get_gender_display() if hasattr(p, 'get_gender_display') else p.gender,
            str(p.phone_number) if p.phone_number else '',
            p.get_tier_display() if hasattr(p, 'get_tier_display') else p.tier,
            p.created_at.strftime('%Y-%m-%d') if p.created_at else '',
        ])
    return response
