"""
Power BI REST API endpoints.

Authentication: Bearer token in Authorization header.
  Authorization: Bearer <your-token>

Connect from Power BI Desktop:
  Get Data > Web > Advanced
  URL: http://<server>/api/powerbi/<endpoint>/
  Header: Authorization = Bearer <token>

All endpoints return JSON. Dates are ISO-8601 strings.
"""
import functools
from datetime import date, timedelta
from django.db.models import (
    Count, Sum, Avg, F, Q, Value, FloatField, IntegerField
)
from django.db.models.functions import (
    TruncMonth, TruncDate, TruncWeek, Coalesce, ExtractYear, ExtractMonth
)
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import APIToken


# ---------------------------------------------------------------------------
# Auth decorator
# ---------------------------------------------------------------------------

def powerbi_auth(view_func):
    """Validate Bearer token from Authorization header."""
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return JsonResponse({'error': 'Missing or invalid Authorization header'}, status=401)
        raw_token = auth.split(' ', 1)[1].strip()
        try:
            token = APIToken.objects.get(token=raw_token)
        except APIToken.DoesNotExist:
            return JsonResponse({'error': 'Invalid token'}, status=403)
        if not token.is_valid:
            return JsonResponse({'error': 'Token expired or inactive'}, status=403)
        token.touch()
        request.api_token = token
        return view_func(request, *args, **kwargs)
    return wrapper


def json_view(view_func):
    """Allow GET only, return JSON."""
    @functools.wraps(view_func)
    @csrf_exempt
    def wrapper(request, *args, **kwargs):
        if request.method != 'GET':
            return JsonResponse({'error': 'Method not allowed'}, status=405)
        return view_func(request, *args, **kwargs)
    return wrapper


def pbi(view_func):
    return json_view(powerbi_auth(view_func))


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _date_range(request, default_days=365):
    """Parse ?from=YYYY-MM-DD&to=YYYY-MM-DD query params."""
    today = timezone.localdate()
    try:
        date_from = date.fromisoformat(request.GET.get('from', str(today - timedelta(days=default_days))))
    except ValueError:
        date_from = today - timedelta(days=default_days)
    try:
        date_to = date.fromisoformat(request.GET.get('to', str(today)))
    except ValueError:
        date_to = today
    return date_from, date_to


# ===========================================================================
# 1. KPI Overview
# ===========================================================================

@pbi
def kpi_overview(request):
    """
    Top-level KPIs snapshot for Power BI scorecards.
    GET /api/powerbi/kpi/overview/
    """
    from apps.patients.models import Patient, Visit
    from apps.appointments.models import Appointment
    from apps.billing.models import Invoice, Payment, InvoiceStatus
    from apps.consultations.models import Consultation
    from apps.laboratory.models import LabOrder

    today = timezone.localdate()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    total_patients = Patient.objects.filter(is_active=True).count()
    new_this_month = Patient.objects.filter(created_at__date__gte=month_start).count()
    new_this_year = Patient.objects.filter(created_at__date__gte=year_start).count()

    visits_today = Visit.objects.filter(visit_date__date=today).count()
    visits_this_month = Visit.objects.filter(visit_date__date__gte=month_start).count()
    visits_this_year = Visit.objects.filter(visit_date__date__gte=year_start).count()

    appts_today = Appointment.objects.filter(appointment_date=today).count()
    appts_no_show = Appointment.objects.filter(
        appointment_date__gte=month_start, status='NO_SHOW'
    ).count()
    appts_this_month = Appointment.objects.filter(
        appointment_date__gte=month_start
    ).count()
    no_show_rate = round(appts_no_show / appts_this_month * 100, 1) if appts_this_month else 0

    # Revenue
    paid_invoices = Invoice.objects.filter(status=InvoiceStatus.PAID)
    revenue_this_month = Payment.objects.filter(
        payment_date__date__gte=month_start
    ).aggregate(total=Coalesce(Sum('amount'), Value(0), output_field=FloatField()))['total']
    revenue_this_year = Payment.objects.filter(
        payment_date__date__gte=year_start
    ).aggregate(total=Coalesce(Sum('amount'), Value(0), output_field=FloatField()))['total']

    pending_revenue = sum(
        inv.balance_due for inv in Invoice.objects.filter(
            status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID]
        ).select_related()
    )

    pending_labs = LabOrder.objects.filter(
        status__in=['ORDERED', 'SAMPLE_COLLECTED', 'PROCESSING']
    ).count()

    consultations_today = Consultation.objects.filter(
        created_at__date=today
    ).count()

    return JsonResponse({
        'snapshot_date': str(today),
        'patients': {
            'total_active': total_patients,
            'new_this_month': new_this_month,
            'new_this_year': new_this_year,
        },
        'visits': {
            'today': visits_today,
            'this_month': visits_this_month,
            'this_year': visits_this_year,
        },
        'appointments': {
            'today': appts_today,
            'this_month': appts_this_month,
            'no_show_this_month': appts_no_show,
            'no_show_rate_pct': no_show_rate,
        },
        'revenue': {
            'this_month_xaf': float(revenue_this_month),
            'this_year_xaf': float(revenue_this_year),
            'pending_xaf': float(pending_revenue),
        },
        'operations': {
            'pending_lab_orders': pending_labs,
            'consultations_today': consultations_today,
        },
    })


