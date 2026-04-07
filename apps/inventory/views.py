from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from .models import InventoryItem, Vendor, PurchaseOrder, StockMovement, ItemCategory


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
