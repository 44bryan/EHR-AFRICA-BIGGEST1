from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Count, Avg, Q
from datetime import timedelta
from .models import LabOrder, LabOrderItem, LabResult, LabTestType, SampleCollection
from .forms import LabOrderForm, LabResultFormSet, SampleCollectionForm
from apps.consultations.models import Consultation


@login_required
def lab_dashboard(request):
    """Lab technician workstation dashboard."""
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_admin_staff):
        return HttpResponseForbidden()

    today = timezone.localdate()
    month_start = today.replace(day=1)

    # Pending work — last 7 days only (avoids pulling historical backlog)
    week_ago = today - timedelta(days=7)
    pending_orders = LabOrder.objects.filter(
        is_deleted=False,
        status__in=['ORDERED', 'SAMPLE_COLLECTED', 'PROCESSING'],
        created_at__date__gte=week_ago,
    ).select_related('patient', 'ordered_by').order_by('-created_at')[:200]

    # Today's completed
    completed_today = LabOrder.objects.filter(
        status='COMPLETED', is_deleted=False,
        updated_at__date=today,
    ).count()

    # Critical results this month (unverified)
    critical_unverified = LabResult.objects.filter(
        is_critical=True, is_verified=False,
        is_deleted=False,
    ).select_related('order_item__order__patient', 'order_item__test_type')

    # Abnormal this month
    abnormal_count = LabResult.objects.filter(
        is_abnormal=True, is_deleted=False,
        created_at__date__gte=month_start,
    ).count()

    # Stats by category this month
    category_stats = (
        LabOrderItem.objects.filter(
            order__is_deleted=False,
            order__created_at__date__gte=month_start,
        )
        .values('test_type__category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # Turnaround time (ordered → completed, last 30 days)
    # We approximate using created_at vs updated_at for completed orders
    completed_this_month = LabOrder.objects.filter(
        status='COMPLETED', is_deleted=False,
        updated_at__date__gte=month_start,
    ).count()

    # Patients waiting at lab (visit status = LABORATORY, today)
    from apps.patients.models import Visit
    from django.db.models import Case, When, IntegerField, Value as _V
    _tier_order = Case(When(service_tier='VIP', then=_V(3)), When(service_tier='FAST_TRACK', then=_V(2)),
                       When(service_tier='EXPRESS', then=_V(1)), default=_V(0), output_field=IntegerField())
    _pt = getattr(request.user, 'patient_tier', 'ALL')
    _lab_qs = Visit.objects.filter(visit_date__date=today, status='LABORATORY', is_deleted=False)
    if _pt == 'VIP':
        _lab_qs = _lab_qs.filter(service_tier='VIP')
    elif _pt == 'EXPRESS':
        _lab_qs = _lab_qs.filter(service_tier__in=['EXPRESS', 'FAST_TRACK'])
    elif _pt == 'STANDARD':
        _lab_qs = _lab_qs.filter(service_tier='STANDARD')
    # _pt == 'ALL' → no filter
    waiting_visits = list(_lab_qs.select_related('patient', 'attending_doctor')
                          .annotate(_tier_order=_tier_order).order_by('-_tier_order', 'visit_date'))

    # Annotate each pending order with payment status and elapsed time
    pending_orders = list(pending_orders)
    now_dt = timezone.now()
    try:
        from apps.billing.models import ServiceWorkOrder, WorkOrderStatus, ServiceCategory
        # Per-test payment: find which lab_order_items have an ACTIVE (PENDING/DONE) work order
        active_item_ids = set(
            ServiceWorkOrder.objects.filter(
                category=ServiceCategory.LABORATORY,
                status__in=[WorkOrderStatus.PENDING, WorkOrderStatus.DONE],
                lab_order_item__isnull=False,
                is_deleted=False,
            ).values_list('lab_order_item__order_id', flat=True)
        )
        for order in pending_orders:
            order.is_paid = order.id in active_item_ids
            # Elapsed time since order was placed
            delta = now_dt - order.created_at
            total_mins = int(delta.total_seconds() // 60)
            if total_mins < 60:
                order.elapsed = f'{total_mins}m'
            else:
                order.elapsed = f'{total_mins // 60}h {total_mins % 60}m'
            order.elapsed_mins = total_mins
    except Exception:
        for order in pending_orders:
            order.is_paid = None
            order.elapsed = ''
            order.elapsed_mins = 0

    context = {
        'pending_orders': pending_orders,
        'pending_count': len(pending_orders),
        'completed_today': completed_today,
        'completed_this_month': completed_this_month,
        'critical_unverified': critical_unverified,
        'critical_count': critical_unverified.count(),
        'abnormal_count': abnormal_count,
        'category_stats': category_stats,
        'today': today,
        'waiting_visits': waiting_visits,
    }
    return render(request, 'laboratory/dashboard.html', context)


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
            or request.user.is_ceo or request.user.is_admin_director):
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
            from apps.accounts.models import HospitalConfig
            _cached['config'] = HospitalConfig.get()
            return render(request, 'laboratory/stats_pdf.html', _cached)
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

    # Daily volume
    daily_volume = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        cnt = LabOrder.objects.filter(is_deleted=False, created_at__date=d).count()
        daily_volume.append({'date': d.strftime('%d %b'), 'count': cnt})

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
    TIER_DISPLAY = {'VIP': 'VIP', 'EXPRESS': 'Express', 'FAST_TRACK': 'Fast Track', 'STANDARD': 'Standard'}
    TIER_ORDER   = ['VIP', 'EXPRESS', 'FAST_TRACK', 'STANDARD']

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
    }
    cache.set(_cache_key, context, _cache_ttl)
    if request.GET.get('pdf'):
        from apps.accounts.models import HospitalConfig
        context['config'] = HospitalConfig.get()
        return render(request, 'laboratory/stats_pdf.html', context)
    return render(request, 'laboratory/stats.html', context)


@login_required
def verify_result(request, result_id):
    """Lab senior / director verifies a result."""
    if not (request.user.is_medical_director or request.user.is_lab_tech):
        return HttpResponseForbidden()
    result = get_object_or_404(LabResult, pk=result_id, is_deleted=False)
    result.is_verified = True
    result.verified_by = request.user
    result.verified_at = timezone.now()
    result.save(update_fields=['is_verified', 'verified_by', 'verified_at', 'updated_at'])
    messages.success(request, 'Result verified.')
    # Check if all results are done — auto-return patient to doctor queue
    try:
        visit = result.order_item.order.consultation.visit if result.order_item.order.consultation else None
        if visit:
            from apps.core.patient_flow import check_and_autoreturn_to_doctor
            check_and_autoreturn_to_doctor(visit, triggered_by=request.user)
    except Exception:
        pass
    return redirect('laboratory:detail', pk=result.order_item.order.pk)


@login_required
def lab_order_view(request, consultation_pk):
    if not request.user.can_order_investigations():
        return HttpResponseForbidden()

    consultation = get_object_or_404(Consultation, pk=consultation_pk)
    test_types = LabTestType.objects.filter(is_active=True).order_by('category', 'name')

    if request.method == 'POST':
        form = LabOrderForm(request.POST)
        selected_tests = request.POST.getlist('test_types')
        if form.is_valid() and selected_tests:
            order = form.save(commit=False)
            order.consultation = consultation
            order.patient = consultation.patient
            order.ordered_by = request.user
            order.created_by = request.user
            order.save()
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
        'categories': LabTestType.objects.values_list('category', flat=True).distinct(),
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
    return render(request, 'laboratory/detail.html', {
        'order': order,
        'sample': sample,
        'all_verified': all_verified,
    })


@login_required
@login_required
def bulk_collect_sample_view(request):
    """Mark multiple lab orders as SAMPLE_COLLECTED in one click."""
    from django.views.decorators.http import require_POST as _rp
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()
    if request.method != 'POST':
        return redirect('laboratory:dashboard')
    pks = request.POST.getlist('order_ids')
    if not pks:
        messages.warning(request, 'No orders selected.')
        return redirect('laboratory:dashboard')
    updated = LabOrder.objects.filter(
        pk__in=pks,
        status=LabOrder.Status.ORDERED,
        is_deleted=False,
    ).update(status=LabOrder.Status.SAMPLE_COLLECTED)
    messages.success(request, f'{updated} order(s) marked as Sample Collected.')
    return redirect('laboratory:dashboard')


@login_required
def collect_sample_view(request, pk):
    if not (request.user.is_lab_tech or request.user.is_medical_director):
        return HttpResponseForbidden()
    order = get_object_or_404(LabOrder, pk=pk)
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
                result, _ = LabResult.objects.get_or_create(
                    order_item=item,
                    defaults={
                        'performed_by': request.user,
                        'created_by': request.user,
                    }
                )
                # Skip verified results — they are locked
                if result.is_verified:
                    continue
                result.result_value = value
                result.result_unit = request.POST.get(f'result_unit_{item.pk}', '')
                result.reference_range = request.POST.get(f'ref_range_{item.pk}', '')
                result.is_abnormal = request.POST.get(f'is_abnormal_{item.pk}') == 'on'
                result.is_critical = request.POST.get(f'is_critical_{item.pk}') == 'on'
                result.comment = request.POST.get(f'comment_{item.pk}', '')
                result.performed_by = request.user
                result.save()
                if result.is_critical:
                    try:
                        from apps.notifications.utils import notify_critical_lab_result
                        notify_critical_lab_result(result)
                        _had_critical = True
                    except Exception:
                        pass
                item.status = LabOrder.Status.COMPLETED
                item.save(update_fields=['status'])

        order.status = LabOrder.Status.COMPLETED
        order.save(update_fields=['status'])
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
        except Exception:
            pass
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


@login_required
def cancel_lab_order(request, pk):
    """
    Cancel a lab order that has not yet been processed.
    Allowed by: the doctor who ordered it, lab tech, or medical director.
    Only orders in ORDERED status can be cancelled (not after sample collected/processing).
    """
    from django.views.decorators.http import require_POST
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
            'Contact the lab technician.'
        )
        return redirect('laboratory:detail', pk=pk)

    if request.method != 'POST':
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