# ===========================================================================
# 2. Patient Demographics
# ===========================================================================

@pbi
def patient_demographics(request):
    """
    Patient breakdown by gender, age group, billing type, district.
    GET /api/powerbi/patients/demographics/
    """
    from apps.patients.models import Patient, BillingType

    qs = Patient.objects.filter(is_active=True)

    gender_data = list(
        qs.values('gender').annotate(count=Count('id')).order_by('gender')
    )

    from apps.patients.models import Visit
    billing_data = list(
        Visit.objects.filter(is_deleted=False).values('billing_type').annotate(count=Count('id')).order_by('billing_type')
    )

    district_data = list(
        qs.values('region').annotate(count=Count('id'))
        .order_by('-count')[:20]
    )

    # Age groups
    today = timezone.localdate()
    age_groups = {'0-17': 0, '18-35': 0, '36-50': 0, '51-65': 0, '65+': 0}
    for p in qs.exclude(date_of_birth=None).values_list('date_of_birth', flat=True):
        age = (today - p).days // 365
        if age <= 17:
            age_groups['0-17'] += 1
        elif age <= 35:
            age_groups['18-35'] += 1
        elif age <= 50:
            age_groups['36-50'] += 1
        elif age <= 65:
            age_groups['51-65'] += 1
        else:
            age_groups['65+'] += 1

    return JsonResponse({
        'total_active': qs.count(),
        'by_gender': gender_data,
        'by_billing_type': billing_data,
        'by_district': district_data,
        'by_age_group': [
            {'age_group': k, 'count': v} for k, v in age_groups.items()
        ],
    })


# ===========================================================================
# 3. Daily Visit Trend
# ===========================================================================

@pbi
def visits_daily(request):
    """
    Daily visit counts for trend charts.
    GET /api/powerbi/patients/visits/daily/?from=YYYY-MM-DD&to=YYYY-MM-DD
    Default: last 90 days.
    """
    from apps.patients.models import Visit

    date_from, date_to = _date_range(request, default_days=90)

    data = list(
        Visit.objects.filter(
            visit_date__date__gte=date_from,
            visit_date__date__lte=date_to,
        )
        .annotate(day=TruncDate('visit_date'))
        .values('day')
        .annotate(visits=Count('id'))
        .order_by('day')
    )

    return JsonResponse({
        'date_from': str(date_from),
        'date_to': str(date_to),
        'data': [{'date': str(row['day']), 'visits': row['visits']} for row in data],
    })


# ===========================================================================
# 4. Monthly Visit Trend
# ===========================================================================

