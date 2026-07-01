from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum
from django.utils import timezone
from .models import InventoryItem, Vendor, PurchaseOrder, PurchaseOrderItem, StockMovement, ItemCategory


@login_required
def dashboard(request):
    low_stock = [i for i in InventoryItem.objects.filter(is_active=True, is_deleted=False) if i.needs_reorder]
    context = {
        'total_items': InventoryItem.objects.filter(is_active=True, is_deleted=False).count(),
        'low_stock_count': len(low_stock),
        'low_stock_items': low_stock[:10],
        'pending_pos': PurchaseOrder.objects.filter(
            status__in=['SUBMITTED', 'APPROVED'], is_deleted=False
        ).count(),
        'vendors_count': Vendor.objects.filter(is_active=True, is_deleted=False).count(),
    }
    return render(request, 'inventory/dashboard.html', context)


@login_required
def item_list(request):
    q = request.GET.get('q', '')
    category = request.GET.get('category', '')
    items = InventoryItem.objects.filter(is_deleted=False)
    if q:
        items = items.filter(Q(name__icontains=q) | Q(item_code__icontains=q))
    if category:
        items = items.filter(category=category)
    return render(request, 'inventory/item_list.html', {
        'items': items.order_by('name'),
        'search': q, 'category': category,
        'categories': ItemCategory.choices,
    })


@login_required
def item_detail(request, item_id):
    item = get_object_or_404(InventoryItem, id=item_id, is_deleted=False)
    movements = item.movements.order_by('-created_at')[:30]
    return render(request, 'inventory/item_detail.html', {'item': item, 'movements': movements})


@login_required
def stock_adjustment(request, item_id):
    item = get_object_or_404(InventoryItem, id=item_id, is_deleted=False)
    if request.method == 'POST':
        qty = int(request.POST['quantity'])
        move_type = request.POST['movement_type']
        notes = request.POST.get('notes', '')
        if move_type == 'OUT':
            qty = -qty
        item.current_stock = max(0, item.current_stock + qty)
        item.save()
        StockMovement.objects.create(
            item=item,
            movement_type=move_type,
            quantity=qty,
            balance_after=item.current_stock,
            notes=notes,
            performed_by=request.user,
        )
        messages.success(request, 'Stock adjusted successfully.')
        return redirect('inventory:item_detail', item_id=item.id)
    return render(request, 'inventory/stock_adjustment.html', {'item': item})


@login_required
def purchase_order_list(request):
    pos = PurchaseOrder.objects.filter(is_deleted=False).select_related('vendor').order_by('-ordered_date')
    return render(request, 'inventory/po_list.html', {'purchase_orders': pos})


@login_required
def vendor_list(request):
    vendors = Vendor.objects.filter(is_deleted=False, is_active=True)
    return render(request, 'inventory/vendor_list.html', {'vendors': vendors})


# ── Item create / edit ─────────────────────────────────────────────────────────

@login_required
def item_create(request):
    if request.method == 'POST':
        item = InventoryItem.objects.create(
            name=request.POST['name'].strip(),
            item_code=request.POST['item_code'].strip(),
            category=request.POST['category'],
            unit=request.POST.get('unit', 'unit').strip(),
            unit_cost=request.POST.get('unit_cost') or 0,
            reorder_level=int(request.POST.get('reorder_level', 5) or 5),
            current_stock=int(request.POST.get('current_stock', 0) or 0),
            location=request.POST.get('location', '').strip(),
            description=request.POST.get('description', '').strip(),
            created_by=request.user,
        )
        # Record opening stock movement
        if item.current_stock > 0:
            StockMovement.objects.create(
                item=item,
                movement_type='IN',
                quantity=item.current_stock,
                balance_after=item.current_stock,
                notes='Opening stock',
                performed_by=request.user,
            )
        messages.success(request, f'Item "{item.name}" created.')
        return redirect('inventory:item_detail', item_id=item.id)
    return render(request, 'inventory/item_form.html', {
        'categories': ItemCategory.choices,
        'action': 'Create',
    })


@login_required
def item_edit(request, item_id):
    item = get_object_or_404(InventoryItem, id=item_id, is_deleted=False)
    if request.method == 'POST':
        item.name = request.POST['name'].strip()
        item.category = request.POST['category']
        item.unit = request.POST.get('unit', 'unit').strip()
        item.unit_cost = request.POST.get('unit_cost') or 0
        item.reorder_level = int(request.POST.get('reorder_level', 5) or 5)
        item.location = request.POST.get('location', '').strip()
        item.description = request.POST.get('description', '').strip()
        item.save()
        messages.success(request, f'Item "{item.name}" updated.')
        return redirect('inventory:item_detail', item_id=item.id)
    return render(request, 'inventory/item_form.html', {
        'item': item,
        'categories': ItemCategory.choices,
        'action': 'Edit',
    })


