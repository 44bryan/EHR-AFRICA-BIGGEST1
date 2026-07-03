from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db.models import Q, Sum
from django.utils import timezone
from django.http import JsonResponse
from .models import Drug, DrugStock, Dispensing, DispensingItem, DispensingStatus, StockAdjustment, AdjustmentReason
from .forms import DrugCreateForm, AddStockForm, DispensingItemForm
from apps.patients.models import Patient
from apps.prescriptions.models import DrugPrescription


@login_required
def pharmacy_dashboard(request):
    today = timezone.localdate()
    all_drugs = list(Drug.objects.filter(is_active=True, is_deleted=False))
    low_stock_drugs = [d for d in all_drugs if d.needs_reorder]

    # Expiry buckets
    _base_expiry_qs = DrugStock.objects.filter(
        is_deleted=False,
        expiry_date__gte=today,
        quantity_remaining__gt=0,
    ).select_related('drug').order_by('expiry_date')
    expiring_critical = list(_base_expiry_qs.filter(
        expiry_date__lte=today + timezone.timedelta(days=30)
    ))
    expiring_warning = list(_base_expiry_qs.filter(
        expiry_date__gt=today + timezone.timedelta(days=30),
        expiry_date__lte=today + timezone.timedelta(days=60),
    ))
    expiring_notice = list(_base_expiry_qs.filter(
        expiry_date__gt=today + timezone.timedelta(days=60),
        expiry_date__lte=today + timezone.timedelta(days=90),
    ))
    expiring_soon = expiring_critical + expiring_warning + expiring_notice

    # Already expired batches still in stock
    expired_in_stock = list(
        DrugStock.objects.filter(
            is_deleted=False,
            expiry_date__lt=today,
            quantity_remaining__gt=0,
        ).select_related('drug').order_by('expiry_date')
    )

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
    waiting_visits = list(
        Visit.objects.filter(
            visit_date__date=today,
            status='PHARMACY',
            is_deleted=False,
        ).exclude(
            patient_id__in=work_order_patient_ids,
        ).select_related('patient', 'attending_doctor').order_by('visit_date')
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
            status=DispensingStatus.PENDING, is_deleted=False
        ).count(),
        'total_drugs': len(all_drugs),
        'pharmacy_work_orders': pharmacy_work_orders,
        'waiting_visits': waiting_visits,
    }
    return render(request, 'pharmacy/dashboard.html', context)


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

    # Require an open shift for pharmacists collecting cash at the pharmacy counter
    from apps.accounts.models import UserRole as _UR
    if request.user.role == _UR.PHARMACIST:
        from apps.billing.models import CashierShift, ShiftStatus
        _today = timezone.localdate()
        _open_shift = CashierShift.objects.filter(
            cashier=request.user, shift_date=_today,
            status=ShiftStatus.OPEN, is_deleted=False,
        ).first()
        if not _open_shift:
            messages.error(
                request,
                'Open your cash desk shift before collecting payment. '
                'Click "My Cash Desk" in the sidebar.'
            )
            return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)

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

    # Step 4: Close the patient visit if still in PHARMACY status
    try:
        from apps.patients.models import Visit
        visit = Visit.objects.filter(
            patient=dispensing.patient,
            status='PHARMACY',
            is_deleted=False,
        ).order_by('-visit_date').first()
        if visit:
            visit.status = 'COMPLETED'
            visit.save(update_fields=['status', 'updated_at'])
    except Exception:
        pass

    messages.success(
        request,
        f'Payment of {int(amount):,} FCFA collected. '
        f'Drugs dispensed — {dispensing.dispensing_number} complete.'
    )
    return redirect('pharmacy:dispensing_detail', dispensing_id=dispensing.id)


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
