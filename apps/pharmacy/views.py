from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db.models import Q, Sum, F, Value, Max, Count, IntegerField
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
import re
from .models import (
    Drug, DrugStock, Dispensing, DispensingItem, DispensingStatus,
    StockAdjustment, AdjustmentReason,
    ControlledDrugEntry, ControlledDrugEntryType,
    WardDrugReturn, WardDrugReturnStatus,
    ChronicPrescription,
    Supplier, PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus,
    DispensingReturn, DispensingReturnReason,
    RxLineUnavailable, UnavailableReason,
    PharmacyLocation, StockTransfer, StockTransferItem, TransferStatus,
    StockExit, StockExitReason, DrugRecall, RecallStatus,
)
from .forms import (
    DrugCreateForm, AddStockForm, DispensingItemForm,
    SupplierForm, PurchaseOrderForm, DispensingReturnForm,
)
from apps.patients.models import Patient
from apps.prescriptions.models import DrugPrescription


def _can_access_pharmacy(user):
    """Pharmacy, dispensing, and admin roles."""
    from apps.accounts.models import UserRole
    return user.role in (
        UserRole.PHARMACIST, UserRole.HEAD_PHARMACIST,
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR,
        UserRole.MEDICAL_DIRECTOR, UserRole.CEO, UserRole.ADMIN,
        UserRole.STORE_KEEPER, UserRole.FINANCE_DIRECTOR,
    ) or user.can_dispense_pharmacy()


@login_required
def pharmacy_dashboard(request):
    if not _can_access_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Access denied — pharmacy roles only.')
    from django.core.cache import cache
    today = timezone.localdate()
    # ── Stock & expiry data — cached 90s (changes infrequently, auto-refresh is 30s) ──
    _cache_key = f'pharm_stock_data_{today}'
    _cached_stock = cache.get(_cache_key)
    if _cached_stock is None:
        _stock_q = Q(stock_items__is_deleted=False) & (Q(stock_items__expiry_date__gte=today) | Q(stock_items__expiry_date__isnull=True))
        low_stock_drugs = list(
            Drug.objects.filter(is_active=True, is_deleted=False)
            .annotate(stock_total=Coalesce(Sum('stock_items__quantity_remaining', filter=_stock_q), Value(0, output_field=IntegerField())))
            .filter(stock_total__lte=F('reorder_level'))
            .order_by('name')
        )
        _base_expiry_qs = DrugStock.objects.filter(
            is_deleted=False, expiry_date__gte=today, quantity_remaining__gt=0,
        ).select_related('drug').order_by('expiry_date')
        expiring_critical = list(_base_expiry_qs.filter(expiry_date__lte=today + timezone.timedelta(days=30)))
        expiring_warning  = list(_base_expiry_qs.filter(expiry_date__gt=today + timezone.timedelta(days=30), expiry_date__lte=today + timezone.timedelta(days=60)))
        expiring_notice   = list(_base_expiry_qs.filter(expiry_date__gt=today + timezone.timedelta(days=60), expiry_date__lte=today + timezone.timedelta(days=90)))
        expired_in_stock  = list(DrugStock.objects.filter(is_deleted=False, expiry_date__lt=today, quantity_remaining__gt=0).select_related('drug').order_by('expiry_date'))
        _cached_stock = {
            'low_stock_drugs': low_stock_drugs,
            'expiring_critical': expiring_critical,
            'expiring_warning': expiring_warning,
            'expiring_notice': expiring_notice,
            'expired_in_stock': expired_in_stock,
        }
        cache.set(_cache_key, _cached_stock, 90)
    else:
        low_stock_drugs  = _cached_stock['low_stock_drugs']
        expiring_critical = _cached_stock['expiring_critical']
        expiring_warning  = _cached_stock['expiring_warning']
        expiring_notice   = _cached_stock['expiring_notice']
        expired_in_stock  = _cached_stock['expired_in_stock']
    expiring_soon = expiring_critical + expiring_warning + expiring_notice

    today_dispensings = Dispensing.objects.filter(
        dispensed_at__date=today, is_deleted=False
    )

    # Pharmacy revenue = what was actually billed and collected via the main
    # billing module (InvoiceItem category=PHARMACY, paid today).
    # This is the authoritative source — not Dispensing.amount_paid.
    try:
        from apps.billing.models import InvoiceItem, Payment
        from django.db.models import F as BF, ExpressionWrapper, DecimalField as DF
        pharmacy_billed_today = InvoiceItem.objects.filter(
            invoice__issue_date=today,
            invoice__is_deleted=False,
            is_deleted=False,
            category='PHARMACY',
        ).aggregate(
            total=Sum(ExpressionWrapper(BF('unit_price') * BF('quantity'), output_field=DF(max_digits=12, decimal_places=2)))
        )['total'] or 0
    except Exception:
        pharmacy_billed_today = 0

    # Paid work orders waiting for pharmacy to dispense
    try:
        from apps.billing.models import ServiceWorkOrder, WorkOrderStatus
        pharmacy_work_orders = list(
            ServiceWorkOrder.objects.filter(
                status=WorkOrderStatus.PENDING,
                category='PHARMACY',
                is_deleted=False,
                created_at__date=today,
            ).select_related('patient', 'invoice').order_by('created_at')
        )
    except Exception:
        pharmacy_work_orders = []

    # Patients currently waiting at pharmacy (visit status = PHARMACY, today)
    # Exclude patients already in a work order (paid queue) to avoid duplication
    from apps.patients.models import Visit
    from apps.prescriptions.models import DrugPrescription
    work_order_patient_ids = {wo.patient_id for wo in pharmacy_work_orders}
    from django.db.models import Case, When, Value as _V
    _tier_order = Case(When(service_tier='VIP', then=_V(3)), When(service_tier='FAST_TRACK', then=_V(2)),
                       When(service_tier='EXPRESS', then=_V(1)), default=_V(0), output_field=IntegerField())
    _pt = getattr(request.user, 'patient_tier', 'ALL')
    _pharm_qs = Visit.objects.filter(visit_date__date=today, status='PHARMACY', is_deleted=False)
    if _pt == 'VIP':
        _pharm_qs = _pharm_qs.filter(service_tier='VIP')
    elif _pt == 'EXPRESS':
        _pharm_qs = _pharm_qs.filter(service_tier__in=['EXPRESS', 'FAST_TRACK'])
    elif _pt == 'STANDARD':
        _pharm_qs = _pharm_qs.filter(service_tier='STANDARD')
    # _pt == 'ALL' → no filter (supervisor sees everyone)
    waiting_visits = list(
        _pharm_qs.exclude(patient_id__in=work_order_patient_ids)
        .select_related('patient', 'attending_doctor')
        .annotate(_tier_order=_tier_order).order_by('-_tier_order', 'visit_date')
    )
    # Attach latest pending prescription to each visit
    if waiting_visits:
        patient_ids = [v.patient_id for v in waiting_visits]
        latest_rx = {
            rx.patient_id: rx
            for rx in DrugPrescription.objects.filter(
                patient_id__in=patient_ids,
                is_dispensed=False,
                is_deleted=False,
            ).select_related('prescribed_by').prefetch_related(
                'items', 'items__unavailable',
            )
            .order_by('-created_at')
        }
        for v in waiting_visits:
            v.latest_rx = latest_rx.get(v.patient_id)

    # Pharmacist's own shift for today (for cash desk status card)
    my_shift = None
    if request.user.is_pharmacist:
        try:
            from apps.billing.models import CashierShift, ShiftStatus
            my_shift = CashierShift.objects.filter(
                cashier=request.user, shift_date=today,
                status=ShiftStatus.OPEN, is_deleted=False,
            ).first()
        except Exception:
            pass

    # Rx lines marked unavailable today
    unavailable_today = RxLineUnavailable.objects.filter(
        is_deleted=False, created_at__date=today,
    ).count()

    # Declined Rx today (marked as "bought elsewhere")
    declined_today = DrugPrescription.objects.filter(
        is_dispensed=True, is_deleted=False,
        dispensed_at__date=today,
        notes__icontains='Bought elsewhere',
    ).count()

    # OTC + confirmed at cashier — single query on Dispensing
    _disp_counts = Dispensing.objects.filter(is_deleted=False).aggregate(
        otc_today=Count('id', filter=Q(is_otc=True, dispensed_at__date=today)),
        confirmed_at_cashier=Count('id', filter=Q(status=DispensingStatus.CONFIRMED)),
    )
    otc_today = _disp_counts['otc_today']
    confirmed_at_cashier = _disp_counts['confirmed_at_cashier']

    # Stock inventory value (selling price × remaining qty, non-expired only)
    stock_value = DrugStock.objects.filter(
        is_deleted=False, quantity_remaining__gt=0,
    ).filter(
        Q(expiry_date__gte=today) | Q(expiry_date__isnull=True)
    ).aggregate(
        total=Sum(F('quantity_remaining') * F('drug__selling_price'))
    )['total'] or 0

    # Top 5 dispensed drugs today
    top_drugs_today = list(
        DispensingItem.objects.filter(
            dispensing__dispensed_at__date=today,
            dispensing__is_deleted=False,
            drug__isnull=False,
        ).values('drug__name').annotate(
            total_qty=Sum('quantity_dispensed'),
            total_val=Sum('subtotal'),
        ).order_by('-total_qty')[:5]
    )

    # Average wait time: Rx created → dispensed (completed dispensings today)
    from django.db.models import Avg, ExpressionWrapper, DurationField
    avg_wait_raw = Dispensing.objects.filter(
        status=DispensingStatus.DISPENSED,
        dispensed_at__date=today,
        is_deleted=False,
        prescription__isnull=False,
    ).annotate(
        wait=ExpressionWrapper(
            F('dispensed_at') - F('prescription__created_at'),
            output_field=DurationField(),
        )
    ).aggregate(avg_wait=Avg('wait'))['avg_wait']
    avg_wait_minutes = round(avg_wait_raw.total_seconds() / 60) if avg_wait_raw else None

    # Fulfilment + status counts — single aggregate instead of 4 separate count() calls
    import json
    from datetime import timedelta
    from django.db.models.functions import TruncDate
    _today_agg = today_dispensings.aggregate(
        today_count=Count('id'),
        today_completed=Count('id', filter=Q(status=DispensingStatus.DISPENSED)),
        today_cancelled=Count('id', filter=Q(status=DispensingStatus.CANCELLED)),
    )
    today_count = _today_agg['today_count']
    today_completed = _today_agg['today_completed']
    today_cancelled = _today_agg['today_cancelled']
    today_total_resolved = today_completed + declined_today + today_cancelled
    fulfilment_rate = round(today_completed / today_total_resolved * 100) if today_total_resolved else 100

    # 7-day dispensing trend for chart — single query
    week_ago = today - timedelta(days=6)
    _trend_raw = dict(
        Dispensing.objects.filter(
            dispensed_at__date__gte=week_ago, is_deleted=False,
        ).annotate(day=TruncDate('dispensed_at'))
        .values_list('day').annotate(c=Count('id')).values_list('day', 'c')
    )
    daily_trend = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        daily_trend.append({'date': d.strftime('%a'), 'count': _trend_raw.get(d, 0)})
    daily_trend_json = json.dumps({
        'labels': [d['date'] for d in daily_trend],
        'data': [d['count'] for d in daily_trend],
    })

    # Status breakdown for doughnut chart — single query
    pending_count = Dispensing.objects.filter(
        status__in=[DispensingStatus.PENDING, DispensingStatus.PARTIAL],
        created_at__date=today, is_deleted=False,
    ).count()
    status_chart_json = json.dumps({
        'labels': ['Dispensed', 'Pending', 'At Cashier', 'Cancelled', 'Declined'],
        'data': [today_completed, pending_count, confirmed_at_cashier, today_cancelled, declined_today],
        'colors': ['#16a34a', '#f59e0b', '#3b82f6', '#6b7280', '#dc2626'],
    })

    # Revenue/financial data: only head pharmacist and management can see
    _can_see_revenue = (
        request.user.is_head_pharmacist or request.user.is_super_admin
        or request.user.is_admin_director or request.user.is_finance_director
        or request.user.is_ceo or request.user.is_medical_director
    )

    context = {
        'low_stock_count': len(low_stock_drugs),
        'low_stock_drugs': low_stock_drugs[:15],
        'expiring_soon': expiring_soon,
        'expiring_critical': expiring_critical,
        'expiring_warning': expiring_warning,
        'expiring_notice': expiring_notice,
        'expired_in_stock': expired_in_stock,
        'today_dispensings': today_count,
        'today_revenue': pharmacy_billed_today if _can_see_revenue else None,
        'pending_dispensings': pending_count,
        'total_drugs': Drug.objects.filter(is_active=True, is_deleted=False).count(),
        'pharmacy_work_orders': pharmacy_work_orders,
        'waiting_visits': waiting_visits,
        'my_shift': my_shift,
        'declined_today': declined_today,
        'unavailable_today': unavailable_today,
        'otc_today': otc_today,
        'confirmed_at_cashier': confirmed_at_cashier,
        'stock_value': stock_value if _can_see_revenue else None,
        'top_drugs_today': top_drugs_today,
        'avg_wait_minutes': avg_wait_minutes,
        'fulfilment_rate': fulfilment_rate,
        'daily_trend_json': daily_trend_json,
        'status_chart_json': status_chart_json,
        'can_see_revenue': _can_see_revenue,
    }
    return render(request, 'pharmacy/dashboard.html', context)