# ── Vendor create / edit ───────────────────────────────────────────────────────

@login_required
def vendor_create(request):
    if request.method == 'POST':
        vendor = Vendor.objects.create(
            name=request.POST['name'].strip(),
            contact_person=request.POST.get('contact_person', '').strip(),
            phone=request.POST.get('phone', '').strip(),
            email=request.POST.get('email', '').strip(),
            address=request.POST.get('address', '').strip(),
            created_by=request.user,
        )
        messages.success(request, f'Vendor "{vendor.name}" created.')
        return redirect('inventory:vendor_list')
    return render(request, 'inventory/vendor_form.html', {'action': 'Create'})


@login_required
def vendor_edit(request, vendor_id):
    vendor = get_object_or_404(Vendor, id=vendor_id, is_deleted=False)
    if request.method == 'POST':
        vendor.name = request.POST['name'].strip()
        vendor.contact_person = request.POST.get('contact_person', '').strip()
        vendor.phone = request.POST.get('phone', '').strip()
        vendor.email = request.POST.get('email', '').strip()
        vendor.address = request.POST.get('address', '').strip()
        vendor.save()
        messages.success(request, f'Vendor "{vendor.name}" updated.')
        return redirect('inventory:vendor_list')
    return render(request, 'inventory/vendor_form.html', {'vendor': vendor, 'action': 'Edit'})


# ── Purchase Order create / detail / receive ───────────────────────────────────

@login_required
def po_create(request):
    vendors = Vendor.objects.filter(is_active=True, is_deleted=False).order_by('name')
    items = InventoryItem.objects.filter(is_active=True, is_deleted=False).order_by('name')

    if request.method == 'POST':
        vendor = get_object_or_404(Vendor, id=request.POST['vendor_id'], is_deleted=False)
        expected_date = request.POST.get('expected_date') or None
        notes = request.POST.get('notes', '').strip()

        po = PurchaseOrder.objects.create(
            vendor=vendor,
            expected_date=expected_date,
            notes=notes,
            status='SUBMITTED',
            created_by=request.user,
        )

        item_ids = request.POST.getlist('item_id[]')
        quantities = request.POST.getlist('quantity[]')
        unit_prices = request.POST.getlist('unit_price[]')
        total = 0
        for item_id, qty_str, price_str in zip(item_ids, quantities, unit_prices):
            if not item_id or not qty_str:
                continue
            try:
                qty = int(qty_str)
                price = float(price_str or 0)
                inv_item = InventoryItem.objects.get(id=item_id)
                sub = qty * price
                PurchaseOrderItem.objects.create(
                    purchase_order=po,
                    item=inv_item,
                    quantity_ordered=qty,
                    unit_price=price,
                    subtotal=sub,
                )
                total += sub
            except (ValueError, InventoryItem.DoesNotExist):
                continue

        po.total_amount = total
        po.save(update_fields=['total_amount'])
        messages.success(request, f'Purchase order {po.po_number} created.')
        return redirect('inventory:po_detail', po_id=po.id)

    return render(request, 'inventory/po_create.html', {
        'vendors': vendors,
        'items': items,
        'today': timezone.localdate(),
    })


@login_required
def po_detail(request, po_id):
    po = get_object_or_404(PurchaseOrder, id=po_id, is_deleted=False)
    po_items = po.items.select_related('item').all()
    return render(request, 'inventory/po_detail.html', {'po': po, 'po_items': po_items})


@login_required
def po_receive(request, po_id):
    """Mark PO as received and update stock levels."""
    po = get_object_or_404(PurchaseOrder, id=po_id, is_deleted=False)
    if request.method == 'POST':
        for po_item in po.items.select_related('item').all():
            received_key = f'received_{po_item.id}'
            qty_received = int(request.POST.get(received_key, 0) or 0)
            if qty_received > 0:
                po_item.quantity_received = qty_received
                po_item.save(update_fields=['quantity_received'])

                inv_item = po_item.item
                inv_item.current_stock += qty_received
                inv_item.save(update_fields=['current_stock'])

                StockMovement.objects.create(
                    item=inv_item,
                    movement_type='IN',
                    quantity=qty_received,
                    balance_after=inv_item.current_stock,
                    reference=po.po_number,
                    notes=f'PO {po.po_number} received',
                    performed_by=request.user,
                )

        po.status = 'RECEIVED'
        po.received_date = timezone.localdate()
        po.approved_by = request.user
        po.save(update_fields=['status', 'received_date', 'approved_by'])
        messages.success(request, f'PO {po.po_number} marked as received. Stock updated.')
        return redirect('inventory:po_detail', po_id=po.id)

    po_items = po.items.select_related('item').all()
    return render(request, 'inventory/po_receive.html', {'po': po, 'po_items': po_items})
