from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, F, Count, FloatField, ExpressionWrapper
from django.db.models.functions import Coalesce
from django.utils import timezone
from decimal import Decimal
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from .models import (
    InventoryItem, Vendor, PurchaseOrder, PurchaseOrderItem,
    StockMovement, ItemCategory, BatchStock,
    DepartmentRequisition, RequisitionItem, RequisitionStatus,
    StoreLocation, StockCount, StockCountItem, StockCountStatus,
    DepartmentReturn, DepartmentReturnItem,
    StoreTransfer, StoreTransferItem, StoreTransferStatus,
    GoodsReceivedNote, GRNItem, GRNStatus,
    DisposalRecord, DisposalItem, DisposalStatus,
    StockTakeSchedule, ABCClass, VENClass,
    SupplierQuotation, QuotationItem, QuotationStatus,
    StoreBudget,
    StockValidation, StockValidationType, StockValidationStatus,
    SupplierInvoice, SupplierInvoiceItem, SupplierInvoiceStatus,
    ThreeWayMatch, ThreeWayMatchStatus,
    PurchaseOrderStatus,
)


# ── Access Control ────────────────────────────────────────────────────────────

def _can_access_inventory(user):
    """Read-only access: view items, dashboards, alerts — both store keeper + procurement + leadership."""
    from apps.accounts.models import UserRole
    return user.role in (
        UserRole.STORE_KEEPER, UserRole.PROCUREMENT_OFFICER,
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR,
        UserRole.ADMIN, UserRole.CEO, UserRole.FINANCE_DIRECTOR,
        UserRole.SENIOR_ACCOUNTANT, UserRole.NURSE_DIRECTOR,
    )


def _can_access_store(user):
    """Store operations access: store keeper + leadership + finance (NOT accountant — SoD)."""
    from apps.accounts.models import UserRole
    return user.role in (
        UserRole.STORE_KEEPER, UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR,
        UserRole.ADMIN, UserRole.CEO, UserRole.FINANCE_DIRECTOR,
        UserRole.NURSE_DIRECTOR,
    )


def _can_manage_store(user):
    """Store Keeper write ops: items CRUD, stock entry/exit, GRN receiving, issues, counts, transfers, disposal.
    HEAD_PHARMACIST can manage the pharmacy store (stock in/out, counts).
    Finance Director has read-only access via _can_access_store — not write access."""
    from apps.accounts.models import UserRole
    return user.role in (
        UserRole.STORE_KEEPER, UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR,
        UserRole.ADMIN, UserRole.HEAD_PHARMACIST,
    )


def _can_manage_procurement(user):
    """Procurement Officer write ops: vendors, RFQs, POs, supplier invoices, 3-way match, budget."""
    from apps.accounts.models import UserRole
    return user.role in (
        UserRole.PROCUREMENT_OFFICER, UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR,
        UserRole.ADMIN, UserRole.FINANCE_DIRECTOR,
    )


def _can_requisition(user):
    """Any authenticated staff can raise a requisition."""
    return user.is_authenticated


def _can_view_reports(user):
    """Reports: store keeper + procurement + leadership."""
    from apps.accounts.models import UserRole
    return user.role in (
        UserRole.STORE_KEEPER, UserRole.PROCUREMENT_OFFICER,
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR,
        UserRole.ADMIN, UserRole.CEO, UserRole.FINANCE_DIRECTOR,
        UserRole.SENIOR_ACCOUNTANT,
    )



