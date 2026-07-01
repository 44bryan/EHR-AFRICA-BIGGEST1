"""
Embedded analytics dashboard — Power BI-style charts in the browser.
"""
import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone


def _require_director(request):
    return (
        request.user.is_super_admin
        or request.user.is_medical_director
        or request.user.is_ceo
        or request.user.is_finance_director
        or request.user.is_admin_director
    )


@login_required
def analytics_dashboard(request):
    """Embedded Power BI-style analytics dashboard."""
    if not _require_director(request):
        raise PermissionDenied

    from apps.api.models import APIToken
    try:
        token = APIToken.objects.filter(is_active=True).first()
        api_token = token.token if token else ''
    except Exception:
        api_token = ''

    return render(request, 'leadership/analytics_dashboard.html', {
        'api_token': api_token,
        'today': timezone.localdate(),
    })


@login_required
def analytics_data_json(request):
    """Single JSON endpoint that feeds all analytics dashboard charts."""
    if not _require_director(request):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    today = timezone.localdate()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    last_month_end = month_start - timedelta(days=1)

    from apps.patients.models import Patient, Visit
    from apps.appointments.models import Appointment
    from apps.consultations.models import Consultation, ConsultationDiagnosis

    # 12-month trend
    monthly_visits = []
    monthly_patients = []
    monthly_revenue = []
    for i in range(11, -1, -1):
        d = (today.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        next_d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        v = Visit.objects.filter(visit_date__date__gte=d, visit_date__date__lt=next_d, is_deleted=False).count()
        p = Patient.objects.filter(created_at__date__gte=d, created_at__date__lt=next_d, is_deleted=False).count()
        monthly_visits.append({'month': d.strftime('%b %Y'), 'visits': v})
        monthly_patients.append({'month': d.strftime('%b %Y'), 'patients': p})

    try:
        from apps.billing.models import Payment
        for i in range(11, -1, -1):
            d = (today.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
            next_d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
            r = Payment.objects.filter(
                payment_date__date__gte=d, payment_date__date__lt=next_d, is_deleted=False
            ).aggregate(total=Sum('amount'))['total'] or 0
            monthly_revenue.append({'month': d.strftime('%b %Y'), 'revenue': float(r)})
    except Exception:
        monthly_revenue = [{'month': m['month'], 'revenue': 0} for m in monthly_visits]

    # Daily visits last 30 days
    daily_visits = []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        v = Visit.objects.filter(visit_date__date=d, is_deleted=False).count()
        daily_visits.append({'date': d.strftime('%d %b'), 'visits': v})

    # Top diagnoses last 90 days
    top_dx = list(
        ConsultationDiagnosis.objects.filter(
            consultation__created_at__date__gte=today - timedelta(days=90),
            consultation__is_deleted=False,
        ).values('diagnosis__description').annotate(count=Count('id')).order_by('-count')[:10]
    )

    # Appointments by status this month
    appt_status = list(
        Appointment.objects.filter(
            appointment_date__gte=month_start, is_deleted=False
        ).values('status').annotate(count=Count('id')).order_by('-count')
    )

    # Revenue by payment method this month
    rev_by_method = []
    try:
        from apps.billing.models import Payment
        raw = list(
            Payment.objects.filter(
                payment_date__date__gte=month_start, is_deleted=False
            ).values('payment_method').annotate(total=Sum('amount')).order_by('-total')
        )
        rev_by_method = [{'method': r['payment_method'], 'total': float(r['total'] or 0)} for r in raw]
    except Exception:
        pass

    # Patient demographics
    gender_data = list(Patient.objects.filter(is_active=True, is_deleted=False).values('gender').annotate(count=Count('id')))
    from apps.patients.models import Visit
    billing_type_data = list(Visit.objects.filter(is_deleted=False).values('billing_type').annotate(count=Count('id')))

    # Doctor throughput last 30 days
    doctor_data = list(
        Consultation.objects.filter(
            created_at__date__gte=today - timedelta(days=30), is_deleted=False
        ).values('consulting_doctor__first_name', 'consulting_doctor__last_name')
        .annotate(count=Count('id')).order_by('-count')[:8]
    )

    # Consultation monthly trend (12 months)
    monthly_consultations = []
    for i in range(11, -1, -1):
        d = (today.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        next_d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        c = Consultation.objects.filter(
            consultation_date__date__gte=d, consultation_date__date__lt=next_d, is_deleted=False
        ).count()
        monthly_consultations.append({'month': d.strftime('%b %Y'), 'count': c})

    # Consultation by status (all time)
    consult_by_status = list(
        Consultation.objects.filter(is_deleted=False)
        .values('status').annotate(count=Count('id')).order_by('-count')
    )

    # Consultation by department
    consult_by_dept = list(
        Consultation.objects.filter(is_deleted=False)
        .values('department__name').annotate(count=Count('id')).order_by('-count')[:10]
    )

    # Pharmacy: stock levels and dispensing trend
    pharmacy_stock = []
    dispensing_trend = []
    try:
        from apps.pharmacy.models import Drug, Dispensing
        all_drugs = list(Drug.objects.filter(is_active=True, is_deleted=False))
        for d in sorted(all_drugs, key=lambda x: x.current_stock)[:10]:
            pharmacy_stock.append({
                'name': d.name[:30],
                'stock': d.current_stock,
                'reorder': d.reorder_level,
                'low': d.needs_reorder,
            })
        for i in range(29, -1, -1):
            dd = today - timedelta(days=i)
            cnt = Dispensing.objects.filter(dispensed_at__date=dd, is_deleted=False).count()
            dispensing_trend.append({'date': dd.strftime('%d %b'), 'count': cnt})
    except Exception:
        pass

    # KPI summary
    try:
        from apps.billing.models import Payment
        rev_month = Payment.objects.filter(payment_date__date__gte=month_start, is_deleted=False).aggregate(t=Sum('amount'))['t'] or 0
        rev_year = Payment.objects.filter(payment_date__date__gte=year_start, is_deleted=False).aggregate(t=Sum('amount'))['t'] or 0
        rev_last_month = Payment.objects.filter(
            payment_date__date__gte=last_month_start, payment_date__date__lte=last_month_end, is_deleted=False
        ).aggregate(t=Sum('amount'))['t'] or 0
        rev_growth = round(((float(rev_month) - float(rev_last_month)) / float(rev_last_month)) * 100, 1) if rev_last_month else 0
    except Exception:
        rev_month = rev_year = rev_last_month = rev_growth = 0

    visits_this_month = Visit.objects.filter(visit_date__date__gte=month_start, is_deleted=False).count()
    visits_last_month = Visit.objects.filter(
        visit_date__date__gte=last_month_start, visit_date__date__lte=last_month_end, is_deleted=False
    ).count()
    visit_growth = round(((visits_this_month - visits_last_month) / visits_last_month) * 100, 1) if visits_last_month else 0

    new_patients_month = Patient.objects.filter(created_at__date__gte=month_start, is_deleted=False).count()
    new_patients_last = Patient.objects.filter(
        created_at__date__gte=last_month_start, created_at__date__lte=last_month_end, is_deleted=False
    ).count()
    patient_growth = round(((new_patients_month - new_patients_last) / new_patients_last) * 100, 1) if new_patients_last else 0

    return JsonResponse({
        'kpis': {
            'total_patients': Patient.objects.filter(is_active=True, is_deleted=False).count(),
            'visits_today': Visit.objects.filter(visit_date__date=today, is_deleted=False).count(),
            'visits_this_month': visits_this_month,
            'visit_growth': visit_growth,
            'new_patients_month': new_patients_month,
            'patient_growth': patient_growth,
            'rev_month': float(rev_month),
            'rev_year': float(rev_year),
            'rev_growth': rev_growth,
            'appts_today': Appointment.objects.filter(appointment_date=today, is_deleted=False).count(),
        },
        'monthly_visits': monthly_visits,
        'monthly_patients': monthly_patients,
        'monthly_revenue': monthly_revenue,
        'daily_visits': daily_visits,
        'top_diagnoses': [{'name': (d['diagnosis__description'] or 'Unknown')[:40], 'count': d['count']} for d in top_dx],
        'appointments_by_status': [{'status': a['status'], 'count': a['count']} for a in appt_status],
        'revenue_by_method': rev_by_method,
        'patient_gender': [{'gender': g['gender'], 'count': g['count']} for g in gender_data],
        'patient_billing_type': [{'type': b['billing_type'], 'count': b['count']} for b in billing_type_data],
        'doctor_throughput': [
            {
                'name': f"Dr. {d['consulting_doctor__first_name']} {d['consulting_doctor__last_name']}",
                'count': d['count'],
            }
            for d in doctor_data
        ],
        'monthly_consultations': monthly_consultations,
        'consultations_by_status': [{'status': c['status'], 'count': c['count']} for c in consult_by_status],
        'consultations_by_dept': [{'dept': (c['department__name'] or 'General')[:30], 'count': c['count']} for c in consult_by_dept],
        'pharmacy_stock': pharmacy_stock,
        'dispensing_trend': dispensing_trend,
    })
