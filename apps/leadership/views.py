"""
Leadership Dashboard — 360° Hospital Performance Overview
Financial performance, operational efficiency, clinical outcomes, resource allocation.
Designed for Medical Director and Senior Management.
"""
import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db import models
from django.db.models import Count, Avg, Q, Sum, F
from django.db.models.functions import TruncMonth
from calendar import monthrange
from django.utils import timezone
from datetime import timedelta, date
from django.core.cache import cache


def _require_director(request):
    """
    Leadership views are visible to:
    - Super Admin (master account, controls everything)
    - System Administrator (ADMIN role — IT/system admin)
    - Django superuser (Django is_superuser flag)
    - Medical Director (controls all clinical operations)
    - CEO (sees everything, read-only)
    - Finance Director (sees everything, focus on finance)
    - Admin Director (sees everything, read-only)
    """
    from apps.accounts.models import UserRole
    return (
        request.user.is_superuser
        or request.user.is_super_admin
        or request.user.role == UserRole.ADMIN
        or request.user.is_medical_director
        or request.user.is_ceo
        or request.user.is_finance_director
        or request.user.is_admin_director
    )


@login_required
def leadership_dashboard(request):
    if not _require_director(request):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    today = timezone.localdate()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    last_30 = today - timedelta(days=30)
    last_7 = today - timedelta(days=7)

    from apps.patients.models import Patient, Visit
    from apps.appointments.models import Appointment
    from apps.consultations.models import Consultation, ConsultationDiagnosis

    # ── Patient KPIs ─────────────────────────────────────────────────────────
    total_patients   = Patient.objects.filter(is_deleted=False).count()
    new_this_month   = Patient.objects.filter(created_at__date__gte=month_start, is_deleted=False).count()
    new_this_year    = Patient.objects.filter(created_at__date__gte=year_start, is_deleted=False).count()
    today_visits     = Visit.objects.filter(visit_date__date=today, is_deleted=False).count()
    today_consults   = Consultation.objects.filter(created_at__date=today, is_deleted=False).count()
    today_appts      = Appointment.objects.filter(appointment_date=today, is_deleted=False).count()

    # DNA / cancellation rate
    appt_last30 = Appointment.objects.filter(appointment_date__gte=last_30, is_deleted=False)
    appt_total  = appt_last30.count()
    appt_dna    = appt_last30.filter(status='NO_SHOW').count()
    appt_dna_pct = round((appt_dna / appt_total * 100), 1) if appt_total else 0
    appt_checked_in = appt_last30.filter(status='CHECKED_IN').count()
    appt_checkin_rate = round((appt_checked_in / appt_total * 100), 1) if appt_total else 0
    
    # Consultation rate
    consultation_rate = round((today_consults / today_visits * 100), 1) if today_visits else 0
    returning_patients = Patient.objects.filter(
        is_active=True, is_deleted=False, created_at__date__lt=last_30
    ).count()

    # ── Financial Performance ─────────────────────────────────────────────────
    try:
        from apps.billing.models import Invoice, Payment, InvoiceItem
        from apps.pharmacy.models import Dispensing

        # Revenue collected (payments received)
        revenue_today = Payment.objects.filter(
            payment_date__date=today, is_deleted=False
        ).aggregate(total=Sum('amount'))['total'] or 0

        revenue_month = Payment.objects.filter(
            payment_date__date__gte=month_start, is_deleted=False
        ).aggregate(total=Sum('amount'))['total'] or 0

        revenue_year = Payment.objects.filter(
            payment_date__date__gte=year_start, is_deleted=False
        ).aggregate(total=Sum('amount'))['total'] or 0

        # Outstanding (unpaid invoices)
        outstanding = InvoiceItem.objects.filter(
            invoice__status__in=['UNPAID', 'PARTIAL'],
            invoice__is_deleted=False,
        ).aggregate(
            total=Sum(F('unit_price') * F('quantity'))
        )['total'] or 0

        # Revenue by payment method (this month)
        revenue_by_method = list(
            Payment.objects.filter(
                payment_date__date__gte=month_start, is_deleted=False
            ).values('payment_method').annotate(total=Sum('amount')).order_by('-total')
        )

        # Revenue 7-day trend
        revenue_trend = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            amt = Payment.objects.filter(
                payment_date__date=d, is_deleted=False
            ).aggregate(total=Sum('amount'))['total'] or 0
            revenue_trend.append({'date': d.strftime('%d %b'), 'amount': float(amt)})

        # Pharmacy revenue (month)
        pharmacy_rev = Dispensing.objects.filter(
            dispensed_at__date__gte=month_start, is_deleted=False
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        dispensing_count = Dispensing.objects.filter(
            dispensed_at__date__gte=month_start, is_deleted=False
        ).count()

        # Collection rate (paid / total invoiced this month)
        total_invoiced_amt = InvoiceItem.objects.filter(
            invoice__issue_date__gte=month_start,
            invoice__is_deleted=False,
        ).aggregate(total=Sum(F('unit_price') * F('quantity')))['total'] or 1
        collection_rate = round((float(revenue_month) / float(total_invoiced_amt)) * 100, 1)

    except Exception:
        revenue_today = revenue_month = revenue_year = outstanding = 0
        pharmacy_rev = dispensing_count = collection_rate = 0
        revenue_by_method = []
        revenue_trend = [{'date': (today - timedelta(days=i)).strftime('%d %b'), 'amount': 0} for i in range(6, -1, -1)]

    # ── Operational Efficiency ─────────────────────────────────────────────────
    from apps.core.context_processors import qms_active as _qms_active
    try:
        if not _qms_active():
            raise ValueError('QMS off')
        from apps.qms.models import QueueToken, TokenStatus

        # Average wait time across all departments (last 7 days)
        avg_wait = QueueToken.objects.filter(
            token_date__gte=last_7,
            wait_time_minutes__isnull=False,
            is_deleted=False,
        ).aggregate(avg=Avg('wait_time_minutes'))['avg'] or 0

        # Average service time (consultation duration)
        avg_service = QueueToken.objects.filter(
            token_date__gte=last_7,
            service_time_minutes__isnull=False,
            is_deleted=False,
        ).aggregate(avg=Avg('service_time_minutes'))['avg'] or 0

        # Wait time per department (last 7 days)
        dept_wait = list(
            QueueToken.objects.filter(
                token_date__gte=last_7,
                wait_time_minutes__isnull=False,
                is_deleted=False,
            ).values('service_type').annotate(
                avg_wait=Avg('wait_time_minutes'),
                count=Count('id'),
            ).order_by('-avg_wait')[:8]
        )

        # Patients served today
        served_today = QueueToken.objects.filter(
            token_date=today,
            status=TokenStatus.COMPLETED,
            is_deleted=False,
        ).count()

        # Queue depth right now (waiting)
        queue_now = QueueToken.objects.filter(
            token_date=today,
            status=TokenStatus.WAITING,
            is_deleted=False,
        ).count()

    except Exception:
        avg_wait = avg_service = served_today = queue_now = 0
        dept_wait = []

    # ── Resource Allocation ───────────────────────────────────────────────────
    try:
        from apps.ipd.models import Admission, Bed, AdmissionStatus, BedStatus

        total_beds     = Bed.objects.filter(is_deleted=False).count()
        occupied_beds  = Bed.objects.filter(status='OCCUPIED', is_deleted=False).count()
        available_beds = total_beds - occupied_beds
        bed_occupancy  = round((occupied_beds / total_beds * 100), 1) if total_beds else 0
        current_admissions = Admission.objects.filter(
            status=AdmissionStatus.ADMITTED, is_deleted=False
        ).count()

        # Avg length of stay (last 30 days discharged)
        from apps.ipd.models import Admission
        discharged_recent = Admission.objects.filter(
            status=AdmissionStatus.DISCHARGED,
            discharge_date__date__gte=last_30,
            is_deleted=False,
        ).values('admission_date', 'discharge_date')
        los_days = []
        for a in discharged_recent:
            if a['discharge_date'] and a['admission_date']:
                delta = (a['discharge_date'].date() - a['admission_date'].date()).days
                if delta >= 0:
                    los_days.append(delta)
        avg_los = round(sum(los_days) / len(los_days), 1) if los_days else 0

    except Exception:
        total_beds = occupied_beds = available_beds = current_admissions = 0
        bed_occupancy = avg_los = 0

    # Active staff today
    try:
        from apps.hrms.models import AttendanceRecord
        staff_present_today = AttendanceRecord.objects.filter(
            date=today, clock_in__isnull=False
        ).count()
    except Exception:
        staff_present_today = 0

    from apps.accounts.models import User
    total_staff = User.objects.filter(is_active=True).count()

    # ── Clinical Quality ──────────────────────────────────────────────────────
    # Department consultation breakdown (last 30 days)
    dept_breakdown = list(
        Consultation.objects.filter(
            created_at__date__gte=last_30, is_deleted=False
        ).values('department__name').annotate(count=Count('id')).order_by('-count')[:10]
    )

    # Doctor throughput (consultations per doctor, last 30 days)
    doctor_stats = list(
        Consultation.objects.filter(
            created_at__date__gte=last_30, is_deleted=False
        ).values(
            'consulting_doctor__first_name',
            'consulting_doctor__last_name',
            'consulting_doctor__role',
        ).annotate(count=Count('id')).order_by('-count')[:10]
    )

    # Top diagnoses (last 30 days)
    top_diagnoses = list(
        ConsultationDiagnosis.objects.filter(
            consultation__created_at__date__gte=last_30,
            consultation__is_deleted=False,
        ).values('diagnosis__description').annotate(count=Count('id')).order_by('-count')[:10]
    )

    # Monthly new patient trend (last 6 months)
    monthly_trend = []
    for i in range(5, -1, -1):
        month_date = (today.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        next_month = (month_date.replace(day=28) + timedelta(days=4)).replace(day=1)
        count = Visit.objects.filter(
            visit_date__date__gte=month_date, visit_date__date__lt=next_month, is_deleted=False
        ).count()
        monthly_trend.append({'month': month_date.strftime('%b %Y'), 'count': count})

    # ── Month-over-Month Growth ───────────────────────────────────────────────
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    last_month_end   = month_start - timedelta(days=1)

    visits_this_month = Visit.objects.filter(
        visit_date__date__gte=month_start, visit_date__date__lte=today, is_deleted=False
    ).count()
    visits_last_month = Visit.objects.filter(
        visit_date__date__gte=last_month_start, visit_date__date__lte=last_month_end, is_deleted=False
    ).count()
    visit_growth = round(((visits_this_month - visits_last_month) / visits_last_month * 100), 1) if visits_last_month else 0

    patients_this_month = Patient.objects.filter(
        created_at__date__gte=month_start, is_deleted=False
    ).count()
    patients_last_month = Patient.objects.filter(
        created_at__date__gte=last_month_start, created_at__date__lte=last_month_end, is_deleted=False
    ).count()
    patient_growth = round(((patients_this_month - patients_last_month) / patients_last_month * 100), 1) if patients_last_month else 0

    try:
        from apps.billing.models import Payment as _Payment
        rev_last_month = _Payment.objects.filter(
            payment_date__date__gte=last_month_start,
            payment_date__date__lte=last_month_end,
            is_deleted=False,
        ).aggregate(total=Sum('amount'))['total'] or 0
        revenue_growth = round(((float(revenue_month) - float(rev_last_month)) / float(rev_last_month) * 100), 1) if rev_last_month else 0
    except Exception:
        rev_last_month = 0
        revenue_growth = 0

    # ── Patient Satisfaction ──────────────────────────────────────────────────
    try:
        from apps.feedback.models import PatientFeedback
        fb_qs = PatientFeedback.objects.filter(is_deleted=False)
        total_fb = fb_qs.filter(nps_score__isnull=False).count()
        promoters  = fb_qs.filter(nps_score__gte=9).count()
        detractors = fb_qs.filter(nps_score__lte=6).count()
        passives   = total_fb - promoters - detractors
        nps = round(((promoters - detractors) / total_fb) * 100) if total_fb else 0
        avg_satisfaction = fb_qs.filter(overall_rating__isnull=False).aggregate(
            avg=Avg('overall_rating')
        )['avg'] or 0

        # Open complaints
        open_complaints = fb_qs.filter(
            status__in=['NEW', 'ACKNOWLEDGED', 'INVESTIGATING']
        ).count()

        # NPS last 30 days
        nps_last30_total = fb_qs.filter(
            nps_score__isnull=False, created_at__date__gte=last_30
        ).count()
        nps_last30_promo = fb_qs.filter(nps_score__gte=9, created_at__date__gte=last_30).count()
        nps_last30_detra = fb_qs.filter(nps_score__lte=6, created_at__date__gte=last_30).count()
        nps_last30 = round(((nps_last30_promo - nps_last30_detra) / nps_last30_total) * 100) if nps_last30_total else 0
        
        # Positive feedback percentage
        positive_count = fb_qs.filter(overall_rating__gte=4, created_at__date__gte=last_30).count()
        total_fb_30 = fb_qs.filter(created_at__date__gte=last_30).count()
        feedback_positive = round((positive_count / total_fb_30 * 100), 1) if total_fb_30 else 0

    except Exception:
        nps = nps_last30 = 0
        avg_satisfaction = 0
        promoters = passives = detractors = 0
        open_complaints = 0
        positive_count = feedback_positive = 0

    context = {
        # Patient KPIs
        'total_patients': total_patients,
        'new_this_month': new_this_month,
        'new_this_year': new_this_year,
        'returning_patients': returning_patients,
        'today_visits': today_visits,
        'today_consultations': today_consults,
        'consultation_rate': consultation_rate,
        'today_appointments': today_appts,
        'appt_checkin_rate': appt_checkin_rate,
        'served_today': served_today,
        'queue_now': queue_now,
        # Financial
        'revenue_today': revenue_today,
        'revenue_month': revenue_month,
        'revenue_year': revenue_year,
        'outstanding': outstanding,
        'collection_rate': collection_rate,
        'pharmacy_rev': pharmacy_rev,
        'dispensing_count': dispensing_count,
        'revenue_by_method': revenue_by_method,
        'revenue_trend_json': json.dumps(revenue_trend),
        # Operational
        'avg_wait': round(float(avg_wait), 1),
        'avg_service': round(float(avg_service), 1),
        'dept_wait': dept_wait,
        'appt_dna_pct': appt_dna_pct,
        'appt_dna': appt_dna,
        'appt_total': appt_total,
        # Resource
        'total_beds': total_beds,
        'occupied_beds': occupied_beds,
        'available_beds': available_beds,
        'bed_occupancy': bed_occupancy,
        'bed_capacity': total_beds,
        'current_admissions': current_admissions,
        'avg_los': avg_los,
        'total_staff': total_staff,
        'staff_present_today': staff_present_today,
        # Clinical
        'dept_breakdown': dept_breakdown,
        'doctor_stats': doctor_stats,
        'top_diagnoses': top_diagnoses,
        'monthly_trend_json': json.dumps(monthly_trend),
        # Satisfaction
        'nps': nps,
        'nps_last30': nps_last30,
        'avg_satisfaction': round(float(avg_satisfaction), 1),
        'promoters': promoters,
        'passives': passives,
        'detractors': detractors,
        'open_complaints': open_complaints,
        'positive_count': positive_count,
        'feedback_positive': feedback_positive,
        'today': today,
        # Growth indicators
        'visit_growth': visit_growth,
        'visits_this_month': visits_this_month,
        'visits_last_month': visits_last_month,
        'patient_growth': patient_growth,
        'patients_this_month': patients_this_month,
        'patients_last_month': patients_last_month,
        'revenue_growth': revenue_growth,
        'rev_last_month': rev_last_month,
    }
    return render(request, 'leadership/dashboard.html', context)


@login_required
def kpi_json(request):
    """JSON endpoint — live KPI data for chart auto-refresh."""
    if not _require_director(request):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    from apps.patients.models import Visit
    from apps.core.context_processors import qms_active as _qms_active
    today = timezone.localdate()
    last_7 = [(today - timedelta(days=i)) for i in range(6, -1, -1)]

    visits_per_day, revenue_per_day, queue_per_day = [], [], []
    for d in last_7:
        visits_per_day.append({'date': d.isoformat(), 'visits': Visit.objects.filter(visit_date__date=d, is_deleted=False).count()})
        if _qms_active():
            from apps.qms.models import QueueToken, TokenStatus
            queue_per_day.append({'date': d.isoformat(), 'served': QueueToken.objects.filter(token_date=d, status=TokenStatus.COMPLETED, is_deleted=False).count()})
        else:
            queue_per_day.append({'date': d.isoformat(), 'served': 0})

    if _qms_active():
        from apps.qms.models import QueueToken, TokenStatus
        queue_now = QueueToken.objects.filter(token_date=today, status=TokenStatus.WAITING, is_deleted=False).count()
    else:
        queue_now = 0

    return JsonResponse({
        'visits_per_day': visits_per_day,
        'queue_per_day': queue_per_day,
        'queue_now': queue_now,
    })


@login_required
def monthly_stats(request):
    """
    End-of-month statistics report for Medical Director / CEO.
    All key metrics in one printable page.
    """
    if not _require_director(request):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    import json
    from datetime import timedelta

    today = timezone.localdate()

    # Month selector (default = current month)
    year  = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    _, last_day = monthrange(year, month)
    period_start = today.replace(year=year, month=month, day=1)
    period_end   = today.replace(year=year, month=month, day=last_day)

    # ── Cache check ───────────────────────────────────────────────────────────
    _cache_key = f'leadership_monthly_{year}_{month}'
    _cached = cache.get(_cache_key)
    if _cached:
        return render(request, 'leadership/monthly_stats.html', _cached)
    _cache_ttl = 600 if (year == today.year and month == today.month) else 86400

    from apps.patients.models import Patient, Visit
    from apps.consultations.models import Consultation
    from apps.appointments.models import Appointment
    from apps.laboratory.models import LabOrder, LabOrderItem, LabResult
    from apps.ipd.models import Admission, SurgicalBooking, AdmissionStatus, SurgicalBookingStatus

    # ── Patient counts ────────────────────────────────────────────────────────
    visits = Visit.objects.filter(
        visit_date__date__gte=period_start, visit_date__date__lte=period_end, is_deleted=False
    )
    new_patients = visits.filter(visit_type='NEW').count()
    returning    = visits.filter(visit_type__in=['FOLLOW_UP', 'REVIEW', 'PROCEDURE']).count()
    total_visits = visits.count()

    # explicit visit-type counts
    _vt = {d['visit_type']: d['count'] for d in visits.values('visit_type').annotate(count=Count('id'))}
    followup_visits   = _vt.get('FOLLOW_UP', 0)
    emergency_visits  = _vt.get('EMERGENCY', 0)
    review_visits     = _vt.get('REVIEW', 0)
    procedure_visits  = _vt.get('PROCEDURE', 0)

    # by tier
    tier_breakdown = list(
        visits.values('service_tier').annotate(count=Count('id')).order_by('-count')
    )
    _tier = {d['service_tier']: d['count'] for d in tier_breakdown}
    tier_standard  = _tier.get('STANDARD', 0)
    tier_express   = _tier.get('EXPRESS', 0)
    tier_fast      = _tier.get('FAST_TRACK', 0)
    tier_vip       = _tier.get('VIP', 0)

    # by billing type
    billing_breakdown = list(
        visits.values('billing_type').annotate(count=Count('id')).order_by('-count')
    )
    _bt = {d['billing_type']: d['count'] for d in billing_breakdown}
    bt_self_pay  = _bt.get('SELF_PAY', 0)
    bt_insurance = _bt.get('INSURANCE', 0)
    bt_hmo       = _bt.get('HMO', 0)
    bt_free      = _bt.get('FREE', 0)

    # ── Consultations ─────────────────────────────────────────────────────────
    consults = Consultation.objects.filter(
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
        is_deleted=False,
    )
    total_consults = consults.count()

    dept_consults = list(
        consults.values('department__name').annotate(count=Count('id')).order_by('-count')[:10]
    )

    doctor_consults = list(
        consults.values(
            'consulting_doctor__first_name',
            'consulting_doctor__last_name',
        ).annotate(count=Count('id')).order_by('-count')[:10]
    )

    # ── Surgeries ─────────────────────────────────────────────────────────────
    bookings = SurgicalBooking.objects.filter(
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
        is_deleted=False,
    )
    total_surgery_prescribed = bookings.count()
    total_surgery_paid = bookings.filter(
        deposit_paid__gte=F('deposit_required'), deposit_required__gt=0
    ).count()
    total_surgery_done = bookings.filter(status=SurgicalBookingStatus.COMPLETED).count()

    surgery_by_category = list(
        bookings.filter(surgery_category__gt='')
        .values('surgery_category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # ── Admissions / IPD ─────────────────────────────────────────────────────
    admissions = Admission.objects.filter(
        admission_date__date__gte=period_start,
        admission_date__date__lte=period_end,
        is_deleted=False,
    )
    total_admissions = admissions.count()
    discharged = admissions.filter(status=AdmissionStatus.DISCHARGED).count()

    # ── Laboratory ────────────────────────────────────────────────────────────
    lab_orders = LabOrder.objects.filter(
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
        is_deleted=False,
    )
    total_lab_orders = lab_orders.count()
    total_lab_tests  = LabOrderItem.objects.filter(
        order__in=lab_orders
    ).count()
    lab_by_category = list(
        LabOrderItem.objects.filter(order__in=lab_orders)
        .values('test_type__category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    abnormal_results = LabResult.objects.filter(
        is_abnormal=True, is_deleted=False,
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
    ).count()

    # ── Financial ─────────────────────────────────────────────────────────────
    try:
        from apps.billing.models import Payment, InvoiceItem
        revenue = Payment.objects.filter(
            payment_date__gte=period_start,
            payment_date__lte=period_end,
            is_deleted=False,
        ).aggregate(total=Sum('amount'))['total'] or 0

        outstanding = InvoiceItem.objects.filter(
            invoice__status__in=['UNPAID', 'PARTIAL'],
            invoice__is_deleted=False,
        ).aggregate(total=Sum(F('unit_price') * F('quantity')))['total'] or 0

        by_method = list(
            Payment.objects.filter(
                payment_date__gte=period_start,
                payment_date__lte=period_end,
                is_deleted=False,
            ).values('payment_method').annotate(total=Sum('amount')).order_by('-total')
        )
    except Exception:
        revenue = outstanding = 0
        by_method = []

    # ── Appointments ──────────────────────────────────────────────────────────
    appts = Appointment.objects.filter(
        appointment_date__gte=period_start,
        appointment_date__lte=period_end,
        is_deleted=False,
    )
    total_appts = appts.count()
    appt_dna    = appts.filter(status='NO_SHOW').count()

    # ── Patient Satisfaction ──────────────────────────────────────────────────
    try:
        from apps.feedback.models import PatientFeedback
        fb_qs = PatientFeedback.objects.filter(
            is_deleted=False,
            created_at__date__gte=period_start,
            created_at__date__lte=period_end,
        )
        fb_total = fb_qs.filter(nps_score__isnull=False).count()
        fb_promo = fb_qs.filter(nps_score__gte=9).count()
        fb_detra = fb_qs.filter(nps_score__lte=6).count()
        nps = round(((fb_promo - fb_detra) / fb_total) * 100) if fb_total else 0
        avg_rating = fb_qs.filter(overall_rating__isnull=False).aggregate(
            avg=Avg('overall_rating'))['avg'] or 0
    except Exception:
        nps = avg_rating = fb_promo = fb_detra = fb_total = 0

    # Build month list for selector
    months = []
    for m in range(1, 13):
        months.append({'value': m, 'label': today.replace(month=m, day=1).strftime('%B')})

    context = {
        'period_start': period_start,
        'period_end': period_end,
        'year': year, 'month': month,
        'months': months,
        'years': range(today.year - 2, today.year + 1),
        # Patients
        'total_visits': total_visits,
        'new_patients': new_patients,
        'returning': returning,
        'followup_visits': followup_visits,
        'emergency_visits': emergency_visits,
        'review_visits': review_visits,
        'procedure_visits': procedure_visits,
        'tier_breakdown': tier_breakdown,
        'tier_standard': tier_standard,
        'tier_express': tier_express,
        'tier_fast': tier_fast,
        'tier_vip': tier_vip,
        'billing_breakdown': billing_breakdown,
        'bt_self_pay': bt_self_pay,
        'bt_insurance': bt_insurance,
        'bt_hmo': bt_hmo,
        'bt_free': bt_free,
        # Consultations
        'total_consults': total_consults,
        'dept_consults': dept_consults,
        'doctor_consults': doctor_consults,
        # Surgeries
        'total_surgery_prescribed': total_surgery_prescribed,
        'total_surgery_paid': total_surgery_paid,
        'total_surgery_done': total_surgery_done,
        'surgery_by_category': surgery_by_category,
        # IPD
        'total_admissions': total_admissions,
        'discharged': discharged,
        # Lab
        'total_lab_orders': total_lab_orders,
        'total_lab_tests': total_lab_tests,
        'lab_by_category': lab_by_category,
        'abnormal_results': abnormal_results,
        # Financial
        'revenue': revenue,
        'outstanding': outstanding,
        'by_method': by_method,
        # Appointments
        'total_appts': total_appts,
        'appt_dna': appt_dna,
        # Satisfaction
        'nps': nps,
        'avg_rating': round(float(avg_rating), 1),
        'fb_promo': fb_promo,
        'fb_detra': fb_detra,
        'fb_total': fb_total,
    }
    cache.set(_cache_key, context, _cache_ttl)
    return render(request, 'leadership/monthly_stats.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# Retina / Vitreoretinal Outcomes Dashboard (CEO — Head of Retina)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def retina_dashboard(request):
    """
    Retina-specific outcomes dashboard for the CEO (Head of Retinal Unit)
    and Medical Director. Tracks injections, visual outcomes, DR screening,
    and surgical results.
    """
    from apps.accounts.models import UserRole
    from django.db.models import Count, Q
    from django.utils import timezone
    from apps.consultations.models import Consultation
    from apps.patients.models import Patient

    # Access: CEO, Medical Director, Retina Specialist, Super Admin
    allowed = (UserRole.CEO, UserRole.MEDICAL_DIRECTOR, UserRole.RETINA_SPECIALIST)
    if request.user.role not in allowed and not request.user.is_super_admin:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    today = timezone.localdate()
    month_ago  = today - timezone.timedelta(days=30)
    year_ago   = today - timezone.timedelta(days=365)

    # Retina consultations (last 12 months)
    retina_consults = Consultation.objects.filter(
        is_deleted=False,
        department__name__icontains='retina',
        created_at__date__gte=year_ago,
    ).select_related('patient', 'consulting_doctor')

    total_retina = retina_consults.count()
    unique_retina_patients = retina_consults.values('patient').distinct().count()

    # Monthly retina consultations trend
    monthly_retina = (
        retina_consults
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(n=Count('id'))
        .order_by('month')
    )

    # Anti-VEGF injections (from surgical bookings with procedure = ANTI_VEGF)
    try:
        from apps.ipd.models import SurgicalBooking
        anti_vegf_total = SurgicalBooking.objects.filter(
            is_deleted=False,
            procedure='ANTI_VEGF',
            created_at__date__gte=year_ago,
        ).count()
        anti_vegf_month = SurgicalBooking.objects.filter(
            is_deleted=False,
            procedure='ANTI_VEGF',
            created_at__date__gte=month_ago,
        ).count()
        retinal_surgeries = SurgicalBooking.objects.filter(
            is_deleted=False,
            procedure__in=['VITRECTOMY', 'BUCKLE', 'ANTI_VEGF', 'LASER_RETINA'],
            created_at__date__gte=year_ago,
        ).values('procedure').annotate(n=Count('id')).order_by('-n')
    except Exception:
        anti_vegf_total = anti_vegf_month = 0
        retinal_surgeries = []

    # Diagnoses breakdown (from JSON stored diagnoses via primary_diagnosis text)
    # Since diagnoses are stored in consultation_diagnoses many-to-many, count common retinal Dx
    retinal_dx_keywords = {
        'Diabetic Retinopathy': Q(consultation_diagnoses__diagnosis__description__icontains='diabetic retinopathy'),
        'AMD': Q(consultation_diagnoses__diagnosis__description__icontains='macular degeneration'),
        'Retinal Detachment': Q(consultation_diagnoses__diagnosis__description__icontains='retinal detachment'),
        'CRVO/BRVO': Q(consultation_diagnoses__diagnosis__description__icontains='retinal vein occlusion'),
        'Macular Hole': Q(consultation_diagnoses__diagnosis__description__icontains='macular hole'),
        'Vitreomacular': Q(consultation_diagnoses__diagnosis__description__icontains='vitreomacular'),
        'Uveitis': Q(consultation_diagnoses__diagnosis__description__icontains='uveitis'),
    }
    dx_breakdown = {}
    for label, q in retinal_dx_keywords.items():
        dx_breakdown[label] = Consultation.objects.filter(
            is_deleted=False, department__name__icontains='retina',
            created_at__date__gte=year_ago,
        ).filter(q).distinct().count()

    # New patients vs returns
    new_retina = retina_consults.filter(visit__visit_type='NEW').count()
    return_retina = retina_consults.filter(visit__visit_type='FOLLOW_UP').count()

    context = {
        'today': today,
        'total_retina': total_retina,
        'unique_retina_patients': unique_retina_patients,
        'monthly_retina': list(monthly_retina),
        'anti_vegf_total': anti_vegf_total,
        'anti_vegf_month': anti_vegf_month,
        'retinal_surgeries': list(retinal_surgeries),
        'dx_breakdown': dx_breakdown,
        'new_retina': new_retina,
        'return_retina': return_retina,
    }
    return render(request, 'leadership/retina_dashboard.html', context)


# ── Finance Director Dashboard ────────────────────────────────────────────────

@login_required
def finance_dashboard(request):
    """
    Finance Director view — billing, revenue, collections, outstanding.
    Also accessible to CEO and Super Admin.
    """
    if not (request.user.is_finance_director or request.user.is_super_admin
            or request.user.is_ceo or request.user.is_admin_director
            or request.user.is_medical_director):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    today = timezone.localdate()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    last_30 = today - timedelta(days=30)
    last_7 = today - timedelta(days=7)

    from apps.billing.models import Invoice, InvoiceItem, Payment, InvoiceStatus, PaymentMethod

    # ── Revenue Totals ────────────────────────────────────────────────────────
    rev_today = Payment.objects.filter(
        payment_date__date=today, is_deleted=False
    ).aggregate(t=Sum('amount'))['t'] or 0

    rev_week = Payment.objects.filter(
        payment_date__date__gte=last_7, is_deleted=False
    ).aggregate(t=Sum('amount'))['t'] or 0

    rev_month = Payment.objects.filter(
        payment_date__date__gte=month_start, is_deleted=False
    ).aggregate(t=Sum('amount'))['t'] or 0

    rev_year = Payment.objects.filter(
        payment_date__date__gte=year_start, is_deleted=False
    ).aggregate(t=Sum('amount'))['t'] or 0

    # ── Outstanding ───────────────────────────────────────────────────────────
    open_invoices = Invoice.objects.filter(
        status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
        is_deleted=False
    ).select_related('patient').prefetch_related('items', 'payments').order_by('-created_at')

    outstanding_total = sum(inv.balance_due for inv in open_invoices)
    outstanding_count = open_invoices.count()

    # ── Invoice Counts ────────────────────────────────────────────────────────
    invoices_today = Invoice.objects.filter(created_at__date=today, is_deleted=False).count()
    invoices_month = Invoice.objects.filter(created_at__date__gte=month_start, is_deleted=False).count()
    paid_invoices = Invoice.objects.filter(status=InvoiceStatus.PAID, is_deleted=False).count()

    # ── Revenue by Payment Method ─────────────────────────────────────────────
    by_method = list(
        Payment.objects.filter(
            payment_date__date__gte=month_start, is_deleted=False
        ).values('payment_method').annotate(
            total=Sum('amount'), count=Count('id')
        ).order_by('-total')
    )

    # ── Revenue by Service Category ───────────────────────────────────────────
    by_category = list(
        InvoiceItem.objects.filter(
            invoice__created_at__date__gte=month_start,
            invoice__is_deleted=False,
            is_deleted=False,
        ).values('category').annotate(
            total=Sum(F('quantity') * F('unit_price'))
        ).order_by('-total')
    )

    # ── Daily Collections this month ──────────────────────────────────────────
    from django.db.models.functions import TruncDate
    daily_collections = list(
        Payment.objects.filter(
            payment_date__date__gte=month_start, is_deleted=False
        ).annotate(day=TruncDate('payment_date')).values('day').annotate(
            total=Sum('amount')
        ).order_by('day')
    )
    daily_labels = [str(d['day']) for d in daily_collections]
    daily_values = [float(d['total']) for d in daily_collections]

    # ── Monthly Revenue Trend (12 months) ─────────────────────────────────────
    twelve_months_ago = today - timedelta(days=365)
    monthly_trend = list(
        Payment.objects.filter(
            payment_date__date__gte=twelve_months_ago, is_deleted=False
        ).annotate(month=TruncMonth('payment_date')).values('month').annotate(
            total=Sum('amount')
        ).order_by('month')
    )
    monthly_labels = [d['month'].strftime('%b %Y') for d in monthly_trend]
    monthly_values = [float(d['total']) for d in monthly_trend]

    # ── Top 10 Outstanding Invoices ───────────────────────────────────────────
    top_outstanding = sorted(open_invoices, key=lambda i: i.balance_due, reverse=True)[:10]

    # ── Recent Payments ───────────────────────────────────────────────────────
    recent_payments = Payment.objects.filter(
        is_deleted=False
    ).select_related('invoice__patient').order_by('-payment_date')[:15]

    # ── Waiver / Discount Summary ─────────────────────────────────────────────
    waivers_month = Invoice.objects.filter(
        created_at__date__gte=month_start,
        discount_amount__gt=0, is_deleted=False
    ).aggregate(count=Count('id'), total=Sum('discount_amount'))
    waiver_count = waivers_month['count'] or 0
    waiver_total = waivers_month['total'] or 0

    context = {
        'today': today,
        'rev_today': rev_today,
        'rev_week': rev_week,
        'rev_month': rev_month,
        'rev_year': rev_year,
        'outstanding_total': outstanding_total,
        'outstanding_count': outstanding_count,
        'invoices_today': invoices_today,
        'invoices_month': invoices_month,
        'paid_invoices': paid_invoices,
        'by_method': by_method,
        'by_category': by_category,
        'daily_labels': json.dumps(daily_labels),
        'daily_values': json.dumps(daily_values),
        'monthly_labels': json.dumps(monthly_labels),
        'monthly_values': json.dumps(monthly_values),
        'top_outstanding': top_outstanding,
        'recent_payments': recent_payments,
        'waiver_count': waiver_count,
        'waiver_total': waiver_total,
    }
    return render(request, 'leadership/finance_dashboard.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# Comprehensive Hospital Statistics — segmented by department, tier, billing
# type, WHO age groups. WHO-standard monthly report modelled on lab stats.
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def hospital_stats_view(request):
    """
    Comprehensive segmented hospital statistics.
    Covers: consultations by specialty, visits by service tier/billing type,
    WHO age+gender groups, IPD admissions, theatre cases by procedure,
    optical shop, pharmacy dispensing, lab and investigation orders.
    """
    if not _require_director(request):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    import json, calendar as _cal

    today = timezone.localdate()

    # ── Month selector ────────────────────────────────────────────────────────
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
        month_start = today.replace(year=year, month=month, day=1)
    except (ValueError, TypeError):
        month_start = today.replace(day=1)
        year, month = month_start.year, month_start.month

    last_day  = _cal.monthrange(year, month)[1]
    month_end = today.replace(year=year, month=month, day=last_day)

    # ── Cache check ───────────────────────────────────────────────────────────
    _cache_key = f'hospital_stats_{year}_{month}'
    if request.GET.get('format') != 'pdf':
        _cached = cache.get(_cache_key)
        if _cached:
            return render(request, 'leadership/hospital_stats.html', _cached)
    _cache_ttl = 600 if (year == today.year and month == today.month) else 86400

    # Previous / next month navigation
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    # ── Model imports ─────────────────────────────────────────────────────────
    from apps.patients.models import Visit, Patient, VisitType
    from apps.consultations.models import Consultation

    # ── Base querysets ────────────────────────────────────────────────────────
    base_visits = Visit.objects.filter(
        is_deleted=False,
        visit_date__date__gte=month_start,
        visit_date__date__lte=month_end,
    )
    base_consults = Consultation.objects.filter(
        is_deleted=False,
        consultation_date__date__gte=month_start,
        consultation_date__date__lte=month_end,
    )

    # ── Top-level KPIs ────────────────────────────────────────────────────────
    total_visits   = base_visits.count()
    total_consults = base_consults.count()
    new_patients   = base_visits.filter(visit_type=VisitType.NEW).count()
    followup       = base_visits.filter(visit_type=VisitType.FOLLOW_UP).count()
    emergency      = base_visits.filter(visit_type=VisitType.EMERGENCY).count()

    # ── Consultations by department ───────────────────────────────────────────
    dept_consults_raw = (
        base_consults.values('department__name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    dept_labels  = [d['department__name'] or 'Unknown' for d in dept_consults_raw]
    dept_counts  = [d['count'] for d in dept_consults_raw]
    dept_consults_json = json.dumps({'labels': dept_labels, 'data': dept_counts})
    dept_consults_table = list(dept_consults_raw)

    # ── Visits by service tier ────────────────────────────────────────────────
    TIER_LABELS = {
        'STANDARD': 'Regular',
        'EXPRESS':  'Express',
        'FAST_TRACK': 'Fast Track',
        'VIP':      'VIP',
    }
    tier_raw = (
        base_visits.values('service_tier')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    tier_data    = {r['service_tier']: r['count'] for r in tier_raw}
    tier_labels  = [TIER_LABELS.get(k, k) for k in TIER_LABELS]
    tier_counts  = [tier_data.get(k, 0) for k in TIER_LABELS]
    tier_json    = json.dumps({'labels': tier_labels, 'data': tier_counts})

    # ── Visits by billing type ────────────────────────────────────────────────
    BT_LABELS = {
        'SELF_PAY':  'Cash / Card',
        'INSURANCE': 'Insurance',
        'HMO':       'HMO',
        'WAIVER':    'Waiver',
        'FREE':      'Free / Subsidised',
    }
    bt_raw    = base_visits.values('billing_type').annotate(count=Count('id')).order_by('-count')
    bt_data   = {r['billing_type']: r['count'] for r in bt_raw}
    bt_labels = [BT_LABELS.get(k, k) for k in BT_LABELS]
    bt_counts = [bt_data.get(k, 0) for k in BT_LABELS]
    bt_json   = json.dumps({'labels': bt_labels, 'data': bt_counts})

    # ── Daily visit volume (this month) ──────────────────────────────────────
    daily_raw = (
        base_visits.values('visit_date__date')
        .annotate(count=Count('id'))
        .order_by('visit_date__date')
    )
    daily_map   = {r['visit_date__date']: r['count'] for r in daily_raw}
    from datetime import timedelta as _td, date as _date
    daily_labels = []
    daily_counts = []
    d = month_start
    while d <= min(month_end, today):
        daily_labels.append(d.strftime('%d'))
        daily_counts.append(daily_map.get(d, 0))
        d += _td(days=1)
    daily_json = json.dumps({'labels': daily_labels, 'data': daily_counts})

    # ── WHO Age groups + gender ───────────────────────────────────────────────
    WHO_BANDS = [
        ('0–4',   0,  4),
        ('5–14',  5,  14),
        ('15–24', 15, 24),
        ('25–44', 25, 44),
        ('45–59', 45, 59),
        ('60+',   60, 999),
    ]
    dobs = list(
        base_visits.filter(patient__date_of_birth__isnull=False)
        .values_list('patient_id', 'patient__date_of_birth', 'patient__gender')
        .distinct()
    )
    age_male   = {b[0]: 0 for b in WHO_BANDS}
    age_female = {b[0]: 0 for b in WHO_BANDS}
    age_other  = {b[0]: 0 for b in WHO_BANDS}
    age_unknown = 0
    total_male = total_female = total_other = 0
    for _, dob, gender in dobs:
        if gender == 'M':
            total_male += 1
        elif gender == 'F':
            total_female += 1
        else:
            total_other += 1
        try:
            age = (today - dob).days // 365
            placed = False
            for label, lo, hi in WHO_BANDS:
                if lo <= age <= hi:
                    if gender == 'M':
                        age_male[label] += 1
                    elif gender == 'F':
                        age_female[label] += 1
                    else:
                        age_other[label] += 1
                    placed = True
                    break
            if not placed:
                age_unknown += 1
        except Exception:
            age_unknown += 1

    who_labels = [b[0] for b in WHO_BANDS]
    who_json   = json.dumps({
        'labels': who_labels,
        'male':   [age_male[b[0]] for b in WHO_BANDS],
        'female': [age_female[b[0]] for b in WHO_BANDS],
    })
    who_table = [
        {
            'band':   b[0],
            'male':   age_male[b[0]],
            'female': age_female[b[0]],
            'other':  age_other[b[0]],
            'total':  age_male[b[0]] + age_female[b[0]] + age_other[b[0]],
        }
        for b in WHO_BANDS
    ]

    # ── Tier × Gender × Age cross-tab ────────────────────────────────────────
    from collections import defaultdict as _dd
    _visit_detail = list(
        base_visits.filter(patient__date_of_birth__isnull=False)
        .values('service_tier', 'billing_type', 'patient__gender', 'patient__date_of_birth')
    )
    _mx_data = _dd(lambda: _dd(lambda: _dd(int)))
    for _v in _visit_detail:
        _dob     = _v['patient__date_of_birth']
        _gender  = _v['patient__gender'] or 'Other'
        _billing = _v['billing_type']
        _tk      = _billing if _billing in ('INSURANCE', 'HMO') else _v['service_tier']
        try:
            _age = (today - _dob).days // 365
            _ag  = 'Children' if _age < 18 else ('Adult' if _age < 60 else 'Elderly')
        except Exception:
            _ag = 'Unknown'
        _mx_data[_tk][_ag][_gender] += 1

    _TIER_ROWS = [
        ('STANDARD',   'Regular',   '#0d6efd'),
        ('EXPRESS',    'Express',   '#0dcaf0'),
        ('FAST_TRACK', 'Fast Track','#ffc107'),
        ('VIP',        'VIP',       '#dc3545'),
        ('INSURANCE',  'Insurance', '#198754'),
        ('HMO',        'HMO',       '#6f42c1'),
    ]

    def _mx(tk, ag, g):
        return _mx_data[tk][ag].get(g, 0)

    tier_matrix = []
    for _tk, _label, _color in _TIER_ROWS:
        _cm = _mx(_tk,'Children','M'); _cf = _mx(_tk,'Children','F')
        _am = _mx(_tk,'Adult','M');    _af = _mx(_tk,'Adult','F')
        _em = _mx(_tk,'Elderly','M');  _ef = _mx(_tk,'Elderly','F')
        _tm = _cm + _am + _em;        _tf = _cf + _af + _ef
        tier_matrix.append({
            'tier':      _label,
            'color':     _color,
            'total':     _tm + _tf,
            'male':      _tm,
            'female':    _tf,
            'children':  _cm + _cf, 'children_m': _cm, 'children_f': _cf,
            'adult':     _am + _af, 'adult_m':    _am, 'adult_f':    _af,
            'elderly':   _em + _ef, 'elderly_m':  _em, 'elderly_f':  _ef,
        })

    # ── IPD Admissions ────────────────────────────────────────────────────────
    try:
        from apps.ipd.models import Admission
        ipd_qs = Admission.objects.filter(
            is_deleted=False,
            admission_date__date__gte=month_start,
            admission_date__date__lte=month_end,
        )
        total_admissions = ipd_qs.count()
        discharged_qs = ipd_qs.filter(discharge_date__isnull=False)
        # Average LOS via Python (discharge_date - admission_date)
        los_list = []
        for adm in discharged_qs.values('admission_date', 'discharge_date'):
            try:
                los_list.append((adm['discharge_date'] - adm['admission_date']).days)
            except Exception:
                pass
        avg_los = round(sum(los_list) / len(los_list), 1) if los_list else 0
        discharged_count = discharged_qs.count()
    except Exception:
        total_admissions = discharged_count = 0
        avg_los = 0

    # ── Theatre / Surgical Cases ──────────────────────────────────────────────
    try:
        from apps.ipd.models import SurgicalBooking, SurgicalBookingStatus
        surg_qs = SurgicalBooking.objects.filter(
            is_deleted=False,
            surgery_date__date__gte=month_start,
            surgery_date__date__lte=month_end,
        )
        total_theatre = surg_qs.count()
        completed_theatre = surg_qs.filter(status=SurgicalBookingStatus.COMPLETED).count()
        surg_by_proc_raw = (
            surg_qs.values('procedure')
            .annotate(count=Count('id'))
            .order_by('-count')[:12]
        )
        # Get display names
        surg_choices = dict(SurgicalBooking._meta.get_field('procedure').flatchoices)
        surg_by_proc = [
            {
                'procedure': surg_choices.get(r['procedure'], r['procedure']),
                'count': r['count'],
            }
            for r in surg_by_proc_raw
        ]
        surg_labels = [s['procedure'] for s in surg_by_proc]
        surg_counts = [s['count'] for s in surg_by_proc]
        surg_json = json.dumps({'labels': surg_labels, 'data': surg_counts})
    except Exception:
        total_theatre = completed_theatre = 0
        surg_by_proc = []
        surg_json = json.dumps({'labels': [], 'data': []})

    # ── Optical Orders ────────────────────────────────────────────────────────
    try:
        from apps.opticals.models import OpticalOrder
        opt_qs = OpticalOrder.objects.filter(
            is_deleted=False,
            ordered_date__gte=month_start,
            ordered_date__lte=month_end,
        )
        total_optical = opt_qs.count()
        optical_delivered = opt_qs.filter(status='DELIVERED').count()
    except Exception:
        total_optical = optical_delivered = 0

    # ── Pharmacy Dispensing ───────────────────────────────────────────────────
    try:
        from apps.pharmacy.models import Dispensing
        from django.db.models import Sum as _Sum
        pharma_qs = Dispensing.objects.filter(
            is_deleted=False,
            dispensed_at__date__gte=month_start,
            dispensed_at__date__lte=month_end,
        )
        total_dispensing = pharma_qs.count()
        pharma_revenue = pharma_qs.aggregate(total=_Sum('amount_paid'))['total'] or 0
    except Exception:
        total_dispensing = 0
        pharma_revenue = 0

    # ── Laboratory ────────────────────────────────────────────────────────────
    try:
        from apps.laboratory.models import LabOrder, LabOrderItem, LabResult
        lab_qs = LabOrder.objects.filter(
            is_deleted=False,
            created_at__date__gte=month_start,
            created_at__date__lte=month_end,
        )
        total_lab_orders = lab_qs.count()
        total_lab_tests  = LabOrderItem.objects.filter(
            order__is_deleted=False,
            order__created_at__date__gte=month_start,
            order__created_at__date__lte=month_end,
        ).count()
        lab_abnormal = LabResult.objects.filter(
            is_deleted=False,
            is_abnormal=True,
            created_at__date__gte=month_start,
            created_at__date__lte=month_end,
        ).count()
    except Exception:
        total_lab_orders = total_lab_tests = lab_abnormal = 0

    # ── Visits by Region ──────────────────────────────────────────────────────
    region_raw = (
        base_visits
        .exclude(patient__region='')
        .values('patient__region')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    region_table = [
        {'region': r['patient__region'] or 'Unknown', 'count': r['count']}
        for r in region_raw
    ]
    region_labels = [r['region'] for r in region_table]
    region_counts = [r['count'] for r in region_table]
    region_json = json.dumps({'labels': region_labels, 'data': region_counts})

    # ── Eye Investigations ────────────────────────────────────────────────────
    try:
        from apps.investigations.models import InvestigationOrder, InvestigationCategory
        inv_qs = InvestigationOrder.objects.filter(
            is_deleted=False,
            created_at__date__gte=month_start,
            created_at__date__lte=month_end,
        )
        total_inv = inv_qs.count()
        inv_by_cat_raw = (
            inv_qs.values('investigation_type__category')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        cat_choices = dict(InvestigationCategory.choices)
        inv_by_cat = [
            {
                'category': cat_choices.get(r['investigation_type__category'], r['investigation_type__category'] or 'Unknown'),
                'count': r['count'],
            }
            for r in inv_by_cat_raw
        ]
        inv_labels = [i['category'] for i in inv_by_cat]
        inv_counts = [i['count'] for i in inv_by_cat]
        inv_json   = json.dumps({'labels': inv_labels, 'data': inv_counts})
    except Exception:
        total_inv = 0
        inv_by_cat = []
        inv_json   = json.dumps({'labels': [], 'data': []})

    # ── Context ───────────────────────────────────────────────────────────────
    months_list = [{'value': m, 'label': _date(year, m, 1).strftime('%B')} for m in range(1, 13)]

    ctx = {
        'month_start': month_start,
        'year': year, 'month': month,
        'months_list': months_list,
        'years': range(today.year - 2, today.year + 1),
        'prev_year': prev_year, 'prev_month': prev_month,
        'next_year': next_year, 'next_month': next_month,
        # KPIs
        'total_visits': total_visits,
        'total_consults': total_consults,
        'new_patients': new_patients,
        'followup': followup,
        'emergency': emergency,
        # Departments
        'dept_consults_json': dept_consults_json,
        'dept_consults_table': dept_consults_table,
        # Tiers
        'tier_json': tier_json,
        'tier_labels': json.dumps(tier_labels),
        'tier_standard': tier_data.get('STANDARD', 0),
        'tier_express': tier_data.get('EXPRESS', 0),
        'tier_fast': tier_data.get('FAST_TRACK', 0),
        'tier_vip': tier_data.get('VIP', 0),
        # Billing type
        'bt_json': bt_json,
        'bt_cash': bt_data.get('SELF_PAY', 0),
        'bt_insurance': bt_data.get('INSURANCE', 0),
        'bt_hmo': bt_data.get('HMO', 0),
        'bt_waiver': bt_data.get('WAIVER', 0),
        'bt_free': bt_data.get('FREE', 0),
        # Daily volume
        'daily_json': daily_json,
        # WHO
        'who_json': who_json,
        'who_table': who_table,
        'total_male': total_male,
        'total_female': total_female,
        'total_other': total_other,
        'age_unknown': age_unknown,
        # IPD
        'total_admissions': total_admissions,
        'discharged_count': discharged_count,
        'avg_los': avg_los,
        # Theatre
        'total_theatre': total_theatre,
        'completed_theatre': completed_theatre,
        'surg_by_proc': surg_by_proc,
        'surg_json': surg_json,
        # Optical
        'total_optical': total_optical,
        'optical_delivered': optical_delivered,
        # Pharmacy
        'total_dispensing': total_dispensing,
        'pharma_revenue': pharma_revenue,
        # Lab
        'total_lab_orders': total_lab_orders,
        'total_lab_tests': total_lab_tests,
        'lab_abnormal': lab_abnormal,
        # Investigations
        'total_inv': total_inv,
        'inv_by_cat': inv_by_cat,
        'inv_json': inv_json,
        # Tier × Gender × Age cross-tab
        'tier_matrix': tier_matrix,
        # Visits by region
        'region_table': region_table,
        'region_json': region_json,
    }
    ctx['pdf_filename'] = f'Hospital-Stats-{month_start.strftime("%b-%Y")}.pdf'
    ctx['orientation'] = request.GET.get('orientation', 'portrait')

    if request.GET.get('format') == 'pdf':
        # Extract chart images posted from the browser (canvas.toDataURL captures)
        chart_images = {}
        for key, val in request.POST.items():
            if key.startswith('chart_') and val.startswith('data:image'):
                chart_images[key[6:]] = val  # strip 'chart_' prefix
        ctx['chart_images'] = chart_images
        from apps.reports.views import render_pdf
        return render_pdf('leadership/pdf/hospital_stats_pdf.html', ctx)

    cache.set(_cache_key, ctx, _cache_ttl)
    return render(request, 'leadership/hospital_stats.html', ctx)


# ── Department Stats (visible to all clinical staff for their own dept) ───────
@login_required
def department_stats_view(request):
    """
    Segmented stats for the requesting user's department.
    Shows tier × gender × age breakdown for consultations in this department.
    """
    import json, calendar as _cal
    from collections import defaultdict as _dd
    from apps.consultations.models import Consultation
    from apps.patients.models import Visit

    today = timezone.localdate()

    # Month selector
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
        month_start = today.replace(year=year, month=month, day=1)
    except (ValueError, TypeError):
        month_start = today.replace(day=1)
        year, month = today.year, today.month

    last_day  = _cal.monthrange(year, month)[1]
    month_end = today.replace(year=year, month=month, day=last_day)

    if month == 1:  prev_year, prev_month = year - 1, 12
    else:           prev_year, prev_month = year, month - 1
    if month == 12: next_year, next_month = year + 1, 1
    else:           next_year, next_month = year, month + 1

    # Determine the user's department
    user = request.user
    dept_code = getattr(user, 'role_department_code', None)
    dept_name = dept_code or 'Your Department'

    # Consultations for this department
    dept_qs = Consultation.objects.filter(
        is_deleted=False,
        consultation_date__date__gte=month_start,
        consultation_date__date__lte=month_end,
    )
    if dept_code:
        dept_qs = dept_qs.filter(department__code=dept_code)

    total_consults = dept_qs.count()

    # Tier × Gender × Age cross-tab via visits
    visit_ids = dept_qs.values_list('visit_id', flat=True)
    detail = list(
        Visit.objects.filter(
            id__in=visit_ids,
            is_deleted=False,
            patient__date_of_birth__isnull=False,
        ).values('service_tier', 'billing_type', 'patient__gender', 'patient__date_of_birth')
    )

    mx = _dd(lambda: _dd(lambda: _dd(int)))
    for v in detail:
        dob     = v['patient__date_of_birth']
        gender  = v['patient__gender'] or 'Other'
        billing = v['billing_type']
        tk      = billing if billing in ('INSURANCE', 'HMO') else v['service_tier']
        try:
            age = (today - dob).days // 365
            ag  = 'Children' if age < 18 else ('Adult' if age < 60 else 'Elderly')
        except Exception:
            ag = 'Unknown'
        mx[tk][ag][gender] += 1

    TIER_ROWS = [
        ('STANDARD',   'Regular',   '#0d6efd'),
        ('EXPRESS',    'Express',   '#0dcaf0'),
        ('FAST_TRACK', 'Fast Track','#ffc107'),
        ('VIP',        'VIP',       '#dc3545'),
        ('INSURANCE',  'Insurance', '#198754'),
        ('HMO',        'HMO',       '#6f42c1'),
    ]

    def _m(tk, ag, g): return mx[tk][ag].get(g, 0)

    tier_matrix = []
    for tk, label, color in TIER_ROWS:
        cm = _m(tk,'Children','M'); cf = _m(tk,'Children','F')
        am = _m(tk,'Adult','M');    af = _m(tk,'Adult','F')
        em = _m(tk,'Elderly','M');  ef = _m(tk,'Elderly','F')
        tm = cm + am + em;          tf = cf + af + ef
        if tm + tf == 0:
            continue  # skip empty tiers
        tier_matrix.append({
            'tier': label, 'color': color,
            'total': tm + tf, 'male': tm, 'female': tf,
            'children': cm+cf, 'children_m': cm, 'children_f': cf,
            'adult':    am+af, 'adult_m':    am, 'adult_f':    af,
            'elderly':  em+ef, 'elderly_m':  em, 'elderly_f':  ef,
        })

    # Daily volume chart
    from datetime import timedelta as _td
    daily_raw = (
        dept_qs.values('consultation_date__date')
        .annotate(count=Count('id'))
        .order_by('consultation_date__date')
    )
    daily_map = {r['consultation_date__date']: r['count'] for r in daily_raw}
    daily_labels, daily_counts = [], []
    d = month_start
    while d <= min(month_end, today):
        daily_labels.append(d.strftime('%d'))
        daily_counts.append(daily_map.get(d, 0))
        d += _td(days=1)
    daily_json = json.dumps({'labels': daily_labels, 'data': daily_counts})

    # Gender totals
    total_male = sum(mx[tk]['Children']['M'] + mx[tk]['Adult']['M'] + mx[tk]['Elderly']['M'] for tk, *_ in TIER_ROWS)
    total_female = sum(mx[tk]['Children']['F'] + mx[tk]['Adult']['F'] + mx[tk]['Elderly']['F'] for tk, *_ in TIER_ROWS)
    total_children = sum(mx[tk]['Children']['M'] + mx[tk]['Children']['F'] for tk, *_ in TIER_ROWS)
    total_adult    = sum(mx[tk]['Adult']['M']    + mx[tk]['Adult']['F']    for tk, *_ in TIER_ROWS)
    total_elderly  = sum(mx[tk]['Elderly']['M']  + mx[tk]['Elderly']['F']  for tk, *_ in TIER_ROWS)

    ctx = {
        'dept_name': dept_name,
        'dept_code': dept_code,
        'month_start': month_start,
        'year': year, 'month': month,
        'months_list': [{'value': m, 'label': today.replace(year=year, month=m, day=1).strftime('%B')} for m in range(1, 13)],
        'years': range(today.year - 2, today.year + 1),
        'prev_year': prev_year, 'prev_month': prev_month,
        'next_year': next_year, 'next_month': next_month,
        'total_consults': total_consults,
        'total_male': total_male,
        'total_female': total_female,
        'total_children': total_children,
        'total_adult': total_adult,
        'total_elderly': total_elderly,
        'tier_matrix': tier_matrix,
        'daily_json': daily_json,
        'pdf_filename': f'{dept_name}-Stats-{month_start.strftime("%b-%Y")}.pdf',
        'orientation': request.GET.get('orientation', 'portrait'),
    }

    if request.GET.get('format') == 'pdf':
        from apps.reports.views import render_pdf
        return render_pdf('leadership/pdf/department_stats_pdf.html', ctx)

    return render(request, 'leadership/department_stats.html', ctx)