# ── Document Number Generator — Bon d'Entrée / Bon de Sortie ──────────────────
def _next_doc_number(doc_type, store_code=''):
    """
    Generate next sequential document number.
    Entry: BE-{store_code}-{nnnnnn}  (Bon d'Entrée)
    Exit:  BS-{store_code}-{nnnnnn}  (Bon de Sortie)
    Sequence is per store per doc_type.
    """
    from django.db.models import Max
    prefix = 'BE' if doc_type == 'ENTRY' else 'BS'
    sc = (store_code or 'GEN').upper().replace(' ', '')[:6]
    tag = f'{prefix}-{sc}-'
    last = StockValidation.objects.filter(reference__startswith=tag)                                    .aggregate(m=Max('reference'))['m']
    if last:
        try:
            seq = int(last.split('-')[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f'{tag}{seq:06d}'

# ── 4-Eyes Stock Validation Helper ────────────────────────────────────────────

def _create_stock_validation(validation_type, source_id, reference, description,
                              total_value, user, operation_type_id=None):
    """
    Auto-create a StockValidation record (PENDING) for Finance Director review.
    Every inventory transaction with financial impact goes through this.
    """
    return StockValidation.objects.create(
        validation_type=validation_type,
        source_id=source_id,
        reference=reference,
        description=description,
        total_value=Decimal(str(total_value)),
        submitted_by=user,
        created_by=user,
        operation_type_id=operation_type_id,
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
    if not _can_access_store(request.user) and not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied — Store Keeper or Admin role required.')
    today = timezone.localdate()
    base_qs = InventoryItem.objects.filter(is_active=True, is_deleted=False)
    # Use DB aggregations instead of loading all items into Python
    from django.db.models import DecimalField as _DF, ExpressionWrapper
    totals = base_qs.aggregate(
        total_items=Count('id'),
        low_stock_count=Count('id', filter=Q(current_stock__lte=F('reorder_level'))),
        stock_value=Sum(
            ExpressionWrapper(F('current_stock') * F('unit_cost'), output_field=_DF()),
            filter=Q(is_consignment=False)
        ),
        consignment_value=Sum(
            ExpressionWrapper(F('current_stock') * F('unit_cost'), output_field=_DF()),
            filter=Q(is_consignment=True)
        ),
    )
    low_stock = list(base_qs.filter(current_stock__lte=F('reorder_level')).select_related('store_location')[:15])
    stock_value = int(totals['stock_value'] or 0)
    consignment_value = int(totals['consignment_value'] or 0)

    # YTD PO spend
    po_spend_ytd = PurchaseOrder.objects.filter(
        status='RECEIVED', is_deleted=False, ordered_date__year=today.year
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

    # Expiry alerts
    expiring_soon = BatchStock.objects.filter(
        is_quarantined=False,
        quantity_remaining__gt=0,
        expiry_date__lte=today + timezone.timedelta(days=90),
        expiry_date__gte=today,
    ).select_related('item').order_by('expiry_date')

    expired_count = BatchStock.objects.filter(
        quantity_remaining__gt=0,
        expiry_date__lt=today,
    ).count()

    quarantined_count = BatchStock.objects.filter(is_quarantined=True, quantity_remaining__gt=0).count()

    pending_reqs = DepartmentRequisition.objects.filter(
        status='PENDING', is_deleted=False
    ).count()

    # Recent requisitions (last 8)
    recent_reqs = DepartmentRequisition.objects.filter(
        is_deleted=False
    ).order_by('-created_at')[:8]

    # Recent received POs (last 5)
    recent_pos = PurchaseOrder.objects.filter(
        is_deleted=False, status='RECEIVED'
    ).select_related('vendor').order_by('-received_date')[:5]

    # Vendor performance scoreboard
    vendors = Vendor.objects.filter(is_active=True, is_deleted=False, total_orders__gt=0).order_by('-on_time_deliveries')

    # Auto-generated pending POs
    auto_pos = PurchaseOrder.objects.filter(
        is_deleted=False, status='DRAFT', is_auto_generated=True
    ).count()

    context = {
        'total_items':        totals['total_items'],
        'low_stock_count':    totals['low_stock_count'],
        'low_stock_items':    low_stock,
        'pending_pos':        PurchaseOrder.objects.filter(status__in=['SUBMITTED', 'APPROVED'], is_deleted=False).count(),
        'auto_pos':           auto_pos,
        'vendors_count':      Vendor.objects.filter(is_active=True, is_deleted=False).count(),
        'expiring_soon':      expiring_soon[:15],
        'expiring_count':     expiring_soon.count(),
        'expired_count':      expired_count,
        'quarantined_count':  quarantined_count,
        'pending_reqs':       pending_reqs,
        'stock_value':        int(stock_value),
        'consignment_value':  int(consignment_value),
        'po_spend_ytd':       int(po_spend_ytd),
        'recent_reqs':        recent_reqs,
        'recent_pos':         recent_pos,
        'vendors':            vendors,
    }
    return render(request, 'inventory/dashboard.html', context)


# ── Procurement Dashboard ─────────────────────────────────────────────────────

@login_required
def procurement_dashboard(request):
    """Dedicated dashboard for Procurement Officer — focuses on sourcing, POs, invoices, matching."""
    if not _can_manage_procurement(request.user):
        return HttpResponseForbidden('Access denied — Procurement Officer role required.')

    today = timezone.localdate()

    # PO statistics
    po_qs = PurchaseOrder.objects.filter(is_deleted=False)
    draft_pos = po_qs.filter(status='DRAFT').count()
    submitted_pos = po_qs.filter(status='SUBMITTED').count()
    approved_pos = po_qs.filter(status='APPROVED').count()
    received_pos = po_qs.filter(status='RECEIVED', received_date__year=today.year).count()

    # YTD PO spend
    po_spend_ytd = po_qs.filter(
        status='RECEIVED', ordered_date__year=today.year
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

    # Pending finance approval
    pending_finance = po_qs.filter(status='SUBMITTED').count()

    # Supplier Invoices
    inv_qs = SupplierInvoice.objects.filter(is_deleted=False)
    pending_invoices = inv_qs.filter(status='PENDING').count()
    total_invoices = inv_qs.count()

    # 3-Way Match
    match_qs = ThreeWayMatch.objects.filter(is_deleted=False)
    pending_matches = match_qs.filter(status='PENDING').count()
    mismatched = match_qs.filter(status='MISMATCH').count()
    matched_count = match_qs.filter(status='MATCHED').count()

    # Open quotations
    open_rfqs = SupplierQuotation.objects.filter(
        is_deleted=False, status__in=['DRAFT', 'SENT']
    ).count()

    # Vendor stats
    active_vendors = Vendor.objects.filter(is_active=True, is_deleted=False).count()

    # Items needing reorder — DB filter instead of loading all items
    low_qs = InventoryItem.objects.filter(
        is_active=True, is_deleted=False, current_stock__lte=F('reorder_level')
    ).select_related('store_location')
    low_stock_items = list(low_qs[:10])

    # Auto-generated POs awaiting review
    auto_pos = po_qs.filter(status='DRAFT', is_auto_generated=True).count()

    # Recent POs (last 10)
    recent_pos = po_qs.select_related('vendor').order_by('-created_at')[:10]

    # Recent supplier invoices (last 10)
    recent_invoices = inv_qs.select_related('vendor').order_by('-created_at')[:10]

    # Unmatched invoices (no 3-way match yet)
    matched_invoice_ids = ThreeWayMatch.objects.filter(is_deleted=False).values_list('supplier_invoice_id', flat=True)
    unmatched_invoices = inv_qs.exclude(id__in=matched_invoice_ids).count()

    context = {
        'draft_pos': draft_pos,
        'submitted_pos': submitted_pos,
        'approved_pos': approved_pos,
        'received_pos': received_pos,
        'po_spend_ytd': int(po_spend_ytd),
        'pending_finance': pending_finance,
        'pending_invoices': pending_invoices,
        'total_invoices': total_invoices,
        'unmatched_invoices': unmatched_invoices,
        'pending_matches': pending_matches,
        'mismatched': mismatched,
        'matched_count': matched_count,
        'open_rfqs': open_rfqs,
        'active_vendors': active_vendors,
        'low_stock_count': low_qs.count(),
        'low_stock_items': low_stock_items,
        'auto_pos': auto_pos,
        'recent_pos': recent_pos,
        'recent_invoices': recent_invoices,
    }
    return render(request, 'inventory/procurement_dashboard.html', context)


# ── Item list / detail ────────────────────────────────────────────────────────

@login_required
def item_list(request):
    if not _can_access_inventory(request.user):
        return HttpResponseForbidden('Access denied.')
    from django.core.paginator import Paginator
    q        = request.GET.get('q', '')
    category = request.GET.get('category', '')
    store    = request.GET.get('store', '')
    low      = request.GET.get('low', '')
    items    = InventoryItem.objects.filter(is_deleted=False, is_active=True).select_related('preferred_vendor', 'store_location')
    if q:
        items = items.filter(Q(name__icontains=q) | Q(item_code__icontains=q))
    if category:
        items = items.filter(category=category)
    if store:
        items = items.filter(store_location_id=store)
    if low:
        items = items.filter(current_stock__lte=F('reorder_level'))
    paginator = Paginator(items.order_by('name'), 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    store_locations = StoreLocation.objects.filter(is_deleted=False, is_active=True).order_by('store_code')
    return render(request, 'inventory/item_list.html', {
        'items':           page_obj,
        'page_obj':        page_obj,
        'search':          q,
        'category':        category,
        'store':           store,
        'low':             low,
        'categories':      ItemCategory.choices,
        'store_locations': store_locations,
    })


@login_required
def item_detail(request, item_id):
    if not _can_access_inventory(request.user):
        return HttpResponseForbidden('Access denied.')
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
    if not _can_manage_store(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Access denied.')
    item = get_object_or_404(InventoryItem, id=item_id, is_deleted=False)
    if request.method == 'POST':
        qty       = int(request.POST.get('quantity', 0) or 0)
        move_type = request.POST.get('movement_type', 'IN')
        notes     = request.POST.get('notes', '')
        if move_type == 'OUT':
            qty = -qty
        item.current_stock = max(0, item.current_stock + qty)
        item.save()
        sm = StockMovement.objects.create(
            item=item, movement_type=move_type,
            quantity=qty, balance_after=item.current_stock,
            notes=notes, performed_by=request.user,
        )
        if move_type == 'OUT':
            _trigger_auto_reorder(item, request.user)
        # 4-Eyes: Create validation for adjustment GL posting
        total_value = abs(qty) * float(item.unit_cost or 0)
        if total_value > 0:
            _create_stock_validation(
                validation_type=StockValidationType.ADJUSTMENT,
                source_id=sm.pk, reference=f'ADJ-{item.item_code}',
                description=f'Stock adjustment — {item.name} ({move_type} {abs(qty)})',
                total_value=total_value, user=request.user,
            )
        messages.success(request, 'Stock adjusted successfully.')
        return redirect('inventory:item_detail', item_id=item.id)
    return render(request, 'inventory/stock_adjustment.html', {'item': item})


# ── Purchase Orders ───────────────────────────────────────────────────────────

@login_required
def purchase_order_list(request):
    if not _can_manage_procurement(request.user) and not _can_access_store(request.user):
        return HttpResponseForbidden('Access denied.')
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '')
    pos = PurchaseOrder.objects.filter(is_deleted=False).select_related('vendor').order_by('-ordered_date')
    if status_filter:
        pos = pos.filter(status=status_filter)
    if search:
        pos = pos.filter(Q(po_number__icontains=search) | Q(vendor__name__icontains=search))
    return render(request, 'inventory/po_list.html', {
        'purchase_orders': pos,
        'status_filter': status_filter,
        'search': search,
        'statuses': PurchaseOrderStatus.choices,
    })


@login_required
def po_create(request):
    if not _can_manage_procurement(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Access denied.')
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
    if not _can_manage_procurement(request.user) and not _can_access_store(request.user):
        return HttpResponseForbidden('Access denied.')
    po       = get_object_or_404(PurchaseOrder, id=po_id, is_deleted=False)
    po_items = po.items.select_related('item').all()
    return render(request, 'inventory/po_detail.html', {'po': po, 'po_items': po_items})


@login_required
def po_edit(request, po_id):
    """Edit PO — only SUBMITTED status (before finance approval)."""
    if not _can_manage_procurement(request.user):
        return HttpResponseForbidden('Access denied.')
    po = get_object_or_404(PurchaseOrder, id=po_id, is_deleted=False)
    if po.status not in ('DRAFT', 'SUBMITTED'):
        messages.error(request, f'Cannot edit PO {po.po_number} — status is {po.get_status_display()}.')
        return redirect('inventory:po_detail', po_id=po.pk)

    vendors = Vendor.objects.filter(is_active=True, is_deleted=False).order_by('name')
    items = InventoryItem.objects.filter(is_active=True, is_deleted=False).order_by('name')

    if request.method == 'POST':
        vendor_id = request.POST.get('vendor_id')
        if vendor_id:
            po.vendor = get_object_or_404(Vendor, id=vendor_id, is_deleted=False)
        po.expected_date = request.POST.get('expected_date') or None
        po.notes = request.POST.get('notes', '').strip()
        po.save(update_fields=['vendor', 'expected_date', 'notes'])

        # Replace line items
        po.items.all().delete()
        item_ids = request.POST.getlist('item_id[]')
        quantities = request.POST.getlist('quantity[]')
        unit_prices = request.POST.getlist('unit_price[]')
        total = Decimal('0')
        for item_id, qty_str, price_str in zip(item_ids, quantities, unit_prices):
            if not item_id or not qty_str:
                continue
            try:
                qty = int(qty_str)
                price = Decimal(price_str or '0')
                PurchaseOrderItem.objects.create(
                    purchase_order=po, item_id=item_id,
                    quantity_ordered=qty, unit_price=price, subtotal=qty * price,
                )
                total += qty * price
            except (ValueError, InventoryItem.DoesNotExist):
                continue
        po.total_amount = total
        po.save(update_fields=['total_amount'])
        messages.success(request, f'PO {po.po_number} updated.')
        return redirect('inventory:po_detail', po_id=po.pk)

    return render(request, 'inventory/po_create.html', {
        'vendors': vendors, 'items': items, 'today': timezone.localdate(),
        'po': po, 'po_items': po.items.select_related('item').all(),
        'action': 'Edit',
    })


@login_required
def po_delete(request, po_id):
    """Soft-delete PO — only before receiving."""
    if not _can_manage_procurement(request.user):
        return HttpResponseForbidden('Access denied.')
    po = get_object_or_404(PurchaseOrder, id=po_id, is_deleted=False)
    if request.method == 'POST':
        if po.status == 'RECEIVED':
            messages.error(request, f'Cannot delete PO {po.po_number} — already received.')
            return redirect('inventory:po_detail', po_id=po.pk)
        reason = request.POST.get('deletion_reason', '').strip()
        if not reason:
            messages.error(request, 'A deletion reason is required.')
            return redirect('inventory:po_detail', po_id=po.pk)
        po.soft_delete(user=request.user, reason=reason)
        messages.success(request, f'PO {po.po_number} moved to recycle bin.')
        return redirect('inventory:po_list')
    return redirect('inventory:po_list')


@login_required
def po_receive(request, po_id):
    if not _can_manage_store(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Access denied.')
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
    if not _can_manage_procurement(request.user):
        return HttpResponseForbidden('Access denied.')
    search = request.GET.get('q', '').strip()
    status_filter = request.GET.get('active', '')
    vendors = Vendor.objects.filter(is_deleted=False)
    if status_filter == '1':
        vendors = vendors.filter(is_active=True)
    elif status_filter == '0':
        vendors = vendors.filter(is_active=False)
    if search:
        vendors = vendors.filter(
            Q(name__icontains=search) |
            Q(contact_person__icontains=search) |
            Q(email__icontains=search)
        )
    return render(request, 'inventory/vendor_list.html', {
        'vendors': vendors,
        'search': search,
        'active_filter': status_filter,
    })


@login_required
def vendor_create(request):
    if not _can_manage_procurement(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Access denied.')
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
    if not _can_manage_procurement(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Access denied.')
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


@login_required
def vendor_delete(request, vendor_id):
    if not _can_manage_procurement(request.user):
        return HttpResponseForbidden('Access denied.')
    vendor = get_object_or_404(Vendor, id=vendor_id, is_deleted=False)
    if request.method == 'POST':
        # Check for linked POs or quotations before soft-deleting
        active_pos = PurchaseOrder.objects.filter(vendor=vendor, is_deleted=False).exclude(status='CANCELLED').count()
        if active_pos:
            messages.error(request, f'Cannot delete "{vendor.name}" — {active_pos} active purchase order(s) linked.')
            return redirect('inventory:vendor_list')
        reason = request.POST.get('deletion_reason', '').strip()
        if not reason:
            messages.error(request, 'A deletion reason is required.')
            return redirect('inventory:vendor_list')
        vendor.soft_delete(user=request.user, reason=reason)
        messages.success(request, f'Vendor "{vendor.name}" deleted.')
        return redirect('inventory:vendor_list')
    return redirect('inventory:vendor_list')


# ── Item CRUD ─────────────────────────────────────────────────────────────────

@login_required
def item_create(request):
    if not _can_manage_store(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Access denied.')
    from apps.billing.models import ServicePrice, ServiceSubCategory, GLAccount
    from decimal import Decimal, InvalidOperation
    vendors = Vendor.objects.filter(is_active=True, is_deleted=False).order_by('name')
    store_locations = StoreLocation.objects.filter(is_active=True, is_deleted=False).order_by('name')
    gl_accounts = GLAccount.objects.filter(is_deleted=False, code__startswith='7').order_by('code')
    gl_expense_accounts = GLAccount.objects.filter(is_deleted=False, code__startswith='6').order_by('code')
    gl_asset_accounts = GLAccount.objects.filter(is_deleted=False, code__startswith='3').order_by('code')
    sub_categories = ServiceSubCategory.objects.filter(is_deleted=False).order_by('name')

    if request.method == 'POST':
        pv_id = request.POST.get('preferred_vendor') or None
        preferred_vendor = Vendor.objects.filter(id=pv_id).first() if pv_id else None
        sl_id = request.POST.get('store_location') or None
        store_loc = StoreLocation.objects.filter(id=sl_id).first() if sl_id else None
        item = InventoryItem.objects.create(
            name=request.POST.get('name', '').strip(),
            item_code=request.POST.get('item_code', '').strip(),
            category=request.POST.get('category', ''),
            unit=request.POST.get('unit', 'unit').strip(),
            unit_cost=request.POST.get('unit_cost') or 0,
            reorder_level=int(request.POST.get('reorder_level', 5) or 5),
            current_stock=int(request.POST.get('current_stock', 0) or 0),
            location=request.POST.get('location', '').strip(),
            store_location=store_loc,
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
        # Auto-create ServicePrice entry in billing catalog
        price_str = request.POST.get('price', '0').strip()
        try:
            price_val = Decimal(price_str) if price_str else Decimal('0')
        except (InvalidOperation, ValueError):
            price_val = Decimal('0')
        ht_str = request.POST.get('price_ht', '0').strip()
        tax_str = request.POST.get('tax_rate', '0').strip()
        nhis_str = request.POST.get('nhis_price', '').strip()
        ins_str = request.POST.get('insurance_price', '').strip()
        sub_cat_id = request.POST.get('sub_category', '').strip()
        gl_id = request.POST.get('gl_account', '').strip()
        pgl_id = request.POST.get('purchase_gl_account', '').strip()
        sgl_id = request.POST.get('stock_gl_account', '').strip()
        vgl_id = request.POST.get('stock_variation_gl_account', '').strip()
        ServicePrice.objects.create(
            entry_type='ITEM',
            name=item.name,
            code=item.item_code,
            category=item.category,
            sub_category_id=sub_cat_id or None,
            tier=request.POST.get('tier', '').strip(),
            gl_account_id=gl_id or None,
            purchase_gl_account_id=pgl_id or None,
            stock_gl_account_id=sgl_id or None,
            stock_variation_gl_account_id=vgl_id or None,
            price_ht=Decimal(ht_str) if ht_str else Decimal('0'),
            tax_rate=Decimal(tax_str) if tax_str else Decimal('0'),
            price=price_val,
            nhis_price=Decimal(nhis_str) if nhis_str else None,
            insurance_price=Decimal(ins_str) if ins_str else None,
            is_stockable=True,
            is_taxable='is_taxable' in request.POST,
            requires_price_entry='requires_price_entry' in request.POST,
        )
        messages.success(request, f'Item "{item.name}" created + added to billing catalog.')
        return redirect('inventory:item_detail', item_id=item.id)
    return render(request, 'inventory/item_form.html', {
        'categories': ItemCategory.choices,
        'vendors': vendors,
        'store_locations': store_locations,
        'gl_accounts': gl_accounts,
        'gl_expense_accounts': gl_expense_accounts,
        'gl_asset_accounts': gl_asset_accounts,
        'sub_categories': sub_categories,
        'action': 'Create',
    })


@login_required
def item_edit(request, item_id):
    if not _can_manage_store(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Access denied.')
    from apps.billing.models import ServicePrice, ServiceSubCategory, GLAccount
    from decimal import Decimal, InvalidOperation
    item    = get_object_or_404(InventoryItem, id=item_id, is_deleted=False)
    vendors = Vendor.objects.filter(is_active=True, is_deleted=False).order_by('name')
    store_locations = StoreLocation.objects.filter(is_active=True, is_deleted=False).order_by('name')
    gl_accounts = GLAccount.objects.filter(is_deleted=False, code__startswith='7').order_by('code')
    gl_expense_accounts = GLAccount.objects.filter(is_deleted=False, code__startswith='6').order_by('code')
    gl_asset_accounts = GLAccount.objects.filter(is_deleted=False, code__startswith='3').order_by('code')
    sub_categories = ServiceSubCategory.objects.filter(is_deleted=False).order_by('name')
    # Find linked ServicePrice
    sp = ServicePrice.objects.filter(code=item.item_code, entry_type='ITEM', is_deleted=False).first()

    if request.method == 'POST':
        pv_id = request.POST.get('preferred_vendor') or None
        item.preferred_vendor = Vendor.objects.filter(id=pv_id).first() if pv_id else None
        sl_id = request.POST.get('store_location') or None
        item.store_location = StoreLocation.objects.filter(id=sl_id).first() if sl_id else None
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
        # Update or create linked ServicePrice
        price_str = request.POST.get('price', '0').strip()
        try:
            price_val = Decimal(price_str) if price_str else Decimal('0')
        except (InvalidOperation, ValueError):
            price_val = Decimal('0')
        ht_str = request.POST.get('price_ht', '0').strip()
        tax_str = request.POST.get('tax_rate', '0').strip()
        nhis_str = request.POST.get('nhis_price', '').strip()
        ins_str = request.POST.get('insurance_price', '').strip()
        sub_cat_id = request.POST.get('sub_category', '').strip()
        gl_id = request.POST.get('gl_account', '').strip()
        pgl_id = request.POST.get('purchase_gl_account', '').strip()
        sgl_id = request.POST.get('stock_gl_account', '').strip()
        vgl_id = request.POST.get('stock_variation_gl_account', '').strip()
        sp_data = dict(
            entry_type='ITEM', name=item.name, category=item.category,
            sub_category_id=sub_cat_id or None,
            tier=request.POST.get('tier', '').strip(),
            gl_account_id=gl_id or None,
            purchase_gl_account_id=pgl_id or None,
            stock_gl_account_id=sgl_id or None,
            stock_variation_gl_account_id=vgl_id or None,
            price_ht=Decimal(ht_str) if ht_str else Decimal('0'),
            tax_rate=Decimal(tax_str) if tax_str else Decimal('0'),
            price=price_val,
            nhis_price=Decimal(nhis_str) if nhis_str else None,
            insurance_price=Decimal(ins_str) if ins_str else None,
            is_stockable=True,
            is_taxable='is_taxable' in request.POST,
            requires_price_entry='requires_price_entry' in request.POST,
        )
        if sp:
            for k, v in sp_data.items():
                setattr(sp, k, v)
            sp.save()
        else:
            sp_data['code'] = item.item_code
            ServicePrice.objects.create(**sp_data)
        messages.success(request, f'Item "{item.name}" updated.')
        return redirect('inventory:item_detail', item_id=item.id)

    # Pre-fill ServicePrice fields for the template
    ctx = {
        'item': item, 'categories': ItemCategory.choices,
        'vendors': vendors, 'store_locations': store_locations,
        'gl_accounts': gl_accounts, 'gl_expense_accounts': gl_expense_accounts,
        'gl_asset_accounts': gl_asset_accounts, 'sub_categories': sub_categories,
        'action': 'Edit',
    }
    if sp:
        ctx.update({
            'sp_sub_category': sp.sub_category_id,
            'sp_tier': sp.tier,
            'sp_price_ht': sp.price_ht, 'sp_tax_rate': sp.tax_rate,
            'sp_price': sp.price, 'sp_nhis': sp.nhis_price, 'sp_insurance': sp.insurance_price,
            'sp_gl': sp.gl_account_id, 'sp_purchase_gl': sp.purchase_gl_account_id,
            'sp_stock_gl': sp.stock_gl_account_id, 'sp_var_gl': sp.stock_variation_gl_account_id,
            'sp_taxable': sp.is_taxable, 'sp_manual': sp.requires_price_entry,
        })
    return render(request, 'inventory/item_form.html', ctx)


# ── Batch Stock (lot/expiry management) ───────────────────────────────────────

@login_required
def item_batches(request, item_id):
    """View all batches for a specific item, manage quarantine."""
    if not _can_access_inventory(request.user):
        return HttpResponseForbidden('Access denied.')
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
    if not _can_access_inventory(request.user) and not _can_requisition(request.user):
        return HttpResponseForbidden('Access denied.')
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '').strip()
    reqs = DepartmentRequisition.objects.filter(is_deleted=False).select_related('requested_by')
    if status_filter:
        reqs = reqs.filter(status=status_filter)
    if search:
        reqs = reqs.filter(
            Q(req_number__icontains=search) |
            Q(department__icontains=search)
        )
    return render(request, 'inventory/requisition_list.html', {
        'reqs':          reqs,
        'status_filter': status_filter,
        'search':        search,
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
    if not _can_access_inventory(request.user) and not _can_requisition(request.user):
        return HttpResponseForbidden('Access denied.')
    req      = get_object_or_404(DepartmentRequisition, id=req_id, is_deleted=False)
    req_items = req.items.select_related('item').all()
    return render(request, 'inventory/requisition_detail.html', {
        'req': req, 'req_items': req_items,
    })


@login_required
def requisition_approve(request, req_id):
    """Store manager approves or rejects a requisition."""
    if not _can_manage_store(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Access denied.')
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
    if not _can_manage_store(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Access denied.')
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
            # 4-Eyes: Create validation for stock issue
            total_value = sum(
                (ri.quantity_issued or 0) * float(ri.item.unit_cost or 0)
                for ri in req.items.select_related('item').all()
            )
            if total_value > 0:
                _create_stock_validation(
                    validation_type=StockValidationType.ISSUE,
                    source_id=req.pk, reference=req.req_number,
                    description=f'Stock issued — REQ {req.req_number} — {req.department}',
                    total_value=total_value, user=request.user,
                )
            messages.success(request, f'Items issued for REQ-{req.req_number}.')
        else:
            messages.warning(request, 'No items were issued.')

        return redirect('inventory:requisition_detail', req_id=req.id)

    req_items = req.items.select_related('item').all()
    return render(request, 'inventory/requisition_issue.html', {
        'req': req, 'req_items': req_items,
    })


# ══════════════════════════════════════════════════════════════════════════════
# STORE LOCATIONS
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def store_location_list(request):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    locations = StoreLocation.objects.filter(is_deleted=False).select_related('cost_center').order_by('store_code')
    return render(request, 'inventory/store_location_list.html', {'locations': locations})


@login_required
def store_location_create(request):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    from apps.billing.models import CostCenter
    cost_centers = CostCenter.objects.filter(is_active=True, is_deleted=False).order_by('code')
    if request.method == 'POST':
        cc_id = request.POST.get('cost_center') or None
        cc = CostCenter.objects.filter(pk=cc_id).first() if cc_id else None
        StoreLocation.objects.create(
            store_code=request.POST.get('store_code', '').strip() or '',
            name=request.POST.get('name', '').strip(),
            location_type=request.POST.get('location_type', 'CENTRAL'),
            address=request.POST.get('address', '').strip(),
            cost_center=cc,
            created_by=request.user,
        )
        messages.success(request, 'Store location created.')
        return redirect('inventory:store_location_list')
    return render(request, 'inventory/store_location_form.html', {'action': 'Create', 'cost_centers': cost_centers})


@login_required
def store_location_edit(request, loc_id):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    from apps.billing.models import CostCenter
    cost_centers = CostCenter.objects.filter(is_active=True, is_deleted=False).order_by('code')
    loc = get_object_or_404(StoreLocation, pk=loc_id, is_deleted=False)
    if request.method == 'POST':
        code = request.POST.get('store_code', '').strip()
        if code:
            loc.store_code = code
        loc.name = request.POST.get('name', loc.name).strip()
        loc.location_type = request.POST.get('location_type', loc.location_type)
        loc.address = request.POST.get('address', '').strip()
        loc.is_active = 'is_active' in request.POST
        cc_id = request.POST.get('cost_center') or None
        loc.cost_center = CostCenter.objects.filter(pk=cc_id).first() if cc_id else None
        loc.save()
        messages.success(request, f'Location "{loc.name}" updated.')
        return redirect('inventory:store_location_list')
    return render(request, 'inventory/store_location_form.html', {
        'location': loc, 'action': 'Edit', 'cost_centers': cost_centers,
    })


@login_required
@require_POST
def store_location_delete(request, loc_id):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    loc = get_object_or_404(StoreLocation, pk=loc_id, is_deleted=False)
    # Check if store has items assigned
    item_count = loc.items.filter(is_deleted=False).count() if hasattr(loc, 'items') else 0
    if item_count > 0:
        messages.error(request, f'Cannot delete "{loc.name}" — {item_count} items are assigned to this store.')
        return redirect('inventory:store_location_list')
    loc.is_deleted = True
    loc.save()
    messages.success(request, f'Store "{loc.name}" deleted.')
    return redirect('inventory:store_location_list')


# ══════════════════════════════════════════════════════════════════════════════
# PHYSICAL STOCK COUNT
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def stock_count_list(request):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    status_filter = request.GET.get('status', '')
    counts = StockCount.objects.filter(is_deleted=False).select_related('counted_by', 'approved_by')
    if status_filter:
        counts = counts.filter(status=status_filter)
    return render(request, 'inventory/stock_count_list.html', {
        'counts': counts, 'status_filter': status_filter,
        'statuses': StockCountStatus.choices,
    })


@login_required
def stock_count_create(request):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    if request.method == 'POST':
        store_id = request.POST.get('store_location', '').strip()
        store = None
        if store_id:
            store = get_object_or_404(StoreLocation, pk=store_id, is_deleted=False)
        sc = StockCount.objects.create(
            counted_by=request.user,
            notes=request.POST.get('notes', '').strip(),
            created_by=request.user,
        )
        # Populate items — filter by store if selected (avoid loading all 2800+ items at once)
        qs = InventoryItem.objects.filter(is_active=True, is_deleted=False)
        if store:
            qs = qs.filter(store_location=store)
        qs = qs.order_by('name')
        bulk = [StockCountItem(
            stock_count=sc, item=item,
            system_quantity=item.current_stock,
            physical_quantity=item.current_stock,
        ) for item in qs]
        StockCountItem.objects.bulk_create(bulk)
        label = f' ({store.store_code})' if store else ''
        messages.success(request, f'Stock count {sc.count_number}{label} started — {len(bulk)} items.')
        return redirect('inventory:stock_count_detail', count_id=sc.pk)
    store_locations = StoreLocation.objects.filter(is_deleted=False, is_active=True).order_by('store_code')
    return render(request, 'inventory/stock_count_form.html', {'store_locations': store_locations})


@login_required
def stock_count_detail(request, count_id):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    sc = get_object_or_404(StockCount.objects.select_related('counted_by', 'approved_by'), pk=count_id, is_deleted=False)
    items = sc.items.select_related('item').order_by('item__name')
    variance_count = items.exclude(variance=0).count()
    return render(request, 'inventory/stock_count_detail.html', {
        'sc': sc, 'items': items, 'variance_count': variance_count,
    })


@login_required
@require_POST
def stock_count_update(request, count_id):
    """Update physical quantities for a stock count."""
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    sc = get_object_or_404(StockCount, pk=count_id, is_deleted=False, status=StockCountStatus.IN_PROGRESS)
    for sci in sc.items.all():
        key = f'qty_{sci.pk}'
        if key in request.POST:
            sci.physical_quantity = int(request.POST[key] or 0)
            sci.save()
    messages.success(request, 'Physical quantities updated.')
    return redirect('inventory:stock_count_detail', count_id=sc.pk)


@login_required
@require_POST
def stock_count_complete(request, count_id):
    """Mark count as completed (ready for approval)."""
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    sc = get_object_or_404(StockCount, pk=count_id, is_deleted=False, status=StockCountStatus.IN_PROGRESS)
    sc.status = StockCountStatus.COMPLETED
    sc.save(update_fields=['status'])
    messages.success(request, f'Count {sc.count_number} marked as completed.')
    return redirect('inventory:stock_count_detail', count_id=sc.pk)


@login_required
@require_POST
def stock_count_approve(request, count_id):
    """Approve count and apply variance adjustments to stock."""
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    sc = get_object_or_404(StockCount, pk=count_id, is_deleted=False, status=StockCountStatus.COMPLETED)
    for sci in sc.items.select_related('item').filter().exclude(variance=0):
        item = sci.item
        item.current_stock = sci.physical_quantity
        item.save(update_fields=['current_stock'])
        StockMovement.objects.create(
            item=item, movement_type='ADJUST',
            quantity=sci.variance, balance_after=sci.physical_quantity,
            reference=f'SC-{sc.count_number}',
            notes=f'Physical count adjustment: system={sci.system_quantity} physical={sci.physical_quantity}',
            performed_by=request.user,
        )
    sc.status = StockCountStatus.APPROVED
    sc.approved_by = request.user
    sc.save(update_fields=['status', 'approved_by'])
    # 4-Eyes: Create validation for variance GL posting
    total_value = sum(
        abs(sci.variance or 0) * float(sci.item.unit_cost or 0)
        for sci in sc.items.select_related('item').exclude(variance=0)
    )
    if total_value > 0:
        _create_stock_validation(
            validation_type=StockValidationType.COUNT,
            source_id=sc.pk, reference=sc.count_number,
            description=f'Stock count variance — {sc.count_number}',
            total_value=total_value, user=request.user,
        )
    messages.success(request, f'Count {sc.count_number} approved — stock adjusted, awaiting GL validation.')
    return redirect('inventory:stock_count_detail', count_id=sc.pk)


# ══════════════════════════════════════════════════════════════════════════════
# DEPARTMENT RETURNS
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def return_list(request):
    if not _can_access_store(request.user):
        return HttpResponseForbidden('Access denied.')
    search = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')
    returns = DepartmentReturn.objects.filter(is_deleted=False).select_related('returned_by', 'received_by')
    if status_filter:
        returns = returns.filter(status=status_filter)
    if search:
        returns = returns.filter(
            Q(return_number__icontains=search) |
            Q(department__icontains=search)
        )
    status_choices = [('PENDING', 'Pending'), ('ACCEPTED', 'Accepted'), ('REJECTED', 'Rejected')]
    return render(request, 'inventory/return_list.html', {
        'returns': returns, 'search': search, 'status_filter': status_filter,
        'statuses': status_choices,
    })


@login_required
def return_create(request):
    items = InventoryItem.objects.filter(is_active=True, is_deleted=False).order_by('name')
    if request.method == 'POST':
        ret = DepartmentReturn.objects.create(
            department=request.POST.get('department', '').strip(),
            returned_by=request.user,
            notes=request.POST.get('notes', '').strip(),
            created_by=request.user,
        )
        item_ids = request.POST.getlist('item_id[]')
        qtys = request.POST.getlist('quantity[]')
        conditions = request.POST.getlist('condition[]')
        for item_id, qty_str, cond in zip(item_ids, qtys, conditions):
            if not item_id or not qty_str:
                continue
            try:
                DepartmentReturnItem.objects.create(
                    department_return=ret,
                    item=InventoryItem.objects.get(id=item_id),
                    quantity=int(qty_str),
                    condition=cond or 'GOOD',
                )
            except (ValueError, InventoryItem.DoesNotExist):
                continue
        messages.success(request, f'Return RET-{ret.return_number} submitted.')
        return redirect('inventory:return_list')
    return render(request, 'inventory/return_form.html', {
        'items': items, 'departments': DEPARTMENTS,
    })


@login_required
@require_POST
def return_action(request, return_id):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    ret = get_object_or_404(DepartmentReturn, pk=return_id, is_deleted=False, status='PENDING')
    action = request.POST.get('action')
    if action == 'accept':
        for ri in ret.items.select_related('item').all():
            if ri.condition == 'GOOD':
                ri.item.current_stock += ri.quantity
                ri.item.save(update_fields=['current_stock'])
                StockMovement.objects.create(
                    item=ri.item, movement_type='RETURN',
                    quantity=ri.quantity, balance_after=ri.item.current_stock,
                    reference=f'RET-{ret.return_number}',
                    notes=f'Returned from {ret.department}',
                    performed_by=request.user,
                )
        ret.status = 'ACCEPTED'
        ret.received_by = request.user
        ret.save(update_fields=['status', 'received_by'])
        # 4-Eyes: Create validation for return GL posting
        total_value = sum(
            (ri.quantity or 0) * float(ri.item.unit_cost or 0)
            for ri in ret.items.select_related('item').filter(condition='GOOD')
        )
        if total_value > 0:
            _create_stock_validation(
                validation_type=StockValidationType.RETURN,
                source_id=ret.pk, reference=ret.return_number,
                description=f'Department return — RET-{ret.return_number} — {ret.department}',
                total_value=total_value, user=request.user,
            )
        messages.success(request, f'Return RET-{ret.return_number} accepted — stock restored.')
    elif action == 'reject':
        ret.status = 'REJECTED'
        ret.received_by = request.user
        ret.rejection_reason = request.POST.get('reason', '').strip()
        ret.save(update_fields=['status', 'received_by', 'rejection_reason'])
        messages.warning(request, f'Return RET-{ret.return_number} rejected.')
    return redirect('inventory:return_list')


# ══════════════════════════════════════════════════════════════════════════════
# REPORTS
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def report_stock_valuation(request):
    """Current stock with cost valuation — like SAGE État de Stock."""
    if not _can_view_reports(request.user):
        return HttpResponseForbidden('Access denied.')
    category = request.GET.get('category', '')
    q = request.GET.get('q', '')
    items = InventoryItem.objects.filter(is_active=True, is_deleted=False)
    if category:
        items = items.filter(category=category)
    if q:
        items = items.filter(Q(name__icontains=q) | Q(item_code__icontains=q))
    items = items.order_by('name')
    total_value = 0
    rows = []
    for item in items:
        val = item.current_stock * float(item.unit_cost)
        total_value += val
        rows.append({'item': item, 'value': val})
    return render(request, 'inventory/report_valuation.html', {
        'rows': rows, 'total_value': total_value,
        'categories': ItemCategory.choices, 'category': category, 'search': q,
    })


@login_required
def report_movement_history(request):
    """Stock movement audit trail."""
    if not _can_view_reports(request.user):
        return HttpResponseForbidden('Access denied.')
    import datetime
    days = int(request.GET.get('days', 30))
    cutoff = timezone.localdate() - datetime.timedelta(days=days)
    item_id = request.GET.get('item', '')
    movements = StockMovement.objects.filter(created_at__date__gte=cutoff).select_related('item', 'performed_by')
    if item_id:
        movements = movements.filter(item_id=item_id)
    movements = movements.order_by('-created_at')[:500]
    items_for_filter = InventoryItem.objects.filter(is_active=True, is_deleted=False).order_by('name')
    return render(request, 'inventory/report_movements.html', {
        'movements': movements, 'days': days, 'item_id': item_id,
        'items_for_filter': items_for_filter,
    })


@login_required
def report_consumption_by_dept(request):
    """Consumption by department — from requisition issues."""
    if not _can_view_reports(request.user):
        return HttpResponseForbidden('Access denied.')
    import datetime
    from django.db.models.functions import TruncMonth
    months = int(request.GET.get('months', 6))
    cutoff = timezone.localdate() - datetime.timedelta(days=months * 30)
    # Group by department
    dept_data = (
        DepartmentRequisition.objects.filter(
            status__in=['ISSUED', 'PARTIAL'], is_deleted=False,
            issued_at__date__gte=cutoff,
        )
        .values('department')
        .annotate(
            total_reqs=Count('id'),
            total_items=Sum('items__quantity_issued'),
        )
        .order_by('-total_items')
    )
    return render(request, 'inventory/report_consumption.html', {
        'dept_data': dept_data, 'months': months,
    })


@login_required
def report_expiry_alert(request):
    """Items near expiry or already expired."""
    if not _can_view_reports(request.user):
        return HttpResponseForbidden('Access denied.')
    import datetime
    days = int(request.GET.get('days', 90))
    today = timezone.localdate()
    cutoff = today + datetime.timedelta(days=days)
    batches = BatchStock.objects.filter(
        quantity_remaining__gt=0, expiry_date__lte=cutoff,
    ).select_related('item').order_by('expiry_date').annotate(
        at_risk_value=ExpressionWrapper(
            F('quantity_remaining') * F('unit_cost'), output_field=FloatField()
        ),
    )
    total_value = sum(b.at_risk_value or 0 for b in batches)
    return render(request, 'inventory/report_expiry.html', {
        'batches': batches, 'days': days, 'total_value': total_value, 'today': today,
    })


@login_required
def report_vendor_performance(request):
    """Vendor performance scorecard — ISO 9001 §8.4."""
    if not _can_view_reports(request.user):
        return HttpResponseForbidden('Access denied.')
    vendors = Vendor.objects.filter(is_active=True, is_deleted=False).order_by('-total_orders')
    return render(request, 'inventory/report_vendors.html', {'vendors': vendors})


# ═══════════════════════════════════════════════════════════════════════════════
# INTER-STORE TRANSFERS (ISO 9001 §8.5.4)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def transfer_list(request):
    if not _can_access_store(request.user):
        return HttpResponseForbidden('Access denied.')
    status = request.GET.get('status', '')
    search = request.GET.get('q', '').strip()
    qs = StoreTransfer.objects.filter(is_deleted=False).select_related(
        'from_location', 'to_location', 'requested_by',
    )
    if status:
        qs = qs.filter(status=status)
    if search:
        qs = qs.filter(
            Q(transfer_number__icontains=search) |
            Q(from_location__name__icontains=search) |
            Q(to_location__name__icontains=search)
        )
    return render(request, 'inventory/transfer_list.html', {
        'transfers': qs[:200], 'status_filter': status, 'search': search,
        'status_choices': StoreTransferStatus.choices,
    })


@login_required
def transfer_create(request):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    locations = StoreLocation.objects.filter(is_active=True, is_deleted=False)
    items = InventoryItem.objects.filter(is_active=True, is_deleted=False).order_by('name')
    # Build JSON dict: {store_id: [{id, name, code, stock}]} for client-side filtering
    import json as _json
    items_by_store = {}
    for it in items:
        sid = str(it.store_location_id) if it.store_location_id else '__none__'
        if sid not in items_by_store:
            items_by_store[sid] = []
        items_by_store[sid].append({
            'id': str(it.id),
            'name': it.name,
            'code': it.item_code,
            'stock': it.current_stock,
        })
    items_by_store_json = _json.dumps(items_by_store)
    if request.method == 'POST':
        from_loc = get_object_or_404(StoreLocation, pk=request.POST.get('from_location'))
        to_loc = get_object_or_404(StoreLocation, pk=request.POST.get('to_location'))
        if from_loc == to_loc:
            messages.error(request, 'From and To locations must be different.')
            return render(request, 'inventory/transfer_form.html', {
                'locations': locations, 'items': items,
            })
        tr = StoreTransfer.objects.create(
            from_location=from_loc, to_location=to_loc,
            requested_by=request.user, created_by=request.user,
            notes=request.POST.get('notes', '').strip(),
        )
        item_ids = request.POST.getlist('item_id[]')
        qtys = request.POST.getlist('quantity[]')
        notes_list = request.POST.getlist('item_notes[]')
        for i, (item_id, qty_str) in enumerate(zip(item_ids, qtys)):
            if not item_id or not qty_str:
                continue
            StoreTransferItem.objects.create(
                transfer=tr,
                item=InventoryItem.objects.get(id=item_id),
                quantity=int(qty_str),
                notes=notes_list[i] if i < len(notes_list) else '',
            )
        messages.success(request, f'Transfer {tr.transfer_number} created.')
        return redirect('inventory:transfer_list')
    return render(request, 'inventory/transfer_form.html', {
        'locations': locations,
        'items': items,
        'items_by_store_json': items_by_store_json,
    })


@login_required
def transfer_detail(request, transfer_id):
    if not _can_access_store(request.user):
        return HttpResponseForbidden('Access denied.')
    tr = get_object_or_404(StoreTransfer, pk=transfer_id, is_deleted=False)
    return render(request, 'inventory/transfer_detail.html', {
        'transfer': tr,
        'transfer_items': tr.items.select_related('item').all(),
    })


@login_required
@require_POST
def transfer_approve(request, transfer_id):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    tr = get_object_or_404(StoreTransfer, pk=transfer_id, status=StoreTransferStatus.REQUESTED)
    tr.status = StoreTransferStatus.APPROVED
    tr.approved_by = request.user
    tr.save(update_fields=['status', 'approved_by', 'updated_at'])
    messages.success(request, f'Transfer {tr.transfer_number} approved.')
    return redirect('inventory:transfer_detail', transfer_id=tr.pk)


@login_required
@require_POST
def transfer_dispatch(request, transfer_id):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    tr = get_object_or_404(StoreTransfer, pk=transfer_id, status=StoreTransferStatus.APPROVED)
    # Deduct stock from source
    for ti in tr.items.select_related('item').all():
        item = ti.item
        item.current_stock = max(0, item.current_stock - ti.quantity)
        item.save(update_fields=['current_stock'])
        StockMovement.objects.create(
            item=item, movement_type='OUT', quantity=-ti.quantity,
            balance_after=item.current_stock,
            reference=f'Transfer {tr.transfer_number} to {tr.to_location.name}',
            performed_by=request.user,
        )
    tr.status = StoreTransferStatus.IN_TRANSIT
    tr.save(update_fields=['status', 'updated_at'])
    messages.success(request, f'Transfer {tr.transfer_number} dispatched.')
    return redirect('inventory:transfer_detail', transfer_id=tr.pk)


@login_required
@require_POST
def transfer_receive(request, transfer_id):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    tr = get_object_or_404(StoreTransfer, pk=transfer_id, status=StoreTransferStatus.IN_TRANSIT)
    # Add stock at destination — find or create the matching item in the destination store
    for ti in tr.items.select_related('item').all():
        src_item = ti.item
        # Look for same item already in destination store
        dst_item = InventoryItem.objects.filter(
            store_location=tr.to_location,
            name=src_item.name,
            is_deleted=False,
        ).first()
        if dst_item is None:
            # Create new item record in destination store
            dst_item = InventoryItem.objects.create(
                store_location=tr.to_location,
                name=src_item.name,
                item_code=f'{tr.to_location.store_code}-{src_item.item_code}'[:50],
                category=src_item.category,
                unit=src_item.unit,
                unit_cost=src_item.unit_cost,
                reorder_level=src_item.reorder_level,
                description=src_item.description,
                created_by=request.user,
            )
        dst_item.current_stock += ti.quantity
        dst_item.save(update_fields=['current_stock'])
        StockMovement.objects.create(
            item=dst_item, movement_type='IN', quantity=ti.quantity,
            balance_after=dst_item.current_stock,
            reference=f'Transfer {tr.transfer_number} from {tr.from_location.name}',
            performed_by=request.user,
        )
    tr.status = StoreTransferStatus.RECEIVED
    tr.received_by = request.user
    tr.save(update_fields=['status', 'received_by', 'updated_at'])
    # GL posting: Dr destination store / Cr source store (balance sheet reclassification)
    try:
        from apps.inventory.gl_service import post_inter_store_transfer
        post_inter_store_transfer(tr, user=request.user)
    except Exception:
        pass
    messages.success(request, f'Transfer {tr.transfer_number} received.')
    return redirect('inventory:transfer_detail', transfer_id=tr.pk)


@login_required
@require_POST
def transfer_cancel(request, transfer_id):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    tr = get_object_or_404(StoreTransfer, pk=transfer_id)
    if tr.status in (StoreTransferStatus.RECEIVED,):
        messages.error(request, 'Cannot cancel a received transfer.')
        return redirect('inventory:transfer_detail', transfer_id=tr.pk)
    tr.status = StoreTransferStatus.CANCELLED
    tr.save(update_fields=['status', 'updated_at'])
    messages.success(request, f'Transfer {tr.transfer_number} cancelled.')
    return redirect('inventory:transfer_detail', transfer_id=tr.pk)


# ═══════════════════════════════════════════════════════════════════════════════
# GOODS RECEIVED NOTE (JCI FMS.5 / ISO 9001 §8.6)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def grn_list(request):
    if not _can_access_inventory(request.user):
        return HttpResponseForbidden('Access denied.')
    search = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')
    grns = GoodsReceivedNote.objects.filter(is_deleted=False).select_related(
        'purchase_order__vendor', 'received_by',
    )
    if status_filter:
        grns = grns.filter(status=status_filter)
    if search:
        grns = grns.filter(
            Q(grn_number__icontains=search) |
            Q(purchase_order__vendor__name__icontains=search) |
            Q(purchase_order__po_number__icontains=search)
        )
    return render(request, 'inventory/grn_list.html', {
        'grns': grns[:200],
        'search': search,
        'status_filter': status_filter,
        'statuses': GRNStatus.choices,
    })


@login_required
def grn_create(request):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    received_pos = PurchaseOrder.objects.filter(
        status='RECEIVED', is_deleted=False,
    ).select_related('vendor')
    if request.method == 'POST':
        po = get_object_or_404(PurchaseOrder, pk=request.POST.get('purchase_order'))
        grn = GoodsReceivedNote.objects.create(
            purchase_order=po,
            received_by=request.user,
            created_by=request.user,
            packaging_intact='packaging_intact' in request.POST,
            labels_correct='labels_correct' in request.POST,
            quantity_matches_po='quantity_matches_po' in request.POST,
            expiry_acceptable='expiry_acceptable' in request.POST,
            storage_temp_ok='storage_temp_ok' in request.POST,
            certificates_present='certificates_present' in request.POST,
            visual_inspection_ok='visual_inspection_ok' in request.POST,
            inspection_notes=request.POST.get('inspection_notes', '').strip(),
            notes=request.POST.get('notes', '').strip(),
            requester_name=request.POST.get('requester_name', '').strip(),
            logistics_assistant=request.POST.get('logistics_assistant', '').strip(),
            requester_signature_date=timezone.localdate(),
            logistics_signature_date=timezone.localdate(),
            status=GRNStatus.INSPECTED,
        )
        # Auto-create GRN items from PO items
        for poi in po.items.select_related('item').all():
            GRNItem.objects.create(
                grn=grn, po_item=poi,
                quantity_received=poi.quantity_received or poi.quantity_ordered,
                quantity_accepted=poi.quantity_received or poi.quantity_ordered,
                lot_number=poi.lot_number,
                expiry_date=poi.expiry_date,
            )
        grn.inspected_by = request.user
        grn.save(update_fields=['inspected_by'])
        messages.success(request, f'GRN {grn.grn_number} created and inspected.')
        return redirect('inventory:grn_detail', grn_id=grn.pk)
    return render(request, 'inventory/grn_form.html', {'pos': received_pos})


@login_required
def grn_detail(request, grn_id):
    if not _can_access_inventory(request.user):
        return HttpResponseForbidden('Access denied.')
    grn = get_object_or_404(GoodsReceivedNote, pk=grn_id, is_deleted=False)
    return render(request, 'inventory/grn_detail.html', {
        'grn': grn,
        'grn_items': grn.items.select_related('po_item__item').all(),
    })


@login_required
def grn_pdf(request, grn_id):
    """Generate professional PDF for a GRN with letterhead and signatures."""
    if not _can_access_inventory(request.user):
        return HttpResponseForbidden('Access denied.')
    grn = get_object_or_404(GoodsReceivedNote, pk=grn_id, is_deleted=False)
    grn_items = grn.items.select_related('po_item__item').all()
    from apps.reports.views import render_pdf
    return render_pdf('inventory/pdf/grn_pdf.html', {
        'grn': grn, 'grn_items': grn_items,
        'pdf_filename': f'GRN_{grn.grn_number}.pdf',
        'pdf_seal_label': 'GOODS RECEIVED NOTE',
    })


@login_required
@require_POST
def grn_accept(request, grn_id):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    grn = get_object_or_404(GoodsReceivedNote, pk=grn_id, status=GRNStatus.INSPECTED)
    # Update stock for accepted quantities
    for gi in grn.items.select_related('po_item__item').all():
        item = gi.po_item.item
        item.current_stock += gi.quantity_accepted
        item.save(update_fields=['current_stock'])
        StockMovement.objects.create(
            item=item, movement_type='IN', quantity=gi.quantity_accepted,
            balance_after=item.current_stock,
            reference=f'GRN {grn.grn_number}',
            performed_by=request.user,
        )
        # Create batch if expiry tracked
        if item.requires_expiry_tracking and gi.expiry_date:
            BatchStock.objects.create(
                item=item, lot_number=gi.lot_number or grn.grn_number,
                expiry_date=gi.expiry_date,
                quantity_received=gi.quantity_accepted,
                quantity_remaining=gi.quantity_accepted,
                unit_cost=gi.po_item.unit_price,
                purchase_order=grn.purchase_order,
            )
    grn.status = GRNStatus.AWAITING_VALIDATION
    grn.save(update_fields=['status', 'updated_at'])
    # Update vendor stats
    vendor = grn.purchase_order.vendor
    vendor.total_orders += 1
    po = grn.purchase_order
    if po.expected_date and grn.received_date <= po.expected_date:
        vendor.on_time_deliveries += 1
    else:
        vendor.late_deliveries += 1
    vendor.save(update_fields=['total_orders', 'on_time_deliveries', 'late_deliveries'])
    # 4-Eyes: Calculate total value and create validation request
    total_value = sum(
        (gi.quantity_accepted or 0) * float(gi.po_item.unit_price or 0)
        for gi in grn.items.select_related('po_item').all()
    )
    _create_stock_validation(
        validation_type=StockValidationType.GRN,
        source_id=grn.pk, reference=grn.grn_number,
        description=f'GRN {grn.grn_number} — PO {grn.purchase_order.po_number} — {grn.purchase_order.vendor.name}',
        total_value=total_value, user=request.user,
    )
    messages.success(request, f'GRN {grn.grn_number} accepted — awaiting Finance Director validation for GL posting.')
    return redirect('inventory:grn_detail', grn_id=grn.pk)


@login_required
@require_POST
def grn_reject(request, grn_id):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    grn = get_object_or_404(GoodsReceivedNote, pk=grn_id, status=GRNStatus.INSPECTED)
    grn.status = GRNStatus.REJECTED
    grn.notes = f"{grn.notes}\nRejection: {request.POST.get('reason', '').strip()}"
    grn.save(update_fields=['status', 'notes', 'updated_at'])
    # Record quality incident on vendor
    vendor = grn.purchase_order.vendor
    vendor.quality_incidents += 1
    vendor.save(update_fields=['quality_incidents'])
    messages.warning(request, f'GRN {grn.grn_number} rejected.')
    return redirect('inventory:grn_detail', grn_id=grn.pk)


# ═══════════════════════════════════════════════════════════════════════════════
# DISPOSAL WORKFLOW (JCI MMU.3.2 / WHO)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def disposal_list(request):
    if not _can_access_store(request.user):
        return HttpResponseForbidden('Access denied.')
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '').strip()
    qs = DisposalRecord.objects.filter(is_deleted=False).select_related('requested_by')
    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(Q(disposal_number__icontains=search))
    return render(request, 'inventory/disposal_list.html', {
        'disposals': qs[:200], 'status_filter': status_filter, 'search': search,
        'statuses': DisposalStatus.choices,
    })


@login_required
def disposal_create(request):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    items = InventoryItem.objects.filter(is_active=True, is_deleted=False).order_by('name')
    batches = BatchStock.objects.filter(quantity_remaining__gt=0).select_related('item').order_by('item__name', 'expiry_date')
    if request.method == 'POST':
        dr = DisposalRecord.objects.create(
            reason=request.POST.get('reason', 'OTHER'),
            disposal_method=request.POST.get('disposal_method', ''),
            notes=request.POST.get('notes', '').strip(),
            requested_by=request.user,
            created_by=request.user,
        )
        item_ids = request.POST.getlist('item_id[]')
        batch_ids = request.POST.getlist('batch_id[]')
        qtys = request.POST.getlist('quantity[]')
        costs = request.POST.getlist('unit_cost[]')
        for i, (item_id, qty_str) in enumerate(zip(item_ids, qtys)):
            if not item_id or not qty_str:
                continue
            batch = None
            if i < len(batch_ids) and batch_ids[i]:
                try:
                    batch = BatchStock.objects.get(pk=batch_ids[i])
                except BatchStock.DoesNotExist:
                    pass
            cost = Decimal(costs[i]) if i < len(costs) and costs[i] else Decimal('0')
            DisposalItem.objects.create(
                disposal=dr,
                item=InventoryItem.objects.get(id=item_id),
                batch=batch,
                quantity=int(qty_str),
                unit_cost=cost,
            )
        messages.success(request, f'Disposal request {dr.disposal_number} submitted.')
        return redirect('inventory:disposal_list')
    return render(request, 'inventory/disposal_form.html', {
        'items': items, 'batches': batches,
    })


@login_required
def disposal_detail(request, disposal_id):
    if not _can_access_store(request.user):
        return HttpResponseForbidden('Access denied.')
    dr = get_object_or_404(DisposalRecord, pk=disposal_id, is_deleted=False)
    return render(request, 'inventory/disposal_detail.html', {
        'disposal': dr,
        'disposal_items': dr.items.select_related('item', 'batch').all(),
    })


@login_required
@require_POST
def disposal_authorize(request, disposal_id):
    """Admin / Finance Director authorizes disposal."""
    from apps.accounts.models import UserRole
    if request.user.role not in (UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR, UserRole.FINANCE_DIRECTOR):
        return HttpResponseForbidden('Only Admin Director or Finance Director can authorize disposal.')
    dr = get_object_or_404(DisposalRecord, pk=disposal_id, status=DisposalStatus.PENDING)
    dr.status = DisposalStatus.APPROVED
    dr.authorized_by = request.user
    dr.save(update_fields=['status', 'authorized_by', 'updated_at'])
    messages.success(request, f'Disposal {dr.disposal_number} authorized.')
    return redirect('inventory:disposal_detail', disposal_id=dr.pk)


@login_required
@require_POST
def disposal_dispose(request, disposal_id):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    dr = get_object_or_404(DisposalRecord, pk=disposal_id, status=DisposalStatus.APPROVED)
    # Deduct from stock
    for di in dr.items.select_related('item', 'batch').all():
        item = di.item
        item.current_stock = max(0, item.current_stock - di.quantity)
        item.save(update_fields=['current_stock'])
        StockMovement.objects.create(
            item=item, movement_type='OUT', quantity=-di.quantity,
            balance_after=item.current_stock,
            reference=f'Disposal {dr.disposal_number} ({dr.get_reason_display()})',
            performed_by=request.user,
        )
        # If linked to a batch, deduct from batch too
        if di.batch:
            di.batch.quantity_remaining = max(0, di.batch.quantity_remaining - di.quantity)
            di.batch.save(update_fields=['quantity_remaining'])
    dr.status = DisposalStatus.DISPOSED
    dr.disposal_date = timezone.localdate()
    dr.witness_id = request.POST.get('witness') or None
    dr.environmental_certificate = 'env_cert' in request.POST
    dr.save(update_fields=['status', 'disposal_date', 'witness', 'environmental_certificate', 'updated_at'])
    # 4-Eyes: Create validation for disposal GL posting
    total_value = sum(
        (di.quantity or 0) * float(di.unit_cost or 0)
        for di in dr.items.all()
    )
    if total_value > 0:
        _create_stock_validation(
            validation_type=StockValidationType.DISPOSAL,
            source_id=dr.pk, reference=dr.disposal_number,
            description=f'Stock disposal — {dr.disposal_number} ({dr.get_disposal_method_display()})',
            total_value=total_value, user=request.user,
        )
    messages.success(request, f'Disposal {dr.disposal_number} completed — stock deducted, awaiting GL validation.')
    return redirect('inventory:disposal_detail', disposal_id=dr.pk)


@login_required
@require_POST
def disposal_reject(request, disposal_id):
    from apps.accounts.models import UserRole
    if request.user.role not in (UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR, UserRole.FINANCE_DIRECTOR):
        return HttpResponseForbidden('Access denied.')
    dr = get_object_or_404(DisposalRecord, pk=disposal_id, status=DisposalStatus.PENDING)
    dr.status = DisposalStatus.REJECTED
    dr.notes = f"{dr.notes}\nRejection: {request.POST.get('reason', '').strip()}"
    dr.save(update_fields=['status', 'notes', 'updated_at'])
    messages.warning(request, f'Disposal {dr.disposal_number} rejected.')
    return redirect('inventory:disposal_detail', disposal_id=dr.pk)


# ═══════════════════════════════════════════════════════════════════════════════
# STOCK TAKE SCHEDULE (ISO 9001 §8.5.4)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def schedule_list(request):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    schedules = StockTakeSchedule.objects.filter(is_active=True, is_deleted=False)
    return render(request, 'inventory/schedule_list.html', {'schedules': schedules})


@login_required
def schedule_create(request):
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    from apps.accounts.models import User, UserRole
    staff = User.objects.filter(role__in=[UserRole.STORE_KEEPER, UserRole.ADMIN], is_active=True).order_by('first_name')
    if request.method == 'POST':
        StockTakeSchedule.objects.create(
            name=request.POST.get('name', '').strip(),
            frequency=request.POST.get('frequency', 'MONTHLY'),
            category_filter=request.POST.get('category_filter', ''),
            abc_filter=request.POST.get('abc_filter', ''),
            assigned_to_id=request.POST.get('assigned_to') or None,
            next_due=request.POST.get('next_due'),
            notes=request.POST.get('notes', '').strip(),
            created_by=request.user,
        )
        messages.success(request, 'Stock take schedule created.')
        return redirect('inventory:schedule_list')
    return render(request, 'inventory/schedule_form.html', {
        'staff': staff,
        'category_choices': ItemCategory.choices,
        'abc_choices': ABCClass.choices,
        'frequency_choices': StockTakeSchedule._meta.get_field('frequency').choices,
    })


@login_required
@require_POST
def schedule_start_count(request, schedule_id):
    """Create a new StockCount from a schedule."""
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    sched = get_object_or_404(StockTakeSchedule, pk=schedule_id, is_active=True)
    # Build item filter
    items = InventoryItem.objects.filter(is_active=True, is_deleted=False)
    if sched.category_filter:
        items = items.filter(category=sched.category_filter)
    if sched.abc_filter:
        items = items.filter(abc_class=sched.abc_filter)
    # Create count
    sc = StockCount.objects.create(
        counted_by=request.user,
        notes=f'Scheduled: {sched.name} ({sched.get_frequency_display()})',
        created_by=request.user,
    )
    for item in items:
        StockCountItem.objects.create(
            stock_count=sc, item=item,
            system_quantity=item.current_stock,
            physical_quantity=0,
        )
    # Update schedule
    import datetime
    sched.last_completed = timezone.localdate()
    freq_days = {'WEEKLY': 7, 'MONTHLY': 30, 'QUARTERLY': 90, 'SEMI_ANNUAL': 182, 'ANNUAL': 365}
    sched.next_due = timezone.localdate() + datetime.timedelta(days=freq_days.get(sched.frequency, 30))
    sched.save(update_fields=['last_completed', 'next_due', 'updated_at'])
    messages.success(request, f'Stock count {sc.count_number} created from schedule "{sched.name}" with {items.count()} items.')
    return redirect('inventory:stock_count_detail', count_id=sc.pk)


# ═══════════════════════════════════════════════════════════════════════════════
# ABC / VEN ANALYSIS REPORT (WHO Essential Medicines Standard)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def report_abc_analysis(request):
    """ABC/VEN analysis — classify items by annual consumption value."""
    if not _can_view_reports(request.user):
        return HttpResponseForbidden('Access denied.')
    import datetime
    # Calculate annual consumption value from stock movements (last 12 months)
    cutoff = timezone.localdate() - datetime.timedelta(days=365)
    items = InventoryItem.objects.filter(is_active=True, is_deleted=False).annotate(
        annual_usage=Coalesce(
            Sum('movements__quantity',
                filter=Q(movements__movement_type__in=['OUT', 'ISSUE'],
                         movements__created_at__date__gte=cutoff)),
            0,
        ),
    )
    # Calculate annual value
    analysis = []
    for item in items:
        annual_value = abs(item.annual_usage) * float(item.unit_cost)
        analysis.append({
            'item': item, 'annual_usage': abs(item.annual_usage),
            'annual_value': annual_value,
        })
    # Sort by annual_value DESC
    analysis.sort(key=lambda x: x['annual_value'], reverse=True)
    grand_total = sum(a['annual_value'] for a in analysis) or 1
    # Calculate cumulative % and assign ABC class
    cumulative = 0
    class_a_count = class_b_count = class_c_count = 0
    class_a_value = class_b_value = class_c_value = 0
    for a in analysis:
        cumulative += a['annual_value']
        a['cumulative_pct'] = round(cumulative / grand_total * 100, 1)
        if a['cumulative_pct'] <= 80:
            a['abc_class'] = 'A'
            class_a_count += 1
            class_a_value += a['annual_value']
        elif a['cumulative_pct'] <= 95:
            a['abc_class'] = 'B'
            class_b_count += 1
            class_b_value += a['annual_value']
        else:
            a['abc_class'] = 'C'
            class_c_count += 1
            class_c_value += a['annual_value']
    # Auto-update ABC class on items if requested
    if request.GET.get('apply') == '1':
        for a in analysis:
            item = a['item']
            if item.abc_class != a['abc_class']:
                item.abc_class = a['abc_class']
                item.save(update_fields=['abc_class'])
        messages.success(request, 'ABC classes updated on all items.')
    return render(request, 'inventory/report_abc.html', {
        'analysis': analysis, 'grand_total': grand_total,
        'class_a_count': class_a_count, 'class_a_value': class_a_value,
        'class_b_count': class_b_count, 'class_b_value': class_b_value,
        'class_c_count': class_c_count, 'class_c_value': class_c_value,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# STATS / ANALYTICS (WHO / ISO 9001)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def stats(request):
    """Comprehensive store analytics — consumption trends, KPIs, charts."""
    if not _can_view_reports(request.user):
        return HttpResponseForbidden('Access denied.')
    import datetime
    from django.db.models.functions import TruncMonth, TruncDate

    today = timezone.localdate()
    month_start = today.replace(day=1)

    # ── Period filter ────────────────────────────────────────────────
    period = request.GET.get('period', 'month')
    if period == 'year':
        cutoff = today.replace(month=1, day=1)
        period_label = f'Year {today.year}'
    elif period == 'quarter':
        q_month = ((today.month - 1) // 3) * 3 + 1
        cutoff = today.replace(month=q_month, day=1)
        period_label = f'Q{(today.month - 1) // 3 + 1} {today.year}'
    else:
        cutoff = month_start
        period_label = today.strftime('%B %Y')

    # ── KPIs ─────────────────────────────────────────────────────────
    all_items = InventoryItem.objects.filter(is_active=True, is_deleted=False)
    total_items = all_items.count()
    low_stock = all_items.filter(current_stock__lte=F('reorder_level')).count()
    out_of_stock = all_items.filter(current_stock=0).count()
    overstocked = all_items.filter(max_stock_level__gt=0, current_stock__gt=F('max_stock_level')).count()

    stock_value = all_items.aggregate(
        total=Sum(F('current_stock') * F('unit_cost'), output_field=FloatField())
    )['total'] or 0

    # Stockout rate
    stockout_rate = round(out_of_stock / total_items * 100, 1) if total_items else 0

    # PO spend this period
    po_spend = PurchaseOrder.objects.filter(
        status='RECEIVED', is_deleted=False, received_date__gte=cutoff,
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

    # Requisition stats
    reqs_period = DepartmentRequisition.objects.filter(
        is_deleted=False, created_at__date__gte=cutoff,
    )
    total_reqs = reqs_period.count()
    fulfilled_reqs = reqs_period.filter(status='ISSUED').count()
    fulfillment_rate = round(fulfilled_reqs / total_reqs * 100, 1) if total_reqs else 0

    # Average lead time (POs with expected_date and received_date)
    from django.db.models.functions import Cast
    lead_time_pos = PurchaseOrder.objects.filter(
        status='RECEIVED', is_deleted=False,
        expected_date__isnull=False, received_date__isnull=False,
        received_date__gte=cutoff,
    )
    lead_times = []
    for po in lead_time_pos[:100]:
        lead_times.append((po.received_date - po.ordered_date).days)
    avg_lead_time = round(sum(lead_times) / len(lead_times), 1) if lead_times else 0

    # Expiry risk
    near_expiry = BatchStock.objects.filter(
        quantity_remaining__gt=0, expiry_date__lte=today + datetime.timedelta(days=90),
        expiry_date__gte=today,
    ).count()
    expired = BatchStock.objects.filter(
        quantity_remaining__gt=0, expiry_date__lt=today,
    ).count()
    expiry_value = BatchStock.objects.filter(
        quantity_remaining__gt=0, expiry_date__lte=today + datetime.timedelta(days=90),
    ).aggregate(
        val=Sum(F('quantity_remaining') * F('unit_cost'), output_field=FloatField())
    )['val'] or 0

    # ── 12-month trend (movements) ───────────────────────────────────
    twelve_months_ago = today - datetime.timedelta(days=365)
    monthly_in = (
        StockMovement.objects.filter(
            movement_type='IN', created_at__date__gte=twelve_months_ago,
        ).annotate(month=TruncMonth('created_at'))
        .values('month').annotate(total=Sum('quantity')).order_by('month')
    )
    monthly_out = (
        StockMovement.objects.filter(
            movement_type__in=['OUT', 'ISSUE'], created_at__date__gte=twelve_months_ago,
        ).annotate(month=TruncMonth('created_at'))
        .values('month').annotate(total=Sum('quantity')).order_by('month')
    )
    # Build month labels
    trend_labels, trend_in, trend_out = [], [], []
    in_dict = {m['month'].strftime('%Y-%m'): m['total'] for m in monthly_in}
    out_dict = {m['month'].strftime('%Y-%m'): abs(m['total']) for m in monthly_out}
    for i in range(12):
        d = today - datetime.timedelta(days=(11 - i) * 30)
        key = d.strftime('%Y-%m')
        label = d.strftime('%b %y')
        trend_labels.append(label)
        trend_in.append(in_dict.get(key, 0))
        trend_out.append(out_dict.get(key, 0))

    # ── Daily movements (last 30 days) ───────────────────────────────
    thirty_ago = today - datetime.timedelta(days=30)
    daily_moves = (
        StockMovement.objects.filter(created_at__date__gte=thirty_ago)
        .annotate(day=TruncDate('created_at'))
        .values('day').annotate(count=Count('id')).order_by('day')
    )
    daily_labels = []
    daily_data = []
    d_dict = {m['day'].strftime('%d/%m'): m['count'] for m in daily_moves}
    for i in range(30):
        d = thirty_ago + datetime.timedelta(days=i)
        key = d.strftime('%d/%m')
        daily_labels.append(key)
        daily_data.append(d_dict.get(key, 0))

    # ── Category distribution ────────────────────────────────────────
    cat_data = (
        all_items.values('category').annotate(count=Count('id'))
        .order_by('-count')
    )
    cat_labels = [ItemCategory(c['category']).label for c in cat_data]
    cat_counts = [c['count'] for c in cat_data]

    # ── Top 10 consumed items ────────────────────────────────────────
    top_consumed = (
        StockMovement.objects.filter(
            movement_type__in=['OUT', 'ISSUE'], created_at__date__gte=cutoff,
        ).values('item__name', 'item__item_code')
        .annotate(total_qty=Sum('quantity'))
        .order_by('total_qty')[:10]
    )
    top_consumed = [{'name': t['item__name'], 'code': t['item__item_code'],
                     'qty': abs(t['total_qty'])} for t in top_consumed]

    # ── Department consumption ───────────────────────────────────────
    dept_consumption = (
        DepartmentRequisition.objects.filter(
            status__in=['ISSUED', 'PARTIAL'], is_deleted=False,
            issued_at__date__gte=cutoff,
        ).values('department')
        .annotate(total_items=Sum('items__quantity_issued'))
        .order_by('-total_items')
    )
    dept_labels = [d['department'] for d in dept_consumption]
    dept_values = [d['total_items'] or 0 for d in dept_consumption]

    # ── Vendor performance summary ───────────────────────────────────
    vendors = Vendor.objects.filter(
        is_active=True, is_deleted=False, total_orders__gt=0,
    ).order_by('-on_time_deliveries')[:10]

    # ── ABC class summary ────────────────────────────────────────────
    abc_counts = all_items.exclude(abc_class='').values('abc_class').annotate(
        count=Count('id'),
        value=Sum(F('current_stock') * F('unit_cost'), output_field=FloatField()),
    ).order_by('abc_class')

    # ── VEN class summary ────────────────────────────────────────────
    ven_counts = all_items.exclude(ven_class='').values('ven_class').annotate(
        count=Count('id'),
    ).order_by('ven_class')

    # ── Stock turn rate ──────────────────────────────────────────────
    annual_consumption = StockMovement.objects.filter(
        movement_type__in=['OUT', 'ISSUE'],
        created_at__date__gte=twelve_months_ago,
    ).aggregate(total=Sum('quantity'))['total'] or 0
    stock_turn_rate = round(abs(annual_consumption) / (float(stock_value) / max(1, float(all_items.aggregate(
        avg_cost=Coalesce(Sum(F('unit_cost')), 0, output_field=FloatField()))['avg_cost'] or 1))) * 12, 1) if stock_value else 0

    import json
    context = {
        'period': period, 'period_label': period_label,
        'total_items': total_items, 'low_stock': low_stock,
        'out_of_stock': out_of_stock, 'overstocked': overstocked,
        'stock_value': int(stock_value), 'stockout_rate': stockout_rate,
        'po_spend': int(po_spend), 'total_reqs': total_reqs,
        'fulfilled_reqs': fulfilled_reqs, 'fulfillment_rate': fulfillment_rate,
        'avg_lead_time': avg_lead_time,
        'near_expiry': near_expiry, 'expired': expired, 'expiry_value': int(expiry_value),
        'stock_turn_rate': stock_turn_rate,
        # Charts
        'trend_labels': json.dumps(trend_labels), 'trend_in': json.dumps(trend_in),
        'trend_out': json.dumps(trend_out),
        'daily_labels': json.dumps(daily_labels), 'daily_data': json.dumps(daily_data),
        'cat_labels': json.dumps(cat_labels), 'cat_counts': json.dumps(cat_counts),
        'dept_labels': json.dumps(dept_labels), 'dept_values': json.dumps(dept_values),
        'top_consumed': top_consumed,
        'vendors': vendors,
        'abc_counts': abc_counts, 'ven_counts': ven_counts,
    }
    return render(request, 'inventory/stats.html', context)


# ═══════════════════════════════════════════════════════════════════════════════
# MOVEMENT LOG (Unified Audit Trail)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def movement_log(request):
    """Unified stock movement audit trail with filters."""
    if not _can_access_store(request.user):
        return HttpResponseForbidden('Access denied.')
    import datetime
    days = int(request.GET.get('days', 30))
    move_type = request.GET.get('type', '')
    q = request.GET.get('q', '')
    cutoff = timezone.localdate() - datetime.timedelta(days=days)

    movements = StockMovement.objects.filter(
        created_at__date__gte=cutoff,
    ).select_related('item', 'performed_by', 'batch')

    if move_type:
        movements = movements.filter(movement_type=move_type)
    if q:
        movements = movements.filter(
            Q(item__name__icontains=q) | Q(item__item_code__icontains=q) | Q(reference__icontains=q)
        )

    movements = movements.order_by('-created_at')[:500]

    # Summary counts
    period_moves = StockMovement.objects.filter(created_at__date__gte=cutoff)
    summary = period_moves.values('movement_type').annotate(count=Count('id'))
    type_map = {s['movement_type']: s['count'] for s in summary}

    move_types = [('IN', 'Stock In'), ('OUT', 'Stock Out'), ('ADJUST', 'Adjustment'),
                  ('RETURN', 'Return'), ('EXPIRE', 'Expiry Write-off'), ('ISSUE', 'Dept. Issue')]

    return render(request, 'inventory/movement_log.html', {
        'movements': movements, 'days': days, 'move_type': move_type,
        'search': q, 'type_map': type_map, 'move_types': move_types,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# RECEIVE STOCK (Standalone — Walk-in Deliveries)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def receive_stock(request):
    """Receive stock directly without a PO — for walk-in deliveries."""
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')

    items = InventoryItem.objects.filter(is_active=True, is_deleted=False).order_by('name')
    vendors = Vendor.objects.filter(is_active=True, is_deleted=False).order_by('name')

    if request.method == 'POST':
        vendor_name = request.POST.get('vendor_name', '').strip()
        delivery_note = request.POST.get('delivery_note', '').strip()

        item_ids = request.POST.getlist('item_id[]')
        quantities = request.POST.getlist('quantity[]')
        lot_numbers = request.POST.getlist('lot_number[]')
        expiry_dates = request.POST.getlist('expiry_date[]')
        unit_costs = request.POST.getlist('unit_cost[]')

        received_count = 0
        for i, item_id in enumerate(item_ids):
            if not item_id:
                continue
            qty = int(quantities[i]) if i < len(quantities) and quantities[i] else 0
            if qty <= 0:
                continue

            try:
                inv_item = InventoryItem.objects.get(id=item_id, is_deleted=False)
            except InventoryItem.DoesNotExist:
                continue

            lot = lot_numbers[i].strip() if i < len(lot_numbers) else ''
            exp = expiry_dates[i] if i < len(expiry_dates) and expiry_dates[i] else None
            cost = Decimal(unit_costs[i]) if i < len(unit_costs) and unit_costs[i] else inv_item.unit_cost

            inv_item.current_stock += qty
            inv_item.save(update_fields=['current_stock'])

            batch = None
            if inv_item.requires_expiry_tracking and exp:
                batch = BatchStock.objects.create(
                    item=inv_item, lot_number=lot or f'WLK-{timezone.localdate().strftime("%Y%m%d")}',
                    expiry_date=exp, quantity_received=qty, quantity_remaining=qty,
                    unit_cost=cost,
                )

            StockMovement.objects.create(
                item=inv_item, movement_type='IN', quantity=qty,
                balance_after=inv_item.current_stock,
                reference=f'Walk-in: {vendor_name}' if vendor_name else 'Direct Receipt',
                notes=f'DN: {delivery_note}' if delivery_note else '',
                performed_by=request.user, batch=batch,
            )
            received_count += 1

        if received_count:
            messages.success(request, f'{received_count} item(s) received successfully.')
        return redirect('inventory:receive_stock')

    # Recent receipts (last 7 days)
    import datetime
    recent = StockMovement.objects.filter(
        movement_type='IN',
        created_at__date__gte=timezone.localdate() - datetime.timedelta(days=7),
    ).select_related('item', 'performed_by').order_by('-created_at')[:20]

    return render(request, 'inventory/receive_stock.html', {
        'items': items, 'vendors': vendors, 'recent': recent,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# ALERTS — Low Stock + Expiry + Reorder
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def alerts(request):
    """Consolidated alerts dashboard — low stock, expiry, overstock, auto-reorder."""
    if not _can_access_inventory(request.user):
        return HttpResponseForbidden('Access denied.')
    import datetime
    today = timezone.localdate()

    # Low stock items
    low_stock_items = InventoryItem.objects.filter(
        is_active=True, is_deleted=False,
        current_stock__lte=F('reorder_level'), current_stock__gt=0,
    ).order_by('current_stock')

    # Out of stock
    out_of_stock_items = InventoryItem.objects.filter(
        is_active=True, is_deleted=False, current_stock=0,
    ).order_by('name')

    # Overstocked
    overstocked_items = InventoryItem.objects.filter(
        is_active=True, is_deleted=False, max_stock_level__gt=0,
        current_stock__gt=F('max_stock_level'),
    ).order_by('-current_stock')

    # Expiring in 30 days
    expiring_30 = BatchStock.objects.filter(
        quantity_remaining__gt=0,
        expiry_date__gte=today, expiry_date__lte=today + datetime.timedelta(days=30),
    ).select_related('item').order_by('expiry_date')

    # Expiring in 90 days
    expiring_90 = BatchStock.objects.filter(
        quantity_remaining__gt=0,
        expiry_date__gt=today + datetime.timedelta(days=30),
        expiry_date__lte=today + datetime.timedelta(days=90),
    ).select_related('item').order_by('expiry_date')

    # Already expired
    expired_batches = BatchStock.objects.filter(
        quantity_remaining__gt=0, expiry_date__lt=today,
    ).select_related('item').order_by('expiry_date')

    # Pending auto-reorder POs
    auto_pos = PurchaseOrder.objects.filter(
        is_deleted=False, status='DRAFT', is_auto_generated=True,
    ).select_related('vendor')

    # Quarantined batches
    quarantined = BatchStock.objects.filter(
        is_quarantined=True, quantity_remaining__gt=0,
    ).select_related('item')

    # Overdue stock counts
    overdue_schedules = StockTakeSchedule.objects.filter(
        is_active=True, is_deleted=False, next_due__lt=today,
    )

    context = {
        'low_stock_items': low_stock_items, 'out_of_stock_items': out_of_stock_items,
        'overstocked_items': overstocked_items,
        'expiring_30': expiring_30, 'expiring_90': expiring_90,
        'expired_batches': expired_batches,
        'auto_pos': auto_pos, 'quarantined': quarantined,
        'overdue_schedules': overdue_schedules,
        'today': today,
    }
    return render(request, 'inventory/alerts.html', context)


# ═══════════════════════════════════════════════════════════════════════════════
# BARCODE SCAN (Quick Lookup / Issue)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def barcode_scan(request):
    """Barcode scan page — look up items by scanning barcode."""
    if not _can_access_store(request.user):
        return HttpResponseForbidden('Access denied.')
    scanned_item = None
    if request.GET.get('code'):
        code = request.GET['code'].strip()
        scanned_item = InventoryItem.objects.filter(
            Q(barcode=code) | Q(item_code=code), is_deleted=False,
        ).first()
    return render(request, 'inventory/barcode_scan.html', {
        'scanned_item': scanned_item,
        'code': request.GET.get('code', ''),
    })


@login_required
def barcode_lookup_ajax(request):
    """AJAX barcode lookup — returns JSON item data."""
    code = request.GET.get('code', '').strip()
    if not code:
        return JsonResponse({'found': False})
    item = InventoryItem.objects.filter(
        Q(barcode=code) | Q(item_code=code), is_deleted=False,
    ).first()
    if not item:
        return JsonResponse({'found': False})
    batches = list(item.batches.filter(
        quantity_remaining__gt=0, is_quarantined=False,
    ).order_by('expiry_date').values('lot_number', 'expiry_date', 'quantity_remaining')[:5])
    return JsonResponse({
        'found': True,
        'id': str(item.id),
        'name': item.name,
        'item_code': item.item_code,
        'category': item.get_category_display(),
        'current_stock': item.current_stock,
        'reorder_level': item.reorder_level,
        'unit': item.unit,
        'unit_cost': float(item.unit_cost),
        'stock_status': item.stock_status,
        'barcode': item.barcode or '',
        'batches': batches,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# CONSIGNMENT STOCK
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def consignment_dashboard(request):
    """Track consignment stock separately — items not paid until used."""
    if not _can_access_store(request.user):
        return HttpResponseForbidden('Access denied.')

    consignment_items = InventoryItem.objects.filter(
        is_active=True, is_deleted=False, is_consignment=True,
    ).order_by('name')

    total_value = sum(float(i.current_stock) * float(i.unit_cost) for i in consignment_items)
    total_items = consignment_items.count()
    in_stock = consignment_items.filter(current_stock__gt=0).count()

    # Usage in last 30 days
    import datetime
    cutoff = timezone.localdate() - datetime.timedelta(days=30)
    usage = StockMovement.objects.filter(
        item__is_consignment=True,
        movement_type__in=['OUT', 'ISSUE'],
        created_at__date__gte=cutoff,
    ).aggregate(total=Sum('quantity'))['total'] or 0

    return render(request, 'inventory/consignment_dashboard.html', {
        'items': consignment_items,
        'total_value': int(total_value), 'total_items': total_items,
        'in_stock': in_stock, 'usage_30d': abs(usage),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# SUPPLIER QUOTATION (ISO 9001 §8.4 — Vendor Selection)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def quotation_list(request):
    if not _can_access_store(request.user) and not _can_manage_procurement(request.user):
        return HttpResponseForbidden('Access denied.')
    status = request.GET.get('status', '')
    qs = SupplierQuotation.objects.filter(is_deleted=False).select_related('vendor', 'requested_by')
    if status:
        qs = qs.filter(status=status)
    return render(request, 'inventory/quotation_list.html', {
        'quotations': qs[:200], 'status_filter': status,
        'status_choices': QuotationStatus.choices,
    })


@login_required
def quotation_create(request):
    if not _can_manage_procurement(request.user):
        return HttpResponseForbidden('Access denied.')
    vendors = Vendor.objects.filter(is_active=True, is_deleted=False).order_by('name')
    items = InventoryItem.objects.filter(is_active=True, is_deleted=False).order_by('name')

    if request.method == 'POST':
        vendor = get_object_or_404(Vendor, id=request.POST.get('vendor_id'), is_deleted=False)
        valid_until = request.POST.get('valid_until') or None
        q = SupplierQuotation.objects.create(
            vendor=vendor, valid_until=valid_until,
            notes=request.POST.get('notes', '').strip(),
            requested_by=request.user, created_by=request.user,
        )
        item_ids = request.POST.getlist('item_id[]')
        quantities = request.POST.getlist('quantity[]')
        prices = request.POST.getlist('price[]')
        total = Decimal('0')
        for item_id, qty_str, price_str in zip(item_ids, quantities, prices):
            if not item_id or not qty_str:
                continue
            try:
                qty = int(qty_str)
                price = Decimal(price_str or '0')
                QuotationItem.objects.create(
                    quotation=q, item_id=item_id,
                    quantity=qty, quoted_price=price,
                )
                total += qty * price
            except (ValueError, InventoryItem.DoesNotExist):
                continue
        q.total_amount = total
        q.save(update_fields=['total_amount'])
        messages.success(request, f'Quotation {q.rfq_number} created.')
        return redirect('inventory:quotation_detail', rfq_id=q.pk)

    return render(request, 'inventory/quotation_form.html', {
        'vendors': vendors, 'items': items, 'action': 'Create',
    })


@login_required
def quotation_detail(request, rfq_id):
    if not _can_manage_procurement(request.user) and not _can_access_store(request.user):
        return HttpResponseForbidden('Access denied.')
    q = get_object_or_404(SupplierQuotation, pk=rfq_id, is_deleted=False)
    # Find competing quotations for same items
    item_ids = list(q.items.values_list('item_id', flat=True))
    competitors = SupplierQuotation.objects.filter(
        is_deleted=False, status__in=['RECEIVED', 'REQUESTED'],
        items__item_id__in=item_ids,
    ).exclude(pk=q.pk).select_related('vendor').distinct()[:10]

    return render(request, 'inventory/quotation_detail.html', {
        'quotation': q,
        'quotation_items': q.items.select_related('item').all(),
        'competitors': competitors,
    })


@login_required
def quotation_update(request, rfq_id):
    """Update quotation with received prices."""
    if not _can_manage_procurement(request.user):
        return HttpResponseForbidden('Access denied.')
    q = get_object_or_404(SupplierQuotation, pk=rfq_id, is_deleted=False)
    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'update_prices':
            total = Decimal('0')
            for qi in q.items.all():
                price_key = f'price_{qi.pk}'
                if price_key in request.POST:
                    qi.quoted_price = Decimal(request.POST[price_key] or '0')
                    qi.save(update_fields=['quoted_price'])
                    total += qi.quantity * qi.quoted_price
            q.total_amount = total
            q.status = QuotationStatus.RECEIVED
            q.save(update_fields=['total_amount', 'status'])
            messages.success(request, f'Quotation {q.rfq_number} prices updated.')
        elif action == 'accept':
            q.status = QuotationStatus.ACCEPTED
            q.save(update_fields=['status'])
            messages.success(request, f'Quotation {q.rfq_number} accepted.')
        elif action == 'reject':
            q.status = QuotationStatus.REJECTED
            q.save(update_fields=['status'])
            messages.warning(request, f'Quotation {q.rfq_number} rejected.')
        elif action == 'create_po':
            # Create PO from accepted quotation
            po = PurchaseOrder.objects.create(
                vendor=q.vendor, status='SUBMITTED',
                notes=f'From quotation {q.rfq_number}',
                created_by=request.user,
            )
            total = Decimal('0')
            for qi in q.items.select_related('item').all():
                sub = qi.quantity * qi.quoted_price
                PurchaseOrderItem.objects.create(
                    purchase_order=po, item=qi.item,
                    quantity_ordered=qi.quantity, unit_price=qi.quoted_price,
                    subtotal=sub,
                )
                total += sub
            po.total_amount = total
            po.save(update_fields=['total_amount'])
            q.linked_po = po
            q.save(update_fields=['linked_po'])
            messages.success(request, f'PO {po.po_number} created from quotation {q.rfq_number}.')
            return redirect('inventory:po_detail', po_id=po.pk)
        return redirect('inventory:quotation_detail', rfq_id=q.pk)
    return redirect('inventory:quotation_detail', rfq_id=q.pk)


@login_required
def quotation_edit(request, rfq_id):
    """Edit quotation header + line items (only REQUESTED/RECEIVED)."""
    if not _can_manage_procurement(request.user):
        return HttpResponseForbidden('Access denied.')
    q = get_object_or_404(SupplierQuotation, pk=rfq_id, is_deleted=False)
    if q.status not in ('REQUESTED', 'RECEIVED'):
        messages.error(request, f'Cannot edit quotation {q.rfq_number} — status is {q.get_status_display()}.')
        return redirect('inventory:quotation_detail', rfq_id=q.pk)

    vendors = Vendor.objects.filter(is_active=True, is_deleted=False).order_by('name')
    items = InventoryItem.objects.filter(is_active=True, is_deleted=False).order_by('name')

    if request.method == 'POST':
        # Update header
        vendor_id = request.POST.get('vendor_id')
        if vendor_id:
            q.vendor = get_object_or_404(Vendor, id=vendor_id, is_deleted=False)
        q.valid_until = request.POST.get('valid_until') or None
        q.notes = request.POST.get('notes', '').strip()
        q.updated_by = request.user
        q.save(update_fields=['vendor', 'valid_until', 'notes', 'updated_by'])

        # Replace line items
        q.items.all().delete()
        item_ids = request.POST.getlist('item_id[]')
        quantities = request.POST.getlist('quantity[]')
        prices = request.POST.getlist('price[]')
        total = Decimal('0')
        for item_id, qty_str, price_str in zip(item_ids, quantities, prices):
            if not item_id or not qty_str:
                continue
            try:
                qty = int(qty_str)
                price = Decimal(price_str or '0')
                QuotationItem.objects.create(
                    quotation=q, item_id=item_id,
                    quantity=qty, quoted_price=price,
                )
                total += qty * price
            except (ValueError, InventoryItem.DoesNotExist):
                continue
        q.total_amount = total
        q.save(update_fields=['total_amount'])
        messages.success(request, f'Quotation {q.rfq_number} updated.')
        return redirect('inventory:quotation_detail', rfq_id=q.pk)

    return render(request, 'inventory/quotation_form.html', {
        'vendors': vendors, 'items': items, 'action': 'Edit',
        'quotation': q,
        'quotation_items': q.items.select_related('item').all(),
    })


@login_required
def quotation_delete(request, rfq_id):
    """Soft-delete quotation — preserved in recycle bin for audit."""
    if not _can_manage_procurement(request.user):
        return HttpResponseForbidden('Access denied.')
    q = get_object_or_404(SupplierQuotation, pk=rfq_id, is_deleted=False)
    if request.method == 'POST':
        if q.linked_po:
            messages.error(request, f'Cannot delete {q.rfq_number} — linked to PO {q.linked_po.po_number}.')
            return redirect('inventory:quotation_detail', rfq_id=q.pk)
        reason = request.POST.get('deletion_reason', '').strip()
        if not reason:
            messages.error(request, 'A deletion reason is required.')
            return redirect('inventory:quotation_detail', rfq_id=q.pk)
        q.soft_delete(user=request.user, reason=reason)
        messages.success(request, f'Quotation {q.rfq_number} moved to recycle bin.')
        return redirect('inventory:quotation_list')
    return redirect('inventory:quotation_list')


@login_required
def recycle_bin(request):
    """Super Admin audit: view all soft-deleted inventory records."""
    if not request.user.is_super_admin and not request.user.is_admin_director:
        return HttpResponseForbidden('Access denied.')
    deleted_vendors = Vendor.objects.filter(is_deleted=True).order_by('-deleted_at')[:50]
    deleted_quotations = SupplierQuotation.objects.filter(is_deleted=True).select_related('vendor').order_by('-deleted_at')[:50]
    deleted_items = InventoryItem.objects.filter(is_deleted=True).order_by('-deleted_at')[:50]
    deleted_pos = PurchaseOrder.objects.filter(is_deleted=True).select_related('vendor').order_by('-deleted_at')[:50]
    deleted_invoices = SupplierInvoice.objects.filter(is_deleted=True).select_related('vendor').order_by('-deleted_at')[:50]
    return render(request, 'inventory/recycle_bin.html', {
        'deleted_vendors': deleted_vendors,
        'deleted_quotations': deleted_quotations,
        'deleted_items': deleted_items,
        'deleted_pos': deleted_pos,
        'deleted_invoices': deleted_invoices,
    })


@login_required
def recycle_restore(request, model_type, obj_id):
    """Restore a soft-deleted record from recycle bin."""
    if not request.user.is_super_admin and not request.user.is_admin_director:
        return HttpResponseForbidden('Access denied.')
    if request.method != 'POST':
        return redirect('inventory:recycle_bin')
    model_map = {
        'vendor': Vendor,
        'quotation': SupplierQuotation,
        'item': InventoryItem,
        'po': PurchaseOrder,
        'invoice': SupplierInvoice,
    }
    model_cls = model_map.get(model_type)
    if not model_cls:
        return HttpResponseForbidden('Invalid type.')
    obj = get_object_or_404(model_cls, pk=obj_id, is_deleted=True)
    obj.is_deleted = False
    obj.deleted_at = None
    obj.save(update_fields=['is_deleted', 'deleted_at'])
    messages.success(request, f'{model_type.title()} "{obj}" restored.')
    return redirect('inventory:recycle_bin')


@login_required
def quotation_compare(request):
    """Compare quotations for the same items side-by-side."""
    if not _can_access_store(request.user) and not _can_manage_procurement(request.user):
        return HttpResponseForbidden('Access denied.')
    rfq_ids = request.GET.getlist('rfq')
    quotations = SupplierQuotation.objects.filter(
        pk__in=rfq_ids, is_deleted=False,
    ).select_related('vendor').prefetch_related('items__item')

    # Build comparison matrix: item → {vendor: price}
    all_items = {}
    for q in quotations:
        for qi in q.items.all():
            key = str(qi.item_id)
            if key not in all_items:
                all_items[key] = {'item': qi.item, 'quotes': {}}
            all_items[key]['quotes'][str(q.pk)] = {
                'price': qi.quoted_price, 'qty': qi.quantity,
                'subtotal': qi.subtotal, 'vendor': q.vendor.name,
            }

    return render(request, 'inventory/quotation_compare.html', {
        'quotations': quotations,
        'comparison': all_items.values(),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# STORE BUDGET (ISO 9001 §7.1 — Resource Management)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def budget_list(request):
    if not _can_view_reports(request.user):
        return HttpResponseForbidden('Access denied.')
    year = int(request.GET.get('year', timezone.localdate().year))
    budgets = StoreBudget.objects.filter(is_deleted=False, fiscal_year=year)
    total_allocated = budgets.aggregate(total=Sum('allocated'))['total'] or Decimal('0')
    total_spent = budgets.aggregate(total=Sum('spent'))['total'] or Decimal('0')
    total_remaining = total_allocated - total_spent
    return render(request, 'inventory/budget_list.html', {
        'budgets': budgets, 'year': year,
        'total_allocated': total_allocated, 'total_spent': total_spent,
        'total_remaining': total_remaining,
        'years': range(timezone.localdate().year - 2, timezone.localdate().year + 2),
    })


@login_required
def budget_create(request):
    if not _can_manage_procurement(request.user):
        return HttpResponseForbidden('Access denied.')
    if request.method == 'POST':
        StoreBudget.objects.create(
            name=request.POST.get('name', '').strip(),
            fiscal_year=int(request.POST.get('fiscal_year', timezone.localdate().year)),
            category=request.POST.get('category', ''),
            allocated=Decimal(request.POST.get('allocated', '0')),
            notes=request.POST.get('notes', '').strip(),
            created_by=request.user,
        )
        messages.success(request, 'Budget created.')
        return redirect('inventory:budget_list')
    return render(request, 'inventory/budget_form.html', {
        'categories': ItemCategory.choices,
        'current_year': timezone.localdate().year,
        'action': 'Create',
    })


@login_required
def budget_edit(request, budget_id):
    if not _can_manage_procurement(request.user):
        return HttpResponseForbidden('Access denied.')
    budget = get_object_or_404(StoreBudget, pk=budget_id, is_deleted=False)
    if request.method == 'POST':
        budget.name = request.POST.get('name', budget.name).strip()
        budget.allocated = Decimal(request.POST.get('allocated', budget.allocated))
        budget.notes = request.POST.get('notes', '').strip()
        budget.save()
        messages.success(request, f'Budget "{budget.name}" updated.')
        return redirect('inventory:budget_list')
    return render(request, 'inventory/budget_form.html', {
        'budget': budget, 'categories': ItemCategory.choices,
        'current_year': timezone.localdate().year, 'action': 'Edit',
    })


# ═══════════════════════════════════════════════════════════════════════════════
# STOCK EXIT / ISSUE (ISO 9001 §8.5.2 — Controlled Stock Release)
# ═══════════════════════════════════════════════════════════════════════════════

EXIT_REASONS = [
    ('DEPT_ISSUE', 'Department Issue'),
    ('PATIENT_USE', 'Patient Use'),
    ('MAINTENANCE', 'Maintenance / Repair'),
    ('EXPIRED', 'Expired — Write-Off'),
    ('DAMAGED', 'Damaged — Write-Off'),
    ('SAMPLE', 'Sample / Demo'),
    ('DONATION', 'Donation'),
    ('RETURN_VENDOR', 'Return to Vendor'),
    ('LOSS', 'Loss / Shrinkage'),
    ('OTHER', 'Other'),
]


@login_required
def stock_exit_list(request):
    """List all stock exit/issue records."""
    if not _can_access_store(request.user):
        return HttpResponseForbidden('Access denied.')
    import datetime
    days = int(request.GET.get('days', 30))
    search = request.GET.get('q', '').strip()
    cutoff = timezone.localdate() - datetime.timedelta(days=days)
    exits = StockMovement.objects.filter(
        movement_type__in=['OUT', 'ISSUE', 'EXPIRE'],
        created_at__date__gte=cutoff,
    ).select_related('item', 'performed_by', 'batch').order_by('-created_at')
    if search:
        exits = exits.filter(
            Q(item__name__icontains=search) | Q(item__item_code__icontains=search)
        )
    return render(request, 'inventory/stock_exit_list.html', {
        'exits': exits[:500], 'days': days, 'search': search,
    })


@login_required
def stock_exit_create(request):
    """Create a stock exit / issue note — multi-line, batch optional."""
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    from apps.billing.models import StockOperationType
    items = InventoryItem.objects.filter(is_active=True, is_deleted=False).order_by('name')
    store_locations = StoreLocation.objects.filter(is_active=True, is_deleted=False).order_by('name')
    exit_op_types = StockOperationType.objects.filter(
        category='EXIT', is_active=True, is_deleted=False
    ).select_related('debit_account', 'credit_account').order_by('code')

    if request.method == 'POST':
        department = request.POST.get('department', '').strip()
        op_type_id = request.POST.get('operation_type', '')
        reason = request.POST.get('reason', 'DEPT_ISSUE')
        reference = request.POST.get('reference', '').strip()
        notes = request.POST.get('notes', '').strip()
        authorized_by = request.POST.get('authorized_by', '').strip()
        source_store_id = request.POST.get('source_store', '')
        received_by_name = request.POST.get('received_by', '').strip()

        item_ids = request.POST.getlist('item_id[]')
        quantities = request.POST.getlist('quantity[]')

        issued_count = 0
        for i, item_id in enumerate(item_ids):
            if not item_id:
                continue
            qty = int(quantities[i]) if i < len(quantities) and quantities[i] else 0
            if qty <= 0:
                continue
            try:
                inv_item = InventoryItem.objects.get(id=item_id, is_deleted=False)
            except InventoryItem.DoesNotExist:
                continue

            actual_qty = min(qty, inv_item.current_stock)
            if actual_qty <= 0:
                continue

            inv_item.current_stock -= actual_qty
            inv_item.save(update_fields=['current_stock'])

            # FEFO batch consumption (optional)
            batch_ref = None
            if inv_item.requires_expiry_tracking:
                remaining = actual_qty
                for batch in inv_item.batches.filter(
                    quantity_remaining__gt=0, is_quarantined=False,
                ).order_by('expiry_date'):
                    if remaining <= 0:
                        break
                    take = min(remaining, batch.quantity_remaining)
                    batch.quantity_remaining -= take
                    batch.save(update_fields=['quantity_remaining'])
                    remaining -= take
                    if not batch_ref:
                        batch_ref = batch

            ref_parts = [reason]
            if department:
                ref_parts.append(department)
            if source_store_id:
                try:
                    src = StoreLocation.objects.get(pk=source_store_id)
                    ref_parts.append(f'Store: {src.name}')
                except StoreLocation.DoesNotExist:
                    pass
            note_parts = []
            if authorized_by:
                note_parts.append(f'Auth: {authorized_by}')
            if received_by_name:
                note_parts.append(f'Rcvd: {received_by_name}')
            if notes:
                note_parts.append(notes)

            StockMovement.objects.create(
                item=inv_item, movement_type='OUT', quantity=-actual_qty,
                balance_after=inv_item.current_stock,
                reference=' | '.join(ref_parts),
                notes=' | '.join(note_parts),
                performed_by=request.user, batch=batch_ref,
            )
            _trigger_auto_reorder(inv_item, request.user)
            issued_count += 1

        if issued_count:
            # 4-Eyes: Create validation for stock exit GL posting
            recent_movements = StockMovement.objects.filter(
                performed_by=request.user, movement_type='OUT',
            ).order_by('-created_at')[:issued_count]
            total_value = sum(
                abs(m.quantity or 0) * float(m.item.unit_cost or 0)
                for m in recent_movements.select_related('item')
            )
            # Get store code for document number
            try:
                _exit_store = StoreLocation.objects.get(pk=source_store_id)
                _exit_store_code = _exit_store.store_code or _exit_store.location_type[:4]
            except StoreLocation.DoesNotExist:
                _exit_store_code = 'GEN'
            exit_ref = _next_doc_number('EXIT', _exit_store_code)
            op_label = ''
            if op_type_id:
                op_obj = StockOperationType.objects.filter(pk=op_type_id).first()
                if op_obj:
                    op_label = f' [OP:{op_obj.code}]'
            _create_stock_validation(
                validation_type=StockValidationType.EXIT,
                source_id=recent_movements.first().pk if recent_movements.exists() else request.user.pk,
                reference=exit_ref,
                description=f'Stock exit — {reason} — {department or "N/A"} — {issued_count} item(s){op_label}',
                total_value=total_value, user=request.user,
                operation_type_id=op_type_id or None,
            )
            messages.success(request, f'{issued_count} item(s) issued — awaiting GL validation.')
        else:
            messages.warning(request, 'No items were issued — check stock availability.')
        return redirect('inventory:stock_exit_list')

    import json as _json
    store_codes = {str(s.pk): (s.store_code or s.location_type[:4]) for s in store_locations}
    return render(request, 'inventory/stock_exit_form.html', {
        'items': items, 'departments': DEPARTMENTS,
        'reasons': EXIT_REASONS, 'store_locations': store_locations,
        'operation_types': exit_op_types,
        'store_codes': store_codes,
        'store_codes_json': _json.dumps(store_codes),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# STOCK ENTRY NOTE (ISO 9001 §8.5.1 — Controlled Stock Receipt)
# ═══════════════════════════════════════════════════════════════════════════════

ENTRY_SOURCES = [
    ('PURCHASE', 'Purchase / PO Delivery'),
    ('DONATION', 'Donation'),
    ('TRANSFER_IN', 'Transfer In (from other store)'),
    ('RETURN', 'Department Return'),
    ('FOUND', 'Found / Adjustment (+)'),
    ('OPENING', 'Opening Stock'),
    ('OTHER', 'Other'),
]


@login_required
def stock_entry_list(request):
    """List all stock entry records."""
    if not _can_access_store(request.user):
        return HttpResponseForbidden('Access denied.')
    import datetime
    days = int(request.GET.get('days', 30))
    search = request.GET.get('q', '').strip()
    cutoff = timezone.localdate() - datetime.timedelta(days=days)
    entries = StockMovement.objects.filter(
        movement_type='IN',
        created_at__date__gte=cutoff,
    ).select_related('item', 'performed_by', 'batch').order_by('-created_at')
    if search:
        entries = entries.filter(
            Q(item__name__icontains=search) | Q(item__item_code__icontains=search)
        )
    return render(request, 'inventory/stock_entry_list.html', {
        'entries': entries[:500], 'days': days, 'search': search,
    })


@login_required
def stock_entry_create(request):
    """Create a stock entry note — multi-line, batch optional."""
    if not _can_manage_store(request.user):
        return HttpResponseForbidden('Access denied.')
    from apps.billing.models import StockOperationType
    items = InventoryItem.objects.filter(is_active=True, is_deleted=False).order_by('name')
    vendors = Vendor.objects.filter(is_active=True, is_deleted=False).order_by('name')
    store_locations = StoreLocation.objects.filter(is_active=True, is_deleted=False).order_by('name')
    entry_op_types = StockOperationType.objects.filter(
        category='ENTRY', is_active=True, is_deleted=False
    ).select_related('debit_account', 'credit_account').order_by('code')

    if request.method == 'POST':
        source = request.POST.get('source', 'PURCHASE')
        op_type_id = request.POST.get('operation_type', '')
        vendor_name = request.POST.get('vendor_name', '').strip()
        delivery_note = request.POST.get('delivery_note', '').strip()
        invoice_number = request.POST.get('invoice_number', '').strip()
        notes = request.POST.get('notes', '').strip()
        dest_store_id = request.POST.get('destination_store', '')
        condition = request.POST.get('condition', 'GOOD')
        po_reference = request.POST.get('po_reference', '').strip()
        temp_check = request.POST.get('temp_check', '')

        item_ids = request.POST.getlist('item_id[]')
        quantities = request.POST.getlist('quantity[]')
        lot_numbers = request.POST.getlist('lot_number[]')
        expiry_dates = request.POST.getlist('expiry_date[]')
        unit_costs = request.POST.getlist('unit_cost[]')

        received_count = 0
        for i, item_id in enumerate(item_ids):
            if not item_id:
                continue
            qty = int(quantities[i]) if i < len(quantities) and quantities[i] else 0
            if qty <= 0:
                continue
            try:
                inv_item = InventoryItem.objects.get(id=item_id, is_deleted=False)
            except InventoryItem.DoesNotExist:
                continue

            lot = lot_numbers[i].strip() if i < len(lot_numbers) else ''
            exp = expiry_dates[i] if i < len(expiry_dates) and expiry_dates[i] else None
            cost = Decimal(unit_costs[i]) if i < len(unit_costs) and unit_costs[i] else inv_item.unit_cost

            inv_item.current_stock += qty
            if cost and cost != inv_item.unit_cost:
                inv_item.unit_cost = cost
            inv_item.save(update_fields=['current_stock', 'unit_cost'])

            batch = None
            if exp or lot:
                batch = BatchStock.objects.create(
                    item=inv_item,
                    lot_number=lot or f'SEN-{timezone.localdate().strftime("%Y%m%d")}',
                    expiry_date=exp, quantity_received=qty, quantity_remaining=qty,
                    unit_cost=cost,
                )

            ref_parts = [source]
            if vendor_name:
                ref_parts.append(vendor_name)
            if delivery_note:
                ref_parts.append(f'DN:{delivery_note}')
            if po_reference:
                ref_parts.append(f'PO:{po_reference}')
            if dest_store_id:
                try:
                    dst = StoreLocation.objects.get(pk=dest_store_id)
                    ref_parts.append(f'Store: {dst.name}')
                except StoreLocation.DoesNotExist:
                    pass

            note_parts = []
            if invoice_number:
                note_parts.append(f'INV:{invoice_number}')
            if condition and condition != 'GOOD':
                note_parts.append(f'Condition: {condition}')
            if temp_check:
                note_parts.append(f'Temp: {temp_check}')
            if notes:
                note_parts.append(notes)

            StockMovement.objects.create(
                item=inv_item, movement_type='IN', quantity=qty,
                balance_after=inv_item.current_stock,
                reference=(entry_ref + ' | ' + ' | '.join(ref_parts)).strip(' | ') if 'entry_ref' in dir() else ' | '.join(ref_parts),
                notes=' | '.join(note_parts) if note_parts else '',
                performed_by=request.user, batch=batch,
            )
            received_count += 1

        if received_count:
            # 4-Eyes: Create validation for stock entry GL posting
            # Recalculate total from movements just created
            recent_movements = StockMovement.objects.filter(
                performed_by=request.user, movement_type='IN',
            ).order_by('-created_at')[:received_count]
            total_value = sum(
                abs(m.quantity or 0) * float(m.item.unit_cost or 0)
                for m in recent_movements.select_related('item')
            )
            # Get store code for document number
            try:
                _entry_store = StoreLocation.objects.get(pk=dest_store_id)
                _entry_store_code = _entry_store.store_code or _entry_store.location_type[:4]
            except StoreLocation.DoesNotExist:
                _entry_store_code = 'GEN'
            entry_ref = _next_doc_number('ENTRY', _entry_store_code)
            op_label = ''
            if op_type_id:
                op_obj = StockOperationType.objects.filter(pk=op_type_id).first()
                if op_obj:
                    op_label = f' [OP:{op_obj.code}]'
            _create_stock_validation(
                validation_type=StockValidationType.ENTRY,
                source_id=recent_movements.first().pk if recent_movements.exists() else request.user.pk,
                reference=entry_ref,
                description=f'Stock entry — {source} — {vendor_name or "N/A"} — {received_count} item(s){op_label}',
                total_value=total_value, user=request.user,
                operation_type_id=op_type_id or None,
            )
            messages.success(request, f'{received_count} item(s) received — awaiting GL validation.')
        return redirect('inventory:stock_entry_list')

    # Build store_code map for JS preview
    import json as _json
    store_codes = {str(s.pk): (s.store_code or s.location_type[:4]) for s in store_locations}
    return render(request, 'inventory/stock_entry_form.html', {
        'items': items, 'vendors': vendors,
        'sources': ENTRY_SOURCES, 'store_locations': store_locations,
        'operation_types': entry_op_types,
        'store_codes': store_codes,
        'store_codes_json': _json.dumps(store_codes),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# PDF GENERATION — Professional letterhead PDFs for inventory documents
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def stock_entry_pdf(request):
    """PDF report of stock entries with letterhead and signatures."""
    if not _can_access_store(request.user):
        return HttpResponseForbidden('Access denied.')
    import datetime
    days = int(request.GET.get('days', 30))
    search = request.GET.get('q', '').strip()
    cutoff = timezone.localdate() - datetime.timedelta(days=days)
    entries = StockMovement.objects.filter(
        movement_type='IN', created_at__date__gte=cutoff,
    ).select_related('item', 'performed_by', 'batch').order_by('-created_at')
    if search:
        entries = entries.filter(
            Q(item__name__icontains=search) | Q(item__item_code__icontains=search)
        )
    from apps.reports.views import render_pdf
    return render_pdf('inventory/pdf/stock_entry_pdf.html', {
        'entries': entries[:500],
        'reference': f'SEN-RPT-{timezone.localdate().strftime("%Y%m%d")}',
        'date_from': cutoff, 'date_to': timezone.localdate(),
        'user': request.user,
        'pdf_filename': f'Stock_Entry_Report_{timezone.localdate()}.pdf',
        'pdf_seal_label': 'STOCK ENTRY REPORT',
    })


@login_required
def stock_exit_pdf(request):
    """PDF report of stock exits with letterhead and signatures."""
    if not _can_access_store(request.user):
        return HttpResponseForbidden('Access denied.')
    import datetime
    days = int(request.GET.get('days', 30))
    search = request.GET.get('q', '').strip()
    cutoff = timezone.localdate() - datetime.timedelta(days=days)
    exits = StockMovement.objects.filter(
        movement_type__in=['OUT', 'ISSUE', 'EXPIRE'],
        created_at__date__gte=cutoff,
    ).select_related('item', 'performed_by', 'batch').order_by('-created_at')
    if search:
        exits = exits.filter(
            Q(item__name__icontains=search) | Q(item__item_code__icontains=search)
        )
    from apps.reports.views import render_pdf
    return render_pdf('inventory/pdf/stock_exit_pdf.html', {
        'exits': exits[:500],
        'reference': f'SEX-RPT-{timezone.localdate().strftime("%Y%m%d")}',
        'date_from': cutoff, 'date_to': timezone.localdate(),
        'user': request.user,
        'pdf_filename': f'Stock_Exit_Report_{timezone.localdate()}.pdf',
        'pdf_seal_label': 'STOCK EXIT REPORT',
    })


@login_required
def transfer_pdf(request, transfer_id):
    """PDF for a specific inter-store transfer with letterhead and signatures."""
    if not _can_access_store(request.user):
        return HttpResponseForbidden('Access denied.')
    tr = get_object_or_404(StoreTransfer, pk=transfer_id, is_deleted=False)
    from apps.reports.views import render_pdf
    return render_pdf('inventory/pdf/transfer_pdf.html', {
        'transfer': tr,
        'transfer_items': tr.items.select_related('item').all(),
        'pdf_filename': f'Transfer_{tr.transfer_number}.pdf',
        'pdf_seal_label': 'INTER-STORE TRANSFER',
    })


# ═══════════════════════════════════════════════════════════════════════════════
# 4-EYES STOCK VALIDATION (Finance Director reviews & validates)
# GL auto-posts ONLY after Finance Director validation
# ═══════════════════════════════════════════════════════════════════════════════

def _can_validate_stock(user):
    """Only Finance Director, Senior Accountant, Super Admin can validate stock for GL."""
    from apps.accounts.models import UserRole
    return user.role in (
        UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT,
        UserRole.SUPER_ADMIN,
    )


@login_required
def stock_validation_list(request):
    """List all pending stock validations for Finance Director review."""
    if not _can_validate_stock(request.user) and not _can_access_store(request.user):
        return HttpResponseForbidden('Access denied.')
    status = request.GET.get('status', '')
    search = request.GET.get('q', '').strip()
    qs = StockValidation.objects.filter(is_deleted=False).select_related('submitted_by', 'validated_by')
    if status:
        qs = qs.filter(status=status)
    if search:
        qs = qs.filter(
            Q(reference__icontains=search) | Q(description__icontains=search)
        )
    pending_count = StockValidation.objects.filter(status=StockValidationStatus.PENDING, is_deleted=False).count()
    return render(request, 'inventory/stock_validation_list.html', {
        'validations': qs[:200],
        'status_filter': status, 'search': search,
        'status_choices': StockValidationStatus.choices,
        'pending_count': pending_count,
        'can_validate': _can_validate_stock(request.user),
    })


@login_required
def stock_validation_detail(request, validation_id):
    """View details of a stock validation with source transaction info."""
    sv = get_object_or_404(StockValidation, pk=validation_id, is_deleted=False)
    if not _can_validate_stock(request.user) and not _can_access_store(request.user):
        return HttpResponseForbidden('Access denied.')

    # Load source transaction based on type
    source_obj = None
    source_items = []
    if sv.validation_type == StockValidationType.GRN:
        source_obj = GoodsReceivedNote.objects.filter(pk=sv.source_id).select_related('purchase_order__vendor').first()
        if source_obj:
            source_items = source_obj.items.select_related('po_item__item').all()
    elif sv.validation_type == StockValidationType.ISSUE:
        source_obj = DepartmentRequisition.objects.filter(pk=sv.source_id).first()
        if source_obj:
            source_items = source_obj.items.select_related('item').all()
    elif sv.validation_type == StockValidationType.DISPOSAL:
        source_obj = DisposalRecord.objects.filter(pk=sv.source_id).first()
        if source_obj:
            source_items = source_obj.items.select_related('item', 'batch').all()
    elif sv.validation_type == StockValidationType.COUNT:
        source_obj = StockCount.objects.filter(pk=sv.source_id).first()
        if source_obj:
            source_items = source_obj.items.select_related('item').exclude(variance=0)
    elif sv.validation_type == StockValidationType.RETURN:
        source_obj = DepartmentReturn.objects.filter(pk=sv.source_id).first()
        if source_obj:
            source_items = source_obj.items.select_related('item').filter(condition='GOOD')

    return render(request, 'inventory/stock_validation_detail.html', {
        'sv': sv, 'source_obj': source_obj, 'source_items': source_items,
        'can_validate': _can_validate_stock(request.user),
    })


@login_required
@require_POST
def stock_validation_approve(request, validation_id):
    """Finance Director validates — triggers GL auto-posting."""
    if not _can_validate_stock(request.user):
        return HttpResponseForbidden('Only Finance Director can validate stock transactions.')
    sv = get_object_or_404(StockValidation, pk=validation_id, status=StockValidationStatus.PENDING)
    notes = request.POST.get('notes', '').strip()

    # Import GL service
    from apps.inventory.gl_service import (
        post_stock_receipt, post_stock_issue, post_stock_disposal,
        post_stock_entry, post_stock_exit, post_stock_adjustment,
        post_stock_count_variance, post_department_return,
    )

    journal_entry = None
    try:
        if sv.validation_type == StockValidationType.GRN:
            grn = GoodsReceivedNote.objects.get(pk=sv.source_id)
            journal_entry = post_stock_receipt(grn, user=request.user)
            if journal_entry:
                grn.status = GRNStatus.VALIDATED
                grn.validated_by = request.user
                grn.validated_at = timezone.now()
                grn.validation_notes = notes
                grn.journal_entry = journal_entry
                grn.save(update_fields=['status', 'validated_by', 'validated_at', 'validation_notes', 'journal_entry'])

        elif sv.validation_type == StockValidationType.ISSUE:
            req = DepartmentRequisition.objects.get(pk=sv.source_id)
            journal_entry = post_stock_issue(req, user=request.user)

        elif sv.validation_type == StockValidationType.DISPOSAL:
            disposal = DisposalRecord.objects.get(pk=sv.source_id)
            journal_entry = post_stock_disposal(disposal, user=request.user)

        elif sv.validation_type == StockValidationType.COUNT:
            sc = StockCount.objects.get(pk=sv.source_id)
            journal_entry = post_stock_count_variance(sc, user=request.user)

        elif sv.validation_type == StockValidationType.RETURN:
            ret = DepartmentReturn.objects.get(pk=sv.source_id)
            journal_entry = post_department_return(ret, user=request.user)

        elif sv.validation_type == StockValidationType.ADJUSTMENT:
            # Stock manual adjustment — look up the movement by source_id
            m = StockMovement.objects.filter(pk=sv.source_id).select_related('item').first()
            if m:
                journal_entry = post_stock_adjustment(
                    m.item, m.quantity, m.item.unit_cost,
                    m.created_at.date(), sv.reference,
                    reason=sv.description, user=request.user,
                )

        elif sv.validation_type in (StockValidationType.ENTRY, StockValidationType.EXIT):
            op_type = sv.operation_type  # StockOperationType or None
            # Recalculate amount from movement's CURRENT unit_cost.
            # Handles the case where price was 0 at entry time but set before validation.
            m_ref = StockMovement.objects.filter(pk=sv.source_id).select_related('item').first()
            live_total = sv.total_value
            if m_ref and (live_total == 0):
                live_total = abs(m_ref.quantity or 0) * (m_ref.item.unit_cost or 0)

            if op_type and op_type.debit_account and op_type.credit_account and live_total > 0:
                # Fast path: operation type has explicit GL accounts + computed total.
                from apps.inventory.gl_service import _create_entry, _op_for_code
                from decimal import Decimal as _D
                amt = _D(str(live_total))
                lines_direct = [
                    (op_type.debit_account.code, amt, 0,
                     f"{sv.get_validation_type_display()} - {sv.reference}"),
                    (op_type.credit_account.code, 0, amt,
                     f"{sv.get_validation_type_display()} - {sv.reference}"),
                ]
                # Auto-tag cost center from the item's store location
                _store_cc = None
                if m_ref and m_ref.item and m_ref.item.store_location_id:
                    try:
                        _sl = StoreLocation.objects.select_related('cost_center').get(
                            pk=m_ref.item.store_location_id
                        )
                        _store_cc = _sl.cost_center if _sl.cost_center_id else None
                    except Exception:
                        pass
                journal_entry = _create_entry(
                    date=timezone.localdate(),
                    description=sv.description or f"Stock {sv.validation_type} - {sv.reference}",
                    reference=sv.reference,
                    source_type=f'stock_{sv.validation_type.lower()}',
                    source_id=sv.pk,
                    lines=lines_direct,
                    user=request.user,
                    operation=_op_for_code(op_type.code),
                    cost_center=_store_cc,
                )
            elif m_ref and live_total > 0:
                # Fallback: no operation type — use item-level GL mapping
                items_data = [(m_ref.item, abs(m_ref.quantity), m_ref.item.unit_cost)]
                if sv.validation_type == StockValidationType.ENTRY:
                    journal_entry = post_stock_entry(
                        sv.reference, items_data,
                        m_ref.created_at.date(), user=request.user,
                        operation_type=op_type,
                    )
                else:
                    journal_entry = post_stock_exit(
                        sv.reference, items_data,
                        m_ref.created_at.date(), reason=sv.description, user=request.user,
                        operation_type=op_type,
                    )

    except Exception as e:
        messages.error(request, f'GL posting failed: {e}')
        return redirect('inventory:stock_validation_detail', validation_id=sv.pk)

    # Update validation record
    sv.status = StockValidationStatus.VALIDATED
    sv.validated_by = request.user
    sv.validated_at = timezone.now()
    sv.validation_notes = notes
    sv.journal_entry = journal_entry
    sv.save(update_fields=['status', 'validated_by', 'validated_at', 'validation_notes', 'journal_entry'])

    if journal_entry:
        messages.success(request, f'{sv.get_validation_type_display()} — {sv.reference} validated. GL journal entry {journal_entry.entry_number} posted.')
    else:
        messages.warning(request, f'{sv.reference} validated but GL posting skipped (accounts not seeded or zero value).')
    return redirect('inventory:stock_validation_list')


@login_required
@require_POST
def stock_validation_reject(request, validation_id):
    """Finance Director rejects a stock transaction validation."""
    if not _can_validate_stock(request.user):
        return HttpResponseForbidden('Only Finance Director can reject stock validations.')
    sv = get_object_or_404(StockValidation, pk=validation_id, status=StockValidationStatus.PENDING)
    sv.status = StockValidationStatus.REJECTED
    sv.validated_by = request.user
    sv.validated_at = timezone.now()
    sv.validation_notes = request.POST.get('notes', '').strip()
    sv.save(update_fields=['status', 'validated_by', 'validated_at', 'validation_notes'])
    messages.warning(request, f'{sv.reference} rejected — no GL posting.')
    return redirect('inventory:stock_validation_list')


# ═══════════════════════════════════════════════════════════════════════════════
# STOCK CARD (Fiche de Stock) — per-item movement history
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def stock_card(request, item_id):
    """
    Stock Card (Fiche de Stock): complete movement history for a single item.
    Shows opening balance, each IN/OUT/ADJUST/RETURN/ISSUE with running balance.
    """
    if not _can_access_inventory(request.user):
        return HttpResponseForbidden('Access denied.')
    item = get_object_or_404(InventoryItem, id=item_id, is_deleted=False)

    date_from = request.GET.get('from', '')
    date_to   = request.GET.get('to', '')
    movements = StockMovement.objects.filter(
        item=item, is_deleted=False
    ).select_related('performed_by', 'batch').order_by('created_at')

    if date_from:
        movements = movements.filter(created_at__date__gte=date_from)
    if date_to:
        movements = movements.filter(created_at__date__lte=date_to)

    # Calculate running balance
    running = Decimal('0')
    card_rows = []
    for m in movements:
        qty_in  = m.quantity if m.quantity > 0 else 0
        qty_out = abs(m.quantity) if m.quantity < 0 else 0
        if m.movement_type in ('IN', 'RETURN'):
            running += abs(m.quantity)
            qty_in = abs(m.quantity)
            qty_out = 0
        elif m.movement_type in ('OUT', 'ISSUE', 'EXPIRE'):
            running -= abs(m.quantity)
            qty_in = 0
            qty_out = abs(m.quantity)
        else:  # ADJUST
            running += m.quantity
            if m.quantity >= 0:
                qty_in = m.quantity
                qty_out = 0
            else:
                qty_in = 0
                qty_out = abs(m.quantity)

        card_rows.append({
            'date': m.created_at,
            'type': m.movement_type,
            'reference': m.reference,
            'notes': m.notes,
            'qty_in': qty_in,
            'qty_out': qty_out,
            'balance': running,
            'batch': m.batch,
            'user': m.performed_by,
        })

    return render(request, 'inventory/stock_card.html', {
        'item': item,
        'card_rows': card_rows,
        'current_stock': item.current_stock,
        'date_from': date_from,
        'date_to': date_to,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# BIN CARD — physical location card
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def bin_card(request, item_id):
    """
    Bin Card: physical location-based stock tracking for a single item.
    Shows item location, batches, expiry dates, and recent movements.
    """
    if not _can_access_inventory(request.user):
        return HttpResponseForbidden('Access denied.')
    item = get_object_or_404(InventoryItem, id=item_id, is_deleted=False)

    batches = BatchStock.objects.filter(
        item=item, is_deleted=False, quantity_remaining__gt=0
    ).order_by('expiry_date')

    recent_movements = StockMovement.objects.filter(
        item=item, is_deleted=False
    ).select_related('performed_by', 'batch').order_by('-created_at')[:20]

    return render(request, 'inventory/bin_card.html', {
        'item': item,
        'batches': batches,
        'recent_movements': recent_movements,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# STOCK LEDGER (Grand Livre des Stocks)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def stock_ledger(request):
    """
    Stock Ledger (Grand Livre des Stocks): master ledger of all items with
    opening stock, total IN, total OUT, closing stock, and total value.
    """
    if not _can_access_inventory(request.user):
        return HttpResponseForbidden('Access denied.')

    category = request.GET.get('category', '')
    search   = request.GET.get('q', '')

    items = InventoryItem.objects.filter(is_active=True, is_deleted=False)
    if category:
        items = items.filter(category=category)
    if search:
        items = items.filter(Q(name__icontains=search) | Q(item_code__icontains=search))

    # Annotate with total IN and OUT movements
    from django.db.models import Case, When, Value, IntegerField
    items = items.annotate(
        total_in=Coalesce(Sum(
            Case(
                When(movements__movement_type__in=['IN', 'RETURN'], movements__is_deleted=False,
                     then='movements__quantity'),
                default=Value(0), output_field=IntegerField(),
            )
        ), Value(0)),
        total_out=Coalesce(Sum(
            Case(
                When(movements__movement_type__in=['OUT', 'ISSUE', 'EXPIRE'], movements__is_deleted=False,
                     then='movements__quantity'),
                default=Value(0), output_field=IntegerField(),
            )
        ), Value(0)),
    ).order_by('category', 'name')

    # Calculate total stock value
    ledger_rows = []
    grand_total = Decimal('0')
    for item in items:
        stock_value = item.current_stock * (item.unit_cost or 0)
        grand_total += stock_value
        ledger_rows.append({
            'item': item,
            'total_in': abs(item.total_in),
            'total_out': abs(item.total_out),
            'stock_value': stock_value,
        })

    return render(request, 'inventory/stock_ledger.html', {
        'ledger_rows': ledger_rows,
        'grand_total': grand_total,
        'categories': ItemCategory.choices,
        'filter_category': category,
        'search': search,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# ANNUAL STOCK TAKE REPORT
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def annual_stock_take_report(request):
    """
    Annual Stock Take Report: comprehensive year-end inventory report.
    Shows all items, their system vs physical quantities, variances,
    and total stock valuation.
    """
    if not _can_view_reports(request.user) and not _can_validate_stock(request.user):
        return HttpResponseForbidden('Access denied.')

    year = request.GET.get('year', str(timezone.localdate().year))
    try:
        year = int(year)
    except ValueError:
        year = timezone.localdate().year

    # Get all stock counts approved in the selected year
    counts = StockCount.objects.filter(
        status=StockCountStatus.APPROVED,
        count_date__year=year,
        is_deleted=False,
    ).select_related('counted_by', 'approved_by').order_by('-count_date')

    # Latest approved count per item
    latest_count_items = {}
    for count in counts:
        for ci in count.items.select_related('item').all():
            if ci.item_id not in latest_count_items:
                latest_count_items[ci.item_id] = {
                    'item': ci.item,
                    'system_qty': ci.system_quantity,
                    'physical_qty': ci.physical_quantity,
                    'variance': ci.variance,
                    'count_date': count.count_date,
                    'counted_by': count.counted_by,
                }

    # All items with their status
    all_items = InventoryItem.objects.filter(is_active=True, is_deleted=False).order_by('category', 'name')
    report_rows = []
    total_system_value = Decimal('0')
    total_physical_value = Decimal('0')
    total_variance_value = Decimal('0')
    items_counted = 0
    items_with_variance = 0

    for item in all_items:
        count_data = latest_count_items.get(item.id)
        system_qty = item.current_stock
        physical_qty = count_data['physical_qty'] if count_data else None
        variance = count_data['variance'] if count_data else None
        unit_cost = item.unit_cost or Decimal('0')

        sys_val = system_qty * unit_cost
        phys_val = (physical_qty * unit_cost) if physical_qty is not None else None
        var_val = (variance * unit_cost) if variance is not None else None

        total_system_value += sys_val
        if phys_val is not None:
            total_physical_value += phys_val
            items_counted += 1
        if variance and variance != 0:
            items_with_variance += 1
            total_variance_value += var_val or Decimal('0')

        report_rows.append({
            'item': item,
            'system_qty': system_qty,
            'physical_qty': physical_qty,
            'variance': variance,
            'unit_cost': unit_cost,
            'system_value': sys_val,
            'physical_value': phys_val,
            'variance_value': var_val,
            'count_date': count_data['count_date'] if count_data else None,
        })

    return render(request, 'inventory/annual_stock_take_report.html', {
        'year': year,
        'report_rows': report_rows,
        'total_items': all_items.count(),
        'items_counted': items_counted,
        'items_with_variance': items_with_variance,
        'total_system_value': total_system_value,
        'total_physical_value': total_physical_value,
        'total_variance_value': total_variance_value,
        'stock_counts': counts,
        'years': range(timezone.localdate().year, 2024, -1),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# PO FINANCE APPROVAL
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def po_finance_approve(request, po_id):
    """Finance Director approval of a Purchase Order (budget gate)."""
    if not _can_validate_stock(request.user):
        return HttpResponseForbidden('Only Finance Director can approve POs.')
    po = get_object_or_404(PurchaseOrder, id=po_id, is_deleted=False)
    if po.finance_approved_by:
        messages.info(request, 'This PO has already been finance-approved.')
        return redirect('inventory:po_detail', po_id=po.id)

    po.finance_approved_by = request.user
    po.finance_approved_at = timezone.now()
    po.finance_notes = request.POST.get('finance_notes', '').strip()
    if po.status == PurchaseOrderStatus.SUBMITTED:
        po.status = PurchaseOrderStatus.APPROVED
        po.approved_by = request.user
    po.save(update_fields=['finance_approved_by', 'finance_approved_at', 'finance_notes', 'status', 'approved_by'])
    messages.success(request, f'PO {po.po_number} approved by Finance. Budget gate cleared.')
    return redirect('inventory:po_detail', po_id=po.id)


@login_required
@require_POST
def po_finance_reject(request, po_id):
    """Finance Director rejects a Purchase Order."""
    if not _can_validate_stock(request.user):
        return HttpResponseForbidden('Only Finance Director can reject POs.')
    po = get_object_or_404(PurchaseOrder, id=po_id, is_deleted=False)
    po.status = PurchaseOrderStatus.CANCELLED
    po.finance_notes = request.POST.get('finance_notes', '').strip() or 'Rejected by Finance'
    po.save(update_fields=['status', 'finance_notes'])
    messages.warning(request, f'PO {po.po_number} rejected by Finance.')
    return redirect('inventory:po_detail', po_id=po.id)


# ═══════════════════════════════════════════════════════════════════════════════
# SUPPLIER INVOICE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def supplier_invoice_list(request):
    """List all supplier invoices."""
    if not _can_access_store(request.user) and not _can_manage_procurement(request.user):
        return HttpResponseForbidden('Access denied.')
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '').strip()
    invoices = SupplierInvoice.objects.filter(is_deleted=False).select_related('vendor', 'purchase_order', 'grn')
    if status_filter:
        invoices = invoices.filter(status=status_filter)
    if search:
        invoices = invoices.filter(
            Q(invoice_number__icontains=search) | Q(vendor__name__icontains=search)
        )
    return render(request, 'inventory/supplier_invoice_list.html', {
        'invoices': invoices[:200],
        'statuses': SupplierInvoiceStatus.choices,
        'filter_status': status_filter, 'search': search,
    })


@login_required
def supplier_invoice_create(request):
    """Record a new supplier invoice."""
    if not _can_manage_procurement(request.user):
        return HttpResponseForbidden('Access denied.')
    vendors = Vendor.objects.filter(is_active=True, is_deleted=False).order_by('name')
    pos     = PurchaseOrder.objects.filter(is_deleted=False, status__in=['APPROVED', 'RECEIVED']).order_by('-ordered_date')
    grns    = GoodsReceivedNote.objects.filter(is_deleted=False, status__in=['ACCEPTED', 'AWAITING_VALIDATION', 'VALIDATED']).order_by('-received_date')
    items_qs = InventoryItem.objects.filter(is_active=True, is_deleted=False).order_by('name')

    if request.method == 'POST':
        vendor = get_object_or_404(Vendor, id=request.POST.get('vendor_id', ''), is_deleted=False)
        po_id  = request.POST.get('purchase_order_id', '').strip()
        grn_id = request.POST.get('grn_id', '').strip()
        inv_number = request.POST.get('invoice_number', '').strip()
        inv_date   = request.POST.get('invoice_date', '')
        due_date   = request.POST.get('due_date', '') or None
        notes      = request.POST.get('notes', '').strip()

        if not inv_number or not inv_date:
            messages.error(request, 'Invoice number and date are required.')
            return redirect('inventory:supplier_invoice_create')

        si = SupplierInvoice.objects.create(
            invoice_number=inv_number,
            vendor=vendor,
            purchase_order_id=po_id or None,
            grn_id=grn_id or None,
            invoice_date=inv_date,
            due_date=due_date,
            total_amount=0,
            notes=notes,
            created_by=request.user,
        )

        item_ids    = request.POST.getlist('item_id[]')
        quantities  = request.POST.getlist('quantity[]')
        unit_prices = request.POST.getlist('unit_price[]')
        total = Decimal('0')
        for item_id, qty_str, price_str in zip(item_ids, quantities, unit_prices):
            if not item_id or not qty_str:
                continue
            try:
                qty   = int(qty_str)
                price = Decimal(price_str or '0')
                SupplierInvoiceItem.objects.create(
                    supplier_invoice=si, item_id=item_id,
                    quantity=qty, unit_price=price,
                )
                total += qty * price
            except (ValueError, Exception):
                continue

        si.total_amount = total
        si.save(update_fields=['total_amount'])
        messages.success(request, f'Supplier invoice {si.invoice_number} recorded ({total:,.0f} XAF).')
        return redirect('inventory:supplier_invoice_list')

    return render(request, 'inventory/supplier_invoice_form.html', {
        'vendors': vendors, 'purchase_orders': pos, 'grns': grns, 'items': items_qs,
    })


@login_required
def supplier_invoice_detail(request, invoice_id):
    """View supplier invoice detail."""
    if not _can_manage_procurement(request.user) and not _can_validate_stock(request.user):
        return HttpResponseForbidden('Access denied.')
    si = get_object_or_404(SupplierInvoice, id=invoice_id, is_deleted=False)
    si_items = si.items.select_related('item').all()
    matches = si.three_way_matches.all()
    return render(request, 'inventory/supplier_invoice_detail.html', {
        'si': si, 'si_items': si_items, 'matches': matches,
    })


@login_required
def supplier_invoice_edit(request, invoice_id):
    """Edit supplier invoice — only RECEIVED status (before matching)."""
    if not _can_manage_procurement(request.user):
        return HttpResponseForbidden('Access denied.')
    si = get_object_or_404(SupplierInvoice, id=invoice_id, is_deleted=False)
    if si.status != 'RECEIVED':
        messages.error(request, f'Cannot edit invoice {si.invoice_number} — status is {si.get_status_display()}.')
        return redirect('inventory:supplier_invoice_detail', invoice_id=si.pk)

    vendors = Vendor.objects.filter(is_active=True, is_deleted=False).order_by('name')
    pos = PurchaseOrder.objects.filter(is_deleted=False, status__in=['APPROVED', 'RECEIVED']).order_by('-ordered_date')
    grns = GoodsReceivedNote.objects.filter(is_deleted=False, status__in=['ACCEPTED', 'AWAITING_VALIDATION', 'VALIDATED']).order_by('-received_date')
    items_qs = InventoryItem.objects.filter(is_active=True, is_deleted=False).order_by('name')

    if request.method == 'POST':
        vendor_id = request.POST.get('vendor_id')
        if vendor_id:
            si.vendor = get_object_or_404(Vendor, id=vendor_id, is_deleted=False)
        si.purchase_order_id = request.POST.get('purchase_order_id', '').strip() or None
        si.grn_id = request.POST.get('grn_id', '').strip() or None
        si.invoice_number = request.POST.get('invoice_number', '').strip() or si.invoice_number
        si.invoice_date = request.POST.get('invoice_date', '') or si.invoice_date
        si.due_date = request.POST.get('due_date', '') or None
        si.notes = request.POST.get('notes', '').strip()
        si.updated_by = request.user
        si.save(update_fields=['vendor', 'purchase_order', 'grn', 'invoice_number', 'invoice_date',
                               'due_date', 'notes', 'updated_by'])

        # Replace line items
        si.items.all().delete()
        item_ids = request.POST.getlist('item_id[]')
        quantities = request.POST.getlist('quantity[]')
        unit_prices = request.POST.getlist('unit_price[]')
        total = Decimal('0')
        for item_id, qty_str, price_str in zip(item_ids, quantities, unit_prices):
            if not item_id or not qty_str:
                continue
            try:
                qty = int(qty_str)
                price = Decimal(price_str or '0')
                SupplierInvoiceItem.objects.create(
                    supplier_invoice=si, item_id=item_id,
                    quantity=qty, unit_price=price,
                )
                total += qty * price
            except (ValueError, Exception):
                continue
        si.total_amount = total
        si.save(update_fields=['total_amount'])
        messages.success(request, f'Invoice {si.invoice_number} updated.')
        return redirect('inventory:supplier_invoice_detail', invoice_id=si.pk)

    return render(request, 'inventory/supplier_invoice_form.html', {
        'vendors': vendors, 'purchase_orders': pos, 'grns': grns, 'items': items_qs,
        'si': si, 'si_items': si.items.select_related('item').all(),
        'action': 'Edit',
    })


@login_required
def supplier_invoice_delete(request, invoice_id):
    """Soft-delete supplier invoice — only before matching/payment."""
    if not _can_manage_procurement(request.user):
        return HttpResponseForbidden('Access denied.')
    si = get_object_or_404(SupplierInvoice, id=invoice_id, is_deleted=False)
    if request.method == 'POST':
        if si.status in ('MATCHED', 'PAID'):
            messages.error(request, f'Cannot delete invoice {si.invoice_number} — status is {si.get_status_display()}.')
            return redirect('inventory:supplier_invoice_detail', invoice_id=si.pk)
        reason = request.POST.get('deletion_reason', '').strip()
        if not reason:
            messages.error(request, 'A deletion reason is required.')
            return redirect('inventory:supplier_invoice_detail', invoice_id=si.pk)
        si.soft_delete(user=request.user, reason=reason)
        messages.success(request, f'Invoice {si.invoice_number} moved to recycle bin.')
        return redirect('inventory:supplier_invoice_list')
    return redirect('inventory:supplier_invoice_list')


# ═══════════════════════════════════════════════════════════════════════════════
# 3-WAY MATCH (PO vs GRN vs Supplier Invoice)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def three_way_match_list(request):
    """List all 3-way matches."""
    if not _can_access_store(request.user) and not _can_manage_procurement(request.user) and not _can_validate_stock(request.user):
        return HttpResponseForbidden('Access denied.')
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '').strip()
    matches = ThreeWayMatch.objects.filter(is_deleted=False).select_related(
        'purchase_order__vendor', 'grn', 'supplier_invoice', 'resolved_by'
    )
    if status_filter:
        matches = matches.filter(status=status_filter)
    if search:
        matches = matches.filter(
            Q(match_number__icontains=search) |
            Q(purchase_order__po_number__icontains=search) |
            Q(supplier_invoice__invoice_number__icontains=search)
        )
    return render(request, 'inventory/three_way_match_list.html', {
        'matches': matches[:200],
        'statuses': ThreeWayMatchStatus.choices,
        'filter_status': status_filter, 'search': search,
    })


@login_required
def three_way_match_create(request):
    """Create a new 3-way match by selecting PO, GRN, and Supplier Invoice."""
    if not _can_manage_procurement(request.user):
        return HttpResponseForbidden('Access denied.')

    if request.method == 'POST':
        po_id  = request.POST.get('purchase_order_id', '')
        grn_id = request.POST.get('grn_id', '')
        si_id  = request.POST.get('supplier_invoice_id', '')

        if not po_id or not grn_id or not si_id:
            messages.error(request, 'All three documents (PO, GRN, Supplier Invoice) are required.')
            return redirect('inventory:three_way_match_create')

        po  = get_object_or_404(PurchaseOrder, id=po_id, is_deleted=False)
        grn = get_object_or_404(GoodsReceivedNote, id=grn_id, is_deleted=False)
        si  = get_object_or_404(SupplierInvoice, id=si_id, is_deleted=False)

        match = ThreeWayMatch(
            purchase_order=po, grn=grn, supplier_invoice=si,
            created_by=request.user,
        )
        match.save()
        match.perform_match()

        status_msg = match.get_status_display()
        if match.status == ThreeWayMatchStatus.MATCHED:
            si.status = SupplierInvoiceStatus.MATCHED
            si.save(update_fields=['status'])
            messages.success(request, f'3-Way Match {match.match_number}: {status_msg}. All documents align.')
        else:
            messages.warning(request, f'3-Way Match {match.match_number}: {status_msg}. Review discrepancies.')
        return redirect('inventory:three_way_match_detail', match_id=match.pk)

    pos  = PurchaseOrder.objects.filter(is_deleted=False, status__in=['APPROVED', 'RECEIVED']).order_by('-ordered_date')
    grns = GoodsReceivedNote.objects.filter(is_deleted=False, status__in=['ACCEPTED', 'AWAITING_VALIDATION', 'VALIDATED']).order_by('-received_date')
    sis  = SupplierInvoice.objects.filter(is_deleted=False, status='RECEIVED').order_by('-invoice_date')

    return render(request, 'inventory/three_way_match_form.html', {
        'purchase_orders': pos, 'grns': grns, 'supplier_invoices': sis,
    })


@login_required
def three_way_match_detail(request, match_id):
    """View 3-way match result with line-by-line comparison."""
    if not _can_manage_procurement(request.user) and not _can_validate_stock(request.user):
        return HttpResponseForbidden('Access denied.')
    match = get_object_or_404(ThreeWayMatch, id=match_id, is_deleted=False)
    po_items  = match.purchase_order.items.select_related('item').all()
    grn_items = match.grn.items.select_related('po_item__item').all()
    si_items  = match.supplier_invoice.items.select_related('item').all()

    # Build comparison table
    item_map = {}
    for pi in po_items:
        item_map.setdefault(pi.item_id, {'item': pi.item, 'po_qty': 0, 'po_price': 0, 'grn_qty': 0, 'si_qty': 0, 'si_price': 0})
        item_map[pi.item_id]['po_qty'] = pi.quantity_ordered
        item_map[pi.item_id]['po_price'] = pi.unit_price
    for gi in grn_items:
        item_id = gi.po_item.item_id if gi.po_item else None
        if item_id and item_id in item_map:
            item_map[item_id]['grn_qty'] = gi.quantity_accepted
    for si in si_items:
        item_map.setdefault(si.item_id, {'item': si.item, 'po_qty': 0, 'po_price': 0, 'grn_qty': 0, 'si_qty': 0, 'si_price': 0})
        item_map[si.item_id]['si_qty'] = si.quantity
        item_map[si.item_id]['si_price'] = si.unit_price

    comparison_rows = []
    for item_id, data in item_map.items():
        qty_ok = (data['po_qty'] == data['grn_qty'] == data['si_qty'])
        price_ok = (abs(data['po_price'] - data['si_price']) <= Decimal('0.01'))
        comparison_rows.append({**data, 'qty_ok': qty_ok, 'price_ok': price_ok})

    can_resolve = _can_validate_stock(request.user) and match.status in (
        ThreeWayMatchStatus.PARTIAL, ThreeWayMatchStatus.MISMATCH
    )

    return render(request, 'inventory/three_way_match_detail.html', {
        'match': match,
        'comparison_rows': comparison_rows,
        'can_resolve': can_resolve,
    })


@login_required
@require_POST
def three_way_match_resolve(request, match_id):
    """Finance Director resolves a mismatched 3-way match."""
    if not _can_validate_stock(request.user):
        return HttpResponseForbidden('Only Finance Director can resolve match discrepancies.')
    match = get_object_or_404(ThreeWayMatch, id=match_id, is_deleted=False)
    match.status = ThreeWayMatchStatus.RESOLVED
    match.resolved_by = request.user
    match.resolved_at = timezone.now()
    match.discrepancy_notes = request.POST.get('notes', '').strip()
    match.save(update_fields=['status', 'resolved_by', 'resolved_at', 'discrepancy_notes'])
    messages.success(request, f'3-Way Match {match.match_number} resolved.')
    return redirect('inventory:three_way_match_detail', match_id=match.pk)



# ═══════════════════════════════════════════════════════════════════════════════
# AJAX ENDPOINTS — Store-Filtered Items & Operation Types
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def items_by_store_ajax(request):
    """
    GET /inventory/ajax/items-by-store/?store_id=<uuid>
    Returns JSON list of items belonging to the selected store, for cascading
    dropdown population in stock entry / exit forms.
    """
    from django.http import JsonResponse
    store_id = request.GET.get('store_id', '').strip()
    if not store_id:
        return JsonResponse({'items': [], 'store_type': ''})

    store = StoreLocation.objects.filter(pk=store_id, is_deleted=False, is_active=True).first()
    if not store:
        return JsonResponse({'items': [], 'store_type': ''})

    items = InventoryItem.objects.filter(
        store_location=store, is_active=True, is_deleted=False
    ).order_by('name').values('id', 'item_code', 'name', 'unit', 'unit_cost', 'current_stock')

    return JsonResponse({
        'store_type': store.location_type,
        'gl_account': store.gl_account_code,
        'items': [
            {
                'id': str(i['id']),
                'item_code': i['item_code'],
                'name': i['name'],
                'unit': i['unit'],
                'unit_cost': float(i['unit_cost'] or 0),
                'current_stock': i['current_stock'],
                'label': f"{i['item_code']} \u2014 {i['name']} ({i['unit']})",
            }
            for i in items
        ],
    })


@login_required
def op_types_by_store_ajax(request):
    """
    GET /inventory/ajax/op-types-by-store/?store_id=<uuid>&category=ENTRY
    Returns JSON list of StockOperationType records applicable to the store's
    location_type. Blank location_types on an op type means it applies to all.
    """
    from django.http import JsonResponse
    from apps.billing.models import StockOperationType
    store_id = request.GET.get('store_id', '').strip()
    category = request.GET.get('category', 'ENTRY').upper()

    store_type = ''
    if store_id:
        store = StoreLocation.objects.filter(pk=store_id, is_deleted=False, is_active=True).first()
        if store:
            store_type = store.location_type

    qs = StockOperationType.objects.filter(
        category=category, is_active=True, is_deleted=False
    ).select_related('debit_account', 'credit_account').order_by('code')

    result = []
    for op in qs:
        # If location_types blank → all stores; otherwise only if store_type matches
        if not op.location_types or (store_type and op.applies_to_store_type(store_type)):
            result.append({
                'id': str(op.id),
                'code': op.code,
                'name': op.name,
                'dr_code': op.debit_account.code if op.debit_account else '',
                'cr_code': op.credit_account.code if op.credit_account else '',
                'label': f"{op.code} \u2014 {op.name}",
            })

    return JsonResponse({'op_types': result, 'store_type': store_type})