@pbi
def visits_monthly(request):
    """
    Monthly visit counts + new patient registrations.
    GET /api/powerbi/patients/visits/monthly/?from=YYYY-MM-DD&to=YYYY-MM-DD
    Default: last 24 months.
    """
    from apps.patients.models import Visit, Patient

    date_from, date_to = _date_range(request, default_days=730)

    visits = list(
        Visit.objects.filter(
            visit_date__date__gte=date_from,
            visit_date__date__lte=date_to,
        )
        .annotate(month=TruncMonth('visit_date'))
        .values('month')
        .annotate(visits=Count('id'))
        .order_by('month')
    )

    new_patients = list(
        Patient.objects.filter(
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        )
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(new_patients=Count('id'))
        .order_by('month')
    )

    # Merge by month key
    np_map = {str(r['month'].date())[:7]: r['new_patients'] for r in new_patients}
    merged = []
    for row in visits:
        month_key = str(row['month'].date())[:7]
        merged.append({
            'month': month_key,
            'visits': row['visits'],
            'new_patients': np_map.get(month_key, 0),
        })

    return JsonResponse({
        'date_from': str(date_from),
        'date_to': str(date_to),
        'data': merged,
    })


# ===========================================================================
# 5. Revenue by Month & Category
# ===========================================================================

@pbi
def revenue_monthly(request):
    """
    Monthly revenue broken down by service category.
    GET /api/powerbi/billing/revenue/monthly/?from=YYYY-MM-DD&to=YYYY-MM-DD
    """
    from apps.billing.models import Payment, Invoice, InvoiceItem

    date_from, date_to = _date_range(request, default_days=365)

    # Payments by month
    payments_by_month = list(
        Payment.objects.filter(
            payment_date__date__gte=date_from,
            payment_date__date__lte=date_to,
        )
        .annotate(month=TruncMonth('payment_date'))
        .values('month', 'payment_method')
        .annotate(total=Sum('amount'))
        .order_by('month')
    )

    # Revenue by service category
    by_category = list(
        InvoiceItem.objects.filter(
            invoice__issue_date__gte=date_from,
            invoice__issue_date__lte=date_to,
            is_deleted=False,
        )
        .values('category')
        .annotate(total=Sum('line_total'))
        .order_by('-total')
    )

    return JsonResponse({
        'date_from': str(date_from),
        'date_to': str(date_to),
        'by_month_and_method': [
            {
                'month': str(r['month'].date())[:7],
                'payment_method': r['payment_method'],
                'total_xaf': float(r['total'] or 0),
            }
            for r in payments_by_month
        ],
        'by_service_category': [
            {'category': r['category'], 'total_xaf': float(r['total'] or 0)}
            for r in by_category
        ],
    })


# ===========================================================================
# 6. Appointment Analytics
# ===========================================================================