@login_required
def pharmacy_stats_view(request):
    """Monthly pharmacy statistics — dispensings, top drugs, revenue, gender breakdown.
    Revenue/financial data restricted to head pharmacist and management only."""
    if not (request.user.is_head_pharmacist or request.user.is_medical_director
            or request.user.is_super_admin or request.user.is_ceo
            or request.user.is_admin_director or request.user.is_finance_director):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Access denied — Head Pharmacist or management only.')

    import json, calendar
    from datetime import date as _date

    today = timezone.localdate()
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
        month_start = _date(year, month, 1)
    except (ValueError, TypeError):
        month_start = today.replace(day=1)
        year, month = month_start.year, month_start.month

    last_day   = calendar.monthrange(year, month)[1]
    month_end  = _date(year, month, last_day)

    base = Dispensing.objects.filter(
        is_deleted=False,
        dispensed_at__date__gte=month_start,
        dispensed_at__date__lte=month_end,
    )
    base_items = DispensingItem.objects.filter(
        dispensing__is_deleted=False,
        dispensing__dispensed_at__date__gte=month_start,
        dispensing__dispensed_at__date__lte=month_end,
    )

    # Single aggregate for all status counts + revenue (replaces 5 separate queries)
    _stats_agg = base.aggregate(
        total_dispensings=Count('id'),
        dispensed_count=Count('id', filter=Q(status=DispensingStatus.DISPENSED)),
        partial_count=Count('id', filter=Q(status=DispensingStatus.PARTIAL)),
        cancelled_count=Count('id', filter=Q(status=DispensingStatus.CANCELLED)),
        revenue=Sum('total_amount', filter=Q(status=DispensingStatus.DISPENSED)),
    )
    total_dispensings  = _stats_agg['total_dispensings']
    dispensed_count    = _stats_agg['dispensed_count']
    partial_count      = _stats_agg['partial_count']
    cancelled_count    = _stats_agg['cancelled_count']
    revenue            = _stats_agg['revenue'] or 0
    total_items        = base_items.count()
    completion_rate    = round(dispensed_count / total_dispensings * 100, 1) if total_dispensings else 0

    # Top 15 drugs dispensed — group by drug FK + custom name
    top_drugs_raw = list(
        base_items.values('drug__name', 'custom_drug_name')
        .annotate(count=Count('id'), qty=Sum('quantity_dispensed'))
        .order_by('-qty')[:15]
    )
    # Normalise to single drug_name key
    top_drugs = []
    for d in top_drugs_raw:
        top_drugs.append({
            'drug_name': d['drug__name'] or d['custom_drug_name'] or 'Non-formulary Drug',
            'count': d['count'],
            'qty': d['qty'] or 0,
        })

    # Daily volume (last 14 days) — single query instead of 14
    from datetime import timedelta
    from django.db.models.functions import TruncDate
    _14d_ago = today - timedelta(days=13)
    _daily_raw = dict(
        Dispensing.objects.filter(
            is_deleted=False, dispensed_at__date__gte=_14d_ago,
        ).annotate(day=TruncDate('dispensed_at'))
        .values_list('day').annotate(c=Count('id')).values_list('day', 'c')
    )
    daily_volume = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        daily_volume.append({'date': d.strftime('%d %b'), 'count': _daily_raw.get(d, 0)})
    daily_json = json.dumps({'labels': [d['date'] for d in daily_volume], 'data': [d['count'] for d in daily_volume]})

    # Gender breakdown (from patient)
    gender_raw = base.values('patient__gender').annotate(count=Count('id'))
    gender_map = {g['patient__gender']: g['count'] for g in gender_raw}
    male_count   = gender_map.get('M', 0)
    female_count = gender_map.get('F', 0)
    gender_json  = json.dumps([
        {'label': 'Male',   'count': male_count},
        {'label': 'Female', 'count': female_count},
    ])

    # ── WHO Age Group Breakdown ────────────────────────────────────────
    from datetime import date as _dt
    WHO_BANDS = [
        ('0-4', 0, 4), ('5-14', 5, 14), ('15-24', 15, 24), ('25-34', 25, 34),
        ('35-44', 35, 44), ('45-54', 45, 54), ('55-64', 55, 64), ('65+', 65, 200),
    ]
    age_counts = {b[0]: 0 for b in WHO_BANDS}
    paed_count = 0
    adult_count = 0
    # Get unique patients with DOB from this month's dispensings
    _patient_dobs = list(
        base.filter(patient__isnull=False)
        .values_list('patient__date_of_birth', flat=True)
        .distinct()
    )
    for dob in _patient_dobs:
        if not dob:
            continue
        age = (month_start - dob).days // 365
        if age < 15:
            paed_count += 1
        else:
            adult_count += 1
        for label, lo, hi in WHO_BANDS:
            if lo <= age <= hi:
                age_counts[label] += 1
                break
    age_json = json.dumps([{'label': k, 'count': v} for k, v in age_counts.items()])

    # ── Drug Category × Sex × Age Group Audit Table ────────────────────
    # For each drug category: male_adult, male_child, female_adult, female_child
    _cat_gender_age_raw = list(
        base_items.filter(drug__isnull=False, dispensing__patient__isnull=False)
        .values(
            'drug__category',
            'dispensing__patient__gender',
            'dispensing__patient__date_of_birth',
        )
        .annotate(cnt=Count('id'))
    )
    _cat_breakdown = {}
    for row in _cat_gender_age_raw:
        cat = row['drug__category'] or 'OTHER'
        sex = row['dispensing__patient__gender'] or ''
        dob = row['dispensing__patient__date_of_birth']
        cnt = row['cnt'] or 0
        if cat not in _cat_breakdown:
            _cat_breakdown[cat] = {'male_adult': 0, 'male_child': 0, 'female_adult': 0, 'female_child': 0, 'total': 0}
        is_child = False
        if dob:
            age = (month_start - dob).days // 365
            is_child = age < 15
        if sex == 'M':
            _cat_breakdown[cat]['male_child' if is_child else 'male_adult'] += cnt
        elif sex == 'F':
            _cat_breakdown[cat]['female_child' if is_child else 'female_adult'] += cnt
        _cat_breakdown[cat]['total'] += cnt

    from apps.pharmacy.models import DrugCategory as _DC
    _cat_lbl = dict(_DC.choices)
    cat_gender_age = []
    for cat_code, vals in sorted(_cat_breakdown.items(), key=lambda x: -x[1]['total']):
        cat_gender_age.append({
            'category': _cat_lbl.get(cat_code, cat_code),
            **vals,
        })

    # ── 12-Month Rolling Trend ──────────────────────────────────────────
    monthly_trend = []
    for i in range(11, -1, -1):
        _m = month - i
        _y = year
        while _m <= 0:
            _m += 12
            _y -= 1
        _ms = _date(_y, _m, 1)
        _me = _date(_y, _m, calendar.monthrange(_y, _m)[1])
        _mc = Dispensing.objects.filter(
            is_deleted=False,
            dispensed_at__date__gte=_ms,
            dispensed_at__date__lte=_me,
            status=DispensingStatus.DISPENSED,
        ).aggregate(c=Count('id'), r=Sum('total_amount'))
        monthly_trend.append({
            'label': _ms.strftime('%b %Y'),
            'count': _mc['c'] or 0,
            'revenue': float(_mc['r'] or 0),
        })
    monthly_trend_json = json.dumps({
        'labels': [m['label'] for m in monthly_trend],
        'counts': [m['count'] for m in monthly_trend],
        'revenue': [m['revenue'] for m in monthly_trend],
    })

    # Status doughnut
    status_json = json.dumps({
        'labels': ['Dispensed', 'Partial', 'Cancelled', 'Pending'],
        'data':   [dispensed_count, partial_count, cancelled_count,
                   total_dispensings - dispensed_count - partial_count - cancelled_count],
    })

    # Tier breakdown — join dispensings to same-day visits via patient
    try:
        from apps.patients.models import Visit
        from django.db.models import OuterRef, Subquery, CharField
        tier_subq = Visit.objects.filter(
            patient=OuterRef('patient'),
            visit_date__date=OuterRef('dispensed_at__date'),
            is_deleted=False,
        ).order_by('-visit_date').values('service_tier')[:1]
        tier_raw = (
            base.annotate(tier=Subquery(tier_subq, output_field=CharField()))
            .values('tier')
            .annotate(count=Count('id'))
        )
        tier_map = {row['tier'] or 'STANDARD': row['count'] for row in tier_raw}
        tier_stats = [
            {'label': 'Standard',   'key': 'STANDARD',   'color': '#0d6efd', 'count': tier_map.get('STANDARD', 0)},
            {'label': 'Fast Track', 'key': 'FAST_TRACK', 'color': '#fd7e14', 'count': tier_map.get('FAST_TRACK', 0)},
            {'label': 'VIP',        'key': 'VIP',        'color': '#6f42c1', 'count': tier_map.get('VIP', 0)},
        ]
        tier_json = json.dumps({
            'labels': [t['label'] for t in tier_stats],
            'data':   [t['count'] for t in tier_stats],
            'colors': [t['color'] for t in tier_stats],
        })
    except Exception:
        tier_stats = []
        tier_json  = json.dumps({'labels': [], 'data': [], 'colors': []})

    # ── WHO/JCI Pharmacy Indicators ──────────────────────────────────────────
    # WHO Core Drug Use Indicators (Management Sciences for Health / WHO 1993)
    # Use dispensings with at least one item (exclude empty PENDING)
    _rx_with_items = base.filter(items__isnull=False).distinct().count()
    avg_items_per_rx = round(total_items / _rx_with_items, 2) if _rx_with_items else 0

    # WHO/JCI item-level indicators — single aggregate (replaces 2 separate count queries)
    _item_agg = base_items.aggregate(
        antibiotic_items=Count('id', filter=Q(drug__category='ANTIBIOTIC')),
        controlled_items=Count('id', filter=Q(drug__is_controlled=True)),
    )
    antibiotic_items = _item_agg['antibiotic_items']
    antibiotic_rate = round(antibiotic_items / total_items * 100, 1) if total_items else 0
    controlled_items = _item_agg['controlled_items']
    controlled_rate = round(controlled_items / total_items * 100, 1) if total_items else 0

    # Rx rejection/decline rate (JCI quality indicator) — single aggregate
    try:
        from apps.prescriptions.models import DrugPrescription
        _rx_agg = DrugPrescription.objects.filter(
            is_deleted=False,
            prescription_date__gte=month_start,
            prescription_date__lte=month_end,
        ).aggregate(
            total_rx=Count('id'),
            declined_rx=Count('id', filter=Q(notes__icontains='Bought elsewhere')),
        )
        total_rx = _rx_agg['total_rx']
        declined_rx = _rx_agg['declined_rx']
        rx_decline_rate = round(declined_rx / total_rx * 100, 1) if total_rx else 0
    except Exception:
        total_rx = declined_rx = rx_decline_rate = 0

    # Verified + counseled — single aggregate (replaces 2 separate count queries)
    _qual_agg = base.aggregate(
        verified_count=Count('id', filter=Q(verified_by_pharmacist__isnull=False)),
        counseled_count=Count('id', filter=Q(counseling_given=True)),
    )
    verified_count = _qual_agg['verified_count']
    verification_rate = round(verified_count / dispensed_count * 100, 1) if dispensed_count else 0
    counseled_count = _qual_agg['counseled_count']
    counseling_rate = round(counseled_count / dispensed_count * 100, 1) if dispensed_count else 0

    # Revenue by tier
    try:
        from apps.patients.models import Visit
        from django.db.models import OuterRef, Subquery, CharField
        tier_rev_subq = Visit.objects.filter(
            patient=OuterRef('patient'),
            visit_date__date=OuterRef('dispensed_at__date'),
            is_deleted=False,
        ).order_by('-visit_date').values('service_tier')[:1]
        tier_revenue_raw = (
            base.filter(status=DispensingStatus.DISPENSED)
            .annotate(tier=Subquery(tier_rev_subq, output_field=CharField()))
            .values('tier')
            .annotate(rev=Sum('total_amount'))
        )
        tier_revenue_map = {r['tier'] or 'STANDARD': int(r['rev'] or 0) for r in tier_revenue_raw}
    except Exception:
        tier_revenue_map = {}

    for ts in tier_stats:
        ts['revenue'] = tier_revenue_map.get(ts['key'], 0)

    # Category breakdown (top 5 categories by qty)
    category_raw = list(
        base_items.filter(drug__isnull=False)
        .values('drug__category')
        .annotate(qty=Sum('quantity_dispensed'))
        .order_by('-qty')[:8]
    )
    from apps.pharmacy.models import DrugCategory
    _cat_labels = dict(DrugCategory.choices)
    category_stats = [
        {'label': _cat_labels.get(r['drug__category'], r['drug__category'] or 'Other'),
         'qty': r['qty'] or 0}
        for r in category_raw
    ] if category_raw else []
    category_json = json.dumps({
        'labels': [c['label'] for c in category_stats],
        'data':   [c['qty']   for c in category_stats],
    })

    # Low stock snapshot — single annotated query (not N+1 via needs_reorder property)
    _stock_q = Q(stock_items__is_deleted=False) & (Q(stock_items__expiry_date__gte=today) | Q(stock_items__expiry_date__isnull=True))
    low_stock_drugs = list(
        Drug.objects.filter(is_active=True, is_deleted=False)
        .annotate(_stock=Coalesce(Sum('stock_items__quantity_remaining', filter=_stock_q), Value(0, output_field=IntegerField())))
        .filter(_stock__lte=F('reorder_level'))
    )

    # ── WHO Additional Indicators ─────────────────────────────────────────
    # WHO indicator: % prescribed by generic name
    _generic_agg = base_items.aggregate(
        with_generic=Count('id', filter=Q(drug__generic_name__gt='')),
        total_items_ct=Count('id'),
    )
    generic_prescribing_rate = round(
        _generic_agg['with_generic'] / _generic_agg['total_items_ct'] * 100, 1
    ) if _generic_agg['total_items_ct'] else 0

    # WHO indicator: % encounters with injection
    injection_items = base_items.filter(drug__form='INJECTION').count()
    injection_rate = round(injection_items / total_items * 100, 1) if total_items else 0

    # WHO indicator: % from essential drug list (formulary drugs vs custom/non-formulary)
    formulary_items = base_items.filter(drug__isnull=False).count()
    formulary_rate = round(formulary_items / total_items * 100, 1) if total_items else 0

    # WHO indicator: generic substitution rate
    substitution_count = base_items.filter(substituted_for__gt='').count()
    substitution_rate = round(substitution_count / total_items * 100, 1) if total_items else 0

    # ── Inventory Health Indicators ───────────────────────────────────────
    from datetime import timedelta
    total_active_drugs = Drug.objects.filter(is_active=True, is_deleted=False).count()

    # Stockout rate: drugs with 0 stock / total active drugs
    _drugs_with_stock = Drug.objects.filter(
        is_active=True, is_deleted=False,
        stock_items__is_deleted=False,
        stock_items__quantity_remaining__gt=0,
    ).filter(
        Q(stock_items__expiry_date__gte=today) | Q(stock_items__expiry_date__isnull=True)
    ).distinct().count()
    stockout_count = total_active_drugs - _drugs_with_stock
    stockout_rate = round(stockout_count / total_active_drugs * 100, 1) if total_active_drugs else 0

    # Expiry/wastage: expired stock value in period
    expired_batches = DrugStock.objects.filter(
        is_deleted=False, expiry_date__gte=month_start, expiry_date__lte=month_end,
    )
    expired_value = expired_batches.aggregate(
        val=Sum(F('quantity_remaining') * F('purchase_price'))
    )['val'] or 0
    expired_units = expired_batches.aggregate(u=Sum('quantity_remaining'))['u'] or 0

    # Near-expiry (next 30 days) stock value at risk
    near_expiry_batches = DrugStock.objects.filter(
        is_deleted=False, quantity_remaining__gt=0,
        expiry_date__gt=today, expiry_date__lte=today + timedelta(days=30),
    )
    near_expiry_value = near_expiry_batches.aggregate(
        val=Sum(F('quantity_remaining') * F('purchase_price'))
    )['val'] or 0
    near_expiry_count = near_expiry_batches.count()

    # Total inventory value (at cost)
    total_inventory_value = DrugStock.objects.filter(
        is_deleted=False, quantity_remaining__gt=0,
    ).filter(
        Q(expiry_date__gte=today) | Q(expiry_date__isnull=True)
    ).aggregate(val=Sum(F('quantity_remaining') * F('purchase_price')))['val'] or 0

    # Stock turnover ratio: cost of goods dispensed / avg inventory value
    # COGS only from DISPENSED dispensings (not pending/partial/cancelled)
    cogs = base_items.filter(
        drug__isnull=False,
        dispensing__status=DispensingStatus.DISPENSED,
    ).aggregate(
        cost=Sum(F('quantity_dispensed') * F('drug__cost_price'))
    )['cost'] or 0
    stock_turnover = round(float(cogs) / float(total_inventory_value), 2) if total_inventory_value else 0

    # ── Financial KPIs ────────────────────────────────────────────────────
    avg_cost_per_rx = round(float(revenue) / dispensed_count, 0) if dispensed_count else 0

    # Gross margin: (revenue - COGS) / revenue
    gross_margin = round((float(revenue) - float(cogs)) / float(revenue) * 100, 1) if revenue else 0

    # Returns in period
    returns_in_period = DispensingReturn.objects.filter(
        is_deleted=False,
        created_at__date__gte=month_start,
        created_at__date__lte=month_end,
    )
    return_count = returns_in_period.count()
    return_qty = returns_in_period.aggregate(q=Sum('quantity_returned'))['q'] or 0
    return_rate = round(return_count / dispensed_count * 100, 1) if dispensed_count else 0

    # OTC vs Rx split
    otc_count = base.filter(is_otc=True).count()
    rx_count = base.filter(is_otc=False).count()
    otc_revenue = base.filter(is_otc=True, status=DispensingStatus.DISPENSED).aggregate(
        r=Sum('total_amount'))['r'] or 0
    rx_revenue = base.filter(is_otc=False, status=DispensingStatus.DISPENSED).aggregate(
        r=Sum('total_amount'))['r'] or 0

    # Revenue trend (daily, full month)
    _daily_rev_raw = dict(
        base.filter(status=DispensingStatus.DISPENSED)
        .annotate(day=TruncDate('dispensed_at'))
        .values_list('day').annotate(r=Sum('total_amount')).values_list('day', 'r')
    )
    daily_revenue = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        daily_revenue.append({'date': d.strftime('%d %b'), 'amount': float(_daily_rev_raw.get(d, 0))})
    revenue_json = json.dumps({
        'labels': [d['date'] for d in daily_revenue],
        'data': [d['amount'] for d in daily_revenue],
    })

    # ── Staff Productivity ────────────────────────────────────────────────
    staff_throughput = list(
        base.filter(status=DispensingStatus.DISPENSED)
        .values('dispensed_by__first_name', 'dispensed_by__last_name')
        .annotate(count=Count('id'), rev=Sum('total_amount'))
        .order_by('-count')[:10]
    )
    for s in staff_throughput:
        s['name'] = f"{s['dispensed_by__first_name']} {s['dispensed_by__last_name']}".strip()

    # Working days in month (Mon-Sat = 6 working days/week, exclude Sunday)
    _end = min(month_end, today)
    working_days = sum(1 for i in range((_end - month_start).days + 1)
                       if (month_start + timedelta(days=i)).weekday() < 6)
    working_days = max(working_days, 1)
    rx_per_day = round(dispensed_count / working_days, 1) if working_days else 0

    # Month nav
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1)  if month == 12 else (year, month + 1)
    is_current_month = (year == today.year and month == today.month)

    context = {
        'year': year, 'month': month,
        'month_name': _date(year, month, 1).strftime('%B %Y'),
        'is_current_month': is_current_month,
        'prev_year': prev_year, 'prev_month': prev_month,
        'next_year': next_year, 'next_month': next_month,
        'total_dispensings': total_dispensings,
        'total_items': total_items,
        'dispensed_count': dispensed_count,
        'partial_count': partial_count,
        'cancelled_count': cancelled_count,
        'completion_rate': completion_rate,
        'revenue': revenue,
        'top_drugs': top_drugs,
        'daily_json': daily_json,
        'gender_json': gender_json,
        'status_json': status_json,
        'male_count': male_count,
        'female_count': female_count,
        'low_stock_count': len(low_stock_drugs),
        'tier_stats': tier_stats,
        'tier_json': tier_json,
        'today': today,
        # WHO/JCI indicators
        'avg_items_per_rx': avg_items_per_rx,
        'antibiotic_rate': antibiotic_rate,
        'antibiotic_items': antibiotic_items,
        'controlled_rate': controlled_rate,
        'controlled_items': controlled_items,
        'total_rx': total_rx,
        'rx_decline_rate': rx_decline_rate,
        'verified_count': verified_count,
        'verification_rate': verification_rate,
        'counseled_count': counseled_count,
        'counseling_rate': counseling_rate,
        'category_stats': category_stats,
        'category_json': category_json,
        # WHO additional indicators
        'generic_prescribing_rate': generic_prescribing_rate,
        'injection_rate': injection_rate,
        'formulary_rate': formulary_rate,
        'substitution_rate': substitution_rate,
        'substitution_count': substitution_count,
        # Inventory health
        'total_active_drugs': total_active_drugs,
        'stockout_count': stockout_count,
        'stockout_rate': stockout_rate,
        'expired_value': expired_value,
        'expired_units': expired_units,
        'near_expiry_value': near_expiry_value,
        'near_expiry_count': near_expiry_count,
        'total_inventory_value': total_inventory_value,
        'stock_turnover': stock_turnover,
        'cogs': cogs,
        # Financial KPIs
        'avg_cost_per_rx': avg_cost_per_rx,
        'gross_margin': gross_margin,
        'return_count': return_count,
        'return_qty': return_qty,
        'return_rate': return_rate,
        'otc_count': otc_count,
        'rx_count': rx_count,
        'otc_revenue': otc_revenue,
        'rx_revenue': rx_revenue,
        'revenue_json': revenue_json,
        # Staff productivity
        'staff_throughput': staff_throughput,
        'rx_per_day': rx_per_day,
        'working_days': working_days,
        # WHO Demographics
        'age_counts': age_counts,
        'age_json': age_json,
        'paed_count': paed_count,
        'adult_count': adult_count,
        # Drug Category × Sex × Age audit table
        'cat_gender_age': cat_gender_age,
        # 12-month rolling trend
        'monthly_trend_json': monthly_trend_json,
    }
    if request.GET.get('pdf'):
        from apps.reports.views import render_pdf
        context['pdf_filename'] = 'pharmacy-stats.pdf'
        return render_pdf('pharmacy/stats_pdf.html', context)
    return render(request, 'pharmacy/stats.html', context)


@login_required
def pharmacy_stats_csv(request):
    """Export monthly pharmacy stats as CSV."""
    if not (request.user.is_pharmacist or request.user.is_medical_director
            or request.user.is_admin_staff or request.user.is_super_admin
            or request.user.is_ceo or request.user.is_admin_director
            or request.user.is_finance_director):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    import csv, calendar
    from datetime import date as _date

    today = timezone.localdate()
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        year, month = today.year, today.month

    month_start = _date(year, month, 1)
    month_end   = _date(year, month, calendar.monthrange(year, month)[1])

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="pharmacy-stats-{year}-{month:02d}.csv"'
    writer = csv.writer(response)

    # Header
    writer.writerow(['Pharmacy Statistics', f'{month_start.strftime("%B %Y")}'])
    writer.writerow([])

    # Dispensing summary
    base = Dispensing.objects.filter(
        is_deleted=False,
        dispensed_at__date__gte=month_start,
        dispensed_at__date__lte=month_end,
    )
    _agg = base.aggregate(
        total=Count('id'),
        dispensed=Count('id', filter=Q(status=DispensingStatus.DISPENSED)),
        partial=Count('id', filter=Q(status=DispensingStatus.PARTIAL)),
        cancelled=Count('id', filter=Q(status=DispensingStatus.CANCELLED)),
        revenue=Sum('total_amount', filter=Q(status=DispensingStatus.DISPENSED)),
    )
    writer.writerow(['Metric', 'Value'])
    writer.writerow(['Total Dispensings', _agg['total']])
    writer.writerow(['Dispensed', _agg['dispensed']])
    writer.writerow(['Partial', _agg['partial']])
    writer.writerow(['Cancelled', _agg['cancelled']])
    writer.writerow(['Revenue (FCFA)', _agg['revenue'] or 0])
    writer.writerow([])

    # Gender
    writer.writerow(['Gender', 'Count'])
    for row in base.values('patient__gender').annotate(c=Count('id')):
        writer.writerow([row['patient__gender'] or 'Unknown', row['c']])
    writer.writerow([])

    # Top drugs
    writer.writerow(['Top Drugs', 'Rx Count', 'Quantity'])
    items = DispensingItem.objects.filter(
        dispensing__is_deleted=False,
        dispensing__dispensed_at__date__gte=month_start,
        dispensing__dispensed_at__date__lte=month_end,
    )
    top = items.values('drug__name').annotate(
        cnt=Count('id'), qty=Sum('quantity_dispensed')
    ).order_by('-qty')[:30]
    for d in top:
        writer.writerow([d['drug__name'] or 'Non-formulary', d['cnt'], d['qty'] or 0])

    return response


@login_required
def drug_list(request):
    if not _can_access_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    q = request.GET.get('q', '')
    category = request.GET.get('category', '')
    drug_form = request.GET.get('form', '')
    status_filter = request.GET.get('status', '')   # active, inactive, controlled, low_stock, out_of_stock
    sort_by = request.GET.get('sort', 'name')       # name, -name, price, -price, category, stock

    drugs = Drug.objects.filter(is_deleted=False).only(
        'id', 'name', 'generic_name', 'brand_name', 'strength', 'form',
        'category', 'selling_price', 'reorder_level', 'is_active', 'is_controlled',
    )
    if q:
        drugs = drugs.filter(Q(name__icontains=q) | Q(generic_name__icontains=q) | Q(brand_name__icontains=q))
    if category:
        drugs = drugs.filter(category=category)
    if drug_form:
        drugs = drugs.filter(form=drug_form)

    # Status filters
    today = timezone.localdate()
    if status_filter == 'active':
        drugs = drugs.filter(is_active=True)
    elif status_filter == 'inactive':
        drugs = drugs.filter(is_active=False)
    elif status_filter == 'controlled':
        drugs = drugs.filter(is_controlled=True)
    elif status_filter == 'low_stock':
        _stock_q = Q(stock_items__is_deleted=False, stock_items__quantity_remaining__gt=0) & (Q(stock_items__expiry_date__gte=today) | Q(stock_items__expiry_date__isnull=True))
        drugs = drugs.annotate(
            _stock=Coalesce(Sum('stock_items__quantity_remaining', filter=_stock_q), Value(0, output_field=IntegerField()))
        ).filter(_stock__gt=0, _stock__lte=F('reorder_level'))
    elif status_filter == 'out_of_stock':
        _stock_q = Q(stock_items__is_deleted=False, stock_items__quantity_remaining__gt=0) & (Q(stock_items__expiry_date__gte=today) | Q(stock_items__expiry_date__isnull=True))
        drugs = drugs.annotate(
            _stock=Coalesce(Sum('stock_items__quantity_remaining', filter=_stock_q), Value(0, output_field=IntegerField()))
        ).filter(_stock=0)

    # Sorting
    SORT_MAP = {
        'name': 'name', '-name': '-name',
        'price': 'selling_price', '-price': '-selling_price',
        'category': 'category', '-category': '-category',
    }
    order = SORT_MAP.get(sort_by, 'name')
    drugs = drugs.order_by(order)

    # Paginate — 50 per page
    from django.core.paginator import Paginator
    paginator = Paginator(drugs, 50)
    page = paginator.get_page(request.GET.get('page', 1))
    from .models import DrugCategory, DrugForm as DrugFormChoices
    return render(request, 'pharmacy/drug_list.html', {
        'drugs': page, 'search': q, 'category': category, 'drug_form': drug_form,
        'status_filter': status_filter, 'sort_by': sort_by,
        'categories': DrugCategory.choices, 'drug_forms': DrugFormChoices.choices,
        'paginator': paginator, 'page_obj': page,
    })


@login_required
def drug_detail(request, drug_id):
    if not _can_access_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    drug = get_object_or_404(Drug, id=drug_id, is_deleted=False)
    stocks = drug.stock_items.filter(is_deleted=False).order_by('expiry_date')
    dispensings = DispensingItem.objects.filter(drug=drug).select_related(
        'dispensing', 'dispensing__patient'
    ).order_by('-dispensing__dispensed_at')[:20]
    return render(request, 'pharmacy/drug_detail.html', {
        'drug': drug, 'stocks': stocks, 'dispensings': dispensings
    })


@login_required
def drug_create(request):
    if not _can_access_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    form = DrugCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        drug = form.save(commit=False)
        # If user can't edit prices, strip any price changes from the form
        if not _can_edit_drug_prices(request.user):
            drug.cost_price = 0
            drug.selling_price = 0
            drug.price_express = 0
            drug.price_vip = 0
            drug.price_executive_vip = 0
            drug.price_staff = 0
            drug.price_outreach = 0
            drug.insurance_markup_pct = 0
        drug.created_by = request.user
        drug.save()
        messages.success(request, f'{drug.name} added to formulary.')
        return redirect('pharmacy:drug_detail', drug_id=drug.id)
    return render(request, 'pharmacy/drug_form.html', {
        'form': form, 'action': 'Add New Drug',
        'can_edit_prices': _can_edit_drug_prices(request.user),
    })


@login_required
def drug_edit(request, drug_id):
    if not _can_access_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    drug = get_object_or_404(Drug, id=drug_id, is_deleted=False)
    _price_fields = [
        'cost_price', 'selling_price', 'price_express', 'price_vip',
        'price_executive_vip', 'price_staff', 'price_outreach', 'insurance_markup_pct',
    ]
    # Save original prices to revert if user can't edit prices
    _orig_prices = {f: getattr(drug, f) for f in _price_fields}
    form = DrugCreateForm(request.POST or None, instance=drug)
    if request.method == 'POST' and form.is_valid():
        updated = form.save(commit=False)
        # If user can't edit prices, revert price fields to originals
        if not _can_edit_drug_prices(request.user):
            for f in _price_fields:
                setattr(updated, f, _orig_prices[f])
        updated.save()
        messages.success(request, f'{drug.name} updated.')
        return redirect('pharmacy:drug_detail', drug_id=drug.id)
    return render(request, 'pharmacy/drug_form.html', {
        'form': form, 'drug': drug, 'action': f'Edit: {drug.name}',
        'can_edit_prices': _can_edit_drug_prices(request.user),
    })


@login_required
def add_stock(request, drug_id):
    if not _can_access_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    drug = get_object_or_404(Drug, id=drug_id, is_deleted=False)
    form = AddStockForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save(drug=drug, user=request.user)
        messages.success(request, f'Stock added for {drug.name}.')
        return redirect('pharmacy:drug_detail', drug_id=drug.id)
    return render(request, 'pharmacy/add_stock.html', {'drug': drug, 'form': form})


@login_required
def dispense(request):
    """Create a new dispensing record"""
    if not _can_access_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    if request.method == 'POST':
        patient_id = request.POST.get('patient_id')
        if not patient_id:
            messages.error(request, 'Please select a patient.')
            return redirect('pharmacy:dispense')
        patient = get_object_or_404(Patient, id=patient_id, is_deleted=False)
        prescription_id = request.POST.get('prescription_id')
        prescription = None
        if prescription_id:
            prescription = DrugPrescription.objects.filter(id=prescription_id).first()

        dispensing = Dispensing.objects.create(
            patient=patient,
            prescription=prescription,
            dispensed_by=request.user,
            notes=request.POST.get('notes', ''),
            created_by=request.user,
        )
        messages.success(request, f'Dispensing record {dispensing.dispensing_number} created. Add items below.')
        return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)

    patient_id = request.GET.get('patient')
    patient = None
    prescription = None
    if patient_id:
        patient = Patient.objects.filter(id=patient_id, is_deleted=False).first()
        if patient:
            prescription = DrugPrescription.objects.filter(
                patient=patient, is_deleted=False
            ).order_by('-created_at').first()

    return render(request, 'pharmacy/dispense.html', {
        'patient': patient, 'prescription': prescription
    })


