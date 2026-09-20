from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Count, Avg, Q, Sum
from datetime import timedelta
from .models import (
    LabOrder, LabOrderItem, LabResult, LabTestType, SampleCollection,
    SampleRejection, LabResultAmendment, OrderSet, PaymentStatus,
    SpecimenStatus, ResultStatus, ResultAcknowledgment, QCRecord,
    AutoverificationRule, SendOutTest, CultureResult, OrganismIdentification,
    AntibioticSensitivity, CumulativeAntibiogram, HistopathologySpecimen,
    TATTimestamp,
)
from .forms import LabOrderForm, LabResultFormSet, SampleCollectionForm
from apps.consultations.models import Consultation


def _log_tat(order, event, user=None, notes=''):
    """Record a TAT timestamp for audit trail."""
    TATTimestamp.objects.create(order=order, event=event, user=user, notes=notes)


@login_required
def lab_dashboard(request):
    """
    Lab technician workstation — Clinical Pipeline.
    Only shows PAID orders. Pipeline: Checked In → Sample Collected → Processing → Done.
    """
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_admin_staff):
        return HttpResponseForbidden()

    today = timezone.localdate()
    now_dt = timezone.now()
    month_start = today.replace(day=1)
    week_ago = today - timedelta(days=7)

    # ── Only paid orders are actionable ──────────────────────────────────────
    _paid_statuses = ['PAID', 'INSURED', 'WAIVED', 'STAT_OVERRIDE', 'PREPAID', 'BILL_LATER']

    _base_qs = LabOrder.objects.filter(
        is_deleted=False, created_at__date__gte=week_ago,
    ).select_related('patient', 'ordered_by').prefetch_related('items__test_type')

    # ── Pipeline stages ──────────────────────────────────────────────────────
    # 1. Checked In — patient arrived, waiting for phlebotomy
    checked_in_orders = list(
        _base_qs.filter(
            payment_status__in=_paid_statuses,
            checked_in_at__isnull=False,
            status='ORDERED',
        ).order_by('urgency', 'checked_in_at')
    )

    # 2. Sample Collected — sample taken, waiting for processing
    sample_collected_orders = list(
        _base_qs.filter(
            payment_status__in=_paid_statuses,
            status='SAMPLE_COLLECTED',
        ).order_by('urgency', 'updated_at')
    )

    # 3. Processing — analysis in progress
    processing_orders = list(
        _base_qs.filter(
            payment_status__in=_paid_statuses,
            status='PROCESSING',
        ).order_by('urgency', 'updated_at')
    )

    # 4. Expected Arrivals — paid but NOT yet checked in
    expected_arrivals = list(
        _base_qs.filter(
            payment_status__in=_paid_statuses,
            checked_in_at__isnull=True,
            status='ORDERED',
        ).order_by('urgency', 'created_at')
    )

    # ── Elapsed time annotations ─────────────────────────────────────────────
    for o in checked_in_orders:
        if o.checked_in_at:
            delta = now_dt - o.checked_in_at
            o.wait_minutes = int(delta.total_seconds() / 60)
        else:
            o.wait_minutes = 0

    for o in (sample_collected_orders + processing_orders):
        delta = now_dt - o.created_at
        total_mins = int(delta.total_seconds() // 60)
        if total_mins < 60:
            o.elapsed = f'{total_mins}m'
        else:
            o.elapsed = f'{total_mins // 60}h {total_mins % 60}m'
        o.elapsed_mins = total_mins

    # ── Critical results (unverified) ────────────────────────────────────────
    critical_unverified = LabResult.objects.filter(
        is_critical=True, is_verified=False,
        is_deleted=False,
        order_item__is_deleted=False,
        order_item__order__is_deleted=False,
    ).select_related('order_item__order__patient', 'order_item__test_type')

    # ── Completed today ──────────────────────────────────────────────────────
    completed_today_count = LabOrder.objects.filter(
        status='COMPLETED', is_deleted=False,
        updated_at__date=today,
    ).count()

    completed_today_list = list(
        LabOrder.objects.filter(
            status='COMPLETED', is_deleted=False,
            updated_at__date=today,
        ).select_related('patient', 'ordered_by')
        .prefetch_related('items__test_type', 'items__result')
        .order_by('-updated_at')[:30]
    )

    # ── Month summary stats ──────────────────────────────────────────────────
    completed_this_month = LabOrder.objects.filter(
        status='COMPLETED', is_deleted=False,
        updated_at__date__gte=month_start,
    ).count()

    abnormal_count = LabResult.objects.filter(
        is_abnormal=True, is_deleted=False,
        created_at__date__gte=month_start,
    ).count()

    category_stats = (
        LabOrderItem.objects.filter(
            order__is_deleted=False,
            order__created_at__date__gte=month_start,
        )
        .values('test_type__category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    context = {
        'checked_in_orders': checked_in_orders,
        'sample_collected_orders': sample_collected_orders,
        'processing_orders': processing_orders,
        'expected_arrivals': expected_arrivals,
        'checked_in_count': len(checked_in_orders),
        'sample_collected_count': len(sample_collected_orders),
        'processing_count': len(processing_orders),
        'expected_count': len(expected_arrivals),
        'completed_today': completed_today_count,
        'completed_today_list': completed_today_list,
        'completed_this_month': completed_this_month,
        'critical_unverified': critical_unverified,
        'critical_count': critical_unverified.count(),
        'abnormal_count': abnormal_count,
        'category_stats': category_stats,
        'today': today,
    }
    return render(request, 'laboratory/dashboard.html', context)


@login_required
@require_POST
def lab_check_in_view(request, pk):
    """Check in patient — they have physically arrived at the lab."""
    if not (request.user.is_lab_tech or request.user.is_admin_staff):
        return HttpResponseForbidden()
    order = get_object_or_404(LabOrder, pk=pk, is_deleted=False)
    if not order.checked_in_at:
        order.checked_in_at = timezone.now()
        order.checked_in_by = request.user
        order.save(update_fields=['checked_in_at', 'checked_in_by', 'updated_at'])
        messages.success(request, f'{order.patient.full_name} checked in at lab.')
    return redirect('laboratory:dashboard')


@login_required
@require_POST
def lab_bulk_check_in_view(request):
    """Bulk check-in multiple patients at once."""
    if not (request.user.is_lab_tech or request.user.is_admin_staff):
        return HttpResponseForbidden()
    order_ids = request.POST.getlist('order_ids')
    if order_ids:
        now = timezone.now()
        updated = LabOrder.objects.filter(
            pk__in=order_ids,
            checked_in_at__isnull=True,
            is_deleted=False,
        ).update(
            checked_in_at=now,
            checked_in_by=request.user,
            updated_at=now,
        )
        messages.success(request, f'{updated} patient(s) checked in at lab.')
    return redirect('laboratory:dashboard')


@login_required
def lab_list_view(request):
    orders = (LabOrder.objects
              .select_related('patient', 'ordered_by')
              .prefetch_related('items__test_type')
              .filter(is_deleted=False))

    if not (request.user.is_medical_director or request.user.is_admin_staff or request.user.is_lab_tech):
        orders = orders.filter(ordered_by=request.user)

    status_filter = request.GET.get('status', '')
    if status_filter:
        orders = orders.filter(status=status_filter)

    urgency_filter = request.GET.get('urgency', '')
    if urgency_filter:
        orders = orders.filter(urgency=urgency_filter)

    patient_id_filter = request.GET.get('patient_id', '').strip()
    if patient_id_filter:
        orders = orders.filter(patient__patient_id__iexact=patient_id_filter)

    orders = orders.order_by('-created_at')

    return render(request, 'laboratory/list.html', {
        'orders': orders[:200],
        'status_choices': LabOrder.Status.choices,
        'urgency_choices': [('ROUTINE','Routine'),('URGENT','Urgent'),('EMERGENCY','Emergency')],
        'status_filter': status_filter,
        'urgency_filter': urgency_filter,
        'patient_id_filter': patient_id_filter,
    })


@login_required
def lab_stats_view(request):
    """Monthly statistics for lab — WHO-standard demographics included."""
    if not (request.user.is_lab_tech or request.user.is_medical_director
            or request.user.is_admin_staff or request.user.is_super_admin
            or request.user.is_ceo or request.user.is_admin_director
            or request.user.is_investigation_tech):
        return HttpResponseForbidden()

    import json
    from datetime import date as _date

    today = timezone.localdate()

    # ── Month selector (default = current month) ─────────────────────────────
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
        month_start = _date(year, month, 1)
    except (ValueError, TypeError):
        month_start = today.replace(day=1)
        year, month = month_start.year, month_start.month

    import calendar
    last_day = calendar.monthrange(year, month)[1]
    month_end = _date(year, month, last_day)

    # ── Cache check ───────────────────────────────────────────────────────────
    _cache_key = f'lab_stats_{year}_{month}'
    _cached = cache.get(_cache_key)
    if _cached:
        if request.GET.get('pdf'):
            from apps.reports.views import render_pdf
            _cached['pdf_filename'] = 'laboratory-stats.pdf'
            return render_pdf('laboratory/stats_pdf.html', _cached)
        return render(request, 'laboratory/stats.html', _cached)
    _cache_ttl = 600 if (year == today.year and month == today.month) else 86400

    base_orders = LabOrder.objects.filter(
        is_deleted=False,
        created_at__date__gte=month_start,
        created_at__date__lte=month_end,
    )
    base_items = LabOrderItem.objects.filter(
        order__is_deleted=False,
        order__created_at__date__gte=month_start,
        order__created_at__date__lte=month_end,
    )
    base_results = LabResult.objects.filter(
        is_deleted=False,
        created_at__date__gte=month_start,
        created_at__date__lte=month_end,
    )

    # ── KPI totals ────────────────────────────────────────────────────────────
    total_orders   = base_orders.count()
    total_items    = base_items.count()
    total_abnormal = base_results.filter(is_abnormal=True).count()
    total_critical = base_results.filter(is_critical=True).count()

    # Positivity rate (abnormal / total with results)
    total_results  = base_results.count()
    positivity_rate = round(total_abnormal / total_results * 100, 1) if total_results else 0

    # ── Gender breakdown ──────────────────────────────────────────────────────
    gender_raw = (
        base_orders.values('patient__gender').annotate(count=Count('id'))
    )
    gender_map = {g['patient__gender']: g['count'] for g in gender_raw}
    male_count   = gender_map.get('M', 0)
    female_count = gender_map.get('F', 0)
    other_count  = sum(v for k, v in gender_map.items() if k not in ('M', 'F'))
    gender_json  = json.dumps([
        {'label': 'Male',   'count': male_count},
        {'label': 'Female', 'count': female_count},
    ] + ([{'label': 'Other', 'count': other_count}] if other_count else []))

    # ── WHO age groups ────────────────────────────────────────────────────────
    # WHO standard age bands: 0-4, 5-14, 15-24, 25-44, 45-59, 60+
    WHO_BANDS = [
        ('0–4',   0,  4),
        ('5–14',  5,  14),
        ('15–24', 15, 24),
        ('25–44', 25, 44),
        ('45–59', 45, 59),
        ('60+',   60, 999),
    ]
    dobs = list(
        base_orders.filter(patient__date_of_birth__isnull=False)
        .values_list('patient_id', 'patient__date_of_birth')
        .distinct()
    )
    age_counts = {band[0]: 0 for band in WHO_BANDS}
    age_unknown = 0
    for _, dob in dobs:
        try:
            age = (today - dob).days // 365
            placed = False
            for label, lo, hi in WHO_BANDS:
                if lo <= age <= hi:
                    age_counts[label] += 1
                    placed = True
                    break
            if not placed:
                age_unknown += 1
        except Exception:
            age_unknown += 1

    # Also split by gender per age band (paediatric highlight)
    paed_count  = age_counts.get('0–4', 0) + age_counts.get('5–14', 0)
    adult_count = sum(v for k, v in age_counts.items() if k not in ('0–4', '5–14'))
    age_json = json.dumps([{'label': k, 'count': v} for k, v in age_counts.items()])

    # ── Positivity rate for qualitative tests ─────────────────────────────────
    positivity_by_test = list(
        base_results.filter(
            order_item__test_type__result_type__in=['QUALITATIVE', 'SEMI_QUANT'],
        )
        .values('order_item__test_type__name', 'order_item__test_type__code')
        .annotate(
            total=Count('id'),
            positive=Count('id', filter=Q(is_abnormal=True)),
        )
        .filter(total__gt=0)
        .order_by('-total')
    )
    for t in positivity_by_test:
        t['rate'] = round(t['positive'] / t['total'] * 100, 1) if t['total'] else 0

    # ── Gender per test category ──────────────────────────────────────────────
    cat_gender_raw = list(
        base_items.values('test_type__category', 'order__patient__gender')
        .annotate(count=Count('id'))
    )
    cat_gender = {}
    for row in cat_gender_raw:
        cat = row['test_type__category']
        g   = row['order__patient__gender']
        if cat not in cat_gender:
            cat_gender[cat] = {'M': 0, 'F': 0}
        if g == 'M':
            cat_gender[cat]['M'] += row['count']
        elif g == 'F':
            cat_gender[cat]['F'] += row['count']

    # ── Existing stats ────────────────────────────────────────────────────────
    category_volume = (
        base_items.values('test_type__category', 'test_type__name')
        .annotate(count=Count('id'))
        .order_by('test_type__category', '-count')
    )
    top_tests = (
        base_items.values('test_type__name', 'test_type__code')
        .annotate(count=Count('id'))
        .order_by('-count')[:15]
    )
    abnormal_by_test = (
        base_results.values('order_item__test_type__name')
        .annotate(
            total=Count('id'),
            abnormal=Count('id', filter=Q(is_abnormal=True)),
            critical=Count('id', filter=Q(is_critical=True)),
        )
        .filter(total__gt=0)
        .order_by('-abnormal')[:10]
    )
    for t in abnormal_by_test:
        t['abn_rate'] = round(t['abnormal'] / t['total'] * 100, 1) if t['total'] else 0

    # Daily volume — single aggregate instead of 14 separate queries
    from django.db.models.functions import TruncDate as _TruncDate
    _14_ago = today - timedelta(days=13)
    _daily_raw = dict(
        LabOrder.objects.filter(
            is_deleted=False,
            created_at__date__gte=_14_ago,
            created_at__date__lte=today,
        )
        .annotate(day=_TruncDate('created_at'))
        .values_list('day')
        .annotate(cnt=Count('id'))
        .values_list('day', 'cnt')
    )
    daily_volume = [
        {'date': (today - timedelta(days=i)).strftime('%d %b'),
         'count': _daily_raw.get(today - timedelta(days=i), 0)}
        for i in range(13, -1, -1)
    ]

    # ── Lab orders by requesting department / consultation type ──────────────
    dept_lab_raw = list(
        base_orders.values('consultation__department__name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    total_dept_orders = sum(r['count'] for r in dept_lab_raw)
    dept_lab_table = [
        {
            'name': r['consultation__department__name'] or 'Unknown',
            'count': r['count'],
            'pct': round(r['count'] / total_dept_orders * 100, 1) if total_dept_orders else 0,
        }
        for r in dept_lab_raw
    ]
    dept_lab_json = json.dumps({
        'labels': [r['name'] for r in dept_lab_table],
        'data':   [r['count'] for r in dept_lab_table],
    })

    # ── Completed tests by service tier + WHO age groups ─────────────────────
    # Base on COMPLETED LabOrderItems (actual tests done, not just ordered)
    TIER_DISPLAY = {'VIP': 'VIP', 'EXPRESS': 'Express', 'STANDARD': 'Standard'}
    TIER_ORDER   = ['VIP', 'EXPRESS', 'STANDARD']

    # Pull completed items with tier and patient DOB
    completed_items = list(
        base_items.filter(status='COMPLETED')
        .values(
            'order__consultation__visit__service_tier',
            'order__patient__date_of_birth',
        )
    )

    # Age buckets: Children 0-14, Adults 15-59, Elderly 60+
    tier_age = {}   # {'STANDARD': {'children': 0, 'adults': 0, 'elderly': 0, 'total': 0}, ...}
    for row in completed_items:
        tier_key = row['order__consultation__visit__service_tier'] or 'STANDARD'
        dob      = row['order__patient__date_of_birth']
        if tier_key not in tier_age:
            tier_age[tier_key] = {'children': 0, 'adults': 0, 'elderly': 0, 'total': 0}
        tier_age[tier_key]['total'] += 1
        if dob:
            try:
                age = (today - dob).days // 365
                if age <= 14:
                    tier_age[tier_key]['children'] += 1
                elif age <= 59:
                    tier_age[tier_key]['adults'] += 1
                else:
                    tier_age[tier_key]['elderly'] += 1
            except Exception:
                pass

    # Build ordered table (all tiers, even zeros)
    total_completed_items = sum(d['total'] for d in tier_age.values())

    tier_age_table = []
    for tk in TIER_ORDER:
        d = tier_age.get(tk, {'children': 0, 'adults': 0, 'elderly': 0, 'total': 0})
        if d['total'] > 0:
            pct = round(d['total'] / total_completed_items * 100, 1) if total_completed_items else 0
            tier_age_table.append({'tier': TIER_DISPLAY[tk], 'key': tk, 'pct': pct, **d})

    for tk, d in tier_age.items():
        if tk not in TIER_ORDER and d['total'] > 0:
            pct = round(d['total'] / total_completed_items * 100, 1) if total_completed_items else 0
            tier_age_table.append({'tier': tk, 'key': tk, 'pct': pct, **d})

    # JSON for tier doughnut
    tier_lab_json = json.dumps({
        'labels': [r['tier'] for r in tier_age_table],
        'data':   [r['total'] for r in tier_age_table],
    })

    # ── Urgency breakdown ────────────────────────────────────────────────────
    urgency_raw = list(
        base_orders.values('urgency').annotate(count=Count('id')).order_by('-count')
    )
    urgency_json = json.dumps({
        'labels': [r['urgency'].title() for r in urgency_raw],
        'data':   [r['count'] for r in urgency_raw],
    })

    # ── Patient Flow Funnel ────────────────────────────────────────────────
    prescribed_count = total_orders
    paid_count = base_orders.filter(payment_status__in=[
        PaymentStatus.PAID, PaymentStatus.INSURED, PaymentStatus.WAIVED,
        PaymentStatus.STAT_OVERRIDE, PaymentStatus.PREPAID, PaymentStatus.BILL_LATER,
    ]).count()
    sample_collected_count = base_orders.filter(
        status__in=['SAMPLE_COLLECTED', 'PROCESSING', 'COMPLETED']
    ).count()
    completed_count = base_orders.filter(status='COMPLETED').count()
    cancelled_count = base_orders.filter(status='CANCELLED').count()
    unpaid_count = prescribed_count - paid_count
    not_collected_count = prescribed_count - sample_collected_count
    show_rate = round(sample_collected_count / prescribed_count * 100) if prescribed_count else 0
    payment_rate = round(paid_count / prescribed_count * 100) if prescribed_count else 0
    funnel_completion_rate = round(completed_count / prescribed_count * 100) if prescribed_count else 0

    # Category totals for donut chart
    category_labels = {
        'HAEMATOLOGY': 'Haematology', 'BIOCHEMISTRY': 'Biochemistry',
        'MICROBIOLOGY': 'Microbiology', 'SEROLOGY': 'Serology',
        'URINALYSIS': 'Urinalysis', 'HISTOLOGY': 'Histology/Cytology',
        'OCULAR': 'Ocular',
    }
    category_totals = (
        base_items.values('test_type__category').annotate(count=Count('id')).order_by('-count')
    )
    category_json = json.dumps([
        {'label': category_labels.get(c['test_type__category'], c['test_type__category']), 'count': c['count']}
        for c in category_totals
    ])

    # ── Lab tests by sex × age group (WHO standard) ─────────────────────────
    type_rows = list(
        base_items.values_list(
            'test_type__name',
            'test_type__category',
            'order__patient__gender',
            'order__patient__date_of_birth',
        )
    )
    type_breakdown = {}
    for _name, _cat, _gender, _dob in type_rows:
        cat_label = (_cat or '').replace('_', ' ').title()
        if _name not in type_breakdown:
            type_breakdown[_name] = {'category': cat_label, 'male': 0, 'female': 0,
                                     'child_male': 0, 'child_female': 0, 'total': 0}
        _is_child = False
        if _dob:
            try:
                _is_child = (today - _dob).days // 365 <= 14
            except Exception:
                pass
        type_breakdown[_name]['total'] += 1
        if _gender == 'M':
            type_breakdown[_name]['male'] += 1
            if _is_child:
                type_breakdown[_name]['child_male'] += 1
        elif _gender == 'F':
            type_breakdown[_name]['female'] += 1
            if _is_child:
                type_breakdown[_name]['child_female'] += 1
    type_breakdown_list = sorted(
        [{'name': k, **v,
          'male_adult':   v['male']   - v['child_male'],
          'female_adult': v['female'] - v['child_female']}
         for k, v in type_breakdown.items()],
        key=lambda x: x['total'], reverse=True,
    )

    # Previous / next month navigation
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    context = {
        'month_start': month_start,
        'today': today,
        'year': year,
        'month': month,
        'prev_year': prev_year, 'prev_month': prev_month,
        'next_year': next_year, 'next_month': next_month,
        # KPIs
        'total_orders': total_orders,
        'total_items': total_items,
        'total_abnormal': total_abnormal,
        'total_critical': total_critical,
        'positivity_rate': positivity_rate,
        # Demographics
        'male_count': male_count,
        'female_count': female_count,
        'paed_count': paed_count,
        'adult_count': adult_count,
        'age_counts': age_counts,
        'age_json': age_json,
        'gender_json': gender_json,
        'cat_gender': cat_gender,
        # Positivity
        'positivity_by_test': positivity_by_test,
        # Existing
        'category_volume': category_volume,
        'top_tests': top_tests,
        'abnormal_by_test': abnormal_by_test,
        'daily_volume': daily_volume,
        'daily_volume_json': json.dumps(daily_volume),
        'category_json': category_json,
        # By department / tier+age / urgency
        'dept_lab_table': dept_lab_table,
        'dept_lab_json': dept_lab_json,
        'tier_age_table': tier_age_table,
        'tier_lab_json': tier_lab_json,
        'total_completed_items': total_completed_items,
        'urgency_json': urgency_json,
        'type_breakdown_list': type_breakdown_list,
        # Funnel
        'prescribed_count': prescribed_count,
        'paid_count': paid_count,
        'sample_collected_count': sample_collected_count,
        'completed_count': completed_count,
        'cancelled_count': cancelled_count,
        'unpaid_count': unpaid_count,
        'not_collected_count': not_collected_count,
        'show_rate': show_rate,
        'payment_rate': payment_rate,
        'funnel_completion_rate': funnel_completion_rate,
    }
    cache.set(_cache_key, context, _cache_ttl)
    if request.GET.get('pdf'):
        from apps.reports.views import render_pdf
        context['pdf_filename'] = 'laboratory-stats.pdf'
        return render_pdf('laboratory/stats_pdf.html', context)
    return render(request, 'laboratory/stats.html', context)


@login_required
def verify_result(request, result_id):
    """Lab senior / director verifies a result (ISO 15189 — tech who performed cannot verify)."""
    if not (request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()
    result = get_object_or_404(LabResult, pk=result_id, is_deleted=False)
    if result.performed_by and result.performed_by == request.user:
        messages.error(request, 'ISO 15189: The person who performed the test cannot verify the result.')
        return redirect('laboratory:detail', pk=result.order_item.order.pk)
    result.is_verified = True
    result.verified_by = request.user
    result.verified_at = timezone.now()
    result.result_status = ResultStatus.TECH_VALID
    result.save(update_fields=['is_verified', 'verified_by', 'verified_at', 'result_status', 'updated_at'])
    _log_tat(result.order_item.order, TATTimestamp.Event.TECH_VALIDATED, request.user)
    messages.success(request, 'Result verified.')
    # Check if all results are done — auto-return patient to doctor queue
    try:
        visit = result.order_item.order.consultation.visit if result.order_item.order.consultation else None
        if visit:
            from apps.core.patient_flow import check_and_autoreturn_to_doctor
            check_and_autoreturn_to_doctor(visit, triggered_by=request.user)
    except Exception as exc:
        import logging as _logging
        _logging.getLogger('ehr.laboratory').warning(
            'Auto-return to doctor failed for lab order %s: %s', result.order_item.order.pk, exc,
        )
    return redirect('laboratory:detail', pk=result.order_item.order.pk)


@login_required
def lab_order_view(request, consultation_pk):
    if not request.user.can_order_investigations():
        return HttpResponseForbidden()

    consultation = get_object_or_404(Consultation, pk=consultation_pk, is_deleted=False)
    test_types = LabTestType.objects.filter(is_active=True).order_by('category', 'name')
    order_sets = OrderSet.objects.filter(is_active=True).prefetch_related('tests')

    # Duplicate order warning — check for same tests in last 24h
    recent_test_ids = set(
        LabOrderItem.objects.filter(
            order__patient=consultation.patient,
            order__is_deleted=False,
            order__created_at__gte=timezone.now() - timedelta(hours=24),
        ).exclude(
            order__status=LabOrder.Status.CANCELLED,
        ).values_list('test_type_id', flat=True)
    )

    if request.method == 'POST':
        form = LabOrderForm(request.POST)
        selected_tests = request.POST.getlist('test_types')
        if form.is_valid() and selected_tests:
            # Check for duplicates unless acknowledged
            dup_acknowledged = request.POST.get('duplicate_warning_acknowledged') == '1'
            dup_test_ids = set(selected_tests) & {str(tid) for tid in recent_test_ids}
            if dup_test_ids and not dup_acknowledged:
                dup_names = list(LabTestType.objects.filter(id__in=dup_test_ids).values_list('name', flat=True))
                messages.warning(
                    request,
                    f'Duplicate order warning: {", ".join(dup_names)} were ordered for this '
                    f'patient in the last 24 hours. Re-submit to confirm.'
                )
                return render(request, 'laboratory/order_form.html', {
                    'form': form, 'consultation': consultation,
                    'test_types': test_types, 'order_sets': order_sets,
                    'categories': LabTestType.objects.values_list('category', flat=True).distinct(),
                    'duplicate_tests': dup_test_ids, 'selected_tests': selected_tests,
                    'recent_test_ids': recent_test_ids,
                })

            order = form.save(commit=False)
            order.consultation = consultation
            order.patient = consultation.patient
            order.ordered_by = request.user
            order.created_by = request.user
            order.icd10_code = request.POST.get('icd10_code', '').strip()
            order.duplicate_warning_acknowledged = bool(dup_test_ids)
            # Payment bypass for STAT/Emergency
            if order.urgency in (LabOrder.Urgency.STAT, LabOrder.Urgency.EMERGENCY):
                order.payment_status = PaymentStatus.STAT_OVERRIDE
                order.payment_authorized_by = request.user
                order.payment_authorized_at = timezone.now()
                order.payment_authorization_reason = f'Auto-authorized: {order.get_urgency_display()} order'
            # Order set if selected
            order_set_id = request.POST.get('order_set')
            if order_set_id:
                order.order_set_id = order_set_id
            order.save()
            _log_tat(order, TATTimestamp.Event.ORDERED, request.user)
            items_created = []
            for test_id in selected_tests:
                item = LabOrderItem.objects.create(order=order, test_type_id=test_id)
                items_created.append(item)
            # Create one PENDING_PAYMENT work order per test item for per-test payment tracking
            try:
                from apps.billing.models import ServiceWorkOrder, WorkOrderStatus, ServiceCategory
                for item in items_created:
                    ServiceWorkOrder.objects.create(
                        patient=consultation.patient,
                        consultation=consultation,
                        category=ServiceCategory.LABORATORY,
                        description=f'Lab: {item.test_type.name}',
                        status=WorkOrderStatus.PENDING_PAYMENT,
                        lab_order_item=item,
                        created_by=request.user,
                    )
            except Exception:
                pass
            # Auto-route patient to lab queue
            try:
                from apps.core.patient_flow import auto_route_to_lab
                auto_route_to_lab(consultation, ordered_by=request.user)
            except Exception:
                pass
            messages.success(
                request,
                f'Lab order created ({len(selected_tests)} test(s)). '
                'Patient has been routed to the lab queue automatically.'
            )
            return redirect('consultations:detail', pk=consultation_pk)
        elif not selected_tests:
            messages.error(request, 'Please select at least one test.')
    else:
        form = LabOrderForm()

    return render(request, 'laboratory/order_form.html', {
        'form': form,
        'consultation': consultation,
        'test_types': test_types,
        'order_sets': order_sets,
        'categories': LabTestType.objects.values_list('category', flat=True).distinct(),
        'recent_test_ids': recent_test_ids,
    })


@login_required
def lab_detail_view(request, pk):
    order = get_object_or_404(
        LabOrder.objects.prefetch_related('items__test_type', 'items__result__verified_by'),
        pk=pk, is_deleted=False
    )
    sample = getattr(order, 'sample_collection', None)
    items = list(order.items.all())
    items_with_results = [i for i in items if hasattr(i, 'result') and i.result]
    all_verified = (
        bool(items_with_results) and
        all(i.result.is_verified for i in items_with_results)
    )
    # ISO 15189 §5.8.3 — amendment audit trail
    result_ids = [i.result.pk for i in items_with_results]
    amendments = list(
        LabResultAmendment.objects.filter(result_id__in=result_ids)
        .select_related('amended_by', 'result__order_item__test_type')
        .order_by('-created_at')
    ) if result_ids else []
    return render(request, 'laboratory/detail.html', {
        'order': order,
        'sample': sample,
        'all_verified': all_verified,
        'amendments': amendments,
    })


@login_required
def bulk_collect_sample_view(request):
    """Mark multiple lab orders as SAMPLE_COLLECTED in one click."""
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()
    if request.method != 'POST':
        return redirect('laboratory:dashboard')
    pks = request.POST.getlist('order_ids')
    if not pks:
        messages.warning(request, 'No orders selected.')
        return redirect('laboratory:dashboard')
    orders_to_update = list(LabOrder.objects.filter(
        pk__in=pks,
        status=LabOrder.Status.ORDERED,
        is_deleted=False,
    ))
    updated = LabOrder.objects.filter(pk__in=[o.pk for o in orders_to_update]).update(
        status=LabOrder.Status.SAMPLE_COLLECTED,
    )
    for o in orders_to_update:
        _log_tat(o, TATTimestamp.Event.COLLECTED, request.user, notes='Bulk collection')
    messages.success(request, f'{updated} order(s) marked as Sample Collected.')
    return redirect('laboratory:dashboard')


@login_required
def collect_sample_view(request, pk):
    if not (request.user.is_lab_tech or request.user.is_medical_director):
        return HttpResponseForbidden()
    order = get_object_or_404(LabOrder, pk=pk, is_deleted=False)
    if hasattr(order, 'sample_collection'):
        messages.info(request, 'Sample already collected.')
        return redirect('laboratory:detail', pk=pk)

    if request.method == 'POST':
        form = SampleCollectionForm(request.POST)
        if form.is_valid():
            sc = form.save(commit=False)
            sc.order = order
            sc.collected_by = request.user
            sc.created_by = request.user
            sc.save()
            order.status = LabOrder.Status.SAMPLE_COLLECTED
            order.save(update_fields=['status'])
            _log_tat(order, TATTimestamp.Event.COLLECTED, request.user)
            messages.success(request, 'Sample collection recorded.')
            return redirect('laboratory:detail', pk=pk)
    else:
        form = SampleCollectionForm()

    return render(request, 'laboratory/collect_sample.html', {'form': form, 'order': order})


@login_required
def enter_results_view(request, pk):
    if not (request.user.is_lab_tech or request.user.is_medical_director):
        return HttpResponseForbidden()

    order = get_object_or_404(
        LabOrder.objects.prefetch_related('items__test_type'),
        pk=pk
    )
    items = list(order.items.all())

    if request.method == 'POST':
        all_valid = True
        _had_critical = False
        for item in items:
            value = request.POST.get(f'result_value_{item.pk}', '').strip()
            if value:
                result, created = LabResult.objects.get_or_create(
                    order_item=item,
                    defaults={
                        'performed_by': request.user,
                        'created_by': request.user,
                    }
                )
                # Skip verified results — they are locked
                if result.is_verified:
                    continue
                # ISO 15189 §5.8.3 — log amendment if value is being changed
                amendment_reason = request.POST.get(f'amendment_reason_{item.pk}', '').strip()
                if not created and result.result_value and result.result_value != value:
                    LabResultAmendment.objects.create(
                        result=result,
                        original_value=result.result_value,
                        amended_by=request.user,
                        reason=amendment_reason or 'Corrected by technician',
                    )
                    _log_tat(order, TATTimestamp.Event.AMENDED, request.user,
                             notes=f'{item.test_type.name}: {result.result_value} → {value}')
                result.result_value = value
                result.result_unit = request.POST.get(f'result_unit_{item.pk}', '')
                result.reference_range = request.POST.get(f'ref_range_{item.pk}', '')
                result.is_abnormal = request.POST.get(f'is_abnormal_{item.pk}') == 'on'
                result.is_critical = request.POST.get(f'is_critical_{item.pk}') == 'on'
                result.comment = request.POST.get(f'comment_{item.pk}', '')
                result.performed_by = request.user
                result.save()
                # Auto-verification — check if result passes auto-release rules
                if not result.is_verified:
                    try:
                        rule = AutoverificationRule.objects.get(
                            test_type=item.test_type, is_active=True,
                        )
                        if rule.check_result(result):
                            result.is_verified = True
                            result.auto_verified = True
                            result.verified_at = timezone.now()
                            result.result_status = ResultStatus.TECH_VALID
                            result.save(update_fields=[
                                'is_verified', 'auto_verified', 'verified_at',
                                'result_status', 'updated_at',
                            ])
                            _log_tat(order, TATTimestamp.Event.TECH_VALIDATED,
                                     notes=f'Auto-verified: {item.test_type.name}')
                    except AutoverificationRule.DoesNotExist:
                        pass
                if result.is_critical:
                    try:
                        from apps.notifications.utils import notify_critical_lab_result
                        notify_critical_lab_result(result)
                        _had_critical = True
                    except Exception as exc:
                        import logging as _logging
                        _logging.getLogger('ehr.laboratory').error(
                            'Critical lab notification failed for result %s: %s', result.pk, exc,
                        )
                item.status = LabOrder.Status.COMPLETED
                item.save(update_fields=['status'])

        order.status = LabOrder.Status.COMPLETED
        order.save(update_fields=['status'])
        _log_tat(order, TATTimestamp.Event.RESULT_ENTERED, request.user)
        # Notify ordering doctor — only send general "ready" notification when no
        # critical notification was already sent (avoids duplicate alerts to the doctor)
        try:
            if not _had_critical:
                from apps.notifications.utils import notify
                from apps.notifications.models import NotificationType, NotificationPriority
                doctor = getattr(order, 'ordered_by', None)
                if doctor:
                    notify(
                        recipient=doctor,
                        title=f'Lab Results Ready — {order.patient.full_name}',
                        message=(
                            f'All laboratory results for {order.patient.full_name} are now available. '
                            f'Order from {order.created_at:%d %b %Y}.'
                        ),
                        link=f'/laboratory/{order.id}/',
                        notification_type=NotificationType.LAB_RESULT,
                        priority=NotificationPriority.NORMAL,
                    )
        except Exception as exc:
            import logging as _logging
            _logging.getLogger('ehr.laboratory').error(
                'Lab result notification failed for order %s: %s', order.pk, exc,
            )
        messages.success(request, 'Results saved successfully.')
        return redirect('laboratory:detail', pk=pk)

    # Previous results for the same test types on this patient — last 5 per test type
    from django.db.models import Prefetch as _Prefetch
    test_type_ids = [item.test_type_id for item in items]
    prev_results = list(
        LabResult.objects.filter(
            is_deleted=False,
            order_item__test_type_id__in=test_type_ids,
            order_item__order__patient=order.patient,
            order_item__order__status='COMPLETED',
        )
        .exclude(order_item__order=order)
        .select_related('order_item__test_type', 'order_item__order', 'performed_by', 'verified_by')
        .order_by('-created_at')[:20]
    )

    # Build delta check map: test_type_id → most recent prior result
    _prev_map = {}
    for pr in prev_results:
        tid = pr.order_item.test_type_id
        if tid not in _prev_map:
            _prev_map[tid] = pr

    for item in items:
        item._prev_result = _prev_map.get(item.test_type_id)

    return render(request, 'laboratory/results_form.html', {
        'order': order,
        'items': items,
        'prev_results': prev_results,
    })


@require_POST
@login_required
def cancel_lab_order(request, pk):
    """
    Cancel a lab order that has not yet been processed.
    Allowed by: the doctor who ordered it, lab tech, or medical director.
    Only orders in ORDERED status can be cancelled (not after sample collected/processing).
    """
    order = get_object_or_404(LabOrder, pk=pk, is_deleted=False)

    can_cancel = (
        request.user == order.ordered_by
        or request.user.is_lab_tech
        or request.user.is_medical_director
        or request.user.is_super_admin
    )
    if not can_cancel:
        return HttpResponseForbidden()

    if order.status != LabOrder.Status.ORDERED:
        messages.error(
            request,
            f'Cannot cancel — order is already {order.get_status_display()}. '
            'Contact the requesting doctor to discuss further action.'
        )
        return redirect('laboratory:detail', pk=pk)

    reason = request.POST.get('cancel_reason', '').strip() or 'Patient unable to pay / cancelled by request'
    order.status = LabOrder.Status.CANCELLED
    order.notes = (order.notes + '\n' if order.notes else '') + f'CANCELLED: {reason}'
    order.save(update_fields=['status', 'notes', 'updated_at'])

    # Cancel all items too
    order.items.update(status=LabOrder.Status.CANCELLED)

    # Void any billing work order for this lab order (if billing module is active)
    try:
        from apps.billing.models import ServiceWorkOrder, WorkOrderStatus
        ServiceWorkOrder.objects.filter(
            source_ref=str(order.id),
            status=WorkOrderStatus.PENDING,
            is_deleted=False,
        ).update(status=WorkOrderStatus.CANCELLED)
    except Exception:
        pass

    messages.success(
        request,
        f'Lab order cancelled for {order.patient.full_name}. '
        'Billing work order (if any) has also been voided.'
    )
    # Redirect back to the consultation if possible
    if order.consultation_id:
        return redirect('consultations:workstation')
    return redirect('laboratory:list')


# ── Stats CSV Export ──────────────────────────────────────────────────────────

@login_required
def lab_stats_csv_view(request):
    """Download monthly lab stats breakdown as CSV (test × sex × age)."""
    import csv
    import datetime as _dt
    import calendar as _cal
    from django.http import HttpResponse

    u = request.user
    if not (u.is_lab_tech or u.is_medical_director or u.is_super_admin
            or u.is_admin_director or u.is_ceo):
        return HttpResponseForbidden()

    today = timezone.localdate()
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
        month_start = _dt.date(year, month, 1)
    except (ValueError, TypeError):
        month_start = today.replace(day=1)
        year, month = month_start.year, month_start.month
    last_day  = _cal.monthrange(year, month)[1]
    month_end = _dt.date(year, month, last_day)

    base_items = LabOrderItem.objects.filter(
        order__is_deleted=False,
        order__created_at__date__gte=month_start,
        order__created_at__date__lte=month_end,
    )

    rows = list(base_items.values_list(
        'test_type__name', 'test_type__category',
        'order__patient__gender', 'order__patient__date_of_birth',
    ))

    bd = {}
    for name, category, gender, dob in rows:
        cat = (category or '').replace('_', ' ').title()
        if name not in bd:
            bd[name] = {'cat': cat, 'M': 0, 'F': 0, 'CM': 0, 'CF': 0, 'tot': 0}
        is_child = bool(dob) and (today - dob).days // 365 <= 14
        bd[name]['tot'] += 1
        if gender == 'M':
            bd[name]['M'] += 1
            if is_child:
                bd[name]['CM'] += 1
        elif gender == 'F':
            bd[name]['F'] += 1
            if is_child:
                bd[name]['CF'] += 1

    base_orders = LabOrder.objects.filter(
        is_deleted=False,
        created_at__date__gte=month_start,
        created_at__date__lte=month_end,
    )
    total_orders = base_orders.count()

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    fname = f"lab_stats_{year}_{month:02d}.csv"
    response['Content-Disposition'] = f'attachment; filename="{fname}"'
    w = csv.writer(response)
    w.writerow([f'Laboratory Statistics — {month_start.strftime("%B %Y")}'])
    w.writerow(['Generated:', today.strftime('%d/%m/%Y')])
    w.writerow([])
    w.writerow(['Test Name', 'Category',
                'Male Adult (15+)', 'Male Child (0–14)',
                'Female Adult (15+)', 'Female Child (0–14)',
                'Total Male', 'Total Female', 'Grand Total'])
    for name, v in sorted(bd.items(), key=lambda x: -x[1]['tot']):
        w.writerow([name, v['cat'],
                    v['M'] - v['CM'], v['CM'],
                    v['F'] - v['CF'], v['CF'],
                    v['M'], v['F'], v['tot']])
    w.writerow([])
    w.writerow(['', '', '', '', '', '', '', 'TOTAL', sum(v['tot'] for v in bd.values())])
    w.writerow([])
    w.writerow(['Summary'])
    w.writerow(['Total Orders', total_orders])
    completion = base_orders.filter(status='COMPLETED').count()
    w.writerow(['Completed', completion])
    w.writerow(['Completion Rate %',
                f"{round(completion / total_orders * 100, 1) if total_orders else 0}%"])
    w.writerow(['Urgent / Emergency',
                base_orders.filter(urgency__in=['URGENT', 'EMERGENCY']).count()])
    return response


# ── Staff Throughput Report ───────────────────────────────────────────────────

@login_required
def lab_staff_throughput_view(request):
    """Per-staff ISO 15189 §5.1 competence monitoring — throughput + quality metrics."""
    import datetime as _dt
    import json
    from django.db.models import Count, Avg, ExpressionWrapper, F, DurationField
    from django.db.models.functions import TruncDate

    u = request.user
    if not (u.is_lab_tech or u.is_medical_director or u.is_super_admin
            or u.is_admin_director or u.is_ceo):
        return HttpResponseForbidden()

    today = timezone.localdate()
    try:
        days = int(request.GET.get('days', 30))
        if days not in (7, 14, 30, 60, 90):
            days = 30
    except (ValueError, TypeError):
        days = 30

    since = today - _dt.timedelta(days=days - 1)

    # ── Today's leaderboard ───────────────────────────────────────────────────
    today_results = (
        LabResult.objects
        .filter(is_deleted=False, result_date__date=today)
        .values('performed_by__id', 'performed_by__first_name', 'performed_by__last_name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    today_board = [
        {
            'name': f"{r['performed_by__first_name']} {r['performed_by__last_name']}".strip() or 'Unknown',
            'count': r['count'],
        }
        for r in today_results if r['performed_by__id']
    ]

    # ── Per-staff summary with full quality metrics ────────────────────────────
    staff_summary_raw = (
        LabResult.objects
        .filter(is_deleted=False, result_date__date__gte=since, result_date__date__lte=today)
        .values('performed_by__id', 'performed_by__first_name', 'performed_by__last_name')
        .annotate(
            total=Count('id'),
            verified=Count('id', filter=Q(is_verified=True)),
            critical=Count('id', filter=Q(is_critical=True)),
            abnormal=Count('id', filter=Q(is_abnormal=True)),
        )
        .order_by('-total')
    )

    # ── Average TAT: sample collection → result entry ─────────────────────────
    tat_map = {}
    for r in (
        LabResult.objects
        .filter(
            is_deleted=False,
            result_date__date__gte=since,
            result_date__date__lte=today,
            order_item__order__sample_collection__isnull=False,
        )
        .values('performed_by__id')
        .annotate(avg_tat=Avg(ExpressionWrapper(
            F('result_date') - F('order_item__order__sample_collection__collection_date'),
            output_field=DurationField(),
        )))
    ):
        if r['performed_by__id'] and r['avg_tat']:
            tat_map[r['performed_by__id']] = max(0, int(r['avg_tat'].total_seconds() / 60))

    # ── Amendment counts (ISO 15189 §5.8.3 — result correction audit) ────────
    amendment_map = {
        r['amended_by__id']: r['count']
        for r in LabResultAmendment.objects
        .filter(created_at__date__gte=since, created_at__date__lte=today)
        .values('amended_by__id').annotate(count=Count('id'))
        if r['amended_by__id']
    }

    # ── Sample rejection counts (ISO 15189 §5.4.5) ───────────────────────────
    rejection_map = {
        r['rejected_by__id']: r['count']
        for r in SampleRejection.objects
        .filter(is_deleted=False, created_at__date__gte=since, created_at__date__lte=today)
        .values('rejected_by__id').annotate(count=Count('id'))
        if r['rejected_by__id']
    }

    staff_summary = []
    for r in staff_summary_raw:
        if not r['performed_by__id']:
            continue
        uid      = r['performed_by__id']
        total    = r['total']
        verified = r['verified']
        critical = r['critical']
        abnormal = r['abnormal']
        tat_mins = tat_map.get(uid)
        if tat_mins is not None:
            tat_str   = f"{tat_mins // 60}h {tat_mins % 60}m" if tat_mins >= 60 else f"{tat_mins}m"
            tat_class = 'text-success' if tat_mins < 120 else ('text-warning' if tat_mins < 240 else 'text-danger fw-bold')
        else:
            tat_str, tat_class = '—', 'text-muted'
        staff_summary.append({
            'name':         f"{r['performed_by__first_name']} {r['performed_by__last_name']}".strip() or 'Unknown',
            'uid':          uid,
            'total':        total,
            'verified':     verified,
            'verified_pct': round(verified / total * 100) if total else 0,
            'critical':     critical,
            'critical_pct': round(critical / total * 100, 1) if total else 0,
            'abnormal':     abnormal,
            'abnormal_pct': round(abnormal / total * 100, 1) if total else 0,
            'avg_per_day':  round(total / days, 1) if days else 0,
            'amendments':   amendment_map.get(uid, 0),
            'rejections':   rejection_map.get(uid, 0),
            'tat_str':      tat_str,
            'tat_class':    tat_class,
            'tat_mins':     tat_mins or 0,
        })

    # ── Daily totals chart ───────────────────────────────────────────────────
    daily_raw = (
        LabResult.objects
        .filter(is_deleted=False, result_date__date__gte=since, result_date__date__lte=today)
        .annotate(day=TruncDate('result_date'))
        .values('day').annotate(count=Count('id')).order_by('day')
    )
    daily_json = json.dumps([{'day': str(r['day']), 'count': r['count']} for r in daily_raw])

    # ── Top 5 staff per-day trend ─────────────────────────────────────────────
    top5 = [s['name'] for s in staff_summary[:5]]
    staff_daily = {}
    if top5:
        for r in (
            LabResult.objects
            .filter(is_deleted=False, result_date__date__gte=since, result_date__date__lte=today)
            .annotate(day=TruncDate('result_date'))
            .values('day', 'performed_by__first_name', 'performed_by__last_name')
            .annotate(count=Count('id')).order_by('day')
        ):
            name = f"{r['performed_by__first_name']} {r['performed_by__last_name']}".strip() or 'Unknown'
            if name in top5:
                staff_daily.setdefault(name, {})[str(r['day'])] = r['count']

    date_labels = [(since + _dt.timedelta(days=i)).strftime('%d %b') for i in range(days)]
    date_keys   = [(since + _dt.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days)]
    CHART_COLORS = ['#6366f1', '#0d6efd', '#198754', '#ffc107', '#dc3545']
    staff_chart_json = json.dumps({
        'labels': date_labels,
        'datasets': [
            {
                'label': name,
                'data': [staff_daily.get(name, {}).get(dk, 0) for dk in date_keys],
                'borderColor': CHART_COLORS[i % len(CHART_COLORS)],
                'backgroundColor': 'transparent',
                'borderWidth': 2, 'pointRadius': 3, 'tension': 0.3,
            }
            for i, name in enumerate(top5)
        ],
    })

    grand_total = sum(s['total'] for s in staff_summary)
    today_total = sum(t['count'] for t in today_board)

    return render(request, 'laboratory/staff_throughput.html', {
        'today':            today,
        'days':             days,
        'since':            since,
        'today_board':      today_board,
        'today_total':      today_total,
        'staff_summary':    staff_summary,
        'grand_total':      grand_total,
        'daily_json':       daily_json,
        'staff_chart_json': staff_chart_json,
        'date_labels':      date_labels,
    })


# ── Staff Throughput CSV Export ───────────────────────────────────────────────

@login_required
def lab_staff_throughput_csv_view(request):
    """CSV — full ISO 15189 §5.1 staff competence metrics."""
    import csv
    import datetime as _dt
    from django.db.models import Count, Avg, ExpressionWrapper, F, DurationField
    from django.http import HttpResponse

    u = request.user
    if not (u.is_lab_tech or u.is_medical_director or u.is_super_admin
            or u.is_admin_director or u.is_ceo):
        return HttpResponseForbidden()

    today = timezone.localdate()
    try:
        days = int(request.GET.get('days', 30))
        if days not in (7, 14, 30, 60, 90):
            days = 30
    except (ValueError, TypeError):
        days = 30

    since = today - _dt.timedelta(days=days - 1)

    staff_raw = (
        LabResult.objects
        .filter(is_deleted=False, result_date__date__gte=since, result_date__date__lte=today)
        .values('performed_by__id', 'performed_by__first_name', 'performed_by__last_name')
        .annotate(
            total=Count('id'),
            verified=Count('id', filter=Q(is_verified=True)),
            critical=Count('id', filter=Q(is_critical=True)),
            abnormal=Count('id', filter=Q(is_abnormal=True)),
        )
        .order_by('-total')
    )
    tat_map = {
        r['performed_by__id']: max(0, int(r['avg_tat'].total_seconds() / 60))
        for r in LabResult.objects
        .filter(
            is_deleted=False, result_date__date__gte=since, result_date__date__lte=today,
            order_item__order__sample_collection__isnull=False,
        )
        .values('performed_by__id')
        .annotate(avg_tat=Avg(ExpressionWrapper(
            F('result_date') - F('order_item__order__sample_collection__collection_date'),
            output_field=DurationField(),
        )))
        if r['performed_by__id'] and r['avg_tat']
    }
    amendment_map = {
        r['amended_by__id']: r['count']
        for r in LabResultAmendment.objects
        .filter(created_at__date__gte=since, created_at__date__lte=today)
        .values('amended_by__id').annotate(count=Count('id'))
        if r['amended_by__id']
    }
    rejection_map = {
        r['rejected_by__id']: r['count']
        for r in SampleRejection.objects
        .filter(is_deleted=False, created_at__date__gte=since, created_at__date__lte=today)
        .values('rejected_by__id').annotate(count=Count('id'))
        if r['rejected_by__id']
    }

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="lab_staff_throughput_{days}d_{today}.csv"'
    w = csv.writer(response)
    w.writerow([f'Lab Staff Throughput — ISO 15189 §5.1 Competence Report — Last {days} Days'])
    w.writerow(['Period:', f'{since.strftime("%d/%m/%Y")} to {today.strftime("%d/%m/%Y")}'])
    w.writerow(['Generated:', today.strftime('%d/%m/%Y')])
    w.writerow([])
    w.writerow([
        'Rank', 'Technician',
        'Total Results', 'Avg / Day',
        'Verified', 'Verified %',
        'Critical', 'Critical %',
        'Abnormal', 'Abnormal %',
        'Avg TAT (min)', 'Amendments', 'Rejections',
    ])
    grand = 0
    for rank, r in enumerate(staff_raw, 1):
        if not r['performed_by__id']:
            continue
        uid = r['performed_by__id']
        total, ver, crit, abn = r['total'], r['verified'], r['critical'], r['abnormal']
        grand += total
        w.writerow([
            rank,
            f"{r['performed_by__first_name']} {r['performed_by__last_name']}".strip() or 'Unknown',
            total, round(total / days, 1),
            ver, f"{round(ver / total * 100) if total else 0}%",
            crit, f"{round(crit / total * 100, 1) if total else 0}%",
            abn, f"{round(abn / total * 100, 1) if total else 0}%",
            tat_map.get(uid, ''),
            amendment_map.get(uid, 0),
            rejection_map.get(uid, 0),
        ])
    w.writerow([])
    w.writerow(['', 'TOTAL', grand, round(grand / days, 1), '', '', '', '', '', '', '', '', ''])
    return response


# ── Staff Throughput PDF (WeasyPrint) ─────────────────────────────────────────

@login_required
def lab_staff_throughput_pdf_view(request):
    """WeasyPrint PDF — ISO 15189 §5.1 staff competence report with hospital letterhead."""
    import datetime as _dt
    from django.db.models import Count, Avg, ExpressionWrapper, F, DurationField

    u = request.user
    if not (u.is_lab_tech or u.is_medical_director or u.is_super_admin
            or u.is_admin_director or u.is_ceo):
        return HttpResponseForbidden()

    today = timezone.localdate()
    try:
        days = int(request.GET.get('days', 30))
        if days not in (7, 14, 30, 60, 90):
            days = 30
    except (ValueError, TypeError):
        days = 30

    since = today - _dt.timedelta(days=days - 1)

    today_results = (
        LabResult.objects
        .filter(is_deleted=False, result_date__date=today)
        .values('performed_by__id', 'performed_by__first_name', 'performed_by__last_name')
        .annotate(count=Count('id')).order_by('-count')
    )
    today_board = [
        {'name': f"{r['performed_by__first_name']} {r['performed_by__last_name']}".strip() or 'Unknown',
         'count': r['count']}
        for r in today_results if r['performed_by__id']
    ]

    staff_summary_raw = (
        LabResult.objects
        .filter(is_deleted=False, result_date__date__gte=since, result_date__date__lte=today)
        .values('performed_by__id', 'performed_by__first_name', 'performed_by__last_name')
        .annotate(
            total=Count('id'),
            verified=Count('id', filter=Q(is_verified=True)),
            critical=Count('id', filter=Q(is_critical=True)),
            abnormal=Count('id', filter=Q(is_abnormal=True)),
        )
        .order_by('-total')
    )
    tat_map = {}
    for r in (
        LabResult.objects
        .filter(is_deleted=False, result_date__date__gte=since, result_date__date__lte=today,
                order_item__order__sample_collection__isnull=False)
        .values('performed_by__id')
        .annotate(avg_tat=Avg(ExpressionWrapper(
            F('result_date') - F('order_item__order__sample_collection__collection_date'),
            output_field=DurationField(),
        )))
    ):
        if r['performed_by__id'] and r['avg_tat']:
            tat_map[r['performed_by__id']] = max(0, int(r['avg_tat'].total_seconds() / 60))

    amendment_map = {
        r['amended_by__id']: r['count']
        for r in LabResultAmendment.objects
        .filter(created_at__date__gte=since, created_at__date__lte=today)
        .values('amended_by__id').annotate(count=Count('id'))
        if r['amended_by__id']
    }
    rejection_map = {
        r['rejected_by__id']: r['count']
        for r in SampleRejection.objects
        .filter(is_deleted=False, created_at__date__gte=since, created_at__date__lte=today)
        .values('rejected_by__id').annotate(count=Count('id'))
        if r['rejected_by__id']
    }

    staff_summary = []
    for r in staff_summary_raw:
        if not r['performed_by__id']:
            continue
        uid = r['performed_by__id']
        total, verified, critical, abnormal = r['total'], r['verified'], r['critical'], r['abnormal']
        tat_mins = tat_map.get(uid)
        tat_str = (f"{tat_mins // 60}h {tat_mins % 60}m" if tat_mins and tat_mins >= 60
                   else (f"{tat_mins}m" if tat_mins else '—'))
        staff_summary.append({
            'name':         f"{r['performed_by__first_name']} {r['performed_by__last_name']}".strip() or 'Unknown',
            'total':        total,
            'verified':     verified,
            'verified_pct': round(verified / total * 100) if total else 0,
            'critical':     critical,
            'critical_pct': round(critical / total * 100, 1) if total else 0,
            'abnormal':     abnormal,
            'abnormal_pct': round(abnormal / total * 100, 1) if total else 0,
            'avg_per_day':  round(total / days, 1) if days else 0,
            'amendments':   amendment_map.get(uid, 0),
            'rejections':   rejection_map.get(uid, 0),
            'tat_str':      tat_str,
            'tat_mins':     tat_mins or 0,
        })

    from apps.reports.views import render_pdf
    ctx = {
        'today':          today,
        'days':           days,
        'since':          since,
        'today_board':    today_board,
        'today_total':    sum(t['count'] for t in today_board),
        'staff_summary':  staff_summary,
        'grand_total':    sum(s['total'] for s in staff_summary),
        'pdf_filename':   f'lab-staff-throughput-{days}d-{today}.pdf',
        'pdf_seal_label': 'INTERNAL USE ONLY',
    }
    return render_pdf('laboratory/staff_throughput_pdf.html', ctx)


# ── Sample Rejection ──────────────────────────────────────────────────────────

@login_required
@require_POST
def reject_sample_view(request, pk):
    """ISO 15189 §5.4.5 — Record sample rejection and reset order to ORDERED."""
    order = get_object_or_404(LabOrder, pk=pk, is_deleted=False)
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    reason = request.POST.get('rejection_reason', '').strip()
    notes  = request.POST.get('rejection_notes', '').strip()
    if not reason:
        messages.error(request, 'Please select a rejection reason.')
        return redirect('laboratory:detail', pk=pk)

    SampleRejection.objects.create(
        order=order,
        rejected_by=request.user,
        reason=reason,
        notes=notes,
        created_by=request.user,
    )

    # Reset order back to ORDERED so a new sample can be recollected
    order.status = LabOrder.Status.ORDERED
    order.specimen_status = SpecimenStatus.RE_COLLECT
    order.notes = (order.notes + '\n' if order.notes else '') + \
                  f'SAMPLE REJECTED [{reason}]: {notes}'
    order.save(update_fields=['status', 'specimen_status', 'notes', 'updated_at'])
    order.items.update(status=LabOrder.Status.ORDERED)
    _log_tat(order, TATTimestamp.Event.REJECTED, request.user, notes=reason)

    # If there was a SampleCollection, remove it so a new one can be created
    try:
        order.sample_collection.delete()
    except Exception:
        pass

    # Notify the requesting doctor
    try:
        from apps.notifications.utils import notify
        from apps.notifications.models import NotificationType, NotificationPriority
        if order.ordered_by:
            rejection_obj = SampleRejection.Reason(reason)
            notify(
                recipient=order.ordered_by,
                title=f'Sample Rejected — {order.patient.full_name}',
                message=(
                    f'The lab sample for {order.patient.full_name} was rejected: '
                    f'{rejection_obj.label}. {notes} '
                    f'Please arrange a new sample collection.'
                ),
                link=f'/laboratory/{order.id}/',
                notification_type=NotificationType.LAB_RESULT,
                priority=NotificationPriority.HIGH,
            )
    except Exception:
        pass

    messages.warning(
        request,
        f'Sample rejected ({SampleRejection.Reason(reason).label}). '
        'Order reset to ORDERED — requesting doctor notified to arrange a new sample.'
    )
    return redirect('laboratory:detail', pk=pk)


# ── Critical Value Acknowledgement ────────────────────────────────────────────

@login_required
@require_POST
def acknowledge_critical_view(request, result_id):
    """JCI IPSG.2 — Doctor acknowledges a critical lab result (read-back confirmation)."""
    result = get_object_or_404(LabResult, pk=result_id, is_critical=True, is_deleted=False)
    # Only the ordering doctor or medical director can acknowledge
    if not (request.user == result.order_item.order.ordered_by
            or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    if result.critical_acknowledged_at:
        messages.info(request, 'Already acknowledged.')
        return redirect('laboratory:detail', pk=result.order_item.order.pk)

    result.critical_acknowledged_by = request.user
    result.critical_acknowledged_at = timezone.now()
    result.critical_notified_to = request.POST.get('notified_to', request.user.get_full_name())
    result.critical_read_back_confirmed = request.POST.get('read_back_confirmed') == '1'
    if result.critical_read_back_confirmed:
        result.critical_read_back_at = timezone.now()
    result.save(update_fields=[
        'critical_acknowledged_by', 'critical_acknowledged_at',
        'critical_notified_to', 'critical_read_back_confirmed',
        'critical_read_back_at', 'updated_at',
    ])

    messages.success(
        request,
        f'Critical result for {result.order_item.test_type.name} acknowledged. '
        'This has been recorded in the audit log (JCI IPSG.2).'
    )
    return redirect('laboratory:detail', pk=result.order_item.order.pk)


# ── Printable Result PDF ──────────────────────────────────────────────────────

@login_required
def result_pdf_view(request, pk):
    """ISO 15189 §5.8.2 — Generate a printed lab report for the patient."""
    from apps.reports.views import render_pdf
    order = get_object_or_404(
        LabOrder.objects
        .select_related('patient', 'ordered_by')
        .prefetch_related('items__test_type', 'items__result', 'sample_collection'),
        pk=pk, is_deleted=False,
    )
    if not (request.user.is_lab_tech or request.user.is_medical_director
            or request.user.is_super_admin or request.user == order.ordered_by
            or request.user.is_admin_staff):
        return HttpResponseForbidden()

    completed_items = [
        item for item in order.items.all()
        if hasattr(item, 'result') and item.result
    ]

    # Build reference ranges and technique from LabTestType master data
    patient_gender = (order.patient.gender or '').upper()  # 'M' or 'F'
    for item in completed_items:
        tt = item.test_type
        # Technique from master catalogue
        item._technique = tt.method or ''
        # Reference range: prefer result-level, fall back to master catalogue
        if item.result.reference_range:
            item._ref_range = item.result.reference_range
        elif tt.normal_range:
            nr = tt.normal_range
            if isinstance(nr, dict):
                # Gender-specific: {"male": {"min":..,"max":..,"unit":..}, "female": {..}}
                key = 'female' if patient_gender == 'F' else 'male'
                gen = nr.get(key) or nr.get('male') or nr.get('default') or {}
                if isinstance(gen, dict) and ('min' in gen or 'max' in gen):
                    lo = gen.get('min', '')
                    hi = gen.get('max', '')
                    unit = gen.get('unit', '')
                    item._ref_range = f"{lo} – {hi} {unit}".strip()
                elif isinstance(gen, str):
                    item._ref_range = gen
                else:
                    item._ref_range = ''
            else:
                item._ref_range = str(nr)
        else:
            item._ref_range = ''

    return render_pdf('laboratory/result_pdf.html', {
        'order': order,
        'completed_items': completed_items,
        'pdf_filename': f'lab-result-{order.patient.patient_id}-{order.created_at:%Y%m%d}.pdf',
        'pdf_seal_label': 'LABORATORY REPORT',
    })


# ══════════════════════════════════════════════════════════════════════════════
# PAYMENT AUTHORIZATION (bypass paths)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def payment_authorize_view(request, pk):
    """Authorize lab work without upfront payment (insurance, waiver, STAT override)."""
    order = get_object_or_404(LabOrder, pk=pk, is_deleted=False)
    u = request.user
    if not (u.is_lab_tech or u.is_medical_director or u.is_super_admin
            or u.is_cashier or u.is_chief_cashier or u.is_finance_director):
        return HttpResponseForbidden()

    bypass_type = request.POST.get('bypass_type', '').strip()
    reason = request.POST.get('reason', '').strip()
    if bypass_type not in dict(PaymentStatus.choices):
        messages.error(request, 'Invalid payment bypass type.')
        return redirect('laboratory:detail', pk=pk)

    order.payment_status = bypass_type
    order.payment_authorized_by = u
    order.payment_authorized_at = timezone.now()
    order.payment_authorization_reason = reason
    order.save(update_fields=[
        'payment_status', 'payment_authorized_by',
        'payment_authorized_at', 'payment_authorization_reason', 'updated_at',
    ])
    _log_tat(order, TATTimestamp.Event.PAYMENT_CLEARED, u, notes=bypass_type)
    messages.success(request, f'Payment authorized: {order.get_payment_status_display()}')
    return redirect('laboratory:detail', pk=pk)


# ══════════════════════════════════════════════════════════════════════════════
# SPECIMEN RECEIPT (separate from collection)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def specimen_receive_view(request, pk):
    """Lab receives specimen — records condition, updates specimen_status."""
    order = get_object_or_404(LabOrder, pk=pk, is_deleted=False)
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    try:
        sample = order.sample_collection
    except SampleCollection.DoesNotExist:
        messages.error(request, 'No sample has been collected for this order yet.')
        return redirect('laboratory:detail', pk=pk)

    condition = request.POST.get('condition_on_arrival', 'GOOD')
    sample.received_by = request.user
    sample.received_at = timezone.now()
    sample.condition_on_arrival = condition
    sample.save(update_fields=['received_by', 'received_at', 'condition_on_arrival', 'updated_at'])

    order.specimen_status = SpecimenStatus.RECEIVED
    order.save(update_fields=['specimen_status', 'updated_at'])
    _log_tat(order, TATTimestamp.Event.RECEIVED_AT_LAB, request.user)

    messages.success(request, f'Specimen received (condition: {condition}).')
    return redirect('laboratory:detail', pk=pk)


# ══════════════════════════════════════════════════════════════════════════════
# RESULT AUTHORIZATION (biologist / pathologist sign-off)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def authorize_result_view(request, result_id):
    """Biologist / pathologist authorizes result for release to clinician."""
    result = get_object_or_404(LabResult, pk=result_id, is_deleted=False)
    if not (request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    if not result.is_verified:
        messages.error(request, 'Result must be technically validated before authorization.')
        return redirect('laboratory:detail', pk=result.order_item.order.pk)

    result.authorized_by = request.user
    result.authorized_at = timezone.now()
    result.result_status = ResultStatus.AUTHORIZED
    result.save(update_fields=[
        'authorized_by', 'authorized_at', 'result_status', 'updated_at',
    ])
    _log_tat(result.order_item.order, TATTimestamp.Event.AUTHORIZED, request.user)
    messages.success(request, f'{result.order_item.test_type.name} authorized for release.')
    return redirect('laboratory:detail', pk=result.order_item.order.pk)


@login_required
@require_POST
def release_result_view(request, result_id):
    """Release authorized result to clinician dashboard."""
    result = get_object_or_404(LabResult, pk=result_id, is_deleted=False)
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    if result.result_status not in (ResultStatus.AUTHORIZED, ResultStatus.TECH_VALID):
        messages.error(request, 'Result must be authorized before release.')
        return redirect('laboratory:detail', pk=result.order_item.order.pk)

    result.result_status = ResultStatus.RELEASED
    result.released_at = timezone.now()
    result.save(update_fields=['result_status', 'released_at', 'updated_at'])
    _log_tat(result.order_item.order, TATTimestamp.Event.RELEASED, request.user)

    # Notify ordering doctor
    try:
        from apps.notifications.utils import notify
        from apps.notifications.models import NotificationType, NotificationPriority
        order = result.order_item.order
        if order.ordered_by:
            notify(
                recipient=order.ordered_by,
                title=f'Lab Result Ready — {order.patient.full_name}',
                message=f'{result.order_item.test_type.name}: {result.result_value} {result.result_unit}',
                link=f'/laboratory/{order.id}/',
                notification_type=NotificationType.LAB_RESULT,
                priority=NotificationPriority.HIGH if result.is_critical else NotificationPriority.NORMAL,
            )
    except Exception:
        pass

    messages.success(request, 'Result released to clinician.')
    return redirect('laboratory:detail', pk=result.order_item.order.pk)


# ══════════════════════════════════════════════════════════════════════════════
# RESULT ACKNOWLEDGMENT (doctor seen / unseen)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def acknowledge_result_view(request, result_id):
    """Doctor marks a result as seen/acknowledged."""
    result = get_object_or_404(LabResult, pk=result_id, is_deleted=False)
    ack, created = ResultAcknowledgment.objects.get_or_create(
        result=result,
        acknowledged_by=request.user,
    )
    if created:
        _log_tat(result.order_item.order, TATTimestamp.Event.DOCTOR_VIEWED, request.user)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'created': created})
    messages.success(request, 'Result acknowledged.')
    return redirect('laboratory:detail', pk=result.order_item.order.pk)


@login_required
def unacknowledged_results_view(request):
    """Doctor's dashboard — results pending acknowledgment."""
    results = (
        LabResult.objects.filter(
            result_status=ResultStatus.RELEASED,
            order_item__order__ordered_by=request.user,
            order_item__order__is_deleted=False,
            is_deleted=False,
        )
        .exclude(acknowledgments__acknowledged_by=request.user)
        .select_related('order_item__test_type', 'order_item__order__patient')
        .order_by('-released_at')[:100]
    )
    return render(request, 'laboratory/unacknowledged_results.html', {
        'results': results,
    })


# ══════════════════════════════════════════════════════════════════════════════
# QUALITY CONTROL — QC Records + Levey-Jennings
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def qc_dashboard_view(request):
    """QC overview with recent records and Levey-Jennings data."""
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    import json
    today = timezone.localdate()
    last_30 = today - timedelta(days=30)

    records = QCRecord.objects.filter(
        is_deleted=False, run_date__date__gte=last_30,
    ).select_related('test_type', 'performed_by').order_by('-run_date')[:200]

    # Failed QC count
    failed_count = QCRecord.objects.filter(
        is_deleted=False, is_acceptable=False, run_date__date__gte=last_30,
    ).count()

    # Levey-Jennings data for selected test (AJAX param)
    lj_test_id = request.GET.get('lj_test')
    lj_data = []
    if lj_test_id:
        lj_records = QCRecord.objects.filter(
            test_type_id=lj_test_id, is_deleted=False,
            run_date__date__gte=last_30,
        ).order_by('run_date').values('run_date', 'observed_value', 'target_value', 'target_sd', 'calculated_z_score')
        lj_data = [
            {
                'date': r['run_date'].strftime('%d/%m'),
                'z': float(r['calculated_z_score']) if r['calculated_z_score'] else 0,
                'observed': float(r['observed_value']),
                'target': float(r['target_value']),
            }
            for r in lj_records
        ]

    # Tests with QC records
    qc_tests = LabTestType.objects.filter(
        qc_records__isnull=False
    ).distinct().order_by('name')

    return render(request, 'laboratory/qc_dashboard.html', {
        'records': records,
        'failed_count': failed_count,
        'qc_tests': qc_tests,
        'lj_data_json': json.dumps(lj_data),
        'lj_test_id': lj_test_id,
    })


@login_required
def qc_record_create_view(request):
    """Create a new QC record."""
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    if request.method == 'POST':
        from decimal import Decimal, InvalidOperation
        try:
            test_type_id = request.POST['test_type']
            record = QCRecord(
                test_type_id=test_type_id,
                run_date=timezone.now(),
                qc_material=request.POST.get('qc_material', '').strip(),
                lot_number=request.POST.get('lot_number', '').strip(),
                level=request.POST.get('level', 'NORMAL'),
                target_value=Decimal(request.POST['target_value']),
                observed_value=Decimal(request.POST['observed_value']),
                target_sd=Decimal(request.POST['target_sd']),
                reagent_lot=request.POST.get('reagent_lot', '').strip(),
                notes=request.POST.get('notes', '').strip(),
                corrective_action=request.POST.get('corrective_action', '').strip(),
                performed_by=request.user,
                created_by=request.user,
            )
            # Reagent expiry
            exp = request.POST.get('reagent_expiry', '').strip()
            if exp:
                from datetime import date as _date
                record.reagent_expiry = _date.fromisoformat(exp)
            cal = request.POST.get('calibration_date', '').strip()
            if cal:
                from datetime import date as _date
                record.calibration_date = _date.fromisoformat(cal)
            record.save()  # auto z-score + westgard check in model save()

            if not record.is_acceptable:
                messages.warning(
                    request,
                    f'QC FAILED — Westgard rule {record.get_westgard_rule_display()} violated! '
                    f'Results for {record.test_type.name} should NOT be released until corrective action is taken.'
                )
            else:
                messages.success(request, f'QC record saved (z={record.calculated_z_score}).')
            return redirect('laboratory:qc_dashboard')
        except (KeyError, InvalidOperation, ValueError) as e:
            messages.error(request, f'Invalid data: {e}')

    test_types = LabTestType.objects.filter(is_active=True).order_by('name')
    return render(request, 'laboratory/qc_record_form.html', {
        'test_types': test_types,
    })


# ══════════════════════════════════════════════════════════════════════════════
# SEND-OUT / REFERRAL TESTS
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def sendout_list_view(request):
    """List all send-out tests with status tracking."""
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    tests = (
        SendOutTest.objects.filter(is_deleted=False)
        .select_related('order_item__test_type', 'order_item__order__patient', 'dispatched_by')
        .order_by('-created_at')[:200]
    )
    overdue = [t for t in tests if t.is_overdue]
    return render(request, 'laboratory/sendout_list.html', {
        'tests': tests,
        'overdue_count': len(overdue),
    })


@login_required
def sendout_create_view(request, item_pk):
    """Create a send-out record for a lab order item."""
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    item = get_object_or_404(LabOrderItem, pk=item_pk)
    if hasattr(item, 'send_out'):
        messages.info(request, 'This test already has a send-out record.')
        return redirect('laboratory:sendout_list')

    if request.method == 'POST':
        from decimal import Decimal, InvalidOperation
        try:
            sendout = SendOutTest(
                order_item=item,
                referral_lab_name=request.POST.get('referral_lab_name', '').strip(),
                referral_lab_address=request.POST.get('referral_lab_address', '').strip(),
                referral_lab_phone=request.POST.get('referral_lab_phone', '').strip(),
                courier=request.POST.get('courier', '').strip(),
                tracking_number=request.POST.get('tracking_number', '').strip(),
                external_cost=Decimal(request.POST.get('external_cost', '0') or '0'),
                markup_percentage=Decimal(request.POST.get('markup_percentage', '0') or '0'),
                created_by=request.user,
            )
            exp_return = request.POST.get('expected_return_date', '').strip()
            if exp_return:
                from datetime import date as _date
                sendout.expected_return_date = _date.fromisoformat(exp_return)
            # Auto-dispatch if courier is filled
            if sendout.courier:
                sendout.status = SendOutTest.Status.DISPATCHED
                sendout.dispatch_date = timezone.now()
                sendout.dispatched_by = request.user
            sendout.save()
            messages.success(request, f'Send-out created: {item.test_type.name} → {sendout.referral_lab_name}')
            return redirect('laboratory:sendout_list')
        except (InvalidOperation, ValueError) as e:
            messages.error(request, f'Invalid data: {e}')

    return render(request, 'laboratory/sendout_form.html', {
        'item': item,
        'default_lab': item.test_type.default_referral_lab,
    })


@login_required
@require_POST
def sendout_update_status_view(request, pk):
    """Update send-out test status (dispatched, received, resulted)."""
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    sendout = get_object_or_404(SendOutTest, pk=pk, is_deleted=False)
    new_status = request.POST.get('status', '')
    if new_status not in dict(SendOutTest.Status.choices):
        messages.error(request, 'Invalid status.')
        return redirect('laboratory:sendout_list')

    sendout.status = new_status
    if new_status == SendOutTest.Status.DISPATCHED and not sendout.dispatch_date:
        sendout.dispatch_date = timezone.now()
        sendout.dispatched_by = request.user
    elif new_status == SendOutTest.Status.RESULTED:
        from datetime import date as _date
        sendout.actual_return_date = _date.today()
        # Handle uploaded report file
        if 'external_report_file' in request.FILES:
            sendout.external_report_file = request.FILES['external_report_file']
        sendout.external_accession_number = request.POST.get('external_accession_number', '').strip()
    sendout.save()
    messages.success(request, f'Send-out status updated to {sendout.get_status_display()}.')
    return redirect('laboratory:sendout_list')


# ══════════════════════════════════════════════════════════════════════════════
# MICROBIOLOGY — Culture, Organisms, Sensitivity
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def culture_create_view(request, item_pk):
    """Create a microbiology culture record for a lab order item."""
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    item = get_object_or_404(LabOrderItem, pk=item_pk)
    if hasattr(item, 'culture'):
        return redirect('laboratory:culture_detail', pk=item.culture.pk)

    if request.method == 'POST':
        culture = CultureResult(
            order_item=item,
            specimen_source=request.POST.get('specimen_source', '').strip(),
            gram_stain_result=request.POST.get('gram_stain_result', '').strip(),
            koh_mount_result=request.POST.get('koh_mount_result', '').strip(),
            culture_media=request.POST.get('culture_media', '').strip(),
            incubation_temp=request.POST.get('incubation_temp', '').strip(),
            incubation_atmosphere=request.POST.get('incubation_atmosphere', '').strip(),
            created_by=request.user,
        )
        if culture.gram_stain_result:
            culture.gram_stain_by = request.user
            culture.gram_stain_at = timezone.now()
        if culture.koh_mount_result:
            culture.koh_mount_at = timezone.now()
        culture.save()
        messages.success(request, 'Culture record created. Gram stain / KOH results saved.')
        return redirect('laboratory:culture_detail', pk=culture.pk)

    return render(request, 'laboratory/culture_form.html', {'item': item})


@login_required
def culture_detail_view(request, pk):
    """View and update a microbiology culture result (staged readings)."""
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    culture = get_object_or_404(
        CultureResult.objects.select_related('order_item__test_type', 'order_item__order__patient')
        .prefetch_related('organisms__sensitivities'),
        pk=pk, is_deleted=False,
    )
    return render(request, 'laboratory/culture_detail.html', {'culture': culture})


@login_required
@require_POST
def culture_update_reading_view(request, pk):
    """Update staged culture reading (24h / 48h / 72h)."""
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    culture = get_object_or_404(CultureResult, pk=pk, is_deleted=False)
    reading = request.POST.get('reading_stage', '')  # '24h', '48h', '72h'
    text = request.POST.get('reading_text', '').strip()
    growth = request.POST.get('growth_status', '')

    now = timezone.now()
    if reading == '24h':
        culture.culture_read_24h = text
        culture.culture_read_24h_at = now
    elif reading == '48h':
        culture.culture_read_48h = text
        culture.culture_read_48h_at = now
    elif reading == '72h':
        culture.culture_read_72h = text
        culture.culture_read_72h_at = now
    elif reading == 'final':
        culture.final_report = text
        culture.final_report_at = now
        culture.is_preliminary = False

    if growth and growth in dict(CultureResult.GrowthStatus.choices):
        culture.growth_status = growth

    culture.save()
    messages.success(request, f'Culture {reading} reading saved.')
    return redirect('laboratory:culture_detail', pk=pk)


@login_required
@require_POST
def organism_add_view(request, culture_pk):
    """Add an identified organism to a culture result."""
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    culture = get_object_or_404(CultureResult, pk=culture_pk, is_deleted=False)
    organism = OrganismIdentification.objects.create(
        culture=culture,
        organism_name=request.POST.get('organism_name', '').strip(),
        organism_code=request.POST.get('organism_code', '').strip(),
        colony_count=request.POST.get('colony_count', '').strip(),
        identification_method=request.POST.get('identification_method', '').strip(),
        is_significant=request.POST.get('is_significant') != '0',
    )
    messages.success(request, f'Organism added: {organism.organism_name}')
    return redirect('laboratory:culture_detail', pk=culture_pk)


@login_required
@require_POST
def sensitivity_add_view(request, organism_pk):
    """Add antibiotic sensitivity results for an organism."""
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    organism = get_object_or_404(OrganismIdentification, pk=organism_pk)
    # Bulk add — expects parallel arrays
    names = request.POST.getlist('antibiotic_name')
    sensitivities = request.POST.getlist('sensitivity')
    zones = request.POST.getlist('zone_diameter_mm')
    mics = request.POST.getlist('mic_value')

    created = 0
    for i, name in enumerate(names):
        if not name.strip():
            continue
        from decimal import Decimal, InvalidOperation
        zone = None
        try:
            zone = Decimal(zones[i]) if i < len(zones) and zones[i].strip() else None
        except (InvalidOperation, ValueError, IndexError):
            pass
        AntibioticSensitivity.objects.create(
            organism=organism,
            antibiotic_name=name.strip(),
            sensitivity=sensitivities[i] if i < len(sensitivities) else 'NT',
            zone_diameter_mm=zone,
            mic_value=mics[i].strip() if i < len(mics) else '',
            method=request.POST.get('method', 'DISK'),
        )
        created += 1

    messages.success(request, f'{created} sensitivity result(s) added.')
    return redirect('laboratory:culture_detail', pk=organism.culture_id)


@login_required
def antibiogram_view(request):
    """View cumulative antibiogram — hospital-wide resistance patterns."""
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    antibiogram = CumulativeAntibiogram.objects.order_by(
        'organism_name', 'antibiotic_name'
    )
    # Build matrix: rows = organisms, cols = antibiotics
    org_data = {}
    antibiotics = set()
    for row in antibiogram:
        antibiotics.add(row.antibiotic_name)
        if row.organism_name not in org_data:
            org_data[row.organism_name] = {}
        org_data[row.organism_name][row.antibiotic_name] = {
            'rate': row.sensitivity_rate,
            'n': row.total_isolates,
        }
    antibiotics = sorted(antibiotics)

    # Pre-build rows for template iteration (avoids dict key lookup issues)
    matrix_rows = []
    for org_name in sorted(org_data.keys()):
        cells = []
        for abx in antibiotics:
            cell = org_data[org_name].get(abx)
            cells.append(cell)  # None if no data
        matrix_rows.append({'name': org_name, 'cells': cells})

    return render(request, 'laboratory/antibiogram.html', {
        'matrix_rows': matrix_rows,
        'antibiotics': antibiotics,
        'has_data': bool(matrix_rows),
    })


@login_required
@require_POST
def generate_antibiogram_view(request):
    """Regenerate cumulative antibiogram from current sensitivity data."""
    if not (request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    from django.db.models import Count
    today = timezone.localdate()
    period_start = today.replace(month=1, day=1)  # current year

    # Clear existing for this period
    CumulativeAntibiogram.objects.filter(period_start=period_start, period_end=today).delete()

    # Aggregate from AntibioticSensitivity
    raw = (
        AntibioticSensitivity.objects.filter(
            organism__culture__created_at__date__gte=period_start,
        )
        .values('organism__organism_name', 'antibiotic_name', 'sensitivity')
        .annotate(count=Count('id'))
    )

    # Build aggregates
    agg = {}
    for r in raw:
        key = (r['organism__organism_name'], r['antibiotic_name'])
        if key not in agg:
            agg[key] = {'S': 0, 'I': 0, 'R': 0, 'total': 0}
        s = r['sensitivity']
        if s in ('S', 'I', 'R'):
            agg[key][s] += r['count']
            agg[key]['total'] += r['count']

    created = 0
    for (org, abx), counts in agg.items():
        if counts['total'] > 0:
            CumulativeAntibiogram.objects.create(
                organism_name=org,
                antibiotic_name=abx,
                period_start=period_start,
                period_end=today,
                total_isolates=counts['total'],
                sensitive_count=counts['S'],
                intermediate_count=counts['I'],
                resistant_count=counts['R'],
            )
            created += 1

    messages.success(request, f'Antibiogram regenerated: {created} entries for {today.year}.')
    return redirect('laboratory:antibiogram')


# ══════════════════════════════════════════════════════════════════════════════
# HISTOPATHOLOGY
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def histopath_list_view(request):
    """List all histopathology specimens."""
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    specimens = (
        HistopathologySpecimen.objects.filter(is_deleted=False)
        .select_related('order_item__order__patient', 'pathologist')
        .order_by('-created_at')[:200]
    )
    return render(request, 'laboratory/histopath_list.html', {'specimens': specimens})


@login_required
def histopath_create_view(request, item_pk):
    """Create a histopathology specimen record."""
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    item = get_object_or_404(LabOrderItem, pk=item_pk)
    if hasattr(item, 'histopath'):
        return redirect('laboratory:histopath_detail', pk=item.histopath.pk)

    if request.method == 'POST':
        specimen = HistopathologySpecimen(
            order_item=item,
            specimen_site=request.POST.get('specimen_site', '').strip(),
            specimen_type=request.POST.get('specimen_type', '').strip(),
            laterality=request.POST.get('laterality', '').strip(),
            clinical_history=request.POST.get('clinical_history', '').strip(),
            created_by=request.user,
        )
        specimen.save()  # auto accession number
        messages.success(request, f'Histopathology specimen {specimen.accession_number} created.')
        return redirect('laboratory:histopath_detail', pk=specimen.pk)

    return render(request, 'laboratory/histopath_form.html', {'item': item})


@login_required
def histopath_detail_view(request, pk):
    """View and update histopathology specimen."""
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    specimen = get_object_or_404(
        HistopathologySpecimen.objects.select_related(
            'order_item__order__patient', 'pathologist', 'gross_by'
        ),
        pk=pk, is_deleted=False,
    )
    return render(request, 'laboratory/histopath_detail.html', {'specimen': specimen})


@login_required
@require_POST
def histopath_update_view(request, pk):
    """Update histopathology specimen status / fields."""
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    specimen = get_object_or_404(HistopathologySpecimen, pk=pk, is_deleted=False)
    section = request.POST.get('section', '')

    if section == 'grossing':
        specimen.gross_description = request.POST.get('gross_description', '').strip()
        specimen.cassette_count = int(request.POST.get('cassette_count', 0) or 0)
        specimen.block_count = int(request.POST.get('block_count', 0) or 0)
        specimen.gross_by = request.user
        specimen.gross_at = timezone.now()
        specimen.status = HistopathologySpecimen.Status.PROCESSING
        specimen.save()
        messages.success(request, 'Gross description saved.')

    elif section == 'microscopy':
        specimen.microscopic_description = request.POST.get('microscopic_description', '').strip()
        specimen.diagnosis = request.POST.get('diagnosis', '').strip()
        specimen.snomed_code = request.POST.get('snomed_code', '').strip()
        specimen.icd_o_code = request.POST.get('icd_o_code', '').strip()
        import json
        special = request.POST.get('special_stains', '').strip()
        ihc = request.POST.get('ihc_stains', '').strip()
        if special:
            specimen.special_stains = [s.strip() for s in special.split(',') if s.strip()]
        if ihc:
            specimen.ihc_stains = [s.strip() for s in ihc.split(',') if s.strip()]
        specimen.status = HistopathologySpecimen.Status.REPORTING
        specimen.save()
        messages.success(request, 'Microscopy description saved.')

    elif section == 'finalize':
        specimen.pathologist = request.user
        specimen.reported_at = timezone.now()
        specimen.storage_location = request.POST.get('storage_location', '').strip()
        specimen.status = HistopathologySpecimen.Status.FINALIZED
        specimen.save()
        messages.success(request, f'Report finalized by {request.user.get_full_name()}.')

    elif section == 'addendum':
        specimen.addendum_text = request.POST.get('addendum_text', '').strip()
        specimen.addendum_by = request.user
        specimen.addendum_at = timezone.now()
        specimen.status = HistopathologySpecimen.Status.ADDENDUM
        specimen.save()
        messages.success(request, 'Addendum added.')

    return redirect('laboratory:histopath_detail', pk=pk)


# ══════════════════════════════════════════════════════════════════════════════
# TAT REPORT
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def tat_report_view(request):
    """Turnaround time report — every transition timestamped."""
    if not (request.user.is_lab_tech or request.user.is_medical_director
            or request.user.is_super_admin or request.user.is_admin_director
            or request.user.is_ceo):
        return HttpResponseForbidden()

    import json
    today = timezone.localdate()
    days = int(request.GET.get('days', 30))
    since = today - timedelta(days=days)

    # Average TAT by segment
    from django.db.models import Min, Max, F, ExpressionWrapper, DurationField

    orders = LabOrder.objects.filter(
        is_deleted=False, created_at__date__gte=since,
        status=LabOrder.Status.COMPLETED,
    )

    # Collect timestamps per order
    tat_data = []
    for order in orders.select_related('patient')[:500]:
        ts = dict(
            order.tat_timestamps.values_list('event', 'timestamp')
        )
        if 'ORDERED' in ts and 'RELEASED' in ts:
            total = (ts['RELEASED'] - ts['ORDERED']).total_seconds() / 60
            segments = {
                'order_to_collect': _mins_between(ts, 'ORDERED', 'COLLECTED'),
                'collect_to_receive': _mins_between(ts, 'COLLECTED', 'RECEIVED_AT_LAB'),
                'receive_to_result': _mins_between(ts, 'RECEIVED_AT_LAB', 'RESULT_ENTERED'),
                'result_to_authorize': _mins_between(ts, 'RESULT_ENTERED', 'AUTHORIZED'),
                'authorize_to_release': _mins_between(ts, 'AUTHORIZED', 'RELEASED'),
                'total_mins': round(total, 1),
            }
            tat_data.append(segments)

    # Averages
    if tat_data:
        avg_tat = {
            k: round(sum(d.get(k, 0) or 0 for d in tat_data) / len(tat_data), 1)
            for k in ['order_to_collect', 'collect_to_receive', 'receive_to_result',
                       'result_to_authorize', 'authorize_to_release', 'total_mins']
        }
    else:
        avg_tat = {}

    return render(request, 'laboratory/tat_report.html', {
        'avg_tat': avg_tat,
        'total_orders': len(tat_data),
        'days': days,
        'tat_json': json.dumps(tat_data[:200]),
    })


def _mins_between(ts_dict, event_a, event_b):
    a = ts_dict.get(event_a)
    b = ts_dict.get(event_b)
    if a and b:
        return round((b - a).total_seconds() / 60, 1)
    return None


# ══════════════════════════════════════════════════════════════════════════════
# DUPLICATE ORDER CHECK (AJAX)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def check_duplicate_order_ajax(request):
    """AJAX — check if patient already has recent orders for selected tests."""
    patient_id = request.GET.get('patient_id', '')
    test_ids = request.GET.getlist('test_ids')
    if not patient_id or not test_ids:
        return JsonResponse({'duplicates': []})

    recent = (
        LabOrderItem.objects.filter(
            order__patient_id=patient_id,
            order__is_deleted=False,
            order__created_at__gte=timezone.now() - timedelta(hours=24),
            test_type_id__in=test_ids,
        )
        .exclude(order__status=LabOrder.Status.CANCELLED)
        .select_related('test_type', 'order')
        .values('test_type__name', 'test_type_id', 'order__created_at')
    )
    return JsonResponse({
        'duplicates': [
            {
                'name': r['test_type__name'],
                'test_id': str(r['test_type_id']),
                'ordered_at': r['order__created_at'].strftime('%d/%m/%Y %H:%M'),
            }
            for r in recent
        ]
    })
