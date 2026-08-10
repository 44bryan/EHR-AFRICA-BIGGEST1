from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import (Invoice, InvoiceItem, Payment, InvoiceStatus, ServiceCategory,
                     PaymentMethod, ServicePrice, Refund, CashierShift, ShiftStatus,
                     ServiceWorkOrder, WorkOrderStatus, Budget, BudgetType)
from .utils import get_or_create_today_invoice
from apps.patients.models import Patient
from apps.accounts.models import UserRole
from apps.core.context_processors import qms_active as _qms_active
from apps.core.decorators import json_error_handler

# ── Desk tier groupings ───────────────────────────────────────────────────────
# Maps a desk's primary tier to ALL tiers it handles (some desks share patients).
# Update this dict when physical desk assignments change — no migration needed.
DESK_TIER_GROUPS = {
    # The Express/FT desk handles both EXPRESS and FAST_TRACK patients —
    # there is no separate "EXPRESS" desk tier (CashDesk.tier only has STANDARD/FAST_TRACK/VIP).
    'FAST_TRACK': ['FAST_TRACK', 'EXPRESS'],
}
# ─────────────────────────────────────────────────────────────────────────────


# ── Finance role helpers ──────────────────────────────────────────────────────
# Segregation of duties — international hospital finance standard:
#   CASHIER          → collects money only, cannot cancel or refund
#   CHIEF_CASHIER    → supervises cashiers, verifies shifts, cannot cancel invoices
#   ACCOUNTANT       → cancels invoices, processes refunds, AR, corporate accounts
#   SENIOR_ACCOUNTANT→ everything accountant + approve expenses, petty cash, budget
#   FINANCE_DIRECTOR → full access including P&L, waivers, strategic reports

