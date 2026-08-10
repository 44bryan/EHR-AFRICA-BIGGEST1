from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db.models import Q, Sum, F, Value, IntegerField
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.http import JsonResponse
from .models import (
    Drug, DrugStock, Dispensing, DispensingItem, DispensingStatus,
    StockAdjustment, AdjustmentReason,
    ControlledDrugEntry, ControlledDrugEntryType,
    WardDrugReturn, WardDrugReturnStatus,
    ChronicPrescription,
)
from .forms import DrugCreateForm, AddStockForm, DispensingItemForm
from apps.patients.models import Patient
from apps.prescriptions.models import DrugPrescription


@login_required
def pharmacy_dashboard(request):
    from django.core.cache import cache
    today = timezone.localdate()
    # ── Stock & expiry data — cached 90s (changes infrequently, auto-refresh is 30s) ──
    _cache_key = f'pharm_stock_data_{today}'
    _cached_stock = cache.get(_cache_key)
    if _cached_stock is None:
        _stock_q = Q(stock_items__is_deleted=False, stock_items__expiry_date__gte=today)
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
            ).select_related('prescribed_by').prefetch_related('items')
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

    declined_today = 0

    context = {
        'low_stock_count': len(low_stock_drugs),
        'low_stock_drugs': low_stock_drugs[:15],
        'expiring_soon': expiring_soon,
        'expiring_critical': expiring_critical,
        'expiring_warning': expiring_warning,
        'expiring_notice': expiring_notice,
        'expired_in_stock': expired_in_stock,
        'today_dispensings': today_dispensings.count(),
        'today_revenue': pharmacy_billed_today,
        'pending_dispensings': Dispensing.objects.filter(
            status__in=[DispensingStatus.PENDING, DispensingStatus.PARTIAL],
            created_at__date=today,
            is_deleted=False,
        ).count(),
        'total_drugs': Drug.objects.filter(is_active=True, is_deleted=False).count(),
        'pharmacy_work_orders': pharmacy_work_orders,
        'waiting_visits': waiting_visits,
        'my_shift': my_shift,
        'declined_today': declined_today,
    }
    return render(request, 'pharmacy/dashboard.html', context)


@login_required
def pharmacy_stats_view(request):
    """Monthly pharmacy statistics — dispensings, top drugs, revenue, gender breakdown."""
    if not (request.user.is_pharmacist or request.user.is_medical_director
            or request.user.is_admin_staff or request.user.is_super_admin
            or request.user.is_ceo or request.user.is_admin_director
            or request.user.is_finance_director):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    import json, calendar
    from datetime import date as _date
    from django.db.models import Count, Sum, Q as _Q

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

    total_dispensings  = base.count()
    total_items        = base_items.count()
    dispensed_count    = base.filter(status=DispensingStatus.DISPENSED).count()
    partial_count      = base.filter(status=DispensingStatus.PARTIAL).count()
    cancelled_count    = base.filter(status=DispensingStatus.CANCELLED).count()
    completion_rate    = round(dispensed_count / total_dispensings * 100, 1) if total_dispensings else 0

    # Revenue (total_amount on dispensed records)
    revenue = base.filter(status=DispensingStatus.DISPENSED).aggregate(
        total=Sum('total_amount')
    )['total'] or 0

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

    # Daily volume (last 14 days)
    from datetime import timedelta
    daily_volume = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        cnt = Dispensing.objects.filter(is_deleted=False, dispensed_at__date=d).count()
        daily_volume.append({'date': d.strftime('%d %b'), 'count': cnt})
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

    # Status doughnut
    status_json = json.dumps({
        'labels': ['Dispensed', 'Partial', 'Cancelled', 'Pending'],
        'data':   [dispensed_count, partial_count, cancelled_count,
                   total_dispensings - dispensed_count - partial_count - cancelled_count],
    })

    # Low stock snapshot
    low_stock_drugs = [d for d in Drug.objects.filter(is_active=True, is_deleted=False) if d.needs_reorder]

    # Month nav
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1)  if month == 12 else (year, month + 1)

    context = {
        'year': year, 'month': month,
        'month_name': _date(year, month, 1).strftime('%B %Y'),
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
        'today': today,
    }
    return render(request, 'pharmacy/stats.html', context)


@login_required
def drug_list(request):
    q = request.GET.get('q', '')
    category = request.GET.get('category', '')
    drugs = Drug.objects.filter(is_deleted=False)
    if q:
        drugs = drugs.filter(Q(name__icontains=q) | Q(generic_name__icontains=q) | Q(brand_name__icontains=q))
    if category:
        drugs = drugs.filter(category=category)
    drugs = drugs.order_by('name')
    from .models import DrugCategory
    return render(request, 'pharmacy/drug_list.html', {
        'drugs': drugs, 'search': q, 'category': category,
        'categories': DrugCategory.choices,
    })


