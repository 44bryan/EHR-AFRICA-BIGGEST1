from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum
from django.utils import timezone
from .models import (
    InventoryItem, Vendor, PurchaseOrder, PurchaseOrderItem,
    StockMovement, ItemCategory, BatchStock,
    DepartmentRequisition, RequisitionItem, RequisitionStatus,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _trigger_auto_reorder(item, user):
    """
    If item.needs_reorder and it has a preferred_vendor, create a draft PO
    automatically (only if no open PO already exists for this item).
    ISO 9001 §7.4 / JCI MMU.3 automated reorder.
    """
    if not item.needs_reorder:
        return
    if not item.preferred_vendor:
        return
    # Check for an existing open PO containing this item
    open_po_exists = PurchaseOrderItem.objects.filter(
        item=item,
        purchase_order__status__in=['DRAFT', 'SUBMITTED', 'APPROVED'],
        purchase_order__is_deleted=False,
    ).exists()
    if open_po_exists:
        return
    # Create a draft auto-reorder PO
    po = PurchaseOrder.objects.create(
        vendor=item.preferred_vendor,
        status='DRAFT',
        notes=f'Auto-reorder: {item.name} stock fell to {item.current_stock} (reorder level: {item.reorder_level})',
        is_auto_generated=True,
        created_by=user,
    )
    qty_to_order = max(item.reorder_level * 2, 10)  # order 2× reorder level
    PurchaseOrderItem.objects.create(
        purchase_order=po,
        item=item,
        quantity_ordered=qty_to_order,
        unit_price=item.unit_cost,
        subtotal=qty_to_order * item.unit_cost,
    )
    po.total_amount = qty_to_order * item.unit_cost
    po.save(update_fields=['total_amount'])


# ── Dashboard ─────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    today = timezone.localdate()
    low_stock = [i for i in InventoryItem.objects.filter(is_active=True, is_deleted=False) if i.needs_reorder]

    # Expiry alerts (items with batch stock expiring in ≤ 90 days or already expired)
    expiring_soon = BatchStock.objects.filter(
        is_quarantined=False,
        quantity_remaining__gt=0,
        expiry_date__lte=today + timezone.timedelta(days=90),
    ).select_related('item').order_by('expiry_date')

    expired_count = BatchStock.objects.filter(
        quantity_remaining__gt=0,
        expiry_date__lt=today,
    ).count()

    pending_reqs = DepartmentRequisition.objects.filter(
        status='PENDING', is_deleted=False
    ).count()

    context = {
        'total_items':      InventoryItem.objects.filter(is_active=True, is_deleted=False).count(),
        'low_stock_count':  len(low_stock),
        'low_stock_items':  low_stock[:10],
        'pending_pos':      PurchaseOrder.objects.filter(
            status__in=['SUBMITTED', 'APPROVED'], is_deleted=False
        ).count(),
        'vendors_count':    Vendor.objects.filter(is_active=True, is_deleted=False).count(),
        'expiring_soon':    expiring_soon[:10],
        'expiring_count':   expiring_soon.count(),
        'expired_count':    expired_count,
        'pending_reqs':     pending_reqs,
    }
    return render(request, 'inventory/dashboard.html', context)


# ── Item list / detail ────────────────────────────────────────────────────────

@login_required
def item_list(request):
    q        = request.GET.get('q', '')
    category = request.GET.get('category', '')
    items    = InventoryItem.objects.filter(is_deleted=False)
    if q:
        items = items.filter(Q(name__icontains=q) | Q(item_code__icontains=q))
    if category:
        items = items.filter(category=category)
    return render(request, 'inventory/item_list.html', {
        'items':      items.order_by('name'),
        'search':     q,
        'category':   category,
        'categories': ItemCategory.choices,
    })


@login_required
def item_detail(request, item_id):
    item      = get_object_or_404(InventoryItem, id=item_id, is_deleted=False)
    movements = item.movements.order_by('-created_at')[:30]
    batches   = item.batches.order_by('expiry_date') if item.requires_expiry_tracking else []
    return render(request, 'inventory/item_detail.html', {
        'item':      item,
        'movements': movements,
        'batches':   batches,
    })


# ── Stock adjustment ──────────────────────────────────────────────────────────

@login_required
def stock_adjustment(request, item_id):
    item = get_object_or_404(InventoryItem, id=item_id, is_deleted=False)
    if request.method == 'POST':
        qty       = int(request.POST.get('quantity', 0) or 0)
        move_type = request.POST.get('movement_type', 'IN')
        notes     = request.POST.get('notes', '')
        if move_type == 'OUT':
            qty = -qty
        item.current_stock = max(0, item.current_stock + qty)
        item.save()
        StockMovement.objects.create(
            item=item, movement_type=move_type,
            quantity=qty, balance_after=item.current_stock,
            notes=notes, performed_by=request.user,
        )
        if move_type == 'OUT':
            _trigger_auto_reorder(item, request.user)
        messages.success(request, 'Stock adjusted successfully.')
        return redirect('inventory:item_detail', item_id=item.id)
    return render(request, 'inventory/stock_adjustment.html', {'item': item})


# ── Purchase Orders ───────────────────────────────────────────────────────────

@login_required
def purchase_order_list(request):
    pos = PurchaseOrder.objects.filter(is_deleted=False).select_related('vendor').order_by('-ordered_date')
    return render(request, 'inventory/po_list.html', {'purchase_orders': pos})


@login_required
def po_create(request):
    vendors = Vendor.objects.filter(is_active=True, is_deleted=False).order_by('name')
    items   = InventoryItem.objects.filter(is_active=True, is_deleted=False).order_by('name')

    if request.method == 'POST':
        vendor        = get_object_or_404(Vendor, id=request.POST.get('vendor_id', ''), is_deleted=False)
        expected_date = request.POST.get('expected_date') or None
        notes         = request.POST.get('notes', '').strip()

        po = PurchaseOrder.objects.create(
            vendor=vendor, expected_date=expected_date,
            notes=notes, status='SUBMITTED', created_by=request.user,
        )

        item_ids    = request.POST.getlist('item_id[]')
        quantities  = request.POST.getlist('quantity[]')
        unit_prices = request.POST.getlist('unit_price[]')
        total = 0
        for item_id, qty_str, price_str in zip(item_ids, quantities, unit_prices):
            if not item_id or not qty_str:
                continue
            try:
                qty      = int(qty_str)
                price    = float(price_str or 0)
                inv_item = InventoryItem.objects.get(id=item_id)
                sub      = qty * price
                PurchaseOrderItem.objects.create(
                    purchase_order=po, item=inv_item,
                    quantity_ordered=qty, unit_price=price, subtotal=sub,
                )
                total += sub
            except (ValueError, InventoryItem.DoesNotExist):
                continue

        po.total_amount = total
        po.save(update_fields=['total_amount'])
        messages.success(request, f'Purchase order {po.po_number} created.')
        return redirect('inventory:po_detail', po_id=po.id)

    return render(request, 'inventory/po_create.html', {
        'vendors': vendors, 'items': items, 'today': timezone.localdate(),
    })


@login_required
def po_detail(request, po_id):
    po       = get_object_or_404(PurchaseOrder, id=po_id, is_deleted=False)
    po_items = po.items.select_related('item').all()
    return render(request, 'inventory/po_detail.html', {'po': po, 'po_items': po_items})


@login_required
def po_receive(request, po_id):
    """
    Mark PO as received, update stock levels, and create BatchStock records
    for items that require expiry tracking (JCI MMU.3 / FEFO compliance).
    Also scores vendor delivery performance (ISO 9001 §8.4).
    """
    po = get_object_or_404(PurchaseOrder, id=po_id, is_deleted=False)
    if request.method == 'POST':
        on_time = request.POST.get('on_time_delivery') == '1'

        for po_item in po.items.select_related('item').all():
            received_key = f'received_{po_item.id}'
            qty_received = int(request.POST.get(received_key, 0) or 0)
            if qty_received <= 0:
                continue

            # Lot / expiry data from form
            lot_number        = request.POST.get(f'lot_{po_item.id}', '').strip()
            expiry_date_str   = request.POST.get(f'expiry_{po_item.id}', '')
            mfg_date_str      = request.POST.get(f'mfg_{po_item.id}', '')
            expiry_date       = expiry_date_str or None
            manufactured_date = mfg_date_str or None

            # Save lot/expiry on PO item
            po_item.quantity_received  = qty_received
            po_item.lot_number         = lot_number
            po_item.expiry_date        = expiry_date
            po_item.manufactured_date  = manufactured_date
            po_item.save(update_fields=['quantity_received', 'lot_number', 'expiry_date', 'manufactured_date'])

            inv_item = po_item.item
            inv_item.current_stock += qty_received
            inv_item.save(update_fields=['current_stock'])

            # Create BatchStock record if item requires expiry tracking
            batch = None
            if inv_item.requires_expiry_tracking and expiry_date:
                batch = BatchStock.objects.create(
                    item=inv_item,
                    lot_number=lot_number or f'AUTO-{po.po_number}',
                    manufactured_date=manufactured_date,
                    expiry_date=expiry_date,
                    quantity_received=qty_received,
                    quantity_remaining=qty_received,
                    unit_cost=po_item.unit_price,
                    purchase_order=po,
                )

            StockMovement.objects.create(
                item=inv_item,
                movement_type='IN',
                quantity=qty_received,
                balance_after=inv_item.current_stock,
                reference=po.po_number,
                notes=f'PO {po.po_number} received' + (f' | Lot {lot_number}' if lot_number else ''),
                performed_by=request.user,
                batch=batch,
            )

        # Update vendor performance scoring
        vendor = po.vendor
        vendor.total_orders += 1
        if on_time:
            vendor.on_time_deliveries += 1
        else:
            vendor.late_deliveries += 1
        vendor.save(update_fields=['total_orders', 'on_time_deliveries', 'late_deliveries'])

        po.status        = 'RECEIVED'
        po.received_date = timezone.localdate()
        po.approved_by   = request.user
        po.save(update_fields=['status', 'received_date', 'approved_by'])
        messages.success(request, f'PO {po.po_number} received. Stock updated.')
        return redirect('inventory:po_detail', po_id=po.id)

    po_items = po.items.select_related('item').all()
    return render(request, 'inventory/po_receive.html', {'po': po, 'po_items': po_items})


# ── Vendors ───────────────────────────────────────────────────────────────────

@login_required
def vendor_list(request):
    vendors = Vendor.objects.filter(is_deleted=False, is_active=True)
    return render(request, 'inventory/vendor_list.html', {'vendors': vendors})


@login_required
def vendor_create(request):
    if request.method == 'POST':
        vendor = Vendor.objects.create(
            name=request.POST.get('name', '').strip(),
            contact_person=request.POST.get('contact_person', '').strip(),
            phone=request.POST.get('phone', '').strip(),
            email=request.POST.get('email', '').strip(),
            address=request.POST.get('address', '').strip(),
            notes=request.POST.get('notes', '').strip(),
            created_by=request.user,
        )
        messages.success(request, f'Vendor "{vendor.name}" created.')
        return redirect('inventory:vendor_list')
    return render(request, 'inventory/vendor_form.html', {'action': 'Create'})


@login_required
def vendor_edit(request, vendor_id):
    vendor = get_object_or_404(Vendor, id=vendor_id, is_deleted=False)
    if request.method == 'POST':
        vendor.name           = request.POST.get('name', vendor.name).strip()
        vendor.contact_person = request.POST.get('contact_person', '').strip()
        vendor.phone          = request.POST.get('phone', '').strip()
        vendor.email          = request.POST.get('email', '').strip()
        vendor.address        = request.POST.get('address', '').strip()
        vendor.notes          = request.POST.get('notes', '').strip()
        vendor.save()
        messages.success(request, f'Vendor "{vendor.name}" updated.')
        return redirect('inventory:vendor_list')
    return render(request, 'inventory/vendor_form.html', {'vendor': vendor, 'action': 'Edit'})


# ── Item CRUD ─────────────────────────────────────────────────────────────────

@login_required
def item_create(request):
    vendors = Vendor.objects.filter(is_active=True, is_deleted=False).order_by('name')
    if request.method == 'POST':
        pv_id = request.POST.get('preferred_vendor') or None
        preferred_vendor = Vendor.objects.filter(id=pv_id).first() if pv_id else None
        item = InventoryItem.objects.create(
            name=request.POST.get('name', '').strip(),
            item_code=request.POST.get('item_code', '').strip(),
            category=request.POST.get('category', ''),
            unit=request.POST.get('unit', 'unit').strip(),
            unit_cost=request.POST.get('unit_cost') or 0,
            reorder_level=int(request.POST.get('reorder_level', 5) or 5),
            current_stock=int(request.POST.get('current_stock', 0) or 0),
            location=request.POST.get('location', '').strip(),
            description=request.POST.get('description', '').strip(),
            requires_expiry_tracking='requires_expiry_tracking' in request.POST,
            is_consignment='is_consignment' in request.POST,
            udi_code=request.POST.get('udi_code', '').strip(),
            storage_conditions=request.POST.get('storage_conditions', '').strip(),
            preferred_vendor=preferred_vendor,
            created_by=request.user,
        )
        if item.current_stock > 0:
            StockMovement.objects.create(
                item=item, movement_type='IN',
                quantity=item.current_stock, balance_after=item.current_stock,
                notes='Opening stock', performed_by=request.user,
            )
        messages.success(request, f'Item "{item.name}" created.')
        return redirect('inventory:item_detail', item_id=item.id)
    return render(request, 'inventory/item_form.html', {
        'categories': ItemCategory.choices,
        'vendors': vendors,
        'action': 'Create',
    })


@login_required
def item_edit(request, item_id):
    item    = get_object_or_404(InventoryItem, id=item_id, is_deleted=False)
    vendors = Vendor.objects.filter(is_active=True, is_deleted=False).order_by('name')
    if request.method == 'POST':
        pv_id = request.POST.get('preferred_vendor') or None
        item.preferred_vendor = Vendor.objects.filter(id=pv_id).first() if pv_id else None
        item.name               = request.POST.get('name', item.name).strip()
        item.category           = request.POST.get('category', item.category)
        item.unit               = request.POST.get('unit', 'unit').strip()
        item.unit_cost          = request.POST.get('unit_cost') or 0
        item.reorder_level      = int(request.POST.get('reorder_level', 5) or 5)
        item.location           = request.POST.get('location', '').strip()
        item.description        = request.POST.get('description', '').strip()
        item.requires_expiry_tracking = 'requires_expiry_tracking' in request.POST
        item.is_consignment     = 'is_consignment' in request.POST
        item.udi_code           = request.POST.get('udi_code', '').strip()
        item.storage_conditions = request.POST.get('storage_conditions', '').strip()
        item.save()
        messages.success(request, f'Item "{item.name}" updated.')
        return redirect('inventory:item_detail', item_id=item.id)
    return render(request, 'inventory/item_form.html', {
        'item': item, 'categories': ItemCategory.choices,
        'vendors': vendors, 'action': 'Edit',
    })


# ── Batch Stock (lot/expiry management) ───────────────────────────────────────

@login_required
def item_batches(request, item_id):
    """View all batches for a specific item, manage quarantine."""
    item    = get_object_or_404(InventoryItem, id=item_id, is_deleted=False)
    batches = item.batches.order_by('expiry_date')

    if request.method == 'POST':
        action   = request.POST.get('action')
        batch_id = request.POST.get('batch_id')
        batch    = get_object_or_404(BatchStock, id=batch_id, item=item)

        if action == 'quarantine':
            batch.is_quarantined    = True
            batch.quarantine_reason = request.POST.get('reason', '').strip()
            batch.save(update_fields=['is_quarantined', 'quarantine_reason'])
            messages.warning(request, f'Batch {batch.lot_number} quarantined.')

        elif action == 'release':
            batch.is_quarantined    = False
            batch.quarantine_reason = ''
            batch.save(update_fields=['is_quarantined', 'quarantine_reason'])
            messages.success(request, f'Batch {batch.lot_number} released from quarantine.')

        elif action == 'write_off_expired':
            # Write off all expired stock for this item
            today   = timezone.localdate()
            expired = item.batches.filter(expiry_date__lt=today, quantity_remaining__gt=0)
            total_written = 0
            for exp_batch in expired:
                total_written += exp_batch.quantity_remaining
                StockMovement.objects.create(
                    item=item, movement_type='EXPIRE',
                    quantity=-exp_batch.quantity_remaining,
                    balance_after=max(0, item.current_stock - exp_batch.quantity_remaining),
                    reference=exp_batch.lot_number,
                    notes=f'Expired stock write-off | Lot {exp_batch.lot_number} expired {exp_batch.expiry_date}',
                    performed_by=request.user, batch=exp_batch,
                )
                item.current_stock = max(0, item.current_stock - exp_batch.quantity_remaining)
                exp_batch.quantity_remaining = 0
                exp_batch.save(update_fields=['quantity_remaining'])
            item.save(update_fields=['current_stock'])
            messages.warning(request, f'{total_written} units written off as expired.')

        return redirect('inventory:item_batches', item_id=item.id)

    return render(request, 'inventory/batch_list.html', {'item': item, 'batches': batches})


# ── Department Requisitions ───────────────────────────────────────────────────

DEPARTMENTS = [
    'Emergency / A&E', 'OPD', 'Ophthalmology Clinic', 'Ward 1',
    'Ward 2', 'ICU', 'Operating Theatre', 'Labour Room',
    'Pharmacy', 'Laboratory', 'Radiology', 'Outreach / Field',
    'Administration', 'Housekeeping', 'Kitchen', 'Other',
]


@login_required
def requisition_list(request):
    status_filter = request.GET.get('status', '')
    reqs = DepartmentRequisition.objects.filter(is_deleted=False).select_related('requested_by')
    if status_filter:
        reqs = reqs.filter(status=status_filter)
    return render(request, 'inventory/requisition_list.html', {
        'reqs':          reqs,
        'status_filter': status_filter,
        'statuses':      RequisitionStatus.choices,
    })


@login_required
def requisition_create(request):
    items = InventoryItem.objects.filter(is_active=True, is_deleted=False).order_by('name')
    if request.method == 'POST':
        req = DepartmentRequisition.objects.create(
            department=request.POST.get('department', '').strip(),
            requested_by=request.user,
            priority=request.POST.get('priority', 'ROUTINE'),
            needed_by=request.POST.get('needed_by') or None,
            notes=request.POST.get('notes', '').strip(),
            created_by=request.user,
        )
        item_ids    = request.POST.getlist('item_id[]')
        quantities  = request.POST.getlist('quantity[]')
        item_notes  = request.POST.getlist('item_note[]')
        for item_id, qty_str, note in zip(item_ids, quantities, item_notes):
            if not item_id or not qty_str:
                continue
            try:
                qty = int(qty_str)
                inv_item = InventoryItem.objects.get(id=item_id, is_deleted=False)
                RequisitionItem.objects.create(
                    requisition=req, item=inv_item,
                    quantity_requested=qty, notes=note.strip(),
                )
            except (ValueError, InventoryItem.DoesNotExist):
                continue
        messages.success(request, f'Requisition REQ-{req.req_number} submitted.')
        return redirect('inventory:requisition_detail', req_id=req.id)
    return render(request, 'inventory/requisition_form.html', {
        'items':       items,
        'departments': DEPARTMENTS,
        'today':       timezone.localdate(),
    })


@login_required
def requisition_detail(request, req_id):
    req      = get_object_or_404(DepartmentRequisition, id=req_id, is_deleted=False)
    req_items = req.items.select_related('item').all()
    return render(request, 'inventory/requisition_detail.html', {
        'req': req, 'req_items': req_items,
    })


@login_required
def requisition_approve(request, req_id):
    """Store manager approves or rejects a requisition."""
    req = get_object_or_404(DepartmentRequisition, id=req_id, is_deleted=False, status='PENDING')
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            req.status      = 'APPROVED'
            req.approved_by = request.user
            req.save(update_fields=['status', 'approved_by'])
            messages.success(request, f'REQ-{req.req_number} approved.')
        elif action == 'reject':
            req.status          = 'REJECTED'
            req.approved_by     = request.user
            req.rejected_reason = request.POST.get('reason', '').strip()
            req.save(update_fields=['status', 'approved_by', 'rejected_reason'])
            messages.warning(request, f'REQ-{req.req_number} rejected.')
        return redirect('inventory:requisition_detail', req_id=req.id)
    return redirect('inventory:requisition_detail', req_id=req.id)


@login_required
def requisition_issue(request, req_id):
    """
    Issue items from central store using FEFO (First Expired First Out).
    For non-expiry-tracked items, deducts from current_stock directly.
    For expiry-tracked items, consumes oldest-expiring batches first.
    """
    req = get_object_or_404(DepartmentRequisition, id=req_id, is_deleted=False)
    if req.status not in ('APPROVED', 'PARTIAL'):
        messages.error(request, 'Requisition must be approved before issuing.')
        return redirect('inventory:requisition_detail', req_id=req.id)

    if request.method == 'POST':
        any_issued = False
        all_fulfilled = True

        for req_item in req.items.select_related('item').all():
            qty_key    = f'issue_{req_item.id}'
            qty_to_issue = int(request.POST.get(qty_key, 0) or 0)
            if qty_to_issue <= 0:
                all_fulfilled = False
                continue

            qty_to_issue = min(qty_to_issue, req_item.quantity_requested - req_item.quantity_issued)
            inv_item     = req_item.item

            if inv_item.requires_expiry_tracking:
                # FEFO: consume batches in expiry_date ASC order
                remaining_to_issue = qty_to_issue
                for batch in inv_item.available_batches:
                    if remaining_to_issue <= 0:
                        break
                    from_batch = min(batch.quantity_remaining, remaining_to_issue)
                    batch.quantity_remaining -= from_batch
                    batch.save(update_fields=['quantity_remaining'])
                    remaining_to_issue -= from_batch
                    inv_item.current_stock = max(0, inv_item.current_stock - from_batch)
                    inv_item.save(update_fields=['current_stock'])
                    StockMovement.objects.create(
                        item=inv_item, movement_type='ISSUE',
                        quantity=-from_batch,
                        balance_after=inv_item.current_stock,
                        reference=f'REQ-{req.req_number}',
                        notes=f'Issued to {req.department} | Lot {batch.lot_number}',
                        performed_by=request.user, batch=batch,
                    )
                actual_issued = qty_to_issue - remaining_to_issue
            else:
                # Simple deduction
                actual_issued = min(qty_to_issue, inv_item.current_stock)
                inv_item.current_stock = max(0, inv_item.current_stock - actual_issued)
                inv_item.save(update_fields=['current_stock'])
                StockMovement.objects.create(
                    item=inv_item, movement_type='ISSUE',
                    quantity=-actual_issued,
                    balance_after=inv_item.current_stock,
                    reference=f'REQ-{req.req_number}',
                    notes=f'Issued to {req.department}',
                    performed_by=request.user,
                )
                # Trigger auto-reorder if needed
                _trigger_auto_reorder(inv_item, request.user)

            req_item.quantity_issued += actual_issued
            req_item.save(update_fields=['quantity_issued'])
            any_issued = True

            if req_item.quantity_issued < req_item.quantity_requested:
                all_fulfilled = False

        if any_issued:
            req.issued_by = request.user
            req.issued_at = timezone.now()
            req.status    = 'ISSUED' if all_fulfilled else 'PARTIAL'
            req.save(update_fields=['issued_by', 'issued_at', 'status'])
            messages.success(request, f'Items issued for REQ-{req.req_number}.')
        else:
            messages.warning(request, 'No items were issued.')

        return redirect('inventory:requisition_detail', req_id=req.id)

    req_items = req.items.select_related('item').all()
    return render(request, 'inventory/requisition_issue.html', {
        'req': req, 'req_items': req_items,
    })