@login_required
def add_dispensing_item(request, dispensing_id):
    """Add a drug item to an open dispensing record."""
    dispensing = get_object_or_404(Dispensing, id=dispensing_id, is_deleted=False)
    if not (request.user.can_dispense_pharmacy() or request.user == dispensing.dispensed_by):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    if dispensing.status not in (DispensingStatus.PENDING, DispensingStatus.PARTIAL):
        messages.error(request, 'Cannot add items to a completed or cancelled dispensing.')
        return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)

    drug_id = request.POST.get('drug') if request.method == 'POST' else None
    form = DispensingItemForm(request.POST or None, drug_id=drug_id)

    if request.method == 'POST' and form.is_valid():
        drug = form.cleaned_data['drug']
        qty = form.cleaned_data['quantity_dispensed']
        unit_price = form.cleaned_data['unit_price']
        batch = form.cleaned_data.get('stock_batch')

        # If no batch specified, use FEFO (first to expire)
        if not batch:
            batch = DrugStock.objects.filter(
                drug=drug, is_deleted=False, quantity_remaining__gt=0,
            ).filter(
                Q(expiry_date__gte=timezone.localdate()) | Q(expiry_date__isnull=True)
            ).order_by('expiry_date').first()

        item = DispensingItem.objects.create(
            dispensing=dispensing,
            drug=drug,
            stock_batch=batch,
            quantity_dispensed=qty,
            unit_price=unit_price,
            instructions=form.cleaned_data.get('instructions', ''),
        )

        # Update dispensing totals
        total = DispensingItem.objects.filter(dispensing=dispensing).aggregate(t=Sum('subtotal'))['t'] or 0
        dispensing.total_amount = total
        dispensing.status = DispensingStatus.PENDING
        dispensing.save(update_fields=['total_amount', 'status'])

        messages.success(request, f'{drug.name} x{qty} added.')
        return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)

    # Validation failed — show errors via messages
    if request.method == 'POST' and not form.is_valid():
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f'{error}')
    return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)


@login_required
def drug_search_ajax(request):
    """Search drugs by name/generic name — returns JSON for autocomplete."""
    q = request.GET.get('q', '').strip()
    base = Drug.objects.filter(is_active=True, is_deleted=False)
    if q:
        drugs = base.filter(
            Q(name__icontains=q) | Q(generic_name__icontains=q) | Q(brand_name__icontains=q)
        )
        # Fallback: if no exact match, try each word individually (AND)
        if not drugs.exists():
            words = q.split()
            if len(words) > 1:
                qs = base
                for w in words:
                    qs = qs.filter(
                        Q(name__icontains=w) | Q(generic_name__icontains=w) | Q(brand_name__icontains=w)
                    )
                drugs = qs
            # Final fallback: try just the first word
            if not drugs.exists() and len(words) >= 1:
                drugs = base.filter(
                    Q(name__icontains=words[0]) | Q(generic_name__icontains=words[0]) | Q(brand_name__icontains=words[0])
                )
    else:
        drugs = base
    drugs = drugs.order_by('name')[:25]
    tier = request.GET.get('tier', 'STANDARD')
    billing_type = request.GET.get('billing_type', 'SELF_PAY')
    return JsonResponse({'drugs': [
        {
            'id': str(d.id),
            'name': d.name,
            'generic': d.generic_name,
            'strength': d.strength or '',
            'form': d.get_form_display(),
            'stock': d.current_stock,
            'price': str(d.get_tier_price(tier=tier, billing_type=billing_type)),
            'low': d.needs_reorder,
            'barcode': d.barcode or '',
        }
        for d in drugs
    ]})


@login_required
def barcode_lookup_ajax(request):
    """Lookup a drug by barcode — returns same format as drug_search_ajax for a single match."""
    code = request.GET.get('code', '').strip()
    if not code:
        return JsonResponse({'error': 'No barcode provided'}, status=400)
    drug = Drug.objects.filter(barcode=code, is_active=True, is_deleted=False).first()
    if not drug:
        return JsonResponse({'error': 'No drug found for this barcode'}, status=404)
    tier = request.GET.get('tier', 'STANDARD')
    billing_type = request.GET.get('billing_type', 'SELF_PAY')
    return JsonResponse({'drug': {
        'id': str(drug.id),
        'name': drug.name,
        'generic': drug.generic_name,
        'strength': drug.strength or '',
        'form': drug.get_form_display(),
        'stock': drug.current_stock,
        'price': str(drug.get_tier_price(tier=tier, billing_type=billing_type)),
        'low': drug.needs_reorder,
        'barcode': drug.barcode or '',
    }})


@login_required
def add_dispensing_item_ajax(request, dispensing_id):
    """AJAX: add a drug item to dispensing, return updated totals and interaction check."""
    dispensing = get_object_or_404(Dispensing, id=dispensing_id, is_deleted=False)
    if not (request.user.can_dispense_pharmacy() or request.user == dispensing.dispensed_by):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    if dispensing.status not in (DispensingStatus.PENDING, DispensingStatus.PARTIAL):
        return JsonResponse({'error': 'Cannot add items to a completed dispensing'}, status=400)

    drug_id = request.POST.get('drug_id', '').strip()
    try:
        qty = int(request.POST.get('qty', 1))
        from decimal import Decimal, InvalidOperation
        unit_price = Decimal(request.POST.get('unit_price', '0'))
    except (ValueError, InvalidOperation):
        return JsonResponse({'error': 'Invalid quantity or price'}, status=400)

    drug = Drug.objects.filter(id=drug_id, is_active=True, is_deleted=False).first()
    if not drug:
        return JsonResponse({'error': 'Drug not found'}, status=404)
    if qty <= 0:
        return JsonResponse({'error': 'Quantity must be at least 1'}, status=400)

    batch_id = request.POST.get('batch_id', '').strip()
    batch = None
    if batch_id:
        batch = DrugStock.objects.filter(id=batch_id, is_deleted=False).first()
    if not batch:
        batch = DrugStock.objects.filter(
            drug=drug, is_deleted=False, quantity_remaining__gt=0,
        ).filter(
            Q(expiry_date__gte=timezone.localdate()) | Q(expiry_date__isnull=True)
        ).order_by('expiry_date').first()

    item = DispensingItem.objects.create(
        dispensing=dispensing,
        drug=drug,
        stock_batch=batch,
        quantity_dispensed=qty,
        unit_price=unit_price,
        instructions=request.POST.get('instructions', '').strip(),
    )

    # Auto-create controlled drug register entry for narcotics
    if drug.is_controlled:
        from decimal import Decimal as D
        balance_before = ControlledDrugEntry.objects.filter(
            drug=drug
        ).order_by('-entry_date').values_list('balance_after', flat=True).first() or D('0')
        ControlledDrugEntry.objects.create(
            drug=drug,
            batch=batch,
            entry_type=ControlledDrugEntryType.DISPENSE,
            quantity=D(str(qty)),
            balance_before=balance_before,
            balance_after=balance_before - D(str(qty)),
            patient=dispensing.patient,
            dispensing=dispensing,
            performed_by=request.user,
            notes=f'Auto-created from dispensing {dispensing.dispensing_number}',
        )

    total = DispensingItem.objects.filter(dispensing=dispensing).aggregate(t=Sum('subtotal'))['t'] or 0
    dispensing.total_amount = total
    dispensing.status = DispensingStatus.PENDING
    dispensing.save(update_fields=['total_amount', 'status'])

    drug_names = list(DispensingItem.objects.filter(dispensing=dispensing).values_list('drug__name', flat=True))
    interactions = []
    try:
        from apps.prescriptions.models import DrugInteraction
        interactions = [
            {'severity': ix.get_severity_display(), 'drug_a': ix.drug_a, 'drug_b': ix.drug_b, 'description': ix.description}
            for ix in DrugInteraction.find_interactions(drug_names)
        ]
    except Exception:
        pass

    return JsonResponse({
        'success': True,
        'item': {
            'id': str(item.pk),
            'drug_name': drug.name,
            'strength': drug.strength or '',
            'form': drug.get_form_display(),
            'batch': batch.batch_number if batch else 'N/A',
            'expiry': batch.expiry_date.strftime('%b %Y') if batch else '',
            'qty': qty,
            'unit_price': str(unit_price),
            'subtotal': str(item.subtotal),
            'instructions': item.instructions,
        },
        'total': str(total),
        'interactions': interactions,
        'is_controlled': drug.is_controlled,
        'no_stock': batch is None,
    })


@login_required
def add_manual_item_ajax(request, dispensing_id):
    """AJAX: add a non-formulary (Others) drug item to dispensing by name + price."""
    dispensing = get_object_or_404(Dispensing, id=dispensing_id, is_deleted=False)
    if not (request.user.can_dispense_pharmacy() or request.user == dispensing.dispensed_by):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    if dispensing.status not in (DispensingStatus.PENDING, DispensingStatus.PARTIAL):
        return JsonResponse({'error': 'Cannot add items to a completed dispensing'}, status=400)

    drug_name = request.POST.get('drug_name', '').strip()
    if not drug_name:
        return JsonResponse({'error': 'Drug name is required'}, status=400)
    try:
        qty = int(request.POST.get('qty', 1))
        from decimal import Decimal, InvalidOperation
        unit_price = Decimal(request.POST.get('unit_price', '0'))
    except (ValueError, InvalidOperation):
        return JsonResponse({'error': 'Invalid quantity or price'}, status=400)
    if qty <= 0:
        return JsonResponse({'error': 'Quantity must be at least 1'}, status=400)

    item = DispensingItem.objects.create(
        dispensing=dispensing,
        drug=None,
        custom_drug_name=drug_name,
        quantity_dispensed=qty,
        unit_price=unit_price,
        instructions=request.POST.get('instructions', '').strip(),
    )

    total = DispensingItem.objects.filter(dispensing=dispensing).aggregate(t=Sum('subtotal'))['t'] or 0
    dispensing.total_amount = total
    dispensing.status = DispensingStatus.PENDING
    dispensing.save(update_fields=['total_amount', 'status'])

    return JsonResponse({
        'success': True,
        'item': {
            'id': str(item.pk),
            'drug_name': drug_name,
            'strength': '',
            'form': 'Other',
            'batch': '—',
            'expiry': '',
            'qty': qty,
            'unit_price': str(unit_price),
            'subtotal': str(item.subtotal),
        },
        'new_total': str(total),
        'interactions': [],
    })


@login_required
def remove_dispensing_item_ajax(request, dispensing_id, item_id):
    """AJAX: remove a drug item from an open dispensing and restore stock."""
    dispensing = get_object_or_404(Dispensing, id=dispensing_id, is_deleted=False)
    if dispensing.status not in (DispensingStatus.PENDING, DispensingStatus.PARTIAL):
        return JsonResponse({'error': 'Cannot modify a completed dispensing'}, status=400)
    item = get_object_or_404(DispensingItem, id=item_id, dispensing=dispensing)
    if item.stock_batch:
        item.stock_batch.quantity_remaining += item.quantity_dispensed
        item.stock_batch.save(update_fields=['quantity_remaining'])
    item.delete()
    total = DispensingItem.objects.filter(dispensing=dispensing).aggregate(t=Sum('subtotal'))['t'] or 0
    dispensing.total_amount = total
    if not DispensingItem.objects.filter(dispensing=dispensing).exists():
        dispensing.status = DispensingStatus.PENDING
    dispensing.save(update_fields=['total_amount', 'status'])
    return JsonResponse({'success': True, 'total': str(total)})


@login_required
def edit_dispensing_item_ajax(request, dispensing_id, item_id):
    """AJAX POST: edit qty, unit_price, or instructions on an open dispensing item."""
    dispensing = get_object_or_404(Dispensing, id=dispensing_id, is_deleted=False)
    if not (request.user.can_dispense_pharmacy() or request.user == dispensing.dispensed_by):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    if dispensing.status not in (DispensingStatus.PENDING, DispensingStatus.PARTIAL):
        return JsonResponse({'error': 'Cannot modify a completed dispensing'}, status=400)
    item = get_object_or_404(DispensingItem, id=item_id, dispensing=dispensing)

    from decimal import Decimal, InvalidOperation
    new_qty = request.POST.get('qty')
    new_price = request.POST.get('unit_price')
    new_instr = request.POST.get('instructions')

    # ── Audit trail: capture old values before modification ────────────────
    old_qty = item.quantity_dispensed
    old_price = item.unit_price
    old_instr = item.instructions
    _changes = []

    if new_qty is not None:
        try:
            new_qty = int(new_qty)
            if new_qty < 1:
                return JsonResponse({'error': 'Quantity must be at least 1'}, status=400)
        except ValueError:
            return JsonResponse({'error': 'Invalid quantity'}, status=400)
        # Adjust stock: restore old qty, deduct new qty
        if item.stock_batch:
            item.stock_batch.quantity_remaining += old_qty
            if new_qty > item.stock_batch.quantity_remaining:
                item.stock_batch.quantity_remaining -= old_qty  # revert
                return JsonResponse({'error': f'Only {item.stock_batch.quantity_remaining + old_qty - old_qty} in stock'}, status=400)
            item.stock_batch.quantity_remaining -= new_qty
            item.stock_batch.save(update_fields=['quantity_remaining'])
        item.quantity_dispensed = new_qty

    if new_price is not None:
        try:
            item.unit_price = Decimal(new_price)
        except (InvalidOperation, ValueError):
            return JsonResponse({'error': 'Invalid price'}, status=400)

    if new_instr is not None:
        item.instructions = new_instr.strip()

    item.save()

    # ── Audit trail: log what changed ──────────────────────────────────────
    if new_qty is not None and int(new_qty) != old_qty:
        _changes.append(f'qty: {old_qty} → {new_qty}')
    if new_price is not None and item.unit_price != old_price:
        _changes.append(f'price: {old_price} → {item.unit_price}')
    if new_instr is not None and item.instructions != old_instr:
        _changes.append(f'instructions changed')
    if _changes:
        try:
            from apps.accounts.models import UserAuditLog
            UserAuditLog.objects.create(
                user=request.user,
                action=UserAuditLog.Action.UPDATE_RECORD,
                resource_type='DispensingItem',
                resource_id=str(item.pk),
                details=(
                    f'Edited dispensing item: {item.drug.name if item.drug else "unknown"} '
                    f'on Rx#{dispensing.id} — {", ".join(_changes)}'
                ),
                ip_address=request.META.get('REMOTE_ADDR', ''),
            )
        except Exception:
            pass  # Don't block on audit failure

    total = DispensingItem.objects.filter(dispensing=dispensing).aggregate(t=Sum('subtotal'))['t'] or 0
    dispensing.total_amount = total
    dispensing.save(update_fields=['total_amount'])

    return JsonResponse({
        'success': True,
        'item': {
            'id': str(item.pk),
            'qty': item.quantity_dispensed,
            'unit_price': str(item.unit_price),
            'subtotal': str(item.subtotal),
            'instructions': item.instructions,
        },
        'total': str(total),
        'item_count': dispensing.items.count(),
    })


@login_required
def drug_stock_ajax(request):
    """Return available stock batches for a drug as JSON (for dynamic form).
    Accepts optional ?tier= and ?billing_type= to return tier-resolved price."""
    drug_id = request.GET.get('drug_id')
    if not drug_id:
        return JsonResponse({'batches': [], 'selling_price': 0})
    drug = Drug.objects.filter(id=drug_id, is_deleted=False).first()
    if not drug:
        return JsonResponse({'batches': [], 'selling_price': 0})
    batches = DrugStock.objects.filter(
        drug=drug, is_deleted=False, quantity_remaining__gt=0,
    ).filter(
        Q(expiry_date__gte=timezone.localdate()) | Q(expiry_date__isnull=True)
    ).order_by('expiry_date')

    # Tier-resolved price
    tier = request.GET.get('tier', 'STANDARD')
    billing_type = request.GET.get('billing_type', 'SELF_PAY')
    resolved_price = drug.get_tier_price(tier=tier, billing_type=billing_type)

    return JsonResponse({
        'selling_price': str(resolved_price),
        'standard_price': str(drug.selling_price),
        'tier': tier,
        'billing_type': billing_type,
        'current_stock': drug.current_stock,
        'batches': [
            {
                'id': str(b.id),
                'label': f'Batch {b.batch_number} — Exp: {b.expiry_date} ({b.quantity_remaining} left)',
                'qty_remaining': b.quantity_remaining,
            }
            for b in batches
        ],
    })


def _get_dispensing_tier_info(dispensing):
    """Resolve service_tier and billing_type from the patient's active visit.
    Walk-in OTC: use dispensing.service_tier if set (pharmacist picks on OTC form)."""
    tier, billing_type, insurance_copay = 'STANDARD', 'SELF_PAY', None
    # Walk-in tier override (set on OTC form)
    if dispensing.service_tier:
        return dispensing.service_tier, billing_type, insurance_copay
    if dispensing.patient:
        try:
            from apps.patients.models import Visit
            visit = Visit.objects.filter(
                patient=dispensing.patient, is_deleted=False,
            ).order_by('-visit_date').first()
            if visit:
                tier = visit.service_tier or 'STANDARD'
                billing_type = visit.billing_type or 'SELF_PAY'
                # Look up insurance copay if insured
                if billing_type in ('INSURANCE', 'HMO'):
                    try:
                        from apps.hmo.models import InsuredMember
                        member = InsuredMember.objects.filter(
                            patient=dispensing.patient, is_active=True
                        ).select_related('scheme').first()
                        if member:
                            insurance_copay = float(member.copay_pct)
                    except Exception:
                        pass
        except Exception:
            pass
    return tier, billing_type, insurance_copay


@login_required
def dispensing_detail(request, dispensing_id):
    if not _can_access_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    dispensing = get_object_or_404(
        Dispensing.objects.prefetch_related('items__drug', 'items__stock_batch'),
        id=dispensing_id, is_deleted=False
    )
    tier, billing_type, insurance_copay = _get_dispensing_tier_info(dispensing)
    ctx = {
        'dispensing': dispensing,
        'patient_tier': tier,
        'billing_type': billing_type,
        'insurance_copay': insurance_copay,
    }
    if dispensing.status in (DispensingStatus.PENDING, DispensingStatus.PARTIAL):
        ctx['available_drugs'] = Drug.objects.filter(
            is_active=True, is_deleted=False
        ).order_by('name')
    # Drug interaction check
    try:
        from apps.prescriptions.models import DrugInteraction
        drug_names = [item.display_name for item in dispensing.items.all()]
        ctx['drug_interactions'] = DrugInteraction.find_interactions(drug_names)
    except Exception:
        ctx['drug_interactions'] = []
    return render(request, 'pharmacy/dispensing_detail.html', ctx)


@login_required
@require_POST
def confirm_dispensing(request, dispensing_id):
    """
    Step 1 of 2-step flow: pharmacist confirms Rx items → invoice created → patient sent to cashier.
    Dispensing status moves to CONFIRMED. Patient visit moves to BILLING.
    After cashier collects payment, pharmacist clicks 'Dispense' to hand out drugs.
    """
    if not request.user.can_dispense_pharmacy():
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    dispensing = get_object_or_404(Dispensing, id=dispensing_id, is_deleted=False)
    if dispensing.status not in (DispensingStatus.PENDING, DispensingStatus.PARTIAL):
        messages.error(request, 'Cannot confirm a dispensing that is already confirmed, dispensed, or cancelled.')
        return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)

    if not dispensing.items.exists():
        messages.error(request, 'Add at least one item before confirming.')
        return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)

    # Walk-in OTC sales cannot use the 2-step confirm→cashier flow — redirect
    # to the single-step complete_dispensing flow instead.
    if not dispensing.patient:
        messages.info(request, 'Walk-in sales use direct payment. Use the "Collect Payment & Dispense" button.')
        return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)

    # Bill the dispensing items to the patient's invoice
    from apps.billing.utils import bill_dispensing
    try:
        bill_dispensing(dispensing, created_by=request.user)
    except Exception as e:
        messages.error(request, f'Billing failed: {e}')
        return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)

    # Move dispensing to CONFIRMED
    dispensing.status = DispensingStatus.CONFIRMED
    dispensing.save(update_fields=['status'])

    # Move the patient's visit to BILLING so the cashier sees them
    try:
        from apps.patients.models import Visit
        visit = Visit.objects.filter(
            patient=dispensing.patient,
            status='PHARMACY',
            is_deleted=False,
        ).order_by('-visit_date').first()
        if visit:
            visit.status = 'BILLING'
            visit.save(update_fields=['status', 'updated_at'])
    except Exception:
        pass

    messages.success(
        request,
        f'Prescription confirmed and billed — {dispensing.dispensing_number}. '
        f'Patient sent to cashier for payment.'
    )
    return redirect('pharmacy:dashboard')


@login_required
@require_POST
def finalize_dispensing(request, dispensing_id):
    """
    Step 2: after cashier has collected payment, pharmacist hands out drugs.
    Marks dispensing as DISPENSED and marks the linked Rx as dispensed.
    """
    if not request.user.can_dispense_pharmacy():
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    dispensing = get_object_or_404(Dispensing, id=dispensing_id, is_deleted=False)
    if dispensing.status != DispensingStatus.CONFIRMED:
        messages.error(request, 'Only CONFIRMED dispensings can be finalized.')
        return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)

    dispensing.status = DispensingStatus.DISPENSED
    dispensing.save(update_fields=['status'])

    # Mark linked Rx as dispensed
    if dispensing.prescription and not dispensing.prescription.is_dispensed:
        dispensing.prescription.is_dispensed = True
        dispensing.prescription.dispensed_by = request.user
        dispensing.prescription.dispensed_at = timezone.now()
        dispensing.prescription.save(update_fields=['is_dispensed', 'dispensed_by', 'dispensed_at'])

    messages.success(
        request,
        f'Drugs dispensed — {dispensing.dispensing_number} complete.'
    )
    return redirect('pharmacy:dispensing_receipt', dispensing_id=dispensing.id)


