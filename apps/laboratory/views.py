from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Count, Avg, Q, Sum
from datetime import timedelta
from .models import LabOrder, LabOrderItem, LabResult, LabTestType, SampleCollection, SampleRejection, LabResultAmendment
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
    }
    cache.set(_cache_key, context, _cache_ttl)
    if request.GET.get('pdf'):
        from apps.reports.views import render_pdf
        context['pdf_filename'] = 'laboratory-stats.pdf'
        return render_pdf('laboratory/stats_pdf.html', context)
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
            'Contact the requesting doctor to discuss further action.'
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
    w.writerow(['Completed', base_orders.filter(status='COMPLETED').count()])
    completion = base_orders.filter(status='COMPLETED').count()
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
        .extra(select={'day': 'DATE(result_date)'})
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
            .extra(select={'day': 'DATE(result_date)'})
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
    order.notes = (order.notes + '\n' if order.notes else '') + \
                  f'SAMPLE REJECTED [{reason}]: {notes}'
    order.save(update_fields=['status', 'notes', 'updated_at'])
    order.items.update(status=LabOrder.Status.ORDERED)

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
    result = get_object_or_404(LabResult, pk=result_id, is_critical=True)
    # Only the ordering doctor or medical director can acknowledge
    if not (request.user == result.order_item.order.ordered_by
            or request.user.is_medical_director or request.user.is_super_admin):
        return HttpResponseForbidden()

    if result.critical_acknowledged_at:
        messages.info(request, 'Already acknowledged.')
        return redirect('laboratory:detail', pk=result.order_item.order.pk)

    result.critical_acknowledged_by = request.user
    result.critical_acknowledged_at = timezone.now()
    result.save(update_fields=['critical_acknowledged_by', 'critical_acknowledged_at', 'updated_at'])

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
    return render_pdf('laboratory/result_pdf.html', {
        'order': order,
        'completed_items': completed_items,
        'pdf_filename': f'lab-result-{order.patient.patient_id}-{order.created_at:%Y%m%d}.pdf',
        'pdf_seal_label': 'LABORATORY REPORT',
    })