@pbi
def appointments_analytics(request):
    """
    Appointment volume, status breakdown, no-show rate by month.
    GET /api/powerbi/appointments/analytics/?from=YYYY-MM-DD&to=YYYY-MM-DD
    """
    from apps.appointments.models import Appointment

    date_from, date_to = _date_range(request, default_days=365)

    by_status = list(
        Appointment.objects.filter(
            appointment_date__gte=date_from,
            appointment_date__lte=date_to,
        )
        .values('status')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    by_month = list(
        Appointment.objects.filter(
            appointment_date__gte=date_from,
            appointment_date__lte=date_to,
        )
        .annotate(month=TruncMonth('appointment_date'))
        .values('month', 'status')
        .annotate(count=Count('id'))
        .order_by('month')
    )

    by_doctor = list(
        Appointment.objects.filter(
            appointment_date__gte=date_from,
            appointment_date__lte=date_to,
        )
        .values(doctor_name=F('doctor__get_full_name'))
        .annotate(total=Count('id'), no_shows=Count('id', filter=Q(status='NO_SHOW')))
        .order_by('-total')[:15]
    )

    return JsonResponse({
        'date_from': str(date_from),
        'date_to': str(date_to),
        'by_status': by_status,
        'by_month_and_status': [
            {
                'month': str(r['month'].date())[:7],
                'status': r['status'],
                'count': r['count'],
            }
            for r in by_month
        ],
        'by_doctor': [
            {
                'doctor': r['doctor_name'],
                'total': r['total'],
                'no_shows': r['no_shows'],
                'no_show_rate_pct': round(r['no_shows'] / r['total'] * 100, 1) if r['total'] else 0,
            }
            for r in by_doctor
        ],
    })


# ===========================================================================
# 7. Clinical Diagnoses
# ===========================================================================

@pbi
def diagnoses_frequency(request):
    """
    Top diagnoses by frequency for disease burden analysis.
    GET /api/powerbi/clinical/diagnoses/?from=YYYY-MM-DD&to=YYYY-MM-DD&limit=50
    """
    from apps.consultations.models import Diagnosis

    date_from, date_to = _date_range(request, default_days=365)
    limit = min(int(request.GET.get('limit', 50)), 200)

    data = list(
        Diagnosis.objects.filter(
            consultation__created_at__date__gte=date_from,
            consultation__created_at__date__lte=date_to,
        )
        .values('icd_code', 'description', 'eye_affected')
        .annotate(count=Count('id'))
        .order_by('-count')[:limit]
    )

    by_month = list(
        Diagnosis.objects.filter(
            consultation__created_at__date__gte=date_from,
            consultation__created_at__date__lte=date_to,
        )
        .annotate(month=TruncMonth('consultation__created_at'))
        .values('month', 'icd_code', 'description')
        .annotate(count=Count('id'))
        .order_by('month', '-count')
    )

    return JsonResponse({
        'date_from': str(date_from),
        'date_to': str(date_to),
        'top_diagnoses': data,
        'by_month': [
            {
                'month': str(r['month'].date())[:7],
                'icd_code': r['icd_code'],
                'diagnosis': r['description'],
                'count': r['count'],
            }
            for r in by_month
        ],
    })


# ===========================================================================
# 8. Laboratory Analytics
# ===========================================================================

@pbi
def lab_analytics(request):
    """
    Lab order volumes, turnaround time, status breakdown.
    GET /api/powerbi/laboratory/analytics/?from=YYYY-MM-DD&to=YYYY-MM-DD
    """
    from apps.laboratory.models import LabOrder

    date_from, date_to = _date_range(request, default_days=365)

    by_status = list(
        LabOrder.objects.filter(
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        )
        .values('status')
        .annotate(count=Count('id'))
    )

    by_month = list(
        LabOrder.objects.filter(
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        )
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(
            total=Count('id'),
            completed=Count('id', filter=Q(status='COMPLETED')),
        )
        .order_by('month')
    )

    return JsonResponse({
        'date_from': str(date_from),
        'date_to': str(date_to),
        'by_status': by_status,
        'by_month': [
            {
                'month': str(r['month'].date())[:7],
                'total_orders': r['total'],
                'completed': r['completed'],
                'completion_rate_pct': round(r['completed'] / r['total'] * 100, 1) if r['total'] else 0,
            }
            for r in by_month
        ],
    })


# ===========================================================================
# 9. Pharmacy / Drug Dispensing
# ===========================================================================

@pbi
def pharmacy_analytics(request):
    """
    Top dispensed drugs, monthly dispensing volume, stock alerts.
    GET /api/powerbi/pharmacy/analytics/?from=YYYY-MM-DD&to=YYYY-MM-DD
    """
    from apps.pharmacy.models import Drug, DispensingLog

    date_from, date_to = _date_range(request, default_days=365)

    # Low stock drugs
    low_stock = list(
        Drug.objects.filter(
            is_active=True,
            current_stock__lte=F('reorder_level'),
        )
        .values('name', 'generic_name', 'current_stock', 'reorder_level')
        .order_by('current_stock')[:20]
    )

    # Try to get dispensing logs if model exists
    dispensed = []
    try:
        dispensed = list(
            DispensingLog.objects.filter(
                dispensed_at__date__gte=date_from,
                dispensed_at__date__lte=date_to,
            )
            .values('drug__name', 'drug__generic_name')
            .annotate(total_qty=Sum('quantity_dispensed'), count=Count('id'))
            .order_by('-total_qty')[:30]
        )
    except Exception:
        pass

    drug_count = Drug.objects.filter(is_active=True).count()
    out_of_stock = Drug.objects.filter(is_active=True, current_stock=0).count()

    return JsonResponse({
        'date_from': str(date_from),
        'date_to': str(date_to),
        'inventory_summary': {
            'total_active_drugs': drug_count,
            'out_of_stock': out_of_stock,
            'low_stock_count': len(low_stock),
        },
        'low_stock_alerts': [
            {
                'drug': r['name'],
                'generic_name': r['generic_name'],
                'current_stock': r['current_stock'],
                'reorder_level': r['reorder_level'],
            }
            for r in low_stock
        ],
        'top_dispensed': [
            {
                'drug': r['drug__name'],
                'generic_name': r['drug__generic_name'],
                'total_qty': r['total_qty'],
                'dispensing_count': r['count'],
            }
            for r in dispensed
        ],
    })


# ===========================================================================
# 10. Staff Performance
# ===========================================================================

@pbi
def staff_performance(request):
    """
    Consultations per doctor, appointment completion rates.
    GET /api/powerbi/staff/performance/?from=YYYY-MM-DD&to=YYYY-MM-DD
    """
    from apps.consultations.models import Consultation
    from apps.appointments.models import Appointment
    from apps.accounts.models import User, UserRole

    date_from, date_to = _date_range(request, default_days=365)

    consultations_by_doctor = list(
        Consultation.objects.filter(
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        )
        .values('doctor__first_name', 'doctor__last_name', 'doctor__email')
        .annotate(total_consultations=Count('id'))
        .order_by('-total_consultations')
    )

    appts_by_doctor = list(
        Appointment.objects.filter(
            appointment_date__gte=date_from,
            appointment_date__lte=date_to,
        )
        .values('doctor__first_name', 'doctor__last_name', 'doctor__email')
        .annotate(
            total=Count('id'),
            completed=Count('id', filter=Q(status='COMPLETED')),
            no_show=Count('id', filter=Q(status='NO_SHOW')),
        )
        .order_by('-total')
    )

    return JsonResponse({
        'date_from': str(date_from),
        'date_to': str(date_to),
        'consultations_by_doctor': [
            {
                'doctor': f"{r['doctor__first_name']} {r['doctor__last_name']}",
                'email': r['doctor__email'],
                'consultations': r['total_consultations'],
            }
            for r in consultations_by_doctor
        ],
        'appointments_by_doctor': [
            {
                'doctor': f"{r['doctor__first_name']} {r['doctor__last_name']}",
                'total_appointments': r['total'],
                'completed': r['completed'],
                'no_show': r['no_show'],
                'completion_rate_pct': round(r['completed'] / r['total'] * 100, 1) if r['total'] else 0,
            }
            for r in appts_by_doctor
        ],
    })


# ===========================================================================
# 11. Financial Summary (CEO / CFO level)
# ===========================================================================

@pbi
def financial_summary(request):
    """
    Full financial overview: revenue, collections, outstanding, by category.
    GET /api/powerbi/billing/financial-summary/?from=YYYY-MM-DD&to=YYYY-MM-DD
    """
    from apps.billing.models import Invoice, Payment, InvoiceStatus, PaymentMethod

    date_from, date_to = _date_range(request, default_days=365)

    invoices = Invoice.objects.filter(
        issue_date__gte=date_from,
        issue_date__lte=date_to,
    )

    total_invoiced = sum(inv.total for inv in invoices)
    total_collected = Payment.objects.filter(
        payment_date__date__gte=date_from,
        payment_date__date__lte=date_to,
    ).aggregate(total=Coalesce(Sum('amount'), Value(0), output_field=FloatField()))['total']

    by_payment_method = list(
        Payment.objects.filter(
            payment_date__date__gte=date_from,
            payment_date__date__lte=date_to,
        )
        .values('payment_method')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')
    )

    invoice_status_summary = list(
        invoices.values('status').annotate(count=Count('id')).order_by('status')
    )

    monthly_revenue = list(
        Payment.objects.filter(
            payment_date__date__gte=date_from,
            payment_date__date__lte=date_to,
        )
        .annotate(month=TruncMonth('payment_date'))
        .values('month')
        .annotate(collected=Sum('amount'))
        .order_by('month')
    )

    return JsonResponse({
        'date_from': str(date_from),
        'date_to': str(date_to),
        'summary': {
            'total_invoiced_xaf': float(total_invoiced),
            'total_collected_xaf': float(total_collected),
            'collection_rate_pct': round(float(total_collected) / float(total_invoiced) * 100, 1) if total_invoiced else 0,
        },
        'by_payment_method': [
            {
                'method': r['payment_method'],
                'total_xaf': float(r['total'] or 0),
                'transaction_count': r['count'],
            }
            for r in by_payment_method
        ],
        'invoice_status': invoice_status_summary,
        'monthly_collections': [
            {
                'month': str(r['month'].date())[:7],
                'collected_xaf': float(r['collected'] or 0),
            }
            for r in monthly_revenue
        ],
    })


# ===========================================================================
# 12. Outreach & Community
# ===========================================================================

@pbi
def outreach_analytics(request):
    """
    Outreach programme reach, locations, patient acquisitions.
    GET /api/powerbi/outreach/analytics/?from=YYYY-MM-DD&to=YYYY-MM-DD
    """
    from apps.outreach.models import OutreachProgram, OutreachPatient

    date_from, date_to = _date_range(request, default_days=365)

    programs = list(
        OutreachProgram.objects.filter(
            date__gte=date_from,
            date__lte=date_to,
        )
        .values('name', 'location', 'date', 'patients_screened', 'patients_referred')
        .order_by('date')
    )

    return JsonResponse({
        'date_from': str(date_from),
        'date_to': str(date_to),
        'programs': [
            {
                'name': r['name'],
                'location': r['location'],
                'date': str(r['date']),
                'screened': r['patients_screened'] or 0,
                'referred': r['patients_referred'] or 0,
            }
            for r in programs
        ],
        'totals': {
            'programs': len(programs),
            'total_screened': sum(r['patients_screened'] or 0 for r in programs),
            'total_referred': sum(r['patients_referred'] or 0 for r in programs),
        },
    })


# ===========================================================================
# 13. Endpoint Discovery
# ===========================================================================

@json_view
@csrf_exempt
def powerbi_index(request):
    """
    Lists all available Power BI endpoints.
    GET /api/powerbi/
    No authentication required for discovery.
    """
    base = '/api/powerbi'
    return JsonResponse({
        'name': 'EHR Africa Power BI API',
        'version': '1.0',
        'authentication': 'Bearer token — set Authorization: Bearer <token> header',
        'endpoints': {
            'kpi_overview': f'{base}/kpi/overview/',
            'patient_demographics': f'{base}/patients/demographics/',
            'visits_daily': f'{base}/patients/visits/daily/?from=YYYY-MM-DD&to=YYYY-MM-DD',
            'visits_monthly': f'{base}/patients/visits/monthly/?from=YYYY-MM-DD&to=YYYY-MM-DD',
            'revenue_monthly': f'{base}/billing/revenue/monthly/?from=YYYY-MM-DD&to=YYYY-MM-DD',
            'financial_summary': f'{base}/billing/financial-summary/?from=YYYY-MM-DD&to=YYYY-MM-DD',
            'appointments_analytics': f'{base}/appointments/analytics/?from=YYYY-MM-DD&to=YYYY-MM-DD',
            'diagnoses_frequency': f'{base}/clinical/diagnoses/?from=YYYY-MM-DD&to=YYYY-MM-DD&limit=50',
            'lab_analytics': f'{base}/laboratory/analytics/?from=YYYY-MM-DD&to=YYYY-MM-DD',
            'pharmacy_analytics': f'{base}/pharmacy/analytics/?from=YYYY-MM-DD&to=YYYY-MM-DD',
            'staff_performance': f'{base}/staff/performance/?from=YYYY-MM-DD&to=YYYY-MM-DD',
            'outreach_analytics': f'{base}/outreach/analytics/?from=YYYY-MM-DD&to=YYYY-MM-DD',
        },
    })