@login_required
@require_POST
def complete_dispensing(request, dispensing_id):
    """
    Collect payment at pharmacy counter and dispense drugs in one step.
    Pharmacist enters payment method + amount → invoice created → payment recorded → drugs dispensed.
    (Legacy single-step flow — still available for OTC sales and when pharmacist collects directly.)
    """
    if not request.user.can_dispense_pharmacy():
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    dispensing = get_object_or_404(Dispensing, id=dispensing_id, is_deleted=False)

    if dispensing.status not in (DispensingStatus.PENDING, DispensingStatus.PARTIAL):
        messages.error(request, 'Cannot complete a dispensing that is already dispensed or cancelled.')
        return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)

    # Auto-open a pharmacy cash desk shift if the pharmacist doesn't have one yet today
    from apps.accounts.models import UserRole as _UR
    if request.user.role == _UR.PHARMACIST:
        from apps.billing.models import CashierShift, ShiftStatus
        from decimal import Decimal as _D
        _today = timezone.localdate()
        _open_shift = CashierShift.objects.filter(
            cashier=request.user, shift_date=_today,
            status=ShiftStatus.OPEN, is_deleted=False,
        ).first()
        if not _open_shift:
            CashierShift.objects.create(
                cashier=request.user,
                shift_date=_today,
                opening_cash=_D('0'),
                status=ShiftStatus.OPEN,
                created_by=request.user,
            )

    from decimal import Decimal, InvalidOperation
    from apps.billing.models import Payment, PaymentMethod, Invoice, InvoiceStatus
    from apps.billing.utils import bill_dispensing, get_or_create_today_invoice

    payment_method = request.POST.get('payment_method', PaymentMethod.CASH)
    amount_str = request.POST.get('amount', '').strip()

    # Save discount fields
    try:
        disc_pct = Decimal(request.POST.get('discount_pct', '0').strip() or '0')
        disc_pct = max(Decimal('0'), min(disc_pct, Decimal('100')))
    except InvalidOperation:
        disc_pct = Decimal('0')
    try:
        disc_flat = Decimal(request.POST.get('discount', '0').strip() or '0')
        disc_flat = max(Decimal('0'), disc_flat)
    except InvalidOperation:
        disc_flat = Decimal('0')

    dispensing.discount_pct = disc_pct
    dispensing.discount = disc_flat
    dispensing.save(update_fields=['discount_pct', 'discount'])

    net_amount = dispensing.net_amount

    try:
        amount = Decimal(amount_str) if amount_str else net_amount
    except InvalidOperation:
        messages.error(request, 'Invalid payment amount.')
        return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)

    if amount <= 0:
        messages.error(request, 'Payment amount must be greater than zero.')
        return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)

    # Guard: pharmacy counter always collects full payment — no partial dispensing allowed
    if amount < net_amount:
        messages.error(
            request,
            f'Amount entered ({int(amount):,} FCFA) is less than the net total '
            f'({int(net_amount):,} FCFA). '
            'Full payment is required before drugs can be dispensed.'
        )
        return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)

    # Step 1: Bill — add dispensing items to patient invoice
    # Walk-in OTC sales (no patient) skip the formal invoice pipeline and
    # record payment directly on the Dispensing record.
    if dispensing.patient:
        try:
            invoice = get_or_create_today_invoice(dispensing.patient, created_by=request.user)
            bill_dispensing(dispensing, created_by=request.user)
        except Exception as e:
            messages.error(request, f'Billing failed: {e}')
            return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)

        # Step 2: Record payment at pharmacy counter
        Payment.objects.create(
            invoice=invoice,
            payment_method=payment_method,
            amount=amount,
            reference=request.POST.get('reference', '').strip(),
            received_by=request.user,
            created_by=request.user,
        )
    else:
        # Walk-in OTC — no patient account, no invoice. Payment tracked on
        # the Dispensing record itself (amount_paid field).
        pass

    # Step 3: Mark dispensing as DISPENSED and record amount paid
    dispensing.status = DispensingStatus.DISPENSED
    dispensing.amount_paid = amount
    dispensing.save(update_fields=['status', 'amount_paid'])

    # Step 3b: Mark the linked prescription as dispensed so it leaves the pending queue
    if dispensing.prescription and not dispensing.prescription.is_dispensed:
        dispensing.prescription.is_dispensed = True
        dispensing.prescription.dispensed_by = request.user
        dispensing.prescription.dispensed_at = timezone.now()
        dispensing.prescription.save(update_fields=['is_dispensed', 'dispensed_by', 'dispensed_at'])

    # Step 4: Move patient visit from PHARMACY → BILLING so cashier can
    # confirm any remaining outstanding items. Skip for walk-in (no visit).
    if dispensing.patient:
        try:
            from apps.patients.models import Visit
            visit = Visit.objects.filter(
                patient=dispensing.patient,
                status='PHARMACY',
                is_deleted=False,
            ).order_by('-visit_date').first()
            if visit:
                visit.status = 'BILLING'
                visit.save(update_fields=['status', 'updated_at'])
        except Exception:
            pass

    messages.success(
        request,
        f'Payment of {int(amount):,} FCFA collected. '
        f'Drugs dispensed — {dispensing.dispensing_number} complete.'
    )
    # Redirect to receipt page — auto-prints and then returns to pharmacy dashboard
    return redirect('pharmacy:dispensing_receipt', dispensing_id=dispensing.id)


@login_required
@require_POST
def cancel_dispensing(request, dispensing_id):
    """
    Cancel a PENDING or PARTIAL dispensing (e.g. patient changed mind before payment).
    Restores any reserved stock, marks the dispensing CANCELLED.
    Only pharmacists and admins can cancel.
    """
    if not request.user.can_dispense_pharmacy():
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    dispensing = get_object_or_404(Dispensing, id=dispensing_id, is_deleted=False)

    if dispensing.status not in (DispensingStatus.PENDING, DispensingStatus.PARTIAL):
        messages.error(request, 'Only pending or partial dispensings can be cancelled.')
        return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)

    reason = request.POST.get('reason', '').strip() or 'Cancelled by pharmacist'

    # Restore stock for each dispensed item (FEFO — restore to original batch)
    for item in dispensing.items.select_related('stock_batch').all():
        if item.stock_batch:
            item.stock_batch.quantity_remaining += item.quantity_dispensed
            item.stock_batch.save(update_fields=['quantity_remaining'])

    dispensing.status = DispensingStatus.CANCELLED
    dispensing.notes = f'[CANCELLED] {reason}\n{dispensing.notes or ""}'.strip()
    dispensing.save(update_fields=['status', 'notes'])

    messages.warning(request, f'Dispensing {dispensing.dispensing_number} has been cancelled and stock restored.')
    return redirect('pharmacy:dashboard')


@login_required
def dispensing_list(request):
    if not _can_access_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    status_filter = request.GET.get('status', '')
    qs = Dispensing.objects.filter(is_deleted=False).select_related(
        'patient', 'dispensed_by'
    ).order_by('-dispensed_at')
    if status_filter:
        qs = qs.filter(status=status_filter)
    # My active dispensings (PENDING/PARTIAL by current user)
    my_active = Dispensing.objects.filter(
        is_deleted=False, dispensed_by=request.user,
        status__in=[DispensingStatus.PENDING, DispensingStatus.PARTIAL],
    ).select_related('patient').order_by('-dispensed_at')
    return render(request, 'pharmacy/dispensing_list.html', {
        'dispensings': qs[:100],
        'my_active': my_active,
        'status_filter': status_filter,
        'status_choices': DispensingStatus.choices,
    })


@login_required
def stock_adjustment_list(request):
    """List all stock adjustments, newest first."""
    adjustments = StockAdjustment.objects.filter(
        is_deleted=False
    ).select_related('batch__drug', 'created_by').order_by('-adjusted_at')[:200]
    return render(request, 'pharmacy/stock_adjustment_list.html', {
        'adjustments': adjustments,
        'reasons': AdjustmentReason.choices,
    })


@login_required
def stock_adjustment_create(request, batch_id):
    """Record a manual adjustment to a specific stock batch."""
    batch = get_object_or_404(DrugStock, id=batch_id, is_deleted=False)

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        change_str = request.POST.get('quantity_change', '').strip()
        notes = request.POST.get('notes', '').strip()

        if reason not in dict(AdjustmentReason.choices):
            messages.error(request, 'Invalid adjustment reason.')
            return redirect('pharmacy:stock_adjustment_create', batch_id=batch.id)

        try:
            change = int(change_str)
        except (ValueError, TypeError):
            messages.error(request, 'Quantity change must be a whole number (negative to reduce stock).')
            return redirect('pharmacy:stock_adjustment_create', batch_id=batch.id)

        if change == 0:
            messages.error(request, 'Quantity change cannot be zero.')
            return redirect('pharmacy:stock_adjustment_create', batch_id=batch.id)

        qty_before = batch.quantity_remaining
        qty_after = max(0, qty_before + change)

        adj = StockAdjustment(
            batch=batch,
            reason=reason,
            quantity_before=qty_before,
            quantity_change=change,
            quantity_after=qty_after,
            notes=notes,
            created_by=request.user,
        )
        adj.save()  # save() also updates batch.quantity_remaining

        messages.success(
            request,
            f'Adjustment recorded for {batch.drug.name} '
            f'(Batch {batch.batch_number}): '
            f'{qty_before} → {qty_after}.'
        )
        return redirect('pharmacy:drug_detail', drug_id=batch.drug.id)

    return render(request, 'pharmacy/stock_adjustment_form.html', {
        'batch': batch,
        'reasons': AdjustmentReason.choices,
    })


@login_required
def pilferage_dashboard(request):
    """
    Pilferage Protection Dashboard:
    - Batch variance: quantity_remaining vs (quantity_received - dispensed)
    - Dispensings with zero/underpayment (amount_paid < total_amount)
    - Large unaccounted stock outflows (inventory)
    - Revenue gap: drugs dispensed value vs pharmacy billing collected
    """
    from django.db.models import F, ExpressionWrapper, DecimalField
    from datetime import timedelta

    today = timezone.localdate()
    month_start = today.replace(day=1)

    # ── 1. Drug batch stock variance ─────────────────────────────────────────
    # For each DrugStock batch: expected = received - dispensed; compare to remaining
    batch_variance = []
    batches = DrugStock.objects.filter(
        is_deleted=False, quantity_received__gt=0
    ).select_related('drug').order_by('drug__name', 'batch_number')

    for batch in batches:
        dispensed_qty = DispensingItem.objects.filter(
            stock_batch=batch, is_deleted=False
        ).aggregate(total=Sum('quantity_dispensed'))['total'] or 0
        expected_remaining = batch.quantity_received - dispensed_qty
        variance = batch.quantity_remaining - expected_remaining
        if variance != 0:
            batch_variance.append({
                'batch': batch,
                'received': batch.quantity_received,
                'dispensed': dispensed_qty,
                'expected': expected_remaining,
                'actual': batch.quantity_remaining,
                'variance': variance,
                'value': abs(variance) * float(batch.drug.cost_price or 0),
            })

    # ── 2. Dispensings with underpayment ─────────────────────────────────────
    underpaid = Dispensing.objects.filter(
        is_deleted=False,
        status='DISPENSED',
    ).exclude(
        amount_paid__gte=F('total_amount')
    ).select_related('patient', 'dispensed_by').order_by('-dispensed_at')[:50]

    # ── 3. Unprescribed dispensings (no prescription linked) ─────────────────
    unprescribed = Dispensing.objects.filter(
        is_deleted=False,
        prescription__isnull=True,
        status='DISPENSED',
        dispensed_at__date__gte=month_start,
    ).select_related('patient', 'dispensed_by').order_by('-dispensed_at')

    # ── 4. Inventory unaccounted outflows (last 30 days) ─────────────────────
    from apps.inventory.models import StockMovement
    unaccounted_out = StockMovement.objects.filter(
        is_deleted=False,
        movement_type='OUT',
        created_at__date__gte=today - timedelta(days=30),
        reference='',   # no reference = unaccounted
    ).select_related('item', 'performed_by').order_by('-created_at')

    # ── 5. Revenue gap this month ─────────────────────────────────────────────
    # Drugs dispensed value this month
    dispensed_value = DispensingItem.objects.filter(
        dispensing__dispensed_at__date__gte=month_start,
        dispensing__is_deleted=False,
        is_deleted=False,
    ).aggregate(total=Sum('subtotal'))['total'] or 0

    # Pharmacy billing collected this month
    try:
        from apps.billing.models import Payment, InvoiceItem
        pharmacy_billed = InvoiceItem.objects.filter(
            invoice__issue_date__gte=month_start,
            invoice__is_deleted=False,
            is_deleted=False,
            category='PHARMACY',
        ).aggregate(total=Sum(F('unit_price') * F('quantity')))['total'] or 0
    except Exception:
        pharmacy_billed = 0

    revenue_gap = float(dispensed_value) - float(pharmacy_billed)

    # ── 6. Low stock drugs ────────────────────────────────────────────────────
    low_stock = [d for d in Drug.objects.filter(is_active=True, is_deleted=False) if d.needs_reorder]

    context = {
        'batch_variance': batch_variance,
        'total_variance_value': sum(r['value'] for r in batch_variance),
        'underpaid': underpaid,
        'underpaid_total': underpaid.aggregate(
            gap=Sum(F('total_amount') - F('amount_paid'))
        )['gap'] or 0,
        'unprescribed': unprescribed,
        'unaccounted_out': unaccounted_out,
        'dispensed_value': dispensed_value,
        'pharmacy_billed': pharmacy_billed,
        'revenue_gap': revenue_gap,
        'low_stock': low_stock,
        'today': today,
        'month_start': month_start,
    }
    return render(request, 'pharmacy/pilferage.html', context)


@login_required
def dispensing_receipt(request, dispensing_id):
    """Printable dispensing receipt — thermal POS format matching billing desk."""
    dispensing = get_object_or_404(
        Dispensing.objects.select_related('prescription').prefetch_related(
            'items__drug', 'items__stock_batch',
        ),
        id=dispensing_id, is_deleted=False,
    )
    balance_due = max(dispensing.total_amount - dispensing.amount_paid, 0)
    # Attach prescription details (dose, frequency, admin times) to each item
    from apps.core.templatetags.ehr_tags import _FREQ_TIME_SLOTS
    items_with_rx = []
    rx_by_name = {}
    if dispensing.prescription:
        for rx_item in dispensing.prescription.items.all():
            rx_by_name[rx_item.drug_name.strip().lower()] = rx_item
    for item in dispensing.items.all():
        drug_name = (item.drug.name if item.drug else item.custom_drug_name).strip().lower()
        rx = rx_by_name.get(drug_name)
        item.rx_dose = rx.dose if rx else ''
        item.rx_frequency = rx.frequency if rx else ''
        item.rx_duration = rx.duration if rx else ''
        item.rx_route = rx.get_route_display() if rx else ''
        item.rx_eye = (rx.get_eye_display() if rx and rx.eye and rx.eye != 'NA' else '')
        item.rx_times = _FREQ_TIME_SLOTS.get(rx.frequency.strip(), '') if rx and rx.frequency else ''
        items_with_rx.append(item)
    return render(request, 'pharmacy/dispensing_receipt.html', {
        'dispensing': dispensing,
        'balance_due': balance_due,
        'items_with_rx': items_with_rx,
    })


@login_required
def patient_typeahead_ajax(request):
    """AJAX typeahead for pharmacy patient search — returns JSON with pending Rx info."""
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})
    from apps.core.utils import patient_search_q, calculate_age
    patients = Patient.objects.filter(
        patient_search_q(q), is_deleted=False,
    ).order_by('last_name', 'first_name')[:8]
    rx_counts = dict(
        DrugPrescription.objects.filter(
            patient__in=patients, is_dispensed=False, is_deleted=False,
        ).values_list('patient_id').annotate(cnt=Count('id')).values_list('patient_id', 'cnt')
    )
    results = []
    for p in patients:
        results.append({
            'id': str(p.id),
            'patient_id': p.patient_id,
            'name': p.full_name,
            'age': calculate_age(p.date_of_birth) if p.date_of_birth else None,
            'gender': p.get_gender_display() if p.gender else '',
            'pending_rx': rx_counts.get(p.id, 0),
        })
    return JsonResponse({'results': results})


@login_required
def patient_search(request):
    """
    Dedicated pharmacy patient search page.
    Search by name or patient ID, see all pending prescriptions.
    """
    q = request.GET.get('q', '').strip()
    results = []
    if q:
        from apps.core.utils import patient_search_q
        matched = list(
            Patient.objects.filter(
                patient_search_q(q), is_deleted=False,
            ).order_by('last_name', 'first_name')[:15]
        )
        for patient in matched:
            # Get all pending prescriptions for this patient
            pending_rx = list(
                DrugPrescription.objects.filter(
                    patient=patient,
                    is_dispensed=False,
                    is_deleted=False,
                ).select_related('prescribed_by').prefetch_related('items')
                .order_by('-prescription_date')
            )
            # Also get the most recent already-dispensed one for context
            last_dispensed = DrugPrescription.objects.filter(
                patient=patient,
                is_dispensed=True,
                is_deleted=False,
            ).order_by('-prescription_date').first()
            results.append({
                'patient': patient,
                'pending_rx': pending_rx,
                'last_dispensed': last_dispensed,
            })
    return render(request, 'pharmacy/patient_search.html', {'q': q, 'results': results})


@login_required
def start_rx_dispensing(request, rx_id):
    """
    One-click: create a Dispensing + auto-populate all items from a DrugPrescription.
    Matches Rx drug names to the formulary, uses FEFO batches, applies selling prices.
    Skips drugs not found in formulary or with zero stock (shows warnings).
    Redirects straight to dispensing_detail — patient is ready for payment review.
    """
    rx = get_object_or_404(
        DrugPrescription.objects.select_related('patient').prefetch_related('items'),
        id=rx_id, is_deleted=False,
    )

    if rx.is_dispensed:
        messages.warning(request, 'This prescription has already been dispensed.')
        return redirect('pharmacy:patient_search')

    today = timezone.localdate()

    # Resolve tier pricing from patient's active visit
    tier, billing_type = 'STANDARD', 'SELF_PAY'
    if rx.patient:
        try:
            from apps.patients.models import Visit
            visit = Visit.objects.filter(
                patient=rx.patient, is_deleted=False,
            ).order_by('-visit_date').first()
            if visit:
                tier = visit.service_tier or 'STANDARD'
                billing_type = visit.billing_type or 'SELF_PAY'
        except Exception:
            pass

    # Create the dispensing record
    dispensing = Dispensing.objects.create(
        patient=rx.patient,
        prescription=rx,
        dispensed_by=request.user,
        notes=f'Auto-loaded from Rx — {rx.prescription_date}',
        created_by=request.user,
    )

    matched_count = 0
    skipped = []

    for rx_item in rx.items.all():
        # Try to match drug name to formulary (exact then partial)
        drug = Drug.objects.filter(
            name__iexact=rx_item.drug_name, is_active=True, is_deleted=False
        ).first()
        if not drug:
            drug = Drug.objects.filter(
                Q(name__icontains=rx_item.drug_name) |
                Q(generic_name__icontains=rx_item.drug_name),
                is_active=True, is_deleted=False,
            ).first()

        if not drug:
            skipped.append(f'{rx_item.drug_name} — not found in formulary')
            continue

        # Find FEFO batch
        batch = DrugStock.objects.filter(
            drug=drug, is_deleted=False,
            quantity_remaining__gte=rx_item.quantity,
        ).filter(
            Q(expiry_date__gte=today) | Q(expiry_date__isnull=True)
        ).order_by('expiry_date').first()

        if not batch:
            # Try any batch with any remaining quantity
            batch = DrugStock.objects.filter(
                drug=drug, is_deleted=False,
                quantity_remaining__gt=0,
            ).filter(
                Q(expiry_date__gte=today) | Q(expiry_date__isnull=True)
            ).order_by('expiry_date').first()

        if not batch:
            skipped.append(f'{drug.name} — out of stock')
            continue

        # Build instruction string from Rx item
        parts = [rx_item.dose, rx_item.frequency]
        if rx_item.duration:
            parts.append(f'× {rx_item.duration}')
        if rx_item.route:
            parts.append(rx_item.get_route_display())
        if rx_item.eye and rx_item.eye != 'NA':
            parts.append(rx_item.get_eye_display())
        if rx_item.special_instructions:
            parts.append(rx_item.special_instructions)
        instructions = ' — '.join(filter(None, parts))

        DispensingItem.objects.create(
            dispensing=dispensing,
            drug=drug,
            stock_batch=batch,
            quantity_dispensed=rx_item.quantity,
            unit_price=drug.get_tier_price(tier=tier, billing_type=billing_type),
            instructions=instructions,
        )
        matched_count += 1

    # Update dispensing total
    total = DispensingItem.objects.filter(dispensing=dispensing).aggregate(
        t=Sum('subtotal')
    )['t'] or 0
    dispensing.total_amount = total
    if matched_count > 0:
        dispensing.status = DispensingStatus.PENDING
    dispensing.save(update_fields=['total_amount', 'status'])

    if skipped:
        messages.warning(
            request,
            f'{len(skipped)} drug(s) could not be auto-loaded: '
            + '; '.join(skipped)
            + '. Please add them manually below.'
        )
    if matched_count > 0:
        messages.success(
            request,
            f'{matched_count} drug(s) loaded from prescription. '
            'Review below and collect payment.'
        )
    else:
        messages.error(
            request,
            'No drugs could be matched to the formulary. Please add items manually.'
        )

    return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)


@login_required
@require_POST
def rx_declined(request, rx_id):
    """Patient declined / bought elsewhere — remove from queue."""
    rx = get_object_or_404(DrugPrescription, id=rx_id, is_deleted=False)
    if not rx.is_dispensed:
        rx.is_dispensed = True
        rx.dispensed_by = request.user
        rx.dispensed_at = timezone.now()
        rx.notes = (rx.notes + '\n' if rx.notes else '') + 'Bought elsewhere / declined dispensing at pharmacy.'
        rx.save(update_fields=['is_dispensed', 'dispensed_by', 'dispensed_at', 'notes'])
        messages.info(request, 'Prescription marked as bought elsewhere and removed from queue.')
    return redirect('pharmacy:patient_search')


# ═══════════════════════════════════════════════════════════════════════════════
# DIRECT SALE / OTC (walk-in, no prescription)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def direct_sale(request):
    """
    OTC / walk-in sale — pharmacist sells drugs without a doctor's prescription.
    Creates a Dispensing record with is_otc=True and prescription=None.
    Patient lookup is optional — can sell to anonymous walk-in.
    """
    if not request.user.can_dispense_pharmacy():
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    if request.method == 'POST':
        patient_id = request.POST.get('patient_id', '').strip()
        walk_in_name = request.POST.get('walk_in_name', '').strip()
        patient = None
        if patient_id:
            patient = Patient.objects.filter(id=patient_id, is_deleted=False).first()

        # Walk-in: either a registered patient OR just a name
        if not patient and not walk_in_name:
            messages.error(request, 'Please select a patient or enter a walk-in customer name.')
            return redirect('pharmacy:direct_sale')

        # Walk-in tier selection — defaults to STANDARD
        otc_tier = request.POST.get('service_tier', 'STANDARD').strip()
        if otc_tier not in ('STANDARD', 'EXPRESS', 'FAST_TRACK', 'VIP'):
            otc_tier = 'STANDARD'

        dispensing = Dispensing.objects.create(
            patient=patient,
            walk_in_name=walk_in_name if not patient else '',
            prescription=None,
            dispensed_by=request.user,
            is_otc=True,
            service_tier=otc_tier if not patient else '',
            notes=request.POST.get('notes', '') or 'OTC / Walk-in sale',
            created_by=request.user,
        )
        messages.success(
            request,
            f'OTC sale {dispensing.dispensing_number} created for {dispensing.customer_name}. Add items below.'
        )
        return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)

    return render(request, 'pharmacy/direct_sale.html')