@login_required
def drug_detail(request, drug_id):
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
    form = DrugCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        drug = form.save(commit=False)
        drug.created_by = request.user
        drug.save()
        messages.success(request, f'{drug.name} added to formulary.')
        return redirect('pharmacy:drug_detail', drug_id=drug.id)
    return render(request, 'pharmacy/drug_form.html', {'form': form, 'action': 'Add New Drug'})


@login_required
def drug_edit(request, drug_id):
    drug = get_object_or_404(Drug, id=drug_id, is_deleted=False)
    form = DrugCreateForm(request.POST or None, instance=drug)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'{drug.name} updated.')
        return redirect('pharmacy:drug_detail', drug_id=drug.id)
    return render(request, 'pharmacy/drug_form.html', {'form': form, 'drug': drug, 'action': f'Edit: {drug.name}'})


@login_required
def add_stock(request, drug_id):
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
                expiry_date__gte=timezone.localdate()
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
        dispensing.status = DispensingStatus.PARTIAL
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
    drugs = Drug.objects.filter(is_active=True, is_deleted=False)
    if q:
        drugs = drugs.filter(
            Q(name__icontains=q) | Q(generic_name__icontains=q) | Q(brand_name__icontains=q)
        )
    drugs = drugs.order_by('name')[:25]
    return JsonResponse({'drugs': [
        {
            'id': str(d.id),
            'name': d.name,
            'generic': d.generic_name,
            'strength': d.strength or '',
            'form': d.get_form_display(),
            'stock': d.current_stock,
            'price': str(d.selling_price),
            'low': d.needs_reorder,
        }
        for d in drugs
    ]})


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
            expiry_date__gte=timezone.localdate()
        ).order_by('expiry_date').first()

    item = DispensingItem.objects.create(
        dispensing=dispensing,
        drug=drug,
        stock_batch=batch,
        quantity_dispensed=qty,
        unit_price=unit_price,
        instructions=request.POST.get('instructions', '').strip(),
    )

    total = DispensingItem.objects.filter(dispensing=dispensing).aggregate(t=Sum('subtotal'))['t'] or 0
    dispensing.total_amount = total
    dispensing.status = DispensingStatus.PARTIAL
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
            'batch': batch.batch_number if batch else 'Auto',
            'expiry': batch.expiry_date.strftime('%b %Y') if batch else '',
            'qty': qty,
            'unit_price': str(unit_price),
            'subtotal': str(item.subtotal),
            'instructions': item.instructions,
        },
        'total': str(total),
        'interactions': interactions,
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
    dispensing.status = DispensingStatus.PARTIAL
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
def drug_stock_ajax(request):
    """Return available stock batches for a drug as JSON (for dynamic form)."""
    drug_id = request.GET.get('drug_id')
    if not drug_id:
        return JsonResponse({'batches': [], 'selling_price': 0})
    drug = Drug.objects.filter(id=drug_id, is_deleted=False).first()
    if not drug:
        return JsonResponse({'batches': [], 'selling_price': 0})
    batches = DrugStock.objects.filter(
        drug=drug, is_deleted=False, quantity_remaining__gt=0,
        expiry_date__gte=timezone.localdate()
    ).order_by('expiry_date')
    return JsonResponse({
        'selling_price': str(drug.selling_price),
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


@login_required
def dispensing_detail(request, dispensing_id):
    dispensing = get_object_or_404(
        Dispensing.objects.prefetch_related('items__drug', 'items__stock_batch'),
        id=dispensing_id, is_deleted=False
    )
    ctx = {'dispensing': dispensing}
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
def complete_dispensing(request, dispensing_id):
    """
    Collect payment at pharmacy counter and dispense drugs in one step.
    Pharmacist enters payment method + amount → invoice created → payment recorded → drugs dispensed.
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

    try:
        amount = Decimal(amount_str) if amount_str else dispensing.total_amount
    except InvalidOperation:
        messages.error(request, 'Invalid payment amount.')
        return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)

    if amount <= 0:
        messages.error(request, 'Payment amount must be greater than zero.')
        return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)

    # Guard: pharmacy counter always collects full payment — no partial dispensing allowed
    if amount < dispensing.total_amount:
        messages.error(
            request,
            f'Amount entered ({int(amount):,} FCFA) is less than the total '
            f'({int(dispensing.total_amount):,} FCFA). '
            'Full payment is required before drugs can be dispensed.'
        )
        return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)

    # Step 1: Bill — add dispensing items to patient invoice
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

    # Step 4: Move patient visit from PHARMACY → WAITING_DISCHARGE so they
    # can be routed back to reception/exit. Do NOT mark COMPLETED — the visit
    # may still have other pending stops (cashier, etc.)
    try:
        from apps.patients.models import Visit
        visit = Visit.objects.filter(
            patient=dispensing.patient,
            status='PHARMACY',
            is_deleted=False,
        ).order_by('-visit_date').first()
        if visit:
            # Move to BILLING so reception/cashier can confirm any remaining
            # outstanding items before final discharge. Do NOT mark COMPLETED
            # here — the central cashier decides when the visit is fully done.
            visit.status = 'BILLING'
            visit.save(update_fields=['status', 'updated_at'])
    except Exception:
        pass

    messages.success(
        request,
        f'Payment of {int(amount):,} FCFA collected. '
        f'Drugs dispensed — {dispensing.dispensing_number} complete.'
    )
    # Return to pharmacy dashboard so pharmacist can handle the next patient
    return redirect('pharmacy:dashboard')


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
    dispensing.status = DispensingStatus.CANCELLED
    dispensing.notes = f'[CANCELLED] {reason}\n{dispensing.notes or ""}'.strip()
    dispensing.save(update_fields=['status', 'notes'])

    messages.warning(request, f'Dispensing {dispensing.dispensing_number} has been cancelled.')
    return redirect('pharmacy:dashboard')


@login_required
def dispensing_list(request):
    dispensings = Dispensing.objects.filter(is_deleted=False).select_related(
        'patient', 'dispensed_by'
    ).order_by('-dispensed_at')[:100]
    return render(request, 'pharmacy/dispensing_list.html', {'dispensings': dispensings})


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
        Dispensing.objects.prefetch_related('items__drug', 'items__stock_batch'),
        id=dispensing_id, is_deleted=False,
    )
    balance_due = max(dispensing.total_amount - dispensing.amount_paid, 0)
    return render(request, 'pharmacy/dispensing_receipt.html', {
        'dispensing': dispensing,
        'balance_due': balance_due,
    })


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
            expiry_date__gte=today,
        ).order_by('expiry_date').first()

        if not batch:
            # Try any batch with any remaining quantity
            batch = DrugStock.objects.filter(
                drug=drug, is_deleted=False,
                quantity_remaining__gt=0,
                expiry_date__gte=today,
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
            unit_price=drug.selling_price,
            instructions=instructions,
        )
        matched_count += 1

    # Update dispensing total
    total = DispensingItem.objects.filter(dispensing=dispensing).aggregate(
        t=Sum('subtotal')
    )['t'] or 0
    dispensing.total_amount = total
    if matched_count > 0:
        dispensing.status = DispensingStatus.PARTIAL
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


# ── Controlled Drugs Register ─────────────────────────────────────────────────

@login_required
def controlled_register(request):
    """Narcotics/controlled drug register — full movement log."""
    from apps.core.decorators import CAN_VIEW_PATIENT
    if request.user.role not in CAN_VIEW_PATIENT and not request.user.is_super_admin:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

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
    base_qs = DrugStock.objects.filter(is_deleted=False, quantity_remaining__gt=0).select_related('drug')

    expired           = base_qs.filter(expiry_date__lt=today).order_by('expiry_date')
    expiring_30       = base_qs.filter(expiry_date__gte=today, expiry_date__lte=today + timezone.timedelta(days=30)).order_by('expiry_date')
    expiring_60       = base_qs.filter(expiry_date__gt=today + timezone.timedelta(days=30), expiry_date__lte=today + timezone.timedelta(days=60)).order_by('expiry_date')
    expiring_90       = base_qs.filter(expiry_date__gt=today + timezone.timedelta(days=60), expiry_date__lte=today + timezone.timedelta(days=90)).order_by('expiry_date')
    low_stock         = [d for d in Drug.objects.filter(is_active=True, is_deleted=False).annotate(
        stock_total=Coalesce(Sum(F('stock_items__quantity_remaining'), filter=Q(stock_items__is_deleted=False)), Value(0), output_field=IntegerField())
    ) if d.stock_total <= d.reorder_level]

    return render(request, 'pharmacy/expiry_alerts.html', {
        'expired': expired,
        'expiring_30': expiring_30,
        'expiring_60': expiring_60,
        'expiring_90': expiring_90,
        'low_stock': low_stock,
        'today': today,
    })