def _can_cancel_invoice(user):
    """Cancel / void invoices — ACCOUNTING OFFICE only. Cashiers and billing officers cannot."""
    return user.role in (
        UserRole.ACCOUNTANT,
        UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR,
        UserRole.MEDICAL_DIRECTOR,
        UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_authorize_billing(user):
    """Alias for cancel/refund authority — used throughout views."""
    return _can_cancel_invoice(user)


def _can_process_refund(user):
    """Refunds — Accountants and above only. Billing officers cannot."""
    return user.role in (
        UserRole.ACCOUNTANT,
        UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR,
        UserRole.MEDICAL_DIRECTOR,
        UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_verify_shift(user):
    """Verify cashier shift handover — Chief Cashier and above."""
    return user.role in (
        UserRole.CHIEF_CASHIER,
        UserRole.BILLING_OFFICER,
        UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR,
        UserRole.MEDICAL_DIRECTOR,
        UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_open_day(user):
    """Open the working day for all cashiers — Chief Cashier, Senior Accountant, Finance Director."""
    return user.role in (
        UserRole.CHIEF_CASHIER,
        UserRole.SENIOR_ACCOUNTANT,
        UserRole.BILLING_OFFICER,
        UserRole.FINANCE_DIRECTOR,
        UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_waive(user):
    """Invoice waivers — Finance Director only (full write-off authority)."""
    return user.role in (
        UserRole.FINANCE_DIRECTOR,
        UserRole.MEDICAL_DIRECTOR,
        UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_view_financial_reports(user):
    """Operational financial reports — Chief Cashier, Accountants and above."""
    return user.role in (
        UserRole.CHIEF_CASHIER,
        UserRole.ACCOUNTANT,
        UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR,
        UserRole.BILLING_OFFICER,
        UserRole.MEDICAL_DIRECTOR,
        UserRole.CEO,
        UserRole.ADMIN_DIRECTOR,
        UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_view_pl(user):
    """P&L and strategic financial reports — Finance Director and above only."""
    return user.role in (
        UserRole.FINANCE_DIRECTOR,
        UserRole.CEO,
        UserRole.ADMIN_DIRECTOR,
        UserRole.MEDICAL_DIRECTOR,
        UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_record_expense(user):
    """Submit expenses for approval — Accountants and above. IT Admin role excluded."""
    return user.role in (
        UserRole.ACCOUNTANT,
        UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR,
        UserRole.ADMIN_DIRECTOR,
        UserRole.MEDICAL_DIRECTOR,
        UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_approve_expense(user):
    """Approve / reject expenses — Senior Accountant and above only."""
    return user.role in (
        UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR,
        UserRole.MEDICAL_DIRECTOR,
        UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_manage_petty_cash(user):
    """Petty cash management — Senior Accountant and above."""
    return user.role in (
        UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR,
        UserRole.BILLING_OFFICER,
        UserRole.ADMIN_DIRECTOR,
        UserRole.SUPER_ADMIN,
    ) or user.is_superuser


@login_required
def billing_dashboard(request):
    if not (request.user.is_super_admin or request.user.role in (
        UserRole.CASHIER, UserRole.CHIEF_CASHIER, UserRole.BILLING_OFFICER,
        UserRole.ACCOUNTANT, UserRole.SENIOR_ACCOUNTANT, UserRole.FINANCE_DIRECTOR,
        UserRole.MEDICAL_DIRECTOR, UserRole.CEO, UserRole.ADMIN_DIRECTOR,
        UserRole.ADMIN,
    ) or request.user.is_superuser):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from django.db.models import Count
    today = timezone.localdate()
    month_start = today.replace(day=1)

    # Revenue — gross payments minus refunds for accurate net figures
    gross_today = Payment.objects.filter(
        payment_date__date=today, is_deleted=False
    ).aggregate(total=Sum('amount'))['total'] or 0
    refunds_today_amt = Refund.objects.filter(
        refund_date__date=today, is_deleted=False
    ).aggregate(total=Sum('amount'))['total'] or 0
    paid_today = max(0, float(gross_today) - float(refunds_today_amt))

    gross_month = Payment.objects.filter(
        payment_date__date__gte=month_start, is_deleted=False
    ).aggregate(total=Sum('amount'))['total'] or 0
    refunds_month_amt = Refund.objects.filter(
        refund_date__date__gte=month_start, is_deleted=False
    ).aggregate(total=Sum('amount'))['total'] or 0
    paid_month = max(0, float(gross_month) - float(refunds_month_amt))

    # By payment method today
    by_method = Payment.objects.filter(
        payment_date__date=today, is_deleted=False
    ).values('payment_method').annotate(total=Sum('amount')).order_by('-total')

    # Outstanding — total is a Python property so aggregate via items
    outstanding_qs = Invoice.objects.filter(
        status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
        is_deleted=False
    )
    outstanding_count = outstanding_qs.count()
    from django.db.models import F, ExpressionWrapper, DecimalField as DField
    outstanding_items_total = InvoiceItem.objects.filter(
        invoice__in=outstanding_qs,
        is_deleted=False,
    ).aggregate(
        s=Sum(ExpressionWrapper(F('unit_price') * F('quantity'), output_field=DField(max_digits=14, decimal_places=2)))
    )['s'] or 0
    discount_total = outstanding_qs.aggregate(d=Sum('discount_amount'))['d'] or 0
    outstanding_amount = max(0, outstanding_items_total - discount_total)

    # Invoice stats today
    invoices_today = Invoice.objects.filter(
        created_at__date=today, is_deleted=False
    ).count()

    # Recent invoices
    from django.db.models import Prefetch as _Pf
    recent_invoices = Invoice.objects.filter(
        is_deleted=False
    ).select_related('patient').prefetch_related(
        _Pf('items', queryset=InvoiceItem.objects.filter(is_deleted=False), to_attr='_items_cache'),
        _Pf('payments', queryset=Payment.objects.filter(is_deleted=False), to_attr='_payments_cache'),
        _Pf('refunds', queryset=Refund.objects.filter(is_deleted=False), to_attr='_refunds_cache'),
    ).order_by('-created_at')[:15]

    # Revenue last 7 days for sparkline
    from datetime import timedelta
    seven_days = []
    seven_labels = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        rev = Payment.objects.filter(
            payment_date__date=d, is_deleted=False
        ).aggregate(t=Sum('amount'))['t'] or 0
        seven_days.append(float(rev))
        seven_labels.append(d.strftime('%d %b'))

    # Revenue by service category this month
    from django.db.models import ExpressionWrapper, F, DecimalField as DField2
    cat_rev = InvoiceItem.objects.filter(
        is_deleted=False,
        invoice__is_deleted=False,
        invoice__created_at__date__gte=month_start,
    ).values('category').annotate(
        total=Sum(ExpressionWrapper(F('unit_price') * F('quantity'), output_field=DField2(max_digits=14, decimal_places=2)))
    ).order_by('-total')
    cat_labels = [c['category'] for c in cat_rev]
    cat_values = [float(c['total']) for c in cat_rev]

    # Invoice status breakdown (all time)
    status_counts = Invoice.objects.filter(is_deleted=False).values('status').annotate(count=Count('status'))
    status_labels = [s['status'] for s in status_counts]
    status_values = [s['count'] for s in status_counts]

    # 12-month revenue trend
    twelve_labels = []
    twelve_values = []
    for i in range(11, -1, -1):
        mo = today.month - i
        yr = today.year
        while mo <= 0:
            mo += 12
            yr -= 1
        import calendar
        _, last_day = calendar.monthrange(yr, mo)
        mo_start = today.replace(year=yr, month=mo, day=1)
        mo_end = today.replace(year=yr, month=mo, day=last_day)
        rev = Payment.objects.filter(
            payment_date__date__gte=mo_start, payment_date__date__lte=mo_end, is_deleted=False
        ).aggregate(t=Sum('amount'))['t'] or 0
        twelve_labels.append(mo_start.strftime('%b %Y'))
        twelve_values.append(float(rev))

    context = {
        'today': today,
        'paid_today': paid_today,
        'paid_month': paid_month,
        'outstanding_count': outstanding_count,
        'outstanding_amount': outstanding_amount,
        'invoices_today': invoices_today,
        'by_method': list(by_method),
        'recent_invoices': recent_invoices,
        'seven_days': seven_days,
        'seven_labels': seven_labels,
        'cat_labels': cat_labels,
        'cat_values': cat_values,
        'status_labels': status_labels,
        'status_values': status_values,
        'twelve_labels': twelve_labels,
        'twelve_values': twelve_values,
        'payment_methods': PaymentMethod.choices,
        'statuses': InvoiceStatus.choices,
    }
    return render(request, 'billing/dashboard.html', context)


@login_required
def invoice_list(request):
    if not (request.user.is_super_admin or request.user.role in (
        UserRole.CASHIER, UserRole.CHIEF_CASHIER, UserRole.BILLING_OFFICER,
        UserRole.ACCOUNTANT, UserRole.SENIOR_ACCOUNTANT, UserRole.FINANCE_DIRECTOR,
        UserRole.MEDICAL_DIRECTOR, UserRole.CEO, UserRole.ADMIN_DIRECTOR,
        UserRole.ADMIN,
    ) or request.user.is_superuser):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from django.core.paginator import Paginator
    q = request.GET.get('q', '')
    status = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    from django.contrib.auth import get_user_model
    User = get_user_model()

    cashier_filter = request.GET.get('cashier', '')

    from django.db.models import Count as _Count
    invoices = (
        Invoice.objects
        .filter(is_deleted=False)
        .select_related('patient', 'created_by')
        .annotate(_item_count=_Count('items'))
        # Hide empty DRAFT invoices — these are abandoned POS sessions, not real invoices
        .exclude(status=InvoiceStatus.DRAFT, _item_count=0)
    )

    # Cashiers see ONLY their own invoices — oversight roles see all
    if request.user.role == UserRole.CASHIER and not request.user.is_superuser:
        invoices = invoices.filter(created_by=request.user)

    if q:
        from apps.core.utils import patient_search_q
        invoices = invoices.filter(
            Q(invoice_number__icontains=q) | patient_search_q(q, prefix='patient__')
        )
    if status:
        invoices = invoices.filter(status=status)
    if date_from:
        invoices = invoices.filter(issue_date__gte=date_from)
    if date_to:
        invoices = invoices.filter(issue_date__lte=date_to)
    if cashier_filter:
        invoices = invoices.filter(created_by_id=cashier_filter)

    invoices = invoices.order_by('-created_at')
    paginator = Paginator(invoices, 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Build cashier list for the filter dropdown (billing staff who have created invoices)
    _billing_roles = (
        UserRole.CASHIER, UserRole.CHIEF_CASHIER, UserRole.BILLING_OFFICER,
        UserRole.ACCOUNTANT, UserRole.SENIOR_ACCOUNTANT, UserRole.FINANCE_DIRECTOR,
    )
    cashiers = User.objects.filter(role__in=_billing_roles, is_active=True).order_by('first_name', 'last_name')

    return render(request, 'billing/invoice_list.html', {
        'page_obj': page_obj,
        'paginator': paginator,
        'search': q,
        'status': status,
        'date_from': date_from,
        'date_to': date_to,
        'cashier_filter': cashier_filter,
        'cashiers': cashiers,
        'statuses': InvoiceStatus.choices,
    })


@login_required
def invoice_detail(request, invoice_id):
    from .models import InvoiceVoidReason
    invoice = get_object_or_404(Invoice, id=invoice_id, is_deleted=False)
    return render(request, 'billing/invoice_detail.html', {
        'invoice': invoice,
        'payment_methods': PaymentMethod.choices,
        'void_reasons': InvoiceVoidReason.objects.filter(is_active=True, is_deleted=False),
        'today': timezone.localdate(),
    })


@login_required
def invoice_create(request):
    # Accountants/senior accountants audit invoices — they must not create them (SoD)
    if request.user.role in (UserRole.ACCOUNTANT, UserRole.SENIOR_ACCOUNTANT):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    # GET with ?patient=<UUID or patient_id> — direct link from dashboard "Bill" button
    if request.method == 'GET':
        patient_ref = request.GET.get('patient', '').strip()
        if patient_ref:
            try:
                # Try UUID pk first (dashboard passes patient.pk)
                import uuid as _uuid
                _uuid.UUID(patient_ref)
                p = Patient.objects.filter(pk=patient_ref, is_deleted=False).first()
            except ValueError:
                # Fall back to patient_id string
                p = Patient.objects.filter(patient_id=patient_ref, is_deleted=False).first()
            if p:
                return redirect('billing:patient_pos', patient_id=p.patient_id)

    # Resolve active desk session → drives default tier for this invoice
    _inv_session = _get_active_cashier_session(request.user)
    _session_tier = (
        _inv_session.cash_desk.tier
        if _inv_session and _inv_session.cash_desk.desk_type == 'TIER' and _inv_session.cash_desk.tier
        else ''
    )

    if request.method == 'POST':
        patient_id = request.POST.get('patient_id')
        patient = get_object_or_404(Patient, patient_id=patient_id)
        invoice = Invoice.objects.create(
            patient=patient,
            due_date=request.POST.get('due_date') or None,
            discount_amount=request.POST.get('discount_amount') or 0,
            discount_reason=request.POST.get('discount_reason', ''),
            notes=request.POST.get('notes', ''),
            status=InvoiceStatus.DRAFT,
            service_tier=request.POST.get('service_tier', _session_tier),
            cash_desk=_inv_session.cash_desk if _inv_session else None,
            created_by=request.user,
        )
        descriptions = request.POST.getlist('description')
        categories = request.POST.getlist('category')
        quantities = request.POST.getlist('quantity')
        prices = request.POST.getlist('unit_price')
        for desc, cat, qty, price in zip(descriptions, categories, quantities, prices):
            if desc.strip() and price:
                InvoiceItem.objects.create(
                    invoice=invoice,
                    description=desc,
                    category=cat,
                    quantity=int(qty) if qty else 1,
                    unit_price=price,
                    created_by=request.user,
                )
        invoice.status = InvoiceStatus.ISSUED
        invoice.save()
        messages.success(request, f'Invoice {invoice.invoice_number} created.')
        return redirect('billing:invoice_detail', invoice_id=invoice.id)
    return render(request, 'billing/invoice_form.html', {
        'categories': ServiceCategory.choices,
        'service_catalog': _get_service_catalog(cashier_station='ALL'),
        'session_tier': _session_tier,
        'active_session': _inv_session,
    })


def _sync_surgical_deposit(invoice):
    """
    If this invoice is the linked invoice of a SurgicalBooking, keep
    booking.deposit_paid in sync with the total amount received on the invoice.
    """
    try:
        booking = invoice.surgical_booking  # reverse OneToOne from ipd.SurgicalBooking
        booking.deposit_paid = invoice.amount_paid
        booking.save(update_fields=['deposit_paid', 'updated_at'])
    except Exception:
        pass


@login_required
def add_payment(request, invoice_id):
    if not (request.user.is_cashier or _can_cancel_invoice(request.user)):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Only billing staff can record payments.')
    invoice = get_object_or_404(Invoice, id=invoice_id, is_deleted=False)
    if request.method == 'POST':
        # Block payment if cashier has no open shift today
        if request.user.role == 'cashier':
            today = timezone.localdate()
            open_shift = CashierShift.objects.filter(
                cashier=request.user, shift_date=today,
                status=ShiftStatus.OPEN, is_deleted=False
            ).first()
            if not open_shift:
                messages.error(
                    request,
                    'You cannot collect payments — your shift for today is not open. '
                    'Ask the Chief Cashier to open the working day first.'
                )
                return redirect('billing:invoice_detail', invoice_id=invoice.id)

        amount = request.POST.get('amount', '').strip()
        if not amount:
            messages.error(request, 'Amount is required.')
            return redirect('billing:invoice_detail', invoice_id=invoice.id)
        try:
            amount = Decimal(amount)
            if amount <= 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            messages.error(request, 'Enter a valid positive amount.')
            return redirect('billing:invoice_detail', invoice_id=invoice.id)
        Payment.objects.create(
            invoice=invoice,
            payment_method=request.POST.get('payment_method', ''),
            amount=amount,
            reference=request.POST.get('reference', ''),
            notes=request.POST.get('notes', ''),
            received_by=request.user,
            created_by=request.user,
            cashier_session=_get_active_cashier_session(request.user),
        )
        from apps.accounts.models import UserAuditLog
        _log_financial(request, UserAuditLog.Action.CREATE_RECORD, invoice,
                       extra={'payment': amount, 'method': request.POST.get('payment_method', '')})
        # Open the 15-day consultation window for this patient's current visit
        # if the invoice contains a CONSULT or REG item (first-time payment)
        _try_open_consultation_window(invoice)
        invoice.refresh_from_db()
        _sync_surgical_deposit(invoice)
        # ── Route patient after full payment (same logic as patient_finalize) ──
        if invoice.balance_due <= 0 and invoice.patient:
            _route_patient_after_payment(invoice, request)
            messages.success(request, 'Payment recorded. Patient routed to triage.')
            return redirect('billing:receipt', invoice_id=invoice.id)
        messages.success(request, f'Payment of {amount} FCFA recorded.')
        return redirect('billing:invoice_detail', invoice_id=invoice.id)
    return redirect('billing:invoice_detail', invoice_id=invoice.id)


def _route_patient_after_payment(invoice, request):
    """
    Shared helper: after an invoice is fully paid, create/update a Visit and
    route the patient through the QMS (complete cashier token → create triage token).
    Called from add_payment AND patient_finalize so ALL billing paths produce the
    same outcome.
    """
    from django.db import transaction
    from apps.patients.models import Visit, VisitStatus, VisitType

    patient = invoice.patient
    today = timezone.localdate()

    try:
        with transaction.atomic():
            visit = Visit.objects.filter(
                patient=patient, visit_date__date=today, is_deleted=False,
            ).first()
            if not visit:
                has_prior = Visit.objects.filter(patient=patient, is_deleted=False).exists()
                visit = Visit.objects.create(
                    patient=patient,
                    visit_type=VisitType.FOLLOW_UP if has_prior else VisitType.NEW,
                    chief_complaint='',
                    status=VisitStatus.PARAMETERS,
                    created_by=request.user,
                )
            else:
                visit.status = VisitStatus.PARAMETERS
                visit.save(update_fields=['status', 'updated_at'])

            # QMS routing — best-effort, never blocks payment confirmation
            if _qms_active():
                from apps.qms.models import (
                    QueueToken, DailyTokenSequence,
                    ServiceType, ServiceTier, TokenStatus, IssuancePoint, TIER_PRIORITY,
                )
                cashier_token = (
                    QueueToken.objects
                    .filter(
                        patient=patient,
                        token_date=today,
                        service_type=ServiceType.CASHIER,
                        is_deleted=False,
                    )
                    .exclude(status__in=[TokenStatus.COMPLETED, TokenStatus.CANCELLED])
                    .order_by('-issued_at')
                    .first()
                )
                if cashier_token:
                    cashier_token.complete()
                    if cashier_token.counter:
                        cashier_token.counter.current_serving = None
                        cashier_token.counter.save(update_fields=['current_serving', 'updated_at'])
                    triage_stype = (
                        ServiceType.PARAMETERS
                        if cashier_token.service_tier == ServiceTier.STANDARD
                        else ServiceType.PARAMETERS_VIP
                    )
                    triage_num = DailyTokenSequence.next_dept_token(triage_stype)
                    QueueToken.objects.create(
                        token_number=triage_num,
                        token_date=today,
                        patient=patient,
                        visit=visit,
                        patient_name=patient.full_name,
                        service_type=triage_stype,
                        service_tier=cashier_token.service_tier,
                        issuance_point=IssuancePoint.SYSTEM,
                        priority=TIER_PRIORITY.get(cashier_token.service_tier, 0),
                        entry_token=cashier_token.entry_token or cashier_token,
                        issued_by=request.user,
                        notes='Auto-routed after payment',
                    )
    except Exception:
        pass  # never block payment over routing errors


def _try_open_consultation_window(invoice):
    """
    After a CONSULT or REG payment, open the 15-day consultation window
    on the patient's most recent active visit (if not already set).
    """
    try:
        has_consult_item = invoice.items.filter(
            category__in=['CONSULT', 'REG'], is_deleted=False
        ).exists()
        if not has_consult_item:
            return
        from apps.patients.models import Visit
        visit = (
            Visit.objects
            .filter(patient=invoice.patient, is_deleted=False)
            .order_by('-visit_date')
            .first()
        )
        if visit and not visit.consultation_valid_until:
            visit.mark_consultation_paid()
            # After payment → move to PARAMETERS (triage), not directly to doctor.
            # Triage nurse records vitals, then routes to the correct department.
            if visit.status == 'AT_CASHIER':
                visit.status = 'PARAMETERS'
                visit.save(update_fields=['status', 'updated_at'])
    except Exception:
        pass


@login_required
def cancel_invoice(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id, is_deleted=False)
    if request.method == 'POST':
        if not _can_authorize_billing(request.user):
            messages.error(
                request,
                'Access denied. Only Billing Officers, Finance Director, or Super Admin '
                'can cancel invoices.'
            )
            return redirect('billing:invoice_detail', invoice_id=invoice.id)

        # Require a void reason
        from .models import InvoiceVoidReason
        reason_id = request.POST.get('void_reason_id', '').strip()
        void_reason = None
        if reason_id:
            void_reason = InvoiceVoidReason.objects.filter(id=reason_id, is_active=True).first()
        if not void_reason:
            messages.error(request, 'A cancellation reason is required.')
            return redirect('billing:invoice_detail', invoice_id=invoice.id)

        invoice.status = InvoiceStatus.CANCELLED
        invoice.void_reason = void_reason
        invoice.notes = (
            f"{invoice.notes}\n[CANCELLED by {request.user.get_full_name()} on "
            f"{timezone.now().strftime('%d/%m/%Y %H:%M')} — Reason: {void_reason.label}]"
        ).strip()
        invoice.save(update_fields=['status', 'void_reason', 'notes', 'updated_at'])
        messages.warning(
            request,
            f'Invoice {invoice.invoice_number} cancelled. Reason: {void_reason.label}'
        )
    return redirect('billing:invoice_detail', invoice_id=invoice.id)


@login_required
@require_POST
def void_draft_invoice(request, invoice_id):
    """
    Cashier-accessible: discard an empty DRAFT invoice that was auto-created
    when the POS was opened but no items were added.
    Only works on DRAFT invoices with zero items.
    """
    invoice = get_object_or_404(Invoice, id=invoice_id, is_deleted=False)

    # Security: only the creator or billing management can discard
    if invoice.created_by != request.user and not _can_authorize_billing(request.user):
        messages.error(request, 'You can only discard your own draft invoices.')
        return redirect('billing:invoice_list')

    if invoice.status != InvoiceStatus.DRAFT:
        messages.error(request, 'Only DRAFT invoices with no items can be discarded.')
        return redirect('billing:invoice_detail', invoice_id=invoice.id)

    if invoice.items.filter(is_deleted=False).exists():
        messages.error(request, 'Cannot discard an invoice that already has items. Use Cancel instead.')
        return redirect('billing:invoice_detail', invoice_id=invoice.id)

    # Safe to delete — no items, still draft
    invoice.is_deleted = True
    invoice.save(update_fields=['is_deleted', 'updated_at'])
    messages.success(request, f'Draft invoice {invoice.invoice_number} discarded.')
    return redirect('billing:cashier_queue')


@login_required
@require_POST
def waive_invoice(request, invoice_id):
    """
    Mark an invoice as WAIVED (full write-off) with a mandatory reason.
    Records a zero-amount waiver entry for audit trail.
    Only staff with the right permission (or superuser) should do this.
    """
    invoice = get_object_or_404(Invoice, id=invoice_id, is_deleted=False)

    if not _can_waive(request.user):
        messages.error(
            request,
            'Access denied. Only the Finance Director or Super Admin can waive invoices.'
        )
        return redirect('billing:invoice_detail', invoice_id=invoice.id)

    reason = request.POST.get('waiver_reason', '').strip()
    if not reason:
        messages.error(request, 'A waiver reason is required.')
        return redirect('billing:invoice_detail', invoice_id=invoice.id)

    invoice.status = InvoiceStatus.WAIVED
    invoice.discount_amount = invoice.total           # full write-off
    invoice.discount_reason = f'WAIVED by {request.user.get_full_name()} — {reason}'
    invoice.save(update_fields=['status', 'discount_amount', 'discount_reason', 'updated_at'])
    messages.success(
        request,
        f'Invoice {invoice.invoice_number} has been waived. Reason: {reason}'
    )
    return redirect('billing:invoice_detail', invoice_id=invoice.id)


# ─────────────────────────────────────────────────────────────────────────────
# POS (Point of Sale) — Cashier Station
# ─────────────────────────────────────────────────────────────────────────────

def _get_service_catalog(cashier_station=None):
    """
    Load active service prices from the Charge Master (DB), filtered by cashier station tier.
    - tier='' (blank) services are visible to ALL cashiers.
    - tier-specific services are only visible to cashiers assigned to that station.
    - cashier_station='ALL' or None → show everything (e.g. super admin, billing officer).
    """
    from .models import ServicePrice
    from django.db.models import Q
    try:
        qs = ServicePrice.objects.filter(is_active=True, is_deleted=False)
        if cashier_station and cashier_station != 'ALL':
            _tiers = DESK_TIER_GROUPS.get(cashier_station, [cashier_station])
            # Show services with no tier restriction OR matching this cashier's tier(s)
            qs = qs.filter(Q(tier='') | Q(tier__in=_tiers))
        return list(
            qs.order_by('tier', 'category', 'name')
            .values('id', 'name', 'category', 'tier', 'price', 'nhis_price',
                    'insurance_price', 'requires_price_entry', 'code')
        )
    except Exception:
        return []


@login_required
def pos_landing(request):
    """
    Sidebar shortcut for cashiers.
    Priority order:
    1. Counter assigned to this cashier and actively SERVING a patient → POS for that patient.
    2. Any CASHIER-type token CALLED or SERVING today → POS for that patient.
    3. Any CASHIER-type token WAITING today → POS for the first waiting patient.
    4. Most recent open (unpaid) invoice today → invoice detail to collect payment.
    5. Fall back to invoice list.
    """
    today = timezone.localdate()

    if _qms_active():
        from apps.qms.models import ServiceCounter, QueueToken, TokenStatus, ServiceType

        # 1 — Cashier has an assigned counter → their counter IS their workstation.
        #     If mid-serving → go to that patient's POS.
        #     Otherwise → always return to the counter (not pos, not invoice list).
        counter = ServiceCounter.objects.filter(
            staff_assigned=request.user, is_active=True
        ).first()
        if counter:
            if counter.current_serving:
                token = counter.current_serving
                if token.status in (TokenStatus.SERVING, TokenStatus.CALLED):
                    return redirect('billing:cashier_pos', token_id=token.id)
            # No active patient at counter — show cashier queue so they can pick next patient
            return redirect('billing:cashier_queue')

        # 2 — No counter assigned but QMS active: check active desk session first
        #     If cashier has a TIER desk session, go straight to that desk's queue.
        _active_session = CashierSession.objects.filter(
            cashier=request.user, status=SessionStatus.OPEN, is_deleted=False,
        ).order_by('-opened_at').select_related('cash_desk').first()

        if _active_session and _active_session.cash_desk.desk_type == DeskType.TIER and _active_session.cash_desk.tier:
            return redirect('billing:desk_queue', desk_id=_active_session.cash_desk.pk)

        # 3 — No desk session / non-tier desk: fall back to cashier_queue
        return redirect('billing:cashier_queue')

    # QMS inactive — open the patient search / direct billing page
    return redirect('billing:invoice_create')


def _get_cashier_tier(user):
    """
    Determine the active tier for a cashier:
    1. Active desk session tier (if cashier opened a TIER desk session)
    2. User's patient_tier field (fallback)
    3. 'ALL' (if neither set — chief cashier / unrestricted)
    """
    session = _get_active_cashier_session(user)
    if session and getattr(session, 'cash_desk', None):
        desk = session.cash_desk
        if getattr(desk, 'desk_type', None) == 'TIER' and desk.tier:
            return desk.tier
    return (getattr(user, 'patient_tier', '') or '').strip() or 'ALL'


@login_required
def cashier_queue(request):
    """
    Cashier queue — tier isolation via active desk session first, then patient_tier.
    Supports ?partial=1 for HTMX live updates (returns only tbody rows, no full page).
    """
    if not _qms_active():
        return redirect('billing:invoice_list')

    from apps.qms.models import QueueToken, TokenStatus, ServiceType

    today = timezone.localdate()
    waiting = QueueToken.objects.filter(
        service_type=ServiceType.CASHIER,
        status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
        token_date=today,
        is_deleted=False,
    ).select_related('patient').order_by('-priority', 'issued_at')

    # ── Tier isolation: session desk tier → patient_tier → ALL ───────────────
    _tier = _get_cashier_tier(request.user)
    if _tier == 'VIP':
        waiting = waiting.filter(service_tier='VIP')
    elif _tier in ('EXPRESS', 'FAST_TRACK'):
        waiting = waiting.filter(service_tier__in=['EXPRESS', 'FAST_TRACK'])
    elif _tier == 'STANDARD':
        waiting = waiting.filter(service_tier='STANDARD')
    # else 'ALL' → no filter

    # ── Partial response for HTMX live polling ───────────────────────────────
    if request.GET.get('partial') == '1':
        from django.template.loader import render_to_string
        html = render_to_string('billing/_cashier_queue_rows.html', {'waiting': waiting}, request=request)
        from django.http import HttpResponse
        return HttpResponse(html)

    return render(request, 'billing/cashier_queue.html', {
        'waiting': waiting,
        'today': today,
        'cashier_tier': _tier,
    })


@login_required
def cashier_pos(request, token_id):
    """Main POS view — displays the cashier point-of-sale interface."""
    from apps.qms.models import QueueToken
    from apps.accounts.models import CashierStation as _CS
    token = get_object_or_404(QueueToken, id=token_id, is_deleted=False)

    # ── Tier guard: use active desk session tier (new system) or fall back to cashier_station ──
    from apps.billing.models import CashierSession, SessionStatus as _SS
    _active_session = CashierSession.objects.filter(
        cashier=request.user, status=_SS.OPEN, is_deleted=False,
    ).order_by('-opened_at').select_related('cash_desk').first()

    if _active_session and _active_session.cash_desk.desk_type == 'TIER' and _active_session.cash_desk.tier:
        # New system: tier comes from desk session
        _desk_tier = _active_session.cash_desk.tier
        _allowed = DESK_TIER_GROUPS.get(_desk_tier, [_desk_tier])
        if _allowed and token.service_tier not in _allowed:
            messages.error(
                request,
                f'Your desk ({_active_session.cash_desk.name}) handles {_desk_tier} patients only. '
                f'This is a {token.get_service_tier_display()} patient — route to the correct counter.'
            )
            return redirect('billing:cashier_queue')
    # ────────────────────────────────────────────────────────────────────────

    patient = token.patient

    invoice = None
    items = []
    payments = []
    active_consultation = None
    prior_unpaid_invoices = []

    if patient:
        invoice = get_or_create_today_invoice(patient, created_by=request.user)
        items = invoice.items.filter(is_deleted=False).order_by('created_at')
        payments = invoice.payments.filter(is_deleted=False).order_by('payment_date')

        # Gap 4: Check if patient is still in their 15-day consultation window
        active_consultation = patient.active_consultation_visit

        # Outstanding balance alert: unpaid invoices from previous visits (not today)
        from django.db.models import Prefetch as _Pf2
        prior_unpaid_invoices = Invoice.objects.filter(
            patient=patient,
            is_deleted=False,
        ).exclude(
            status__in=[InvoiceStatus.PAID, InvoiceStatus.CANCELLED, InvoiceStatus.WAIVED]
        ).exclude(
            id=invoice.id
        ).prefetch_related(
            _Pf2('items', queryset=InvoiceItem.objects.filter(is_deleted=False), to_attr='_items_cache'),
            _Pf2('payments', queryset=Payment.objects.filter(is_deleted=False), to_attr='_payments_cache'),
            _Pf2('refunds', queryset=Refund.objects.filter(is_deleted=False), to_attr='_refunds_cache'),
        ).order_by('-created_at')[:5]

    # Active insurance for co-pay display
    from apps.patients.models import InsuranceInfo
    active_insurance = None
    if patient:
        active_insurance = (
            InsuranceInfo.objects
            .filter(patient=patient, is_active=True, is_deleted=False)
            .order_by('-created_at')
            .first()
        )

    # Doctor's pre-orders waiting for payment
    doctor_orders = []
    if patient:
        doctor_orders = list(
            ServiceWorkOrder.objects.filter(
                patient=patient,
                status=WorkOrderStatus.PENDING_PAYMENT,
                is_deleted=False,
                created_at__date=timezone.localdate(),
            ).order_by('created_at')
        )

    # Shift running total — today's payments collected by this cashier
    today = timezone.localdate()
    shift_totals = Payment.objects.filter(
        received_by=request.user,
        payment_date__date=today,
        is_deleted=False,
    ).aggregate(
        total=Sum('amount'),
        cash=Sum('amount', filter=Q(payment_method=PaymentMethod.CASH)),
        mobile=Sum('amount', filter=Q(payment_method=PaymentMethod.MOBILE_MONEY)),
    )

    _pos_session = _get_active_cashier_session(request.user)
    _pos_tier = (
        _pos_session.cash_desk.tier
        if _pos_session and _pos_session.cash_desk.desk_type == 'TIER' and _pos_session.cash_desk.tier
        else (token.service_tier if token else 'STANDARD')
    )
    from django.urls import reverse as _rev
    _queue_url = (
        _rev('billing:desk_queue', kwargs={'desk_id': str(_pos_session.cash_desk.pk)})
        if _pos_session and _pos_session.cash_desk.desk_type == 'TIER' and _pos_session.cash_desk.tier
        else _rev('billing:cashier_queue')
    )
    # ── Tier change history for this visit ────────────────────────────────────
    _visit = token.visit if token else None
    _tier_changes = []
    if _visit:
        from apps.patients.models import VisitTierChange
        _tier_changes = list(
            VisitTierChange.objects.filter(visit=_visit)
            .select_related('changed_by')
            .order_by('-created_at')[:10]
        )

    from apps.patients.models import ServiceTier as _ST
    return render(request, 'billing/cashier_pos.html', {
        'token': token,
        'patient': patient,
        'invoice': invoice,
        'items': items,
        'payments': payments,
        'categories': ServiceCategory.choices,
        'payment_methods': PaymentMethod.choices,
        'service_catalog': _get_service_catalog(cashier_station=_pos_tier),
        'today': today,
        'active_consultation': active_consultation,
        'prior_unpaid_invoices': prior_unpaid_invoices,
        'active_insurance': active_insurance,
        'doctor_orders': doctor_orders,
        'receipt_url': f"/billing/receipt/{invoice.id}/" if invoice else '',
        'shift_total': shift_totals['total'] or 0,
        'shift_cash': shift_totals['cash'] or 0,
        'shift_mobile': shift_totals['mobile'] or 0,
        'patient_tier': _pos_tier,
        'queue_url': _queue_url,
        'visit': _visit,
        'tier_changes': _tier_changes,
        'tier_choices': _ST.choices,
    })


@json_error_handler
@login_required
@require_POST
def pos_add_item(request, invoice_id):
    """AJAX: Add a line item to the invoice."""
    invoice = get_object_or_404(Invoice, id=invoice_id, is_deleted=False)

    description = request.POST.get('description', '').strip()
    category = request.POST.get('category', ServiceCategory.OTHER)
    quantity = int(request.POST.get('quantity', 1) or 1)
    try:
        unit_price = Decimal(request.POST.get('unit_price', '0') or '0')
    except InvalidOperation:
        return JsonResponse({'success': False, 'error': 'Invalid price.'}, status=400)

    if not description:
        return JsonResponse({'success': False, 'error': 'Description is required.'}, status=400)

    item = InvoiceItem.objects.create(
        invoice=invoice,
        description=description,
        category=category,
        quantity=quantity,
        unit_price=unit_price,
        created_by=request.user,
    )

    # Promote invoice from DRAFT to ISSUED when first item added
    if invoice.status == InvoiceStatus.DRAFT:
        invoice.status = InvoiceStatus.ISSUED
        invoice.save(update_fields=['status', 'updated_at'])

    invoice.refresh_from_db()
    return JsonResponse({
        'success': True,
        'item_id': str(item.id),
        'description': item.description,
        'quantity': item.quantity,
        'unit_price': int(item.unit_price),
        'line_total': int(item.line_total),
        'subtotal': int(invoice.subtotal),
        'total': int(invoice.total),
        'balance_due': int(invoice.balance_due),
    })


@json_error_handler
@login_required
@require_POST
def pos_remove_item(request, item_id):
    """AJAX: Soft-delete a line item. Blocked once any payment has been made."""
    item = get_object_or_404(InvoiceItem, id=item_id, is_deleted=False)
    invoice = item.invoice

    # Block removal once the invoice has been fully or partially paid
    if invoice.status in (InvoiceStatus.PAID, InvoiceStatus.PARTIALLY_PAID):
        return JsonResponse({
            'success': False,
            'error': 'Cannot remove items from a paid or partially-paid invoice. '
                     'Issue a refund instead.'
        }, status=400)

    item.is_deleted = True
    item.save(update_fields=['is_deleted', 'updated_at'])

    invoice.refresh_from_db()
    return JsonResponse({
        'success': True,
        'subtotal': int(invoice.subtotal),
        'total': int(invoice.total),
        'balance_due': int(invoice.balance_due),
    })


@json_error_handler
@login_required
@require_POST
def pos_apply_discount(request, invoice_id):
    """AJAX: Apply or update a discount on the invoice."""
    invoice = get_object_or_404(Invoice, id=invoice_id, is_deleted=False)

    try:
        discount_amount = Decimal(request.POST.get('discount_amount', '0') or '0')
    except InvalidOperation:
        return JsonResponse({'success': False, 'error': 'Invalid discount amount.'}, status=400)

    discount_reason = request.POST.get('discount_reason', '').strip()

    invoice.discount_amount = discount_amount
    invoice.discount_reason = discount_reason
    invoice.save(update_fields=['discount_amount', 'discount_reason', 'updated_at'])

    invoice.refresh_from_db()
    return JsonResponse({
        'success': True,
        'discount_amount': int(invoice.discount_amount),
        'total': int(invoice.total),
        'balance_due': int(invoice.balance_due),
    })


@login_required
@require_POST
def pos_record_payment(request, invoice_id):
    """AJAX: Record a payment against the invoice."""
    invoice = get_object_or_404(Invoice, id=invoice_id, is_deleted=False)

    # Block payment if cashier has no open shift today
    if request.user.role == 'cashier':
        today = timezone.localdate()
        open_shift = CashierShift.objects.filter(
            cashier=request.user, shift_date=today,
            status=ShiftStatus.OPEN, is_deleted=False
        ).first()
        if not open_shift:
            return JsonResponse({
                'success': False,
                'error': 'Your shift is not open. Ask the Chief Cashier to open the working day before billing.'
            }, status=403)

    payment_method = request.POST.get('payment_method', PaymentMethod.CASH)
    try:
        amount = Decimal(request.POST.get('amount', '0') or '0')
    except InvalidOperation:
        return JsonResponse({'success': False, 'error': 'Invalid amount.'}, status=400)

    if amount <= 0:
        return JsonResponse({'success': False, 'error': 'Amount must be greater than zero.'}, status=400)

    reference = request.POST.get('reference', '').strip()

    # ── Corporate account linkage and credit limit check ─────────────────
    credit_warning = None
    if payment_method in (PaymentMethod.INSURANCE, PaymentMethod.NHIS):
        try:
            from .models import CorporateAccount, CorporateAccountMember
            membership = CorporateAccountMember.objects.filter(
                patient=invoice.patient, is_active=True, is_deleted=False
            ).select_related('corporate_account').first()
            if membership:
                corp = membership.corporate_account
                # Auto-link invoice to corporate account if not already linked
                if not invoice.corporate_account_id:
                    invoice.corporate_account = corp
                    invoice.save(update_fields=['corporate_account', 'updated_at'])
                # Credit limit check
                if corp.credit_limit > 0:
                    new_balance = float(corp.outstanding_balance) + float(amount)
                    if new_balance > float(corp.credit_limit):
                        credit_warning = (
                            f'⚠️ Credit limit exceeded for {corp.name}: '
                            f'limit {int(corp.credit_limit):,} FCFA, '
                            f'new balance will be {int(new_balance):,} FCFA. '
                            f'Notify Finance Director.'
                        )
        except Exception:
            pass

    Payment.objects.create(
        invoice=invoice,
        payment_method=payment_method,
        amount=amount,
        reference=reference,
        received_by=request.user,
        created_by=request.user,
        cashier_session=_get_active_cashier_session(request.user),
    )
    from apps.accounts.models import UserAuditLog
    _log_financial(request, UserAuditLog.Action.CREATE_RECORD, invoice,
                   extra={'payment': str(amount), 'method': payment_method})
    # Payment.save() already calls invoice.update_status()
    _try_open_consultation_window(invoice)
    invoice.refresh_from_db()
    # Sync surgical booking deposit if this invoice is linked to a booking
    _sync_surgical_deposit(invoice)

    resp = {
        'success': True,
        'amount_paid': int(invoice.amount_paid),
        'balance_due': int(invoice.balance_due),
        'status': invoice.status,
        'is_paid': invoice.status == InvoiceStatus.PAID,
    }
    if credit_warning:
        resp['credit_warning'] = credit_warning
    return JsonResponse(resp)


@json_error_handler
@login_required
@require_POST
def pos_finalize(request, token_id):
    """
    Finalize payment:
    1. Verifies the invoice is PAID (or balance_due <= 0).
    2. Replicates cashier_complete logic:
       - Complete the CASHIER token & free the counter
       - Get or create today's Visit
       - Create PARAMETERS token to route patient to triage
    3. Returns JSON with redirect URL to receipt page.
    """
    from django.db import transaction
    from apps.qms.models import (
        QueueToken, DailyTokenSequence,
        ServiceType, ServiceTier, TokenStatus, IssuancePoint, TIER_PRIORITY,
    )
    from apps.patients.models import Visit, VisitStatus, VisitType

    token = get_object_or_404(QueueToken, id=token_id, is_deleted=False)

    if not token.patient:
        return JsonResponse({'success': False, 'error': 'No patient linked to this token.'}, status=400)

    today = timezone.localdate()
    invoice = Invoice.objects.filter(
        patient=token.patient,
        issue_date=today,
        is_deleted=False,
    ).exclude(status=InvoiceStatus.CANCELLED).first()

    if not invoice:
        return JsonResponse({'success': False, 'error': 'No invoice found for today.'}, status=400)

    if invoice.balance_due > 0:
        return JsonResponse({
            'success': False,
            'error': f'Balance of {int(invoice.balance_due)} FCFA still outstanding.'
        }, status=400)

    with transaction.atomic():
        # 1 — Complete cashier token & free counter
        if token.status not in [TokenStatus.COMPLETED, TokenStatus.CANCELLED]:
            token.complete()
        if token.counter:
            token.counter.current_serving = None
            token.counter.save(update_fields=['current_serving', 'updated_at'])

        # 2 — Get or create today's Visit
        visit = Visit.objects.filter(
            patient=token.patient,
            visit_date__date=today,
            is_deleted=False,
        ).first()

        if not visit:
            has_prior = Visit.objects.filter(
                patient=token.patient, is_deleted=False
            ).exists()
            visit = Visit.objects.create(
                patient=token.patient,
                visit_type=VisitType.FOLLOW_UP if has_prior else VisitType.NEW,
                chief_complaint='',
                status=VisitStatus.PARAMETERS,
                service_tier=token.service_tier,
                created_by=request.user,
            )
        else:
            visit.status = VisitStatus.PARAMETERS
            visit.save(update_fields=['status', 'updated_at'])

        # 3 — Create triage token (tier-aware) — only when QMS is active
        if _qms_active():
            triage_stype = (
                ServiceType.PARAMETERS
                if token.service_tier == ServiceTier.STANDARD
                else ServiceType.PARAMETERS_VIP
            )
            triage_num = DailyTokenSequence.next_dept_token(triage_stype)
            QueueToken.objects.create(
                token_number=triage_num,
                token_date=today,
                patient=token.patient,
                visit=visit,
                patient_name=token.patient.full_name,
                service_type=triage_stype,
                service_tier=token.service_tier,
                issuance_point=IssuancePoint.SYSTEM,
                priority=TIER_PRIORITY.get(token.service_tier, 0),
                entry_token=token.entry_token or token,
                issued_by=request.user,
                notes='Auto-routed after POS payment confirmation',
            )

    # Open 15-day consultation window if invoice has a CONSULT or REG item
    _try_open_consultation_window(invoice)

    from django.urls import reverse
    redirect_url = reverse('billing:receipt', kwargs={'invoice_id': str(invoice.id)})
    return JsonResponse({'success': True, 'redirect_url': redirect_url})


@login_required
def patient_pos(request, patient_id):
    """
    QMS-independent POS — open billing for a patient directly by patient_id.
    Works identically to cashier_pos but without a QMS token.
    Used when QMS is disabled or when a patient walks straight to the cashier.
    """
    patient = get_object_or_404(Patient, patient_id=patient_id, is_deleted=False)
    invoice = get_or_create_today_invoice(patient, created_by=request.user)
    items = invoice.items.filter(is_deleted=False).order_by('created_at')
    payments = invoice.payments.filter(is_deleted=False).order_by('payment_date')
    active_consultation = patient.active_consultation_visit
    prior_unpaid_invoices = Invoice.objects.filter(
        patient=patient, is_deleted=False,
    ).exclude(
        status__in=[InvoiceStatus.PAID, InvoiceStatus.CANCELLED, InvoiceStatus.WAIVED]
    ).exclude(id=invoice.id).order_by('-created_at')[:5]
    from apps.patients.models import InsuranceInfo
    active_insurance = InsuranceInfo.objects.filter(
        patient=patient, is_active=True, is_deleted=False
    ).order_by('-created_at').first()
    doctor_orders = list(
        ServiceWorkOrder.objects.filter(
            patient=patient,
            status=WorkOrderStatus.PENDING_PAYMENT,
            is_deleted=False,
            created_at__date=timezone.localdate(),
        ).order_by('created_at')
    )
    today = timezone.localdate()
    shift_totals = Payment.objects.filter(
        received_by=request.user,
        payment_date__date=today,
        is_deleted=False,
    ).aggregate(
        total=Sum('amount'),
        cash=Sum('amount', filter=Q(payment_method=PaymentMethod.CASH)),
        mobile=Sum('amount', filter=Q(payment_method=PaymentMethod.MOBILE_MONEY)),
    )
    # Tier from today's visit or most recent visit
    from apps.patients.models import Visit as _Visit
    _today_visit = (
        _Visit.objects.filter(patient=patient, is_deleted=False)
        .order_by('-visit_date').first()
    )
    _ppos_session = _get_active_cashier_session(request.user)
    _ppos_tier = (
        _ppos_session.cash_desk.tier
        if _ppos_session and _ppos_session.cash_desk.desk_type == 'TIER' and _ppos_session.cash_desk.tier
        else (_today_visit.service_tier if _today_visit else 'STANDARD')
    )
    from django.urls import reverse as _rev
    _pqueue_url = (
        _rev('billing:desk_queue', kwargs={'desk_id': str(_ppos_session.cash_desk.pk)})
        if _ppos_session and _ppos_session.cash_desk.desk_type == 'TIER' and _ppos_session.cash_desk.tier
        else _rev('billing:cashier_queue')
    )
    return render(request, 'billing/cashier_pos.html', {
        'token': None,
        'patient': patient,
        'invoice': invoice,
        'items': items,
        'payments': payments,
        'categories': ServiceCategory.choices,
        'payment_methods': PaymentMethod.choices,
        'service_catalog': _get_service_catalog(cashier_station=_ppos_tier),
        'today': today,
        'active_consultation': active_consultation,
        'prior_unpaid_invoices': prior_unpaid_invoices,
        'active_insurance': active_insurance,
        'doctor_orders': doctor_orders,
        'receipt_url': f"/billing/receipt/{invoice.id}/" if invoice else '',
        'shift_total': shift_totals['total'] or 0,
        'shift_cash': shift_totals['cash'] or 0,
        'shift_mobile': shift_totals['mobile'] or 0,
        'patient_tier': _ppos_tier,
        'queue_url': _pqueue_url,
    })


@json_error_handler
@login_required
@require_POST
def patient_finalize(request, patient_id):
    """
    Finalize payment via cashier_pos. Calls _route_patient_after_payment to create
    a Visit and complete/route QMS tokens (same as add_payment path).
    """
    from django.urls import reverse

    patient = get_object_or_404(Patient, patient_id=patient_id, is_deleted=False)
    today = timezone.localdate()
    invoice = Invoice.objects.filter(
        patient=patient, issue_date=today, is_deleted=False,
    ).exclude(status=InvoiceStatus.CANCELLED).first()

    if not invoice:
        return JsonResponse({'success': False, 'error': 'No invoice found for today.'}, status=400)
    if invoice.balance_due > 0:
        return JsonResponse({
            'success': False,
            'error': f'Balance of {int(invoice.balance_due)} FCFA still outstanding.'
        }, status=400)

    _try_open_consultation_window(invoice)
    _route_patient_after_payment(invoice, request)

    redirect_url = reverse('billing:receipt', kwargs={'invoice_id': str(invoice.id)})
    return JsonResponse({'success': True, 'redirect_url': redirect_url})


@login_required
def receipt_view(request, invoice_id):
    """Printable receipt page."""
    from apps.qms.models import QueueToken
    invoice = get_object_or_404(Invoice, id=invoice_id, is_deleted=False)
    items = invoice.items.filter(is_deleted=False).order_by('created_at')
    payments = invoice.payments.filter(is_deleted=False).order_by('payment_date')
    # Get the QMS token issued on the invoice date (not the patient's first-ever token)
    today_token = None
    if invoice.patient:
        today_token = (
            QueueToken.objects
            .filter(patient=invoice.patient, token_date=invoice.issue_date, is_deleted=False)
            .order_by('-issued_at')
            .first()
        )
    ctx = {
        'invoice': invoice,
        'items': items,
        'payments': payments,
        'today_token': today_token,
    }
    if request.GET.get('format') == 'pdf':
        return _render_pdf(
            'billing/pdf/invoice_pdf.html', ctx,
            f'invoice_{invoice.invoice_number}.pdf',
        )
    return render(request, 'billing/receipt.html', ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Work Order System — department queues after payment
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def doctor_order_create(request):
    """
    AJAX: Doctor creates a billing order during consultation.
    Creates a PENDING_PAYMENT work order visible on the cashier's POS for this patient.
    """
    from apps.consultations.models import Consultation
    consultation_id = request.POST.get('consultation_id')
    patient_id = request.POST.get('patient_id')
    category = request.POST.get('category', '').strip()
    description = request.POST.get('description', '').strip()

    if not description or not category:
        return JsonResponse({'success': False, 'error': 'Category and description required.'}, status=400)

    consultation = None
    if consultation_id:
        try:
            consultation = Consultation.objects.get(pk=consultation_id, is_deleted=False)
            patient = consultation.patient
        except Consultation.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Consultation not found.'}, status=404)
    else:
        patient = get_object_or_404(Patient, patient_id=patient_id, is_deleted=False)

    wo = ServiceWorkOrder.objects.create(
        patient=patient,
        consultation=consultation,
        category=category,
        description=description,
        status=WorkOrderStatus.PENDING_PAYMENT,
        created_by=request.user,
    )
    return JsonResponse({
        'success': True,
        'wo_id': str(wo.id),
        'description': wo.description,
        'category': wo.get_category_display(),
    })


@login_required
@require_POST
def doctor_order_cancel(request, wo_id):
    """AJAX: Cancel a PENDING_PAYMENT work order before cashier bills it."""
    wo = get_object_or_404(ServiceWorkOrder, id=wo_id, is_deleted=False)
    if wo.status != WorkOrderStatus.PENDING_PAYMENT:
        return JsonResponse({'success': False, 'error': 'Only pending-payment orders can be cancelled.'}, status=400)
    wo.status = WorkOrderStatus.CANCELLED
    wo.save(update_fields=['status', 'updated_at'])
    return JsonResponse({'success': True})


@login_required
def work_queue(request):
    """
    Department work queue — shows paid & pending service work orders for today.
    Filter by category via ?cat=PHARMACY or ?cat=LAB&cat=INVEST etc.
    Any authenticated staff member can access; each dept uses their own link.
    """
    today = timezone.localdate()
    categories = request.GET.getlist('cat')
    qs = ServiceWorkOrder.objects.filter(
        status=WorkOrderStatus.PENDING,
        is_deleted=False,
        created_at__date=today,
    ).select_related('patient', 'invoice').order_by('created_at')
    if categories:
        qs = qs.filter(category__in=categories)
    # Category display label for page title
    cat_labels = dict(ServiceCategory.choices)
    dept_name = ' / '.join(cat_labels.get(c, c) for c in categories) if categories else 'All Departments'
    return render(request, 'billing/work_queue.html', {
        'work_orders': qs,
        'categories': categories,
        'dept_name': dept_name,
        'today': today,
        'service_categories': ServiceCategory.choices,
    })


@login_required
@require_POST
def work_order_done(request, wo_id):
    """AJAX: Mark a work order as done."""
    wo = get_object_or_404(ServiceWorkOrder, id=wo_id, is_deleted=False)
    wo.status = WorkOrderStatus.DONE
    wo.completed_at = timezone.now()
    wo.completed_by = request.user
    wo.notes = request.POST.get('notes', '').strip()
    wo.save(update_fields=['status', 'completed_at', 'completed_by', 'notes', 'updated_at'])

    # If pharmacy work order, mark any pending dispensing for this patient today as dispensed
    if getattr(wo, 'category', None) == 'PHARMACY' and wo.patient_id:
        try:
            from apps.pharmacy.models import Dispensing, DispensingStatus
            today = timezone.localdate()
            Dispensing.objects.filter(
                patient_id=wo.patient_id,
                status__in=[DispensingStatus.PENDING, DispensingStatus.PARTIAL],
                created_at__date=today,
                is_deleted=False,
            ).update(status=DispensingStatus.DISPENSED, dispensed_at=timezone.now())
        except Exception:
            pass

    return JsonResponse({'success': True, 'wo_id': str(wo.id)})


# ─────────────────────────────────────────────────────────────────────────────
# Gap 5: Surgical Deposit Billing
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def surgical_deposit(request, booking_id):
    """
    Collect surgical deposit for a confirmed surgical booking.
    If a Proforma exists (created by Admission Officer), converts it to Invoice.
    Otherwise creates a deposit invoice directly.
    """
    from apps.ipd.models import SurgicalBooking
    from apps.billing.models import Proforma, ProformaStatus
    booking = get_object_or_404(SurgicalBooking, id=booking_id, is_deleted=False)
    patient = booking.patient

    # Find the proforma issued by Admission Officer for this booking
    proforma = Proforma.objects.filter(
        patient=patient,
        notes__icontains=booking.booking_number,
        is_deleted=False,
    ).exclude(status=ProformaStatus.CANCELLED).first()

    # Find existing deposit invoice — first check via proforma, then by notes
    deposit_invoice = None
    if proforma and proforma.invoice:
        deposit_invoice = proforma.invoice
    if not deposit_invoice:
        deposit_invoice = Invoice.objects.filter(
            patient=patient,
            notes__icontains=booking.booking_number,
            is_deleted=False,
        ).exclude(status=InvoiceStatus.CANCELLED).first()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_invoice' and not deposit_invoice:
            if proforma and proforma.status == ProformaStatus.ISSUED:
                # Convert proforma to invoice
                deposit_invoice = Invoice.objects.create(
                    patient=patient,
                    notes=f'Surgical booking {booking.booking_number} — converted from {proforma.proforma_number}',
                    status=InvoiceStatus.ISSUED,
                    created_by=request.user,
                )
                for pitem in proforma.items.filter(is_deleted=False):
                    InvoiceItem.objects.create(
                        invoice=deposit_invoice,
                        description=pitem.description,
                        category=pitem.category,
                        quantity=pitem.quantity,
                        unit_price=pitem.unit_price,
                        created_by=request.user,
                    )
                proforma.invoice = deposit_invoice
                proforma.status = ProformaStatus.CONVERTED
                proforma.save(update_fields=['invoice', 'status', 'updated_at'])
                messages.success(request, f'Proforma {proforma.proforma_number} converted to Invoice {deposit_invoice.invoice_number}.')
            else:
                deposit_invoice = Invoice.objects.create(
                    patient=patient,
                    notes=f'Surgical deposit for {booking.get_procedure_display()} — Booking {booking.booking_number}',
                    status=InvoiceStatus.ISSUED,
                    created_by=request.user,
                )
                InvoiceItem.objects.create(
                    invoice=deposit_invoice,
                    description=f'Surgical Deposit — {booking.get_procedure_display()} ({booking.get_eye_laterality_display()})',
                    category=ServiceCategory.SURGICAL,
                    quantity=1,
                    unit_price=booking.deposit_required or booking.total_amount or 0,
                    created_by=request.user,
                )
                messages.success(request, f'Deposit invoice {deposit_invoice.invoice_number} created.')

        elif action == 'record_payment' and deposit_invoice:
            amount_str = request.POST.get('amount', '').strip()
            method = request.POST.get('payment_method', 'CASH')
            reference = request.POST.get('reference', '').strip()
            try:
                amount = Decimal(amount_str)
                if amount <= 0:
                    raise ValueError
            except (ValueError, InvalidOperation):
                messages.error(request, 'Enter a valid payment amount.')
                return redirect('billing:surgical_deposit', booking_id=booking.id)

            Payment.objects.create(
                invoice=deposit_invoice,
                payment_method=method,
                amount=amount,
                reference=reference,
                notes=f'Surgical deposit — {booking.booking_number}',
                received_by=request.user,
                created_by=request.user,
            )
            # Update booking.deposit_paid
            booking.deposit_paid = (booking.deposit_paid or 0) + amount
            booking.save(update_fields=['deposit_paid', 'updated_at'])

            messages.success(request, f'Deposit of {int(amount):,} FCFA recorded.')
            return redirect('billing:surgical_deposit', booking_id=booking.id)

        return redirect('billing:surgical_deposit', booking_id=booking.id)

    items = deposit_invoice.items.filter(is_deleted=False) if deposit_invoice else []
    payments = deposit_invoice.payments.filter(is_deleted=False).order_by('payment_date') if deposit_invoice else []
    proforma_items = proforma.items.filter(is_deleted=False) if proforma else []

    return render(request, 'billing/surgical_deposit.html', {
        'booking': booking,
        'patient': patient,
        'proforma': proforma,
        'proforma_items': proforma_items,
        'deposit_invoice': deposit_invoice,
        'items': items,
        'payments': payments,
        'payment_methods': PaymentMethod.choices,
        'balance_due': deposit_invoice.balance_due if deposit_invoice else booking.deposit_required or booking.total_amount or 0,
    })


@login_required
@require_POST
def surgical_return_checkin(request, booking_id):
    """
    Receptionist / Cashier: Patient returns later to pay surgical deposit.
    Issues a CASHIER QMS token for the booking so cashier sees them in queue.
    """
    from apps.ipd.models import SurgicalBooking
    booking = get_object_or_404(SurgicalBooking, id=booking_id, is_deleted=False)
    patient = booking.patient

    if _qms_active():
        try:
            from apps.qms.models import (
                QueueToken, DailyTokenSequence,
                IssuancePoint, TIER_PRIORITY, ServiceTier,
            )
            tier = ServiceTier.STANDARD
            cash_token = DailyTokenSequence.next_dept_token('CASHIER')
            QueueToken.objects.create(
                token_number=cash_token,
                patient=patient,
                patient_name=patient.full_name,
                service_type='CASHIER',
                service_tier=tier,
                issuance_point=IssuancePoint.SYSTEM,
                priority=TIER_PRIORITY.get(tier, 0),
                notes=(
                    f'Returning for surgery payment — {booking.get_procedure_display()} | '
                    f'Balance: {booking.balance_due:,.0f} FCFA | {booking.booking_number}'
                ),
                issued_by=request.user,
            )
            messages.success(request, f'Cashier token issued for {patient.full_name}. Balance: {booking.balance_due:,.0f} FCFA.')
        except Exception as e:
            messages.error(request, f'Could not issue token: {e}')
    else:
        messages.info(request, f'QMS is disabled. Direct patient to Cashier. Balance: {booking.balance_due:,.0f} FCFA.')
    return redirect('billing:surgical_deposit', booking_id=booking.pk)


@login_required
def surgical_deposit_receipt(request, booking_id):
    """Printable receipt for all deposit payments on a surgical booking."""
    from apps.ipd.models import SurgicalBooking
    booking = get_object_or_404(SurgicalBooking, id=booking_id, is_deleted=False)
    from apps.billing.models import Proforma, ProformaStatus
    deposit_invoice = None
    proforma = Proforma.objects.filter(
        patient=booking.patient,
        notes__icontains=booking.booking_number,
        is_deleted=False,
    ).exclude(status=ProformaStatus.CANCELLED).first()
    if proforma and proforma.invoice:
        deposit_invoice = proforma.invoice
    if not deposit_invoice:
        deposit_invoice = Invoice.objects.filter(
            patient=booking.patient,
            notes__icontains=booking.booking_number,
            is_deleted=False,
        ).exclude(status=InvoiceStatus.CANCELLED).first()

    payments = deposit_invoice.payments.filter(is_deleted=False).order_by('payment_date') if deposit_invoice else []
    return render(request, 'billing/surgical_deposit_receipt.html', {
        'booking': booking,
        'patient': booking.patient,
        'deposit_invoice': deposit_invoice,
        'payments': payments,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Cashier Shift Management — Open / Close / Submit / Verify
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def shift_day_open(request):
    """
    Billing Agent / Billing Officer opens the working day for ALL cashiers at once.
    Creates a CashierShift for each active cashier who doesn't have one today.
    Each cashier is assigned an opening cash float.
    """
    if not _can_open_day(request.user):
        messages.error(request, 'Only the Chief Cashier can open the working day for cashiers.')
        return redirect('billing:shift_list')

    today = timezone.localdate()

    # All active cashiers (including optical dispenser and pharmacist who also have cash desks)
    cashiers = list(
        __import__('apps.accounts.models', fromlist=['User']).User.objects.filter(
            role__in=[UserRole.CASHIER, UserRole.BILLING_OFFICER, UserRole.OPTICAL_DISPENSER, UserRole.PHARMACIST],
            is_active=True,
        ).order_by('first_name', 'last_name')
    )

    # Find who already has a shift today
    existing_ids = set(
        CashierShift.objects.filter(
            shift_date=today, is_deleted=False
        ).values_list('cashier_id', flat=True)
    )

    if request.method == 'POST':
        # ── Auto-close any OPEN shifts from previous days ────────────────────
        stale = CashierShift.objects.filter(
            shift_date__lt=today, status=ShiftStatus.OPEN, is_deleted=False,
        )
        stale_count = stale.count()
        if stale_count:
            stale.update(
                status=ShiftStatus.CLOSED,
                closed_at=timezone.now(),
                notes='Auto-closed when new day was opened by Chief Cashier.',
            )
            messages.warning(request, f'{stale_count} shift(s) from previous day(s) were automatically closed.')

        # ── Also auto-close any OPEN desk sessions from previous days ─────────
        stale_sessions = CashierSession.objects.filter(
            status=SessionStatus.OPEN, is_deleted=False,
        ).exclude(opened_at__date=today)
        stale_sess_count = stale_sessions.count()
        if stale_sess_count:
            stale_sessions.update(
                status=SessionStatus.CLOSED,
                closed_at=timezone.now(),
                notes='Auto-closed when Chief Cashier opened the new working day.',
            )
            messages.warning(request, f'{stale_sess_count} desk session(s) from previous day(s) were automatically closed.')

        default_float = request.POST.get('default_float', '0').strip() or '0'
        try:
            default_float_dec = Decimal(default_float)
        except InvalidOperation:
            default_float_dec = Decimal('0')

        created = 0
        skipped = 0
        for cashier in cashiers:
            if cashier.id in existing_ids:
                skipped += 1
                continue
            per_cashier_key = f'float_{cashier.id}'
            try:
                opening = Decimal(request.POST.get(per_cashier_key, str(default_float_dec)) or str(default_float_dec))
            except InvalidOperation:
                opening = default_float_dec

            CashierShift.objects.create(
                cashier=cashier,
                shift_date=today,
                opening_cash=opening,
                status=ShiftStatus.OPEN,
                created_by=request.user,
            )
            created += 1

        msg = f'Day opened for {created} cashier(s) on {today.strftime("%d %b %Y")}.'
        if skipped:
            msg += f' {skipped} already had a shift today.'
        messages.success(request, msg)
        return redirect('billing:shift_list')

    # Prepare list annotated with shift status
    cashier_info = []
    for c in cashiers:
        existing = CashierShift.objects.filter(cashier=c, shift_date=today, is_deleted=False).first()
        cashier_info.append({'cashier': c, 'existing_shift': existing})

    return render(request, 'billing/shift_day_open.html', {
        'cashier_info': cashier_info,
        'today': today,
        'all_open': all(c['existing_shift'] for c in cashier_info),
    })


@login_required
@require_POST
def shift_transfer(request, shift_id):
    """
    Cashier closes their shift AND submits it to the Billing Agent in one action.
    This is the 'Transfer to Billing Agent' button — cashier hands over their cash.
    After this, the shift is SUBMITTED and the cashier's balance is pending verification.
    """
    shift = get_object_or_404(CashierShift, id=shift_id, is_deleted=False)

    if shift.cashier != request.user and not _can_authorize_billing(request.user):
        messages.error(request, 'You can only transfer your own shift.')
        return redirect('billing:shift_detail', shift_id=shift.id)

    if shift.status not in (ShiftStatus.OPEN, ShiftStatus.CLOSED):
        messages.warning(request, 'This shift has already been submitted or verified.')
        return redirect('billing:shift_detail', shift_id=shift.id)

    try:
        closing_cash = Decimal(request.POST.get('closing_cash_declared', '0') or '0')
    except InvalidOperation:
        messages.error(request, 'Invalid cash amount entered.')
        return redirect('billing:shift_detail', shift_id=shift.id)

    now = timezone.now()
    shift.closing_cash_declared = closing_cash
    shift.closed_at = now
    shift.submitted_at = now
    shift.notes = request.POST.get('notes', shift.notes).strip()
    shift.status = ShiftStatus.SUBMITTED
    shift.save(update_fields=[
        'closing_cash_declared', 'closed_at', 'submitted_at', 'notes', 'status', 'updated_at'
    ])
    messages.success(
        request,
        f'Transfer complete. You submitted {int(shift.total_collected):,} FCFA to the '
        f'Chief Cashier. Awaiting verification.'
    )
    return redirect('billing:shift_detail', shift_id=shift.id)


@login_required
def my_shift(request):
    """Redirect cashier to their own today's shift detail page."""
    today = timezone.localdate()
    shift = CashierShift.objects.filter(
        cashier=request.user, shift_date=today, is_deleted=False
    ).first()
    if shift:
        return redirect('billing:shift_detail', shift_id=shift.id)
    messages.warning(
        request,
        'No shift open for you today. Ask the Chief Cashier to open the working day first.'
    )
    return redirect('dashboard:home')


@login_required
def shift_open(request):
    """Open a new cashier shift for today with an opening cash float."""
    today = timezone.localdate()

    existing = CashierShift.objects.filter(
        cashier=request.user, shift_date=today, is_deleted=False
    ).first()
    if existing:
        messages.info(request, 'You already have a shift open for today.')
        return redirect('billing:shift_detail', shift_id=existing.id)

    if request.method == 'POST':
        try:
            opening_cash = Decimal(request.POST.get('opening_cash', '0') or '0')
        except InvalidOperation:
            opening_cash = Decimal('0')

        shift = CashierShift.objects.create(
            cashier=request.user,
            shift_date=today,
            opening_cash=opening_cash,
            status=ShiftStatus.OPEN,
            created_by=request.user,
        )
        messages.success(
            request,
            f'Shift opened for {today.strftime("%d %b %Y")}. '
            f'Opening float: {int(opening_cash):,} FCFA'
        )
        return redirect('billing:shift_detail', shift_id=shift.id)

    return render(request, 'billing/shift_open.html', {'today': today})


@login_required
def shift_detail(request, shift_id):
    """Shift detail + printable handover slip."""
    shift = get_object_or_404(CashierShift, id=shift_id, is_deleted=False)
    ctx = {
        'shift': shift,
        'today': timezone.localdate(),
    }
    if request.GET.get('format') == 'pdf':
        return _render_pdf(
            'billing/pdf/shift_reconciliation_pdf.html', ctx,
            f'shift_{shift.cashier.username}_{shift.shift_date}.pdf',
        )
    return render(request, 'billing/shift_detail.html', ctx)


@login_required
@require_POST
def shift_close(request, shift_id):
    """Cashier counts cash and closes their shift."""
    shift = get_object_or_404(CashierShift, id=shift_id, is_deleted=False)

    if shift.cashier != request.user:
        messages.error(request, 'You can only close your own shift.')
        return redirect('billing:shift_detail', shift_id=shift.id)
    if shift.status != ShiftStatus.OPEN:
        messages.warning(request, 'This shift is already closed.')
        return redirect('billing:shift_detail', shift_id=shift.id)

    try:
        closing_cash = Decimal(request.POST.get('closing_cash_declared', '0') or '0')
    except InvalidOperation:
        messages.error(request, 'Invalid closing cash amount.')
        return redirect('billing:shift_detail', shift_id=shift.id)

    shift.closing_cash_declared = closing_cash
    shift.closed_at = timezone.now()
    shift.notes = request.POST.get('notes', '').strip()
    shift.status = ShiftStatus.CLOSED
    shift.save(update_fields=['closing_cash_declared', 'closed_at', 'notes', 'status', 'updated_at'])
    messages.success(request, 'Shift closed. Submit it to the Chief Cashier when ready.')
    return redirect('billing:shift_detail', shift_id=shift.id)


@json_error_handler
@login_required
@require_POST
def shift_force_close(request, shift_id):
    """Chief Cashier force-closes any OPEN shift at end of day."""
    from django.http import JsonResponse
    if not _can_open_day(request.user):
        return JsonResponse({'success': False, 'message': 'Not authorized.'}, status=403)
    shift = get_object_or_404(CashierShift, id=shift_id, is_deleted=False)
    if shift.status not in (ShiftStatus.OPEN,):
        return JsonResponse({'success': False, 'message': 'Shift is not open.'})
    shift.status = ShiftStatus.CLOSED
    shift.closed_at = timezone.now()
    shift.notes = f'Force-closed by {request.user.get_full_name() or request.user.username} at end of day.'
    shift.save(update_fields=['status', 'closed_at', 'notes', 'updated_at'])
    return JsonResponse({'success': True, 'cashier': shift.cashier.get_full_name() or shift.cashier.username})


@login_required
@require_POST
def shift_submit(request, shift_id):
    """Cashier submits a closed shift to the Chief Cashier for verification."""
    shift = get_object_or_404(CashierShift, id=shift_id, is_deleted=False)

    if shift.cashier != request.user:
        messages.error(request, 'You can only submit your own shift.')
        return redirect('billing:shift_detail', shift_id=shift.id)
    if shift.status != ShiftStatus.CLOSED:
        messages.error(request, 'Only a closed shift can be submitted.')
        return redirect('billing:shift_detail', shift_id=shift.id)

    shift.status = ShiftStatus.SUBMITTED
    shift.submitted_at = timezone.now()
    shift.save(update_fields=['status', 'submitted_at', 'updated_at'])
    messages.success(request, 'Shift submitted to Chief Cashier for verification.')
    return redirect('billing:shift_detail', shift_id=shift.id)


@login_required
@require_POST
def shift_verify(request, shift_id):
    """Chief Cashier / Supervisor verifies and signs off a submitted shift."""
    shift = get_object_or_404(CashierShift, id=shift_id, is_deleted=False)

    if not _can_verify_shift(request.user):
        messages.error(
            request,
            'Access denied. Only the Chief Cashier or Finance Director can verify shifts.'
        )
        return redirect('billing:shift_detail', shift_id=shift.id)

    if shift.status != ShiftStatus.SUBMITTED:
        messages.error(request, 'Only submitted shifts can be verified.')
        return redirect('billing:shift_detail', shift_id=shift.id)

    shift.status = ShiftStatus.VERIFIED
    shift.verified_by = request.user
    shift.verified_at = timezone.now()
    shift.save(update_fields=['status', 'verified_by', 'verified_at', 'updated_at'])
    messages.success(
        request,
        f'Shift for {shift.cashier.get_full_name() or shift.cashier.username} '
        f'on {shift.shift_date} verified and confirmed.'
    )
    return redirect('billing:shift_detail', shift_id=shift.id)


@login_required
@require_POST
def shift_reopen(request, shift_id):
    """
    Chief Cashier reopens a CLOSED or SUBMITTED shift back to OPEN.
    Use case: shift was accidentally closed before end of day, or Chief Cashier
    needs to allow the cashier to continue collecting payments.
    Only works on the SAME DAY as the shift date — cannot reopen past-day shifts.
    """
    if not _can_verify_shift(request.user):
        messages.error(request, 'Only the Chief Cashier or Finance Director can reopen a shift.')
        return redirect('billing:shift_detail', shift_id=shift_id)

    shift = get_object_or_404(CashierShift, id=shift_id, is_deleted=False)

    if shift.shift_date != timezone.localdate():
        messages.error(request, 'Cannot reopen a shift from a previous day. Contact Super Admin if needed.')
        return redirect('billing:shift_detail', shift_id=shift.id)

    if shift.status == ShiftStatus.OPEN:
        messages.info(request, 'This shift is already open.')
        return redirect('billing:shift_detail', shift_id=shift.id)

    if shift.status == ShiftStatus.VERIFIED:
        messages.error(request, 'A verified shift cannot be reopened. Contact Finance Director if required.')
        return redirect('billing:shift_detail', shift_id=shift.id)

    prev_status = shift.status
    shift.status = ShiftStatus.OPEN
    shift.closed_at = None
    shift.closing_cash_declared = None
    shift.submitted_at = None
    shift.save(update_fields=['status', 'closed_at', 'closing_cash_declared', 'submitted_at', 'updated_at'])

    from apps.accounts.models import UserAuditLog
    UserAuditLog.log(
        user=request.user,
        action=UserAuditLog.Action.UPDATE_RECORD,
        target_model='CashierShift',
        target_id=str(shift.id),
        extra_data={
            'action': 'shift_reopened',
            'cashier': shift.cashier.get_full_name() or shift.cashier.username,
            'shift_date': str(shift.shift_date),
            'previous_status': prev_status,
        },
        request=request,
    )
    messages.success(
        request,
        f"Shift for {shift.cashier.get_full_name() or shift.cashier.username} "
        f"has been reopened. Cashier can now continue collecting payments."
    )
    return redirect('billing:shift_detail', shift_id=shift.id)


@login_required
def shift_list(request):
    """List all cashier shifts — filterable by date, cashier, and status."""
    if not _can_verify_shift(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    from django.core.paginator import Paginator
    from django.contrib.auth import get_user_model
    User = get_user_model()

    date_str = request.GET.get('date', '')
    cashier_id = request.GET.get('cashier', '')
    status_filter = request.GET.get('status', '')

    shifts = CashierShift.objects.filter(is_deleted=False).select_related('cashier', 'verified_by')
    if date_str:
        shifts = shifts.filter(shift_date=date_str)
    if cashier_id:
        shifts = shifts.filter(cashier_id=cashier_id)
    if status_filter:
        shifts = shifts.filter(status=status_filter)

    paginator = Paginator(shifts, 30)
    page_obj = paginator.get_page(request.GET.get('page'))

    today = timezone.localdate()
    my_shift_today = CashierShift.objects.filter(
        cashier=request.user, shift_date=today, is_deleted=False
    ).first()

    # Today's overview (for Billing Agent / Finance panel)
    today_shifts = CashierShift.objects.filter(
        shift_date=today, is_deleted=False
    ).select_related('cashier', 'verified_by').order_by('cashier__first_name')
    today_total = sum(float(s.total_collected) for s in today_shifts)
    today_open_count = today_shifts.filter(status=ShiftStatus.OPEN).count()
    today_submitted_count = today_shifts.filter(status=ShiftStatus.SUBMITTED).count()
    today_verified_count = today_shifts.filter(status=ShiftStatus.VERIFIED).count()

    return render(request, 'billing/shift_list.html', {
        'page_obj': page_obj,
        'paginator': paginator,
        'cashiers': User.objects.filter(is_active=True).order_by('first_name', 'last_name'),
        'statuses': ShiftStatus.choices,
        'filter_date': date_str,
        'filter_cashier': cashier_id,
        'filter_status': status_filter,
        'my_shift_today': my_shift_today,
        'today': today,
        'today_shifts': today_shifts,
        'today_total': today_total,
        'today_open_count': today_open_count,
        'today_submitted_count': today_submitted_count,
        'today_verified_count': today_verified_count,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Waiting Time SLA — API endpoint for workstation alerts
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def waiting_sla_json(request):
    """
    Returns patients who have been waiting > threshold minutes.
    Used by workstation/triage screens to show SLA breach alerts.
    """
    if not _qms_active():
        from django.http import JsonResponse as _JR
        return _JR({'breached': [], 'count': 0})

    from apps.qms.models import QueueToken, TokenStatus
    threshold_minutes = int(request.GET.get('threshold', 30))
    cutoff = timezone.now() - timezone.timedelta(minutes=threshold_minutes)

    breached = QueueToken.objects.filter(
        status=TokenStatus.WAITING,
        issued_at__lte=cutoff,
        token_date=timezone.localdate(),
        is_deleted=False,
    ).select_related('patient').order_by('issued_at')

    data = []
    for t in breached:
        wait_mins = int((timezone.now() - t.issued_at).total_seconds() / 60)
        data.append({
            'token_number': t.display_token_number,
            'patient_name': t.display_name,
            'service_type': t.get_service_type_display(),
            'wait_minutes': wait_mins,
            'tier': t.service_tier,
            'issued_at': t.issued_at.strftime('%H:%M'),
        })

    return JsonResponse({'breached': data, 'count': len(data), 'threshold': threshold_minutes})


# ─────────────────────────────────────────────────────────────────────────────
# Refund Workflow
# ─────────────────────────────────────────────────────────────────────────────
@login_required
@require_POST
def process_refund(request, invoice_id):
    """
    Issue a refund against a paid or partially paid invoice.
    Refund amount may not exceed amount_paid.
    Recorded with reason, method, and processed_by for full audit trail.
    """
    from .models import Refund
    invoice = get_object_or_404(Invoice, id=invoice_id, is_deleted=False)

    if not _can_authorize_billing(request.user):
        messages.error(
            request,
            'Access denied. Only Billing Officers, Finance Director, or Super Admin '
            'can process refunds.'
        )
        return redirect('billing:invoice_detail', invoice_id=invoice.id)

    reason = request.POST.get('refund_reason', '').strip()
    method = request.POST.get('refund_method', PaymentMethod.CASH)
    reference = request.POST.get('refund_reference', '').strip()

    if not reason:
        messages.error(request, 'A refund reason is required.')
        return redirect('billing:invoice_detail', invoice_id=invoice.id)

    try:
        amount = Decimal(request.POST.get('refund_amount', '0') or '0')
    except InvalidOperation:
        messages.error(request, 'Invalid refund amount.')
        return redirect('billing:invoice_detail', invoice_id=invoice.id)

    if amount <= 0:
        messages.error(request, 'Refund amount must be greater than zero.')
        return redirect('billing:invoice_detail', invoice_id=invoice.id)

    if amount > invoice.amount_paid:
        messages.error(
            request,
            f'Refund amount ({int(amount):,} FCFA) exceeds total payments '
            f'({int(invoice.amount_paid):,} FCFA).'
        )
        return redirect('billing:invoice_detail', invoice_id=invoice.id)

    Refund.objects.create(
        invoice=invoice,
        amount=amount,
        reason=reason,
        payment_method=method,
        reference=reference,
        processed_by=request.user,
        created_by=request.user,
    )
    from apps.accounts.models import UserAuditLog
    _log_financial(request, UserAuditLog.Action.DELETE_RECORD, invoice,
                   extra={'refund_amount': str(amount), 'reason': reason, 'method': method})
    # Re-evaluate invoice status after refund
    invoice.update_status()
    messages.success(
        request,
        f'Refund of {int(amount):,} FCFA issued via {method}. Reason: {reason}'
    )
    return redirect('billing:invoice_detail', invoice_id=invoice.id)


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE PRICE MANAGEMENT — Charge Description Master (CDM)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def service_price_list(request):
    """List/manage all service prices in the Charge Master."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    from .models import ServiceTierFilter
    q = request.GET.get('q', '')
    cat = request.GET.get('cat', '')
    tier = request.GET.get('tier', '')
    prices = ServicePrice.objects.filter(is_deleted=False)
    if q:
        prices = prices.filter(Q(name__icontains=q) | Q(code__icontains=q))
    if cat:
        prices = prices.filter(category=cat)
    if tier != '':
        prices = prices.filter(tier=tier)
    prices = prices.order_by('category', 'tier', 'name')
    return render(request, 'billing/service_prices.html', {
        'prices': prices,
        'categories': ServiceCategory.choices,
        'tiers': [('', 'All Tiers')] + [(k, v) for k, v in [
            ('STANDARD', 'Standard Desk'),
            ('FAST_TRACK', 'Fast Track Desk'),
            ('VIP', 'VIP Desk'),
            ('INSURED', 'Insured / HMO Desk'),
        ]],
        'search': q,
        'filter_cat': cat,
        'filter_tier': tier,
    })


@login_required
@require_POST
def service_price_create(request):
    """Create a new service price entry."""
    if not _can_authorize_billing(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:service_price_list')
    name = request.POST.get('name', '').strip()
    category = request.POST.get('category', '').strip()
    price_str = request.POST.get('price', '').strip()
    if not name or not category or not price_str:
        messages.error(request, 'Name, category and price are required.')
        return redirect('billing:service_price_list')
    try:
        price = Decimal(price_str)
    except InvalidOperation:
        messages.error(request, 'Invalid price.')
        return redirect('billing:service_price_list')

    nhis = request.POST.get('nhis_price', '').strip()
    ins  = request.POST.get('insurance_price', '').strip()
    ServicePrice.objects.create(
        name=name,
        code=request.POST.get('code', '').strip(),
        category=category,
        tier=request.POST.get('tier', '').strip(),
        price=price,
        nhis_price=Decimal(nhis) if nhis else None,
        insurance_price=Decimal(ins) if ins else None,
        requires_price_entry=bool(request.POST.get('requires_price_entry')),
        is_active=True,
        created_by=request.user,
    )
    messages.success(request, f'Service "{name}" added to price list.')
    return redirect('billing:service_price_list')


@login_required
@require_POST
def service_price_edit(request, price_id):
    """Edit an existing service price."""
    if not _can_authorize_billing(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)
    sp = get_object_or_404(ServicePrice, id=price_id, is_deleted=False)
    try:
        sp.name     = request.POST.get('name', sp.name).strip()
        sp.category = request.POST.get('category', sp.category).strip()
        sp.tier     = request.POST.get('tier', sp.tier).strip()
        sp.price    = Decimal(request.POST.get('price', str(sp.price)))
        nhis = request.POST.get('nhis_price', '').strip()
        ins  = request.POST.get('insurance_price', '').strip()
        sp.nhis_price      = Decimal(nhis) if nhis else None
        sp.insurance_price = Decimal(ins) if ins else None
        sp.code            = request.POST.get('code', sp.code).strip()
        sp.requires_price_entry = bool(request.POST.get('requires_price_entry'))
        sp.save()
        return JsonResponse({'success': True})
    except (InvalidOperation, Exception) as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@json_error_handler
@login_required
@require_POST
def service_price_toggle(request, price_id):
    """Toggle is_active on a service price."""
    if not _can_authorize_billing(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)
    sp = get_object_or_404(ServicePrice, id=price_id, is_deleted=False)
    sp.is_active = not sp.is_active
    sp.save(update_fields=['is_active', 'updated_at'])
    return JsonResponse({'success': True, 'is_active': sp.is_active})


# ═══════════════════════════════════════════════════════════════════════════════
# EXPENSE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

from .models import Expense, ExpenseCategory


@login_required
def expense_list(request):
    """List all hospital expenses with filters."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    from django.core.paginator import Paginator
    from django.db.models import Sum as _S
    q         = request.GET.get('q', '')
    cat       = request.GET.get('cat', '')
    date_from = request.GET.get('date_from', '')
    date_to   = request.GET.get('date_to', '')
    month_str = request.GET.get('month', '')

    today = timezone.localdate()
    month_start = today.replace(day=1)

    qs = Expense.objects.filter(is_deleted=False).select_related('approved_by', 'created_by')
    if q:
        qs = qs.filter(Q(description__icontains=q) | Q(vendor__icontains=q))
    if cat:
        qs = qs.filter(category=cat)
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    if month_str:
        try:
            from datetime import date as _d
            parts = month_str.split('-')
            mo_start = _d(int(parts[0]), int(parts[1]), 1)
            import calendar
            _, last = calendar.monthrange(mo_start.year, mo_start.month)
            qs = qs.filter(date__gte=mo_start, date__lte=mo_start.replace(day=last))
        except Exception:
            pass

    total_amount = qs.aggregate(t=_S('amount'))['t'] or 0
    by_category  = qs.values('category').annotate(total=_S('amount')).order_by('-total')

    paginator = Paginator(qs.order_by('-date', '-created_at'), 50)
    page_obj  = paginator.get_page(request.GET.get('page'))

    # Month total for quick summary
    month_total = Expense.objects.filter(
        is_deleted=False, date__gte=month_start
    ).aggregate(t=_S('amount'))['t'] or 0

    return render(request, 'billing/expenses.html', {
        'page_obj': page_obj,
        'total_amount': total_amount,
        'by_category': list(by_category),
        'month_total': month_total,
        'categories': ExpenseCategory.choices,
        'payment_methods': PaymentMethod.choices,
        'search': q, 'filter_cat': cat,
        'date_from': date_from, 'date_to': date_to,
        'today': today,
    })


@login_required
@require_POST
def expense_create(request):
    """Record a new expense (Finance / Admin roles only)."""
    if not _can_record_expense(request.user):
        messages.error(request, 'Access denied. Finance or Admin roles required.')
        return redirect('billing:expense_list')
    date_str    = request.POST.get('date', '').strip()
    category    = request.POST.get('category', '').strip()
    description = request.POST.get('description', '').strip()
    amount_str  = request.POST.get('amount', '').strip()
    method      = request.POST.get('payment_method', PaymentMethod.CASH)

    if not description or not category or not amount_str:
        messages.error(request, 'Description, category and amount are required.')
        return redirect('billing:expense_list')
    try:
        amount = Decimal(amount_str)
        if amount <= 0:
            raise ValueError
    except (ValueError, InvalidOperation):
        messages.error(request, 'Enter a valid amount.')
        return redirect('billing:expense_list')

    from datetime import date as _d
    try:
        exp_date = _d.fromisoformat(date_str) if date_str else timezone.localdate()
    except ValueError:
        exp_date = timezone.localdate()

    approved_by_id = request.POST.get('approved_by', '').strip()
    Expense.objects.create(
        date=exp_date,
        category=category,
        description=description,
        amount=amount,
        payment_method=method,
        vendor=request.POST.get('vendor', '').strip(),
        reference=request.POST.get('reference', '').strip(),
        department=request.POST.get('department', '').strip(),
        notes=request.POST.get('notes', '').strip(),
        approved_by_id=approved_by_id or None,
        created_by=request.user,
    )
    messages.success(request, f'Expense of {int(amount):,} FCFA recorded.')
    return redirect('billing:expense_list')


@login_required
@require_POST
def expense_delete(request, expense_id):
    """Soft-delete an expense (Finance Director / Super Admin only)."""
    if not _can_authorize_billing(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:expense_list')
    exp = get_object_or_404(Expense, id=expense_id, is_deleted=False)
    exp.is_deleted = True
    exp.deleted_at = timezone.now()
    exp.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])
    messages.success(request, 'Expense deleted.')
    return redirect('billing:expense_list')


@login_required
@require_POST
def expense_approve(request, expense_id):
    """
    Finance Director (or Super Admin) approves a pending expense.
    Sets approved_by = current user.
    """
    if not _can_view_pl(request.user):
        messages.error(request, 'Access denied. Finance Director only.')
        return redirect('billing:expense_list')
    exp = get_object_or_404(Expense, id=expense_id, is_deleted=False)
    if exp.approved_by:
        messages.info(request, f'Expense already approved by {exp.approved_by.get_full_name()}.')
        return redirect('billing:expense_list')
    exp.approved_by = request.user
    exp.save(update_fields=['approved_by', 'updated_at'])
    messages.success(request, f'Expense "{exp.description}" approved.')
    return redirect('billing:expense_list')


# ═══════════════════════════════════════════════════════════════════════════════
# CORPORATE ACCOUNT MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

from .models import CorporateAccount, CorporateAccountMember


@login_required
def corporate_list(request):
    """List all corporate accounts."""
    accounts = CorporateAccount.objects.filter(is_deleted=False).order_by('name')
    return render(request, 'billing/corporate_list.html', {
        'accounts': accounts,
    })


@login_required
@require_POST
def corporate_create(request):
    """Create a new corporate account."""
    if not _can_authorize_billing(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:corporate_list')
    name = request.POST.get('name', '').strip()
    if not name:
        messages.error(request, 'Account name is required.')
        return redirect('billing:corporate_list')
    try:
        credit_limit = Decimal(request.POST.get('credit_limit', '0') or '0')
        discount_pct = Decimal(request.POST.get('discount_pct', '0') or '0')
        terms        = int(request.POST.get('payment_terms_days', 30) or 30)
    except (InvalidOperation, ValueError):
        credit_limit, discount_pct, terms = Decimal('0'), Decimal('0'), 30

    acc = CorporateAccount.objects.create(
        name=name,
        account_code=request.POST.get('account_code', '').strip() or None,
        contact_name=request.POST.get('contact_name', '').strip(),
        phone=request.POST.get('phone', '').strip(),
        email=request.POST.get('email', '').strip(),
        address=request.POST.get('address', '').strip(),
        credit_limit=credit_limit,
        discount_pct=discount_pct,
        payment_terms_days=terms,
        notes=request.POST.get('notes', '').strip(),
        created_by=request.user,
    )
    messages.success(request, f'Corporate account "{acc.name}" created.')
    return redirect('billing:corporate_detail', account_id=acc.id)


@login_required
def corporate_detail(request, account_id):
    """Detail view: members, outstanding invoices, statement."""
    acc = get_object_or_404(CorporateAccount, id=account_id, is_deleted=False)
    members  = acc.members.filter(is_deleted=False).select_related('patient').order_by(
        'patient__last_name', 'patient__first_name'
    )
    invoices = Invoice.objects.filter(
        corporate_account=acc, is_deleted=False
    ).select_related('patient').order_by('-created_at')[:50]

    # Outstanding by patient
    from django.db.models import Sum as _S
    return render(request, 'billing/corporate_detail.html', {
        'account': acc,
        'members': members,
        'invoices': invoices,
        'payment_methods': PaymentMethod.choices,
    })


@login_required
@require_POST
def corporate_add_member(request, account_id):
    """Link a patient to a corporate account."""
    acc = get_object_or_404(CorporateAccount, id=account_id, is_deleted=False)
    pid = request.POST.get('patient_id', '').strip()
    if not pid:
        messages.error(request, 'Patient ID is required.')
        return redirect('billing:corporate_detail', account_id=acc.id)
    patient = get_object_or_404(Patient, patient_id=pid, is_deleted=False)
    try:
        coverage = Decimal(request.POST.get('coverage_limit', '0') or '0')
    except InvalidOperation:
        coverage = Decimal('0')
    member, created = CorporateAccountMember.objects.get_or_create(
        corporate_account=acc, patient=patient,
        defaults={
            'employee_id': request.POST.get('employee_id', '').strip(),
            'coverage_limit': coverage,
            'is_active': True,
            'created_by': request.user,
        }
    )
    if not created:
        member.is_active = True
        member.save(update_fields=['is_active', 'updated_at'])
    messages.success(request, f'{patient.full_name} added to {acc.name}.')
    return redirect('billing:corporate_detail', account_id=acc.id)


@login_required
@require_POST
def corporate_remove_member(request, member_id):
    """Deactivate a corporate account membership."""
    member = get_object_or_404(CorporateAccountMember, id=member_id, is_deleted=False)
    acc_id = member.corporate_account_id
    member.is_active = False
    member.save(update_fields=['is_active', 'updated_at'])
    messages.info(request, f'{member.patient.full_name} removed from {member.corporate_account.name}.')
    return redirect('billing:corporate_detail', account_id=acc_id)


@login_required
def corporate_statement(request, account_id):
    """
    Generate a printable statement of all outstanding invoices for a corporate account.
    Used for billing the company at month-end.
    """
    from datetime import date as _d
    acc = get_object_or_404(CorporateAccount, id=account_id, is_deleted=False)

    date_from_str = request.GET.get('from', '')
    date_to_str   = request.GET.get('to',   '')
    try:
        date_from = _d.fromisoformat(date_from_str) if date_from_str else None
    except ValueError:
        date_from = None
    try:
        date_to = _d.fromisoformat(date_to_str) if date_to_str else None
    except ValueError:
        date_to = None

    inv_qs = Invoice.objects.filter(
        corporate_account=acc, is_deleted=False
    ).exclude(status__in=[InvoiceStatus.CANCELLED]).select_related('patient').order_by('issue_date')
    if date_from:
        inv_qs = inv_qs.filter(issue_date__gte=date_from)
    if date_to:
        inv_qs = inv_qs.filter(issue_date__lte=date_to)

    invoices_data = []
    grand_total = grand_paid = grand_balance = 0
    for inv in inv_qs:
        invoices_data.append({
            'invoice': inv,
            'total': float(inv.total),
            'paid': float(inv.amount_paid),
            'balance': float(inv.balance_due),
        })
        grand_total   += float(inv.total)
        grand_paid    += float(inv.amount_paid)
        grand_balance += float(inv.balance_due)

    return render(request, 'billing/corporate_statement.html', {
        'account': acc,
        'invoices_data': invoices_data,
        'grand_total': grand_total,
        'grand_paid': grand_paid,
        'grand_balance': grand_balance,
        'date_from': date_from,
        'date_to': date_to,
        'today': timezone.localdate(),
        'HOSPITAL_NAME': __import__('django.conf', fromlist=['settings']).settings.HOSPITAL_NAME,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# PETTY CASH MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

from .models import PettyCashFund, PettyCashEntry


@login_required
def petty_cash_list(request):
    """List all petty cash funds."""
    funds = PettyCashFund.objects.filter(is_deleted=False).select_related('custodian')
    return render(request, 'billing/petty_cash_list.html', {
        'funds': funds,
    })


@login_required
@require_POST
def petty_cash_create(request):
    """Create a new petty cash fund."""
    if not _can_authorize_billing(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:petty_cash_list')
    name = request.POST.get('name', '').strip()
    if not name:
        messages.error(request, 'Fund name is required.')
        return redirect('billing:petty_cash_list')
    try:
        opening = Decimal(request.POST.get('opening_balance', '0') or '0')
    except InvalidOperation:
        opening = Decimal('0')
    from django.contrib.auth import get_user_model
    User = get_user_model()
    custodian_id = request.POST.get('custodian_id', '').strip()
    try:
        custodian = User.objects.get(pk=custodian_id)
    except User.DoesNotExist:
        custodian = request.user
    fund = PettyCashFund.objects.create(
        name=name,
        custodian=custodian,
        opening_balance=opening,
        created_by=request.user,
    )
    messages.success(request, f'Petty cash fund "{fund.name}" created.')
    return redirect('billing:petty_cash_detail', fund_id=fund.id)


@login_required
def petty_cash_detail(request, fund_id):
    """Petty cash fund detail with full transaction history."""
    fund    = get_object_or_404(PettyCashFund, id=fund_id, is_deleted=False)
    entries = fund.entries.filter(is_deleted=False).order_by('-date', '-created_at')
    return render(request, 'billing/petty_cash_detail.html', {
        'fund': fund,
        'entries': entries,
        'expense_categories': ExpenseCategory.choices,
    })


@login_required
@require_POST
def petty_cash_entry(request, fund_id):
    """Add a debit or credit entry to a petty cash fund."""
    fund        = get_object_or_404(PettyCashFund, id=fund_id, is_deleted=False)
    entry_type  = request.POST.get('entry_type', 'DEBIT')
    description = request.POST.get('description', '').strip()
    amount_str  = request.POST.get('amount', '').strip()
    date_str    = request.POST.get('date', '').strip()

    if not description or not amount_str:
        messages.error(request, 'Description and amount are required.')
        return redirect('billing:petty_cash_detail', fund_id=fund.id)
    try:
        amount = Decimal(amount_str)
        if amount <= 0:
            raise ValueError
    except (ValueError, InvalidOperation):
        messages.error(request, 'Enter a valid amount.')
        return redirect('billing:petty_cash_detail', fund_id=fund.id)

    # Prevent overdraft on debit
    if entry_type == 'DEBIT' and amount > fund.current_balance:
        messages.error(
            request,
            f'Insufficient fund balance ({fund.current_balance:,.0f} FCFA). '
            f'Cannot disburse {amount:,.0f} FCFA.'
        )
        return redirect('billing:petty_cash_detail', fund_id=fund.id)

    from datetime import date as _d
    try:
        entry_date = _d.fromisoformat(date_str) if date_str else timezone.localdate()
    except ValueError:
        entry_date = timezone.localdate()

    PettyCashEntry.objects.create(
        fund=fund,
        entry_type=entry_type,
        date=entry_date,
        description=description,
        amount=amount,
        category=request.POST.get('category', '').strip(),
        reference=request.POST.get('reference', '').strip(),
        created_by=request.user,
    )
    action = 'disbursed from' if entry_type == 'DEBIT' else 'added to'
    messages.success(request, f'{int(amount):,} FCFA {action} {fund.name}.')
    return redirect('billing:petty_cash_detail', fund_id=fund.id)


# ═══════════════════════════════════════════════════════════════════════════════
# FINANCIAL REPORTS
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def report_daily_summary(request):
    """
    Daily Cash Summary — full cashier handover report for a given date.
    Shows revenue by method, expenses, refunds, and net position.
    """
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied. Finance and management roles only.')
        return redirect('billing:dashboard')
    from datetime import date as _d, timedelta as _td
    from django.db.models import Sum as _S

    date_str = request.GET.get('date', '')
    try:
        report_date = _d.fromisoformat(date_str)
    except (ValueError, TypeError):
        report_date = timezone.localdate()

    # Revenue collected
    payments = Payment.objects.filter(
        payment_date__date=report_date, is_deleted=False
    ).select_related('invoice__patient', 'received_by')

    revenue_total = payments.aggregate(t=_S('amount'))['t'] or 0
    revenue_by_method = (
        payments.values('payment_method')
        .annotate(total=_S('amount'))
        .order_by('-total')
    )

    # Revenue by service category
    # Use distinct invoice IDs that received payment today to avoid duplicate joins
    from django.db.models import F as _F, ExpressionWrapper, DecimalField as _DC
    paid_invoice_ids = Payment.objects.filter(
        payment_date__date=report_date, is_deleted=False
    ).values_list('invoice_id', flat=True).distinct()

    revenue_by_cat = (
        InvoiceItem.objects.filter(
            invoice_id__in=paid_invoice_ids,
            is_deleted=False,
        ).values('category')
        .annotate(total=_S(
            ExpressionWrapper(_F('unit_price') * _F('quantity'),
                              output_field=_DC(max_digits=14, decimal_places=2))
        ))
        .order_by('-total')
    )

    # Refunds
    from .models import Refund
    refunds = Refund.objects.filter(refund_date__date=report_date, is_deleted=False)
    refund_total = refunds.aggregate(t=_S('amount'))['t'] or 0

    # Expenses
    expenses = Expense.objects.filter(date=report_date, is_deleted=False)
    expense_total = expenses.aggregate(t=_S('amount'))['t'] or 0
    expense_by_cat = expenses.values('category').annotate(total=_S('amount')).order_by('-total')

    # New invoices created today
    invoices_created = Invoice.objects.filter(
        created_at__date=report_date, is_deleted=False
    ).count()
    invoices_paid = Invoice.objects.filter(
        created_at__date=report_date, status=InvoiceStatus.PAID, is_deleted=False
    ).count()

    # Cashier breakdown
    from django.contrib.auth import get_user_model
    cashier_rows = (
        payments.values('received_by__first_name', 'received_by__last_name', 'received_by__username')
        .annotate(total=_S('amount'))
        .order_by('-total')
    )

    net_revenue = float(revenue_total) - float(refund_total)
    net_position = net_revenue - float(expense_total)

    ctx = {
        'report_date': report_date,
        'prev_date': (report_date - _td(days=1)).isoformat(),
        'next_date': (report_date + _td(days=1)).isoformat(),
        'revenue_total': revenue_total,
        'revenue_by_method': list(revenue_by_method),
        'revenue_by_cat': list(revenue_by_cat),
        'refund_total': refund_total,
        'refunds': refunds,
        'expense_total': expense_total,
        'expense_by_cat': list(expense_by_cat),
        'expenses': expenses,
        'net_revenue': net_revenue,
        'net_position': net_position,
        'invoices_created': invoices_created,
        'invoices_paid': invoices_paid,
        'cashier_rows': list(cashier_rows),
        'payment_method_labels': dict(PaymentMethod.choices),
        'cat_labels': dict(ServiceCategory.choices),
        'expense_cat_labels': dict(ExpenseCategory.choices),
        'payments': payments.order_by('payment_date'),
    }
    if request.GET.get('format') == 'pdf':
        return _render_pdf(
            'billing/pdf/daily_summary_pdf.html', ctx,
            f'daily_summary_{report_date}.pdf',
        )
    return render(request, 'billing/reports/daily_summary.html', ctx)


@login_required
def report_pl(request):
    """
    Monthly Profit & Loss — Revenue minus Expenses for a selected month.
    Essential for Finance Director / CEO.
    """
    if not _can_view_pl(request.user):
        messages.error(request, 'Access denied. Finance Director and senior management only.')
        return redirect('billing:dashboard')
    from datetime import date as _d
    import calendar
    from django.db.models import Sum as _S, F as _F, ExpressionWrapper, DecimalField as _D

    today = timezone.localdate()
    month_str = request.GET.get('month', today.strftime('%Y-%m'))
    try:
        parts = month_str.split('-')
        yr, mo = int(parts[0]), int(parts[1])
    except Exception:
        yr, mo = today.year, today.month

    _, last_day = calendar.monthrange(yr, mo)
    mo_start = _d(yr, mo, 1)
    mo_end   = _d(yr, mo, last_day)

    # Revenue: sum of payments
    rev_total = Payment.objects.filter(
        payment_date__date__gte=mo_start,
        payment_date__date__lte=mo_end,
        is_deleted=False,
    ).aggregate(t=_S('amount'))['t'] or 0

    # Refunds
    from .models import Refund
    ref_total = Refund.objects.filter(
        refund_date__date__gte=mo_start,
        refund_date__date__lte=mo_end,
        is_deleted=False,
    ).aggregate(t=_S('amount'))['t'] or 0

    net_revenue = float(rev_total) - float(ref_total)

    # Revenue by service category
    rev_by_cat = InvoiceItem.objects.filter(
        invoice__is_deleted=False,
        invoice__status__in=[InvoiceStatus.PAID, InvoiceStatus.PARTIALLY_PAID],
        invoice__created_at__date__gte=mo_start,
        invoice__created_at__date__lte=mo_end,
        is_deleted=False,
    ).values('category').annotate(
        total=_S(ExpressionWrapper(_F('unit_price') * _F('quantity'), output_field=_D(max_digits=14, decimal_places=2)))
    ).order_by('-total')

    # Revenue by payment method
    rev_by_method = Payment.objects.filter(
        payment_date__date__gte=mo_start,
        payment_date__date__lte=mo_end,
        is_deleted=False,
    ).values('payment_method').annotate(total=_S('amount')).order_by('-total')

    # Expenses
    exp_total = Expense.objects.filter(
        date__gte=mo_start, date__lte=mo_end, is_deleted=False
    ).aggregate(t=_S('amount'))['t'] or 0

    exp_by_cat = Expense.objects.filter(
        date__gte=mo_start, date__lte=mo_end, is_deleted=False
    ).values('category').annotate(total=_S('amount')).order_by('-total')

    gross_profit = net_revenue - float(exp_total)

    # Invoiced vs collected
    invoiced_total = InvoiceItem.objects.filter(
        invoice__is_deleted=False,
        invoice__created_at__date__gte=mo_start,
        invoice__created_at__date__lte=mo_end,
        is_deleted=False,
    ).aggregate(
        t=_S(ExpressionWrapper(_F('unit_price') * _F('quantity'), output_field=_D(max_digits=14, decimal_places=2)))
    )['t'] or 0

    # Month navigation
    if mo == 1:
        prev_month = f'{yr-1}-12'
    else:
        prev_month = f'{yr}-{mo-1:02d}'
    if mo == 12:
        next_month = f'{yr+1}-01'
    else:
        next_month = f'{yr}-{mo+1:02d}'

    ctx = {
        'month_label': mo_start.strftime('%B %Y'),
        'mo_start': mo_start, 'mo_end': mo_end,
        'rev_total': rev_total,
        'ref_total': ref_total,
        'net_revenue': net_revenue,
        'rev_by_cat': list(rev_by_cat),
        'rev_by_method': list(rev_by_method),
        'exp_total': exp_total,
        'exp_by_cat': list(exp_by_cat),
        'gross_profit': gross_profit,
        'invoiced_total': invoiced_total,
        'month_str': month_str,
        'prev_month': prev_month,
        'next_month': next_month,
        'today': today,
        'cat_labels': dict(ServiceCategory.choices),
        'exp_cat_labels': dict(ExpenseCategory.choices),
        'method_labels': dict(PaymentMethod.choices),
    }
    if request.GET.get('format') == 'pdf':
        return _render_pdf(
            'billing/pdf/pl_pdf.html', ctx,
            f'pl_report_{month_str}.pdf',
        )
    return render(request, 'billing/reports/pl.html', ctx)


@login_required
def report_top_services(request):
    """Revenue by service / top-earning services for a given period."""
    if not _can_view_pl(request.user):
        messages.error(request, 'Access denied. Finance Director and senior management only.')
        return redirect('billing:dashboard')
    from datetime import date as _d
    import calendar
    from django.db.models import Sum as _S, F as _F, ExpressionWrapper, DecimalField as _D, Count

    today    = timezone.localdate()
    date_from_str = request.GET.get('from', today.replace(day=1).isoformat())
    date_to_str   = request.GET.get('to',   today.isoformat())
    try:
        date_from = _d.fromisoformat(date_from_str)
        date_to   = _d.fromisoformat(date_to_str)
    except ValueError:
        date_from = today.replace(day=1)
        date_to   = today

    qs = InvoiceItem.objects.filter(
        invoice__is_deleted=False,
        invoice__status__in=[InvoiceStatus.PAID, InvoiceStatus.PARTIALLY_PAID],
        invoice__created_at__date__gte=date_from,
        invoice__created_at__date__lte=date_to,
        is_deleted=False,
    ).values('description', 'category').annotate(
        revenue=_S(ExpressionWrapper(_F('unit_price') * _F('quantity'), output_field=_D(max_digits=14, decimal_places=2))),
        count=Count('id'),
    ).order_by('-revenue')[:50]

    by_cat = InvoiceItem.objects.filter(
        invoice__is_deleted=False,
        invoice__status__in=[InvoiceStatus.PAID, InvoiceStatus.PARTIALLY_PAID],
        invoice__created_at__date__gte=date_from,
        invoice__created_at__date__lte=date_to,
        is_deleted=False,
    ).values('category').annotate(
        revenue=_S(ExpressionWrapper(_F('unit_price') * _F('quantity'), output_field=_D(max_digits=14, decimal_places=2))),
        count=Count('id'),
    ).order_by('-revenue')

    total_revenue = sum(float(r['revenue']) for r in qs)

    ctx = {
        'services': list(qs),
        'by_cat': list(by_cat),
        'total_revenue': total_revenue,
        'date_from': date_from,
        'date_to': date_to,
        'date_from_str': date_from_str,
        'date_to_str': date_to_str,
        'cat_labels': dict(ServiceCategory.choices),
        'today': today,
    }
    if request.GET.get('format') == 'pdf':
        return _render_pdf(
            'billing/pdf/top_services_pdf.html', ctx,
            f'top_services_{date_from_str}_{date_to_str}.pdf',
        )
    return render(request, 'billing/reports/top_services.html', ctx)


# ═══════════════════════════════════════════════════════════════════════════════
# BUDGET MODULE
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def budget_list(request):
    """Budget vs Actual dashboard — Finance Director / CEO only."""
    if not _can_view_pl(request.user):
        messages.error(request, 'Access denied. Finance Director and senior management only.')
        return redirect('billing:dashboard')

    import calendar
    from datetime import date as _d
    from django.db.models import Sum as _S, F as _F, ExpressionWrapper, DecimalField as _D

    today = timezone.localdate()
    month_str = request.GET.get('month', today.strftime('%Y-%m'))
    try:
        yr, mo = int(month_str.split('-')[0]), int(month_str.split('-')[1])
    except Exception:
        yr, mo = today.year, today.month

    _, last_day = calendar.monthrange(yr, mo)
    mo_start = _d(yr, mo, 1)
    mo_end   = _d(yr, mo, last_day)

    # Revenue actuals by category
    rev_actual = {
        row['category']: float(row['total'])
        for row in InvoiceItem.objects.filter(
            invoice__is_deleted=False,
            invoice__status__in=[InvoiceStatus.PAID, InvoiceStatus.PARTIALLY_PAID],
            invoice__created_at__date__gte=mo_start,
            invoice__created_at__date__lte=mo_end,
            is_deleted=False,
        ).values('category').annotate(
            total=_S(ExpressionWrapper(_F('unit_price') * _F('quantity'), output_field=_D(max_digits=14, decimal_places=2)))
        )
    }

    # Expense actuals by category
    from .models import Expense, ExpenseCategory
    exp_actual = {
        row['category']: float(row['total'])
        for row in Expense.objects.filter(
            date__gte=mo_start, date__lte=mo_end, is_deleted=False
        ).values('category').annotate(total=_S('amount'))
    }

    # Budgets for this month
    budgets = Budget.objects.filter(year=yr, month=mo, is_deleted=False).order_by('budget_type', 'category')

    # Build comparison rows
    budget_rows = []
    total_rev_budget = total_rev_actual = 0
    total_exp_budget = total_exp_actual = 0
    for b in budgets:
        if b.budget_type == BudgetType.REVENUE:
            actual = rev_actual.get(b.category, 0)
            total_rev_budget += float(b.budgeted_amount)
            total_rev_actual += actual
        else:
            actual = exp_actual.get(b.category, 0)
            total_exp_budget += float(b.budgeted_amount)
            total_exp_actual += actual
        variance = actual - float(b.budgeted_amount)
        pct = (actual / float(b.budgeted_amount) * 100) if b.budgeted_amount else 0
        budget_rows.append({
            'budget': b,
            'actual': actual,
            'variance': variance,
            'pct': round(pct, 1),
            'over': variance > 0 and b.budget_type == BudgetType.EXPENSE,
            'under_rev': variance < 0 and b.budget_type == BudgetType.REVENUE,
        })

    # Month navigation
    if mo == 1:
        prev_month = f'{yr-1}-12'
        next_month = f'{yr}-02'
    elif mo == 12:
        prev_month = f'{yr}-11'
        next_month = f'{yr+1}-01'
    else:
        prev_month = f'{yr}-{mo-1:02d}'
        next_month = f'{yr}-{mo+1:02d}'

    return render(request, 'billing/budget.html', {
        'budget_rows': budget_rows,
        'month_label': mo_start.strftime('%B %Y'),
        'month_str': month_str,
        'prev_month': prev_month,
        'next_month': next_month,
        'total_rev_budget': total_rev_budget,
        'total_rev_actual': total_rev_actual,
        'total_exp_budget': total_exp_budget,
        'total_exp_actual': total_exp_actual,
        'budget_types': BudgetType.choices,
        'service_categories': ServiceCategory.choices,
        'expense_categories': ExpenseCategory.choices,
        'today': today,
    })


@login_required
@require_POST
def budget_create(request):
    """Add a new budget line (Finance Director only)."""
    if not _can_view_pl(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:budget_list')
    try:
        yr  = int(request.POST.get('year', timezone.localdate().year))
        mo  = int(request.POST.get('month', timezone.localdate().month))
        amt = Decimal(request.POST.get('budgeted_amount', '0') or '0')
    except (ValueError, InvalidOperation):
        messages.error(request, 'Invalid year, month or amount.')
        return redirect('billing:budget_list')

    Budget.objects.update_or_create(
        year=yr,
        month=mo,
        budget_type=request.POST.get('budget_type', BudgetType.REVENUE),
        category=request.POST.get('category', '').strip(),
        department=request.POST.get('department', '').strip(),
        defaults={
            'budgeted_amount': amt,
            'notes': request.POST.get('notes', '').strip(),
            'created_by': request.user,
        },
    )
    messages.success(request, 'Budget line saved.')
    month_str = f'{yr}-{mo:02d}'
    return redirect(f"{request.path.replace('create/', '')}?month={month_str}")


@login_required
@require_POST
def budget_delete(request, budget_id):
    """Delete a budget line (Finance Director only)."""
    if not _can_view_pl(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:budget_list')
    b = get_object_or_404(Budget, id=budget_id, is_deleted=False)
    month_str = f'{b.year}-{b.month:02d}'
    b.is_deleted = True
    b.deleted_at = timezone.now()
    b.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])
    messages.success(request, 'Budget line deleted.')
    from django.urls import reverse
    return redirect(f"{reverse('billing:budget_list')}?month={month_str}")


# ═══════════════════════════════════════════════════════════════════════════════
# CASHIER RECONCILIATION REPORT
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def cashier_reconciliation(request):
    """
    End-of-day cashier reconciliation.
    For each cashier who worked on the selected date, compare:
      - System total collected (from Payment records)
      - Cash declared by cashier (from CashierShift.closing_cash_declared)
      - Expected cash in drawer (opening float + cash collected)
      - Variance (declared - expected) — positive = overage, negative = shortage
    Only Chief Cashier, Billing Officer, Finance Director, and Management can view.
    """
    if not (_can_verify_shift(request.user) or _can_authorize_billing(request.user)):
        messages.error(request, 'Access denied. Chief Cashier, Billing Officers and Finance only.')
        return redirect('billing:dashboard')

    from datetime import date as _d, timedelta as _td
    from django.db.models import Sum as _S

    date_str = request.GET.get('date', '')
    try:
        report_date = _d.fromisoformat(date_str)
    except (ValueError, TypeError):
        report_date = timezone.localdate()

    prev_date = (report_date - _td(days=1)).isoformat()
    next_date = (report_date + _td(days=1)).isoformat()

    # All cashier shifts for this date
    shifts = CashierShift.objects.filter(
        shift_date=report_date, is_deleted=False
    ).select_related('cashier', 'verified_by').order_by('cashier__first_name')

    rows = []
    total_system  = 0
    total_cash_sys = 0
    total_declared = 0
    total_variance = 0
    unsubmitted_count = 0

    for shift in shifts:
        sys_total   = float(shift.total_collected)
        cash_sys    = float(shift.cash_collected)
        expected    = float(shift.expected_cash_in_hand)
        declared    = float(shift.closing_cash_declared) if shift.closing_cash_declared is not None else None
        variance    = (declared - expected) if declared is not None else None

        total_system   += sys_total
        total_cash_sys += cash_sys
        if declared is not None:
            total_declared += declared
        if variance is not None:
            total_variance += variance
        if shift.status not in (ShiftStatus.SUBMITTED, ShiftStatus.VERIFIED):
            unsubmitted_count += 1

        # Collections by method for this cashier
        by_method = dict(
            Payment.objects.filter(
                received_by=shift.cashier,
                payment_date__date=report_date,
                is_deleted=False,
            ).values('payment_method').annotate(t=_S('amount')).values_list('payment_method', 't')
        )

        rows.append({
            'shift': shift,
            'cashier': shift.cashier,
            'sys_total': sys_total,
            'cash_sys': cash_sys,
            'expected': expected,
            'declared': declared,
            'variance': variance,
            'txn_count': shift.transaction_count,
            'by_method': by_method,
            'status': shift.status,
            'clean': variance == 0 if variance is not None else None,
        })

    # Payments with NO shift (cashier forgot to open shift — orphaned payments)
    cashier_ids_with_shift = [s.cashier_id for s in shifts]
    orphan_payments = Payment.objects.filter(
        payment_date__date=report_date,
        is_deleted=False,
    ).exclude(received_by_id__in=cashier_ids_with_shift).select_related('received_by', 'invoice__patient')

    orphan_total = float(orphan_payments.aggregate(t=_S('amount'))['t'] or 0)

    grand_total = total_system + orphan_total

    return render(request, 'billing/cashier_reconciliation.html', {
        'report_date': report_date,
        'prev_date': prev_date,
        'next_date': next_date,
        'rows': rows,
        'total_system': total_system,
        'total_cash_sys': total_cash_sys,
        'total_declared': total_declared,
        'total_variance': total_variance,
        'unsubmitted_count': unsubmitted_count,
        'orphan_payments': orphan_payments,
        'orphan_total': orphan_total,
        'grand_total': grand_total,
        'method_labels': dict(PaymentMethod.choices),
        'shift_count': shifts.count(),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# AR AGING REPORT
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def ar_aging_report(request):
    """
    Accounts Receivable Aging Report.
    Shows all unpaid / partially-paid invoices grouped by how overdue they are:
      Current (0-30 days), 31-60 days, 61-90 days, 90+ days.
    Finance Director, Billing Officer, CEO, Medical Director.
    """
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')

    from datetime import date as _d
    from django.db.models import Sum as _S

    today = timezone.localdate()

    # All outstanding invoices — prefetch to avoid N+1 on balance_due/total/amount_paid
    from django.db.models import Prefetch as _Pf3
    outstanding = Invoice.objects.filter(
        status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
        is_deleted=False,
    ).select_related('patient', 'corporate_account').prefetch_related(
        _Pf3('items', queryset=InvoiceItem.objects.filter(is_deleted=False), to_attr='_items_cache'),
        _Pf3('payments', queryset=Payment.objects.filter(is_deleted=False), to_attr='_payments_cache'),
        _Pf3('refunds', queryset=Refund.objects.filter(is_deleted=False), to_attr='_refunds_cache'),
    ).order_by('issue_date')

    buckets = {
        'current':  {'label': 'Current (0–30 days)',   'rows': [], 'total': 0},
        'days31':   {'label': '31–60 days overdue',    'rows': [], 'total': 0},
        'days61':   {'label': '61–90 days overdue',    'rows': [], 'total': 0},
        'days90':   {'label': '90+ days overdue',      'rows': [], 'total': 0},
    }

    grand_total = 0
    for inv in outstanding:
        age = (today - inv.issue_date).days
        balance = float(inv.balance_due)
        if balance <= 0:
            continue
        grand_total += balance
        row = {
            'invoice': inv,
            'patient': inv.patient,
            'age_days': age,
            'balance': balance,
            'total': float(inv.total),
            'paid': float(inv.amount_paid),
        }
        if age <= 30:
            buckets['current']['rows'].append(row)
            buckets['current']['total'] += balance
        elif age <= 60:
            buckets['days31']['rows'].append(row)
            buckets['days31']['total'] += balance
        elif age <= 90:
            buckets['days61']['rows'].append(row)
            buckets['days61']['total'] += balance
        else:
            buckets['days90']['rows'].append(row)
            buckets['days90']['total'] += balance

    # Corporate AR summary — single query via annotation instead of per-account loops
    from .models import CorporateAccount
    from django.db.models import OuterRef, Subquery, DecimalField as _DFld, Value as _Val
    from django.db.models.functions import Coalesce as _Coalesce
    # Aggregate paid + refunds per invoice via Python (invoices already prefetched above)
    corp_balances: dict = {}
    for inv in outstanding:
        if inv.corporate_account_id:
            b = float(inv.balance_due)
            if b > 0:
                corp_balances[inv.corporate_account_id] = corp_balances.get(inv.corporate_account_id, 0) + b
    corp_ids = list(corp_balances.keys())
    corp_map = {c.id: c for c in CorporateAccount.objects.filter(id__in=corp_ids, is_active=True, is_deleted=False)}
    corporate_ar = sorted(
        [{'account': corp_map[cid], 'balance': bal} for cid, bal in corp_balances.items() if cid in corp_map],
        key=lambda x: x['balance'], reverse=True,
    )

    ctx = {
        'today': today,
        'buckets': buckets,
        'grand_total': grand_total,
        'corporate_ar': corporate_ar,
        'bucket_order': ['current', 'days31', 'days61', 'days90'],
    }
    if request.GET.get('format') == 'pdf':
        return _render_pdf('billing/pdf/ar_aging_pdf.html', ctx, f'ar_aging_{today}.pdf')
    return render(request, 'billing/ar_aging.html', ctx)


# ═══════════════════════════════════════════════════════════════════════════════
# INSURANCE AMOUNT — AJAX endpoint to set insurance split on an invoice
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def invoice_set_insurance(request, invoice_id):
    """AJAX: Set the insurance coverage amount on an invoice."""
    invoice = get_object_or_404(Invoice, id=invoice_id, is_deleted=False)
    try:
        ins = Decimal(request.POST.get('insurance_amount', '0') or '0')
    except InvalidOperation:
        return JsonResponse({'success': False, 'error': 'Invalid amount.'}, status=400)
    if ins < 0:
        return JsonResponse({'success': False, 'error': 'Amount cannot be negative.'}, status=400)
    if ins > invoice.total:
        ins = invoice.total
    invoice.insurance_amount = ins
    invoice.save(update_fields=['insurance_amount', 'updated_at'])
    return JsonResponse({
        'success': True,
        'insurance_amount': int(ins),
        'patient_amount': int(invoice.patient_amount),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# ALL-CASHDESKS OVERVIEW — TurboClinic "Consult Cashdesks"
# Supervisor sees every cashier's live balance in one screen
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def cashdesks_overview(request):
    """
    Live overview of ALL cashier desks for today.
    Shows each cashier's shift status, cash collected, and balance.
    Access: Chief Cashier, Billing Officer, Finance Director, Admin, Super Admin.
    """
    if not _can_verify_shift(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')

    from django.db.models import Sum as _S
    today = timezone.localdate()

    shifts = CashierShift.objects.filter(
        shift_date=today, is_deleted=False
    ).select_related('cashier', 'verified_by').order_by('cashier__username')

    # Cashiers who collected money today but have no shift opened
    cashier_ids_with_shift = set(shifts.values_list('cashier_id', flat=True))
    orphan_cashiers = (
        Payment.objects.filter(payment_date__date=today, is_deleted=False)
        .exclude(received_by_id__in=cashier_ids_with_shift)
        .values('received_by__id', 'received_by__first_name', 'received_by__last_name')
        .annotate(total=_S('amount'))
    )

    # Pre-aggregate all today's payments by cashier+method in one query (avoids N+1)
    _method_map = dict(PaymentMethod.choices)
    cashier_ids = [s.cashier_id for s in shifts]
    all_payments = (
        Payment.objects.filter(
            received_by_id__in=cashier_ids,
            payment_date__date=today,
            is_deleted=False,
        ).values('received_by_id', 'payment_method').annotate(t=_S('amount'))
    )
    # Build {cashier_id: {method_label: amount}}
    by_cashier: dict = {}
    for row in all_payments:
        cid = row['received_by_id']
        label = _method_map.get(row['payment_method'], row['payment_method'])
        by_cashier.setdefault(cid, {})[label] = float(row['t'])

    desk_rows = []
    grand_total = 0
    grand_cash = 0
    for shift in shifts:
        by_method = by_cashier.get(shift.cashier_id, {})
        row = {
            'shift': shift,
            'cashier': shift.cashier,
            'total_collected': float(shift.total_collected),
            'cash_collected': float(shift.cash_collected),
            'expected_cash': float(shift.expected_cash_in_hand),
            'txn_count': shift.transaction_count,
            'status': shift.status,
            'by_method': by_method,
        }
        desk_rows.append(row)
        grand_total += float(shift.total_collected)
        grand_cash  += float(shift.cash_collected)

    return render(request, 'billing/cashdesks_overview.html', {
        'desk_rows': desk_rows,
        'orphan_cashiers': list(orphan_cashiers),
        'grand_total': grand_total,
        'grand_cash': grand_cash,
        'today': today,
        'method_labels': dict(PaymentMethod.choices),
        'ShiftStatus': ShiftStatus,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# SALES JOURNAL — TurboClinic "Edition Journal de Vente"
# Filterable by cashier, date range — daily audit tool
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def sales_journal(request):
    """
    Sales journal: all invoices in a date range with line items and payments.
    Filter by cashier, date from/to.
    Export-ready layout (printable).
    Access: Chief Cashier and above.
    """
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')

    from datetime import date as _d
    from django.db.models import Sum as _S
    from apps.accounts.models import User as _User

    today = timezone.localdate()
    date_from_str = request.GET.get('date_from', today.isoformat())
    date_to_str   = request.GET.get('date_to',   today.isoformat())
    cashier_id    = request.GET.get('cashier', '')

    try:
        date_from = _d.fromisoformat(date_from_str)
        date_to   = _d.fromisoformat(date_to_str)
    except (ValueError, TypeError):
        date_from = date_to = today

    # Base payment queryset — prefetch invoice sub-relations to avoid N+1 on total/subtotal
    from django.db.models import Prefetch as _Pf4
    pay_qs = Payment.objects.filter(
        payment_date__date__gte=date_from,
        payment_date__date__lte=date_to,
        is_deleted=False,
    ).select_related('invoice__patient', 'received_by').prefetch_related(
        _Pf4('invoice__items', queryset=InvoiceItem.objects.filter(is_deleted=False), to_attr='_items_cache'),
        _Pf4('invoice__payments', queryset=Payment.objects.filter(is_deleted=False), to_attr='_payments_cache'),
        _Pf4('invoice__refunds', queryset=Refund.objects.filter(is_deleted=False), to_attr='_refunds_cache'),
    )

    if cashier_id:
        pay_qs = pay_qs.filter(received_by_id=cashier_id)

    # Group payments by invoice for the journal view
    journal_rows = []
    seen_invoices = {}
    for p in pay_qs.order_by('payment_date'):
        inv = p.invoice
        key = str(inv.id)
        if key not in seen_invoices:
            seen_invoices[key] = {
                'invoice': inv,
                'patient': inv.patient,
                'payments': [],
                'total_paid': 0,
                'insurance_amount': float(inv.insurance_amount),
                'patient_amount': float(inv.patient_amount),
                'date': p.payment_date.date(),
                'cashier': p.received_by,
            }
            journal_rows.append(seen_invoices[key])
        seen_invoices[key]['payments'].append(p)
        seen_invoices[key]['total_paid'] += float(p.amount)

    # Totals — resolve label server-side so template never sees the raw key
    _method_map = dict(PaymentMethod.choices)
    totals_by_method = [
        {
            'payment_method': row['payment_method'],
            'label': _method_map.get(row['payment_method'], row['payment_method']),
            'total': row['total'],
        }
        for row in (
            pay_qs.values('payment_method')
            .annotate(total=_S('amount'))
            .order_by('-total')
        )
    ]
    grand_total = pay_qs.aggregate(t=_S('amount'))['t'] or 0
    grand_insurance = Invoice.objects.filter(
        payments__payment_date__date__gte=date_from,
        payments__payment_date__date__lte=date_to,
        payments__is_deleted=False,
    ).aggregate(t=_S('insurance_amount'))['t'] or 0

    # Cashier list for filter dropdown
    cashiers = _User.objects.filter(
        payments_received__payment_date__date__gte=date_from,
        payments_received__payment_date__date__lte=date_to,
        payments_received__is_deleted=False,
    ).distinct().order_by('first_name')

    return render(request, 'billing/sales_journal.html', {
        'journal_rows': journal_rows,
        'totals_by_method': list(totals_by_method),
        'grand_total': float(grand_total),
        'grand_insurance': float(grand_insurance),
        'grand_patient': float(grand_total) - float(grand_insurance),
        'date_from': date_from,
        'date_to': date_to,
        'date_from_str': date_from_str,
        'date_to_str': date_to_str,
        'cashiers': cashiers,
        'selected_cashier': cashier_id,
        'today': today,
        'method_labels': dict(PaymentMethod.choices),
        'row_count': len(journal_rows),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# PROFORMA INVOICE VIEWS
# ═══════════════════════════════════════════════════════════════════════════════

from .models import Proforma, ProformaItem, ProformaStatus


@login_required
def proforma_list(request):
    """List proforma invoices with status filter."""
    from django.core.paginator import Paginator
    status_f = request.GET.get('status', '')
    q        = request.GET.get('q', '')

    qs = Proforma.objects.filter(is_deleted=False).select_related('patient', 'issued_by')
    if status_f:
        qs = qs.filter(status=status_f)
    if q:
        from apps.core.utils import patient_search_q
        qs = qs.filter(
            Q(proforma_number__icontains=q) | patient_search_q(q, prefix='patient__')
        )

    paginator = Paginator(qs, 25)
    page_obj  = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'billing/proforma_list.html', {
        'page_obj': page_obj,
        'status_f': status_f,
        'q': q,
        'statuses': ProformaStatus.choices,
        'today': timezone.localdate(),
    })


@login_required
def proforma_create(request):
    """Create a new proforma invoice for a patient."""
    from apps.patients.models import Patient as _Patient

    patient_id = request.GET.get('patient', '') or request.POST.get('patient', '')
    patient = None
    if patient_id:
        patient = _Patient.objects.filter(patient_id=patient_id, is_deleted=False).first()

    service_catalog = ServicePrice.objects.filter(is_active=True, is_deleted=False).order_by('category', 'name')

    if request.method == 'POST':
        if not patient:
            messages.error(request, 'Patient not found.')
            return redirect('billing:proforma_list')

        try:
            ins = Decimal(request.POST.get('insurance_amount', '0') or '0')
        except InvalidOperation:
            ins = Decimal('0')

        pro = Proforma.objects.create(
            patient=patient,
            issued_by=request.user,
            status=ProformaStatus.ISSUED,
            insurance_amount=ins,
            notes=request.POST.get('notes', '').strip(),
            valid_days=int(request.POST.get('valid_days', 3) or 3),
            created_by=request.user,
        )

        # Parse line items: description[], category[], qty[], unit_price[]
        descriptions = request.POST.getlist('description[]')
        categories   = request.POST.getlist('category[]')
        quantities   = request.POST.getlist('qty[]')
        prices       = request.POST.getlist('unit_price[]')

        for desc, cat, qty_s, price_s in zip(descriptions, categories, quantities, prices):
            desc = desc.strip()
            if not desc:
                continue
            try:
                qty   = int(qty_s) if qty_s else 1
                price = Decimal(price_s) if price_s else Decimal('0')
            except (ValueError, InvalidOperation):
                continue
            ProformaItem.objects.create(
                proforma=pro,
                category=cat,
                description=desc,
                quantity=max(qty, 1),
                unit_price=price,
                created_by=request.user,
            )

        messages.success(request, f'Proforma {pro.proforma_number} created.')
        return redirect('billing:proforma_detail', proforma_id=pro.id)

    return render(request, 'billing/proforma_create.html', {
        'patient': patient,
        'service_catalog': service_catalog,
        'categories': ServiceCategory.choices,
        'today': timezone.localdate(),
    })


@login_required
def proforma_detail(request, proforma_id):
    """View a proforma invoice — print or convert to real invoice."""
    pro = get_object_or_404(Proforma, id=proforma_id, is_deleted=False)
    items = pro.items.filter(is_deleted=False)
    return render(request, 'billing/proforma_detail.html', {
        'pro': pro,
        'items': items,
        'today': timezone.localdate(),
        'can_convert': pro.status == ProformaStatus.ISSUED and not pro.is_expired,
        'HOSPITAL_NAME': __import__('django.conf', fromlist=['settings']).settings.HOSPITAL_NAME,
    })


@login_required
@require_POST
def proforma_convert(request, proforma_id):
    """
    Convert a proforma to a real invoice.
    Copies all line items and insurance amount. Marks proforma as CONVERTED.
    """
    from django.db import transaction as _tx
    pro = get_object_or_404(Proforma, id=proforma_id, is_deleted=False)

    if pro.status != ProformaStatus.ISSUED:
        messages.error(request, 'Only ISSUED proformas can be converted.')
        return redirect('billing:proforma_detail', proforma_id=pro.id)
    if pro.is_expired:
        messages.error(request, 'This proforma has expired. Please create a new one.')
        return redirect('billing:proforma_detail', proforma_id=pro.id)
    if hasattr(pro, 'invoice') and pro.invoice:
        messages.warning(request, 'This proforma has already been converted.')
        return redirect('billing:invoice_detail', invoice_id=pro.invoice.id)

    with _tx.atomic():
        inv = Invoice.objects.create(
            patient=pro.patient,
            insurance_amount=pro.insurance_amount,
            notes=f'Converted from Proforma {pro.proforma_number}',
            created_by=request.user,
        )
        for item in pro.items.filter(is_deleted=False):
            InvoiceItem.objects.create(
                invoice=inv,
                category=item.category,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                created_by=request.user,
            )
        inv.status = InvoiceStatus.ISSUED
        inv.save(update_fields=['status', 'updated_at'])

        pro.invoice = inv
        pro.status  = ProformaStatus.CONVERTED
        pro.save(update_fields=['invoice', 'status', 'updated_at'])

    messages.success(
        request,
        f'Proforma {pro.proforma_number} converted to Invoice {inv.invoice_number}.'
    )
    return redirect('billing:invoice_detail', invoice_id=inv.id)


@login_required
def proforma_pdf(request, proforma_id):
    """Render a professional printable/PDF version of a proforma invoice."""
    from apps.reports.views import render_pdf
    pro = get_object_or_404(Proforma, id=proforma_id, is_deleted=False)
    items = pro.items.filter(is_deleted=False)
    context = {
        'pro': pro,
        'items': items,
        'pdf_filename': f'proforma_{pro.proforma_number}.pdf',
    }
    return render_pdf('billing/proforma_pdf.html', context)


@login_required
@require_POST
def proforma_cancel(request, proforma_id):
    """Cancel a proforma."""
    pro = get_object_or_404(Proforma, id=proforma_id, is_deleted=False)
    if pro.status in (ProformaStatus.CONVERTED, ProformaStatus.CANCELLED):
        messages.warning(request, 'Cannot cancel this proforma.')
        return redirect('billing:proforma_detail', proforma_id=pro.id)
    pro.status = ProformaStatus.CANCELLED
    pro.save(update_fields=['status', 'updated_at'])
    messages.warning(request, f'Proforma {pro.proforma_number} cancelled.')
    return redirect('billing:proforma_list')


# ─────────────────────────────────────────────────────────────────────────────
# Void / Cancel Register — Audit trail for all cancelled & waived invoices
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def void_register(request):
    """
    Audit register of all CANCELLED and WAIVED invoices.
    Shows who authorised the cancellation/waiver, the reason code, and the amount.
    Accessible to Chief Cashier, Accountants, Finance Director, Management.
    """
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')

    from datetime import date as _d
    from django.db.models import Q

    # Date filter
    date_from_str = request.GET.get('from', '')
    date_to_str   = request.GET.get('to', '')
    try:
        date_from = _d.fromisoformat(date_from_str)
    except (ValueError, TypeError):
        date_from = None
    try:
        date_to = _d.fromisoformat(date_to_str)
    except (ValueError, TypeError):
        date_to = None

    qs = Invoice.objects.filter(
        status__in=[InvoiceStatus.CANCELLED, InvoiceStatus.WAIVED],
        is_deleted=False,
    ).select_related('patient', 'void_reason', 'updated_by', 'created_by')

    if date_from:
        qs = qs.filter(issue_date__gte=date_from)
    if date_to:
        qs = qs.filter(issue_date__lte=date_to)

    qs = qs.order_by('-updated_at')

    from django.db.models import Sum as _S, Count as _C
    summary = qs.aggregate(
        total_count=_C('id'),
        total_cancelled=_C('id', filter=Q(status=InvoiceStatus.CANCELLED)),
        total_waived=_C('id', filter=Q(status=InvoiceStatus.WAIVED)),
    )

    return render(request, 'billing/void_register.html', {
        'invoices': qs,
        'summary': summary,
        'date_from': date_from_str,
        'date_to': date_to_str,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Payment Receipt — per-payment printable receipt
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def payment_receipt(request, payment_id):
    """Printable receipt for a single payment transaction."""
    payment = get_object_or_404(Payment, id=payment_id, is_deleted=False)
    invoice = payment.invoice
    return render(request, 'billing/payment_receipt.html', {
        'payment': payment,
        'invoice': invoice,
        'items': invoice.items.filter(is_deleted=False),
    })


# ─────────────────────────────────────────────────────────────────────────────
# CSV Export Views — Download buttons for all major financial reports
# ─────────────────────────────────────────────────────────────────────────────
import csv
from django.http import HttpResponse


def _csv_response(filename):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _render_pdf(template_name, context, filename):
    """
    Render a template to PDF using the shared render_pdf engine.
    Automatically injects hospital letterhead, logo (base64), and hospital contact details.
    Falls back to browser-print HTML if WeasyPrint is unavailable.
    """
    from apps.reports.views import render_pdf as _shared_render_pdf
    context['pdf_filename'] = filename
    return _shared_render_pdf(template_name, context)


def _log_financial(request, action, invoice, extra=None):
    """Log a financial transaction to the audit trail."""
    try:
        from apps.accounts.models import UserAuditLog
        data = {
            'invoice': invoice.invoice_number,
            'patient': invoice.patient.full_name if invoice.patient_id else '',
            'amount': str(invoice.total),
        }
        if extra:
            data.update(extra)
        UserAuditLog.log(
            user=request.user,
            action=action,
            target_model='Invoice',
            target_id=str(invoice.id),
            extra_data=data,
            request=request,
        )
    except Exception:
        pass


def _log_export(request, export_name):
    """Write an audit entry every time a CSV/data export is performed."""
    try:
        from apps.accounts.models import UserAuditLog
        UserAuditLog.log(
            user=request.user,
            action=UserAuditLog.Action.GENERATE_REPORT,
            target_model='Export',
            target_id=export_name,
            extra_data={'export': export_name, 'filters': dict(request.GET)},
            request=request,
        )
    except Exception:
        pass


@login_required
def patient_financial_history(request):
    """
    Patient Financial Accounts — Chief Cashier and above.
    Default: all patients listed (paginated). Click a patient → full financial history.
    """
    _allowed = (
        UserRole.CHIEF_CASHIER, UserRole.ACCOUNTANT, UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR, UserRole.MEDICAL_DIRECTOR, UserRole.CEO,
        UserRole.ADMIN_DIRECTOR, UserRole.BILLING_OFFICER,
    )
    if not (request.user.is_superuser or request.user.role in _allowed):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    from apps.patients.models import Patient
    from django.db.models import Sum as _Sum, Count as _Count, Max as _Max, Q as _Q
    from django.core.paginator import Paginator

    patient = None
    invoices = []
    summary = {}
    patient_page = None

    patient_id = request.GET.get('patient_id', '').strip()
    q = request.GET.get('q', '').strip()

    # ── Detail: specific patient selected ─────────────────────────────────────
    if patient_id:
        patient = Patient.objects.filter(patient_id=patient_id, is_deleted=False).first()

    if patient:
        invoices = list(
            Invoice.objects.filter(patient=patient, is_deleted=False)
            .select_related('created_by')
            .prefetch_related('payments', 'items')
            .order_by('-created_at')
        )
        # total / amount_paid are properties — compute in Python from prefetched data
        total_billed = sum(inv.total for inv in invoices)
        payment_total = Payment.objects.filter(
            invoice__patient=patient, invoice__is_deleted=False, is_deleted=False,
        ).aggregate(s=_Sum('amount'))['s'] or 0
        summary = {
            'invoice_count': len(invoices),
            'total_billed': total_billed,
            'total_paid': payment_total,
            'total_balance': total_billed - payment_total,
        }
    else:
        # ── List: all patients (like medical records) ──────────────────────────
        patients_qs = Patient.objects.filter(is_active=True, is_deleted=False).annotate(
            invoice_count=_Count('invoices', filter=_Q(invoices__is_deleted=False)),
            last_invoice_at=_Max('invoices__created_at', filter=_Q(invoices__is_deleted=False)),
        ).order_by('-last_invoice_at', '-registration_date')

        if q:
            from apps.core.utils import patient_search_q
            patients_qs = patients_qs.filter(patient_search_q(q))

        paginator = Paginator(patients_qs, 50)
        patient_page = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'billing/patient_accounts.html', {
        'patient': patient,
        'invoices': invoices,
        'summary': summary,
        'patient_page': patient_page,
        'q': q,
        'patient_id': patient_id,
    })


@login_required
def export_invoice_list(request):
    """CSV export of invoice list (same filters as invoice_list view)."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:invoice_list')
    _log_export(request, 'invoice_list')
    q = request.GET.get('q', '')
    status = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    qs = Invoice.objects.filter(is_deleted=False).select_related('patient', 'created_by')
    if q:
        from apps.core.utils import patient_search_q
        qs = qs.filter(
            Q(invoice_number__icontains=q) | patient_search_q(q, prefix='patient__')
        )
    if status:
        qs = qs.filter(status=status)
    if date_from:
        qs = qs.filter(issue_date__gte=date_from)
    if date_to:
        qs = qs.filter(issue_date__lte=date_to)
    qs = qs.order_by('-created_at')
    response = _csv_response(f'invoices_{timezone.localdate()}.csv')
    w = csv.writer(response)
    w.writerow(['Invoice #', 'Date', 'Patient', 'Patient ID', 'Total (FCFA)', 'Paid (FCFA)', 'Balance (FCFA)', 'Status', 'Created By'])
    for inv in qs:
        w.writerow([
            inv.invoice_number,
            inv.issue_date.strftime('%d/%m/%Y'),
            inv.patient.full_name,
            inv.patient.patient_id,
            inv.total,
            inv.amount_paid,
            inv.balance_due,
            inv.get_status_display(),
            inv.created_by.get_full_name() if inv.created_by else '',
        ])
    return response


@login_required
def export_ar_aging(request):
    """CSV export of AR aging report."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:ar_aging')
    _log_export(request, 'ar_aging')
    from datetime import date as _d
    today = timezone.localdate()
    qs = Invoice.objects.filter(
        status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
        is_deleted=False,
    ).select_related('patient', 'corporate_account').order_by('issue_date')
    response = _csv_response(f'ar_aging_{today}.csv')
    w = csv.writer(response)
    w.writerow(['Invoice #', 'Issue Date', 'Patient', 'Patient ID', 'Corporate Account', 'Invoice Total (FCFA)', 'Paid (FCFA)', 'Balance Due (FCFA)', 'Age (Days)', 'Bucket'])
    for inv in qs:
        age = (today - inv.issue_date).days
        balance = float(inv.balance_due)
        if balance <= 0:
            continue
        if age <= 30:
            bucket = 'Current (0-30 days)'
        elif age <= 60:
            bucket = '31-60 days'
        elif age <= 90:
            bucket = '61-90 days'
        else:
            bucket = '90+ days'
        w.writerow([
            inv.invoice_number,
            inv.issue_date.strftime('%d/%m/%Y'),
            inv.patient.full_name,
            inv.patient.patient_id,
            inv.corporate_account.name if inv.corporate_account else '',
            float(inv.total),
            float(inv.amount_paid),
            balance,
            age,
            bucket,
        ])
    return response


@login_required
def export_expense_list(request):
    """CSV export of expense list."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:expense_list')
    _log_export(request, 'expense_list')
    from .models import Expense, ExpenseCategory
    q = request.GET.get('q', '')
    cat = request.GET.get('cat', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    qs = Expense.objects.filter(is_deleted=False).select_related('approved_by', 'created_by')
    if q:
        qs = qs.filter(Q(description__icontains=q) | Q(vendor__icontains=q))
    if cat:
        qs = qs.filter(category=cat)
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    qs = qs.order_by('-date')
    response = _csv_response(f'expenses_{timezone.localdate()}.csv')
    w = csv.writer(response)
    w.writerow(['Date', 'Category', 'Description', 'Vendor', 'Amount (FCFA)', 'Payment Method', 'Status', 'Approved By', 'Submitted By'])
    for exp in qs:
        w.writerow([
            exp.date.strftime('%d/%m/%Y'),
            exp.get_category_display(),
            exp.description,
            exp.vendor or '',
            float(exp.amount),
            exp.get_payment_method_display() if hasattr(exp, 'get_payment_method_display') else '',
            exp.get_status_display() if hasattr(exp, 'get_status_display') else '',
            exp.approved_by.get_full_name() if exp.approved_by else '',
            exp.created_by.get_full_name() if exp.created_by else '',
        ])
    return response


@login_required
def export_shift_list(request):
    """CSV export of cashier shift list."""
    if not _can_verify_shift(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:shift_list')
    _log_export(request, 'shift_list')
    date_str = request.GET.get('date', '')
    cashier_id = request.GET.get('cashier', '')
    status_filter = request.GET.get('status', '')
    qs = CashierShift.objects.filter(is_deleted=False).select_related('cashier', 'verified_by')
    if date_str:
        qs = qs.filter(shift_date=date_str)
    if cashier_id:
        qs = qs.filter(cashier_id=cashier_id)
    if status_filter:
        qs = qs.filter(status=status_filter)
    qs = qs.order_by('-shift_date', 'cashier__first_name')
    response = _csv_response(f'cashier_shifts_{timezone.localdate()}.csv')
    w = csv.writer(response)
    w.writerow(['Date', 'Cashier', 'Opening Float (FCFA)', 'Total Collected (FCFA)', 'Closing Cash (FCFA)', 'Variance (FCFA)', 'Status', 'Verified By'])
    for s in qs:
        w.writerow([
            s.shift_date.strftime('%d/%m/%Y'),
            s.cashier.get_full_name() or s.cashier.username,
            float(s.opening_cash),
            float(s.total_collected),
            float(s.closing_cash) if s.closing_cash else '',
            float(s.variance) if hasattr(s, 'variance') and s.closing_cash else '',
            s.get_status_display(),
            s.verified_by.get_full_name() if s.verified_by else '',
        ])
    return response


@login_required
def export_service_prices(request):
    """CSV export of service price catalogue."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:service_price_list')
    _log_export(request, 'service_prices')
    q = request.GET.get('q', '')
    cat = request.GET.get('cat', '')
    qs = ServicePrice.objects.filter(is_deleted=False)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    if cat:
        qs = qs.filter(category=cat)
    qs = qs.order_by('category', 'name')
    response = _csv_response(f'service_prices_{timezone.localdate()}.csv')
    w = csv.writer(response)
    w.writerow(['Code', 'Name', 'Category', 'Standard Price (FCFA)', 'NHIS Price (FCFA)', 'Insurance Price (FCFA)', 'Active'])
    for p in qs:
        w.writerow([
            p.code or '',
            p.name,
            p.get_category_display(),
            float(p.price),
            float(p.nhis_price) if p.nhis_price else '',
            float(p.insurance_price) if p.insurance_price else '',
            'Yes' if p.is_active else 'No',
        ])
    return response


@login_required
def export_sales_journal(request):
    """CSV export of sales journal."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:sales_journal')
    _log_export(request, 'sales_journal')
    from datetime import date as _d
    today = timezone.localdate()
    date_from_str = request.GET.get('date_from', today.isoformat())
    date_to_str = request.GET.get('date_to', today.isoformat())
    cashier_id = request.GET.get('cashier', '')
    try:
        date_from = _d.fromisoformat(date_from_str)
        date_to = _d.fromisoformat(date_to_str)
    except (ValueError, TypeError):
        date_from = date_to = today
    pay_qs = Payment.objects.filter(
        payment_date__date__gte=date_from,
        payment_date__date__lte=date_to,
        is_deleted=False,
    ).select_related('invoice__patient', 'received_by').order_by('payment_date')
    if cashier_id:
        pay_qs = pay_qs.filter(received_by_id=cashier_id)
    response = _csv_response(f'sales_journal_{date_from_str}_{date_to_str}.csv')
    w = csv.writer(response)
    w.writerow(['Date', 'Receipt #', 'Invoice #', 'Patient', 'Patient ID', 'Amount (FCFA)', 'Payment Method', 'Reference', 'Cashier'])
    for p in pay_qs:
        w.writerow([
            p.payment_date.strftime('%d/%m/%Y %H:%M'),
            p.receipt_number or '',
            p.invoice.invoice_number,
            p.invoice.patient.full_name,
            p.invoice.patient.patient_id,
            float(p.amount),
            p.get_payment_method_display(),
            p.reference or '',
            p.received_by.get_full_name() if p.received_by else '',
        ])
    return response


@login_required
def export_void_register(request):
    """CSV export of void & cancellation register."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:void_register')
    _log_export(request, 'void_register')
    from datetime import date as _d
    date_from_str = request.GET.get('from', '')
    date_to_str = request.GET.get('to', '')
    try:
        date_from = _d.fromisoformat(date_from_str)
    except (ValueError, TypeError):
        date_from = None
    try:
        date_to = _d.fromisoformat(date_to_str)
    except (ValueError, TypeError):
        date_to = None
    qs = Invoice.objects.filter(
        status__in=[InvoiceStatus.CANCELLED, InvoiceStatus.WAIVED],
        is_deleted=False,
    ).select_related('patient', 'void_reason', 'updated_by', 'created_by')
    if date_from:
        qs = qs.filter(issue_date__gte=date_from)
    if date_to:
        qs = qs.filter(issue_date__lte=date_to)
    qs = qs.order_by('-updated_at')
    response = _csv_response(f'void_register_{timezone.localdate()}.csv')
    w = csv.writer(response)
    w.writerow(['Date', 'Invoice #', 'Patient', 'Patient ID', 'Amount (FCFA)', 'Status', 'Reason Code', 'Reason', 'Authorised By', 'Created By'])
    for inv in qs:
        w.writerow([
            inv.issue_date.strftime('%d/%m/%Y'),
            inv.invoice_number,
            inv.patient.full_name,
            inv.patient.patient_id,
            float(inv.total),
            inv.get_status_display(),
            inv.void_reason.code if inv.void_reason else '',
            inv.void_reason.label if inv.void_reason else (inv.discount_reason or ''),
            inv.updated_by.get_full_name() if inv.updated_by else '',
            inv.created_by.get_full_name() if inv.created_by else '',
        ])
    return response


@login_required
def export_corporate_list(request):
    """CSV export of corporate accounts."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:corporate_list')
    _log_export(request, 'corporate_list')
    from .models import CorporateAccount
    accounts = CorporateAccount.objects.filter(is_deleted=False).order_by('name')
    response = _csv_response(f'corporate_accounts_{timezone.localdate()}.csv')
    w = csv.writer(response)
    w.writerow(['Account Name', 'Account Code', 'Contact', 'Phone', 'Email', 'Credit Limit (FCFA)', 'Discount %', 'Payment Terms (Days)', 'Active'])
    for acc in accounts:
        w.writerow([
            acc.name,
            acc.account_code or '',
            acc.contact_name or '',
            acc.phone or '',
            acc.email or '',
            float(acc.credit_limit),
            float(acc.discount_pct),
            acc.payment_terms_days,
            'Yes' if acc.is_active else 'No',
        ])
    return response


@login_required
def export_patient_financial(request):
    """
    CSV export for Patient Financial Records.
    - No patient_id → all patients summary (ID, Name, Invoice count, Last transaction)
    - patient_id provided → full transaction history for that patient
    """
    _allowed = (
        UserRole.CHIEF_CASHIER, UserRole.ACCOUNTANT, UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR, UserRole.MEDICAL_DIRECTOR, UserRole.CEO,
        UserRole.ADMIN_DIRECTOR, UserRole.BILLING_OFFICER,
    )
    if not (request.user.is_superuser or request.user.role in _allowed):
        messages.error(request, 'Access denied.')
        return redirect('billing:patient_financial_history')

    from apps.patients.models import Patient
    from django.db.models import Count as _Count, Max as _Max, Q as _Q

    patient_id = request.GET.get('patient_id', '').strip()

    if patient_id:
        # ── Detail export: one patient's full transaction history ──────────────
        patient = Patient.objects.filter(patient_id=patient_id, is_deleted=False).first()
        if not patient:
            messages.error(request, 'Patient not found.')
            return redirect('billing:patient_financial_history')

        invoices = list(
            Invoice.objects.filter(patient=patient, is_deleted=False)
            .select_related('created_by')
            .prefetch_related('payments', 'items')
            .order_by('-created_at')
        )
        fname = f'financial_record_{patient.patient_id}_{timezone.localdate()}.csv'
        response = _csv_response(fname)
        w = csv.writer(response)
        w.writerow(['Invoice #', 'Date', 'Time', 'Issued By', 'Role', 'Total (FCFA)', 'Paid (FCFA)', 'Balance (FCFA)', 'Status'])
        for inv in invoices:
            issued_by = inv.created_by.get_full_name() or inv.created_by.username if inv.created_by else ''
            role = inv.created_by.get_role_display() if inv.created_by else ''
            w.writerow([
                inv.invoice_number,
                inv.created_at.strftime('%d/%m/%Y'),
                inv.created_at.strftime('%H:%M'),
                issued_by,
                role,
                float(inv.total),
                float(inv.amount_paid),
                float(inv.balance_due),
                inv.get_status_display(),
            ])
    else:
        # ── Summary export: all patients with invoice counts ──────────────────
        patients_qs = Patient.objects.filter(is_active=True, is_deleted=False).annotate(
            invoice_count=_Count('invoices', filter=_Q(invoices__is_deleted=False)),
            last_invoice_at=_Max('invoices__created_at', filter=_Q(invoices__is_deleted=False)),
        ).order_by('-last_invoice_at', '-registration_date')

        q = request.GET.get('q', '').strip()
        if q:
            from apps.core.utils import patient_search_q
            patients_qs = patients_qs.filter(patient_search_q(q))

        fname = f'patient_financial_records_{timezone.localdate()}.csv'
        response = _csv_response(fname)
        w = csv.writer(response)
        w.writerow(['Patient ID', 'Full Name', 'Phone', 'Registered', 'Invoice Count', 'Last Transaction'])
        for p in patients_qs:
            w.writerow([
                p.patient_id,
                p.full_name,
                str(p.phone_number) if p.phone_number else '',
                p.registration_date.strftime('%d/%m/%Y') if p.registration_date else '',
                p.invoice_count or 0,
                p.last_invoice_at.strftime('%d/%m/%Y') if p.last_invoice_at else '',
            ])

    _log_export(request, 'patient_financial')
    return response


# =============================================================================
# PATIENT PREPAYMENT WALLET
# =============================================================================

@login_required
def wallet_list(request):
    """List all patient wallets with non-zero balance."""
    from .models import PatientWallet
    from django.db.models import Q, Sum
    q = request.GET.get('q', '').strip()
    all_wallets = PatientWallet.objects.filter(is_deleted=False).select_related('patient')
    if q:
        from apps.core.utils import patient_search_q
        wallets = all_wallets.filter(patient_search_q(q, prefix='patient__')).order_by('-balance')
    else:
        wallets = all_wallets.order_by('-balance')
    total_balance     = all_wallets.aggregate(t=Sum('balance'))['t'] or 0
    wallets_with_balance = all_wallets.filter(balance__gt=0).count()
    wallets_zero      = all_wallets.filter(balance=0).count()
    from .models import WalletTransaction
    total_transactions = WalletTransaction.objects.filter(is_deleted=False).count()
    return render(request, 'billing/wallet_list.html', {
        'wallets': wallets, 'q': q,
        'total_balance': total_balance,
        'wallets_with_balance': wallets_with_balance,
        'wallets_zero': wallets_zero,
        'total_transactions': total_transactions,
    })


@login_required
def wallet_detail(request, patient_id):
    """View a patient wallet — balance, transactions, deposit form."""
    from apps.patients.models import Patient as _Patient
    from .models import PatientWallet
    patient = get_object_or_404(_Patient, patient_id=patient_id, is_deleted=False)
    wallet, _ = PatientWallet.objects.get_or_create(
        patient=patient, defaults={'created_by': request.user}
    )
    transactions = wallet.transactions.filter(is_deleted=False).order_by('-created_at')[:100]
    from .models import WalletTransactionType
    from django.db.models import Sum
    tx_qs = wallet.transactions.filter(is_deleted=False)
    total_deposited = tx_qs.filter(
        transaction_type__in=[WalletTransactionType.DEPOSIT, WalletTransactionType.REFUND]
    ).aggregate(t=Sum('amount'))['t'] or 0
    total_deducted = tx_qs.filter(
        transaction_type__in=[WalletTransactionType.DEDUCTION, WalletTransactionType.WITHDRAWAL]
    ).aggregate(t=Sum('amount'))['t'] or 0
    return render(request, 'billing/wallet_detail.html', {
        'patient': patient,
        'wallet': wallet,
        'transactions': transactions,
        'total_deposited': total_deposited,
        'total_deducted': total_deducted,
    })


@login_required
def wallet_deposit(request, patient_id):
    """Record a deposit into a patient wallet."""
    from apps.patients.models import Patient as _Patient
    from .models import PatientWallet
    from decimal import Decimal, InvalidOperation
    patient = get_object_or_404(_Patient, patient_id=patient_id, is_deleted=False)
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', '0'))
            if amount <= 0:
                raise ValueError
        except (ValueError, InvalidOperation):
            messages.error(request, 'Enter a valid amount.')
            return redirect('billing:wallet_detail', patient_id=patient_id)
        description = request.POST.get('description', request.POST.get('reference', '')).strip()
        wallet, _ = PatientWallet.objects.get_or_create(
            patient=patient, defaults={'created_by': request.user}
        )
        wallet.deposit(amount, received_by=request.user, reference=description, notes=description)
        messages.success(
            request,
            f'Deposited {int(amount):,} XAF into {patient.full_name}\'s wallet. '
            f'New balance: {wallet.balance:,.0f} XAF.'
        )
    return redirect('billing:wallet_detail', patient_id=patient_id)


@login_required
def wallet_deduct(request, patient_id):
    """Deduct from wallet to settle an invoice."""
    from apps.patients.models import Patient as _Patient
    from .models import PatientWallet
    from decimal import Decimal, InvalidOperation
    patient = get_object_or_404(_Patient, patient_id=patient_id, is_deleted=False)
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', '0'))
        except (ValueError, InvalidOperation):
            messages.error(request, 'Invalid amount.')
            return redirect('billing:wallet_detail', patient_id=patient_id)
        invoice_id = request.POST.get('invoice_id', '').strip()
        invoice = None
        if invoice_id:
            try:
                invoice = Invoice.objects.get(id=invoice_id, is_deleted=False)
            except Invoice.DoesNotExist:
                pass
        try:
            wallet = PatientWallet.objects.get(patient=patient)
            description = request.POST.get('description', request.POST.get('notes', '')).strip()
            wallet.deduct(amount, processed_by=request.user, invoice=invoice, notes=description)
            messages.success(
                request,
                f'{int(amount):,} XAF deducted from wallet. Remaining: {wallet.balance:,.0f} XAF.'
            )
        except PatientWallet.DoesNotExist:
            messages.error(request, 'No wallet found for this patient.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('billing:wallet_detail', patient_id=patient_id)


@login_required
def wallet_search_ajax(request):
    """AJAX: search patients by name/ID for wallet autocomplete."""
    from apps.patients.models import Patient as _Patient
    from django.db.models import Q
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse([], safe=False)
    from apps.core.utils import patient_search_q
    patients = _Patient.objects.filter(is_deleted=False).filter(patient_search_q(q))[:10]
    data = [{'name': p.full_name, 'patient_id': p.patient_id} for p in patients]
    return JsonResponse(data, safe=False)


# =============================================================================
# ASSET REGISTER
# =============================================================================

@login_required
def asset_list(request):
    """List all hospital assets with category / status / search filters."""
    from .models import AssetRegister, AssetCategory, AssetStatus
    cat_filter    = request.GET.get('category', '').strip()
    status_filter = request.GET.get('status', '').strip()
    q             = request.GET.get('q', '').strip()

    assets = AssetRegister.objects.filter(is_deleted=False)
    if cat_filter:
        assets = assets.filter(category=cat_filter)
    if status_filter:
        assets = assets.filter(status=status_filter)
    if q:
        from django.db.models import Q as _Q
        assets = assets.filter(
            _Q(name__icontains=q) |
            _Q(asset_number__icontains=q) |
            _Q(serial_number__icontains=q) |
            _Q(location__icontains=q)
        )

    assets_list = list(assets)
    total_cost        = sum(a.purchase_cost for a in assets_list)
    total_nbv         = sum(a.net_book_value for a in assets_list)
    total_assets      = len(assets_list)
    fully_depreciated = sum(1 for a in assets_list if a.is_fully_depreciated)

    return render(request, 'billing/asset_list.html', {
        'assets': assets_list,
        'categories': AssetCategory.choices,
        'statuses': AssetStatus.choices,
        'cat_filter': cat_filter,
        'status_filter': status_filter,
        'q': q,
        'total_cost': total_cost,
        'total_nbv': total_nbv,
        'total_assets': total_assets,
        'fully_depreciated': fully_depreciated,
    })


@login_required
def asset_create(request):
    """Register a new hospital asset."""
    from .models import AssetRegister, AssetCategory, AssetStatus
    if request.method == 'POST':
        from decimal import Decimal, InvalidOperation
        try:
            cost     = Decimal(request.POST.get('purchase_cost', '0'))
            residual = Decimal(request.POST.get('residual_value', '0') or '0')
        except InvalidOperation:
            messages.error(request, 'Invalid cost value.')
            return redirect('billing:asset_create')
        asset = AssetRegister.objects.create(
            name              = request.POST.get('name', '').strip(),
            category          = request.POST.get('category', ''),
            description       = request.POST.get('description', ''),
            serial_number     = request.POST.get('serial_number', ''),
            make_model        = request.POST.get('make_model', ''),
            location          = request.POST.get('location', ''),
            purchase_date     = request.POST.get('purchase_date', ''),
            purchase_cost     = cost,
            supplier          = request.POST.get('supplier', ''),
            useful_life_years = int(request.POST.get('useful_life_years', 5) or 5),
            residual_value    = residual,
            warranty_expiry   = request.POST.get('warranty_expiry') or None,
            next_service_date = request.POST.get('next_service_date') or None,
            recorded_by       = request.user,
            created_by        = request.user,
        )
        messages.success(request, f'Asset {asset.asset_number} — {asset.name} registered.')
        return redirect('billing:asset_list')
    return render(request, 'billing/asset_form.html', {
        'categories': AssetCategory.choices,
        'statuses': AssetStatus.choices,
        'action': 'Add New Asset',
    })


@login_required
def asset_edit(request, asset_id):
    """Edit / update asset details and maintenance log."""
    from .models import AssetRegister, AssetCategory, AssetStatus
    asset = get_object_or_404(AssetRegister, id=asset_id, is_deleted=False)
    if request.method == 'POST':
        from decimal import Decimal, InvalidOperation
        try:
            cost     = Decimal(request.POST.get('purchase_cost', '0'))
            residual = Decimal(request.POST.get('residual_value', '0') or '0')
        except InvalidOperation:
            messages.error(request, 'Invalid cost value.')
            return redirect('billing:asset_edit', asset_id=asset_id)
        asset.name              = request.POST.get('name', asset.name).strip()
        asset.category          = request.POST.get('category', asset.category)
        asset.description       = request.POST.get('description', '')
        asset.serial_number     = request.POST.get('serial_number', '')
        asset.make_model        = request.POST.get('make_model', '')
        asset.location          = request.POST.get('location', '')
        asset.purchase_date     = request.POST.get('purchase_date', asset.purchase_date)
        asset.purchase_cost     = cost
        asset.supplier          = request.POST.get('supplier', '')
        asset.useful_life_years = int(request.POST.get('useful_life_years', 5) or 5)
        asset.residual_value    = residual
        asset.status            = request.POST.get('status', asset.status)
        asset.warranty_expiry   = request.POST.get('warranty_expiry') or None
        asset.next_service_date = request.POST.get('next_service_date') or None
        asset.last_service_date = request.POST.get('last_service_date') or None
        asset.maintenance_notes = request.POST.get('maintenance_notes', '')
        asset.save()
        messages.success(request, f'Asset {asset.asset_number} updated.')
        return redirect('billing:asset_list')
    return render(request, 'billing/asset_form.html', {
        'asset': asset,
        'categories': AssetCategory.choices,
        'statuses': AssetStatus.choices,
        'action': 'Edit Asset',
    })


# ═══════════════════════════════════════════════════════════════════════════════
# GENERAL LEDGER  —  Chart of Accounts, Journal Entries, Reports
# ═══════════════════════════════════════════════════════════════════════════════
from .models import GLAccount, AccountType, JournalEntry, JournalLine


def _can_access_gl(user):
    return user.role in (
        UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT,
        UserRole.ACCOUNTANT, UserRole.SUPER_ADMIN,
    )


# ── Chart of Accounts ─────────────────────────────────────────────────────────

@login_required
def chart_of_accounts(request):
    if not _can_access_gl(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    accounts = GLAccount.objects.filter(is_deleted=False).order_by('code')
    # Group by type for display
    from collections import defaultdict
    grouped = defaultdict(list)
    for a in accounts:
        grouped[a.account_type].append(a)
    type_order = ['ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE']
    groups = [(t, AccountType(t).label, grouped[t]) for t in type_order if grouped[t]]
    return render(request, 'billing/chart_of_accounts.html', {
        'groups': groups,
        'total_accounts': accounts.count(),
    })


@login_required
def gl_account_create(request):
    if not _can_access_gl(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        name = request.POST.get('name', '').strip()
        account_type = request.POST.get('account_type', '')
        parent_id = request.POST.get('parent_id') or None
        description = request.POST.get('description', '')
        if not code or not name or not account_type:
            messages.error(request, 'Code, Name and Type are required.')
        elif GLAccount.objects.filter(code=code).exists():
            messages.error(request, f'Account code {code} already exists.')
        else:
            parent = GLAccount.objects.filter(pk=parent_id).first() if parent_id else None
            GLAccount.objects.create(
                code=code, name=name, account_type=account_type,
                parent=parent, description=description,
                created_by=request.user,
            )
            messages.success(request, f'Account {code} — {name} created.')
            return redirect('billing:chart_of_accounts')
    return render(request, 'billing/gl_account_form.html', {
        'account_types': AccountType.choices,
        'parent_accounts': GLAccount.objects.filter(is_deleted=False, is_active=True).order_by('code'),
        'action': 'Add Account',
    })


@login_required
def gl_account_edit(request, account_id):
    if not _can_access_gl(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    account = get_object_or_404(GLAccount, pk=account_id, is_deleted=False)
    if request.method == 'POST':
        account.name = request.POST.get('name', account.name).strip()
        account.account_type = request.POST.get('account_type', account.account_type)
        account.description = request.POST.get('description', '')
        account.is_active = request.POST.get('is_active') == 'on'
        account.allow_manual_posting = request.POST.get('allow_manual_posting') == 'on'
        account.save()
        messages.success(request, f'Account {account.code} updated.')
        return redirect('billing:chart_of_accounts')
    return render(request, 'billing/gl_account_form.html', {
        'account': account,
        'account_types': AccountType.choices,
        'parent_accounts': GLAccount.objects.filter(is_deleted=False, is_active=True).exclude(pk=account_id).order_by('code'),
        'action': 'Edit Account',
    })


# ── Journal Entries ───────────────────────────────────────────────────────────

@login_required
def journal_entry_list(request):
    if not _can_access_gl(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    qs = JournalEntry.objects.filter(is_deleted=False).order_by('-entry_date', '-created_at')
    # Filters
    source = request.GET.get('source', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    q = request.GET.get('q', '')
    if source:
        qs = qs.filter(source_type=source)
    if date_from:
        qs = qs.filter(entry_date__gte=date_from)
    if date_to:
        qs = qs.filter(entry_date__lte=date_to)
    if q:
        qs = qs.filter(Q(entry_number__icontains=q) | Q(description__icontains=q) | Q(reference__icontains=q))
    return render(request, 'billing/journal_entry_list.html', {
        'entries': qs[:200],
        'total': qs.count(),
        'source': source,
        'date_from': date_from,
        'date_to': date_to,
        'q': q,
    })


@login_required
def journal_entry_detail(request, entry_id):
    if not _can_access_gl(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    entry = get_object_or_404(JournalEntry, pk=entry_id, is_deleted=False)
    return render(request, 'billing/journal_entry_detail.html', {'entry': entry})


@login_required
def journal_entry_create(request):
    """Manual journal entry — Finance Director / Senior Accountant only."""
    if request.user.role not in (UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT, UserRole.ADMIN, UserRole.SUPER_ADMIN):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    accounts = GLAccount.objects.filter(is_deleted=False, is_active=True, allow_manual_posting=True).order_by('code')
    if request.method == 'POST':
        entry_date = request.POST.get('entry_date')
        description = request.POST.get('description', '').strip()
        reference = request.POST.get('reference', '').strip()
        acct_ids = request.POST.getlist('account_id')
        debits = request.POST.getlist('debit')
        credits = request.POST.getlist('credit')
        descs = request.POST.getlist('line_desc')

        if not entry_date or not description:
            messages.error(request, 'Date and description are required.')
            return render(request, 'billing/journal_entry_form.html', {'accounts': accounts})

        total_dr = sum(Decimal(d or '0') for d in debits)
        total_cr = sum(Decimal(c or '0') for c in credits)
        if abs(total_dr - total_cr) > Decimal('0.01'):
            messages.error(request, f'Entry is not balanced: Debits {total_dr:,.2f} ≠ Credits {total_cr:,.2f}')
            return render(request, 'billing/journal_entry_form.html', {'accounts': accounts})

        entry = JournalEntry.objects.create(
            entry_date=entry_date,
            description=description,
            reference=reference,
            source_type='manual',
            source_id='',
            is_posted=True,
            created_by=request.user,
        )
        for seq, (acct_id, dr, cr, ld) in enumerate(zip(acct_ids, debits, credits, descs), 1):
            acct = GLAccount.objects.filter(pk=acct_id).first()
            if acct and (Decimal(dr or '0') or Decimal(cr or '0')):
                JournalLine.objects.create(
                    entry=entry, account=acct,
                    debit_amount=Decimal(dr or '0'),
                    credit_amount=Decimal(cr or '0'),
                    description=ld, sequence=seq,
                )
        messages.success(request, f'Journal entry {entry.entry_number} posted.')
        return redirect('billing:journal_entry_detail', entry_id=entry.pk)
    return render(request, 'billing/journal_entry_form.html', {'accounts': accounts})


# ── General Ledger Report ─────────────────────────────────────────────────────

@login_required
def general_ledger(request):
    if not _can_access_gl(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    accounts = GLAccount.objects.filter(is_deleted=False, is_active=True).order_by('code')
    account_id = request.GET.get('account_id', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    selected_account = None
    lines = []
    running_balance = Decimal('0')
    if account_id:
        selected_account = get_object_or_404(GLAccount, pk=account_id)
        qs = JournalLine.objects.filter(
            account=selected_account,
            entry__is_posted=True,
            entry__is_deleted=False,
        ).select_related('entry').order_by('entry__entry_date', 'entry__created_at')
        if date_from:
            qs = qs.filter(entry__entry_date__gte=date_from)
        if date_to:
            qs = qs.filter(entry__entry_date__lte=date_to)
        for line in qs:
            if selected_account.account_type in ('ASSET', 'EXPENSE'):
                running_balance += line.debit_amount - line.credit_amount
            else:
                running_balance += line.credit_amount - line.debit_amount
            lines.append({'line': line, 'running_balance': running_balance})
    return render(request, 'billing/general_ledger.html', {
        'accounts': accounts,
        'selected_account': selected_account,
        'lines': lines,
        'closing_balance': running_balance,
        'date_from': date_from,
        'date_to': date_to,
        'account_id': account_id,
    })


# ── Trial Balance ─────────────────────────────────────────────────────────────

@login_required
def trial_balance(request):
    if not _can_access_gl(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    date_to = request.GET.get('date_to', str(timezone.localdate()))
    accounts = GLAccount.objects.filter(is_deleted=False, is_active=True).order_by('code')
    rows = []
    total_dr = Decimal('0')
    total_cr = Decimal('0')
    for acct in accounts:
        lines = JournalLine.objects.filter(
            account=acct,
            entry__is_posted=True,
            entry__is_deleted=False,
            entry__entry_date__lte=date_to,
        )
        dr = lines.aggregate(t=Sum('debit_amount'))['t'] or Decimal('0')
        cr = lines.aggregate(t=Sum('credit_amount'))['t'] or Decimal('0')
        if dr or cr:
            rows.append({'account': acct, 'debit': dr, 'credit': cr})
            total_dr += dr
            total_cr += cr
    return render(request, 'billing/trial_balance.html', {
        'rows': rows,
        'total_dr': total_dr,
        'total_cr': total_cr,
        'balanced': abs(total_dr - total_cr) < Decimal('0.01'),
        'date_to': date_to,
    })


# ── Balance Sheet ─────────────────────────────────────────────────────────────

@login_required
def balance_sheet(request):
    if not _can_access_gl(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    date_to = request.GET.get('date_to', str(timezone.localdate()))

    # Single bulk aggregate across all GL accounts — avoids 2 queries per account
    bulk_agg = (
        JournalLine.objects.filter(
            entry__is_posted=True, entry__is_deleted=False, entry__entry_date__lte=date_to,
        ).values('account_id').annotate(
            total_dr=Sum('debit_amount'), total_cr=Sum('credit_amount')
        )
    )
    bal_map = {
        row['account_id']: (row['total_dr'] or Decimal('0'), row['total_cr'] or Decimal('0'))
        for row in bulk_agg
    }

    def get_balance(acct):
        dr, cr = bal_map.get(acct.id, (Decimal('0'), Decimal('0')))
        if acct.account_type in ('ASSET', 'EXPENSE'):
            return dr - cr
        return cr - dr

    assets      = [{'account': a, 'balance': get_balance(a)} for a in GLAccount.objects.filter(is_deleted=False, is_active=True, account_type=AccountType.ASSET)]
    liabilities = [{'account': a, 'balance': get_balance(a)} for a in GLAccount.objects.filter(is_deleted=False, is_active=True, account_type=AccountType.LIABILITY)]
    equity      = [{'account': a, 'balance': get_balance(a)} for a in GLAccount.objects.filter(is_deleted=False, is_active=True, account_type=AccountType.EQUITY)]

    total_assets      = sum(r['balance'] for r in assets)
    total_liabilities = sum(r['balance'] for r in liabilities)
    total_equity      = sum(r['balance'] for r in equity)

    return render(request, 'billing/balance_sheet.html', {
        'assets': assets, 'liabilities': liabilities, 'equity': equity,
        'total_assets': total_assets,
        'total_liabilities': total_liabilities,
        'total_equity': total_equity,
        'total_liabilities_equity': total_liabilities + total_equity,
        'balanced': abs(total_assets - (total_liabilities + total_equity)) < Decimal('0.01'),
        'date_to': date_to,
    })


# ── Cash Flow Statement ───────────────────────────────────────────────────────

@login_required
def cash_flow_statement(request):
    if not _can_access_gl(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    from apps.billing.models import Payment, Expense, APPayment
    today = timezone.localdate()
    first_of_month = today.replace(day=1)
    date_from = request.GET.get('date_from', str(first_of_month))
    date_to   = request.GET.get('date_to',   str(today))

    # Operating inflows — patient payments
    receipts = Payment.objects.filter(
        is_deleted=False,
        payment_date__date__gte=date_from,
        payment_date__date__lte=date_to,
    ).exclude(payment_method__in=('INSURANCE', 'NHIS', 'WAIVER'))
    cash_receipts = receipts.aggregate(t=Sum('amount'))['t'] or Decimal('0')

    # Operating outflows — expenses
    expenses_total = Expense.objects.filter(
        is_deleted=False, approved_by__isnull=False,
        date__gte=date_from, date__lte=date_to,
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    # AP payments outflow
    ap_payments_total = APPayment.objects.filter(
        is_deleted=False, payment_date__gte=date_from, payment_date__lte=date_to,
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    operating_inflow  = cash_receipts
    operating_outflow = expenses_total + ap_payments_total
    net_operating     = operating_inflow - operating_outflow

    return render(request, 'billing/cash_flow.html', {
        'date_from': date_from,
        'date_to': date_to,
        'cash_receipts': cash_receipts,
        'expenses_total': expenses_total,
        'ap_payments_total': ap_payments_total,
        'operating_inflow': operating_inflow,
        'operating_outflow': operating_outflow,
        'net_operating': net_operating,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# ACCOUNTS PAYABLE  —  Vendors, Bills, Payments
# ═══════════════════════════════════════════════════════════════════════════════
from .models import APVendor, APBill, APPayment, APBillStatus


def _can_access_ap(user):
    return user.role in (
        UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT,
        UserRole.ACCOUNTANT, UserRole.SUPER_ADMIN,
    )


@login_required
def ap_vendor_list(request):
    if not _can_access_ap(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    vendors = APVendor.objects.filter(is_deleted=False).order_by('name')
    if request.GET.get('q'):
        vendors = vendors.filter(Q(name__icontains=request.GET.get('q', '')) | Q(vendor_code__icontains=request.GET.get('q', '')))
    return render(request, 'billing/ap_vendor_list.html', {
        'vendors': vendors,
        'total_vendors': vendors.count(),
    })


@login_required
def ap_vendor_create(request):
    if not _can_access_ap(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Vendor name is required.')
        elif APVendor.objects.filter(name__iexact=name).exists():
            messages.error(request, f'Vendor "{name}" already exists.')
        else:
            vendor = APVendor.objects.create(
                name=name,
                contact_name=request.POST.get('contact_name', ''),
                phone=request.POST.get('phone', ''),
                email=request.POST.get('email', ''),
                address=request.POST.get('address', ''),
                tax_id=request.POST.get('tax_id', ''),
                payment_terms_days=int(request.POST.get('payment_terms_days') or 30),
                bank_name=request.POST.get('bank_name', ''),
                bank_account=request.POST.get('bank_account', ''),
                notes=request.POST.get('notes', ''),
                created_by=request.user,
            )
            messages.success(request, f'Vendor {vendor.vendor_code} — {vendor.name} created.')
            return redirect('billing:ap_vendor_list')
    return render(request, 'billing/ap_vendor_form.html', {'action': 'Add Vendor'})


@login_required
def ap_vendor_edit(request, vendor_id):
    if not _can_access_ap(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    vendor = get_object_or_404(APVendor, pk=vendor_id, is_deleted=False)
    if request.method == 'POST':
        vendor.name = request.POST.get('name', vendor.name).strip()
        vendor.contact_name = request.POST.get('contact_name', '')
        vendor.phone = request.POST.get('phone', '')
        vendor.email = request.POST.get('email', '')
        vendor.address = request.POST.get('address', '')
        vendor.tax_id = request.POST.get('tax_id', '')
        vendor.payment_terms_days = int(request.POST.get('payment_terms_days') or 30)
        vendor.bank_name = request.POST.get('bank_name', '')
        vendor.bank_account = request.POST.get('bank_account', '')
        vendor.notes = request.POST.get('notes', '')
        vendor.is_active = request.POST.get('is_active') == 'on'
        vendor.save()
        messages.success(request, f'Vendor {vendor.name} updated.')
        return redirect('billing:ap_vendor_list')
    return render(request, 'billing/ap_vendor_form.html', {'vendor': vendor, 'action': 'Edit Vendor'})


@login_required
def ap_bill_list(request):
    if not _can_access_ap(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    qs = APBill.objects.filter(is_deleted=False).select_related('vendor').order_by('-bill_date')
    status_filter = request.GET.get('status', '')
    vendor_id = request.GET.get('vendor_id', '')
    q = request.GET.get('q', '')
    if status_filter:
        qs = qs.filter(status=status_filter)
    if vendor_id:
        qs = qs.filter(vendor_id=vendor_id)
    if q:
        qs = qs.filter(Q(bill_number__icontains=q) | Q(description__icontains=q) | Q(vendor__name__icontains=q))
    total_outstanding = qs.exclude(status=APBillStatus.PAID).aggregate(t=Sum('amount_due'))['t'] or Decimal('0')
    return render(request, 'billing/ap_bill_list.html', {
        'bills': qs[:200],
        'total': qs.count(),
        'total_outstanding': total_outstanding,
        'status_choices': APBillStatus.choices,
        'vendors': APVendor.objects.filter(is_deleted=False, is_active=True).order_by('name'),
        'status_filter': status_filter,
        'vendor_id': vendor_id,
        'q': q,
    })


@login_required
def ap_bill_create(request):
    if not _can_access_ap(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    vendors = APVendor.objects.filter(is_deleted=False, is_active=True).order_by('name')
    gl_accounts = GLAccount.objects.filter(is_deleted=False, is_active=True, account_type='EXPENSE').order_by('code')
    if request.method == 'POST':
        vendor = get_object_or_404(APVendor, pk=request.POST.get('vendor_id'))
        amount_due = Decimal(request.POST.get('amount_due') or '0')
        if amount_due <= 0:
            messages.error(request, 'Amount must be greater than zero.')
        else:
            from apps.billing.models import ExpenseCategory
            bill = APBill.objects.create(
                vendor=vendor,
                vendor_ref=request.POST.get('vendor_ref', ''),
                category=request.POST.get('category', 'EXP_OTHER'),
                description=request.POST.get('description', '').strip(),
                amount_due=amount_due,
                tax_amount=Decimal(request.POST.get('tax_amount') or '0'),
                bill_date=request.POST.get('bill_date') or timezone.localdate(),
                due_date=request.POST.get('due_date') or None,
                gl_account=GLAccount.objects.filter(pk=request.POST.get('gl_account_id')).first(),
                attachment_ref=request.POST.get('attachment_ref', ''),
                notes=request.POST.get('notes', ''),
                approved_by=request.user,
                created_by=request.user,
            )
            messages.success(request, f'Bill {bill.bill_number} created.')
            return redirect('billing:ap_bill_list')
    from apps.billing.models import ExpenseCategory
    return render(request, 'billing/ap_bill_form.html', {
        'vendors': vendors,
        'gl_accounts': gl_accounts,
        'expense_categories': ExpenseCategory.choices,
        'action': 'Record Vendor Bill',
    })


@login_required
def ap_bill_detail(request, bill_id):
    if not _can_access_ap(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    bill = get_object_or_404(APBill, pk=bill_id, is_deleted=False)
    return render(request, 'billing/ap_bill_detail.html', {'bill': bill})


@login_required
@require_POST
def ap_bill_pay(request, bill_id):
    if not _can_access_ap(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    bill = get_object_or_404(APBill, pk=bill_id, is_deleted=False)
    amount = Decimal(request.POST.get('amount') or '0')
    if amount <= 0:
        messages.error(request, 'Payment amount must be greater than zero.')
    elif amount > bill.balance_due:
        messages.error(request, f'Amount exceeds balance due of {bill.balance_due:,.0f} XAF.')
    else:
        APPayment.objects.create(
            bill=bill,
            payment_date=request.POST.get('payment_date') or timezone.localdate(),
            amount=amount,
            payment_method=request.POST.get('payment_method', 'TRANSFER'),
            reference=request.POST.get('reference', ''),
            paid_by=request.user,
            notes=request.POST.get('notes', ''),
            created_by=request.user,
        )
        messages.success(request, f'{amount:,.0f} XAF paid to {bill.vendor.name}.')
    return redirect('billing:ap_bill_detail', bill_id=bill_id)


# ═══════════════════════════════════════════════════════════════════════════════
# ADVANCED TIER-SCOPED CASHIER DESK MODULE
# CashDesk management · CashierSession open/close/verify · Z-report
# Discount approvals · Invoice tier-change rerouting · Revenue by desk
# ═══════════════════════════════════════════════════════════════════════════════

from .models import (
    CashDesk, DeskType, DeskReceiptSequence,
    CashierSession, SessionStatus,
    DiscountApproval, DiscountApprovalStatus,
    InvoiceTierChange, InvoiceRoutingType,
)


def _get_active_cashier_session(user):
    """Return the cashier's currently open desk session (any date), or None."""
    return CashierSession.objects.filter(
        cashier=user,
        status=SessionStatus.OPEN,
        is_deleted=False,
    ).order_by('-opened_at').first()


def _can_manage_desks(user):
    """Create / edit cash desks — Finance Director, Senior Accountant, Super Admin."""
    return user.role in (
        UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR,
        UserRole.ADMIN_DIRECTOR,
        UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_verify_session(user):
    """Verify a closed cashier session — Chief Cashier and above."""
    return user.role in (
        UserRole.CHIEF_CASHIER,
        UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR,
        UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_approve_discount(user):
    """Approve discount requests from cashiers — Chief Cashier and above."""
    return user.role in (
        UserRole.CHIEF_CASHIER,
        UserRole.ACCOUNTANT,
        UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR,
        UserRole.SUPER_ADMIN,
    ) or user.is_superuser


# ── Cash Desk Management ──────────────────────────────────────────────────────

@login_required
def desk_list(request):
    if not _can_manage_desks(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    desks = CashDesk.objects.filter(is_deleted=False).order_by('desk_type', 'name')
    return render(request, 'billing/desk_list.html', {'desks': desks})


@login_required
def desk_create(request):
    if not _can_manage_desks(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    if request.method == 'POST':
        name           = request.POST.get('name', '').strip()
        desk_type      = request.POST.get('desk_type', DeskType.TIER)
        tier           = request.POST.get('tier', '').strip()
        location       = request.POST.get('location', '').strip()
        receipt_prefix = request.POST.get('receipt_prefix', 'RCT').strip().upper()
        if not name:
            messages.error(request, 'Desk name is required.')
        elif desk_type == DeskType.TIER and not tier:
            messages.error(request, 'Tier value is required for a tier desk.')
        else:
            desk = CashDesk.objects.create(
                name=name, desk_type=desk_type, tier=tier,
                location=location, receipt_prefix=receipt_prefix or 'RCT',
                is_active=True, created_by=request.user,
            )
            messages.success(request, f'Cash desk "{desk.name}" created.')
            return redirect('billing:desk_list')
    context = {'desk_types': DeskType.choices, 'tier_choices': [
        ('STANDARD', 'Standard'), ('FAST_TRACK', 'Fast Track'), ('VIP', 'VIP'),
    ]}
    return render(request, 'billing/desk_form.html', context)


@login_required
def desk_edit(request, desk_id):
    if not _can_manage_desks(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from django.http import Http404
    desk = get_object_or_404(CashDesk, pk=desk_id, is_deleted=False)
    if request.method == 'POST':
        desk.name           = request.POST.get('name', desk.name).strip()
        desk.desk_type      = request.POST.get('desk_type', desk.desk_type)
        desk.tier           = request.POST.get('tier', desk.tier).strip()
        desk.location       = request.POST.get('location', desk.location).strip()
        desk.receipt_prefix = request.POST.get('receipt_prefix', desk.receipt_prefix).strip().upper()
        desk.is_active      = request.POST.get('is_active') == '1'
        if not desk.name:
            messages.error(request, 'Desk name is required.')
        elif desk.desk_type == DeskType.TIER and not desk.tier:
            messages.error(request, 'Tier value is required for a tier desk.')
        else:
            desk.save()
            messages.success(request, f'Cash desk "{desk.name}" updated.')
            return redirect('billing:desk_list')
    context = {
        'desk': desk,
        'desk_types': DeskType.choices,
        'tier_choices': [
            ('STANDARD', 'Standard'), ('FAST_TRACK', 'Fast Track'), ('VIP', 'VIP'),
        ],
    }
    return render(request, 'billing/desk_form.html', context)


@json_error_handler
@login_required
@require_POST
def desk_toggle(request, desk_id):
    if not _can_manage_desks(request.user):
        return JsonResponse({'error': 'Access denied'}, status=403)
    desk = get_object_or_404(CashDesk, pk=desk_id, is_deleted=False)
    desk.is_active = not desk.is_active
    desk.save(update_fields=['is_active', 'updated_at'])
    return JsonResponse({'active': desk.is_active, 'name': desk.name})


# ── CashierSession management ──────────────────────────────────────────────────

@login_required
def session_list(request):
    """Supervisor view — all sessions (filterable by date / desk / cashier)."""
    if not (_can_verify_session(request.user) or _can_view_financial_reports(request.user)):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    qs = CashierSession.objects.filter(is_deleted=False).select_related('cashier', 'cash_desk', 'verified_by')
    date_str = request.GET.get('date', '')
    desk_id  = request.GET.get('desk', '')
    status   = request.GET.get('status', '')
    if date_str:
        try:
            from datetime import date as _dt
            d = _dt.fromisoformat(date_str)
            qs = qs.filter(opened_at__date=d)
        except ValueError:
            pass
    if desk_id:
        qs = qs.filter(cash_desk_id=desk_id)
    if status:
        qs = qs.filter(status=status)
    desks = CashDesk.objects.filter(is_deleted=False, is_active=True)
    context = {
        'sessions': qs[:200],
        'desks': desks,
        'statuses': SessionStatus.choices,
        'filter_date': date_str,
        'filter_desk': desk_id,
        'filter_status': status,
    }
    return render(request, 'billing/session_list.html', context)


@login_required
def session_open(request):
    """Cashier opens a session on a desk."""
    if request.user.role not in (
        UserRole.CASHIER, UserRole.CHIEF_CASHIER, UserRole.BILLING_OFFICER,
        UserRole.SENIOR_ACCOUNTANT, UserRole.FINANCE_DIRECTOR, UserRole.SUPER_ADMIN,
    ) and not request.user.is_superuser:
        messages.error(request, 'Only cashiers can open a session.')
        return redirect('dashboard:home')

    # Check for any unclosed session (no date filter — a session from yesterday
    # that was never closed must still be found so the cashier can close it).
    existing = CashierSession.objects.filter(
        cashier=request.user, status=SessionStatus.OPEN, is_deleted=False,
    ).order_by('-opened_at').first()
    if existing:
        messages.warning(
            request,
            f'You still have an open session from {existing.opened_at.strftime("%d %b %Y %H:%M")}. '
            f'Please close it before opening a new one.'
        )
        return redirect('billing:session_detail', session_id=existing.pk)

    desks = CashDesk.objects.filter(is_deleted=False, is_active=True).order_by('desk_type', 'name')
    _supervisor_roles = {
        UserRole.CHIEF_CASHIER, UserRole.ACCOUNTANT, UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR, UserRole.ADMIN_DIRECTOR, UserRole.MEDICAL_DIRECTOR,
        UserRole.SUPER_ADMIN,
    }
    is_supervisor = request.user.role in _supervisor_roles or request.user.is_superuser
    open_sessions = (
        CashierSession.objects.filter(status=SessionStatus.OPEN, is_deleted=False)
        .select_related('cashier', 'cash_desk').order_by('cash_desk__name')
        if is_supervisor else []
    )
    if request.method == 'POST':
        desk_id       = request.POST.get('desk_id')
        opening_float = request.POST.get('opening_float', '0').strip() or '0'
        try:
            opening_float = Decimal(opening_float)
        except Exception:
            opening_float = Decimal('0')
        try:
            desk = CashDesk.objects.get(pk=desk_id, is_deleted=False, is_active=True)
        except CashDesk.DoesNotExist:
            messages.error(request, 'Invalid desk selected.')
            return render(request, 'billing/session_open.html', {
                'desks': desks, 'open_sessions': open_sessions, 'is_supervisor': is_supervisor,
            })

        # Only one open session per desk at a time
        blocking = CashierSession.objects.filter(
            cash_desk=desk, status=SessionStatus.OPEN, is_deleted=False
        ).select_related('cashier').first()
        if blocking:
            holder = blocking.cashier.get_full_name() or blocking.cashier.username
            since  = blocking.opened_at.strftime('%H:%M')
            messages.error(
                request,
                f'Desk "{desk.name}" is already open by {holder} (since {since}). '
                f'Ask them to close their session first, or contact a supervisor.'
            )
            if is_supervisor:
                open_sessions = CashierSession.objects.filter(
                    status=SessionStatus.OPEN, is_deleted=False
                ).select_related('cashier', 'cash_desk').order_by('cash_desk__name')
            return render(request, 'billing/session_open.html', {
                'desks': desks, 'open_sessions': open_sessions, 'is_supervisor': is_supervisor,
            })

        # Auto-close any stale OPEN sessions from previous days for this cashier
        today = timezone.localdate()
        stale = CashierSession.objects.filter(
            cashier=request.user, status=SessionStatus.OPEN, is_deleted=False,
        ).exclude(opened_at__date=today)
        stale_count = stale.count()
        if stale_count:
            stale.update(
                status=SessionStatus.CLOSED,
                closed_at=timezone.now(),
                notes='Auto-closed: cashier opened a new session on a new day.',
            )
            messages.warning(request, f'{stale_count} previous unclosed session(s) were automatically closed.')

        session = CashierSession.objects.create(
            cashier=request.user,
            cash_desk=desk,
            opening_float=opening_float,
            status=SessionStatus.OPEN,
            created_by=request.user,
        )
        messages.success(request, f'Session opened at {desk.name}.')
        return redirect('billing:session_detail', session_id=session.pk)

    return render(request, 'billing/session_open.html', {
        'desks': desks, 'open_sessions': open_sessions, 'is_supervisor': is_supervisor,
    })


@login_required
def session_detail(request, session_id):
    """Session detail / Z-report view."""
    session = get_object_or_404(CashierSession, pk=session_id, is_deleted=False)
    # Cashier can see own; supervisor can see all
    is_own = (session.cashier == request.user)
    if not (is_own or _can_verify_session(request.user) or _can_view_financial_reports(request.user)):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    can_force_close = _can_verify_session(request.user) and not is_own
    _is_open = session.status == SessionStatus.OPEN
    _can_sup = _can_verify_session(request.user)
    _has_payments = session.payments.filter(is_deleted=False).exists()
    context = {
        'session': session,
        'collections': session.collections_by_method,
        'can_close': is_own and _is_open,
        'can_force_close': can_force_close and _is_open,
        'can_verify': _can_sup and session.status == SessionStatus.CLOSED,
        'can_edit_float': _can_sup and _is_open,
        'can_void': _can_sup and _is_open and not _has_payments,
    }
    return render(request, 'billing/session_detail.html', context)


@json_error_handler
@login_required
@require_POST
def session_close(request, session_id):
    """Cashier closes their own session, or supervisor force-closes any session."""
    session = get_object_or_404(CashierSession, pk=session_id, is_deleted=False)
    is_own = (session.cashier == request.user)
    can_force = _can_verify_session(request.user)   # Chief Cashier and above
    if not is_own and not can_force:
        return JsonResponse({'error': 'Not your session.'}, status=403)
    if session.status != SessionStatus.OPEN:
        return JsonResponse({'error': 'Session is not open.'}, status=400)

    declared = request.POST.get('closing_declared_cash', '').strip()
    try:
        declared = Decimal(declared)
    except Exception:
        declared = Decimal('0')

    session.closing_declared_cash = declared
    session.closed_at = timezone.now()
    session.status    = SessionStatus.CLOSED
    base_notes = request.POST.get('notes', '').strip()
    if not is_own:
        supervisor_name = request.user.get_full_name() or request.user.username
        session.notes = f'Force-closed by {supervisor_name} ({request.user.get_role_display()}). {base_notes}'.strip()
    else:
        session.notes = base_notes

    # Flag if variance > tolerance (e.g. 500 XAF)
    variance = declared - session.expected_cash_in_hand
    if abs(variance) > 500:
        session.variance_flag  = True
        session.variance_notes = f'Auto-flagged: variance = {variance:+,.0f} XAF'

    session.save()
    if is_own:
        messages.success(request, 'Session closed. Awaiting verification.')
    else:
        cashier_name = session.cashier.get_full_name() or session.cashier.username
        messages.warning(request, f'Session force-closed for {cashier_name}. Desk is now available.')
    return redirect('billing:session_detail', session_id=session.pk)


@json_error_handler
@login_required
@require_POST
def session_verify(request, session_id):
    """Chief Cashier / Finance verifies a closed session."""
    if not _can_verify_session(request.user):
        return JsonResponse({'error': 'Access denied.'}, status=403)
    session = get_object_or_404(CashierSession, pk=session_id, is_deleted=False)
    if session.status != SessionStatus.CLOSED:
        messages.error(request, 'Only CLOSED sessions can be verified.')
        return redirect('billing:session_detail', session_id=session.pk)
    session.status      = SessionStatus.VERIFIED
    session.verified_by = request.user
    session.verified_at = timezone.now()
    session.variance_notes = request.POST.get('variance_notes', session.variance_notes)
    session.save()
    messages.success(request, 'Session verified.')
    return redirect('billing:session_detail', session_id=session.pk)


@json_error_handler
@login_required
@require_POST
def session_edit_float(request, session_id):
    """Chief Cashier / Supervisor corrects the opening float on an OPEN session."""
    if not _can_verify_session(request.user):
        messages.error(request, 'Access denied — Chief Cashier or above required.')
        return redirect('billing:session_detail', session_id=session_id)
    session = get_object_or_404(CashierSession, pk=session_id, is_deleted=False)
    if session.status != SessionStatus.OPEN:
        messages.error(request, 'Opening float can only be adjusted on an OPEN session.')
        return redirect('billing:session_detail', session_id=session_id)
    try:
        new_float = Decimal(request.POST.get('opening_float', '').strip() or '0')
    except Exception:
        messages.error(request, 'Invalid amount entered.')
        return redirect('billing:session_detail', session_id=session_id)
    old_float = session.opening_float
    supervisor = request.user.get_full_name() or request.user.username
    session.opening_float = new_float
    session.notes = (
        (session.notes + '\n' if session.notes else '') +
        f'Float adjusted from {old_float:,.0f} to {new_float:,.0f} XAF by {supervisor} on '
        f'{timezone.now().strftime("%d/%m/%Y %H:%M")}.'
    )
    session.save(update_fields=['opening_float', 'notes', 'updated_at'])
    messages.success(request, f'Opening float updated to {new_float:,.0f} XAF.')
    return redirect('billing:session_detail', session_id=session.pk)


@json_error_handler
@login_required
@require_POST
def session_void(request, session_id):
    """Chief Cashier / Supervisor voids an OPEN session that has no payments yet."""
    if not _can_verify_session(request.user):
        messages.error(request, 'Access denied — Chief Cashier or above required.')
        return redirect('billing:session_detail', session_id=session_id)
    session = get_object_or_404(CashierSession, pk=session_id, is_deleted=False)
    if session.status != SessionStatus.OPEN:
        messages.error(request, 'Only OPEN sessions can be voided.')
        return redirect('billing:session_detail', session_id=session_id)
    if session.payments.filter(is_deleted=False).exists():
        messages.error(request, 'Cannot void a session that already has payments recorded.')
        return redirect('billing:session_detail', session_id=session_id)
    supervisor = request.user.get_full_name() or request.user.username
    reason = request.POST.get('reason', '').strip() or 'No reason provided.'
    session.status = SessionStatus.CLOSED
    session.closed_at = timezone.now()
    session.closing_declared_cash = Decimal('0')
    session.notes = f'VOIDED by {supervisor} on {timezone.now().strftime("%d/%m/%Y %H:%M")}. Reason: {reason}'
    session.is_deleted = True
    session.save()
    messages.success(request, 'Session voided — desk is now available.')
    return redirect('billing:session_list')


@login_required
def my_session(request):
    """Redirect cashier to their active session (any date), or prompt to open one."""
    session = CashierSession.objects.filter(
        cashier=request.user, status=SessionStatus.OPEN, is_deleted=False,
    ).order_by('-opened_at').first()
    if session:
        return redirect('billing:session_detail', session_id=session.pk)
    return redirect('billing:session_open')


# ── Tier-scoped cashier queue (desk-aware) ────────────────────────────────────

@login_required
def desk_cashier_queue(request, desk_id):
    """
    Cashier queue filtered by cash desk.
    TIER desks: show only tokens whose service_tier matches desk.tier.
    Service desks (PHARMACY/OPTICAL): show tokens with matching routing items.
    VIP desks: patient names are masked for non-VIP staff.
    """
    desk = get_object_or_404(CashDesk, pk=desk_id, is_deleted=False, is_active=True)

    # Tier enforcement — cashier must have an open session at this desk
    if request.user.role == UserRole.CASHIER:
        has_session = CashierSession.objects.filter(
            cashier=request.user, cash_desk=desk,
            status=SessionStatus.OPEN,
            is_deleted=False,
        ).exists()
        if not has_session:
            messages.warning(request, f'Open a session at desk "{desk.name}" first.')
            return redirect('billing:session_open')

    from apps.core.context_processors import qms_active as _qms_active
    if not _qms_active():
        messages.error(request, 'QMS is not active.')
        return redirect('billing:cashier_queue')

    from apps.qms.models import QueueToken, TokenStatus, ServiceType as QServiceType
    today = timezone.localdate()
    qs = QueueToken.objects.filter(
        service_type=QServiceType.CASHIER,
        status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
        token_date=today,
        is_deleted=False,
    ).select_related('patient').order_by('-service_tier', 'issued_at')

    # Filter by tier/type — use DESK_TIER_GROUPS so shared desks see all their patients
    if desk.desk_type == DeskType.TIER and desk.tier:
        _tiers = DESK_TIER_GROUPS.get(desk.tier, [desk.tier])
        qs = qs.filter(service_tier__in=_tiers)
        # VIP privacy — mask names if user is not a VIP-desk cashier
        is_vip_desk = desk.tier == 'VIP'
    else:
        is_vip_desk = False

    # Exclude VIP patients from non-VIP queues at tier desks
    if desk.desk_type == DeskType.TIER and desk.tier not in ('VIP', ''):
        qs = qs.exclude(service_tier='VIP')

    if request.GET.get('partial') == '1':
        from django.template.loader import render_to_string
        from django.http import HttpResponse
        html = render_to_string('billing/_cashier_queue_rows.html', {'waiting': qs}, request=request)
        return HttpResponse(html)

    context = {
        'desk': desk,
        'waiting': qs,
        'is_vip_desk': is_vip_desk,
        'today': timezone.localdate(),
    }
    return render(request, 'billing/desk_queue.html', context)


# ── Invoice tier rerouting ────────────────────────────────────────────────────

@json_error_handler
@login_required
@require_POST
def invoice_reroute_tier(request, invoice_id):
    """
    Reroute an invoice to a different tier desk.
    Creates an InvoiceTierChange audit record.
    Only allowed on DRAFT/ISSUED invoices.
    """
    if not (_can_verify_session(request.user) or _can_cancel_invoice(request.user)):
        return JsonResponse({'error': 'Access denied.'}, status=403)

    invoice = get_object_or_404(Invoice, pk=invoice_id, is_deleted=False)
    if invoice.status not in (InvoiceStatus.DRAFT, InvoiceStatus.ISSUED):
        return JsonResponse({'error': 'Can only reroute DRAFT or ISSUED invoices.'}, status=400)

    new_tier    = request.POST.get('new_tier', '').strip()
    new_desk_id = request.POST.get('new_desk_id', '').strip()
    reason      = request.POST.get('reason', '').strip()
    if not reason:
        return JsonResponse({'error': 'Reason is required.'}, status=400)

    old_tier = invoice.service_tier
    old_desk = invoice.cash_desk
    new_desk = None
    if new_desk_id:
        try:
            new_desk = CashDesk.objects.get(pk=new_desk_id, is_deleted=False)
        except CashDesk.DoesNotExist:
            pass

    InvoiceTierChange.objects.create(
        invoice=invoice,
        old_tier=old_tier,
        new_tier=new_tier,
        old_desk=old_desk,
        new_desk=new_desk,
        changed_by=request.user,
        reason=reason,
        created_by=request.user,
    )
    invoice.service_tier = new_tier
    if new_desk:
        invoice.cash_desk = new_desk
    invoice.save(update_fields=['service_tier', 'cash_desk', 'updated_at'])

    return JsonResponse({'success': True, 'new_tier': new_tier})


# ── Discount Approval workflow ────────────────────────────────────────────────

@login_required
def discount_request(request, invoice_id):
    """
    Cashier submits a discount request requiring supervisor approval.
    """
    invoice = get_object_or_404(Invoice, pk=invoice_id, is_deleted=False)
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', '0') or '0')
        except Exception:
            amount = Decimal('0')
        reason = request.POST.get('reason', '').strip()
        if amount <= 0:
            messages.error(request, 'Discount amount must be greater than zero.')
        elif not reason:
            messages.error(request, 'Reason is required.')
        elif amount > invoice.subtotal:
            messages.error(request, 'Discount cannot exceed invoice subtotal.')
        else:
            DiscountApproval.objects.create(
                invoice=invoice,
                requested_by=request.user,
                requested_amount=amount,
                reason=reason,
                status=DiscountApprovalStatus.PENDING,
                created_by=request.user,
            )
            messages.success(request, f'Discount request of {amount:,.0f} XAF submitted for approval.')
            return redirect('billing:invoice_detail', invoice_id=invoice_id)
    return render(request, 'billing/discount_request.html', {'invoice': invoice})


@login_required
def discount_approval_list(request):
    """Supervisor view — pending discount approval requests."""
    if not _can_approve_discount(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    qs = DiscountApproval.objects.filter(
        status=DiscountApprovalStatus.PENDING, is_deleted=False
    ).select_related('invoice', 'invoice__patient', 'requested_by').order_by('-created_at')
    return render(request, 'billing/discount_approval_list.html', {'approvals': qs})


@json_error_handler
@login_required
@require_POST
def discount_decide(request, approval_id):
    """Supervisor approves or rejects a discount request."""
    if not _can_approve_discount(request.user):
        return JsonResponse({'error': 'Access denied.'}, status=403)
    approval = get_object_or_404(DiscountApproval, pk=approval_id, is_deleted=False)
    if approval.status != DiscountApprovalStatus.PENDING:
        messages.error(request, 'This request has already been decided.')
        return redirect('billing:discount_approval_list')

    decision = request.POST.get('decision', '')
    notes    = request.POST.get('notes', '').strip()
    try:
        approved_amount = Decimal(request.POST.get('approved_amount') or str(approval.requested_amount))
    except Exception:
        approved_amount = approval.requested_amount

    if decision == 'APPROVE':
        approval.status          = DiscountApprovalStatus.APPROVED
        approval.approved_by     = request.user
        approval.approved_amount = approved_amount
        approval.decision_at     = timezone.now()
        approval.decision_notes  = notes
        approval.save()
        # Apply discount to invoice
        approval.invoice.discount_amount = approved_amount
        approval.invoice.discount_reason = f'Approved by {request.user.get_full_name() or request.user.username}: {notes}'
        approval.invoice.save(update_fields=['discount_amount', 'discount_reason', 'updated_at'])
        messages.success(request, f'Discount of {approved_amount:,.0f} XAF approved and applied.')
    elif decision == 'REJECT':
        approval.status         = DiscountApprovalStatus.REJECTED
        approval.approved_by    = request.user
        approval.decision_at    = timezone.now()
        approval.decision_notes = notes
        approval.save()
        messages.info(request, 'Discount request rejected.')
    else:
        messages.error(request, 'Invalid decision.')

    return redirect('billing:discount_approval_list')


# ── Revenue by desk / tier reports ───────────────────────────────────────────

@login_required
def revenue_by_desk(request):
    """Revenue breakdown by cash desk for a date range."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    from datetime import date as _date, timedelta
    today  = _date.today()
    date_from = request.GET.get('from', str(today - timedelta(days=30)))
    date_to   = request.GET.get('to',   str(today))

    try:
        df = _date.fromisoformat(date_from)
        dt = _date.fromisoformat(date_to)
    except ValueError:
        df, dt = today - timedelta(days=30), today

    rows = (
        Payment.objects
        .filter(
            payment_date__date__gte=df,
            payment_date__date__lte=dt,
            is_deleted=False,
        )
        .exclude(invoice__cash_desk__isnull=True)
        .values(
            'invoice__cash_desk__name',
            'invoice__cash_desk__desk_type',
            'invoice__service_tier',
        )
        .annotate(total=Sum('amount'))
        .order_by('invoice__cash_desk__name')
    )

    # Tier summary
    tier_rows = (
        Payment.objects
        .filter(
            payment_date__date__gte=df,
            payment_date__date__lte=dt,
            is_deleted=False,
        )
        .values('invoice__service_tier')
        .annotate(total=Sum('amount'))
        .order_by('invoice__service_tier')
    )

    context = {
        'rows': rows,
        'tier_rows': tier_rows,
        'date_from': df,
        'date_to': dt,
    }
    return render(request, 'billing/revenue_by_desk.html', context)