# ═══════════════════════════════════════════════════════════════════════════════
# MARK RX LINE UNAVAILABLE
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def mark_line_unavailable_ajax(request):
    """AJAX: pharmacist marks a prescription line as unavailable with a reason."""
    if not request.user.can_dispense_pharmacy():
        return JsonResponse({'error': 'Permission denied'}, status=403)

    from apps.prescriptions.models import DrugPrescriptionItem
    item_id = request.POST.get('item_id', '').strip()
    reason = request.POST.get('reason', '').strip()
    notes = request.POST.get('notes', '').strip()

    if reason not in dict(UnavailableReason.choices):
        return JsonResponse({'error': 'Invalid reason'}, status=400)

    item = DrugPrescriptionItem.objects.filter(id=item_id).select_related('prescription').first()
    if not item:
        return JsonResponse({'error': 'Prescription item not found'}, status=404)

    # Create or update
    obj, created = RxLineUnavailable.objects.update_or_create(
        rx_item=item,
        defaults={
            'prescription': item.prescription,
            'reason': reason,
            'notes': notes,
            'marked_by': request.user,
            'created_by': request.user,
        },
    )
    return JsonResponse({
        'success': True,
        'created': created,
        'drug_name': item.drug_name,
        'reason_display': obj.get_reason_display(),
    })


@login_required
@require_POST
def unmark_line_unavailable_ajax(request):
    """AJAX: remove the unavailable flag from a prescription line."""
    if not request.user.can_dispense_pharmacy():
        return JsonResponse({'error': 'Permission denied'}, status=403)

    item_id = request.POST.get('item_id', '').strip()
    deleted = RxLineUnavailable.objects.filter(rx_item_id=item_id).delete()[0]
    return JsonResponse({'success': True, 'deleted': deleted > 0})


@login_required
def unavailable_lines_view(request):
    """Report: all prescription lines marked unavailable — filterable by date, reason."""
    if not _can_access_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    today = timezone.localdate()
    date_from = request.GET.get('from', today.isoformat())
    date_to = request.GET.get('to', today.isoformat())
    reason_filter = request.GET.get('reason', '')

    qs = RxLineUnavailable.objects.select_related(
        'rx_item', 'prescription__patient', 'prescription__prescribed_by', 'marked_by',
    ).filter(is_deleted=False)

    try:
        from datetime import date as _d
        qs = qs.filter(created_at__date__gte=_d.fromisoformat(date_from),
                       created_at__date__lte=_d.fromisoformat(date_to))
    except (ValueError, TypeError):
        pass

    if reason_filter:
        qs = qs.filter(reason=reason_filter)

    lines = qs.order_by('-created_at')[:200]

    # Summary counts by reason
    reason_summary = list(
        qs.values('reason').annotate(count=Count('id')).order_by('-count')
    )
    _reason_labels = dict(UnavailableReason.choices)
    for r in reason_summary:
        r['label'] = _reason_labels.get(r['reason'], r['reason'])

    return render(request, 'pharmacy/unavailable_lines.html', {
        'lines': lines,
        'reason_summary': reason_summary,
        'reasons': UnavailableReason.choices,
        'date_from': date_from,
        'date_to': date_to,
        'reason_filter': reason_filter,
        'today': today,
    })


# ── Controlled Drugs Register ─────────────────────────────────────────────────

@login_required
def controlled_register(request):
    """Narcotics/controlled drug register — full movement log."""
    if not (request.user.is_pharmacist or request.user.is_super_admin
            or request.user.is_medical_director or request.user.is_ceo):
        messages.error(request, 'Access restricted to pharmacy staff.')
        return redirect('pharmacy:dashboard')

    drug_id = request.GET.get('drug')
    entries = ControlledDrugEntry.objects.select_related(
        'drug', 'batch', 'patient', 'performed_by', 'witness', 'dispensing'
    )
    if drug_id:
        entries = entries.filter(drug_id=drug_id)

    controlled_drugs = Drug.objects.filter(is_controlled=True, is_deleted=False, is_active=True).order_by('name')
    selected_drug = Drug.objects.filter(id=drug_id).first() if drug_id else None

    # Running balance grouped by drug if not filtered
    context = {
        'entries': entries[:200],
        'controlled_drugs': controlled_drugs,
        'selected_drug': selected_drug,
        'entry_types': ControlledDrugEntryType,
    }
    return render(request, 'pharmacy/controlled_register.html', context)


@login_required
def controlled_entry_create(request):
    """Add a controlled drug entry (stock-in, wastage, manual adjustment)."""
    if not (request.user.is_pharmacist or request.user.is_super_admin or request.user.is_medical_director):
        messages.error(request, 'Only pharmacists can log controlled drug entries.')
        return redirect('pharmacy:controlled_register')

    if request.method == 'POST':
        drug_id = request.POST.get('drug')
        batch_id = request.POST.get('batch')
        entry_type = request.POST.get('entry_type')
        quantity = request.POST.get('quantity')
        witness_id = request.POST.get('witness')
        notes = request.POST.get('notes', '')

        drug = get_object_or_404(Drug, id=drug_id, is_controlled=True)
        batch = DrugStock.objects.filter(id=batch_id).first() if batch_id else None
        from apps.accounts.models import User
        witness = User.objects.filter(id=witness_id).first() if witness_id else None

        try:
            from decimal import Decimal
            qty = Decimal(quantity)
        except Exception:
            messages.error(request, 'Invalid quantity.')
            return redirect('pharmacy:controlled_register')

        # Compute running balance for this drug
        last_entry = ControlledDrugEntry.objects.filter(drug=drug).order_by('-entry_date').first()
        balance_before = last_entry.balance_after if last_entry else Decimal('0')

        is_out = entry_type in (ControlledDrugEntryType.DISPENSE, ControlledDrugEntryType.WASTAGE)
        balance_after = balance_before - qty if is_out else balance_before + qty

        ControlledDrugEntry.objects.create(
            drug=drug,
            batch=batch,
            entry_type=entry_type,
            quantity=qty,
            balance_before=balance_before,
            balance_after=balance_after,
            performed_by=request.user,
            witness=witness,
            witness_confirmed=False,
            notes=notes,
        )
        messages.success(request, f'Controlled drug entry recorded. Balance: {balance_after}')
        return redirect('pharmacy:controlled_register')

    controlled_drugs = Drug.objects.filter(is_controlled=True, is_deleted=False, is_active=True)
    from apps.accounts.models import User
    pharmacists = User.objects.filter(role__in=['pharmacist', 'super_admin'], is_active=True)
    return render(request, 'pharmacy/controlled_entry_form.html', {
        'controlled_drugs': controlled_drugs,
        'pharmacists': pharmacists,
        'entry_types': ControlledDrugEntryType.choices,
    })


@login_required
@require_POST
def controlled_entry_witness_confirm(request, entry_id):
    """Second pharmacist / witness confirms their counter-signature."""
    entry = get_object_or_404(ControlledDrugEntry, id=entry_id)
    if entry.performed_by == request.user:
        return JsonResponse({'error': 'Witness cannot be the same person who made the entry.'}, status=400)
    if not request.user.is_pharmacist and not request.user.is_super_admin:
        return JsonResponse({'error': 'Only a pharmacist can act as witness.'}, status=403)
    entry.witness = request.user
    entry.witness_confirmed = True
    entry.save(update_fields=['witness', 'witness_confirmed'])
    return JsonResponse({'success': True, 'witness': request.user.get_full_name()})


# ── Ward Drug Return ──────────────────────────────────────────────────────────

@login_required
def ward_return_list(request):
    """List all ward drug returns — pharmacist view."""
    if not (request.user.is_pharmacist or request.user.is_super_admin or request.user.is_medical_director
            or request.user.is_ward_nurse or request.user.is_nurse_director):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    status_filter = request.GET.get('status', '')
    returns = WardDrugReturn.objects.select_related(
        'drug', 'batch', 'admission__patient', 'returned_by', 'actioned_by'
    )
    if status_filter:
        returns = returns.filter(status=status_filter)
    context = {
        'returns': returns[:100],
        'status_filter': status_filter,
        'statuses': WardDrugReturnStatus,
        'pending_count': WardDrugReturn.objects.filter(status=WardDrugReturnStatus.PENDING).count(),
    }
    return render(request, 'pharmacy/ward_return_list.html', context)


@login_required
def ward_return_create(request):
    """Nurse submits a drug return from ward on patient discharge."""
    if not (request.user.is_ward_nurse or request.user.is_theatre_nurse
            or request.user.is_nurse_director or request.user.is_super_admin):
        messages.error(request, 'Only ward nurses can submit drug returns.')
        return redirect('pharmacy:ward_return_list')

    if request.method == 'POST':
        from apps.ipd.models import Admission
        admission_id = request.POST.get('admission')
        drug_id = request.POST.get('drug')
        batch_id = request.POST.get('batch')
        qty = request.POST.get('quantity_returned')
        reason = request.POST.get('reason', '')

        admission = get_object_or_404(Admission, id=admission_id)
        drug = get_object_or_404(Drug, id=drug_id)
        batch = DrugStock.objects.filter(id=batch_id).first() if batch_id else None

        WardDrugReturn.objects.create(
            admission=admission,
            drug=drug,
            batch=batch,
            quantity_returned=int(qty),
            reason=reason,
            returned_by=request.user,
        )
        messages.success(request, f'Drug return submitted. Pending pharmacy acceptance.')
        return redirect('pharmacy:ward_return_list')

    from apps.ipd.models import Admission, AdmissionStatus
    active_admissions = Admission.objects.filter(
        status=AdmissionStatus.ADMITTED, is_deleted=False
    ).select_related('patient').order_by('-admission_date')[:50]
    drugs = Drug.objects.filter(is_active=True, is_deleted=False).order_by('name')
    return render(request, 'pharmacy/ward_return_form.html', {
        'admissions': active_admissions,
        'drugs': drugs,
    })


@login_required
@require_POST
def ward_return_action(request, return_id):
    """Pharmacist accepts or rejects a ward drug return."""
    if not (request.user.is_pharmacist or request.user.is_super_admin):
        return JsonResponse({'error': 'Only pharmacists can action drug returns.'}, status=403)

    drug_return = get_object_or_404(WardDrugReturn, id=return_id, status=WardDrugReturnStatus.PENDING)
    action = request.POST.get('action')

    if action == 'accept':
        # Restore stock to the batch (or create a note if no batch)
        if drug_return.batch:
            drug_return.batch.quantity_remaining += drug_return.quantity_returned
            drug_return.batch.save(update_fields=['quantity_remaining'])
        drug_return.status = WardDrugReturnStatus.ACCEPTED
        drug_return.actioned_by = request.user
        drug_return.actioned_at = timezone.now()
        drug_return.save(update_fields=['status', 'actioned_by', 'actioned_at'])
        messages.success(request, f'{drug_return.return_number} accepted — stock restored.')
    elif action == 'reject':
        drug_return.status = WardDrugReturnStatus.REJECTED
        drug_return.actioned_by = request.user
        drug_return.actioned_at = timezone.now()
        drug_return.rejection_reason = request.POST.get('rejection_reason', '')
        drug_return.save(update_fields=['status', 'actioned_by', 'actioned_at', 'rejection_reason'])
        messages.warning(request, f'{drug_return.return_number} rejected — will be disposed.')
    return redirect('pharmacy:ward_return_list')


# ── Chronic Rx Refill Tracking ────────────────────────────────────────────────

@login_required
def chronic_rx_list(request):
    """List all chronic prescriptions — highlight overdue refills."""
    if not (request.user.is_pharmacist or request.user.is_super_admin
            or request.user.is_medical_director or request.user.is_nurse_director):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    today = timezone.localdate()
    rxs = ChronicPrescription.objects.filter(is_active=True, is_deleted=False).select_related(
        'patient', 'drug', 'prescribing_doctor'
    ).order_by('next_refill_date')

    overdue = [r for r in rxs if r.next_refill_date and r.next_refill_date < today]
    due_today = [r for r in rxs if r.next_refill_date == today]
    upcoming = [r for r in rxs if r.next_refill_date and r.next_refill_date > today]

    return render(request, 'pharmacy/chronic_rx_list.html', {
        'overdue': overdue,
        'due_today': due_today,
        'upcoming': upcoming,
        'today': today,
    })


@login_required
def chronic_rx_create(request):
    """Create a new chronic prescription (link from dispensing or standalone)."""
    if not (request.user.is_pharmacist or request.user.is_super_admin or request.user.is_medical_director):
        messages.error(request, 'Only pharmacists can create chronic prescription records.')
        return redirect('pharmacy:chronic_rx_list')

    if request.method == 'POST':
        patient_id = request.POST.get('patient')
        drug_id = request.POST.get('drug')
        patient = get_object_or_404(Patient, id=patient_id)
        drug = get_object_or_404(Drug, id=drug_id)

        import datetime
        try:
            interval = int(request.POST.get('refill_interval_days', 30))
            qty = int(request.POST.get('quantity_per_refill', 1))
            start = datetime.date.fromisoformat(request.POST.get('start_date', str(timezone.localdate())))
        except (ValueError, TypeError):
            messages.error(request, 'Invalid date or quantity.')
            return redirect('pharmacy:chronic_rx_create')

        ChronicPrescription.objects.update_or_create(
            patient=patient, drug=drug,
            defaults={
                'prescribing_doctor': request.user,
                'dose': request.POST.get('dose', ''),
                'frequency': request.POST.get('frequency', ''),
                'quantity_per_refill': qty,
                'refill_interval_days': interval,
                'start_date': start,
                'is_active': True,
                'notes': request.POST.get('notes', ''),
            }
        )
        messages.success(request, f'Chronic Rx for {patient.full_name} — {drug.name} saved.')
        return redirect('pharmacy:chronic_rx_list')

    drugs = Drug.objects.filter(is_active=True, is_deleted=False).order_by('name')
    return render(request, 'pharmacy/chronic_rx_form.html', {
        'drugs': drugs,
        'today': timezone.localdate(),
    })


@login_required
@require_POST
def chronic_rx_refill(request, rx_id):
    """Record a completed refill dispensing and advance the next_refill_date."""
    if not (request.user.is_pharmacist or request.user.is_super_admin):
        return JsonResponse({'error': 'Permission denied.'}, status=403)
    rx = get_object_or_404(ChronicPrescription, id=rx_id, is_active=True)
    rx.record_refill()
    return JsonResponse({
        'success': True,
        'refill_count': rx.refill_count,
        'next_refill_date': rx.next_refill_date.isoformat(),
    })


# ── Drug Expiry & Low-Stock Alert Page ───────────────────────────────────────

@login_required
def drug_expiry_alerts(request):
    """Dedicated page: expired drugs still in stock + drugs expiring within 30/60/90 days + low stock."""
    if not (request.user.is_pharmacist or request.user.is_medical_director
            or request.user.is_admin_staff or request.user.is_super_admin
            or request.user.is_ceo or request.user.is_admin_director
            or request.user.is_finance_director):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    today = timezone.localdate()
    base_qs = DrugStock.objects.filter(is_deleted=False, quantity_remaining__gt=0, expiry_date__isnull=False).select_related('drug')

    expired           = base_qs.filter(expiry_date__lt=today).order_by('expiry_date')
    expiring_30       = base_qs.filter(expiry_date__gte=today, expiry_date__lte=today + timezone.timedelta(days=30)).order_by('expiry_date')
    expiring_60       = base_qs.filter(expiry_date__gt=today + timezone.timedelta(days=30), expiry_date__lte=today + timezone.timedelta(days=60)).order_by('expiry_date')
    expiring_90       = base_qs.filter(expiry_date__gt=today + timezone.timedelta(days=60), expiry_date__lte=today + timezone.timedelta(days=90)).order_by('expiry_date')
    low_stock         = list(Drug.objects.filter(is_active=True, is_deleted=False).annotate(
        stock_total=Coalesce(Sum('stock_items__quantity_remaining', filter=Q(stock_items__is_deleted=False)), Value(0, output_field=IntegerField()))
    ).filter(stock_total__lte=F('reorder_level')))

    return render(request, 'pharmacy/expiry_alerts.html', {
        'expired': expired,
        'expiring_30': expiring_30,
        'expiring_60': expiring_60,
        'expiring_90': expiring_90,
        'low_stock': low_stock,
        'today': today,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# SUPPLIER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def _can_manage_pharmacy(user):
    return (user.is_pharmacist or user.is_super_admin or user.is_admin_director
            or user.is_finance_director or user.is_senior_accountant)


def _can_edit_drug_prices(user):
    """Only head pharmacist and admin roles can set/change drug prices."""
    return (user.is_head_pharmacist or user.is_super_admin or user.is_admin_director
            or user.is_finance_director or user.is_senior_accountant)


@login_required
def supplier_list(request):
    if not _can_manage_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    suppliers = Supplier.objects.filter(is_deleted=False).order_by('name')
    return render(request, 'pharmacy/supplier_list.html', {'suppliers': suppliers})


@login_required
def supplier_create(request):
    if not _can_manage_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            s = form.save(commit=False)
            s.created_by = request.user
            s.save()
            messages.success(request, f'Supplier "{s.name}" added.')
            return redirect('pharmacy:supplier_list')
    else:
        form = SupplierForm()
    return render(request, 'pharmacy/supplier_form.html', {'form': form, 'is_edit': False})


@login_required
def supplier_edit(request, supplier_id):
    if not _can_manage_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    supplier = get_object_or_404(Supplier, id=supplier_id, is_deleted=False)
    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, f'Supplier "{supplier.name}" updated.')
            return redirect('pharmacy:supplier_list')
    else:
        form = SupplierForm(instance=supplier)
    return render(request, 'pharmacy/supplier_form.html', {'form': form, 'supplier': supplier, 'is_edit': True})


# ═══════════════════════════════════════════════════════════════════════════════
# PURCHASE ORDER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def purchase_order_list(request):
    if not _can_manage_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    orders = PurchaseOrder.objects.filter(is_deleted=False).select_related('supplier', 'created_by').order_by('-order_date')[:100]
    return render(request, 'pharmacy/purchase_order_list.html', {'orders': orders, 'statuses': PurchaseOrderStatus})


@login_required
def purchase_order_create(request):
    if not _can_manage_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST)
        if form.is_valid():
            po = form.save(commit=False)
            po.created_by = request.user
            po.save()
            # Create line items from POST arrays
            drug_ids   = request.POST.getlist('drug_id')
            qtys       = request.POST.getlist('quantity_ordered')
            unit_costs = request.POST.getlist('unit_cost')
            total = 0
            for drug_id, qty, uc in zip(drug_ids, qtys, unit_costs):
                try:
                    drug = Drug.objects.get(id=drug_id, is_deleted=False)
                    qty_int = int(qty)
                    cost = float(uc)
                    PurchaseOrderItem.objects.create(order=po, drug=drug, quantity_ordered=qty_int, unit_cost=cost)
                    total += qty_int * cost
                except Exception:
                    pass
            po.total_amount = total
            po.save(update_fields=['total_amount'])
            messages.success(request, f'Purchase Order {po.order_number} created.')
            return redirect('pharmacy:purchase_order_detail', po_id=po.id)
    else:
        form = PurchaseOrderForm()

    drugs = Drug.objects.filter(is_active=True, is_deleted=False).order_by('name')

    # Pick up pre-selected drugs from Quick Reorder
    reorder_items = request.session.pop('reorder_items', None) or []
    prefill = []
    for item in reorder_items:
        try:
            d = Drug.objects.get(id=item['drug_id'], is_deleted=False)
            prefill.append({
                'drug_id': str(d.id),
                'drug_name': f'{d.name} {d.strength}'.strip(),
                'qty': item.get('qty') or d.reorder_level or 10,
                'unit_cost': float(d.cost_price),
            })
        except Drug.DoesNotExist:
            pass

    import json
    return render(request, 'pharmacy/purchase_order_form.html', {
        'form': form, 'drugs': drugs,
        'prefill_json': json.dumps(prefill),
    })


@login_required
def purchase_order_detail(request, po_id):
    if not _can_manage_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    po = get_object_or_404(PurchaseOrder, id=po_id, is_deleted=False)
    items = po.items.select_related('drug', 'stock_created').all()
    return render(request, 'pharmacy/purchase_order_detail.html', {
        'po': po, 'items': items, 'statuses': PurchaseOrderStatus,
    })


@login_required
@require_POST
def purchase_order_approve(request, po_id):
    if not _can_manage_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    po = get_object_or_404(PurchaseOrder, id=po_id, is_deleted=False)
    if po.status not in (PurchaseOrderStatus.DRAFT, PurchaseOrderStatus.SUBMITTED):
        messages.error(request, 'Only DRAFT or SUBMITTED orders can be approved.')
        return redirect('pharmacy:purchase_order_detail', po_id=po.id)
    po.status = PurchaseOrderStatus.APPROVED
    po.approved_by = request.user
    po.approved_at = timezone.now()
    po.save(update_fields=['status', 'approved_by', 'approved_at'])
    messages.success(request, f'PO {po.order_number} approved and sent to supplier.')
    return redirect('pharmacy:purchase_order_detail', po_id=po.id)


@login_required
@require_POST
def receive_purchase_order(request, po_id):
    """Record goods receipt for one or more items. Creates DrugStock batches."""
    if not _can_manage_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    po = get_object_or_404(PurchaseOrder, id=po_id, is_deleted=False)
    if po.status not in (PurchaseOrderStatus.APPROVED, PurchaseOrderStatus.PARTIAL):
        messages.error(request, 'Order must be APPROVED or PARTIAL to receive goods.')
        return redirect('pharmacy:purchase_order_detail', po_id=po.id)

    item_ids  = request.POST.getlist('item_id')
    rcv_qtys  = request.POST.getlist('qty_received')
    batches   = request.POST.getlist('batch_number')
    exp_dates = request.POST.getlist('expiry_date')

    from datetime import date
    received_any = False
    for item_id, qty_s, batch_no, exp_s in zip(item_ids, rcv_qtys, batches, exp_dates):
        try:
            item = PurchaseOrderItem.objects.get(id=item_id, order=po)
            qty = int(qty_s)
            if qty <= 0:
                continue
            exp = date.fromisoformat(exp_s)
            stock = DrugStock.objects.create(
                drug=item.drug,
                batch_number=batch_no or f'PO{po.order_number}',
                expiry_date=exp,
                quantity_received=qty,
                quantity_remaining=qty,
                purchase_price=item.unit_cost,
                created_by=request.user,
            )
            item.quantity_received += qty
            item.batch_number = batch_no or item.batch_number
            item.expiry_date = exp
            item.stock_created = stock
            item.save(update_fields=['quantity_received', 'batch_number', 'expiry_date', 'stock_created'])
            received_any = True
        except Exception:
            continue

    if received_any:
        # Update PO status
        items = po.items.all()
        fully_received = all(i.quantity_received >= i.quantity_ordered for i in items)
        po.status = PurchaseOrderStatus.RECEIVED if fully_received else PurchaseOrderStatus.PARTIAL
        po.save(update_fields=['status'])
        messages.success(request, 'Goods received and stock batches created.')
    else:
        messages.error(request, 'No valid receipt data submitted.')
    return redirect('pharmacy:purchase_order_detail', po_id=po.id)


