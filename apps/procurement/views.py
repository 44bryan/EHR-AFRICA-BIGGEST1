"""
Procurement Module Views
Purchase Requests, Purchase Orders, and Goods Received Notes.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from apps.accounts.models import UserRole
from .models import (
    PurchaseRequest, PurchaseRequestItem, PurchaseOrder, POItem,
    GoodsReceivedNote, GRNItem, PRStatus, POStatus, PurchaseCategory,
)


def _can_manage(user):
    return user.is_superuser or user.role in (
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR, UserRole.FINANCE_DIRECTOR,
        UserRole.SENIOR_ACCOUNTANT, UserRole.ACCOUNTANT,
    )


def _can_approve_pr(user):
    return user.is_superuser or user.role in (
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR, UserRole.FINANCE_DIRECTOR,
    )


def _can_create_po(user):
    return user.is_superuser or user.role in (
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR, UserRole.FINANCE_DIRECTOR,
        UserRole.SENIOR_ACCOUNTANT,
    )


def _can_receive(user):
    return user.is_superuser or user.role in (
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR, UserRole.FINANCE_DIRECTOR,
        UserRole.SENIOR_ACCOUNTANT, UserRole.ACCOUNTANT,
    )


# ── Dashboard ─────────────────────────────────────────────────────────────────
@login_required
def dashboard(request):
    if not _can_manage(request.user) and not request.user.is_authenticated:
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    pending_prs = PurchaseRequest.objects.filter(status=PRStatus.PENDING).count()
    open_pos = PurchaseOrder.objects.filter(status__in=[POStatus.DRAFT, POStatus.SENT, POStatus.PARTIAL]).count()
    recent_prs = PurchaseRequest.objects.order_by('-created_at')[:10]
    return render(request, 'procurement/dashboard.html', {
        'pending_prs': pending_prs,
        'open_pos': open_pos,
        'recent_prs': recent_prs,
    })


# ── Purchase Requests ─────────────────────────────────────────────────────────
@login_required
def pr_list(request):
    status_filter = request.GET.get('status', '')
    prs = PurchaseRequest.objects.select_related('requested_by', 'department').order_by('-created_at')
    # Non-managers only see their own PRs
    if not _can_manage(request.user):
        prs = prs.filter(requested_by=request.user)
    if status_filter:
        prs = prs.filter(status=status_filter)
    return render(request, 'procurement/pr_list.html', {
        'prs': prs,
        'status_filter': status_filter,
        'pr_statuses': PRStatus.choices,
    })


@login_required
def pr_create(request):
    from apps.departments.models import Department
    departments = Department.objects.filter(is_active=True).order_by('name')
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        dept_id = request.POST.get('department_id') or None
        category = request.POST.get('category')
        urgency = request.POST.get('urgency', 'NORMAL')
        justification = request.POST.get('justification', '').strip()
        required_by = request.POST.get('required_by_date') or None
        if not title:
            messages.error(request, 'Title is required.')
        else:
            pr = PurchaseRequest.objects.create(
                title=title,
                department_id=dept_id,
                category=category,
                urgency=urgency,
                justification=justification,
                required_by_date=required_by,
                requested_by=request.user,
            )
            messages.success(request, f'PR {pr.pr_number} created. Add items below.')
            return redirect('procurement:pr_detail', pr_id=pr.pk)
    return render(request, 'procurement/pr_form.html', {
        'departments': departments,
        'categories': PurchaseCategory.choices,
    })


@login_required
def pr_detail(request, pr_id):
    pr = get_object_or_404(PurchaseRequest, pk=pr_id)
    if not _can_manage(request.user) and pr.requested_by != request.user:
        messages.error(request, 'Access denied.')
        return redirect('procurement:pr_list')
    items = pr.items.order_by('id')
    can_edit = pr.status in (PRStatus.DRAFT, PRStatus.PENDING) and (
        pr.requested_by == request.user or _can_manage(request.user)
    )
    return render(request, 'procurement/pr_detail.html', {
        'pr': pr,
        'items': items,
        'can_edit': can_edit,
        'can_approve': _can_approve_pr(request.user),
    })


@login_required
def pr_add_item(request, pr_id):
    pr = get_object_or_404(PurchaseRequest, pk=pr_id)
    if request.method == 'POST':
        desc = request.POST.get('description', '').strip()
        qty = request.POST.get('quantity', '1')
        unit = request.POST.get('unit', 'pcs').strip()
        price = request.POST.get('estimated_unit_price', '0')
        spec = request.POST.get('specification', '').strip()
        if desc:
            PurchaseRequestItem.objects.create(
                request=pr, description=desc, quantity=qty,
                unit=unit, estimated_unit_price=price, specification=spec
            )
            # Update estimated total
            from django.db.models import Sum
            from decimal import Decimal
            total = sum(i.estimated_subtotal for i in pr.items.all())
            pr.estimated_total = total
            pr.save()
    return redirect('procurement:pr_detail', pr_id=pr_id)


@login_required
def pr_submit(request, pr_id):
    pr = get_object_or_404(PurchaseRequest, pk=pr_id)
    if pr.requested_by != request.user and not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('procurement:pr_list')
    if request.method == 'POST' and pr.status == PRStatus.DRAFT:
        if not pr.items.exists():
            messages.error(request, 'Add at least one item before submitting.')
        else:
            pr.status = PRStatus.PENDING
            pr.save()
            messages.success(request, f'{pr.pr_number} submitted for approval.')
    return redirect('procurement:pr_detail', pr_id=pr_id)


@login_required
def pr_approve(request, pr_id):
    if not _can_approve_pr(request.user):
        messages.error(request, 'Only Admin/Finance Director can approve PRs.')
        return redirect('procurement:pr_list')
    pr = get_object_or_404(PurchaseRequest, pk=pr_id)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve' and pr.status == PRStatus.PENDING:
            pr.status = PRStatus.APPROVED
            pr.approved_by = request.user
            pr.approved_at = timezone.now()
            pr.save()
            messages.success(request, f'{pr.pr_number} approved.')
        elif action == 'reject':
            pr.status = PRStatus.REJECTED
            pr.notes = request.POST.get('notes', pr.notes)
            pr.save()
            messages.warning(request, f'{pr.pr_number} rejected.')
    return redirect('procurement:pr_detail', pr_id=pr_id)


# ── Purchase Orders ───────────────────────────────────────────────────────────
@login_required
def po_list(request):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    status_filter = request.GET.get('status', '')
    pos = PurchaseOrder.objects.select_related('vendor', 'purchase_request').order_by('-created_at')
    if status_filter:
        pos = pos.filter(status=status_filter)
    return render(request, 'procurement/po_list.html', {
        'pos': pos,
        'status_filter': status_filter,
        'po_statuses': POStatus.choices,
    })


@login_required
def po_create(request):
    if not _can_create_po(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from apps.billing.models import APVendor
    vendors = APVendor.objects.filter(is_deleted=False).order_by('name')
    approved_prs = PurchaseRequest.objects.filter(status=PRStatus.APPROVED).order_by('-created_at')
    if request.method == 'POST':
        vendor_id = request.POST.get('vendor_id')
        pr_id = request.POST.get('pr_id') or None
        expected_delivery = request.POST.get('expected_delivery_date') or None
        notes = request.POST.get('notes', '').strip()
        terms = request.POST.get('terms', '').strip()
        po = PurchaseOrder.objects.create(
            vendor_id=vendor_id,
            purchase_request_id=pr_id,
            created_by=request.user,
            expected_delivery_date=expected_delivery,
            notes=notes,
            terms=terms or 'Payment within 30 days of delivery.',
        )
        if pr_id:
            pr = PurchaseRequest.objects.get(pk=pr_id)
            for item in pr.items.all():
                POItem.objects.create(
                    purchase_order=po,
                    description=item.description,
                    quantity_ordered=item.quantity,
                    unit=item.unit,
                    unit_price=item.estimated_unit_price,
                    pr_item=item,
                )
            pr.status = PRStatus.ORDERED
            pr.save()
            _update_po_total(po)
        messages.success(request, f'PO {po.po_number} created.')
        return redirect('procurement:po_detail', po_id=po.pk)
    return render(request, 'procurement/po_form.html', {
        'vendors': vendors,
        'approved_prs': approved_prs,
    })


def _update_po_total(po):
    from django.db.models import Sum
    from decimal import Decimal
    total = sum(item.subtotal for item in po.items.all())
    po.total_amount = total
    po.save()


@login_required
def po_detail(request, po_id):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    po = get_object_or_404(PurchaseOrder, pk=po_id)
    items = po.items.order_by('id')
    grns = po.grns.select_related('received_by').order_by('-received_date')
    return render(request, 'procurement/po_detail.html', {
        'po': po,
        'items': items,
        'grns': grns,
        'can_create_po': _can_create_po(request.user),
        'can_receive': _can_receive(request.user),
    })


@login_required
def po_add_item(request, po_id):
    if not _can_create_po(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    po = get_object_or_404(PurchaseOrder, pk=po_id)
    if request.method == 'POST' and po.status in (POStatus.DRAFT,):
        desc = request.POST.get('description', '').strip()
        qty = request.POST.get('quantity_ordered', '1')
        unit = request.POST.get('unit', 'pcs')
        price = request.POST.get('unit_price', '0')
        if desc:
            POItem.objects.create(
                purchase_order=po, description=desc,
                quantity_ordered=qty, unit=unit, unit_price=price
            )
            _update_po_total(po)
    return redirect('procurement:po_detail', po_id=po_id)


@login_required
def po_send(request, po_id):
    if not _can_create_po(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    po = get_object_or_404(PurchaseOrder, pk=po_id)
    if request.method == 'POST' and po.status == POStatus.DRAFT:
        po.status = POStatus.SENT
        po.sent_at = timezone.now()
        po.save()
        messages.success(request, f'{po.po_number} marked as sent to vendor.')
    return redirect('procurement:po_detail', po_id=po_id)


# ── Goods Received Notes ──────────────────────────────────────────────────────
@login_required
def grn_create(request, po_id):
    if not _can_receive(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    po = get_object_or_404(PurchaseOrder, pk=po_id)
    items = po.items.all()
    if request.method == 'POST':
        delivery_ref = request.POST.get('delivery_note_ref', '').strip()
        received_date = request.POST.get('received_date') or timezone.now().date()
        notes = request.POST.get('notes', '').strip()
        with transaction.atomic():
            grn = GoodsReceivedNote.objects.create(
                purchase_order=po,
                received_by=request.user,
                received_date=received_date,
                delivery_note_ref=delivery_ref,
                notes=notes,
            )
            all_received = True
            for item in items:
                qty_key = f'qty_{item.pk}'
                qty = request.POST.get(qty_key)
                if qty and float(qty) > 0:
                    condition = request.POST.get(f'cond_{item.pk}', 'GOOD')
                    GRNItem.objects.create(
                        grn=grn, po_item=item,
                        quantity_received=qty, condition=condition
                    )
                    item.quantity_received += float(qty)
                    item.save()
                if item.remaining > 0:
                    all_received = False
            if all_received:
                po.status = POStatus.RECEIVED
            else:
                po.status = POStatus.PARTIAL
            po.save()
        messages.success(request, f'GRN {grn.grn_number} recorded.')
        return redirect('procurement:po_detail', po_id=po_id)
    return render(request, 'procurement/grn_form.html', {
        'po': po,
        'items': items,
    })
