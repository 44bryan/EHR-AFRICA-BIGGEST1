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


def _require_director(request):
    """
    Leadership views are visible to:
    - Super Admin (master account, controls everything)
    - Medical Director (controls all clinical operations)
    - CEO (sees everything, read-only)
    - Finance Director (sees everything, focus on finance)
    - Admin Director (sees everything, read-only)
    """
    return (
        request.user.is_super_admin
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