# ═══════════════════════════════════════════════════════════════════════════════
# QUICK REORDER — smart PO creation from low / out-of-stock drugs
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def quick_reorder(request):
    """Show low/out-of-stock drugs with checkboxes; POST creates a PO pre-filled."""
    if not _can_manage_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    today = timezone.localdate()
    valid_stock = Q(
        stock_items__is_deleted=False,
        stock_items__quantity_remaining__gt=0,
    ) & (Q(stock_items__expiry_date__gte=today) | Q(stock_items__expiry_date__isnull=True))

    drugs = (
        Drug.objects.filter(is_active=True, is_deleted=False)
        .annotate(
            stock_qty=Coalesce(
                Sum('stock_items__quantity_remaining', filter=valid_stock),
                Value(0, output_field=IntegerField()),
            ),
        )
        .order_by('name')
    )

    # Filters
    stock_filter = request.GET.get('filter', 'needs_reorder')  # needs_reorder, out_of_stock, all
    category = request.GET.get('category', '')
    search = request.GET.get('q', '').strip()

    if stock_filter == 'out_of_stock':
        drugs = drugs.filter(stock_qty=0)
    elif stock_filter == 'needs_reorder':
        drugs = drugs.filter(stock_qty__lte=F('reorder_level'))
    # 'all' shows everything

    if category:
        drugs = drugs.filter(category=category)
    if search:
        drugs = drugs.filter(Q(name__icontains=search) | Q(generic_name__icontains=search))

    # POST: redirect to PO create with selected drug IDs in session
    if request.method == 'POST':
        selected_ids = request.POST.getlist('drug_ids')
        selected_qtys = request.POST.getlist('order_qty')
        if not selected_ids:
            messages.warning(request, 'No drugs selected.')
            return redirect('pharmacy:quick_reorder')
        # Store in session for PO create to pick up
        reorder_items = []
        for did, qty in zip(selected_ids, selected_qtys):
            try:
                reorder_items.append({'drug_id': did, 'qty': int(qty) if qty else 0})
            except (ValueError, TypeError):
                reorder_items.append({'drug_id': did, 'qty': 0})
        request.session['reorder_items'] = reorder_items
        return redirect('pharmacy:purchase_order_create')

    from .models import DrugCategory
    categories = DrugCategory.choices

    return render(request, 'pharmacy/quick_reorder.html', {
        'drugs': drugs,
        'stock_filter': stock_filter,
        'category': category,
        'search': search,
        'categories': categories,
        'suppliers': Supplier.objects.filter(is_deleted=False).order_by('name'),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# DISPENSING RETURN
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def dispensing_return_create(request, dispensing_id):
    """Record a return of dispensed drugs back to pharmacy stock."""
    if not (request.user.can_dispense_pharmacy() or request.user.is_super_admin):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    dispensing = get_object_or_404(Dispensing, id=dispensing_id, is_deleted=False)
    if request.method == 'POST':
        form = DispensingReturnForm(request.POST, dispensing=dispensing)
        if form.is_valid():
            ret = form.save(commit=False)
            ret.dispensing = dispensing
            ret.returned_by = request.user
            ret.created_by = request.user
            ret.save()
            messages.success(
                request,
                f'{ret.quantity_returned}× {ret.drug.name} returned'
                + (' — stock restored.' if ret.stock_restored else ' — stock NOT restored (batch expired).')
            )
            return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)
    else:
        form = DispensingReturnForm(dispensing=dispensing)
    return render(request, 'pharmacy/dispensing_return_form.html', {
        'form': form, 'dispensing': dispensing,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# PHARMACIST VERIFICATION (JCI MMU.6.1)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def dispensing_verify(request, dispensing_id):
    """Pharmacist final verification + counseling confirmation before handout."""
    if not request.user.can_dispense_pharmacy():
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    dispensing = get_object_or_404(Dispensing, id=dispensing_id, is_deleted=False)
    if dispensing.verified_by_pharmacist_id:
        messages.info(request, 'Already verified.')
        return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)
    counseling = request.POST.get('counseling_given') == 'on'
    counseling_notes = request.POST.get('counseling_notes', '').strip()
    dispensing.verified_by_pharmacist = request.user
    dispensing.verified_at = timezone.now()
    dispensing.counseling_given = counseling
    dispensing.counseling_notes = counseling_notes
    dispensing.save(update_fields=['verified_by_pharmacist', 'verified_at', 'counseling_given', 'counseling_notes'])
    messages.success(request, 'Dispensing verified. Patient counseling recorded.')
    return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)


# ═══════════════════════════════════════════════════════════════════════════════
# DISPENSING LABEL PDF (JCI MMU.6)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def dispensing_label_pdf(request, dispensing_id):
    """Generate a printed dispensing label for each item in the dispensing."""
    if not (request.user.can_dispense_pharmacy() or request.user.is_super_admin):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    dispensing = get_object_or_404(
        Dispensing.objects.select_related('prescription'),
        id=dispensing_id, is_deleted=False,
    )
    from apps.accounts.models import HospitalConfig
    config = HospitalConfig.get()
    # Attach rx data to each item for label printing
    from apps.core.templatetags.ehr_tags import _FREQ_TIME_SLOTS
    items = list(dispensing.items.select_related('drug', 'stock_batch').all())
    rx_by_name = {}
    if dispensing.prescription:
        for rx_item in dispensing.prescription.items.all():
            rx_by_name[rx_item.drug_name.strip().lower()] = rx_item
    for item in items:
        drug_name = (item.drug.name if item.drug else item.custom_drug_name).strip().lower()
        rx = rx_by_name.get(drug_name)
        item.rx_dose = rx.dose if rx else ''
        item.rx_frequency = rx.frequency if rx else ''
        item.rx_duration = rx.duration if rx else ''
        item.rx_route = rx.get_route_display() if rx else ''
        item.rx_eye = (rx.get_eye_display() if rx and rx.eye and rx.eye != 'NA' else '')
        item.rx_times = _FREQ_TIME_SLOTS.get(rx.frequency.strip(), '') if rx and rx.frequency else ''
    from django.template.loader import render_to_string
    from django.http import HttpResponse
    try:
        import weasyprint
        html = render_to_string('pharmacy/dispensing_label.html', {
            'dispensing': dispensing,
            'items': items,
            'config': config,
        }, request=request)
        pdf = weasyprint.HTML(string=html).write_pdf()
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="label_{dispensing.dispensing_number}.pdf"'
        return response
    except ImportError:
        return HttpResponse('WeasyPrint not installed.', status=500)


# ═══════════════════════════════════════════════════════════════════════════════
# CONTROLLED DRUG REGISTER PDF (JCI MMU.3.1)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def controlled_register_pdf(request):
    """Daily/period controlled drug balance sheet as PDF."""
    if not _can_manage_pharmacy(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    from datetime import date as date_cls
    date_str = request.GET.get('date', timezone.localdate().isoformat())
    try:
        report_date = date_cls.fromisoformat(date_str)
    except ValueError:
        report_date = timezone.localdate()

    entries = (
        ControlledDrugEntry.objects
        .filter(is_deleted=False, entry_date__date=report_date)
        .select_related('drug', 'patient', 'performed_by', 'witness')
        .order_by('drug__name', 'entry_date')
    )
    from apps.accounts.models import HospitalConfig
    config = HospitalConfig.get()
    from django.template.loader import render_to_string
    from django.http import HttpResponse
    try:
        import weasyprint
        html = render_to_string('pharmacy/controlled_register_pdf.html', {
            'entries': entries,
            'report_date': report_date,
            'config': config,
        }, request=request)
        pdf = weasyprint.HTML(string=html).write_pdf()
        response = HttpResponse(pdf, content_type='application/pdf')
        fname = f'controlled_register_{report_date}.pdf'
        response['Content-Disposition'] = f'inline; filename="{fname}"'
        return response
    except ImportError:
        return HttpResponse('WeasyPrint not installed.', status=500)


# ─────────────────────────────────────────────────────────────────────────────
#  Bulk Drug / Stock Import  (Excel .xlsx  or  CSV)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_date(val):
    """Parse date from Excel date, string DD/MM/YYYY, YYYY-MM-DD, or DD-MM-YYYY."""
    import datetime
    if val is None:
        return None
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val.date() if isinstance(val, datetime.datetime) else val
    s = str(val).strip()
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y'):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _str(val):
    return str(val).strip() if val is not None else ''


def _int(val, default=0):
    try:
        return max(0, int(str(val).strip()))
    except (ValueError, TypeError):
        return default


def _dec(val, default='0'):
    from decimal import Decimal, InvalidOperation
    try:
        return Decimal(str(val).strip())
    except (InvalidOperation, TypeError):
        return Decimal(default)


_FORM_MAP = {
    'eye drop': 'EYE_DROP', 'eyedrop': 'EYE_DROP', 'drops': 'EYE_DROP',
    'eye ointment': 'EYE_OINT', 'ointment': 'EYE_OINT',
    'tablet': 'TABLET', 'tab': 'TABLET',
    'capsule': 'CAPSULE', 'cap': 'CAPSULE',
    'injection': 'INJECTION', 'inj': 'INJECTION', 'ampoule': 'INJECTION',
    'syrup': 'SYRUP', 'suspension': 'SYRUP', 'liquid': 'SYRUP',
    'cream': 'CREAM',
    'nasal': 'NASAL', 'nasal drop': 'NASAL',
    'other': 'OTHER',
}

_CATEGORY_MAP = {
    'antibiotic': 'ANTIBIOTIC', 'antifungal': 'ANTIFUNGAL', 'antiviral': 'ANTIVIRAL',
    'glaucoma': 'GLAUCOMA', 'steroid': 'STEROID', 'nsaid': 'NSAID',
    'mydriatic': 'MYDRIATIC', 'lubricant': 'LUBRICANT',
    'anaesthetic': 'ANAESTHETIC', 'anesthetic': 'ANAESTHETIC',
    'vitamin': 'VITAMIN', 'analgesic': 'ANALGESIC',
    'antihypertensive': 'ANTIHTN', 'antidiabetic': 'ANTIDIAB', 'other': 'OTHER',
}

_STORAGE_MAP = {
    'room temp': 'ROOM', 'ambient': 'ROOM', 'room': 'ROOM',
    'refrigerated': 'FRIDGE', 'fridge': 'FRIDGE', 'cold': 'FRIDGE',
    'frozen': 'FROZEN', 'freeze': 'FROZEN',
    'controlled': 'CONTROLLED',
    'light': 'LIGHT', 'protect from light': 'LIGHT',
    'flammable': 'FLAME',
}


@login_required
def drug_import_template(request):
    """Download a blank Excel import template."""
    if not _can_manage_pharmacy(request.user):
        messages.error(request, 'Access denied.')
        return redirect('pharmacy:drug_list')

    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Drug Inventory'

    headers = [
        'drug_name', 'generic_name', 'brand_name', 'form', 'strength', 'unit',
        'category', 'reorder_level', 'selling_price', 'cost_price',
        'price_express', 'price_vip', 'price_executive_vip',
        'price_staff', 'price_outreach', 'insurance_markup_pct',
        'is_controlled', 'controlled_schedule', 'storage_condition',
        'batch_number', 'expiry_date', 'quantity', 'purchase_price',
        'supplier_name', 'manufacture_date',
    ]
    hints = [
        'REQUIRED', 'Optional', 'Optional',
        'tablet/capsule/eye drop/injection/syrup/cream/other',
        'e.g. 5mg, 0.5%', 'e.g. bottle, tube, tablet',
        'antibiotic/antifungal/glaucoma/analgesic/vitamin/other',
        'Default: 10', 'FCFA — Standard', 'FCFA — Purchase cost',
        'FCFA — Express', 'FCFA — VIP', 'FCFA — Executive VIP',
        'FCFA — Staff', 'FCFA — Outreach', '% markup on cost for insured',
        'Yes / No', 'S2/S3/S4/S5 (only if controlled)',
        'room temp / refrigerated / frozen / controlled / light',
        'REQUIRED for stock entry', 'REQUIRED — DD/MM/YYYY', 'REQUIRED — whole number',
        'FCFA per unit', 'Optional', 'Optional — DD/MM/YYYY',
    ]

    thin = Side(border_style='thin', color='CCCCCC')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for col, (h, hint) in enumerate(zip(headers, hints), 1):
        hc = ws.cell(row=1, column=col, value=h)
        hc.font = Font(bold=True, color='FFFFFF', size=10)
        hc.fill = PatternFill(fill_type='solid', fgColor='1E3A5F')
        hc.alignment = Alignment(horizontal='center', wrap_text=True)
        hc.border = border

        hintc = ws.cell(row=2, column=col, value=hint)
        hintc.font = Font(italic=True, color='555555', size=9)
        hintc.fill = PatternFill(fill_type='solid', fgColor='E8F0FE')
        hintc.alignment = Alignment(wrap_text=True)
        hintc.border = border

    sample = [
        'Ciprofloxacin', 'Ciprofloxacin', 'Cipro', 'tablet', '500mg', 'tablet',
        'antibiotic', 20, 2500, 1500,
        3000, 3500, 4000, 2000, 1800, 30,
        'No', '', 'room temp',
        'BATCH-2024-001', '31/12/2026', 100, 1400, 'PharmaCo Ltd', '',
    ]
    for col, val in enumerate(sample, 1):
        c = ws.cell(row=3, column=col, value=val)
        c.fill = PatternFill(fill_type='solid', fgColor='F0FFF0')
        c.border = border

    for i, w in enumerate([22,20,16,14,12,10,16,12,12,12,12,12,14,12,12,14,12,16,18,18,14,10,14,18,16], 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 28
    ws.row_dimensions[2].height = 36
    ws.freeze_panes = 'A4'

    ws2 = wb.create_sheet('Instructions')
    lines = [
        ('EHR Africa — Pharmacy Bulk Import Template', True),
        ('', False),
        ('REQUIRED COLUMNS:', True),
        ('  drug_name — exact drug name as it should appear in the formulary', False),
        ('  batch_number — unique batch/lot number from the supplier', False),
        ('  expiry_date — format DD/MM/YYYY  (e.g. 31/12/2026)', False),
        ('  quantity — number of units in this batch', False),
        ('', False),
        ('FORM values: tablet, capsule, eye drop, eye ointment, injection, syrup, cream, nasal drop, other', False),
        ('CATEGORY values: antibiotic, antifungal, antiviral, glaucoma, steroid, nsaid, mydriatic,', False),
        ('  lubricant, anaesthetic, vitamin, analgesic, antihypertensive, antidiabetic, other', False),
        ('STORAGE values: room temp, refrigerated, frozen, controlled, light, flammable', False),
        ('', False),
        ('RULES:', True),
        ('  • If the drug already exists in the formulary, its stock batch is added (not duplicated)', False),
        ('  • If the drug does NOT exist, it is created automatically', False),
        ('  • Row 3 is a sample — delete it before uploading real data', False),
        ('  • Accepted file formats: .xlsx (Excel) or .csv', False),
        ('  • Expired batches are rejected automatically', False),
    ]
    for r, (txt, bold) in enumerate(lines, 1):
        c = ws2.cell(row=r, column=1, value=txt)
        if bold:
            c.font = Font(bold=True, size=11)
    ws2.column_dimensions['A'].width = 90

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="EHR_Drug_Import_Template.xlsx"'
    wb.save(response)
    return response


@login_required
def drug_bulk_import(request):
    """Upload Excel (.xlsx) or CSV to bulk-create/update drugs and stock batches."""
    if not _can_manage_pharmacy(request.user):
        messages.error(request, 'Only pharmacists and admins can import drugs.')
        return redirect('pharmacy:drug_list')

    if request.method != 'POST':
        return render(request, 'pharmacy/drug_bulk_import.html')

    uploaded = request.FILES.get('import_file')
    if not uploaded:
        messages.error(request, 'No file selected.')
        return render(request, 'pharmacy/drug_bulk_import.html')

    filename = uploaded.name.lower()
    rows = []

    try:
        if filename.endswith('.xlsx') or filename.endswith('.xls'):
            import openpyxl
            wb = openpyxl.load_workbook(uploaded, data_only=True)
            ws = wb.active
            all_rows = list(ws.iter_rows(values_only=True))
            if len(all_rows) < 3:
                messages.error(request, 'File has no data rows (need at least 3 rows).')
                return render(request, 'pharmacy/drug_bulk_import.html')
            headers = [str(h).strip().lower().replace(' ', '_') if h else '' for h in all_rows[0]]
            for raw in all_rows[2:]:
                if all(v is None for v in raw):
                    continue
                rows.append(dict(zip(headers, raw)))
        elif filename.endswith('.csv'):
            import csv, io
            content = uploaded.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content))
            reader.fieldnames = [f.strip().lower().replace(' ', '_') for f in (reader.fieldnames or [])]
            for row in reader:
                rows.append({k.strip().lower().replace(' ', '_'): v for k, v in row.items()})
        else:
            messages.error(request, 'Unsupported format — upload .xlsx or .csv only.')
            return render(request, 'pharmacy/drug_bulk_import.html')
    except Exception as e:
        messages.error(request, f'Could not read file: {e}')
        return render(request, 'pharmacy/drug_bulk_import.html')

    drugs_created = drugs_updated = batches_created = skipped = 0
    errors = []
    today = timezone.localdate()

    for i, row in enumerate(rows, start=3):
        drug_name = _str(row.get('drug_name') or row.get('name', ''))
        if not drug_name:
            skipped += 1
            continue

        form = _FORM_MAP.get(_str(row.get('form', 'other')).lower(), 'OTHER')
        category = _CATEGORY_MAP.get(_str(row.get('category', 'other')).lower(), 'OTHER')
        storage = _STORAGE_MAP.get(_str(row.get('storage_condition', 'room temp')).lower(), 'ROOM')
        is_controlled = _str(row.get('is_controlled', 'no')).lower() in ('yes', 'y', 'true', '1')
        controlled_schedule = _str(row.get('controlled_schedule', '')).upper()

        drug, created = Drug.objects.get_or_create(
            name__iexact=drug_name,
            is_deleted=False,
            defaults={
                'name': drug_name,
                'generic_name': _str(row.get('generic_name', '')) or drug_name,
                'brand_name': _str(row.get('brand_name', '')),
                'form': form,
                'category': category,
                'strength': _str(row.get('strength', '')),
                'unit': _str(row.get('unit', 'unit')) or 'unit',
                'reorder_level': _int(row.get('reorder_level'), 10),
                'selling_price': _dec(row.get('selling_price', '0')),
                'cost_price': _dec(row.get('cost_price', '0')),
                'price_express': _dec(row.get('price_express', '0')),
                'price_vip': _dec(row.get('price_vip', '0')),
                'price_executive_vip': _dec(row.get('price_executive_vip', '0')),
                'price_staff': _dec(row.get('price_staff', '0')),
                'price_outreach': _dec(row.get('price_outreach', '0')),
                'insurance_markup_pct': _dec(row.get('insurance_markup_pct', '0')),
                'is_controlled': is_controlled,
                'controlled_schedule': controlled_schedule if is_controlled else '',
                'storage_condition': storage,
                'is_active': True,
            }
        )
        if created:
            drugs_created += 1
        else:
            drugs_updated += 1

        batch_number = _str(row.get('batch_number', ''))
        expiry_date = _parse_date(row.get('expiry_date'))
        quantity = _int(row.get('quantity') or row.get('qty'), 0)

        if not batch_number or not expiry_date:
            continue
        if expiry_date < today:
            errors.append(f'Row {i} ({drug_name}): batch {batch_number} is expired ({expiry_date}) — skipped.')
            continue
        if DrugStock.objects.filter(drug=drug, batch_number=batch_number, is_deleted=False).exists():
            errors.append(f'Row {i} ({drug_name}): batch {batch_number} already exists — skipped.')
            skipped += 1
            continue
        if quantity <= 0:
            errors.append(f'Row {i} ({drug_name}): quantity must be > 0 — skipped.')
            continue

        DrugStock.objects.create(
            drug=drug,
            batch_number=batch_number,
            expiry_date=expiry_date,
            quantity_received=quantity,
            quantity_remaining=quantity,
            purchase_price=_dec(row.get('purchase_price') or row.get('unit_cost', '0')),
            supplier=_str(row.get('supplier_name', '')),
            manufacture_date=_parse_date(row.get('manufacture_date')),
            received_date=today,
        )
        batches_created += 1

    return render(request, 'pharmacy/drug_bulk_import.html', {
        'done': True,
        'drugs_created': drugs_created,
        'drugs_updated': drugs_updated,
        'batches_created': batches_created,
        'skipped': skipped,
        'errors': errors,
        'total_rows': len(rows),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# HEAD PHARMACIST MODULE — Administration & Management
# WHO GPP, FIP Guidelines, JCI MMU Standards
# ═══════════════════════════════════════════════════════════════════════════════

def _is_head_pharmacist(user):
    from apps.accounts.models import UserRole
    return user.role in (
        UserRole.HEAD_PHARMACIST, UserRole.SUPER_ADMIN,
        UserRole.ADMIN_DIRECTOR, UserRole.CEO,
    )


# ── Pharmacy Locations ─────────────────────────────────────────────────────

@login_required
def location_list(request):
    if not _is_head_pharmacist(request.user):
        return HttpResponse('Access denied', status=403)
    locations = PharmacyLocation.objects.filter(is_deleted=False)
    return render(request, 'pharmacy/location_list.html', {'locations': locations})


@login_required
def location_create(request):
    if not _is_head_pharmacist(request.user):
        return HttpResponse('Access denied', status=403)
    if request.method == 'POST':
        loc = PharmacyLocation(
            name=request.POST.get('name', ''),
            location_type=request.POST.get('location_type', 'MAIN'),
            address=request.POST.get('address', ''),
            phone_ext=request.POST.get('phone_ext', ''),
            storage_conditions=request.POST.get('storage_conditions', ''),
            license_number=request.POST.get('license_number', ''),
            has_controlled_access=request.POST.get('has_controlled_access') == 'on',
        )
        manager_id = request.POST.get('manager')
        if manager_id:
            from apps.accounts.models import User
            loc.manager = User.objects.filter(pk=manager_id).first()
        loc.save()
        messages.success(request, f'Location "{loc.name}" created.')
        return redirect('pharmacy:location_list')
    from apps.accounts.models import User, UserRole
    pharmacists = User.objects.filter(
        role__in=[UserRole.PHARMACIST, UserRole.HEAD_PHARMACIST], is_active=True
    ).order_by('first_name')
    return render(request, 'pharmacy/location_form.html', {
        'pharmacists': pharmacists,
        'location_types': PharmacyLocation._meta.get_field('location_type').choices,
    })


@login_required
def location_edit(request, loc_id):
    if not _is_head_pharmacist(request.user):
        return HttpResponse('Access denied', status=403)
    loc = get_object_or_404(PharmacyLocation, pk=loc_id, is_deleted=False)
    if request.method == 'POST':
        loc.name = request.POST.get('name', loc.name)
        loc.location_type = request.POST.get('location_type', loc.location_type)
        loc.address = request.POST.get('address', '')
        loc.phone_ext = request.POST.get('phone_ext', '')
        loc.is_active = request.POST.get('is_active') == 'on'
        loc.storage_conditions = request.POST.get('storage_conditions', '')
        loc.license_number = request.POST.get('license_number', '')
        loc.has_controlled_access = request.POST.get('has_controlled_access') == 'on'
        manager_id = request.POST.get('manager')
        if manager_id:
            from apps.accounts.models import User
            loc.manager = User.objects.filter(pk=manager_id).first()
        else:
            loc.manager = None
        loc.save()
        messages.success(request, f'Location "{loc.name}" updated.')
        return redirect('pharmacy:location_list')
    from apps.accounts.models import User, UserRole
    pharmacists = User.objects.filter(
        role__in=[UserRole.PHARMACIST, UserRole.HEAD_PHARMACIST], is_active=True
    ).order_by('first_name')
    return render(request, 'pharmacy/location_form.html', {
        'location': loc,
        'pharmacists': pharmacists,
        'location_types': PharmacyLocation._meta.get_field('location_type').choices,
    })


# ── Inter-Store Transfers ──────────────────────────────────────────────────

@login_required
def transfer_list(request):
    if not _can_manage_pharmacy(request.user):
        return HttpResponse('Access denied', status=403)
    status_filter = request.GET.get('status', '')
    direction = request.GET.get('direction', '')  # 'outgoing', 'incoming', or '' (all)
    qs = StockTransfer.objects.filter(is_deleted=False).select_related(
        'from_location', 'to_location', 'initiated_by', 'received_by'
    )
    if status_filter:
        qs = qs.filter(status=status_filter)
    # Direction filter based on user's pharmacy location
    user_locations = PharmacyLocation.objects.filter(
        is_deleted=False, is_active=True, manager=request.user,
    )
    if direction == 'outgoing':
        if user_locations.exists():
            qs = qs.filter(from_location__in=user_locations)
        else:
            qs = qs.filter(initiated_by=request.user)
    elif direction == 'incoming':
        if user_locations.exists():
            qs = qs.filter(to_location__in=user_locations)
        else:
            qs = qs.exclude(initiated_by=request.user)
    # Count pending incoming for badge
    pending_incoming_count = 0
    if user_locations.exists():
        pending_incoming_count = StockTransfer.objects.filter(
            is_deleted=False, status=TransferStatus.PENDING,
            to_location__in=user_locations,
        ).count()
    return render(request, 'pharmacy/transfer_list.html', {
        'transfers': qs[:200],
        'status_filter': status_filter,
        'statuses': TransferStatus.choices,
        'direction': direction,
        'pending_incoming_count': pending_incoming_count,
    })


@login_required
def transfer_create(request):
    if not _is_head_pharmacist(request.user):
        return HttpResponse('Access denied', status=403)
    locations = PharmacyLocation.objects.filter(is_deleted=False, is_active=True)
    if request.method == 'POST':
        from_loc = get_object_or_404(PharmacyLocation, pk=request.POST.get('from_location'))
        to_loc = get_object_or_404(PharmacyLocation, pk=request.POST.get('to_location'))
        if from_loc == to_loc:
            messages.error(request, 'Source and destination must be different.')
            return redirect('pharmacy:transfer_create')
        transfer = StockTransfer(
            from_location=from_loc, to_location=to_loc,
            initiated_by=request.user, notes=request.POST.get('notes', ''),
        )
        transfer.save()
        # Add items — form uses items-N-field pattern
        item_count = int(request.POST.get('item_count', 0))
        for i in range(item_count):
            drug_id = request.POST.get(f'items-{i}-drug_id')
            batch_id = request.POST.get(f'items-{i}-batch_id')
            qty = request.POST.get(f'items-{i}-qty')
            if not drug_id or not batch_id or not qty or int(qty) <= 0:
                continue
            drug = Drug.objects.filter(pk=drug_id).first()
            batch = DrugStock.objects.filter(pk=batch_id).first()
            if drug and batch and batch.quantity_remaining >= int(qty):
                StockTransferItem.objects.create(
                    transfer=transfer, drug=drug, stock_batch=batch, quantity=int(qty),
                )
                batch.quantity_remaining -= int(qty)
                batch.save(update_fields=['quantity_remaining'])
        messages.success(request, f'Transfer {transfer.transfer_number} created.')
        return redirect('pharmacy:transfer_list')
    drugs_with_stock = Drug.objects.filter(
        is_active=True, is_deleted=False,
        stock_items__quantity_remaining__gt=0, stock_items__is_deleted=False,
    ).filter(
        Q(stock_items__expiry_date__gte=timezone.localdate()) | Q(stock_items__expiry_date__isnull=True)
    ).distinct().prefetch_related('stock_items').order_by('name')
    return render(request, 'pharmacy/transfer_form.html', {
        'locations': locations,
        'drugs': drugs_with_stock,
    })


@login_required
def transfer_detail(request, transfer_id):
    if not _can_manage_pharmacy(request.user):
        return HttpResponse('Access denied', status=403)
    transfer = get_object_or_404(
        StockTransfer.objects.select_related('from_location', 'to_location', 'initiated_by', 'received_by'),
        pk=transfer_id, is_deleted=False
    )
    items = transfer.items.select_related('drug', 'stock_batch').all()
    return render(request, 'pharmacy/transfer_detail.html', {
        'transfer': transfer, 'items': items,
    })


@login_required
@require_POST
def transfer_action(request, transfer_id):
    if not _can_manage_pharmacy(request.user):
        return HttpResponse('Access denied', status=403)
    transfer = get_object_or_404(StockTransfer, pk=transfer_id, is_deleted=False)
    action = request.POST.get('action')
    if action == 'receive' and transfer.status == TransferStatus.PENDING:
        transfer.status = TransferStatus.RECEIVED
        transfer.received_by = request.user
        transfer.received_at = timezone.now()
        for item in transfer.items.all():
            item.quantity_received = item.quantity
            item.save(update_fields=['quantity_received'])
        transfer.save()
        messages.success(request, f'Transfer {transfer.transfer_number} received.')
    elif action == 'reject' and transfer.status == TransferStatus.PENDING:
        transfer.status = TransferStatus.REJECTED
        transfer.received_by = request.user
        transfer.received_at = timezone.now()
        transfer.rejection_reason = request.POST.get('rejection_reason', '')
        # Restore stock to sender
        for item in transfer.items.select_related('stock_batch').all():
            item.stock_batch.quantity_remaining += item.quantity
            item.stock_batch.save(update_fields=['quantity_remaining'])
        transfer.save()
        messages.warning(request, f'Transfer {transfer.transfer_number} rejected — stock restored.')
    elif action == 'cancel' and transfer.status == TransferStatus.PENDING:
        transfer.status = TransferStatus.CANCELLED
        for item in transfer.items.select_related('stock_batch').all():
            item.stock_batch.quantity_remaining += item.quantity
            item.stock_batch.save(update_fields=['quantity_remaining'])
        transfer.save()
        messages.info(request, f'Transfer {transfer.transfer_number} cancelled — stock restored.')
    return redirect('pharmacy:transfer_detail', transfer_id=transfer.pk)


# ── Cross-Store Stock Visibility ──────────────────────────────────────────

@login_required
def cross_store_stock(request):
    """View stock at other pharmacy locations — theatre can see pharmacy stock and vice versa."""
    if not _can_access_pharmacy(request.user):
        return HttpResponse('Access denied', status=403)
    locations = PharmacyLocation.objects.filter(is_deleted=False, is_active=True)
    selected_loc_id = request.GET.get('location', '')
    q = request.GET.get('q', '')
    stock_data = []
    selected_location = None
    if selected_loc_id:
        selected_location = locations.filter(pk=selected_loc_id).first()
    if selected_location:
        drugs = Drug.objects.filter(
            is_deleted=False, is_active=True, location=selected_location,
        )
        if q:
            drugs = drugs.filter(
                Q(name__icontains=q) | Q(generic_name__icontains=q)
            )
        drugs = drugs.annotate(
            avail_stock=Coalesce(
                Sum('stock_items__quantity_remaining',
                    filter=Q(stock_items__is_deleted=False) & (Q(stock_items__expiry_date__gte=timezone.localdate()) | Q(stock_items__expiry_date__isnull=True))),
                0
            ),
        ).order_by('name')[:200]
        stock_data = drugs
    return render(request, 'pharmacy/cross_store_stock.html', {
        'locations': locations,
        'selected_location': selected_location,
        'selected_loc_id': selected_loc_id,
        'stock_data': stock_data,
        'search': q,
    })


# ── Stock Exit (Non-Dispensing) ────────────────────────────────────────────

@login_required
def stock_exit_list(request):
    if not _can_manage_pharmacy(request.user):
        return HttpResponse('Access denied', status=403)
    qs = StockExit.objects.filter(is_deleted=False).select_related(
        'drug', 'stock_batch', 'authorized_by', 'witness'
    )[:200]
    return render(request, 'pharmacy/stock_exit_list.html', {'exits': qs})


@login_required
def stock_exit_create(request):
    if not _is_head_pharmacist(request.user):
        return HttpResponse('Access denied', status=403)
    if request.method == 'POST':
        drug = get_object_or_404(Drug, pk=request.POST.get('drug'))
        batch = get_object_or_404(DrugStock, pk=request.POST.get('stock_batch'))
        qty = int(request.POST.get('quantity', 0))
        if qty <= 0 or qty > batch.quantity_remaining:
            messages.error(request, f'Invalid quantity. Batch has {batch.quantity_remaining} remaining.')
            return redirect('pharmacy:stock_exit_create')
        witness_id = request.POST.get('witness')
        from apps.accounts.models import User
        witness = User.objects.filter(pk=witness_id).first() if witness_id else None
        exit_obj = StockExit(
            drug=drug, stock_batch=batch, quantity=qty,
            reason=request.POST.get('reason', 'OTHER'),
            notes=request.POST.get('notes', ''),
            disposal_method=request.POST.get('disposal_method', ''),
            authorized_by=request.user,
            witness=witness,
            waste_classification=request.POST.get('waste_classification', ''),
            destruction_certificate=request.POST.get('destruction_certificate', ''),
            financial_impact=batch.purchase_price * qty,
        )
        exit_obj.save()
        messages.success(request, f'Stock exit {exit_obj.exit_number} recorded — {qty} units removed.')
        return redirect('pharmacy:stock_exit_list')
    drugs_with_stock = Drug.objects.filter(
        is_active=True, is_deleted=False,
        stock_items__quantity_remaining__gt=0, stock_items__is_deleted=False,
    ).distinct().order_by('name')
    from apps.accounts.models import User, UserRole
    witnesses = User.objects.filter(
        role__in=[UserRole.PHARMACIST, UserRole.HEAD_PHARMACIST], is_active=True
    ).exclude(pk=request.user.pk).order_by('first_name')
    return render(request, 'pharmacy/stock_exit_form.html', {
        'drugs': drugs_with_stock,
        'reasons': StockExitReason.choices,
        'witnesses': witnesses,
    })


# ── Drug Recall Management ────────────────────────────────────────────────

@login_required
def recall_list(request):
    if not _can_manage_pharmacy(request.user):
        return HttpResponse('Access denied', status=403)
    recalls = DrugRecall.objects.filter(is_deleted=False).select_related('drug', 'reported_by')
    return render(request, 'pharmacy/recall_list.html', {'recalls': recalls})


@login_required
def recall_create(request):
    if not _is_head_pharmacist(request.user):
        return HttpResponse('Access denied', status=403)
    if request.method == 'POST':
        drug = get_object_or_404(Drug, pk=request.POST.get('drug'))
        recall = DrugRecall(
            drug=drug,
            batch_numbers=request.POST.get('batch_numbers', ''),
            reason=request.POST.get('reason', ''),
            severity=request.POST.get('severity', 'CLASS_II'),
            recall_source=request.POST.get('recall_source', ''),
            recall_type=request.POST.get('recall_type', ''),
            regulatory_reference=request.POST.get('regulatory_reference', ''),
            corrective_action=request.POST.get('corrective_action', ''),
            notes=request.POST.get('notes', ''),
            reported_by=request.user,
        )
        recall.save()
        # Quarantine affected batches
        affected = recall.get_affected_batches()
        total_quarantined = 0
        for batch in affected:
            total_quarantined += batch.quantity_remaining
            batch.quantity_remaining = 0
            batch.save(update_fields=['quantity_remaining'])
        recall.quarantined_qty = total_quarantined
        recall.patients_affected = recall.get_affected_patients().count()
        recall.save(update_fields=['quarantined_qty', 'patients_affected'])
        messages.warning(request,
            f'Recall {recall.recall_number} issued — {total_quarantined} units quarantined, '
            f'{recall.patients_affected} patients affected.'
        )
        return redirect('pharmacy:recall_list')
    drugs = Drug.objects.filter(is_active=True, is_deleted=False).order_by('name')
    return render(request, 'pharmacy/recall_form.html', {'drugs': drugs})


@login_required
def recall_detail(request, recall_id):
    if not _can_manage_pharmacy(request.user):
        return HttpResponse('Access denied', status=403)
    recall = get_object_or_404(DrugRecall, pk=recall_id, is_deleted=False)
    affected_batches = recall.get_affected_batches()
    affected_patients = recall.get_affected_patients()
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'complete':
            recall.status = RecallStatus.COMPLETED
            recall.save(update_fields=['status'])
            messages.success(request, 'Recall marked as completed.')
        elif action == 'cancel':
            recall.status = RecallStatus.CANCELLED
            recall.save(update_fields=['status'])
            messages.info(request, 'Recall cancelled.')
        return redirect('pharmacy:recall_detail', recall_id=recall.pk)
    return render(request, 'pharmacy/recall_detail.html', {
        'recall': recall,
        'affected_batches': affected_batches,
        'affected_patients': affected_patients,
    })


# ── Advanced Reports (Head Pharmacist) ─────────────────────────────────────

@login_required
def abc_analysis(request):
    """ABC Analysis — classify drugs by annual consumption value."""
    if not _is_head_pharmacist(request.user):
        return HttpResponse('Access denied', status=403)
    import datetime
    one_year_ago = timezone.localdate() - datetime.timedelta(days=365)
    # Calculate annual consumption value per drug
    drug_consumption = (
        DispensingItem.objects.filter(
            dispensing__status=DispensingStatus.DISPENSED,
            dispensing__dispensed_at__date__gte=one_year_ago,
        )
        .values('drug__id', 'drug__name', 'drug__strength')
        .annotate(
            total_qty=Sum('quantity_dispensed'),
            total_value=Sum('subtotal'),
        )
        .order_by('-total_value')
    )
    # Classify into A (70%), B (20%), C (10%)
    grand_total = sum(d['total_value'] or 0 for d in drug_consumption)
    items = []
    running = 0
    for d in drug_consumption:
        val = d['total_value'] or 0
        running += val
        pct = (running / grand_total * 100) if grand_total else 0
        if pct <= 70:
            cls = 'A'
        elif pct <= 90:
            cls = 'B'
        else:
            cls = 'C'
        items.append({**d, 'cumulative_pct': round(pct, 1), 'abc_class': cls,
                      'pct_of_total': round(val / grand_total * 100, 1) if grand_total else 0})
    counts = {'A': sum(1 for i in items if i['abc_class'] == 'A'),
              'B': sum(1 for i in items if i['abc_class'] == 'B'),
              'C': sum(1 for i in items if i['abc_class'] == 'C')}
    return render(request, 'pharmacy/report_abc.html', {
        'items': items, 'grand_total': grand_total, 'counts': counts,
    })


@login_required
def ven_analysis(request):
    """VEN Analysis — Vital / Essential / Non-essential classification."""
    if not _is_head_pharmacist(request.user):
        return HttpResponse('Access denied', status=403)
    if request.method == 'POST':
        # Bulk update VEN classifications
        for key, val in request.POST.items():
            if key.startswith('ven_'):
                drug_id = key.replace('ven_', '')
                if val in ('V', 'E', 'N', ''):
                    Drug.objects.filter(pk=drug_id, is_deleted=False).update(ven_class=val)
        messages.success(request, 'VEN classifications updated.')
        return redirect('pharmacy:ven_analysis')
    drugs = Drug.objects.filter(is_active=True, is_deleted=False).order_by('name')
    # Single aggregate instead of 4 separate count() queries
    summary = drugs.aggregate(
        V=Count('id', filter=Q(ven_class='V')),
        E=Count('id', filter=Q(ven_class='E')),
        N=Count('id', filter=Q(ven_class='N')),
        unclassified=Count('id', filter=Q(ven_class='')),
    )
    return render(request, 'pharmacy/report_ven.html', {'drugs': drugs, 'summary': summary})


@login_required
def dead_stock_report(request):
    """Dead Stock — items with zero movement for 90+ days."""
    if not _is_head_pharmacist(request.user):
        return HttpResponse('Access denied', status=403)
    import datetime
    days = int(request.GET.get('days', 90))
    cutoff = timezone.localdate() - datetime.timedelta(days=days)
    # Drugs with stock but no dispensing since cutoff
    dispensed_drug_ids = (
        DispensingItem.objects.filter(
            dispensing__dispensed_at__date__gte=cutoff,
            dispensing__status=DispensingStatus.DISPENSED,
        ).values_list('drug_id', flat=True).distinct()
    )
    dead_drugs = list(Drug.objects.filter(
        is_active=True, is_deleted=False,
    ).exclude(
        id__in=dispensed_drug_ids
    ).annotate(
        stock_total=Coalesce(
            Sum('stock_items__quantity_remaining',
                filter=Q(stock_items__is_deleted=False) & (Q(stock_items__expiry_date__gte=timezone.localdate()) | Q(stock_items__expiry_date__isnull=True))),
            Value(0, output_field=IntegerField())
        ),
        last_dispensed=Max(
            'dispensingitem__dispensing__dispensed_at',
            filter=Q(dispensingitem__dispensing__status=DispensingStatus.DISPENSED),
        ),
    ).filter(stock_total__gt=0).order_by('-stock_total'))
    for d in dead_drugs:
        d.stock_value = d.stock_total * float(d.selling_price)
    total_value_at_risk = sum(d.stock_value for d in dead_drugs)
    return render(request, 'pharmacy/report_dead_stock.html', {
        'drugs': dead_drugs, 'days': days, 'total_value_at_risk': total_value_at_risk,
    })


@login_required
def consumption_report(request):
    """Drug Consumption Report — monthly trends per drug."""
    if not _is_head_pharmacist(request.user):
        return HttpResponse('Access denied', status=403)
    import datetime
    from django.db.models.functions import TruncMonth
    months = int(request.GET.get('months', 6))
    cutoff = timezone.localdate() - datetime.timedelta(days=months * 30)
    monthly = (
        DispensingItem.objects.filter(
            dispensing__status=DispensingStatus.DISPENSED,
            dispensing__dispensed_at__date__gte=cutoff,
        )
        .annotate(month=TruncMonth('dispensing__dispensed_at'))
        .values('month', 'drug__id', 'drug__name')
        .annotate(qty=Sum('quantity_dispensed'), value=Sum('subtotal'))
        .order_by('drug__name', 'month')
    )
    # Group by drug
    from collections import defaultdict
    by_drug = defaultdict(list)
    for row in monthly:
        by_drug[row['drug__name']].append(row)
    return render(request, 'pharmacy/report_consumption.html', {
        'by_drug': dict(by_drug), 'months': months,
    })


@login_required
def turnover_report(request):
    """Stock Turnover — how fast each drug moves."""
    if not _is_head_pharmacist(request.user):
        return HttpResponse('Access denied', status=403)
    import datetime
    one_year_ago = timezone.localdate() - datetime.timedelta(days=365)
    drugs = Drug.objects.filter(is_active=True, is_deleted=False).annotate(
        stock_total=Coalesce(
            Sum('stock_items__quantity_remaining',
                filter=Q(stock_items__is_deleted=False) & (Q(stock_items__expiry_date__gte=timezone.localdate()) | Q(stock_items__expiry_date__isnull=True))),
            Value(0, output_field=IntegerField())
        ),
        annual_dispensed=Coalesce(
            Sum('dispensingitem__quantity_dispensed',
                filter=Q(dispensingitem__dispensing__status=DispensingStatus.DISPENSED,
                          dispensingitem__dispensing__dispensed_at__date__gte=one_year_ago)),
            Value(0, output_field=IntegerField())
        ),
    ).filter(stock_total__gt=0).order_by('name')
    items = []
    for d in drugs:
        avg_stock = d.stock_total
        ratio = round(d.annual_dispensed / avg_stock, 1) if avg_stock > 0 else 0
        days_of_stock = round(avg_stock / (d.annual_dispensed / 365), 0) if d.annual_dispensed > 0 else 999
        items.append({
            'drug': d, 'stock': d.stock_total, 'dispensed': d.annual_dispensed,
            'turnover_ratio': ratio, 'days_of_stock': int(days_of_stock),
        })
    items.sort(key=lambda x: x['turnover_ratio'])
    return render(request, 'pharmacy/report_turnover.html', {'items': items})


@login_required
def productivity_report(request):
    """Pharmacist Productivity — dispensings per pharmacist per day."""
    if not _is_head_pharmacist(request.user):
        return HttpResponse('Access denied', status=403)
    import datetime
    from django.db.models.functions import TruncDate
    days = int(request.GET.get('days', 30))
    cutoff = timezone.localdate() - datetime.timedelta(days=days)
    # Per pharmacist summary
    by_pharmacist = (
        Dispensing.objects.filter(
            status=DispensingStatus.DISPENSED,
            dispensed_at__date__gte=cutoff, is_deleted=False,
        )
        .values('dispensed_by__id', 'dispensed_by__first_name', 'dispensed_by__last_name')
        .annotate(
            total_dispensings=Count('id'),
            total_items=Sum('items__quantity_dispensed'),
            total_value=Sum('total_amount'),
        )
        .order_by('-total_dispensings')
    )
    # Daily trend
    daily = (
        Dispensing.objects.filter(
            status=DispensingStatus.DISPENSED,
            dispensed_at__date__gte=cutoff, is_deleted=False,
        )
        .annotate(day=TruncDate('dispensed_at'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    return render(request, 'pharmacy/report_productivity.html', {
        'by_pharmacist': by_pharmacist, 'daily': list(daily), 'days': days,
    })


# ── SAGE-Style Reports ─────────────────────────────────────────────────────

@login_required
def stock_situation_report(request):
    """Stock Situation / Inventory Valuation — current stock with cost and selling value."""
    if not _is_head_pharmacist(request.user):
        return HttpResponse('Access denied', status=403)
    location_id = request.GET.get('location', '')
    q = request.GET.get('q', '')
    drugs = Drug.objects.filter(is_active=True, is_deleted=False).annotate(
        stock_qty=Coalesce(
            Sum('stock_items__quantity_remaining',
                filter=Q(stock_items__is_deleted=False) & (Q(stock_items__expiry_date__gte=timezone.localdate()) | Q(stock_items__expiry_date__isnull=True))),
            Value(0, output_field=IntegerField())
        ),
    )
    if location_id:
        drugs = drugs.filter(location_id=location_id)
    if q:
        drugs = drugs.filter(Q(name__icontains=q) | Q(generic_name__icontains=q))
    drugs = drugs.order_by('name')
    items = []
    total_cost_val = 0
    total_sell_val = 0
    for d in drugs:
        cost_val = d.stock_qty * float(d.cost_price)
        sell_val = d.stock_qty * float(d.selling_price)
        total_cost_val += cost_val
        total_sell_val += sell_val
        items.append({
            'drug': d, 'stock_qty': d.stock_qty,
            'cost_val': cost_val, 'sell_val': sell_val,
        })
    locations = PharmacyLocation.objects.filter(is_deleted=False, is_active=True)
    return render(request, 'pharmacy/report_stock_situation.html', {
        'items': items, 'total_cost': total_cost_val, 'total_sell': total_sell_val,
        'locations': locations, 'location_id': location_id, 'search': q,
    })


@login_required
def sales_journal(request):
    """Sales Journal — daily dispensing log with line items and totals."""
    if not _is_head_pharmacist(request.user):
        return HttpResponse('Access denied', status=403)
    import datetime
    date_str = request.GET.get('date', '')
    try:
        report_date = datetime.date.fromisoformat(date_str)
    except (ValueError, TypeError):
        report_date = timezone.localdate()
    dispensings = Dispensing.objects.filter(
        dispensed_at__date=report_date,
        status=DispensingStatus.DISPENSED,
        is_deleted=False,
    ).select_related('patient', 'dispensed_by').prefetch_related('items__drug').order_by('dispensed_at')
    total_sales = dispensings.aggregate(t=Sum('total_amount'))['t'] or 0
    total_discount = dispensings.aggregate(t=Sum('discount'))['t'] or 0
    otc_count = dispensings.filter(is_otc=True).count()
    rx_count = dispensings.filter(is_otc=False).count()
    return render(request, 'pharmacy/report_sales_journal.html', {
        'dispensings': dispensings, 'report_date': report_date,
        'total_sales': total_sales, 'total_discount': total_discount,
        'otc_count': otc_count, 'rx_count': rx_count,
    })


@login_required
def expiring_stock_report(request):
    """Near-Expiry Stock — drugs expiring within N days."""
    if not _is_head_pharmacist(request.user):
        return HttpResponse('Access denied', status=403)
    import datetime
    days = int(request.GET.get('days', 90))
    cutoff = timezone.localdate() + datetime.timedelta(days=days)
    today = timezone.localdate()
    batches = DrugStock.objects.filter(
        is_deleted=False, quantity_remaining__gt=0,
        expiry_date__lte=cutoff,
    ).select_related('drug').order_by('expiry_date')
    total_qty = 0
    total_value = 0
    items = []
    for b in batches:
        val = b.quantity_remaining * float(b.drug.cost_price)
        total_qty += b.quantity_remaining
        total_value += val
        items.append({
            'batch': b, 'value': val,
            'is_expired': b.expiry_date < today,
            'days_left': (b.expiry_date - today).days,
        })
    return render(request, 'pharmacy/report_expiring.html', {
        'items': items, 'days': days, 'total_qty': total_qty, 'total_value': total_value,
    })


@login_required
def supplier_purchase_history(request):
    """Supplier Purchase History — all POs grouped by supplier."""
    if not _is_head_pharmacist(request.user):
        return HttpResponse('Access denied', status=403)
    import datetime
    supplier_id = request.GET.get('supplier', '')
    months = int(request.GET.get('months', 12))
    cutoff = timezone.localdate() - datetime.timedelta(days=months * 30)
    suppliers = Supplier.objects.filter(is_deleted=False).order_by('name')
    orders = PurchaseOrder.objects.filter(
        is_deleted=False, order_date__gte=cutoff,
    ).select_related('supplier').prefetch_related('items__drug')
    if supplier_id:
        orders = orders.filter(supplier_id=supplier_id)
    orders = orders.order_by('-order_date')
    total_amount = orders.aggregate(t=Sum('total_amount'))['t'] or 0
    return render(request, 'pharmacy/report_supplier_history.html', {
        'orders': orders[:200], 'suppliers': suppliers,
        'supplier_id': supplier_id, 'months': months, 'total_amount': total_amount,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# BARCODE LABEL GENERATION & PRINTING
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def barcode_labels_view(request):
    """Generate printable barcode sticker labels for selected drugs."""
    if not _can_manage_pharmacy(request.user):
        messages.error(request, 'Permission denied.')
        return redirect('pharmacy:dashboard')

    drug_ids = request.GET.getlist('drugs')
    copies = int(request.GET.get('copies', 1))
    copies = min(max(copies, 1), 50)  # 1-50 copies
    print_all = request.GET.get('all') == '1'
    location_id = request.GET.get('location', '').strip()

    if drug_ids:
        drugs = Drug.objects.filter(id__in=drug_ids, is_deleted=False)
    elif print_all:
        drugs = Drug.objects.filter(is_active=True, is_deleted=False).order_by('name')
        if location_id:
            drugs = drugs.filter(location_id=location_id)
    else:
        drugs = Drug.objects.filter(is_active=True, is_deleted=False).order_by('name')[:50]

    # Auto-generate barcodes for any drugs missing them
    for drug in drugs:
        if not drug.barcode:
            drug.save()  # triggers auto-generate in save()

    # Generate barcode SVGs inline
    import io
    try:
        import barcode
        from barcode.writer import SVGWriter
    except ImportError:
        messages.error(request, 'python-barcode library not installed.')
        return redirect('pharmacy:drug_list')

    drug_labels = []
    for drug in drugs:
        svg_io = io.BytesIO()
        code128 = barcode.get('code128', drug.barcode, writer=SVGWriter())
        code128.write(svg_io, options={
            'module_width': 0.3,
            'module_height': 8,
            'font_size': 8,
            'text_distance': 2,
            'quiet_zone': 2,
        })
        svg_str = svg_io.getvalue().decode('utf-8')
        # Strip XML declaration for inline embedding
        if '?>' in svg_str:
            svg_str = svg_str[svg_str.index('?>') + 2:]
        # Remove fixed width/height from SVG tag so CSS controls sizing
        svg_str = re.sub(r'\s+width="[^"]*"', '', svg_str, count=1)
        svg_str = re.sub(r'\s+height="[^"]*"', '', svg_str, count=1)
        for _ in range(copies):
            drug_labels.append({
                'drug': drug,
                'svg': svg_str,
            })

    from apps.accounts.models import HospitalConfig
    config = HospitalConfig.get()

    return render(request, 'pharmacy/barcode_labels.html', {
        'labels': drug_labels,
        'config': config,
        'copies': copies,
    })


@login_required
def generate_barcodes_bulk(request):
    """POST: auto-generate barcodes for all drugs that don't have one."""
    if not _can_manage_pharmacy(request.user):
        messages.error(request, 'Permission denied.')
        return redirect('pharmacy:dashboard')

    drugs_without = Drug.objects.filter(
        is_active=True, is_deleted=False
    ).filter(Q(barcode__isnull=True) | Q(barcode=''))
    count = 0
    for drug in drugs_without:
        drug.save()  # triggers auto-generate
        count += 1
    messages.success(request, f'Generated barcodes for {count} drugs.')
    return redirect('pharmacy:drug_list')


# ═══════════════════════════════════════════════════════════════════════════════
# DEDICATED RECEIVE STOCK PAGE
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def receive_stock(request):
    """Standalone stock receiving — add new deliveries without navigating Drug & Stock."""
    if not _can_manage_pharmacy(request.user):
        return HttpResponse('Access denied', status=403)

    suppliers = Supplier.objects.filter(is_deleted=False).order_by('name')
    drugs = Drug.objects.filter(is_active=True, is_deleted=False).order_by('name')

    if request.method == 'POST':
        line_count = int(request.POST.get('line_count', 0))
        created = 0
        for i in range(line_count):
            drug_id = request.POST.get(f'lines-{i}-drug_id')
            batch_number = request.POST.get(f'lines-{i}-batch_number', '').strip()
            quantity = request.POST.get(f'lines-{i}-quantity')
            expiry = request.POST.get(f'lines-{i}-expiry_date', '').strip()
            purchase_price = request.POST.get(f'lines-{i}-purchase_price', '0')
            supplier_name = request.POST.get(f'lines-{i}-supplier', '').strip()
            notes = request.POST.get(f'lines-{i}-notes', '').strip()
            manufacture_date = request.POST.get(f'lines-{i}-manufacture_date', '').strip()

            if not drug_id or not quantity or int(quantity) <= 0:
                continue
            drug = Drug.objects.filter(pk=drug_id, is_deleted=False).first()
            if not drug:
                continue
            import datetime
            exp_date = None
            if expiry:
                try:
                    exp_date = datetime.date.fromisoformat(expiry)
                except ValueError:
                    pass
            mfg_date = None
            if manufacture_date:
                try:
                    mfg_date = datetime.date.fromisoformat(manufacture_date)
                except ValueError:
                    pass
            qty = int(quantity)
            price = float(purchase_price) if purchase_price else 0
            DrugStock.objects.create(
                drug=drug,
                batch_number=batch_number or f"RCV-{timezone.localdate().strftime('%Y%m%d')}-{i+1:03d}",
                expiry_date=exp_date,
                manufacture_date=mfg_date,
                quantity_received=qty,
                quantity_remaining=qty,
                supplier=supplier_name,
                purchase_price=price,
                received_date=timezone.localdate(),
                notes=notes,
                created_by=request.user,
            )
            created += 1

        if created:
            messages.success(request, f'{created} stock batch{"es" if created != 1 else ""} received successfully.')
        else:
            messages.warning(request, 'No valid stock lines to receive.')
        return redirect('pharmacy:receive_stock')

    # Recent stock receipts (last 20)
    recent = DrugStock.objects.filter(
        is_deleted=False,
        received_date__gte=timezone.localdate() - timezone.timedelta(days=7),
    ).select_related('drug').order_by('-created_at')[:20]

    return render(request, 'pharmacy/receive_stock.html', {
        'drugs': drugs,
        'suppliers': suppliers,
        'recent': recent,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# STOCK BULK IMPORT — CSV / Excel upload for receiving deliveries
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def stock_import_template(request):
    """Download a blank Excel template for bulk stock receiving."""
    if not _can_manage_pharmacy(request.user):
        return HttpResponse('Access denied', status=403)

    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Stock Import'

    headers = [
        'drug_name', 'batch_number', 'quantity', 'expiry_date',
        'manufacture_date', 'cost_price', 'supplier', 'notes',
    ]
    hints = [
        'REQUIRED — must match an existing drug in the formulary',
        'Optional — auto-generated if blank',
        'REQUIRED — whole number',
        'Optional — DD/MM/YYYY',
        'Optional — DD/MM/YYYY',
        'FCFA per unit (0 if blank)',
        'Optional — supplier name',
        'Optional — any notes',
    ]
    thin = Side(border_style='thin', color='CCCCCC')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for col, (h, hint) in enumerate(zip(headers, hints), 1):
        hc = ws.cell(row=1, column=col, value=h)
        hc.font = Font(bold=True, color='FFFFFF', size=10)
        hc.fill = PatternFill(fill_type='solid', fgColor='1E3A5F')
        hc.alignment = Alignment(horizontal='center', wrap_text=True)
        hc.border = border
        hintc = ws.cell(row=2, column=col, value=hint)
        hintc.font = Font(italic=True, color='555555', size=9)
        hintc.fill = PatternFill(fill_type='solid', fgColor='E8F0FE')
        hintc.alignment = Alignment(wrap_text=True)
        hintc.border = border

    sample = ['Ciprofloxacin 500mg', 'BATCH-2026-001', 100, '31/12/2027', '', 1400, 'PharmaCo Ltd', '']
    for col, val in enumerate(sample, 1):
        c = ws.cell(row=3, column=col, value=val)
        c.fill = PatternFill(fill_type='solid', fgColor='F0FFF0')
        c.border = border

    for i, w in enumerate([28, 20, 10, 14, 14, 12, 22, 20], 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 28
    ws.row_dimensions[2].height = 36
    ws.freeze_panes = 'A4'

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="EHR_Stock_Import_Template.xlsx"'
    wb.save(response)
    return response


@login_required
def stock_bulk_import(request):
    """Upload Excel/CSV to bulk-receive stock batches for existing drugs."""
    if not _can_manage_pharmacy(request.user):
        return HttpResponse('Access denied', status=403)

    if request.method != 'POST':
        return redirect('pharmacy:receive_stock')

    uploaded = request.FILES.get('import_file')
    if not uploaded:
        messages.error(request, 'No file selected.')
        return redirect('pharmacy:receive_stock')

    filename = uploaded.name.lower()
    rows = []
    try:
        if filename.endswith('.xlsx') or filename.endswith('.xls'):
            import openpyxl
            wb = openpyxl.load_workbook(uploaded, data_only=True)
            ws = wb.active
            all_rows = list(ws.iter_rows(values_only=True))
            if len(all_rows) < 3:
                messages.error(request, 'File has no data rows (need header + hint + at least 1 data row).')
                return redirect('pharmacy:receive_stock')
            headers = [str(h).strip().lower().replace(' ', '_') if h else '' for h in all_rows[0]]
            for raw in all_rows[2:]:  # skip header + hint row
                if all(v is None for v in raw):
                    continue
                rows.append(dict(zip(headers, raw)))
        elif filename.endswith('.csv'):
            import csv, io
            content = uploaded.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content))
            reader.fieldnames = [f.strip().lower().replace(' ', '_') for f in (reader.fieldnames or [])]
            for row in reader:
                rows.append({k.strip().lower().replace(' ', '_'): v for k, v in row.items()})
        else:
            messages.error(request, 'Unsupported format — upload .xlsx or .csv only.')
            return redirect('pharmacy:receive_stock')
    except Exception as e:
        messages.error(request, f'Could not read file: {e}')
        return redirect('pharmacy:receive_stock')

    created = skipped = 0
    errors_list = []
    today = timezone.localdate()

    for i, row in enumerate(rows, start=3):
        drug_name = _str(row.get('drug_name') or row.get('name', ''))
        if not drug_name:
            skipped += 1
            continue
        drug = Drug.objects.filter(
            Q(name__iexact=drug_name) | Q(name__icontains=drug_name),
            is_active=True, is_deleted=False,
        ).first()
        if not drug:
            errors_list.append(f'Row {i}: drug "{drug_name}" not found in formulary — skipped.')
            skipped += 1
            continue

        qty = _int(row.get('quantity') or row.get('qty'), 0)
        if qty <= 0:
            errors_list.append(f'Row {i} ({drug_name}): quantity must be > 0 — skipped.')
            skipped += 1
            continue

        batch_number = _str(row.get('batch_number', ''))
        expiry_date = _parse_date(row.get('expiry_date'))
        mfg_date = _parse_date(row.get('manufacture_date'))
        cost = _dec(row.get('cost_price') or row.get('purchase_price', '0'))
        supplier = _str(row.get('supplier') or row.get('supplier_name', ''))
        notes = _str(row.get('notes', ''))

        if expiry_date and expiry_date < today:
            errors_list.append(f'Row {i} ({drug_name}): expired batch ({expiry_date}) — skipped.')
            skipped += 1
            continue

        if not batch_number:
            batch_number = f"IMP-{today.strftime('%Y%m%d')}-{i:04d}"

        DrugStock.objects.create(
            drug=drug,
            batch_number=batch_number,
            expiry_date=expiry_date,
            manufacture_date=mfg_date,
            quantity_received=qty,
            quantity_remaining=qty,
            purchase_price=cost,
            supplier=supplier,
            received_date=today,
            notes=notes,
            created_by=request.user,
        )
        created += 1

    if created:
        messages.success(request, f'{created} stock batch{"es" if created != 1 else ""} imported successfully.')
    if skipped:
        messages.warning(request, f'{skipped} row{"s" if skipped != 1 else ""} skipped.')
    if errors_list:
        messages.info(request, ' | '.join(errors_list[:10]))
    if not created and not skipped:
        messages.warning(request, 'No valid rows found in the file.')
    return redirect('pharmacy:receive_stock')


# ═══════════════════════════════════════════════════════════════════════════════
# STOCK MOVEMENT LOG — Unified Audit Trail
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def stock_movement_log(request):
    """Unified chronological log of all stock movements."""
    if not _can_manage_pharmacy(request.user):
        return HttpResponse('Access denied', status=403)
    import datetime
    from itertools import chain
    from operator import attrgetter

    days = int(request.GET.get('days', 30))
    movement_type = request.GET.get('type', '')
    drug_search = request.GET.get('q', '').strip()
    cutoff = timezone.now() - datetime.timedelta(days=days)

    movements = []

    # 1) Stock Received
    if not movement_type or movement_type == 'received':
        received_qs = DrugStock.objects.filter(
            is_deleted=False, created_at__gte=cutoff,
        ).select_related('drug')
        if drug_search:
            received_qs = received_qs.filter(
                Q(drug__name__icontains=drug_search) | Q(drug__generic_name__icontains=drug_search)
            )
        for s in received_qs:
            movements.append({
                'date': s.created_at,
                'type': 'Received',
                'type_class': 'success',
                'drug': s.drug.name,
                'drug_strength': s.drug.strength or '',
                'batch': s.batch_number,
                'qty': f'+{s.quantity_received}',
                'detail': f'Supplier: {s.supplier or "N/A"}',
                'user': s.created_by.get_full_name() if s.created_by else '--',
            })

    # 2) Dispensed
    if not movement_type or movement_type == 'dispensed':
        disp_qs = DispensingItem.objects.filter(
            dispensing__status=DispensingStatus.DISPENSED,
            dispensing__dispensed_at__gte=cutoff,
            dispensing__is_deleted=False,
        ).select_related('drug', 'dispensing', 'dispensing__dispensed_by')
        if drug_search:
            disp_qs = disp_qs.filter(
                Q(drug__name__icontains=drug_search) | Q(drug__generic_name__icontains=drug_search)
            )
        for di in disp_qs:
            movements.append({
                'date': di.dispensing.dispensed_at,
                'type': 'Dispensed',
                'type_class': 'primary',
                'drug': di.drug.name,
                'drug_strength': di.drug.strength or '',
                'batch': di.stock_batch.batch_number if di.stock_batch else '--',
                'qty': f'-{di.quantity_dispensed}',
                'detail': f'Rx: {di.dispensing.dispensing_number}',
                'user': di.dispensing.dispensed_by.get_full_name() if di.dispensing.dispensed_by else '--',
            })

    # 3) Transfers Out
    if not movement_type or movement_type == 'transfer_out':
        tout_qs = StockTransferItem.objects.filter(
            transfer__status__in=[TransferStatus.PENDING, TransferStatus.RECEIVED, TransferStatus.IN_TRANSIT],
            transfer__initiated_at__gte=cutoff,
            transfer__is_deleted=False,
        ).select_related('drug', 'transfer', 'transfer__from_location', 'transfer__to_location', 'transfer__initiated_by')
        if drug_search:
            tout_qs = tout_qs.filter(
                Q(drug__name__icontains=drug_search) | Q(drug__generic_name__icontains=drug_search)
            )
        for ti in tout_qs:
            movements.append({
                'date': ti.transfer.initiated_at,
                'type': 'Transfer Out',
                'type_class': 'warning',
                'drug': ti.drug.name,
                'drug_strength': ti.drug.strength or '',
                'batch': ti.stock_batch.batch_number if ti.stock_batch else '--',
                'qty': f'-{ti.quantity}',
                'detail': f'{ti.transfer.from_location} → {ti.transfer.to_location}',
                'user': ti.transfer.initiated_by.get_full_name() if ti.transfer.initiated_by else '--',
            })

    # 4) Transfers In (received)
    if not movement_type or movement_type == 'transfer_in':
        tin_qs = StockTransferItem.objects.filter(
            transfer__status=TransferStatus.RECEIVED,
            transfer__received_at__gte=cutoff,
            transfer__is_deleted=False,
        ).select_related('drug', 'transfer', 'transfer__from_location', 'transfer__to_location', 'transfer__received_by')
        if drug_search:
            tin_qs = tin_qs.filter(
                Q(drug__name__icontains=drug_search) | Q(drug__generic_name__icontains=drug_search)
            )
        for ti in tin_qs:
            movements.append({
                'date': ti.transfer.received_at,
                'type': 'Transfer In',
                'type_class': 'info',
                'drug': ti.drug.name,
                'drug_strength': ti.drug.strength or '',
                'batch': ti.stock_batch.batch_number if ti.stock_batch else '--',
                'qty': f'+{ti.quantity_received}',
                'detail': f'{ti.transfer.from_location} → {ti.transfer.to_location}',
                'user': ti.transfer.received_by.get_full_name() if ti.transfer.received_by else '--',
            })

    # 5) Stock Adjustments
    if not movement_type or movement_type == 'adjusted':
        adj_qs = StockAdjustment.objects.filter(
            is_deleted=False, created_at__gte=cutoff,
        ).select_related('batch__drug', 'created_by')
        if drug_search:
            adj_qs = adj_qs.filter(
                Q(batch__drug__name__icontains=drug_search) | Q(batch__drug__generic_name__icontains=drug_search)
            )
        for a in adj_qs:
            sign = '+' if a.quantity_change > 0 else ''
            movements.append({
                'date': a.created_at,
                'type': 'Adjustment',
                'type_class': 'secondary',
                'drug': a.batch.drug.name,
                'drug_strength': a.batch.drug.strength or '',
                'batch': a.batch.batch_number,
                'qty': f'{sign}{a.quantity_change}',
                'detail': f'{a.get_reason_display()}',
                'user': a.created_by.get_full_name() if a.created_by else '--',
            })

    # 6) Stock Exits
    if not movement_type or movement_type == 'exit':
        exit_qs = StockExit.objects.filter(
            is_deleted=False, exit_date__gte=cutoff,
        ).select_related('drug', 'stock_batch', 'authorized_by')
        if drug_search:
            exit_qs = exit_qs.filter(
                Q(drug__name__icontains=drug_search) | Q(drug__generic_name__icontains=drug_search)
            )
        for ex in exit_qs:
            movements.append({
                'date': ex.exit_date,
                'type': f'Exit ({ex.get_reason_display()})',
                'type_class': 'danger',
                'drug': ex.drug.name,
                'drug_strength': ex.drug.strength or '',
                'batch': ex.stock_batch.batch_number,
                'qty': f'-{ex.quantity}',
                'detail': ex.disposal_method or ex.notes or '--',
                'user': ex.authorized_by.get_full_name() if ex.authorized_by else '--',
            })

    # Sort by date descending
    movements.sort(key=lambda x: x['date'], reverse=True)

    # Limit to 500
    movements = movements[:500]

    movement_types = [
        ('', 'All Movements'),
        ('received', 'Stock Received'),
        ('dispensed', 'Dispensed'),
        ('transfer_out', 'Transfers Out'),
        ('transfer_in', 'Transfers In'),
        ('adjusted', 'Adjustments'),
        ('exit', 'Stock Exits'),
    ]

    return render(request, 'pharmacy/stock_movement_log.html', {
        'movements': movements,
        'days': days,
        'movement_type': movement_type,
        'drug_search': drug_search,
        'movement_types': movement_types,
        'total_count': len(movements),
    })
