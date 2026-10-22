import json
import logging
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, F
from django.http import JsonResponse, HttpResponseForbidden
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import (Invoice, InvoiceItem, Payment, InvoiceStatus, ServiceCategory,
                     PaymentMethod, ServicePrice, Refund, CashierShift, ShiftStatus,
                     ServiceWorkOrder, WorkOrderStatus, Budget, BudgetType,
                     BankAccount, BankStatement, BankReconciliation,
                     BankReconciliationStatus, BankReconciliationItem,
                     ReconciliationItemType, CashToBank, CashToBankStatus,
                     ChequeBook, ChequeRegister, ChequeStatus,
                     StaffAdvance, AdvanceType, AdvanceStatus,
                     CashTransfer, TransferType, TransferStatus, SafeBalance,
                     CashVarianceRegister, AssetDisposal, DisposalMethod,
                     DisposalStatus, AssetRegister, AssetStatus,
                     BudgetAmendment, CashierSession,
                     FiscalPeriod, FiscalPeriodStatus,
                     JournalType, JournalEntry, JournalLine, JournalEntryStatus,
                     GLAccount, CostCenter)
from .utils import get_or_create_today_invoice
from apps.patients.models import Patient
from apps.accounts.models import UserRole
from apps.core.context_processors import qms_active as _qms_active
from apps.core.decorators import json_error_handler

logger = logging.getLogger(__name__)

# ── Desk tier groupings ───────────────────────────────────────────────────────
# Maps a desk's primary tier to ALL tiers it handles (some desks share patients).
# Update this dict when physical desk assignments change — no migration needed.
DESK_TIER_GROUPS = {
    'EXPRESS': ['EXPRESS'],
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
    """Operational financial reports — Chief Cashier, Accountants, Store Keeper and above."""
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
        UserRole.STORE_KEEPER,
    ) or user.is_superuser



def _can_view_pl(user):
    """P&L and strategic financial reports — Senior Accountant, Finance Director and above."""
    return user.role in (
        UserRole.SENIOR_ACCOUNTANT,
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
@login_required
def reports_index(request):
    """Centralised reports navigation — categorised cards for all financial reports."""
    if not (request.user.is_super_admin or request.user.role in (
        UserRole.ACCOUNTANT, UserRole.SENIOR_ACCOUNTANT, UserRole.FINANCE_DIRECTOR,
        UserRole.CHIEF_CASHIER, UserRole.BILLING_OFFICER,
        UserRole.MEDICAL_DIRECTOR, UserRole.CEO, UserRole.ADMIN_DIRECTOR, UserRole.ADMIN,
    ) or request.user.is_superuser):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    return render(request, 'billing/reports/index.html', {})


def billing_dashboard(request):
    # Operational billing roles have their own dedicated dashboards — redirect them
    if request.user.role in (UserRole.CASHIER, UserRole.CHIEF_CASHIER, UserRole.BILLING_OFFICER):
        return redirect('dashboard:home')
    if not (request.user.is_super_admin or request.user.role in (
        UserRole.CHIEF_CASHIER, UserRole.BILLING_OFFICER,
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

    # Outstanding — what patients still owe (invoice total - discounts - payments already made)
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
    # Subtract payments already collected on these invoices (covers PARTIALLY_PAID)
    paid_on_outstanding = Payment.objects.filter(
        invoice__in=outstanding_qs,
        is_deleted=False,
    ).aggregate(s=Sum('amount'))['s'] or 0
    outstanding_amount = max(0, outstanding_items_total - discount_total - paid_on_outstanding)

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

    # Revenue last 7 days for sparkline — single aggregate query (replaces 7 individual queries)
    from datetime import timedelta
    from django.db.models.functions import TruncDate
    week_start = today - timedelta(days=6)
    _seven_raw = {
        row['day']: row['t']
        for row in Payment.objects.filter(
            payment_date__date__gte=week_start,
            payment_date__date__lte=today,
            is_deleted=False,
        ).annotate(day=TruncDate('payment_date')).values('day').annotate(t=Sum('amount'))
    }
    seven_days = []
    seven_labels = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        seven_days.append(float(_seven_raw.get(d, 0) or 0))
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

    # 12-month revenue trend — single TruncMonth aggregate (replaces 12 individual queries)
    import calendar
    from django.db.models.functions import TruncMonth
    from datetime import date as _date
    twelve_start = today.replace(day=1)
    for _ in range(11):
        if twelve_start.month == 1:
            twelve_start = twelve_start.replace(year=twelve_start.year - 1, month=12)
        else:
            twelve_start = twelve_start.replace(month=twelve_start.month - 1)
    _twelve_raw = {
        row['mo']: row['t']
        for row in Payment.objects.filter(
            payment_date__date__gte=twelve_start,
            is_deleted=False,
        ).annotate(mo=TruncMonth('payment_date')).values('mo').annotate(t=Sum('amount'))
    }
    twelve_labels = []
    twelve_values = []
    cur = twelve_start
    for _ in range(12):
        # TruncMonth returns datetime; key might be datetime or date depending on DB
        _key = cur
        val = _twelve_raw.get(_key, 0) or 0
        # Also try datetime key if date key misses
        if not val:
            import datetime
            _dtkey = datetime.datetime(cur.year, cur.month, 1)
            val = _twelve_raw.get(_dtkey, 0) or 0
        twelve_labels.append(cur.strftime('%b %Y'))
        twelve_values.append(float(val))
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)

    # ── AR Aging buckets ────────────────────────────────────────────────────────
    from datetime import timedelta as _td
    _outs = Invoice.objects.filter(
        status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
        is_deleted=False
    ).select_related('patient')
    ar_current_count = ar_current_amount = 0
    ar_30_count = ar_30_amount = 0
    ar_60_count = ar_60_amount = 0
    ar_90_count = ar_90_amount = 0
    for _inv in _outs:
        _age = (today - _inv.issue_date).days
        _bal = float(_inv.balance_due)
        if _age <= 30:
            ar_current_count += 1; ar_current_amount += _bal
        elif _age <= 60:
            ar_30_count += 1; ar_30_amount += _bal
        elif _age <= 90:
            ar_60_count += 1; ar_60_amount += _bal
        else:
            ar_90_count += 1; ar_90_amount += _bal

    # ── Extra stats ─────────────────────────────────────────────────────────────
    invoices_month = Invoice.objects.filter(
        created_at__date__gte=month_start, is_deleted=False
    ).count()
    avg_invoice = 0
    if invoices_month:
        from django.db.models import ExpressionWrapper as _EW, F as _F, DecimalField as _DF
        _month_total = InvoiceItem.objects.filter(
            is_deleted=False,
            invoice__is_deleted=False,
            invoice__created_at__date__gte=month_start,
        ).aggregate(s=Sum(_EW(_F('unit_price') * _F('quantity'), output_field=_DF(max_digits=14, decimal_places=2))))['s'] or 0
        avg_invoice = round(float(_month_total) / invoices_month, 0)

    context = {
        'today': today,
        'paid_today': paid_today,
        'paid_month': paid_month,
        'outstanding_count': outstanding_count,
        'outstanding_amount': outstanding_amount,
        'invoices_today': invoices_today,
        'invoices_month': invoices_month,
        'avg_invoice': avg_invoice,
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
        # AR aging
        'ar_current_count': ar_current_count,
        'ar_current_amount': ar_current_amount,
        'ar_30_count': ar_30_count,
        'ar_30_amount': ar_30_amount,
        'ar_60_count': ar_60_count,
        'ar_60_amount': ar_60_amount,
        'ar_90_count': ar_90_count,
        'ar_90_amount': ar_90_amount,
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
    from django.utils import timezone as _tz
    q = request.GET.get('q', '')
    status = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    period = request.GET.get('period', '')  # today / week / month / year

    from django.contrib.auth import get_user_model
    User = get_user_model()

    cashier_filter = request.GET.get('cashier', '')

    from django.db.models import Count as _Count, Prefetch
    invoices = (
        Invoice.objects
        .filter(is_deleted=False)
        .select_related('patient', 'created_by')
        .prefetch_related(
            Prefetch('items', queryset=InvoiceItem.objects.filter(is_deleted=False), to_attr='_items_cache'),
            Prefetch('payments', queryset=Payment.objects.filter(is_deleted=False), to_attr='_payments_cache'),
            Prefetch('refunds', queryset=Refund.objects.filter(is_deleted=False), to_attr='_refunds_cache'),
        )
        .annotate(_item_count=_Count('items'))
        # Hide empty DRAFT invoices — these are abandoned POS sessions, not real invoices
        .exclude(status=InvoiceStatus.DRAFT, _item_count=0)
    )

    # Cashiers see ONLY their own invoices — oversight roles see all
    is_cashier = request.user.role == UserRole.CASHIER and not request.user.is_superuser
    if is_cashier:
        invoices = invoices.filter(created_by=request.user)

    # Quick period filter (cashier convenience: today/week/month/year)
    _now = _tz.localtime(_tz.now())
    if period == 'today':
        invoices = invoices.filter(created_at__date=_now.date())
    elif period == 'week':
        from datetime import timedelta as _td
        week_start = _now.date() - _td(days=_now.weekday())
        invoices = invoices.filter(created_at__date__gte=week_start)
    elif period == 'month':
        invoices = invoices.filter(created_at__year=_now.year, created_at__month=_now.month)
    elif period == 'year':
        invoices = invoices.filter(created_at__year=_now.year)

    if q:
        from apps.core.utils import patient_search_q
        # Allow search by receipt number (RCT-) — convert to invoice number (INV-)
        q_inv = q
        if q.upper().startswith('RCT-'):
            q_inv = 'INV-' + q[4:]
        invoices = invoices.filter(
            Q(invoice_number__icontains=q_inv)
            | Q(payments__receipt_number__icontains=q)
            | patient_search_q(q, prefix='patient__')
        ).distinct()
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

    # Build cashier list for the filter dropdown — only shown to oversight roles
    _billing_roles = (
        UserRole.CASHIER, UserRole.CHIEF_CASHIER, UserRole.BILLING_OFFICER,
        UserRole.ACCOUNTANT, UserRole.SENIOR_ACCOUNTANT, UserRole.FINANCE_DIRECTOR,
    )
    cashiers = (
        [] if is_cashier
        else User.objects.filter(role__in=_billing_roles, is_active=True).order_by('first_name', 'last_name')
    )

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
        'is_cashier': is_cashier,
        'active_period': period,
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
        _new_pmt = Payment.objects.create(
            invoice=invoice,
            payment_method=request.POST.get('payment_method', ''),
            amount=amount,
            reference=request.POST.get('reference', ''),
            notes=request.POST.get('notes', ''),
            received_by=request.user,
            created_by=request.user,
            cashier_session=_get_active_cashier_session(request.user),
        )
        # ── Explicit GL posting ──────────────────────────────────────────────
        try:
            from apps.billing import gl_service as _gl
            from apps.billing.models import JournalEntry as _JE
            if not _JE.objects.filter(source_type='payment', source_id=str(_new_pmt.pk)).exists():
                _gl.post_payment(_new_pmt)
            invoice.refresh_from_db()
            if not _JE.objects.filter(source_type='invoice', source_id=str(invoice.pk)).exists():
                _gl.post_invoice_issued(invoice)
        except Exception:
            pass
        from apps.accounts.models import UserAuditLog
        _log_financial(request, UserAuditLog.Action.CREATE_RECORD, invoice,
                       extra={'payment': amount, 'method': request.POST.get('payment_method', '')})
        # Open the 15-day consultation window for this patient's current visit
        # if the invoice contains a CONSULT or REG item (first-time payment)
        _try_open_consultation_window(invoice)
        invoice.refresh_from_db()
        _sync_surgical_deposit(invoice)
        # ── Payment bridge: auto-complete work orders + mark investigation/lab PAID ──
        if invoice.balance_due <= 0 and invoice.patient:
            try:
                _now = timezone.now()
                _pending_wos = ServiceWorkOrder.objects.filter(
                    patient=invoice.patient,
                    status__in=[WorkOrderStatus.PENDING_PAYMENT, WorkOrderStatus.PENDING],
                    is_deleted=False,
                    created_at__date=timezone.localdate(),
                )
                for _wo in _pending_wos:
                    _wo.status = WorkOrderStatus.DONE
                    _wo.completed_at = _now
                    _wo.completed_by = request.user
                    _wo.save(update_fields=['status', 'completed_at', 'completed_by', 'updated_at'])
                    _bridge_work_order_to_clinical(_wo, request.user)
            except Exception:
                pass
        # ── Route patient after full payment (same logic as patient_finalize) ──
        # Skip if bridge already routed patient to exam queue (REFRACTION/INVESTIGATION)
        if invoice.balance_due <= 0 and invoice.patient:
            from apps.patients.models import Visit as _PV
            _cur_visit = _PV.objects.filter(
                patient=invoice.patient, visit_date__date=timezone.localdate(), is_deleted=False,
            ).first()
            _already_routed = _cur_visit and _cur_visit.status in ('REFRACTION', 'INVESTIGATION')
            if not _already_routed:
                _route_patient_after_payment(invoice, request)
            messages.success(request, 'Payment recorded.')
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
                try:
                    from apps.core.ws_notify import notify_queue as _ws_nq
                    _ws_nq('opd')
                except Exception:
                    pass

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

                    _tier = cashier_token.service_tier
                    _notes = cashier_token.notes or ''
                    _via_refraction = 'REFRAC_FIRST' in _notes
                    _assigned_doc = cashier_token.assigned_doctor

                    # Routing decision:
                    # VIP + REFRAC_FIRST flag → optometrist does refraction first, then doctor
                    # VIP (direct)            → straight to VIP doctor workstation
                    # Express/FastTrack       → VIP/Express triage (PARAMETERS_VIP)
                    # Standard               → standard triage (PARAMETERS)
                    if _tier == ServiceTier.VIP and _via_refraction:
                        triage_stype = ServiceType.REFRACTION
                        visit.status = 'REFRACTION'
                        visit.save(update_fields=['status', 'updated_at'])
                    elif _tier == ServiceTier.VIP:
                        triage_stype = ServiceType.VIP_CONSULT
                        visit.status = VisitStatus.WAITING
                        visit.save(update_fields=['status', 'updated_at'])
                    elif _tier == ServiceTier.STANDARD:
                        triage_stype = ServiceType.PARAMETERS
                    else:
                        triage_stype = ServiceType.PARAMETERS_VIP

                    triage_num = DailyTokenSequence.next_dept_token(triage_stype)
                    QueueToken.objects.create(
                        token_number=triage_num,
                        token_date=today,
                        patient=patient,
                        visit=visit,
                        patient_name=patient.full_name,
                        service_type=triage_stype,
                        service_tier=_tier,
                        issuance_point=IssuancePoint.SYSTEM,
                        priority=TIER_PRIORITY.get(_tier, 0),
                        entry_token=cashier_token.entry_token or cashier_token,
                        issued_by=request.user,
                        notes='Auto-routed after payment',
                        assigned_doctor=_assigned_doc,
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
                try:
                    from apps.core.ws_notify import notify_queue as _ws_nq2
                    _ws_nq2('opd')
                except Exception:
                    pass
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

        # GL: reverse all payment entries for this invoice
        from apps.billing import gl_service
        gl_service.post_invoice_cancellation(invoice, user=request.user)

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

    # GL: post bad debt write-off entry
    from apps.billing import gl_service
    gl_service.post_waiver(invoice, user=request.user)

    messages.success(
        request,
        f'Invoice {invoice.invoice_number} has been waived. Reason: {reason}'
    )
    return redirect('billing:invoice_detail', invoice_id=invoice.id)


# ─────────────────────────────────────────────────────────────────────────────
# POS (Point of Sale) — Cashier Station
# ─────────────────────────────────────────────────────────────────────────────

_CAT_FALLBACK_LABELS = {
    'REG': 'Registration', 'CONSULT': 'Consultations', 'CLINICAL': 'Clinical',
    'INVEST': 'Investigations', 'LAB': 'Laboratory', 'PHARMACY': 'Pharmacy',
    'OPTICAL': 'Optical', 'SURGICAL': 'Surgeries', 'OTHER': 'Other', 'ADMISSION': 'Admission',
}


def _build_catalog_tabs(catalog):
    """
    Returns list of {key, label, services} — one entry per sub-category (family).
    Services with no sub-category fall into a tab named after their DB category.
    The list is ordered by sub_category__sort_order then by first appearance.
    """
    from collections import OrderedDict
    groups = OrderedDict()
    for svc in catalog:
        subcat_id   = svc.get('sub_category__id')
        subcat_name = svc.get('sub_category__name')
        if subcat_id and subcat_name:
            key   = f'sub_{subcat_id}'
            label = subcat_name
        else:
            cat   = svc.get('category', 'OTHER')
            key   = f'cat_{cat}'
            label = _CAT_FALLBACK_LABELS.get(cat, cat.title())
        if key not in groups:
            groups[key] = {'key': key, 'label': label, 'services': []}
        groups[key]['services'].append(svc)
    return list(groups.values())


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
            qs.order_by('category', 'sub_category__sort_order', 'sub_category__name', 'tier', 'name')
            .values('id', 'name', 'category', 'tier', 'price', 'nhis_price',
                    'insurance_price', 'requires_price_entry', 'code',
                    'gl_account__code', 'sub_category__gl_account__code',
                    'sub_category__id', 'sub_category__name', 'sub_category__sort_order',
                    'tax_rate', 'is_taxable', 'price_ht')
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
    elif _tier == 'EXPRESS':
        waiting = waiting.filter(service_tier='EXPRESS')
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
        # Prefer an open (DRAFT/ISSUED) invoice for today.
        # If only PAID invoices exist and there are new pending work orders,
        # create a fresh invoice so old paid items don't accumulate.
        _today_date = timezone.localdate()
        invoice = Invoice.objects.filter(
            patient=patient,
            issue_date=_today_date,
            status__in=[InvoiceStatus.DRAFT, InvoiceStatus.ISSUED],
            is_deleted=False,
        ).order_by('created_at').first()
        if not invoice:
            # Check if there are new pending work orders that need billing
            _has_pending_wos = ServiceWorkOrder.objects.filter(
                patient=patient,
                status__in=[WorkOrderStatus.PENDING_PAYMENT, WorkOrderStatus.PENDING],
                is_deleted=False,
                created_at__date=_today_date,
            ).exists()
            if _has_pending_wos:
                # New services to bill — create a fresh invoice
                invoice = get_or_create_today_invoice(patient, created_by=request.user)
            else:
                # No new work orders — show the most recent invoice (even if PAID)
                invoice = Invoice.objects.filter(
                    patient=patient,
                    issue_date=_today_date,
                    is_deleted=False,
                ).exclude(status=InvoiceStatus.CANCELLED).order_by('-created_at').first()
                if not invoice:
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

    # Active insurance for co-pay display + auto copay split + eligibility
    from apps.patients.models import InsuranceInfo
    active_insurance = None
    insurance_warnings = []
    insured_member = None
    preauth_warning = None
    if patient:
        active_insurance = (
            InsuranceInfo.objects
            .filter(patient=patient, is_active=True, is_deleted=False)
            .order_by('-created_at')
            .first()
        )

        # ── HMO member lookup for copay + eligibility + pre-auth ──────────
        try:
            from apps.hmo.models import InsuredMember, PreAuthorization, PreAuthStatus
            insured_member = (
                InsuredMember.objects
                .filter(patient=patient, is_active=True)
                .select_related('scheme')
                .order_by('-created_at')
                .first()
            )
            if insured_member:
                # Eligibility: card expiry check
                if insured_member.is_expired:
                    insurance_warnings.append(
                        f'Insurance card EXPIRED on {insured_member.card_expiry.strftime("%d %b %Y")}. '
                        f'Verify coverage before billing.'
                    )
                # Eligibility: annual claim ceiling check
                if insured_member.scheme.max_annual_claim:
                    from django.db.models import Sum as _SumIns
                    _year_start = timezone.localdate().replace(month=1, day=1)
                    _claims_total = insured_member.claims.filter(
                        is_deleted=False,
                        service_date__gte=_year_start,
                    ).aggregate(t=_SumIns('claimed_amount'))['t'] or 0
                    _ceiling = float(insured_member.scheme.max_annual_claim)
                    if float(_claims_total) >= _ceiling * 0.9:
                        _pct_used = round(float(_claims_total) / _ceiling * 100)
                        insurance_warnings.append(
                            f'Annual claim ceiling: {int(_claims_total):,} / {int(_ceiling):,} FCFA '
                            f'({_pct_used}% used). '
                            f'{"CEILING EXCEEDED — bill as self-pay." if _pct_used >= 100 else "Near limit — verify with scheme."}'
                        )
                # Pre-auth enforcement
                if insured_member.scheme.pre_auth_required:
                    _has_valid_preauth = PreAuthorization.objects.filter(
                        member=insured_member,
                        status=PreAuthStatus.APPROVED,
                        is_deleted=False,
                    ).filter(
                        models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=timezone.localdate())
                    ).exists()
                    if not _has_valid_preauth:
                        preauth_warning = (
                            f'{insured_member.scheme.name} requires pre-authorization. '
                            f'No valid pre-auth found for this patient. '
                            f'Request pre-auth before billing or bill as self-pay.'
                        )

                # ── Auto copay split — set insurance_amount on new invoices ──
                if invoice and invoice.insurance_amount == 0 and invoice.total > 0:
                    _copay_pct = float(insured_member.copay_pct or 20)
                    _ins_share = round(float(invoice.total) * (100 - _copay_pct) / 100)
                    if _ins_share > 0 and not insured_member.is_expired:
                        invoice.insurance_amount = _ins_share
                        invoice.save(update_fields=['insurance_amount', 'updated_at'])
        except Exception:
            pass

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
        card=Sum('amount', filter=Q(payment_method=PaymentMethod.CARD)),
        transfer=Sum('amount', filter=Q(payment_method=PaymentMethod.TRANSFER)),
    )

    _pos_session = _get_active_cashier_session(request.user)
    _pos_tier = (
        _pos_session.cash_desk.tier
        if _pos_session and _pos_session.cash_desk.desk_type == 'TIER' and _pos_session.cash_desk.tier
        else (token.service_tier if token else 'STANDARD')
    )
    from django.urls import reverse as _rev
    _queue_url = _rev('dashboard:home')  # always return cashier to their dashboard after payment
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
    # Wallet balance for this patient
    _wallet_balance = None
    if patient:
        try:
            from .models import PatientWallet
            _w = PatientWallet.objects.filter(patient=patient, is_deleted=False).first()
            _wallet_balance = int(_w.balance) if _w else 0
        except Exception:
            _wallet_balance = None

    # Pending discount approval for this invoice (blocks payment)
    from apps.billing.models import DiscountApproval, DiscountApprovalStatus
    _pending_discount = None
    if invoice:
        _pending_discount = DiscountApproval.objects.filter(
            invoice=invoice, status=DiscountApprovalStatus.PENDING, is_deleted=False
        ).order_by('-created_at').first()

    # Insurance schemes for "Change Billing Type" modal
    from apps.hmo.models import InsuranceScheme
    from .models import CorporateAccount as _CA, InvoiceRoutingType
    _insurance_schemes = InsuranceScheme.objects.filter(is_active=True).order_by('name')

    # Corporate accounts for "Change Billing Type" modal
    _corporate_accounts = _CA.objects.filter(is_deleted=False, is_active=True).order_by('name')

    # Tier enforcement: Finance Director / Senior Accountant / Admin can directly change tier.
    # Cashiers can only REQUEST a tier change (requires Finance approval).
    from apps.accounts.models import UserRole as _UR
    _direct_tier_roles = (
        _UR.SENIOR_ACCOUNTANT, _UR.FINANCE_DIRECTOR,
        _UR.ADMIN_DIRECTOR, _UR.SUPER_ADMIN, _UR.ADMIN, _UR.MEDICAL_DIRECTOR,
    )
    _can_change_tier = request.user.role in _direct_tier_roles
    _request_tier_roles = (_UR.CASHIER, _UR.CHIEF_CASHIER, _UR.ACCOUNTANT)
    _can_request_tier = not _can_change_tier and request.user.role in _request_tier_roles

    return render(request, 'billing/cashier_pos.html', {
        'token': token,
        'patient': patient,
        'invoice': invoice,
        'items': items,
        'payments': payments,
        'categories': ServiceCategory.choices,
        'payment_methods': PaymentMethod.choices,
        'service_catalog': (_sc := _get_service_catalog(cashier_station=_pos_tier)),
        'catalog_tabs': _build_catalog_tabs(_sc),
        'today': today,
        'active_consultation': active_consultation,
        'prior_unpaid_invoices': prior_unpaid_invoices,
        'active_insurance': active_insurance,
        'insured_member': insured_member,
        'insurance_warnings': insurance_warnings,
        'preauth_warning': preauth_warning,
        'doctor_orders': doctor_orders,
        'receipt_url': f"/billing/receipt/{invoice.id}/" if invoice else '',
        'shift_total': shift_totals['total'] or 0,
        'shift_cash': shift_totals['cash'] or 0,
        'shift_mobile': shift_totals['mobile'] or 0,
        'shift_card': shift_totals['card'] or 0,
        'shift_transfer': shift_totals['transfer'] or 0,
        'patient_tier': _pos_tier,
        'queue_url': _queue_url,
        'visit': _visit,
        'tier_changes': _tier_changes,
        'tier_choices': _ST.choices,
        'wallet_balance': _wallet_balance,
        'pending_discount': _pending_discount,
        'insurance_schemes': _insurance_schemes,
        'corporate_accounts': _corporate_accounts,
        'routing_choices': InvoiceRoutingType.choices,
        'can_change_tier': _can_change_tier,
        'can_request_tier': _can_request_tier,
    })  # end cashier_pos


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

    # ── Double-billing prevention ───────────────────────────────────────────
    # Check if this patient already has a PAID invoice today with the same item.
    _desc_lc = description.lower()
    _already_paid_items = InvoiceItem.objects.filter(
        invoice__patient=invoice.patient,
        invoice__issue_date=timezone.localdate(),
        invoice__status=InvoiceStatus.PAID,
        invoice__is_deleted=False,
        is_deleted=False,
    ).values_list('description', flat=True)
    for _paid_desc in _already_paid_items:
        if _paid_desc.lower() == _desc_lc:
            return JsonResponse({
                'success': False,
                'error': f'Already Paid — "{description}" was already billed and paid today. '
                         f'Cannot bill the same item twice.'
            }, status=400)

    # Also check items on the CURRENT invoice to prevent duplicate line items
    if invoice.items.filter(
        description__iexact=description, is_deleted=False,
    ).exists():
        return JsonResponse({
            'success': False,
            'error': f'Duplicate — "{description}" is already on this invoice.'
        }, status=400)

    # ── Resolve ServicePrice link and GL account code ───────────────────
    sp = None
    sp_id = request.POST.get('service_price_id', '').strip()
    if sp_id:
        sp = ServicePrice.objects.filter(pk=sp_id, is_active=True, is_deleted=False).first()
    gl_code = ''
    tax_amount = Decimal('0')
    if sp:
        gl_code = sp.get_gl_code()
        if sp.is_taxable and sp.tax_rate:
            tax_amount = (unit_price * quantity * sp.tax_rate / 100).quantize(Decimal('0.01'))
    elif not gl_code:
        from apps.billing.gl_service import get_revenue_code
        gl_code = get_revenue_code(category)

    item = InvoiceItem.objects.create(
        invoice=invoice,
        service_price=sp,
        description=description,
        category=category,
        quantity=quantity,
        unit_price=unit_price,
        gl_account_code=gl_code,
        tax_amount=tax_amount,
        created_by=request.user,
    )

    # ── Mark matching work order as PENDING (added to bill) so it leaves the Orders tab ──
    if invoice.patient:
        _desc_lower = description.lower()
        _matching_wos = ServiceWorkOrder.objects.filter(
            patient=invoice.patient,
            status=WorkOrderStatus.PENDING_PAYMENT,
            is_deleted=False,
            created_at__date=timezone.localdate(),
        )
        for _wo in _matching_wos:
            if _wo.description.lower() == _desc_lower or _desc_lower in _wo.description.lower():
                _wo.status = WorkOrderStatus.PENDING
                _wo.invoice = invoice
                _wo.save(update_fields=['status', 'invoice', 'updated_at'])
                break

    # Promote DRAFT → ISSUED when first item added;
    # revert PAID → ISSUED if a new item is added after payment (balance now positive again).
    if invoice.status in (InvoiceStatus.DRAFT, InvoiceStatus.PAID, InvoiceStatus.PARTIALLY_PAID):
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
def pos_edit_item(request, item_id):
    """AJAX: Update qty and/or unit_price of an existing invoice line item."""
    item = get_object_or_404(InvoiceItem, id=item_id, is_deleted=False)
    invoice = item.invoice

    if invoice.status in (InvoiceStatus.PAID, InvoiceStatus.PARTIALLY_PAID):
        return JsonResponse({
            'success': False,
            'error': 'Cannot edit items on a paid or partially-paid invoice.'
        }, status=400)

    try:
        qty = int(request.POST.get('quantity', item.quantity) or item.quantity)
        if qty < 1:
            raise ValueError
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid quantity.'}, status=400)

    try:
        unit_price = Decimal(request.POST.get('unit_price', str(item.unit_price)) or str(item.unit_price))
        if unit_price < 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid price.'}, status=400)

    item.quantity = qty
    item.unit_price = unit_price
    item.save(update_fields=['quantity', 'unit_price', 'updated_at'])

    invoice.refresh_from_db()
    return JsonResponse({
        'success': True,
        'line_total': int(item.line_total),
        'subtotal': int(invoice.subtotal),
        'total': int(invoice.total),
        'balance_due': int(invoice.balance_due),
    })


@json_error_handler
@login_required
@require_POST
def pos_apply_discount(request, invoice_id):
    """
    AJAX: Cashier requests a discount — creates a DiscountApproval for Finance Director review.
    Finance Director / Senior Accountant applying directly bypasses the approval queue.
    Payment is blocked until the approval is decided.
    """
    from apps.billing.models import DiscountApproval, DiscountApprovalStatus, DiscountType
    invoice = get_object_or_404(Invoice, id=invoice_id, is_deleted=False)

    discount_type = request.POST.get('discount_type', 'AMOUNT')
    discount_reason = request.POST.get('discount_reason', '').strip()

    if discount_type == 'PERCENTAGE':
        try:
            pct = Decimal(request.POST.get('discount_pct', '0') or '0')
            if pct < 0 or pct > 100:
                raise ValueError
        except (InvalidOperation, ValueError):
            return JsonResponse({'success': False, 'error': 'Percentage must be between 0 and 100.'}, status=400)
        discount_amount = (invoice.subtotal * pct / 100).quantize(Decimal('1'))
    else:
        discount_type = 'AMOUNT'
        try:
            discount_amount = Decimal(request.POST.get('discount_amount', '0') or '0')
        except InvalidOperation:
            return JsonResponse({'success': False, 'error': 'Invalid discount amount.'}, status=400)
        pct = None

    if discount_amount < 0:
        return JsonResponse({'success': False, 'error': 'Discount cannot be negative.'}, status=400)
    if discount_amount > invoice.subtotal:
        return JsonResponse({'success': False, 'error': 'Discount cannot exceed invoice subtotal.'}, status=400)
    if not discount_reason:
        return JsonResponse({'success': False, 'error': 'Reason is required for a discount.'}, status=400)

    # Finance Director / Senior Accountant can apply directly without approval queue
    can_apply_directly = _can_approve_discount(request.user)

    if can_apply_directly:
        invoice.discount_amount = discount_amount
        invoice.discount_reason = discount_reason
        invoice.save(update_fields=['discount_amount', 'discount_reason', 'updated_at'])
        invoice.refresh_from_db()
        return JsonResponse({
            'success': True,
            'status': 'applied',
            'message': f'Discount of {int(discount_amount):,} FCFA applied.',
            'discount_amount': int(invoice.discount_amount),
            'total': int(invoice.total),
            'balance_due': int(invoice.balance_due),
        })

    # Cashier: cancel any previous PENDING approval for this invoice first
    DiscountApproval.objects.filter(
        invoice=invoice, status=DiscountApprovalStatus.PENDING, is_deleted=False
    ).update(
        status=DiscountApprovalStatus.REJECTED,
        decision_notes='Superseded by new request',
        decision_at=timezone.now(),
    )

    DiscountApproval.objects.create(
        invoice=invoice,
        requested_by=request.user,
        discount_type=discount_type,
        requested_amount=discount_amount,
        requested_pct=pct,
        reason=discount_reason,
        status=DiscountApprovalStatus.PENDING,
        created_by=request.user,
    )
    return JsonResponse({
        'success': True,
        'status': 'pending',
        'message': 'Discount request sent to Finance Director for approval. Payment is blocked until approved.',
        'discount_amount': int(invoice.discount_amount),  # unchanged until approved
        'total': int(invoice.total),
        'balance_due': int(invoice.balance_due),
    })


@json_error_handler
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

    # ── Block payment if a discount is awaiting Finance Director approval ──
    from apps.billing.models import DiscountApproval, DiscountApprovalStatus
    pending_discount = DiscountApproval.objects.filter(
        invoice=invoice, status=DiscountApprovalStatus.PENDING, is_deleted=False
    ).first()
    if pending_discount:
        return JsonResponse({
            'success': False,
            'error': (
                f'Payment blocked — a discount of {int(pending_discount.requested_amount):,} FCFA '
                f'is awaiting Finance Director approval. '
                f'Wait for approval or cancel the discount request.'
            ),
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

    # ── Wallet deduction (if paying from patient wallet) ──────────────────
    if payment_method == PaymentMethod.WALLET and invoice.patient:
        try:
            from .models import PatientWallet, WalletTransaction
            _wallet = PatientWallet.objects.select_for_update().filter(
                patient=invoice.patient, is_deleted=False
            ).first()
            if not _wallet:
                return JsonResponse({
                    'success': False,
                    'error': 'This patient has no wallet. Top up wallet first.'
                }, status=400)
            if _wallet.balance < amount:
                return JsonResponse({
                    'success': False,
                    'error': f'Insufficient wallet balance: {int(_wallet.balance):,} FCFA available, {int(amount):,} FCFA required.'
                }, status=400)
            _wallet.balance -= amount
            _wallet.save(update_fields=['balance', 'updated_at'])
            WalletTransaction.objects.create(
                wallet=_wallet,
                transaction_type='DEDUCTION',
                amount=amount,
                invoice=invoice,
                balance_after=_wallet.balance,
                notes=f'POS payment for invoice {invoice.invoice_number}',
                created_by=request.user,
            )
        except Exception as _we:
            return JsonResponse({'success': False, 'error': f'Wallet error: {_we}'}, status=500)

    _new_payment = Payment.objects.create(
        invoice=invoice,
        payment_method=payment_method,
        amount=amount,
        reference=reference,
        received_by=request.user,
        created_by=request.user,
        cashier_session=_get_active_cashier_session(request.user),
    )
    # ── Explicit GL posting (belt-and-suspenders — signal may miss inside atomic) ──
    try:
        from apps.billing import gl_service as _gl
        from apps.billing.models import JournalEntry as _JE
        if not _JE.objects.filter(source_type='payment', source_id=str(_new_payment.pk)).exists():
            _gl.post_payment(_new_payment)
        invoice.refresh_from_db()
        if not _JE.objects.filter(source_type='invoice', source_id=str(invoice.pk)).exists():
            _gl.post_invoice_issued(invoice)
    except Exception:
        pass  # GL failure must never block payment confirmation
    from apps.accounts.models import UserAuditLog
    _log_financial(request, UserAuditLog.Action.CREATE_RECORD, invoice,
                   extra={'payment': str(amount), 'method': payment_method})
    # Payment.save() already calls invoice.update_status()
    _try_open_consultation_window(invoice)
    invoice.refresh_from_db()
    # Sync surgical booking deposit if this invoice is linked to a booking
    _sync_surgical_deposit(invoice)

    # ── Auto-claim generation for insured patients ────────────────────────
    # When invoice has insurance_amount > 0, auto-create an HMO claim
    if invoice.insurance_amount > 0 and invoice.patient:
        try:
            from apps.hmo.models import (
                InsuredMember as _IM, Claim as _HClaim,
                ClaimItem as _HCI, ClaimStatus as _HCS,
            )
            _member = _IM.objects.filter(
                patient=invoice.patient, is_active=True,
            ).select_related('scheme').first()
            if _member:
                # Only create if no claim already exists for this invoice
                _existing_claim = _HClaim.objects.filter(
                    invoice=invoice, is_deleted=False,
                ).exists()
                if not _existing_claim:
                    _today = timezone.localdate()
                    _claim_count = _HClaim.objects.filter(
                        member__scheme=_member.scheme,
                        service_date=_today,
                    ).count() + 1
                    _claim_number = (
                        f'{_member.scheme.code}-{_today.strftime("%Y%m%d")}-{_claim_count:04d}'
                    )
                    # Find the patient's visit for today
                    from apps.patients.models import Visit as _ClaimVisit
                    _visit = _ClaimVisit.objects.filter(
                        patient=invoice.patient, is_deleted=False,
                    ).order_by('-visit_date').first()
                    _claim = _HClaim.objects.create(
                        claim_number=_claim_number,
                        member=_member,
                        visit=_visit,
                        invoice=invoice,
                        status=_HCS.DRAFT,
                        service_date=_today,
                        claimed_amount=invoice.insurance_amount,
                        patient_copay=invoice.patient_amount,
                        created_by=request.user,
                    )
                    # Create claim line items from invoice items
                    for _item in invoice.items.filter(is_deleted=False):
                        _copay_pct = float(_member.copay_pct or 20) / 100
                        _item_claimed = round(float(_item.line_total) * (1 - _copay_pct), 2)
                        _HCI.objects.create(
                            claim=_claim,
                            service_name=_item.description,
                            quantity=_item.quantity,
                            unit_price=_item.unit_price,
                            claimed_amount=_item_claimed,
                        )
        except Exception:
            pass  # Don't block payment if claim creation fails

    # ── Payment bridge: when invoice is fully paid, auto-complete work orders
    # and mark investigation/lab orders as PAID ─────────────────────────────
    if invoice.balance_due <= 0 and invoice.patient:
        try:
            _now = timezone.now()
            pending_wos = ServiceWorkOrder.objects.filter(
                patient=invoice.patient,
                status__in=[WorkOrderStatus.PENDING_PAYMENT, WorkOrderStatus.PENDING],
                is_deleted=False,
                created_at__date=timezone.localdate(),
            )
            for _wo in pending_wos:
                _wo.status = WorkOrderStatus.DONE
                _wo.completed_at = _now
                _wo.completed_by = request.user
                _wo.save(update_fields=['status', 'completed_at', 'completed_by', 'updated_at'])
                _bridge_work_order_to_clinical(_wo, request.user)
        except Exception:
            pass  # Never block payment response

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
    # Prefer the most recent PAID invoice (the one the cashier just finished paying).
    # Fall back to the latest non-cancelled invoice.
    invoice = Invoice.objects.filter(
        patient=token.patient,
        issue_date=today,
        status=InvoiceStatus.PAID,
        is_deleted=False,
    ).order_by('-created_at').first()
    if not invoice:
        invoice = Invoice.objects.filter(
            patient=token.patient,
            issue_date=today,
            is_deleted=False,
        ).exclude(status=InvoiceStatus.CANCELLED).order_by('-created_at').first()

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

        # VIP patients skip triage — they go directly to VIP doctor workstation.
        is_vip = (token.service_tier == ServiceTier.VIP)
        initial_status = VisitStatus.WAITING if is_vip else VisitStatus.PARAMETERS

        # Check if the payment bridge already routed this patient to an examiner
        # (e.g. REFRACTION after nurse-ordered exam payment).
        # If so, do NOT overwrite their status or create a triage token.
        _bridge_routed = visit and visit.status in ('REFRACTION', 'INVESTIGATION', 'LABORATORY')

        if not visit:
            has_prior = Visit.objects.filter(
                patient=token.patient, is_deleted=False
            ).exists()
            visit = Visit.objects.create(
                patient=token.patient,
                visit_type=VisitType.FOLLOW_UP if has_prior else VisitType.NEW,
                chief_complaint='',
                status=initial_status,
                service_tier=token.service_tier,
                created_by=request.user,
            )
        elif not _bridge_routed:
            visit.status = initial_status
            visit.save(update_fields=['status', 'updated_at'])

        # 3 — Create next queue token (tier-aware) — only when QMS is active
        # Skip if bridge already routed patient to examiner queue.
        # VIP → VIP_CONSULT (doctor workstation directly, no triage step)
        # Express/FastTrack → PARAMETERS_VIP (VIP/Express triage)
        # Standard → PARAMETERS (standard triage)
        if _qms_active() and not _bridge_routed:
            if token.service_tier == ServiceTier.STANDARD:
                triage_stype = ServiceType.PARAMETERS
            elif is_vip:
                triage_stype = ServiceType.VIP_CONSULT
            else:
                triage_stype = ServiceType.PARAMETERS_VIP
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

    # Notify ALL relevant queues after payment — instant live updates everywhere
    try:
        from apps.core.ws_notify import notify_queue as _ws_nq3
        _ws_nq3('opd')
        _ws_nq3('cashier')
        _ws_nq3('workstation')
        _ws_nq3('invest')
        _ws_nq3('lab')
        _ws_nq3('pharmacy')
    except Exception:
        pass

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
    _today_date = timezone.localdate()
    invoice = Invoice.objects.filter(
        patient=patient,
        issue_date=_today_date,
        is_deleted=False,
    ).exclude(status=InvoiceStatus.CANCELLED).order_by('created_at').first()
    if not invoice:
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

    # ── HMO member: eligibility + pre-auth + auto copay (same as main POS) ──
    insurance_warnings = []
    insured_member = None
    preauth_warning = None
    try:
        from apps.hmo.models import InsuredMember, PreAuthorization, PreAuthStatus
        insured_member = (
            InsuredMember.objects
            .filter(patient=patient, is_active=True)
            .select_related('scheme')
            .order_by('-created_at')
            .first()
        )
        if insured_member:
            if insured_member.is_expired:
                insurance_warnings.append(
                    f'Insurance card EXPIRED on {insured_member.card_expiry.strftime("%d %b %Y")}. '
                    f'Verify coverage before billing.'
                )
            if insured_member.scheme.max_annual_claim:
                from django.db.models import Sum as _SumIns2
                _year_start2 = timezone.localdate().replace(month=1, day=1)
                _claims_total2 = insured_member.claims.filter(
                    is_deleted=False, service_date__gte=_year_start2,
                ).aggregate(t=_SumIns2('claimed_amount'))['t'] or 0
                _ceiling2 = float(insured_member.scheme.max_annual_claim)
                if float(_claims_total2) >= _ceiling2 * 0.9:
                    _pct2 = round(float(_claims_total2) / _ceiling2 * 100)
                    insurance_warnings.append(
                        f'Annual ceiling: {int(_claims_total2):,} / {int(_ceiling2):,} FCFA ({_pct2}%). '
                        f'{"CEILING EXCEEDED." if _pct2 >= 100 else "Near limit."}'
                    )
            if insured_member.scheme.pre_auth_required:
                _has_pa = PreAuthorization.objects.filter(
                    member=insured_member, status=PreAuthStatus.APPROVED, is_deleted=False,
                ).filter(
                    models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=timezone.localdate())
                ).exists()
                if not _has_pa:
                    preauth_warning = (
                        f'{insured_member.scheme.name} requires pre-authorization. '
                        f'No valid pre-auth found. Request pre-auth or bill as self-pay.'
                    )
            if invoice and invoice.insurance_amount == 0 and invoice.total > 0:
                _copay2 = float(insured_member.copay_pct or 20)
                _ins2 = round(float(invoice.total) * (100 - _copay2) / 100)
                if _ins2 > 0 and not insured_member.is_expired:
                    invoice.insurance_amount = _ins2
                    invoice.save(update_fields=['insurance_amount', 'updated_at'])
    except Exception:
        pass

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
        card=Sum('amount', filter=Q(payment_method=PaymentMethod.CARD)),
        transfer=Sum('amount', filter=Q(payment_method=PaymentMethod.TRANSFER)),
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
    _pqueue_url = _rev('dashboard:home')
    _ppos_wallet = None
    if patient:
        try:
            from .models import PatientWallet
            _pw = PatientWallet.objects.filter(patient=patient, is_deleted=False).first()
            _ppos_wallet = int(_pw.balance) if _pw else 0
        except Exception:
            _ppos_wallet = None
    return render(request, 'billing/cashier_pos.html', {
        'token': None,
        'patient': patient,
        'invoice': invoice,
        'items': items,
        'payments': payments,
        'categories': ServiceCategory.choices,
        'payment_methods': PaymentMethod.choices,
        'service_catalog': (_psc := _get_service_catalog(cashier_station=_ppos_tier)),
        'catalog_tabs': _build_catalog_tabs(_psc),
        'today': today,
        'active_consultation': active_consultation,
        'prior_unpaid_invoices': prior_unpaid_invoices,
        'active_insurance': active_insurance,
        'insured_member': insured_member,
        'insurance_warnings': insurance_warnings,
        'preauth_warning': preauth_warning,
        'doctor_orders': doctor_orders,
        'receipt_url': f"/billing/receipt/{invoice.id}/" if invoice else '',
        'shift_total': shift_totals['total'] or 0,
        'shift_cash': shift_totals['cash'] or 0,
        'shift_mobile': shift_totals['mobile'] or 0,
        'shift_card': shift_totals['card'] or 0,
        'shift_transfer': shift_totals['transfer'] or 0,
        'patient_tier': _ppos_tier,
        'queue_url': _pqueue_url,
        'wallet_balance': _ppos_wallet,
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
    ).exclude(status=InvoiceStatus.CANCELLED).order_by('created_at').first()

    if not invoice:
        return JsonResponse({'success': False, 'error': 'No invoice found for today.'}, status=400)
    if invoice.balance_due > 0:
        return JsonResponse({
            'success': False,
            'error': f'Balance of {int(invoice.balance_due)} FCFA still outstanding.'
        }, status=400)

    _try_open_consultation_window(invoice)

    # ── Payment bridge: auto-complete work orders + mark investigation/lab PAID ──
    try:
        _now = timezone.now()
        _pending_wos = ServiceWorkOrder.objects.filter(
            patient=patient,
            status__in=[WorkOrderStatus.PENDING_PAYMENT, WorkOrderStatus.PENDING],
            is_deleted=False,
            created_at__date=today,
        )
        for _wo in _pending_wos:
            _wo.status = WorkOrderStatus.DONE
            _wo.completed_at = _now
            _wo.completed_by = request.user
            _wo.save(update_fields=['status', 'completed_at', 'completed_by', 'updated_at'])
            _bridge_work_order_to_clinical(_wo, request.user)
    except Exception:
        pass

    # Check if bridge already routed patient to exam queue (REFRACTION/INVESTIGATION)
    from apps.patients.models import Visit as _FV
    _fin_visit = _FV.objects.filter(
        patient=patient, visit_date__date=today, is_deleted=False,
    ).first()
    _already_routed = _fin_visit and _fin_visit.status in ('REFRACTION', 'INVESTIGATION')
    if not _already_routed:
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
    total_paid = sum(p.amount for p in payments)
    change_given = max(0, total_paid - invoice.total)
    from apps.reports.views import _sig_b64
    ctx = {
        'invoice': invoice,
        'items': items,
        'payments': payments,
        'today_token': today_token,
        'change_given': change_given,
        'cashier_signature': _sig_b64(invoice.created_by),
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
    # Notify cashier dashboard so they see the new order without refreshing
    try:
        from apps.core.ws_notify import notify_queue
        notify_queue('cashier')
    except Exception:
        pass
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


def _bridge_work_order_to_clinical(wo, user):
    """
    Payment bridge: when a ServiceWorkOrder is marked DONE (paid), update the
    corresponding InvestigationOrder or LabOrder payment_status to PAID so the
    technician's workstation can see it.
    """
    now = timezone.now()

    # ── Investigation orders ──────────────────────────────────────────────
    # CLINICAL_EXAM (refraction, orthoptics, low vision) also creates InvestigationOrders
    if wo.category in (ServiceCategory.INVESTIGATION, ServiceCategory.CLINICAL_EXAM) and wo.patient_id:
        try:
            from apps.investigations.models import InvestigationOrder, PaymentStatus as InvPS
            _inv_filter = {'patient_id': wo.patient_id, 'payment_status': InvPS.UNPAID, 'is_deleted': False}
            if wo.consultation_id:
                _inv_filter['consultation_id'] = wo.consultation_id
            else:
                # No consultation link — match today's unpaid orders for this patient
                _inv_filter['created_at__date'] = now.date()
            InvestigationOrder.objects.filter(**_inv_filter).update(
                payment_status=InvPS.PAID,
                payment_authorized_by=user,
                payment_authorized_at=now,
            )
        except Exception:
            pass

    # ── Lab orders ────────────────────────────────────────────────────────
    if wo.category == ServiceCategory.LABORATORY:
        try:
            from apps.laboratory.models import LabOrder, PaymentStatus as LabPS
            # Per-test tracking: if work order links to a specific LabOrderItem,
            # update that item's parent LabOrder
            if wo.lab_order_item_id:
                order = wo.lab_order_item.order
                if order.payment_status == LabPS.UNPAID:
                    # Check if ALL items for this order are now paid
                    total_items = order.items.count()
                    paid_wos = ServiceWorkOrder.objects.filter(
                        lab_order_item__order=order,
                        status=WorkOrderStatus.DONE,
                        is_deleted=False,
                    ).count()
                    # Include the current WO which was just marked DONE
                    if paid_wos >= total_items:
                        order.payment_status = LabPS.PAID
                        order.payment_authorized_by = user
                        order.payment_authorized_at = now
                        order.save(update_fields=[
                            'payment_status', 'payment_authorized_by',
                            'payment_authorized_at', 'updated_at',
                        ])
            elif wo.consultation_id and wo.patient_id:
                # Fallback: match by consultation + patient
                LabOrder.objects.filter(
                    consultation_id=wo.consultation_id,
                    patient_id=wo.patient_id,
                    payment_status=LabPS.UNPAID,
                    is_deleted=False,
                ).update(
                    payment_status=LabPS.PAID,
                    payment_authorized_by=user,
                    payment_authorized_at=now,
                )
        except Exception:
            pass

    # ── Auto-route patient after exam payment ──────────────────────────────
    # After cashier pays for investigation/exam, route patient to the examiner queue.
    # Works for both doctor-ordered and nurse-ordered exams.
    # Routes when ALL today's investigation orders for this patient are paid.
    if wo.category in (ServiceCategory.INVESTIGATION, ServiceCategory.CLINICAL_EXAM) and wo.patient_id:
        try:
            from apps.patients.models import Visit
            from apps.investigations.models import InvestigationOrder, PaymentStatus as _BridgePS
            _today = timezone.localdate()
            _visit = Visit.objects.filter(
                patient_id=wo.patient_id,
                visit_date__date=_today,
                is_deleted=False,
            ).exclude(
                status__in=['COMPLETED', 'DISCHARGED', 'CANCELLED']
            ).first()
            if _visit and _visit.status not in ('REFRACTION', 'INVESTIGATION'):
                # Only route if not already at examiner and all orders are paid
                # Use visit FK when available, fallback to date for legacy orders
                from django.db.models import Q as _BQ
                _order_filter = _BQ(visit=_visit) | _BQ(visit__isnull=True, patient_id=wo.patient_id, created_at__date=_today)
                _still_unpaid = InvestigationOrder.objects.filter(
                    _order_filter,
                    payment_status=_BridgePS.UNPAID,
                    is_deleted=False,
                ).exists()
                if not _still_unpaid:
                    _paid_order = InvestigationOrder.objects.filter(
                        _order_filter,
                        payment_status=_BridgePS.PAID,
                        status='ORDERED',
                        is_deleted=False,
                    ).select_related('investigation_type').first()
                    if _paid_order:
                        from apps.investigations.models import get_category_for_code as _get_cat
                        _inv_type = _paid_order.investigation_type
                        # Use the authoritative code map first — this fixes legacy InvestigationType
                        # records that were stored with 'INVEST' or 'OTHER' before the mapping existed.
                        _cat = _get_cat(_inv_type.code, default=_inv_type.category)
                        # Last-resort fallback: if category still doesn't route to optometry,
                        # check whether the visit was dispatched to an optometry department.
                        _OPTOM_CATS = {'REFRACTION', 'ORTHOPTICS', 'LOW_VISION'}
                        if _cat not in _OPTOM_CATS:
                            _v_dept_code = getattr(getattr(_visit, 'department', None), 'code', '')
                            if _v_dept_code in ('REFRAC', 'PEDS_REFRAC', 'LOW_VIS', 'ORTHO'):
                                _cat = 'REFRACTION'
                        from apps.core.patient_flow import auto_route_to_investigation

                        class _VisitHolder:
                            def __init__(self, v): self.visit = v
                        auto_route_to_investigation(_VisitHolder(_visit), ordered_by=user, category=_cat)
        except Exception:
            pass

    # ── Notify investigation/lab workstation via WebSocket ─────────────────
    try:
        from apps.core.ws_notify import notify_queue
        if wo.category in (ServiceCategory.INVESTIGATION, ServiceCategory.CLINICAL_EXAM):
            notify_queue('invest')
            notify_queue('workstation')
        elif wo.category == ServiceCategory.LABORATORY:
            notify_queue('lab')
        notify_queue('cashier')  # cashier POS should also update
    except Exception:
        pass


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

    # ── Payment bridge: mark investigation/lab orders as PAID ──────────────
    _bridge_work_order_to_clinical(wo, request.user)

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
            role__in=[UserRole.CASHIER, UserRole.BILLING_OFFICER, UserRole.OPTICAL_DISPENSER, UserRole.PHARMACIST, UserRole.HEAD_PHARMACIST],
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
    if not (_can_verify_shift(request.user) or _can_view_financial_reports(request.user)):
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
    from .models import ServiceTierFilter, ServiceSubCategory, GLAccount, EntryType
    q = request.GET.get('q', '')
    cat = request.GET.get('cat', '')
    sub = request.GET.get('sub', '')
    tier = request.GET.get('tier', '')
    etype = request.GET.get('etype', '')
    prices = ServicePrice.objects.select_related(
        'sub_category', 'gl_account', 'purchase_gl_account',
        'stock_gl_account', 'stock_variation_gl_account',
    ).filter(is_deleted=False)
    if q:
        prices = prices.filter(Q(name__icontains=q) | Q(code__icontains=q))
    if cat:
        prices = prices.filter(category=cat)
    if sub:
        prices = prices.filter(sub_category_id=sub)
    if tier != '':
        prices = prices.filter(tier=tier)
    if etype:
        prices = prices.filter(entry_type=etype)
    prices = prices.order_by('entry_type', 'category', 'sub_category__sort_order', 'name')
    from django.core.paginator import Paginator
    paginator = Paginator(prices, 50)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    sub_categories = ServiceSubCategory.objects.filter(is_deleted=False).select_related('gl_account').order_by('category', 'sort_order')
    gl_revenue  = GLAccount.objects.filter(is_active=True, account_type='REVENUE').order_by('code')
    gl_expense  = GLAccount.objects.filter(is_active=True, account_type='EXPENSE').order_by('code')
    gl_asset    = GLAccount.objects.filter(is_active=True, account_type='ASSET').order_by('code')
    tier_choices = [('', 'All Tiers')] + [(k, v) for k, v in [
        ('STANDARD', 'Standard Desk'),
        ('EXPRESS', 'Express Desk'),
        ('VIP', 'VIP Desk'),
        ('EVIP', 'Executive VIP Desk'),
        ('INSURED', 'Insured / HMO Desk'),
    ]]
    return render(request, 'billing/service_prices.html', {
        'prices': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'categories': ServiceCategory.choices,
        'entry_types': EntryType.choices,
        'sub_categories': sub_categories,
        'gl_accounts': gl_revenue,
        'gl_expense_accounts': gl_expense,
        'gl_asset_accounts': gl_asset,
        'tiers': tier_choices,
        'search': q,
        'filter_cat': cat,
        'filter_sub': sub,
        'filter_tier': tier,
        'filter_etype': etype,
        'total_count': paginator.count,
    })


def _service_price_form_context(request):
    """Shared context for create/edit service price form."""
    from .models import ServiceSubCategory, GLAccount, EntryType
    sub_categories = ServiceSubCategory.objects.filter(is_deleted=False).select_related('gl_account').order_by('category', 'sort_order')
    gl_revenue = GLAccount.objects.filter(is_active=True, account_type='REVENUE').order_by('code')
    gl_expense = GLAccount.objects.filter(is_active=True, account_type='EXPENSE').order_by('code')
    gl_asset   = GLAccount.objects.filter(is_active=True, account_type='ASSET').order_by('code')
    return {
        'categories': ServiceCategory.choices,
        'sub_categories': sub_categories,
        'gl_accounts': gl_revenue,
        'gl_expense_accounts': gl_expense,
        'gl_asset_accounts': gl_asset,
    }


@login_required
def service_price_create(request):
    """Create a new service price entry. Store Keeper can add ITEM entries only."""
    if not _can_authorize_billing(request.user) and request.user.role != UserRole.STORE_KEEPER:
        messages.error(request, 'Access denied.')
        return redirect('billing:service_price_list')

    if request.method == 'GET':
        ctx = _service_price_form_context(request)
        ctx['default_type'] = request.GET.get('type', 'SERVICE')
        return render(request, 'billing/service_price_form.html', ctx)
    name = request.POST.get('name', '').strip()
    category = request.POST.get('category', '').strip()
    price_str = request.POST.get('price', '').strip()
    entry_type = request.POST.get('entry_type', 'SERVICE').strip()
    tier_val = request.POST.get('tier', '').strip()

    if not name or not category or not price_str:
        messages.error(request, 'Name, category and price are required.')
        return redirect('billing:service_price_list')

    # Tier is mandatory for services, optional for items
    if entry_type == 'SERVICE' and not tier_val:
        messages.error(request, 'Desk Tier is mandatory for services. Please select a tier.')
        return redirect('billing:service_price_list')

    try:
        price = Decimal(price_str)
    except InvalidOperation:
        messages.error(request, 'Invalid price.')
        return redirect('billing:service_price_list')

    nhis = request.POST.get('nhis_price', '').strip()
    ins  = request.POST.get('insurance_price', '').strip()
    price_ht_str = request.POST.get('price_ht', '').strip()
    tax_rate_str = request.POST.get('tax_rate', '').strip()
    sub_cat_id = request.POST.get('sub_category', '').strip()
    gl_acct_id = request.POST.get('gl_account', '').strip()
    purchase_gl = request.POST.get('purchase_gl_account', '').strip()
    stock_gl = request.POST.get('stock_gl_account', '').strip()
    stock_var_gl = request.POST.get('stock_variation_gl_account', '').strip()

    is_item = entry_type == 'ITEM'
    shelf_life = request.POST.get('shelf_life_days', '').strip()
    alert_days = request.POST.get('expiry_alert_days', '').strip()
    ServicePrice.objects.create(
        entry_type=entry_type,
        name=name,
        code=request.POST.get('code', '').strip(),
        category=category,
        sub_category_id=sub_cat_id or None,
        tier=tier_val,
        gl_account_id=gl_acct_id or None,
        purchase_gl_account_id=purchase_gl or None,
        stock_gl_account_id=stock_gl or None,
        stock_variation_gl_account_id=stock_var_gl or None,
        price_ht=Decimal(price_ht_str) if price_ht_str else Decimal('0'),
        tax_rate=Decimal(tax_rate_str) if tax_rate_str else Decimal('0'),
        price=price,
        nhis_price=Decimal(nhis) if nhis else None,
        insurance_price=Decimal(ins) if ins else None,
        is_stockable=is_item or bool(request.POST.get('is_stockable')),
        is_taxable=bool(request.POST.get('is_taxable')),
        requires_price_entry=bool(request.POST.get('requires_price_entry')),
        is_active='is_active' in request.POST,
        track_batch='track_batch' in request.POST,
        track_expiry='track_expiry' in request.POST,
        shelf_life_days=int(shelf_life) if shelf_life else None,
        expiry_alert_days=int(alert_days) if alert_days else 30,
        valuation_method=request.POST.get('valuation_method', 'AVCO'),
        created_by=request.user,
    )
    label = 'Item' if is_item else 'Service'
    messages.success(request, f'{label} "{name}" added to price list.')
    return redirect('billing:service_price_list')


@login_required
@require_POST
def service_price_edit(request, price_id):
    """Edit an existing service price. Store Keeper can edit ITEM entries."""
    if not _can_authorize_billing(request.user) and request.user.role != UserRole.STORE_KEEPER:
        return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)
    sp = get_object_or_404(ServicePrice, id=price_id, is_deleted=False)
    try:
        entry_type = request.POST.get('entry_type', sp.entry_type).strip()
        tier_val = request.POST.get('tier', sp.tier).strip()

        # Tier is mandatory for services
        if entry_type == 'SERVICE' and not tier_val:
            return JsonResponse({'success': False, 'error': 'Desk Tier is mandatory for services.'}, status=400)

        sp.entry_type = entry_type
        sp.name     = request.POST.get('name', sp.name).strip()
        sp.category = request.POST.get('category', sp.category).strip()
        sp.tier     = tier_val
        sp.price    = Decimal(request.POST.get('price', str(sp.price)))
        nhis = request.POST.get('nhis_price', '').strip()
        ins  = request.POST.get('insurance_price', '').strip()
        sp.nhis_price      = Decimal(nhis) if nhis else None
        sp.insurance_price = Decimal(ins) if ins else None
        sp.code            = request.POST.get('code', sp.code).strip()
        sp.requires_price_entry = bool(request.POST.get('requires_price_entry'))
        # Pricing fields
        price_ht = request.POST.get('price_ht', '').strip()
        tax_rate = request.POST.get('tax_rate', '').strip()
        sub_cat  = request.POST.get('sub_category', '').strip()
        gl_acct  = request.POST.get('gl_account', '').strip()
        sp.price_ht = Decimal(price_ht) if price_ht else Decimal('0')
        sp.tax_rate = Decimal(tax_rate) if tax_rate else Decimal('0')
        sp.sub_category_id = sub_cat or None
        sp.gl_account_id = gl_acct or None
        # ERP GL accounts
        purchase_gl = request.POST.get('purchase_gl_account', '').strip()
        stock_gl = request.POST.get('stock_gl_account', '').strip()
        stock_var_gl = request.POST.get('stock_variation_gl_account', '').strip()
        sp.purchase_gl_account_id = purchase_gl or None
        sp.stock_gl_account_id = stock_gl or None
        sp.stock_variation_gl_account_id = stock_var_gl or None
        # Items are always stockable
        sp.is_stockable = (entry_type == 'ITEM') or bool(request.POST.get('is_stockable'))
        sp.is_taxable   = bool(request.POST.get('is_taxable'))
        sp.save()
        return JsonResponse({'success': True})
    except (InvalidOperation, Exception) as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
def service_price_edit_form(request, price_id):
    """GET: render the tabbed edit form. POST: save changes and redirect."""
    if not _can_authorize_billing(request.user) and request.user.role != UserRole.STORE_KEEPER:
        messages.error(request, 'Access denied.')
        return redirect('billing:service_price_list')
    sp = get_object_or_404(ServicePrice, id=price_id, is_deleted=False)
    if request.method == 'GET':
        ctx = _service_price_form_context(request)
        ctx['sp'] = sp
        return render(request, 'billing/service_price_form.html', ctx)
    # POST — save changes
    try:
        sp.name        = request.POST.get('name', sp.name).strip()
        sp.code        = request.POST.get('code', sp.code).strip()
        sp.entry_type  = request.POST.get('entry_type', sp.entry_type).strip()
        sp.category    = request.POST.get('category', sp.category).strip()
        sp.tier        = request.POST.get('tier', '').strip()
        sp.sub_category_id = request.POST.get('sub_category', '') or None
        sp.gl_account_id   = request.POST.get('gl_account', '') or None
        sp.purchase_gl_account_id   = request.POST.get('purchase_gl_account', '') or None
        sp.stock_gl_account_id      = request.POST.get('stock_gl_account', '') or None
        sp.stock_variation_gl_account_id = request.POST.get('stock_variation_gl_account', '') or None
        price_ht = request.POST.get('price_ht', '').strip()
        tax_rate = request.POST.get('tax_rate', '').strip()
        nhis     = request.POST.get('nhis_price', '').strip()
        ins      = request.POST.get('insurance_price', '').strip()
        sp.price_ht        = Decimal(price_ht) if price_ht else Decimal('0')
        sp.tax_rate        = Decimal(tax_rate) if tax_rate else Decimal('0')
        sp.price           = Decimal(request.POST.get('price', str(sp.price)))
        sp.nhis_price      = Decimal(nhis) if nhis else None
        sp.insurance_price = Decimal(ins) if ins else None
        sp.is_taxable            = 'is_taxable' in request.POST
        sp.is_stockable          = (sp.entry_type == 'ITEM') or ('is_stockable' in request.POST)
        sp.requires_price_entry  = 'requires_price_entry' in request.POST
        sp.is_active             = 'is_active' in request.POST
        # Tracking fields (items only)
        sp.track_batch       = 'track_batch' in request.POST
        sp.track_expiry      = 'track_expiry' in request.POST
        shelf_life = request.POST.get('shelf_life_days', '').strip()
        alert_days = request.POST.get('expiry_alert_days', '').strip()
        sp.shelf_life_days   = int(shelf_life) if shelf_life else None
        sp.expiry_alert_days = int(alert_days) if alert_days else 30
        sp.valuation_method  = request.POST.get('valuation_method', 'AVCO')
        sp.updated_by = request.user
        sp.save()
        messages.success(request, f'"{sp.name}" updated.')
    except (InvalidOperation, Exception) as e:
        messages.error(request, f'Error saving: {e}')
        ctx = _service_price_form_context(request)
        ctx['sp'] = sp
        return render(request, 'billing/service_price_form.html', ctx)
    return redirect('billing:service_price_list')


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
# SUB-CATEGORY MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

from .models import ServiceSubCategory


@login_required
def sub_category_list(request):
    """Dedicated page to manage service sub-categories (families)."""
    if not _can_authorize_billing(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    from .models import GLAccount
    subs = (ServiceSubCategory.objects.filter(is_deleted=False)
            .select_related('gl_account')
            .order_by('category', 'sort_order', 'name'))
    # count services per sub-category
    from django.db.models import Count
    counts = dict(
        ServicePrice.objects.filter(is_deleted=False, sub_category__isnull=False)
        .values_list('sub_category_id')
        .annotate(c=Count('id'))
        .values_list('sub_category_id', 'c')
    )
    for s in subs:
        s.service_count = counts.get(s.id, 0)
    gl_accounts = GLAccount.objects.filter(is_active=True, account_type='REVENUE').order_by('code')
    return render(request, 'billing/sub_category_list.html', {
        'sub_categories': subs,
        'categories': ServiceCategory.choices,
        'gl_accounts': gl_accounts,
    })


@login_required
@require_POST
def sub_category_create(request):
    """Create a service sub-category."""
    if not _can_authorize_billing(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:sub_category_list')
    from .models import GLAccount
    name = request.POST.get('name', '').strip()
    category = request.POST.get('category', '').strip()
    if not name or not category:
        messages.error(request, 'Name and category are required.')
        return redirect('billing:sub_category_list')
    code = request.POST.get('code', '').strip()
    gl_id = request.POST.get('gl_account', '').strip()
    ServiceSubCategory.objects.create(
        category=category, name=name, code=code,
        gl_account_id=gl_id or None,
        created_by=request.user,
    )
    messages.success(request, f'Sub-category "{name}" created.')
    return redirect('billing:sub_category_list')


@login_required
@require_POST
def sub_category_edit(request, sub_id):
    """Edit a service sub-category."""
    if not _can_authorize_billing(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)
    from .models import GLAccount
    sc = get_object_or_404(ServiceSubCategory, id=sub_id, is_deleted=False)
    try:
        sc.name = request.POST.get('name', sc.name).strip()
        sc.category = request.POST.get('category', sc.category).strip()
        sc.code = request.POST.get('code', sc.code).strip()
        gl_id = request.POST.get('gl_account', '').strip()
        sc.gl_account_id = gl_id or None
        sort_str = request.POST.get('sort_order', '').strip()
        if sort_str:
            sc.sort_order = int(sort_str)
        sc.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_POST
def sub_category_delete(request, sub_id):
    """Soft-delete a service sub-category."""
    if not _can_authorize_billing(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)
    sc = get_object_or_404(ServiceSubCategory, id=sub_id, is_deleted=False)
    sc.is_deleted = True
    sc.save(update_fields=['is_deleted', 'updated_at'])
    return JsonResponse({'success': True})


# ═══════════════════════════════════════════════════════════════════════════════
# REVENUE ANALYSIS REPORT
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def revenue_analysis(request):
    """Revenue breakdown by category → sub-category → GL account."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from .models import InvoiceItem, JournalLine, GLAccount
    from django.db.models import Sum, Count, F

    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    # Revenue from invoices (by category)
    items_qs = InvoiceItem.objects.filter(
        invoice__is_deleted=False, is_deleted=False,
        invoice__status__in=['ISSUED', 'PARTIAL', 'PAID'],
    )
    if date_from:
        items_qs = items_qs.filter(invoice__issue_date__gte=date_from)
    if date_to:
        items_qs = items_qs.filter(invoice__issue_date__lte=date_to)

    # By category
    by_category = list(
        items_qs.values('category')
        .annotate(
            total=Sum(F('quantity') * F('unit_price')),
            count=Count('id'),
        )
        .order_by('-total')
    )
    for row in by_category:
        row['label'] = dict(ServiceCategory.choices).get(row['category'], row['category'])

    grand_total = sum(r['total'] or 0 for r in by_category)

    # By sub-category (where available)
    by_sub = list(
        items_qs.filter(service_price__sub_category__isnull=False)
        .values(
            'service_price__sub_category__name',
            'service_price__sub_category__gl_account__code',
            'category',
        )
        .annotate(total=Sum(F('quantity') * F('unit_price')), count=Count('id'))
        .order_by('category', '-total')
    )

    # Revenue from GL (posted journal lines on revenue accounts)
    gl_qs = JournalLine.objects.filter(
        entry__is_deleted=False,
        account__account_type='REVENUE',
    )
    if date_from:
        gl_qs = gl_qs.filter(entry__entry_date__gte=date_from)
    if date_to:
        gl_qs = gl_qs.filter(entry__entry_date__lte=date_to)

    by_gl_account = list(
        gl_qs.values('account__code', 'account__name')
        .annotate(
            total_cr=Sum('credit_amount'),
            total_dr=Sum('debit_amount'),
        )
        .order_by('account__code')
    )
    for row in by_gl_account:
        row['net'] = (row['total_cr'] or 0) - (row['total_dr'] or 0)

    gl_total = sum(r['net'] for r in by_gl_account)

    # Payment methods breakdown
    from .models import Payment
    pmts_qs = Payment.objects.filter(
        is_deleted=False,
        invoice__is_deleted=False,
    )
    if date_from:
        pmts_qs = pmts_qs.filter(payment_date__date__gte=date_from)
    if date_to:
        pmts_qs = pmts_qs.filter(payment_date__date__lte=date_to)

    by_method = list(
        pmts_qs.values('payment_method')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')
    )
    for row in by_method:
        row['label'] = dict(PaymentMethod.choices).get(row['payment_method'], row['payment_method'])

    return render(request, 'billing/revenue_analysis.html', {
        'by_category': by_category,
        'by_sub': by_sub,
        'by_gl_account': by_gl_account,
        'by_method': by_method,
        'grand_total': grand_total,
        'gl_total': gl_total,
        'date_from': date_from,
        'date_to': date_to,
    })


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
    fmt = request.GET.get('format')
    if fmt == 'pdf':
        return _render_pdf('billing/pdf/daily_summary_pdf.html', ctx, f'daily_summary_{report_date}.pdf')
    if fmt in ('csv', 'excel'):
        hdr = _hospital_header(f'Daily Summary — {report_date}')
        pm_labels = dict(PaymentMethod.choices)
        cols = ['Payment Method', 'Amount (FCFA)']
        rows = [cols] + [
            [pm_labels.get(row['payment_method'], row['payment_method']), f"{float(row['total']):.0f}"]
            for row in ctx.get('payments', []).values('payment_method').annotate(total=Sum('amount'))
        ]
        rows.append(['', ''])
        rows.append(['TOTAL REVENUE', f"{float(ctx.get('net_revenue', 0)):.0f}"])
        if fmt == 'csv':
            return _csv_response(f'daily_summary_{report_date}.csv', hdr, rows)
        return _excel_response(f'daily_summary_{report_date}.xlsx', hdr, rows, sheet_name='Daily Summary')
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
    fmt = request.GET.get('format')
    if fmt == 'pdf':
        return _render_pdf('billing/pdf/pl_pdf.html', ctx, f'pl_report_{month_str}.pdf')
    if fmt == 'csv':
        hdr = _hospital_header(f'Profit & Loss Statement — {ctx.get("month_label", month_str)}')
        cols = ['Category', 'Revenue (FCFA)', 'Expense (FCFA)']
        rev_label = dict(ServiceCategory.choices)
        rows = [cols]
        for row in ctx.get('rev_by_cat', []):
            rows.append([rev_label.get(row['category'], row['category']), f"{float(row['total']):.0f}", ''])
        rows.append(['', '', ''])
        exp_label = dict(ctx.get('exp_cat_labels', {}))
        for row in ctx.get('exp_by_cat', []):
            rows.append([exp_label.get(row['category'], row['category']), '', f"{float(row['total']):.0f}"])
        rows.append(['', '', ''])
        rows.append(['TOTAL REVENUE', f"{float(ctx.get('rev_total', 0)):.0f}", ''])
        rows.append(['TOTAL EXPENSES', '', f"{float(ctx.get('exp_total', 0)):.0f}"])
        rows.append(['GROSS PROFIT', f"{float(ctx.get('gross_profit', 0)):.0f}", ''])
        return _csv_response(f'pl_{month_str}.csv', hdr, rows)
    if fmt == 'excel':
        hdr = _hospital_header(f'Profit & Loss Statement — {ctx.get("month_label", month_str)}')
        rev_label = dict(ServiceCategory.choices)
        rows = [['Type', 'Category', 'Amount (FCFA)']]
        for row in ctx.get('rev_by_cat', []):
            rows.append(['Revenue', rev_label.get(row['category'], row['category']), float(row['total'])])
        for row in ctx.get('exp_by_cat', []):
            exp_label = dict(ExpenseCategory.choices)
            rows.append(['Expense', exp_label.get(row['category'], row['category']), float(row['total'])])
        rows.append(['', 'GROSS PROFIT', float(ctx.get('gross_profit', 0))])
        return _excel_response(f'pl_{month_str}.xlsx', hdr, rows, sheet_name='P&L')
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
    fmt = request.GET.get('format')
    if fmt == 'pdf':
        return _render_pdf('billing/pdf/top_services_pdf.html', ctx, f'top_services_{date_from_str}_{date_to_str}.pdf')
    if fmt in ('csv', 'excel'):
        hdr = _hospital_header(f'Top Services Revenue — {date_from_str} to {date_to_str}')
        cat_labels = dict(ServiceCategory.choices)
        cols = ['Service', 'Category', 'Revenue (FCFA)', 'Count']
        rows = [cols] + [
            [s['description'], cat_labels.get(s['category'], s['category']),
             f"{float(s['revenue']):.0f}", s['count']]
            for s in ctx.get('services', [])
        ]
        if fmt == 'csv':
            return _csv_response(f'top_services_{date_from_str}_{date_to_str}.csv', hdr, rows)
        return _excel_response(f'top_services_{date_from_str}_{date_to_str}.xlsx', hdr, rows, sheet_name='Top Services')
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

    lookup = dict(
        year=yr, month=mo,
        budget_type=request.POST.get('budget_type', BudgetType.REVENUE),
        category=request.POST.get('category', '').strip(),
        department=request.POST.get('department', '').strip(),
    )
    existing = Budget.objects.filter(is_deleted=False, **lookup).first()
    if existing and existing.budgeted_amount != amt:
        # Record amendment before overwriting
        BudgetAmendment.objects.create(
            budget=existing,
            previous_amount=existing.budgeted_amount,
            new_amount=amt,
            reason=request.POST.get('notes', '').strip() or 'Manual budget update',
            amended_by=request.user,
        )
    Budget.objects.update_or_create(
        **lookup,
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


@login_required
@require_POST
def budget_amend(request, budget_id):
    """Amend a budget line amount with mandatory reason — Finance Director / Senior Accountant."""
    from django.urls import reverse
    if not _can_approve_expense(request.user):
        messages.error(request, 'Access denied. Senior Accountant or above required.')
        return redirect('billing:budget_list')
    b = get_object_or_404(Budget, id=budget_id, is_deleted=False)
    try:
        new_amount = Decimal(request.POST.get('new_amount', '0') or '0')
    except InvalidOperation:
        messages.error(request, 'Invalid amount.')
        return redirect(f"{reverse('billing:budget_list')}?month={b.year}-{b.month:02d}")
    reason = request.POST.get('reason', '').strip()
    if not reason:
        messages.error(request, 'Amendment reason is required.')
        return redirect(f"{reverse('billing:budget_list')}?month={b.year}-{b.month:02d}")
    if new_amount == b.budgeted_amount:
        messages.info(request, 'No change in amount — amendment not recorded.')
        return redirect(f"{reverse('billing:budget_list')}?month={b.year}-{b.month:02d}")
    BudgetAmendment.objects.create(
        budget=b,
        previous_amount=b.budgeted_amount,
        new_amount=new_amount,
        reason=reason,
        amended_by=request.user,
    )
    b.budgeted_amount = new_amount
    b.save(update_fields=['budgeted_amount', 'updated_at'])
    messages.success(request, f'Budget amended: {b.budgeted_amount:,.0f} → {new_amount:,.0f} FCFA')
    return redirect(f"{reverse('billing:budget_list')}?month={b.year}-{b.month:02d}")


@login_required
def budget_amendment_history(request, budget_id):
    """Amendment history for a single budget line — rendered as HTMX partial or full page."""
    if not _can_view_pl(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:budget_list')
    b = get_object_or_404(Budget, id=budget_id, is_deleted=False)
    amendments = b.amendments.select_related('amended_by').order_by('-created_at')
    return render(request, 'billing/budget_amendment_history.html', {
        'budget': b,
        'amendments': amendments,
    })


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
    if not (_can_verify_shift(request.user) or _can_authorize_billing(request.user)
            or _can_view_financial_reports(request.user)):
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
    fmt = request.GET.get('format', '')
    if fmt == 'pdf':
        return _render_pdf('billing/pdf/ar_aging_pdf.html', ctx, f'ar_aging_{today}.pdf')
    if fmt in ('csv', 'excel'):
        hdr = _hospital_header(f'AR Aging Report — as of {today}')
        col_hdrs = ['Invoice #', 'Issue Date', 'Patient', 'Patient ID', 'Corporate', 'Total (FCFA)', 'Paid (FCFA)', 'Balance (FCFA)', 'Age (Days)', 'Bucket']
        rows = [col_hdrs]
        for bk in ['current', 'days31', 'days61', 'days90']:
            for row in buckets[bk]['rows']:
                inv = row['invoice']
                rows.append([
                    inv.invoice_number, inv.issue_date.strftime('%d/%m/%Y'),
                    row['patient'].full_name, row['patient'].patient_id,
                    inv.corporate_account.name if inv.corporate_account else '',
                    row['total'], row['paid'], row['balance'], row['age_days'],
                    buckets[bk]['label'],
                ])
        if fmt == 'csv':
            return _csv_response(f'ar_aging_{today}.csv', hdr, rows)
        return _excel_response(f'ar_aging_{today}.xlsx', hdr, rows, sheet_name='AR Aging')
    return render(request, 'billing/ar_aging.html', ctx)


# ═══════════════════════════════════════════════════════════════════════════════
# INSURANCE AMOUNT — AJAX endpoint to set insurance split on an invoice
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def invoice_set_insurance(request, invoice_id):
    """AJAX: Set the insurance coverage amount (and optionally the scheme) on an invoice."""
    from apps.hmo.models import InsuranceScheme
    invoice = get_object_or_404(Invoice, id=invoice_id, is_deleted=False)
    try:
        ins = Decimal(request.POST.get('insurance_amount', '0') or '0')
    except InvalidOperation:
        return JsonResponse({'success': False, 'error': 'Invalid amount.'}, status=400)
    if ins < 0:
        return JsonResponse({'success': False, 'error': 'Amount cannot be negative.'}, status=400)
    # Policy: manual insurance entry must cover at least 20% of the invoice total
    if ins > 0 and invoice.total > 0:
        min_insurance = (invoice.total * Decimal('0.20')).quantize(Decimal('1'), rounding='ROUND_CEILING')
        if ins < min_insurance:
            return JsonResponse({
                'success': False,
                'error': f'Insurance must cover at least 20% of the invoice total (minimum: {int(min_insurance):,} FCFA).'
            }, status=400)
    if ins > invoice.total:
        ins = invoice.total
    invoice.insurance_amount = ins
    # Optional: link to a specific insurance scheme
    scheme_id = request.POST.get('scheme_id', '').strip()
    save_fields = ['insurance_amount', 'updated_at']
    if scheme_id:
        try:
            scheme = InsuranceScheme.objects.get(pk=scheme_id, is_active=True)
            invoice.insurance_scheme = scheme
            save_fields.append('insurance_scheme')
        except InsuranceScheme.DoesNotExist:
            pass
    invoice.save(update_fields=save_fields)
    return JsonResponse({
        'success': True,
        'insurance_amount': int(ins),
        'patient_amount': int(invoice.patient_amount),
        'scheme_name': invoice.insurance_scheme.name if invoice.insurance_scheme else '',
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
    Access: Chief Cashier, Billing Officer, Finance Director, Accountant, Admin, Super Admin.
    """
    if not (_can_verify_shift(request.user) or _can_view_financial_reports(request.user)):
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


def _render_pdf(template_name, context, filename):
    """
    Render a template to PDF using the shared render_pdf engine.
    Automatically injects hospital letterhead, logo (base64), and hospital contact details.
    Falls back to browser-print HTML if WeasyPrint is unavailable.
    """
    from apps.reports.views import render_pdf as _shared_render_pdf
    context['pdf_filename'] = filename
    return _shared_render_pdf(template_name, context)


def _csv_response(filename, header_rows, data_rows):
    """
    Return a CSV HttpResponse with hospital header rows + data.
    header_rows: list of lists for preamble (hospital name, date, etc.)
    data_rows:   list of lists (first list is column headers)
    """
    import csv
    from django.http import HttpResponse
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    w = csv.writer(response)
    for row in header_rows:
        w.writerow(row)
    if header_rows:
        w.writerow([])   # blank separator
    for row in data_rows:
        w.writerow(row)
    return response


def _excel_response(filename, header_rows, data_rows, sheet_name='Report'):
    """
    Return an Excel HttpResponse with hospital header rows + styled data.
    Requires openpyxl.
    header_rows: list of lists for preamble
    data_rows:   list of lists (first list is column headers)
    """
    from django.http import HttpResponse, HttpResponseBadRequest
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        return HttpResponseBadRequest('openpyxl not installed')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]

    row_num = 1
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill('solid', fgColor='0891B2')   # EHR teal

    for prow in header_rows:
        ws.append(prow)
        ws.cell(row=row_num, column=1).font = Font(bold=True)
        row_num += 1

    if header_rows:
        ws.append([])
        row_num += 1

    for i, row in enumerate(data_rows):
        ws.append(row)
        if i == 0:
            # Style first data row as column header
            for col in range(1, len(row) + 1):
                cell = ws.cell(row=row_num, column=col)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal='center')
        row_num += 1

    # Auto-size columns
    for col in ws.columns:
        max_len = max((len(str(c.value or '')) for c in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


def _hospital_header(subtitle=''):
    """Return preamble rows for CSV/Excel exports (hospital identity)."""
    from apps.accounts.models import HospitalConfig
    from django.conf import settings
    try:
        cfg = HospitalConfig.get()
        name = cfg.hospital_name or getattr(settings, 'HOSPITAL_NAME', 'Hospital')
        address = cfg.hospital_address or getattr(settings, 'HOSPITAL_ADDRESS', '')
        phone = cfg.hospital_phone or getattr(settings, 'HOSPITAL_PHONE', '')
        email = cfg.hospital_email or getattr(settings, 'HOSPITAL_EMAIL', '')
        tax = cfg.hospital_tax_id or ''
    except Exception:
        name = getattr(settings, 'HOSPITAL_NAME', 'Hospital')
        address = getattr(settings, 'HOSPITAL_ADDRESS', '')
        phone = getattr(settings, 'HOSPITAL_PHONE', '')
        email = getattr(settings, 'HOSPITAL_EMAIL', '')
        tax = ''
    from django.utils import timezone as _tz
    rows = [
        [name],
        [address] if address else [],
        [f'Tel: {phone}  |  Email: {email}' if phone or email else ''],
        [f'Tax ID/NIU: {tax}'] if tax else [],
        [subtitle] if subtitle else [],
        [f'Generated: {_tz.localtime(_tz.now()).strftime("%d/%m/%Y %H:%M")}'],
    ]
    return [r for r in rows if r]


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
    OHADA Grand Livre Auxiliaire Client — Account 411 (Clients).

    Full subsidiary ledger per patient showing:
      Date | Opération (OP) | N° Pièce | Débit | Crédit | Solde

    Linked to OHADA Chart of Accounts:
      - Classe 4 — Comptes de Tiers (Third Parties)
      - Account 411000 — Clients (Patient Accounts Receivable)
      - Invoice issued = Dr 411 (patient owes)
      - Payment received = Cr 411 (patient paid)
      - Refund = Dr 411 (we return money)
    """
    _allowed = (
        UserRole.CHIEF_CASHIER, UserRole.ACCOUNTANT, UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR, UserRole.MEDICAL_DIRECTOR, UserRole.CEO,
        UserRole.ADMIN_DIRECTOR, UserRole.BILLING_OFFICER, UserRole.SUPER_ADMIN,
    )
    if not (request.user.is_superuser or request.user.is_super_admin or request.user.role in _allowed):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    from apps.patients.models import Patient
    from apps.billing.models import WalletTransaction
    from django.db.models import Sum as _Sum, Count as _Count, Max as _Max, Q as _Q
    from django.core.paginator import Paginator
    from decimal import Decimal

    patient = None
    ledger = []
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
            .prefetch_related('items')
            .order_by('created_at')
        )
        payments = list(
            Payment.objects.filter(
                invoice__patient=patient, invoice__is_deleted=False, is_deleted=False,
            ).select_related('invoice', 'received_by')
            .order_by('payment_date')
        )
        refunds = list(
            Refund.objects.filter(
                invoice__patient=patient, invoice__is_deleted=False, is_deleted=False,
            ).select_related('invoice', 'processed_by')
            .order_by('refund_date')
        )
        wallet_txns = []
        try:
            wallet_txns = list(
                WalletTransaction.objects.filter(wallet__patient=patient)
                .select_related('processed_by', 'invoice')
                .order_by('created_at')
            )
        except Exception:
            pass

        # ── Build unified ledger ────────────────────────────────────────────
        raw = []

        for inv in invoices:
            items_list = list(inv.items.all()[:4])
            items_desc = ', '.join(it.description for it in items_list[:3])
            if len(items_list) > 3:
                items_desc += f' +{inv.items.count() - 3}'
            raw.append({
                'date': inv.created_at,
                'op': f'Facture — {items_desc or "Services"}',
                'piece': inv.invoice_number,
                'debit': inv.total or Decimal('0'),
                'credit': Decimal('0'),
                'ref_type': 'invoice',
                'ref_id': str(inv.id),
                'by': getattr(inv.created_by, 'get_full_name', lambda: '—')() if inv.created_by else '—',
                'status': inv.get_status_display(),
            })

        for pay in payments:
            raw.append({
                'date': pay.payment_date,
                'op': f'Règlement — {pay.get_payment_method_display()}',
                'piece': pay.receipt_number or pay.reference or '—',
                'debit': Decimal('0'),
                'credit': pay.amount,
                'ref_type': 'payment',
                'ref_id': str(pay.invoice.id),
                'by': getattr(pay.received_by, 'get_full_name', lambda: '—')() if pay.received_by else '—',
                'status': pay.get_payment_method_display(),
            })

        for ref in refunds:
            raw.append({
                'date': ref.refund_date,
                'op': f'Remboursement — {ref.reason[:60]}',
                'piece': ref.reference or f'REF-{ref.pk}',
                'debit': ref.amount,
                'credit': Decimal('0'),
                'ref_type': 'refund',
                'ref_id': str(ref.invoice.id),
                'by': getattr(ref.processed_by, 'get_full_name', lambda: '—')() if ref.processed_by else '—',
                'status': 'Remboursement',
            })

        for wtx in wallet_txns:
            if wtx.transaction_type in ('DEPOSIT', 'REFUND'):
                raw.append({
                    'date': wtx.created_at,
                    'op': 'Dépôt portefeuille' if wtx.transaction_type == 'DEPOSIT' else 'Remb. portefeuille',
                    'piece': wtx.reference or f'W-{wtx.pk}',
                    'debit': Decimal('0'),
                    'credit': wtx.amount,
                    'ref_type': 'wallet',
                    'ref_id': '',
                    'by': getattr(wtx.processed_by, 'get_full_name', lambda: '—')() if wtx.processed_by else '—',
                    'status': wtx.get_transaction_type_display(),
                })
            elif wtx.transaction_type == 'DEDUCTION':
                raw.append({
                    'date': wtx.created_at,
                    'op': f'Déduction portefeuille' + (f' — {wtx.invoice.invoice_number}' if wtx.invoice else ''),
                    'piece': wtx.reference or f'W-{wtx.pk}',
                    'debit': Decimal('0'),
                    'credit': wtx.amount,
                    'ref_type': 'wallet',
                    'ref_id': str(wtx.invoice.id) if wtx.invoice else '',
                    'by': getattr(wtx.processed_by, 'get_full_name', lambda: '—')() if wtx.processed_by else '—',
                    'status': 'Wallet Pay',
                })
            elif wtx.transaction_type == 'WITHDRAWAL':
                raw.append({
                    'date': wtx.created_at,
                    'op': 'Retrait portefeuille',
                    'piece': wtx.reference or f'W-{wtx.pk}',
                    'debit': wtx.amount,
                    'credit': Decimal('0'),
                    'ref_type': 'wallet',
                    'ref_id': '',
                    'by': getattr(wtx.processed_by, 'get_full_name', lambda: '—')() if wtx.processed_by else '—',
                    'status': 'Retrait',
                })

        # Sort chronologically
        raw.sort(key=lambda e: e['date'])

        # Running balance (Débit − Crédit = what patient owes us)
        running = Decimal('0')
        for entry in raw:
            running += entry['debit'] - entry['credit']
            entry['balance'] = running

        ledger = raw

        total_debit = sum(e['debit'] for e in raw)
        total_credit = sum(e['credit'] for e in raw)
        summary = {
            'invoice_count': len(invoices),
            'payment_count': len(payments),
            'refund_count': len(refunds),
            'total_debit': total_debit,
            'total_credit': total_credit,
            'balance': total_debit - total_credit,
            'gl_account': '411000',
            'gl_class': 'Class 4 — Third-Party Accounts',
            'gl_label': 'Patient Accounts Receivable',
        }
    else:
        # ── List: all patients ───────────────────────────────────────────────
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
        'ledger': ledger,
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
    hdr = _hospital_header('Invoice List Export')
    col_hdrs = ['Invoice #', 'Date', 'Patient', 'Patient ID', 'Total (FCFA)', 'Paid (FCFA)', 'Balance (FCFA)', 'Status', 'Created By']
    rows = [col_hdrs]
    for inv in qs:
        rows.append([
            inv.invoice_number,
            inv.issue_date.strftime('%d/%m/%Y'),
            inv.patient.full_name,
            inv.patient.patient_id,
            float(inv.total),
            float(inv.amount_paid),
            float(inv.balance_due),
            inv.get_status_display(),
            inv.created_by.get_full_name() if inv.created_by else '',
        ])
    return _csv_response(f'invoices_{timezone.localdate()}.csv', hdr, rows)


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
    hdr = _hospital_header(f'Accounts Receivable Aging — as of {today}')
    col_hdrs = ['Invoice #', 'Issue Date', 'Patient', 'Patient ID', 'Corporate Account', 'Invoice Total (FCFA)', 'Paid (FCFA)', 'Balance Due (FCFA)', 'Age (Days)', 'Bucket']
    rows = [col_hdrs]
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
        rows.append([
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
    return _csv_response(f'ar_aging_{today}.csv', hdr, rows)


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
    hdr = _hospital_header('Expense List Export')
    col_hdrs = ['Date', 'Category', 'Description', 'Vendor', 'Amount (FCFA)', 'Payment Method', 'Status', 'Approved By', 'Submitted By']
    rows = [col_hdrs]
    for exp in qs:
        rows.append([
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
    return _csv_response(f'expenses_{timezone.localdate()}.csv', hdr, rows)


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
    hdr = _hospital_header('Cashier Shifts Export')
    col_hdrs = ['Date', 'Cashier', 'Opening Float (FCFA)', 'Total Collected (FCFA)', 'Closing Cash (FCFA)', 'Variance (FCFA)', 'Status', 'Verified By']
    rows = [col_hdrs]
    for s in qs:
        rows.append([
            s.shift_date.strftime('%d/%m/%Y'),
            s.cashier.get_full_name() or s.cashier.username,
            float(s.opening_cash),
            float(s.total_collected),
            float(s.closing_cash_declared) if s.closing_cash_declared else '',
            '',
            s.get_status_display(),
            s.verified_by.get_full_name() if s.verified_by else '',
        ])
    return _csv_response(f'cashier_shifts_{timezone.localdate()}.csv', hdr, rows)


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
    hdr = _hospital_header('Service Price Catalogue')
    col_hdrs = ['Code', 'Name', 'Category', 'Standard Price (FCFA)', 'NHIS Price (FCFA)', 'Insurance Price (FCFA)', 'Active']
    rows = [col_hdrs]
    for p in qs:
        rows.append([
            p.code or '',
            p.name,
            p.get_category_display(),
            float(p.price),
            float(p.nhis_price) if p.nhis_price else '',
            float(p.insurance_price) if p.insurance_price else '',
            'Yes' if p.is_active else 'No',
        ])
    return _csv_response(f'service_prices_{timezone.localdate()}.csv', hdr, rows)


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
    hdr = _hospital_header(f'Sales Journal — {date_from_str} to {date_to_str}')
    col_hdrs = ['Date', 'Receipt #', 'Invoice #', 'Patient', 'Patient ID', 'Amount (FCFA)', 'Payment Method', 'Reference', 'Cashier']
    rows = [col_hdrs]
    for p in pay_qs:
        rows.append([
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
    return _csv_response(f'sales_journal_{date_from_str}_{date_to_str}.csv', hdr, rows)


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
    hdr = _hospital_header('Void & Cancellation Register')
    col_hdrs = ['Date', 'Invoice #', 'Patient', 'Patient ID', 'Amount (FCFA)', 'Status', 'Reason Code', 'Reason', 'Authorised By', 'Created By']
    rows = [col_hdrs]
    for inv in qs:
        rows.append([
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
    return _csv_response(f'void_register_{timezone.localdate()}.csv', hdr, rows)


@login_required
def export_corporate_list(request):
    """CSV export of corporate accounts."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:corporate_list')
    _log_export(request, 'corporate_list')
    from .models import CorporateAccount
    accounts = CorporateAccount.objects.filter(is_deleted=False).order_by('name')
    hdr = _hospital_header('Corporate Accounts Export')
    col_hdrs = ['Account Name', 'Account Code', 'Contact', 'Phone', 'Email', 'Credit Limit (FCFA)', 'Discount %', 'Payment Terms (Days)', 'Active']
    rows = [col_hdrs]
    for acc in accounts:
        rows.append([
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
    return _csv_response(f'corporate_accounts_{timezone.localdate()}.csv', hdr, rows)


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
        UserRole.ADMIN_DIRECTOR, UserRole.BILLING_OFFICER, UserRole.SUPER_ADMIN,
    )
    if not (request.user.is_superuser or request.user.is_super_admin or request.user.role in _allowed):
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
        hdr = _hospital_header(f'Patient Financial Record — {patient.full_name} ({patient.patient_id})')
        col_hdrs = ['Invoice #', 'Date', 'Time', 'Issued By', 'Role', 'Total (FCFA)', 'Paid (FCFA)', 'Balance (FCFA)', 'Status']
        rows = [col_hdrs]
        for inv in invoices:
            issued_by = inv.created_by.get_full_name() or inv.created_by.username if inv.created_by else ''
            role = inv.created_by.get_role_display() if inv.created_by else ''
            rows.append([
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
        response = _csv_response(fname, hdr, rows)
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
        hdr = _hospital_header('Patient Financial Records — Summary')
        col_hdrs = ['Patient ID', 'Full Name', 'Phone', 'Registered', 'Invoice Count', 'Last Transaction']
        rows = [col_hdrs]
        for p in patients_qs:
            rows.append([
                p.patient_id,
                p.full_name,
                str(p.phone_number) if p.phone_number else '',
                p.registration_date.strftime('%d/%m/%Y') if p.registration_date else '',
                p.invoice_count or 0,
                p.last_invoice_at.strftime('%d/%m/%Y') if p.last_invoice_at else '',
            ])
        response = _csv_response(fname, hdr, rows)

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
        # Post GL: Dr Fixed Asset / Cr AP-Assets (OHADA §24x / §481)
        try:
            from .gl_service import post_asset_addition
            post_asset_addition(asset, user=request.user)
        except Exception:
            pass
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
from .models import GLAccount, AccountType, JournalEntry, JournalLine, JournalEntryStatus, CostCenter, JournalType


def _can_access_gl(user):
    return user.role in (
        UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT,
        UserRole.ACCOUNTANT, UserRole.CHIEF_CASHIER,
        UserRole.BILLING_OFFICER, UserRole.CEO,
        UserRole.ADMIN_DIRECTOR, UserRole.MEDICAL_DIRECTOR,
        UserRole.SUPER_ADMIN,
    ) or user.is_superuser


# ── Chart of Accounts ─────────────────────────────────────────────────────────

@login_required
def chart_of_accounts(request):
    if not _can_access_gl(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    from collections import defaultdict
    from django.db.models import Sum, Value, DecimalField, Q as _Q2
    from django.db.models.functions import Coalesce
    q = request.GET.get('q', '')
    acct_class = request.GET.get('class', '')
    # Single query: fetch all accounts with parent + annotated debit/credit totals
    accounts_qs = (
        GLAccount.objects
        .filter(is_deleted=False)
        .select_related('parent')
        .annotate(
            _total_debit=Coalesce(
                Sum('journal_lines__debit_amount',
                    filter=_Q2(journal_lines__entry__is_deleted=False)),
                Value(0, output_field=DecimalField())),
            _total_credit=Coalesce(
                Sum('journal_lines__credit_amount',
                    filter=_Q2(journal_lines__entry__is_deleted=False)),
                Value(0, output_field=DecimalField())),
        )
        .order_by('code')
    )
    if q:
        accounts_qs = accounts_qs.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(description__icontains=q))
    if acct_class:
        accounts_qs = accounts_qs.filter(code__startswith=acct_class)
    # Compute balance in Python (no extra DB hit per account)
    for a in accounts_qs:
        if a.account_type in (AccountType.ASSET, AccountType.EXPENSE):
            a.computed_balance = a._total_debit - a._total_credit
        else:
            a.computed_balance = a._total_credit - a._total_debit
    CLASS_NAMES = {
        '1': 'Class 1 — Long-Term Resources (Equity & Liabilities)',
        '2': 'Class 2 — Fixed Assets',
        '3': 'Class 3 — Inventories & Stocks',
        '4': 'Class 4 — Third Parties (AR/AP/Staff/Tax)',
        '5': 'Class 5 — Treasury (Cash & Bank)',
        '6': 'Class 6 — Expenses',
        '7': 'Class 7 — Revenue',
        '8': 'Class 8 — Exceptional Items',
        '9': 'Class 9 — Cost Accounting',
    }
    grouped = defaultdict(list)
    for a in accounts_qs:
        cls = a.code[0] if a.code else '?'
        grouped[cls].append(a)
    groups = [(cls, CLASS_NAMES.get(cls, f'Class {cls}'), grouped[cls])
              for cls in sorted(grouped.keys())]
    total_accounts = sum(len(v) for v in grouped.values())
    return render(request, 'billing/chart_of_accounts.html', {
        'groups': groups,
        'total_accounts': total_accounts,
        'q': q,
        'acct_class': acct_class,
        'class_choices': sorted(CLASS_NAMES.items()),
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


@login_required
@require_POST
def gl_account_delete(request, account_id):
    if not _can_access_gl(request.user):
        return HttpResponseForbidden()
    account = get_object_or_404(GLAccount, pk=account_id, is_deleted=False)
    # Block deletion if account has journal lines
    if JournalLine.objects.filter(account=account).exists():
        messages.error(request, f'Cannot delete {account.code} — it has journal entries. Deactivate it instead.')
        return redirect('billing:chart_of_accounts')
    account.is_deleted = True
    account.is_active = False
    account.save(update_fields=['is_deleted', 'is_active'])
    messages.success(request, f'Account {account.code} — {account.name} deleted.')
    return redirect('billing:chart_of_accounts')


# ── Journal Entries ───────────────────────────────────────────────────────────

@login_required
def journal_entry_list(request):
    if not _can_access_gl(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    qs = JournalEntry.objects.filter(is_deleted=False).select_related(
        'cost_center', 'operation', 'recorded_by', 'reviewed_by', 'posted_by'
    ).order_by('-entry_date', '-created_at')
    # Filters
    source = request.GET.get('source', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    q = request.GET.get('q', '')
    status = request.GET.get('status', '')
    op_code = request.GET.get('op_code', '')
    if source:
        qs = qs.filter(source_type=source)
    if date_from:
        qs = qs.filter(entry_date__gte=date_from)
    if date_to:
        qs = qs.filter(entry_date__lte=date_to)
    if q:
        qs = qs.filter(Q(entry_number__icontains=q) | Q(description__icontains=q) | Q(reference__icontains=q))
    if status:
        qs = qs.filter(status=status)
    if op_code:
        qs = qs.filter(operation__operation_code=op_code)
    # Pending counts for workflow badges
    draft_count = JournalEntry.objects.filter(is_deleted=False, status=JournalEntryStatus.DRAFT).count()
    reviewed_count = JournalEntry.objects.filter(is_deleted=False, status=JournalEntryStatus.REVIEWED).count()
    totals = JournalLine.objects.filter(entry__in=qs, entry__is_deleted=False).aggregate(
        grand_dr=Sum('debit_amount'), grand_cr=Sum('credit_amount')
    )
    from apps.billing.models import BillingOperationCC
    all_operations = BillingOperationCC.objects.filter(is_deleted=False).order_by('group', 'sort_order')
    return render(request, 'billing/journal_entry_list.html', {
        'entries': qs[:200],
        'total': qs.count(),
        'source': source,
        'date_from': date_from,
        'date_to': date_to,
        'q': q,
        'status': status,
        'op_code': op_code,
        'all_operations': all_operations,
        'status_choices': JournalEntryStatus.choices,
        'draft_count': draft_count,
        'reviewed_count': reviewed_count,
        'grand_dr': totals['grand_dr'] or 0,
        'grand_cr': totals['grand_cr'] or 0,
    })


@login_required
def journal_entry_detail(request, entry_id):
    if not _can_access_gl(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    entry = get_object_or_404(JournalEntry, pk=entry_id, is_deleted=False)
    # Determine what actions the current user can take
    can_review = (
        request.user.role in (UserRole.SENIOR_ACCOUNTANT, UserRole.SUPER_ADMIN)
        and entry.status == JournalEntryStatus.DRAFT
    )
    can_post = (
        request.user.role in (UserRole.FINANCE_DIRECTOR, UserRole.SUPER_ADMIN)
        and entry.status == JournalEntryStatus.REVIEWED
    )
    can_reject = (
        request.user.role in (UserRole.SENIOR_ACCOUNTANT, UserRole.FINANCE_DIRECTOR, UserRole.SUPER_ADMIN)
        and entry.status in (JournalEntryStatus.DRAFT, JournalEntryStatus.REVIEWED)
    )
    return render(request, 'billing/journal_entry_detail.html', {
        'entry': entry,
        'can_review': can_review,
        'can_post': can_post,
        'can_reject': can_reject,
    })


@login_required
def journal_entry_create(request):
    """
    Manual journal entry — 3-Tier Workflow:
      Accountant RECORDS (DRAFT) → Senior Accountant REVIEWS → Finance Director POSTS
    Accountant, Senior Accountant, Finance Director can all create entries.
    """
    if request.user.role not in (UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT,
                                  UserRole.ACCOUNTANT, UserRole.ADMIN, UserRole.SUPER_ADMIN):
        return HttpResponseForbidden()
    accounts = GLAccount.objects.filter(is_deleted=False, is_active=True, allow_manual_posting=True).order_by('code')
    cost_centers = CostCenter.objects.filter(is_deleted=False, is_active=True).order_by('code')
    if request.method == 'POST':
        entry_date = request.POST.get('entry_date')
        description = request.POST.get('description', '').strip()
        reference = request.POST.get('reference', '').strip()
        cost_center_id = request.POST.get('cost_center') or None
        operation_code = request.POST.get('operation') or None
        acct_ids = request.POST.getlist('account_id')
        debits = request.POST.getlist('debit')
        credits = request.POST.getlist('credit')
        descs = request.POST.getlist('line_desc')

        if not entry_date or not description:
            messages.error(request, 'Date and description are required.')
            return render(request, 'billing/journal_entry_form.html', {
                'accounts': accounts, 'cost_centers': cost_centers,
            })

        total_dr = sum(Decimal(d or '0') for d in debits)
        total_cr = sum(Decimal(c or '0') for c in credits)
        if abs(total_dr - total_cr) > Decimal('0.01'):
            messages.error(request, f'Entry is not balanced: Debits {total_dr:,.2f} ≠ Credits {total_cr:,.2f}')
            return render(request, 'billing/journal_entry_form.html', {
                'accounts': accounts, 'cost_centers': cost_centers,
            })

        journal_type_id = request.POST.get('journal_type') or None
        cc = CostCenter.objects.filter(pk=cost_center_id).first() if cost_center_id else None
        from apps.billing.models import BillingOperationCC as _BOpCC
        op_obj = _BOpCC.objects.filter(operation_code=operation_code, is_deleted=False).first() if operation_code else None
        jt_obj = JournalType.objects.filter(pk=journal_type_id, is_active=True).first() if journal_type_id else None
        entry = JournalEntry.objects.create(
            entry_date=entry_date,
            description=description,
            reference=reference,
            cost_center=cc,
            operation=op_obj,
            journal_type=jt_obj,
            source_type='manual',
            source_id='',
            is_posted=False,  # NOT posted yet — goes through approval
            status=JournalEntryStatus.DRAFT,
            recorded_by=request.user,
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
        messages.success(request, f'Journal entry {entry.entry_number} recorded as DRAFT — awaiting Senior Accountant review.')
        return redirect('billing:journal_entry_detail', entry_id=entry.pk)
    from apps.billing.models import BillingOperationCC
    operations = list(
        BillingOperationCC.objects.filter(is_deleted=False)
        .select_related('cost_center')
        .order_by('group', 'sort_order')
        .values('operation_code', 'operation_name', 'group', 'cost_center_id')
    )
    # Build operation→cost_center lookup for JS
    import json as _json
    op_cc_map = {
        op['operation_code']: str(op['cost_center_id']) if op['cost_center_id'] else ''
        for op in operations
    }
    journal_types = list(JournalType.objects.filter(is_active=True).order_by('code'))
    return render(request, 'billing/journal_entry_form.html', {
        'accounts': accounts, 'cost_centers': cost_centers,
        'operations': operations,
        'op_cc_map_json': _json.dumps(op_cc_map),
        'journal_types': journal_types,
    })


@login_required
@require_POST
def journal_ai_suggest(request):
    """
    AJAX endpoint: given a plain-language transaction description,
    use AI to suggest OHADA double-entry journal lines.
    Returns JSON: {lines: [{account_code, account_name, debit, credit, description}],
                   journal_type_code, summary, error}
    """
    import json as _json
    if request.user.role not in (UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT,
                                  UserRole.ACCOUNTANT, UserRole.ADMIN, UserRole.SUPER_ADMIN):
        return JsonResponse({'error': 'Accès refusé.'}, status=403)

    try:
        body = _json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Corps de requête invalide.'}, status=400)

    description = (body.get('description') or '').strip()
    if not description:
        return JsonResponse({'error': 'Description requise.'}, status=400)

    # Load active GL accounts for context
    accounts_qs = GLAccount.objects.filter(is_deleted=False, is_active=True, allow_manual_posting=True
                                           ).order_by('code').values('code', 'name')[:200]
    accounts_ctx = '\n'.join(f"{a['code']} — {a['name']}" for a in accounts_qs)

    system_prompt = (
        "Tu es un expert-comptable OHADA. Ton rôle est de générer les lignes d'écriture comptable "
        "en partie double à partir d'une description en langage naturel.\n\n"
        "Plan comptable OHADA disponible:\n"
        f"{accounts_ctx}\n\n"
        "Réponds UNIQUEMENT avec un objet JSON valide (pas de markdown, pas de texte autour):\n"
        "{\n"
        '  "journal_type_code": "BQ",  // BQ=Banque, CA=Caisse, AC=Achats, VE=Ventes, SA=Salaires, OD=Opérations Diverses\n'
        '  "summary": "Résumé court de l\'opération",\n'
        '  "lines": [\n'
        '    {"account_code": "521", "account_name": "Banques locales", "debit": 500000, "credit": 0, "description": "Paiement salaires"},\n'
        '    {"account_code": "661", "account_name": "Rémunérations directes", "debit": 0, "credit": 500000, "description": "Salaires juin"}\n'
        '  ]\n'
        "}\n\n"
        "Règles:\n"
        "- total débits = total crédits\n"
        "- Utilise uniquement les codes du plan comptable fourni\n"
        "- Montants en XAF (entiers)\n"
        "- Minimum 2 lignes"
    )

    try:
        from apps.ai_assistant.claude_client import _get_json_fn
        json_fn = _get_json_fn()
        result = json_fn(
            system=system_prompt,
            user=description,
            model=None,
        )
        if result.get('error'):
            return JsonResponse({'error': f"IA indisponible: {result['error']}"}, status=503)
        content = result.get('content', '')
        # Strip markdown code fences if present
        content = content.strip()
        if content.startswith('```'):
            content = content.split('```')[1]
            if content.startswith('json'):
                content = content[4:]
        data = _json.loads(content)
        lines = data.get('lines', [])
        if not lines:
            return JsonResponse({'error': 'Aucune ligne générée par l\'IA.'}, status=400)
        # Match account codes to PKs from our DB
        acct_map = {a.code: {'pk': str(a.pk), 'name': a.name}
                    for a in GLAccount.objects.filter(is_deleted=False, is_active=True, allow_manual_posting=True)}
        enriched = []
        for line in lines:
            code = str(line.get('account_code', '')).strip()
            acct = acct_map.get(code)
            enriched.append({
                'account_code': code,
                'account_name': line.get('account_name', '') if not acct else acct['name'],
                'account_pk': acct['pk'] if acct else '',
                'debit': int(line.get('debit') or 0),
                'credit': int(line.get('credit') or 0),
                'description': line.get('description', ''),
            })
        return JsonResponse({
            'lines': enriched,
            'journal_type_code': data.get('journal_type_code', ''),
            'summary': data.get('summary', description),
        })
    except _json.JSONDecodeError as e:
        return JsonResponse({'error': f"Réponse IA invalide: {e}"}, status=500)
    except Exception as e:
        logger.exception('journal_ai_suggest error')
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def journal_entry_review(request, entry_id):
    """Senior Accountant reviews a DRAFT journal entry → REVIEWED."""
    if request.user.role not in (UserRole.SENIOR_ACCOUNTANT, UserRole.SUPER_ADMIN):
        return HttpResponseForbidden('Only Senior Accountant can review journal entries.')
    entry = get_object_or_404(JournalEntry, pk=entry_id, status=JournalEntryStatus.DRAFT, is_deleted=False)
    entry.status = JournalEntryStatus.REVIEWED
    entry.reviewed_by = request.user
    entry.reviewed_at = timezone.now()
    entry.review_notes = request.POST.get('notes', '').strip()
    entry.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_notes', 'updated_at'])
    messages.success(request, f'{entry.entry_number} reviewed — awaiting Finance Director approval to post.')
    return redirect('billing:journal_entry_detail', entry_id=entry.pk)


@login_required
@require_POST
def journal_entry_post(request, entry_id):
    """Finance Director posts a REVIEWED journal entry → POSTED (affects GL balances)."""
    if request.user.role not in (UserRole.FINANCE_DIRECTOR, UserRole.SUPER_ADMIN):
        return HttpResponseForbidden('Only Finance Director can post journal entries.')
    entry = get_object_or_404(JournalEntry, pk=entry_id, status=JournalEntryStatus.REVIEWED, is_deleted=False)
    if not entry.is_balanced:
        messages.error(request, f'Cannot post — entry is not balanced (Dr {entry.total_debits:,.0f} ≠ Cr {entry.total_credits:,.0f}).')
        return redirect('billing:journal_entry_detail', entry_id=entry.pk)
    entry.status = JournalEntryStatus.POSTED
    entry.is_posted = True
    entry.posted_by = request.user
    entry.posted_at = timezone.now()
    entry.save(update_fields=['status', 'is_posted', 'posted_by', 'posted_at', 'updated_at'])
    messages.success(request, f'{entry.entry_number} posted to the General Ledger.')
    return redirect('billing:journal_entry_detail', entry_id=entry.pk)


@login_required
@require_POST
def journal_entry_reject(request, entry_id):
    """Senior Accountant or Finance Director rejects a journal entry."""
    if request.user.role not in (UserRole.SENIOR_ACCOUNTANT, UserRole.FINANCE_DIRECTOR, UserRole.SUPER_ADMIN):
        return HttpResponseForbidden('Only Senior Accountant or Finance Director can reject entries.')
    entry = get_object_or_404(JournalEntry, pk=entry_id, is_deleted=False)
    if entry.status not in (JournalEntryStatus.DRAFT, JournalEntryStatus.REVIEWED):
        messages.error(request, 'Only DRAFT or REVIEWED entries can be rejected.')
        return redirect('billing:journal_entry_detail', entry_id=entry.pk)
    entry.status = JournalEntryStatus.REJECTED
    entry.is_posted = False
    entry.rejection_reason = request.POST.get('reason', '').strip()
    entry.save(update_fields=['status', 'is_posted', 'rejection_reason', 'updated_at'])
    messages.warning(request, f'{entry.entry_number} rejected.')
    return redirect('billing:journal_entry_detail', entry_id=entry.pk)


# ── Cost Center CRUD ─────────────────────────────────────────────────────────

@login_required
def cost_center_list(request):
    if not _can_access_gl(request.user):
        return HttpResponseForbidden()
    centers = CostCenter.objects.filter(is_deleted=False).select_related('parent', 'manager').order_by('code')
    return render(request, 'billing/cost_center_list.html', {'centers': centers})


@login_required
def cost_center_create(request):
    if request.user.role not in (UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT, UserRole.SUPER_ADMIN):
        return HttpResponseForbidden()
    from apps.accounts.models import User as _User
    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        parent_id = request.POST.get('parent') or None
        manager_id = request.POST.get('manager') or None
        if not code or not name:
            messages.error(request, 'Code and Name are required.')
        elif CostCenter.objects.filter(code=code).exists():
            messages.error(request, f'Cost center {code} already exists.')
        else:
            parent = CostCenter.objects.filter(pk=parent_id).first() if parent_id else None
            manager = _User.objects.filter(pk=manager_id).first() if manager_id else None
            CostCenter.objects.create(
                code=code, name=name, description=description,
                parent=parent, manager=manager, created_by=request.user,
            )
            messages.success(request, f'Cost center {code} — {name} created.')
            return redirect('billing:cost_center_list')
    centers = CostCenter.objects.filter(is_deleted=False, is_active=True).order_by('code')
    staff = _User.objects.filter(is_active=True).order_by('first_name', 'last_name')
    return render(request, 'billing/cost_center_form.html', {
        'centers': centers, 'staff': staff, 'action': 'Create Cost Center',
    })


@login_required
def cost_center_edit(request, center_id):
    if request.user.role not in (UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT, UserRole.SUPER_ADMIN):
        return HttpResponseForbidden()
    from apps.accounts.models import User as _User
    cc = get_object_or_404(CostCenter, pk=center_id, is_deleted=False)
    if request.method == 'POST':
        cc.name = request.POST.get('name', cc.name).strip()
        cc.description = request.POST.get('description', '').strip()
        cc.is_active = request.POST.get('is_active') == 'on'
        manager_id = request.POST.get('manager') or None
        cc.manager = _User.objects.filter(pk=manager_id).first() if manager_id else None
        cc.save(update_fields=['name', 'description', 'is_active', 'manager', 'updated_at'])
        messages.success(request, f'Cost center {cc.code} updated.')
        return redirect('billing:cost_center_list')
    centers = CostCenter.objects.filter(is_deleted=False, is_active=True).exclude(pk=center_id).order_by('code')
    staff = _User.objects.filter(is_active=True).order_by('first_name', 'last_name')
    return render(request, 'billing/cost_center_form.html', {
        'center': cc, 'centers': centers, 'staff': staff, 'action': 'Edit Cost Center',
    })


# ── Journal Types ─────────────────────────────────────────────────────────────

@login_required
def journal_type_list(request):
    if not _can_access_gl(request.user):
        return HttpResponseForbidden()
    from .models import JournalType
    types = JournalType.objects.filter(is_deleted=False).order_by('code')
    return render(request, 'billing/journal_type_list.html', {'types': types})


@login_required
def journal_type_create(request):
    if request.user.role not in (UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT, UserRole.SUPER_ADMIN):
        return HttpResponseForbidden()
    from .models import JournalType
    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        name = request.POST.get('name', '').strip()
        if not code or not name:
            messages.error(request, 'Code and Name are required.')
        elif JournalType.objects.filter(code=code).exists():
            messages.error(request, f'Journal type {code} already exists.')
        else:
            JournalType.objects.create(
                code=code, name=name,
                description=request.POST.get('description', '').strip(),
                created_by=request.user,
            )
            messages.success(request, f'Journal type {code} — {name} created.')
            return redirect('billing:journal_type_list')
    return render(request, 'billing/journal_type_form.html', {'action': 'Create Journal Type'})


@login_required
def journal_type_edit(request, jt_id):
    if request.user.role not in (UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT, UserRole.SUPER_ADMIN):
        return HttpResponseForbidden()
    from .models import JournalType
    jt = get_object_or_404(JournalType, pk=jt_id, is_deleted=False)
    if request.method == 'POST':
        jt.name = request.POST.get('name', jt.name).strip()
        jt.description = request.POST.get('description', '').strip()
        jt.is_active = request.POST.get('is_active') == 'on'
        jt.save(update_fields=['name', 'description', 'is_active', 'updated_at'])
        messages.success(request, f'Journal type {jt.code} updated.')
        return redirect('billing:journal_type_list')
    return render(request, 'billing/journal_type_form.html', {'jtype': jt, 'action': 'Edit Journal Type'})


# ── Item Category GL Routing ──────────────────────────────────────────────────

@login_required
def item_category_gl_list(request):
    """
    Finance Director: view and configure automatic GL account routing per item category.
    Set once — all stock movements auto-post to the correct accounts forever.
    """
    if not _can_access_gl(request.user):
        return HttpResponseForbidden()
    from apps.inventory.models import ItemCategoryGL, ItemCategory
    mappings = {m.category: m for m in ItemCategoryGL.objects.select_related(
        'inventory_account', 'cogs_account', 'loss_account'
    ).all()}
    expense_accounts = GLAccount.objects.filter(
        is_active=True, is_deleted=False, code__startswith='6'
    ).order_by('code')
    stock_accounts = GLAccount.objects.filter(
        is_active=True, is_deleted=False, code__startswith='3'
    ).order_by('code')
    rows = []
    for value, label in ItemCategory.choices:
        rows.append({
            'category': value,
            'label': label,
            'mapping': mappings.get(value),
        })
    return render(request, 'billing/item_category_gl_list.html', {
        'rows': rows,
        'expense_accounts': expense_accounts,
        'stock_accounts': stock_accounts,
    })


@login_required
def item_category_gl_edit(request, category):
    """Edit the GL routing for a single item category."""
    if request.user.role not in (UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT, UserRole.SUPER_ADMIN):
        return HttpResponseForbidden()
    from apps.inventory.models import ItemCategoryGL, ItemCategory
    # Validate category value
    valid = dict(ItemCategory.choices)
    if category not in valid:
        from django.http import Http404
        raise Http404
    mapping, _ = ItemCategoryGL.objects.get_or_create(category=category)
    if request.method == 'POST':
        inv_id = request.POST.get('inventory_account')
        cogs_id = request.POST.get('cogs_account')
        loss_id = request.POST.get('loss_account')
        mapping.inventory_account = GLAccount.objects.filter(pk=inv_id).first() if inv_id else None
        mapping.cogs_account = GLAccount.objects.filter(pk=cogs_id).first() if cogs_id else None
        mapping.loss_account = GLAccount.objects.filter(pk=loss_id).first() if loss_id else None
        mapping.save()
        messages.success(request, f'GL routing updated for {valid[category]}.')
        return redirect('billing:item_category_gl_list')
    stock_accounts = GLAccount.objects.filter(
        is_active=True, is_deleted=False, code__startswith='3'
    ).order_by('code')
    expense_accounts = GLAccount.objects.filter(
        is_active=True, is_deleted=False, code__startswith='6'
    ).order_by('code')
    return render(request, 'billing/item_category_gl_edit.html', {
        'mapping': mapping,
        'category': category,
        'label': valid[category],
        'stock_accounts': stock_accounts,
        'expense_accounts': expense_accounts,
    })


# ── Operation → Cost Center Mapping (Configurable) ───────────────────────────

@login_required
def operation_cc_mapping(request):
    """
    Setup page where the Finance Director can assign each billing operation type
    to a cost center via a dropdown.  Changes are saved immediately to the
    BillingOperationCC table and are picked up by gl_service on the next posting.
    """
    if not _can_access_gl(request.user):
        return HttpResponseForbidden()

    from apps.billing.models import BillingOperationCC, CostCenter

    cost_centers = list(CostCenter.objects.filter(is_active=True, is_deleted=False).order_by('code'))
    operations   = list(BillingOperationCC.objects.filter(is_deleted=False).select_related('cost_center').order_by('group', 'sort_order'))

    saved = False
    if request.method == 'POST':
        for op in operations:
            field_name = f'cc_{op.pk}'
            val = request.POST.get(field_name, '')
            if val == '':
                new_cc = None
            else:
                try:
                    new_cc = CostCenter.objects.get(pk=val, is_active=True, is_deleted=False)
                except CostCenter.DoesNotExist:
                    new_cc = op.cost_center
            if op.cost_center != new_cc:
                op.cost_center = new_cc
                op.save(update_fields=['cost_center', 'updated_at'])
        saved = True
        operations = list(BillingOperationCC.objects.filter(is_deleted=False).select_related('cost_center').order_by('group', 'sort_order'))

    # Ordered group display config: (group_key, label, badge_class, description)
    GROUP_META = [
        ('CASH',      'Cash Desk Operations',   'bg-secondary',        '100-series — Opening/closing, float, deposits, withdrawals, inter-desk transfers, patient receipts'),
        ('REVENUE',   'Revenue Sales',          'bg-success',          '119-130 — Sales per store: OPD, Pharmacy, Optique, OT, Lab, IPD, Registration'),
        ('EXPENSE',   'Expense / Purchases',    'bg-danger',           '201-210 — Drug purchases, supplies, utilities, salaries, equipment, admin costs'),
        ('STOCK',     'Stock Movements',        'bg-warning text-dark','133-300 — Stock entries, exits, transfers per department/store'),
        ('INVENTORY', 'Inventory Count',        'bg-purple',           '150-155 — Physical inventory counts per store'),
        ('ASSET',     'Asset Operations',       'bg-dark',             '160-166 — Depreciation, asset disposal, asset transfer'),
        ('BANK',      'Bank Operations',        'bg-info text-dark',   'T001-T007 — Per-bank operations: SIB, CBM, LCIF, OPIC, ORBIS, LCIF-DR, GIZ Solar'),
        ('YEAR_END',  'Year-End & Special',     'bg-primary',          '170-999 — Proforma advance, misc operations, year-end closing, adjustments'),
    ]

    grouped_ops = {}
    for op in operations:
        grouped_ops.setdefault(op.group, []).append(op)

    groups = [
        (key, label, badge, desc, grouped_ops.get(key, []))
        for key, label, badge, desc in GROUP_META
    ]

    return render(request, 'billing/operation_cc_mapping.html', {
        'groups':       groups,
        'cost_centers': cost_centers,
        'saved':        saved,
        'total_ops':    len(operations),
    })


# ── Stock Operation Types ─────────────────────────────────────────────────────

@login_required
def stock_operation_type_list(request):
    if not _can_access_gl(request.user):
        return HttpResponseForbidden()
    from .models import StockOperationType
    types = StockOperationType.objects.filter(is_deleted=False).select_related(
        'debit_account', 'credit_account', 'billing_operation', 'billing_operation__cost_center'
    ).order_by('category', 'code')
    return render(request, 'billing/stock_operation_type_list.html', {'types': types})


@login_required
def stock_operation_type_create(request):
    if request.user.role not in (UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT, UserRole.SUPER_ADMIN):
        return HttpResponseForbidden()
    from .models import StockOperationType, StockOperationCategory
    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        name = request.POST.get('name', '').strip()
        category = request.POST.get('category', '')
        debit_id = request.POST.get('debit_account')
        credit_id = request.POST.get('credit_account')
        if not code or not name or not category or not debit_id or not credit_id:
            messages.error(request, 'All fields are required.')
        elif StockOperationType.objects.filter(code=code).exists():
            messages.error(request, f'Operation type {code} already exists.')
        else:
            billing_op_id = request.POST.get('billing_operation') or None
            StockOperationType.objects.create(
                code=code, name=name, category=category,
                debit_account_id=debit_id, credit_account_id=credit_id,
                description=request.POST.get('description', '').strip(),
                location_types=request.POST.get('location_types', '').strip(),
                billing_operation_id=billing_op_id,
                created_by=request.user,
            )
            messages.success(request, f'Stock operation type {code} — {name} created.')
            return redirect('billing:stock_operation_type_list')
    accounts = GLAccount.objects.filter(is_deleted=False, is_active=True).order_by('code')
    billing_operations = BillingOperationCC.objects.filter(is_deleted=False).select_related('cost_center').order_by('group', 'operation_code')
    return render(request, 'billing/stock_operation_type_form.html', {
        'action': 'Create Stock Operation Type',
        'categories': StockOperationCategory.choices,
        'accounts': accounts,
        'billing_operations': billing_operations,
    })


@login_required
def stock_operation_type_edit(request, sot_id):
    if request.user.role not in (UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT, UserRole.SUPER_ADMIN):
        return HttpResponseForbidden()
    from .models import StockOperationType, StockOperationCategory
    sot = get_object_or_404(StockOperationType, pk=sot_id, is_deleted=False)
    if request.method == 'POST':
        sot.name = request.POST.get('name', sot.name).strip()
        sot.category = request.POST.get('category', sot.category)
        sot.debit_account_id = request.POST.get('debit_account', sot.debit_account_id)
        sot.credit_account_id = request.POST.get('credit_account', sot.credit_account_id)
        sot.description = request.POST.get('description', '').strip()
        sot.location_types = request.POST.get('location_types', '').strip()
        billing_op_id = request.POST.get('billing_operation') or None
        sot.billing_operation_id = billing_op_id
        sot.is_active = request.POST.get('is_active') == 'on'
        sot.save(update_fields=['name', 'category', 'debit_account', 'credit_account',
                                'description', 'location_types', 'billing_operation',
                                'is_active', 'updated_at'])
        messages.success(request, f'Operation type {sot.code} updated.')
        return redirect('billing:stock_operation_type_list')
    accounts = GLAccount.objects.filter(is_deleted=False, is_active=True).order_by('code')
    billing_operations = BillingOperationCC.objects.filter(is_deleted=False).select_related('cost_center').order_by('group', 'operation_code')
    return render(request, 'billing/stock_operation_type_form.html', {
        'sot': sot, 'action': 'Edit Stock Operation Type',
        'categories': StockOperationCategory.choices,
        'accounts': accounts,
        'billing_operations': billing_operations,
    })


# ── Cost Center P&L Report ───────────────────────────────────────────────────

@login_required
def cost_center_pl_report(request):
    """Departmental P&L — revenue vs expenses per cost center, OHADA detail."""
    if not _can_access_gl(request.user):
        return HttpResponseForbidden()
    from django.db.models import Sum

    today = timezone.localdate()
    date_from = request.GET.get('date_from') or str(today)
    date_to   = request.GET.get('date_to')   or str(today)
    cc_filter = request.GET.get('cc_select', '')

    centers_qs = CostCenter.objects.filter(is_deleted=False, is_active=True).order_by('code')
    if cc_filter:
        centers_qs = centers_qs.filter(pk=cc_filter)

    # Sub-category labels for Class 6 and 7 (OHADA SYSCOHADA)
    _CL6_LABELS = {
        '60': 'Achats et variations de stocks',
        '61': 'Transports',
        '62': 'Services extérieurs A',
        '63': 'Services extérieurs B',
        '64': 'Impôts et taxes',
        '65': 'Autres charges',
        '66': 'Charges de personnel',
        '67': 'Frais financiers',
        '68': 'Dotations aux amortissements / provisions',
        '69': 'Charges HAO',
    }
    _CL7_LABELS = {
        '70': 'Ventes de marchandises',
        '71': 'Ventes de produits fabriqués',
        '72': 'Travaux, services vendus',
        '73': 'Produits accessoires',
        '74': 'Subventions d\'exploitation',
        '75': 'Autres produits',
        '76': 'Reprises de provisions',
        '77': 'Revenus financiers',
        '78': 'Transferts de charges',
        '79': 'Produits HAO',
    }

    D0 = Decimal('0')
    cc_sections = []
    grand_revenue = D0
    grand_expense = D0

    for cc in centers_qs:
        # Aggregate Class 7 lines at account level
        rev_lines = (
            JournalLine.objects
            .filter(
                entry__is_deleted=False, entry__is_posted=True,
                entry__cost_center=cc,
                entry__entry_date__gte=date_from,
                entry__entry_date__lte=date_to,
                account__code__startswith='7',
            )
            .values('account__code', 'account__name')
            .annotate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))
            .order_by('account__code')
        )
        # Aggregate Class 6 lines at account level
        exp_lines = (
            JournalLine.objects
            .filter(
                entry__is_deleted=False, entry__is_posted=True,
                entry__cost_center=cc,
                entry__entry_date__gte=date_from,
                entry__entry_date__lte=date_to,
                account__code__startswith='6',
            )
            .values('account__code', 'account__name')
            .annotate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))
            .order_by('account__code')
        )

        # Build revenue groups by 2-digit prefix
        rev_groups = {}
        for line in rev_lines:
            prefix = line['account__code'][:2]
            amt = (line['cr'] or D0) - (line['dr'] or D0)
            if amt == D0:
                continue
            if prefix not in rev_groups:
                rev_groups[prefix] = {'label': _CL7_LABELS.get(prefix, prefix), 'rows': [], 'total': D0}
            rev_groups[prefix]['rows'].append({
                'code': line['account__code'],
                'name': line['account__name'],
                'amount': amt,
            })
            rev_groups[prefix]['total'] += amt

        # Build expense groups by 2-digit prefix
        exp_groups = {}
        for line in exp_lines:
            prefix = line['account__code'][:2]
            amt = (line['dr'] or D0) - (line['cr'] or D0)
            if amt == D0:
                continue
            if prefix not in exp_groups:
                exp_groups[prefix] = {'label': _CL6_LABELS.get(prefix, prefix), 'rows': [], 'total': D0}
            exp_groups[prefix]['rows'].append({
                'code': line['account__code'],
                'name': line['account__name'],
                'amount': amt,
            })
            exp_groups[prefix]['total'] += amt

        total_rev = sum(g['total'] for g in rev_groups.values())
        total_exp = sum(g['total'] for g in exp_groups.values())
        net_result = total_rev - total_exp

        if not rev_groups and not exp_groups:
            continue  # skip CCs with zero activity

        cc_sections.append({
            'cc': cc,
            'rev_groups': sorted(rev_groups.items()),
            'exp_groups': sorted(exp_groups.items()),
            'total_rev': total_rev,
            'total_exp': total_exp,
            'net_result': net_result,
            'margin_pct': (net_result / total_rev * 100) if total_rev else D0,
        })
        grand_revenue += total_rev
        grand_expense += total_exp

    fmt = request.GET.get('format', '')
    if fmt in ('csv', 'excel'):
        hdr = _hospital_header(f'P&L by Cost Center — {date_from} to {date_to}')
        data_rows = [['Cost Center', 'Code', 'Revenue (XAF)', 'Expenses (XAF)', 'Net Result (XAF)', 'Margin %']]
        for sec in cc_sections:
            data_rows.append([sec['cc'].name, sec['cc'].code,
                              float(sec['total_rev']), float(sec['total_exp']),
                              float(sec['net_result']),
                              round(float(sec['margin_pct']), 2)])
        data_rows.append(['GRAND TOTAL', '', float(grand_revenue), float(grand_expense),
                          float(grand_revenue - grand_expense),
                          round(float((grand_revenue - grand_expense) / grand_revenue * 100) if grand_revenue else 0, 2)])
        if fmt == 'csv':
            return _csv_response(f'cost_center_pl_{date_from}_{date_to}.csv', hdr, data_rows)
        return _excel_response(f'cost_center_pl_{date_from}_{date_to}.xlsx', hdr, data_rows, sheet_name='P&L by Cost Center')
    return render(request, 'billing/cost_center_pl_report.html', {
        'cc_sections':    cc_sections,
        'date_from':      date_from,
        'date_to':        date_to,
        'grand_revenue':  grand_revenue,
        'grand_expense':  grand_expense,
        'grand_margin':   grand_revenue - grand_expense,
        'cost_centers':   CostCenter.objects.filter(is_deleted=False, is_active=True).order_by('code'),
        'cc_filter':      cc_filter,
        'today':          str(today),
    })


# ── General Ledger Report ─────────────────────────────────────────────────────

@login_required
def general_ledger(request):
    if not _can_access_gl(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    all_accounts = GLAccount.objects.filter(is_deleted=False, is_active=True).order_by('code')
    account_id = request.GET.get('account') or request.GET.get('account_id') or ''
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    ledger_data = []

    # Determine which accounts to show
    if account_id:
        target_accounts = all_accounts.filter(pk=account_id)
    else:
        # Show all accounts that have activity
        active_ids = JournalLine.objects.filter(
            entry__is_deleted=False,
        ).values_list('account_id', flat=True).distinct()
        target_accounts = all_accounts.filter(pk__in=active_ids)

    for acct in target_accounts:
        qs = JournalLine.objects.filter(
            account=acct,
            entry__is_deleted=False,
        ).select_related('entry').order_by('entry__entry_date', 'entry__created_at')
        if date_from:
            qs = qs.filter(entry__entry_date__gte=date_from)
        if date_to:
            qs = qs.filter(entry__entry_date__lte=date_to)

        is_debit_normal = acct.account_type in ('ASSET', 'EXPENSE')

        # Compute opening balance (lines before date_from)
        opening_balance = Decimal('0')
        if date_from:
            prior = JournalLine.objects.filter(
                account=acct, entry__is_deleted=False,
                entry__entry_date__lt=date_from,
            ).aggregate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))
            dr = prior['dr'] or Decimal('0')
            cr = prior['cr'] or Decimal('0')
            opening_balance = (dr - cr) if is_debit_normal else (cr - dr)

        running = opening_balance
        total_dr = Decimal('0')
        total_cr = Decimal('0')
        annotated_lines = []
        for line in qs:
            if is_debit_normal:
                running += line.debit_amount - line.credit_amount
            else:
                running += line.credit_amount - line.debit_amount
            line.running_balance = running
            annotated_lines.append(line)
            total_dr += line.debit_amount
            total_cr += line.credit_amount

        if annotated_lines or opening_balance:
            ledger_data.append({
                'account': acct,
                'opening_balance': opening_balance,
                'lines': annotated_lines,
                'total_debits': total_dr,
                'total_credits': total_cr,
                'closing_balance': running,
            })

    return render(request, 'billing/general_ledger.html', {
        'all_accounts': all_accounts,
        'ledger_data': ledger_data,
        'date_from': date_from,
        'date_to': date_to,
    })


# ── Trial Balance ─────────────────────────────────────────────────────────────

@login_required
def trial_balance(request):
    if not _can_access_gl(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    from django.db.models import Q as _Q

    today         = timezone.localdate()
    date_from     = request.GET.get('date_from') or str(today)
    date_to       = request.GET.get('date_to')   or str(today)
    balance_type  = request.GET.get('balance_type', 'general')   # 'general' | 'auxiliaire'
    classe_filter = request.GET.get('classe', '')                 # '' = all, '1'..'8'
    code_from     = request.GET.get('code_from', '').strip()
    code_to       = request.GET.get('code_to', '').strip()
    avec_mouvement = request.GET.get('avec_mouvement', '1')       # '1' = only with movement (default)
    cc_filter     = request.GET.get('cost_center', '')            # '' = all cost centers
    # New unified CC selector: cc_mode=1 + cc_select='' → all-CC breakdown; cc_select=<pk> → single CC
    cc_mode   = request.GET.get('cc_mode') == '1'
    cc_select = request.GET.get('cc_select', '')
    if cc_mode and cc_select:
        cc_filter = cc_select   # specific CC pk chosen from dropdown

    # ── OHADA SYCEBNL classes 1–8 ─────────────────────────────────────────────
    OHADA_CLASSES = [
        ('1', 'Class 1 — Permanent Capital'),
        ('2', 'Class 2 — Fixed Assets'),
        ('3', 'Class 3 — Inventory'),
        ('4', 'Class 4 — Third-Party Accounts'),
        ('5', 'Class 5 — Cash & Bank'),
        ('6', 'Class 6 — Expenses'),
        ('7', 'Class 7 — Revenue'),
        ('8', 'Class 8 — Special Accounts'),
    ]
    classes_to_show = [(c, lbl) for c, lbl in OHADA_CLASSES
                       if not classe_filter or c == classe_filter]

    # ── Two DB queries: raw per-leaf-account aggregates ───────────────────────
    open_base = JournalLine.objects.filter(
        entry__is_deleted=False, entry__entry_date__lt=date_from,
    )
    move_base = JournalLine.objects.filter(
        entry__is_deleted=False,
        entry__entry_date__gte=date_from,
        entry__entry_date__lte=date_to,
    )
    if cc_filter:
        open_base = open_base.filter(entry__cost_center_id=cc_filter)
        move_base = move_base.filter(entry__cost_center_id=cc_filter)

    open_bulk = open_base.values('account_id').annotate(
        total_dr=Sum('debit_amount'), total_cr=Sum('credit_amount')
    )
    open_map = {r['account_id']: (r['total_dr'] or Decimal('0'), r['total_cr'] or Decimal('0'))
                for r in open_bulk}

    move_bulk = move_base.values('account_id').annotate(
        total_dr=Sum('debit_amount'), total_cr=Sum('credit_amount')
    )
    move_map = {r['account_id']: (r['total_dr'] or Decimal('0'), r['total_cr'] or Decimal('0'))
                for r in move_bulk}

    # ── Load ALL active accounts once ─────────────────────────────────────────
    all_accounts = list(GLAccount.objects.filter(is_deleted=False, is_active=True).order_by('code'))
    acct_by_id   = {a.id: a for a in all_accounts}
    parent_of    = {a.id: a.parent_id for a in all_accounts}
    parent_code_of = {}
    parent_name_of = {}
    for a in all_accounts:
        if a.parent_id and a.parent_id in acct_by_id:
            p = acct_by_id[a.parent_id]
            parent_code_of[a.id] = p.code
            parent_name_of[a.id] = p.name
        else:
            parent_code_of[a.id] = ''
            parent_name_of[a.id] = ''

    D0 = Decimal('0')

    # ── Build direct-children map and compute depth for each account ──────────
    children_of = {}
    for a in all_accounts:
        if a.parent_id:
            children_of.setdefault(a.parent_id, []).append(a.id)

    depth_cache = {}
    def _depth(aid):
        if aid not in depth_cache:
            pid = parent_of.get(aid)
            depth_cache[aid] = (1 + _depth(pid)) if pid else 0
        return depth_cache[aid]
    for a in all_accounts:
        _depth(a.id)

    # ── Full recursive rollup: each account → total of ALL leaf descendants ───
    def _full_rollup(raw_map):
        """Propagate leaf journal-line totals up through every ancestor level."""
        totals = {a.id: raw_map.get(a.id, (D0, D0)) for a in all_accounts}
        # Process deepest accounts first so each account's accumulated total
        # reaches its parent before the parent propagates further up.
        for acct in sorted(all_accounts, key=lambda a: -depth_cache[a.id]):
            if acct.parent_id and acct.parent_id in acct_by_id:
                dr, cr = totals[acct.id]
                p_dr, p_cr = totals[acct.parent_id]
                totals[acct.parent_id] = (p_dr + dr, p_cr + cr)
        return totals

    # Account range filter helper
    def _in_range(acct):
        if code_from and acct.code < code_from:
            return False
        if code_to and acct.code > code_to:
            return False
        return True

    # ── CC Breakdown mode — one section per cost center ───────────────────────
    # Triggered by: legacy cc_breakdown=1  OR  cc_mode=1 with no specific CC selected
    cc_breakdown = (request.GET.get('cc_breakdown') == '1') or (cc_mode and not cc_select)
    cc_sections  = []
    sections     = []
    tot_open_dr  = D0; tot_open_cr = D0
    tot_move_dr  = D0; tot_move_cr = D0
    tot_clos_dr  = D0; tot_clos_cr = D0

    if cc_breakdown:
        from collections import defaultdict
        _CC_CLASS_LABELS = {
            '1': 'Class 1 — Permanent Capital',
            '2': 'Class 2 — Fixed Assets',
            '3': 'Class 3 — Inventory',
            '4': 'Class 4 — Third-Party Accounts',
            '5': 'Class 5 — Cash & Bank',
            '6': 'Class 6 — Expenses',
            '7': 'Class 7 — Revenue',
            '8': 'Class 8 — Special Accounts',
        }
        all_ccs_q = CostCenter.objects.filter(is_active=True, is_deleted=False).order_by('code')
        move_by_cc = (
            move_base
            .values('entry__cost_center_id', 'account_id')
            .annotate(total_dr=Sum('debit_amount'), total_cr=Sum('credit_amount'))
        )
        open_by_cc = (
            open_base
            .values('entry__cost_center_id', 'account_id')
            .annotate(total_dr=Sum('debit_amount'), total_cr=Sum('credit_amount'))
        )
        move_data = defaultdict(dict)
        for r in move_by_cc:
            if r['entry__cost_center_id']:
                move_data[r['entry__cost_center_id']][r['account_id']] = (
                    r['total_dr'] or D0, r['total_cr'] or D0)
        open_data = defaultdict(dict)
        for r in open_by_cc:
            if r['entry__cost_center_id']:
                open_data[r['entry__cost_center_id']][r['account_id']] = (
                    r['total_dr'] or D0, r['total_cr'] or D0)

        # Precompute parent→children map and standalone leaves (used for auxiliaire CC)
        _pc_map = {}   # parent_id → [child accts]
        _sl_accts = [] # standalone leaf accounts
        for _a in all_accounts:
            if _a.is_summary:
                continue
            if _a.parent_id and _a.parent_id in acct_by_id:
                _pc_map.setdefault(_a.parent_id, []).append(_a)
            else:
                _sl_accts.append(_a)

        # For General CC: precompute display ids + rollup helper
        _cc_display_ids = None
        if balance_type != 'auxiliaire':
            _cc_display_ids = {
                a.id for a in all_accounts
                if a.is_summary or (not a.parent_id and not a.is_summary)
            }
            def _cc_rollup(raw):
                totals = {a.id: raw.get(a.id, (D0, D0)) for a in all_accounts}
                for acct in sorted(all_accounts, key=lambda a: -depth_cache[a.id]):
                    if acct.parent_id and acct.parent_id in acct_by_id:
                        dr, cr = totals[acct.id]
                        p_dr, p_cr = totals[acct.parent_id]
                        totals[acct.parent_id] = (p_dr + dr, p_cr + cr)
                return totals

        for cc in all_ccs_q:
            cc_id = cc.pk
            mv_raw = move_data.get(cc_id, {})
            op_raw = open_data.get(cc_id, {})
            if not mv_raw and not op_raw:
                continue

            tt = {k: D0 for k in ('open_dr','open_cr','move_dr','move_cr','clos_dr','clos_cr')}
            class_groups = []

            if balance_type == 'auxiliaire':
                # ── Auxiliary CC: same parent→child→subtotal structure as Auxiliary Balance ──
                for cls_key, cls_label in sorted(_CC_CLASS_LABELS.items()):
                    rows = []
                    sub = {k: D0 for k in tt}
                    # 1. Summary/control accounts with their children
                    for par in sorted([a for a in all_accounts if a.is_summary and a.code.startswith(cls_key)], key=lambda a: a.code):
                        kids = sorted(_pc_map.get(par.id, []), key=lambda a: a.code)
                        p_o_dr = p_o_cr = p_m_dr = p_m_cr = D0
                        child_rows = []
                        for child in kids:
                            o_dr_r, o_cr_r = op_raw.get(child.id, (D0, D0))
                            m_dr, m_cr = mv_raw.get(child.id, (D0, D0))
                            if avec_mouvement == '1' and not (o_dr_r or o_cr_r or m_dr or m_cr):
                                continue
                            open_net = o_dr_r - o_cr_r
                            o_dr2 = max(D0, open_net); o_cr2 = max(D0, -open_net)
                            clos_net = open_net + m_dr - m_cr
                            c_dr = max(D0, clos_net); c_cr = max(D0, -clos_net)
                            p_o_dr += o_dr2; p_o_cr += o_cr2; p_m_dr += m_dr; p_m_cr += m_cr
                            child_rows.append({'row_type':'child', 'code':child.code, 'name':child.name, 'pk':child.pk, 'level':depth_cache.get(child.id,0), 'open_dr':o_dr2, 'open_cr':o_cr2, 'move_dr':m_dr, 'move_cr':m_cr, 'clos_dr':c_dr, 'clos_cr':c_cr})
                        if avec_mouvement == '1' and not child_rows:
                            continue
                        p_clos_net = (p_o_dr - p_o_cr) + p_m_dr - p_m_cr
                        p_c_dr = max(D0, p_clos_net); p_c_cr = max(D0, -p_clos_net)
                        rows.append({'row_type':'parent', 'code':par.code, 'name':par.name, 'pk':par.pk, 'level':depth_cache.get(par.id,0), 'open_dr':p_o_dr, 'open_cr':p_o_cr, 'move_dr':p_m_dr, 'move_cr':p_m_cr, 'clos_dr':p_c_dr, 'clos_cr':p_c_cr})
                        rows.extend(child_rows)
                        if len(child_rows) > 1:
                            rows.append({'row_type':'subtotal', 'code':'', 'name':f'= Sous-total {par.code} — {par.name}', 'pk':par.pk, 'level':0, 'open_dr':p_o_dr, 'open_cr':p_o_cr, 'move_dr':p_m_dr, 'move_cr':p_m_cr, 'clos_dr':p_c_dr, 'clos_cr':p_c_cr})
                        for k, v in [('open_dr',p_o_dr),('open_cr',p_o_cr),('move_dr',p_m_dr),('move_cr',p_m_cr),('clos_dr',p_c_dr),('clos_cr',p_c_cr)]:
                            sub[k] += v; tt[k] += v
                    # 2. Standalone leaves in this class
                    for acct in sorted([a for a in _sl_accts if a.code.startswith(cls_key)], key=lambda a: a.code):
                        o_dr_r, o_cr_r = op_raw.get(acct.id, (D0, D0))
                        m_dr, m_cr = mv_raw.get(acct.id, (D0, D0))
                        if avec_mouvement == '1' and not (o_dr_r or o_cr_r or m_dr or m_cr):
                            continue
                        open_net = o_dr_r - o_cr_r
                        o_dr2 = max(D0, open_net); o_cr2 = max(D0, -open_net)
                        clos_net = open_net + m_dr - m_cr
                        c_dr = max(D0, clos_net); c_cr = max(D0, -clos_net)
                        rows.append({'row_type':'standalone', 'code':acct.code, 'name':acct.name, 'pk':acct.pk, 'level':0, 'open_dr':o_dr2, 'open_cr':o_cr2, 'move_dr':m_dr, 'move_cr':m_cr, 'clos_dr':c_dr, 'clos_cr':c_cr})
                        for k, v in [('open_dr',o_dr2),('open_cr',o_cr2),('move_dr',m_dr),('move_cr',m_cr),('clos_dr',c_dr),('clos_cr',c_cr)]:
                            sub[k] += v; tt[k] += v
                    if rows:
                        class_groups.append({'cls': cls_key, 'label': cls_label, 'rows': rows, **sub})

            else:
                # ── General CC: roll up to summary accounts ──
                mv = _cc_rollup(mv_raw)
                op = _cc_rollup(op_raw)
                rows_by_cls = defaultdict(list)
                for acct_id in sorted(_cc_display_ids, key=lambda aid: acct_by_id[aid].code if aid in acct_by_id else '~'):
                    if acct_id not in acct_by_id:
                        continue
                    acct = acct_by_id[acct_id]
                    o_dr_r, o_cr_r = op.get(acct_id, (D0, D0))
                    m_dr, m_cr = mv.get(acct_id, (D0, D0))
                    if avec_mouvement == '1' and not (o_dr_r or o_cr_r or m_dr or m_cr):
                        continue
                    open_net = o_dr_r - o_cr_r
                    o_dr2 = max(D0, open_net); o_cr2 = max(D0, -open_net)
                    clos_net = open_net + m_dr - m_cr
                    c_dr = max(D0, clos_net); c_cr = max(D0, -clos_net)
                    cls_key = acct.code[0] if acct.code else '9'
                    rows_by_cls[cls_key].append({'row_type':'standalone', 'code':acct.code, 'name':acct.name, 'pk':acct.pk, 'level':depth_cache.get(acct.id,0), 'open_dr':o_dr2, 'open_cr':o_cr2, 'move_dr':m_dr, 'move_cr':m_cr, 'clos_dr':c_dr, 'clos_cr':c_cr})
                    tt['open_dr'] += o_dr2; tt['open_cr'] += o_cr2
                    tt['move_dr'] += m_dr;  tt['move_cr'] += m_cr
                    tt['clos_dr'] += c_dr;  tt['clos_cr'] += c_cr
                for cls_key in sorted(rows_by_cls.keys()):
                    cls_rows = rows_by_cls[cls_key]
                    sub = {k: D0 for k in tt}
                    for row in cls_rows:
                        for k in sub: sub[k] += row[k]
                    class_groups.append({'cls': cls_key, 'label': _CC_CLASS_LABELS.get(cls_key, f'Class {cls_key}'), 'rows': cls_rows, **sub})
            if class_groups:
                cc_sections.append({'cc': cc, 'class_groups': class_groups, **tt})
                tot_open_dr += tt['open_dr']; tot_open_cr += tt['open_cr']
                tot_move_dr += tt['move_dr']; tot_move_cr += tt['move_cr']
                tot_clos_dr += tt['clos_dr']; tot_clos_cr += tt['clos_cr']

    elif balance_type == 'general':
        gen_open = _full_rollup(open_map)
        gen_move = _full_rollup(move_map)

        # Show summary accounts + standalone leaves (leaves whose parent is None)
        display_accts = [
            a for a in all_accounts
            if (a.is_summary or (not a.parent_id and not a.is_summary)) and _in_range(a)
        ]
        display_ids = {a.id for a in display_accts}
        # Accounts that are parents of other displayed accounts — they are
        # higher-level rollups. Only their TERMINAL children count toward totals
        # to avoid double-counting across hierarchy levels.
        parent_of_displayed = {a.parent_id for a in display_accts if a.parent_id in display_ids}

        for cls, label in classes_to_show:
            rows = []
            sub = {k: D0 for k in ('open_dr','open_cr','move_dr','move_cr','clos_dr','clos_cr')}
            for acct in [a for a in display_accts if a.code.startswith(cls)]:
                o_raw_dr, o_raw_cr = gen_open.get(acct.id, (D0, D0))
                m_dr,     m_cr     = gen_move.get(acct.id, (D0, D0))
                if avec_mouvement == '1' and not (o_raw_dr or o_raw_cr or m_dr or m_cr):
                    continue
                open_net = o_raw_dr - o_raw_cr
                o_dr = max(D0, open_net);  o_cr = max(D0, -open_net)
                clos_net = open_net + m_dr - m_cr
                c_dr = max(D0, clos_net);  c_cr = max(D0, -clos_net)
                rows.append({
                    'code': acct.code, 'name': acct.name, 'pk': acct.pk,
                    'is_summary': acct.is_summary,
                    'level': depth_cache.get(acct.id, 0),
                    'open_dr': o_dr, 'open_cr': o_cr,
                    'move_dr': m_dr, 'move_cr': m_cr,
                    'clos_dr': c_dr, 'clos_cr': c_cr,
                    'parent_code': parent_code_of.get(acct.id, ''),
                    'parent_name': parent_name_of.get(acct.id, ''),
                })
                # Only terminal displayed accounts (no displayed children) count
                # toward section and grand totals — avoids double-counting.
                if acct.id not in parent_of_displayed:
                    for k, v in [('open_dr',o_dr),('open_cr',o_cr),('move_dr',m_dr),
                                  ('move_cr',m_cr),('clos_dr',c_dr),('clos_cr',c_cr)]:
                        sub[k] += v
            if rows:
                sections.append({'label': label, 'rows': rows, **sub})
            tot_open_dr += sub['open_dr']; tot_open_cr += sub['open_cr']
            tot_move_dr += sub['move_dr']; tot_move_cr += sub['move_cr']
            tot_clos_dr += sub['clos_dr']; tot_clos_cr += sub['clos_cr']

    elif balance_type != 'general':  # auxiliaire — control account header + indented children + subtotal
        # Map each summary to its DIRECT leaf children only.
        # Multi-level summaries (705200 → 7052000 → 7052001) are handled by
        # iterating ALL summaries; 705200 will have no direct leaf children
        # (they're all summaries themselves) so it's naturally skipped when
        # avec_mouvement='1'. Terminal summaries (7052000) correctly list their
        # tier leaves and are the only ones that contribute to section totals.
        parent_children = {}
        standalone_leaves = []
        for acct in all_accounts:
            if acct.is_summary:
                continue
            if acct.parent_id and acct.parent_id in acct_by_id:
                parent_children.setdefault(acct.parent_id, []).append(acct)
            else:
                standalone_leaves.append(acct)

        for cls, label in classes_to_show:
            rows = []
            sub = {k: D0 for k in ('open_dr','open_cr','move_dr','move_cr','clos_dr','clos_cr')}

            # ── 1. Summary accounts as control-account groups ─────────────────
            summary_in_cls = sorted(
                [a for a in all_accounts if a.is_summary and a.code.startswith(cls) and _in_range(a)],
                key=lambda a: a.code,
            )
            for parent_acct in summary_in_cls:
                children = sorted(
                    [a for a in parent_children.get(parent_acct.id, []) if _in_range(a)],
                    key=lambda a: a.code,
                )
                p_o_dr = p_o_cr = p_m_dr = p_m_cr = D0
                child_rows = []
                for child in children:
                    o_raw_dr, o_raw_cr = open_map.get(child.id, (D0, D0))
                    m_dr,     m_cr     = move_map.get(child.id, (D0, D0))
                    if avec_mouvement == '1' and not (o_raw_dr or o_raw_cr or m_dr or m_cr):
                        continue
                    open_net = o_raw_dr - o_raw_cr
                    o_dr = max(D0, open_net);  o_cr = max(D0, -open_net)
                    clos_net = open_net + m_dr - m_cr
                    c_dr = max(D0, clos_net);  c_cr = max(D0, -clos_net)
                    p_o_dr += o_dr;  p_o_cr += o_cr
                    p_m_dr += m_dr;  p_m_cr += m_cr
                    child_rows.append({
                        'row_type': 'child',
                        'code': child.code, 'name': child.name, 'pk': child.pk,
                        'level': depth_cache.get(child.id, 0),
                        'open_dr': o_dr, 'open_cr': o_cr,
                        'move_dr': m_dr, 'move_cr': m_cr,
                        'clos_dr': c_dr, 'clos_cr': c_cr,
                    })

                if avec_mouvement == '1' and not child_rows and not (
                    open_map.get(parent_acct.id) or move_map.get(parent_acct.id)
                ):
                    continue

                p_clos_net = (p_o_dr - p_o_cr) + p_m_dr - p_m_cr
                p_c_dr = max(D0, p_clos_net);  p_c_cr = max(D0, -p_clos_net)

                rows.append({
                    'row_type': 'parent',
                    'code': parent_acct.code, 'name': parent_acct.name, 'pk': parent_acct.pk,
                    'level': depth_cache.get(parent_acct.id, 0),
                    'open_dr': p_o_dr, 'open_cr': p_o_cr,
                    'move_dr': p_m_dr, 'move_cr': p_m_cr,
                    'clos_dr': p_c_dr, 'clos_cr': p_c_cr,
                })
                rows.extend(child_rows)

                if len(child_rows) > 1:
                    rows.append({
                        'row_type': 'subtotal',
                        'code': '', 'name': f'= Sous-total {parent_acct.code} — {parent_acct.name}',
                        'pk': parent_acct.pk,
                        'level': 0,
                        'open_dr': p_o_dr, 'open_cr': p_o_cr,
                        'move_dr': p_m_dr, 'move_cr': p_m_cr,
                        'clos_dr': p_c_dr, 'clos_cr': p_c_cr,
                    })

                for k, v in [('open_dr', p_o_dr), ('open_cr', p_o_cr),
                              ('move_dr', p_m_dr), ('move_cr', p_m_cr),
                              ('clos_dr', p_c_dr), ('clos_cr', p_c_cr)]:
                    sub[k] += v

            # ── 2. Standalone leaf accounts (no parent) in this class ─────────
            for acct in sorted([a for a in standalone_leaves
                                 if a.code.startswith(cls) and _in_range(a)],
                                key=lambda a: a.code):
                o_raw_dr, o_raw_cr = open_map.get(acct.id, (D0, D0))
                m_dr,     m_cr     = move_map.get(acct.id, (D0, D0))
                if avec_mouvement == '1' and not (o_raw_dr or o_raw_cr or m_dr or m_cr):
                    continue
                open_net = o_raw_dr - o_raw_cr
                o_dr = max(D0, open_net);  o_cr = max(D0, -open_net)
                clos_net = open_net + m_dr - m_cr
                c_dr = max(D0, clos_net);  c_cr = max(D0, -clos_net)
                rows.append({
                    'row_type': 'standalone',
                    'code': acct.code, 'name': acct.name, 'pk': acct.pk,
                    'level': 0,
                    'open_dr': o_dr, 'open_cr': o_cr,
                    'move_dr': m_dr, 'move_cr': m_cr,
                    'clos_dr': c_dr, 'clos_cr': c_cr,
                })
                for k, v in [('open_dr', o_dr), ('open_cr', o_cr),
                              ('move_dr', m_dr), ('move_cr', m_cr),
                              ('clos_dr', c_dr), ('clos_cr', c_cr)]:
                    sub[k] += v

            if rows:
                sections.append({'label': label, 'rows': rows, **sub})
            tot_open_dr += sub['open_dr']; tot_open_cr += sub['open_cr']
            tot_move_dr += sub['move_dr']; tot_move_cr += sub['move_cr']
            tot_clos_dr += sub['clos_dr']; tot_clos_cr += sub['clos_cr']

    move_diff = tot_move_dr - tot_move_cr
    clos_diff = tot_clos_dr - tot_clos_cr

    export_fmt = request.GET.get('export', '').lower()
    # Resolve cost center early (needed for export titles)
    _exp_cc = CostCenter.objects.filter(pk=cc_filter).first() if cc_filter else None
    _cc_label = f' — {_exp_cc.name} ({_exp_cc.code})' if _exp_cc else ' — All Departments'
    _cc_slug  = f'_{_exp_cc.code}' if _exp_cc else ''

    if export_fmt == 'csv':
        import csv
        from django.http import HttpResponse
        _cc_mode_slug = '_cc' if cc_breakdown else ''
        resp = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        resp['Content-Disposition'] = (
            f'attachment; filename="balance{_cc_mode_slug}_{balance_type}{_cc_slug}_{date_from}_{date_to}.csv"'
        )
        w = csv.writer(resp)
        bal_lbl = 'GENERAL BALANCE' if balance_type == 'general' else 'AUXILIARY BALANCE'
        cc_mode_lbl = ' (COST CENTER BREAKDOWN)' if cc_breakdown else ''
        # Hospital header
        for hrow in _hospital_header(f'{bal_lbl}{cc_mode_lbl}{_cc_label}  |  Period: {date_from} to {date_to}'):
            w.writerow(hrow)
        w.writerow([])
        w.writerow(['Code', 'Account Name',
                    'Opening Debit', 'Opening Credit',
                    'Movement Debit', 'Movement Credit',
                    'Closing Debit', 'Closing Credit'])
        if cc_breakdown:
            for cc_sec in cc_sections:
                cc_obj = cc_sec['cc']
                w.writerow([f'=== COST CENTER: {cc_obj.code} — {cc_obj.name} ===',
                            '', '', '', '', '', '', ''])
                for grp in cc_sec['class_groups']:
                    w.writerow([f'Class {grp["cls"]} — {grp["label"]}',
                                '', '', '', '', '', '', ''])
                    for row in grp['rows']:
                        indent = '    ' if row['row_type'] == 'child' else ''
                        row_prefix = '' if row['row_type'] not in ('parent', 'subtotal') else ''
                        w.writerow([indent + row['code'], row['name'],
                                    row['open_dr'], row['open_cr'],
                                    row['move_dr'], row['move_cr'],
                                    row['clos_dr'], row['clos_cr']])
                    w.writerow(['Subtotal — Class ' + grp['cls'], '',
                                grp['open_dr'], grp['open_cr'],
                                grp['move_dr'], grp['move_cr'],
                                grp['clos_dr'], grp['clos_cr']])
                w.writerow([f'TOTAL — {cc_obj.code} {cc_obj.name}', '',
                            cc_sec['open_dr'], cc_sec['open_cr'],
                            cc_sec['move_dr'], cc_sec['move_cr'],
                            cc_sec['clos_dr'], cc_sec['clos_cr']])
                w.writerow([])  # blank separator between cost centers
        else:
            for sec in sections:
                w.writerow([sec['label'], '', '', '', '', '', '', ''])
                for row in sec['rows']:
                    w.writerow([row['code'], row['name'],
                                row['open_dr'], row['open_cr'],
                                row['move_dr'], row['move_cr'],
                                row['clos_dr'], row['clos_cr']])
                w.writerow(['Subtotal — ' + sec['label'], '',
                            sec['open_dr'], sec['open_cr'],
                            sec['move_dr'], sec['move_cr'],
                            sec['clos_dr'], sec['clos_cr']])
        w.writerow(['GRAND TOTALS', '',
                    tot_open_dr, tot_open_cr,
                    tot_move_dr, tot_move_cr,
                    tot_clos_dr, tot_clos_cr])
        return resp

    if export_fmt == 'xlsx':
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter
            from django.http import HttpResponse as HR
        except ImportError:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest('openpyxl not installed')

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Balance des Comptes'

        # Styles
        hdr_fill  = PatternFill('solid', fgColor='1E3A5F')
        hdr_font  = Font(bold=True, color='FFFFFF', size=10)
        sec_fill  = PatternFill('solid', fgColor='D9E1F2')
        sec_font  = Font(bold=True, size=9)
        sub_fill  = PatternFill('solid', fgColor='F2F2F2')
        tot_fill  = PatternFill('solid', fgColor='1E3A5F')
        tot_font  = Font(bold=True, color='FFFFFF', size=10)
        num_fmt   = '#,##0'
        thin      = Side(style='thin')
        border    = Border(left=thin, right=thin, top=thin, bottom=thin)

        # Title rows — row 1: report name, row 2: department scope
        ws.merge_cells('A1:H1')
        lbl = 'GENERAL BALANCE' if balance_type == 'general' else 'AUXILIARY BALANCE'
        cls_lbl = f' · Classe {classe_filter}' if classe_filter else ''
        cc_mode_lbl_x = ' — COST CENTER BREAKDOWN' if cc_breakdown else ''
        ws['A1'] = f'{lbl}{cc_mode_lbl_x}{cls_lbl} — Du {date_from} au {date_to}'
        ws['A1'].font = Font(bold=True, size=12)
        ws['A1'].alignment = Alignment(horizontal='center')
        ws.merge_cells('A2:H2')
        cc_scope = f'Department: {_exp_cc.name} ({_exp_cc.code})' if _exp_cc else 'Scope: All Departments — Entire Hospital'
        ws['A2'] = cc_scope
        ws['A2'].font = Font(bold=True, size=10, color='92400E' if _exp_cc else '374151')
        ws['A2'].fill = PatternFill('solid', fgColor='FEF3C7' if _exp_cc else 'F3F4F6')
        ws['A2'].alignment = Alignment(horizontal='center')

        # Group header row 3
        headers_top = ['', '', 'Opening Balances', '', 'Period Movements', '', 'Closing Balances', '']
        for col, val in enumerate(headers_top, 1):
            c = ws.cell(row=3, column=col, value=val)
            c.fill = hdr_fill; c.font = hdr_font
            c.alignment = Alignment(horizontal='center')
        ws.merge_cells('C3:D3'); ws.merge_cells('E3:F3'); ws.merge_cells('G3:H3')

        # Sub-header row 4
        headers_sub = ['Code', 'Account Name', 'Debit', 'Credit', 'Debit', 'Credit', 'Debit', 'Credit']
        for col, val in enumerate(headers_sub, 1):
            c = ws.cell(row=4, column=col, value=val)
            c.fill = hdr_fill; c.font = hdr_font
            c.alignment = Alignment(horizontal='right' if col > 2 else 'left')

        cc_hdr_fill = PatternFill('solid', fgColor='1E3A5F')   # dark blue — CC banner
        cc_tot_fill = PatternFill('solid', fgColor='E8EEF7')   # light blue — CC total
        cc_tot_font = Font(bold=True, size=9, color='1E3A5F')
        cls_fill    = PatternFill('solid', fgColor='D9E1F2')   # same as sec_fill
        par_fill    = PatternFill('solid', fgColor='EEF2FA')   # light blue-tint — parent rows
        sub_row_fill= PatternFill('solid', fgColor='F5F7FB')   # subtotal rows inside CC

        row_num = 5
        if cc_breakdown:
            for cc_sec in cc_sections:
                cc_obj = cc_sec['cc']
                # CC banner row
                ws.merge_cells(f'A{row_num}:H{row_num}')
                c = ws.cell(row=row_num, column=1,
                            value=f'COST CENTER: {cc_obj.code} — {cc_obj.name}')
                c.fill = cc_hdr_fill
                c.font = Font(bold=True, color='FFFFFF', size=10)
                c.alignment = Alignment(horizontal='left', indent=1)
                row_num += 1
                for grp in cc_sec['class_groups']:
                    # Class sub-header
                    ws.merge_cells(f'A{row_num}:H{row_num}')
                    c = ws.cell(row=row_num, column=1,
                                value=f'Class {grp["cls"]} — {grp["label"]}'.upper())
                    c.fill = cls_fill; c.font = sec_font
                    row_num += 1
                    for row in grp['rows']:
                        rtype = row.get('row_type', 'standalone')
                        if rtype == 'parent':
                            row_fill = par_fill
                            row_font = Font(bold=True, size=9, color='1E3A5F')
                            indent = 1
                        elif rtype == 'subtotal':
                            row_fill = sub_row_fill
                            row_font = Font(bold=False, italic=True, size=9)
                            indent = 1
                        elif rtype == 'child':
                            row_fill = None
                            row_font = Font(size=9)
                            indent = 3
                        else:  # standalone
                            row_fill = None
                            row_font = Font(size=9)
                            indent = 1
                        vals = [row['code'], row['name'],
                                float(row['open_dr']), float(row['open_cr']),
                                float(row['move_dr']), float(row['move_cr']),
                                float(row['clos_dr']), float(row['clos_cr'])]
                        for col, val in enumerate(vals, 1):
                            c = ws.cell(row=row_num, column=col, value=val)
                            c.border = border
                            c.font = row_font
                            if row_fill:
                                c.fill = row_fill
                            if col == 2:
                                c.alignment = Alignment(horizontal='left', indent=indent)
                            elif col > 2:
                                c.number_format = num_fmt
                                c.alignment = Alignment(horizontal='right')
                        row_num += 1
                    # Class subtotal within CC
                    cls_sub = [f'Subtotal — Class {grp["cls"]}', '',
                               float(grp['open_dr']), float(grp['open_cr']),
                               float(grp['move_dr']), float(grp['move_cr']),
                               float(grp['clos_dr']), float(grp['clos_cr'])]
                    for col, val in enumerate(cls_sub, 1):
                        c = ws.cell(row=row_num, column=col, value=val)
                        c.fill = sub_fill; c.font = Font(bold=True, size=9)
                        if col > 2:
                            c.number_format = num_fmt
                            c.alignment = Alignment(horizontal='right')
                    row_num += 1
                # CC total row
                cc_tot = [f'TOTAL — {cc_obj.code} {cc_obj.name}', '',
                          float(cc_sec['open_dr']), float(cc_sec['open_cr']),
                          float(cc_sec['move_dr']), float(cc_sec['move_cr']),
                          float(cc_sec['clos_dr']), float(cc_sec['clos_cr'])]
                for col, val in enumerate(cc_tot, 1):
                    c = ws.cell(row=row_num, column=col, value=val)
                    c.fill = cc_tot_fill; c.font = cc_tot_font
                    if col > 2:
                        c.number_format = num_fmt
                        c.alignment = Alignment(horizontal='right')
                row_num += 1
                row_num += 1  # blank spacer row between cost centers
        else:
            for sec in sections:
                # Section header
                ws.merge_cells(f'A{row_num}:H{row_num}')
                c = ws.cell(row=row_num, column=1, value=sec['label'].upper())
                c.fill = sec_fill; c.font = sec_font
                row_num += 1
                # Account rows
                for row in sec['rows']:
                    vals = [row['code'], row['name'],
                            float(row['open_dr']), float(row['open_cr']),
                            float(row['move_dr']), float(row['move_cr']),
                            float(row['clos_dr']), float(row['clos_cr'])]
                    for col, val in enumerate(vals, 1):
                        c = ws.cell(row=row_num, column=col, value=val)
                        c.border = border
                        if col > 2:
                            c.number_format = num_fmt
                            c.alignment = Alignment(horizontal='right')
                    row_num += 1
                # Section subtotal
                sub_vals = ['Subtotal — ' + sec['label'], '',
                            float(sec['open_dr']), float(sec['open_cr']),
                            float(sec['move_dr']), float(sec['move_cr']),
                            float(sec['clos_dr']), float(sec['clos_cr'])]
                for col, val in enumerate(sub_vals, 1):
                    c = ws.cell(row=row_num, column=col, value=val)
                    c.fill = sub_fill; c.font = Font(bold=True, size=9)
                    if col > 2:
                        c.number_format = num_fmt
                        c.alignment = Alignment(horizontal='right')
                row_num += 1

        # Grand total
        tot_vals = ['GRAND TOTALS', '',
                    float(tot_open_dr), float(tot_open_cr),
                    float(tot_move_dr), float(tot_move_cr),
                    float(tot_clos_dr), float(tot_clos_cr)]
        for col, val in enumerate(tot_vals, 1):
            c = ws.cell(row=row_num, column=col, value=val)
            c.fill = tot_fill; c.font = tot_font
            if col > 2:
                c.number_format = num_fmt
                c.alignment = Alignment(horizontal='right')

        # Column widths
        ws.column_dimensions['A'].width = 12
        ws.column_dimensions['B'].width = 40
        for col in 'CDEFGH':
            ws.column_dimensions[col].width = 18

        # Hospital header rows inserted at top
        _hosp_rows = _hospital_header(f'{lbl}{cc_mode_lbl_x} — {date_from} to {date_to}')
        _n = len(_hosp_rows) + 1  # +1 blank separator
        ws.insert_rows(1, _n)
        for _i, _hrow in enumerate(_hosp_rows, 1):
            _c = ws.cell(row=_i, column=1, value=' | '.join(str(x) for x in _hrow))
            _c.font = Font(bold=True, size=12 if _i == 1 else 9, color='0891B2' if _i == 1 else '374151')
        # row _n is blank separator — leave empty

        import io
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        resp = HR(buf.read(),
                  content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        _cc_mode_slug_x = '_cc' if cc_breakdown else ''
        resp['Content-Disposition'] = (
            f'attachment; filename="balance{_cc_mode_slug_x}_{balance_type}{_cc_slug}_{date_from}_{date_to}.xlsx"'
        )
        return resp

    from apps.accounts.models import HospitalConfig
    hconfig = HospitalConfig.get()

    cost_centers = CostCenter.objects.filter(is_deleted=False, is_active=True).order_by('code')
    selected_cc  = CostCenter.objects.filter(pk=cc_filter).first() if cc_filter else None

    return render(request, 'billing/trial_balance.html', {
        'sections':       sections,
        'cc_sections':    cc_sections,
        'cc_breakdown':   cc_breakdown,
        'date_from':      date_from,
        'date_to':        date_to,
        'balance_type':   balance_type,
        'classe_filter':  classe_filter,
        'code_from':      code_from,
        'code_to':        code_to,
        'avec_mouvement': avec_mouvement,
        'ohada_classes':  OHADA_CLASSES,
        'tot_open_dr':    tot_open_dr, 'tot_open_cr': tot_open_cr,
        'tot_move_dr':    tot_move_dr, 'tot_move_cr': tot_move_cr,
        'tot_clos_dr':    tot_clos_dr, 'tot_clos_cr': tot_clos_cr,
        'is_balanced':    abs(move_diff) < Decimal('0.01'),
        'move_diff':      move_diff,
        'clos_diff':      clos_diff,
        'hconfig':        hconfig,
        'cost_centers':   cost_centers,
        'cc_filter':      cc_filter,
        'selected_cc':    selected_cc,
        # For new CC filter UI: cc_mode=True when any CC filter active
        'cc_mode':        cc_breakdown or bool(cc_filter),
        'cc_select_val':  '' if cc_breakdown else cc_filter,
        'today':          str(today),
    })


# ── Auxiliary Balance ──────────────────────────────────────────────────────────

@login_required
def auxiliary_balance(request):
    """
    True OHADA auxiliary balance — breaks down collective (control) accounts
    by individual third party:
      411  Clients    → one row per patient (from Invoice model)
      401  Fournisseurs → one row per vendor  (from APBill model)
      421  Personnel  → one row per staff member (from StaffAdvance model)
    Each section shows: Subsidiary total vs GL collective account balance.
    If they match → reconciled. If not → data entry error exists.
    """
    if not _can_access_gl(request.user):
        return HttpResponseForbidden()

    from django.db.models import Sum, Prefetch
    from .models import (Invoice, InvoiceStatus, APBill, APBillStatus,
                         StaffAdvance, AdvanceStatus, JournalLine)

    today     = timezone.localdate()
    as_of     = request.GET.get('as_of', str(today))
    try:
        from datetime import date as _d
        as_of_date = _d.fromisoformat(as_of)
    except Exception:
        as_of_date = today

    D0 = Decimal('0')

    def gl_net(prefix):
        """Dr − Cr for all posted lines on accounts starting with prefix, up to as_of_date."""
        r = JournalLine.objects.filter(
            entry__is_deleted=False,
            entry__status='POSTED',
            entry__entry_date__lte=as_of_date,
            account__code__startswith=prefix,
        ).aggregate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))
        return (r['dr'] or D0) - (r['cr'] or D0)

    # ── 1. CLIENTS 411 — AR per patient ───────────────────────────────────────
    ar_gl = gl_net('41')

    invoices = Invoice.objects.filter(
        is_deleted=False,
        issue_date__lte=as_of_date,
        status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
    ).select_related('patient').prefetch_related(
        Prefetch('items',    to_attr='_items_cache'),
        Prefetch('payments', to_attr='_payments_cache'),
        Prefetch('refunds',  to_attr='_refunds_cache'),
    )

    patient_map = {}
    for inv in invoices:
        pid = inv.patient_id
        if pid not in patient_map:
            patient_map[pid] = {
                'name': inv.patient.full_name,
                'ref':  inv.patient.patient_id,
                'billed': D0, 'paid': D0,
            }
        patient_map[pid]['billed'] += Decimal(str(inv.total))
        patient_map[pid]['paid']   += Decimal(str(inv.net_paid))

    ar_rows = sorted([
        {**d, 'balance': d['billed'] - d['paid']}
        for d in patient_map.values()
        if d['billed'] - d['paid'] > D0
    ], key=lambda r: r['name'])
    ar_sub = sum(r['balance'] for r in ar_rows) or D0

    # ── 2. FOURNISSEURS 401 — AP per vendor ───────────────────────────────────
    ap_gl = gl_net('40')   # credit balance → negative; we abs() for display

    bills = APBill.objects.filter(
        is_deleted=False,
        status__in=[APBillStatus.PENDING, APBillStatus.PARTIAL, APBillStatus.OVERDUE],
    ).select_related('vendor')

    vendor_map = {}
    for bill in bills:
        vid = bill.vendor_id
        if vid not in vendor_map:
            vendor_map[vid] = {
                'name': bill.vendor.name,
                'ref':  getattr(bill.vendor, 'vendor_code', '') or '—',
                'billed': D0, 'paid': D0,
            }
        vendor_map[vid]['billed'] += Decimal(str(bill.amount_due))
        vendor_map[vid]['paid']   += Decimal(str(bill.total_paid))

    ap_rows = sorted([
        {**d, 'balance': d['billed'] - d['paid']}
        for d in vendor_map.values()
        if d['billed'] - d['paid'] > D0
    ], key=lambda r: r['name'])
    ap_sub  = sum(r['balance'] for r in ap_rows) or D0
    ap_gl_abs = abs(ap_gl)

    # ── 3. PERSONNEL 421 — Advances per staff member ──────────────────────────
    adv_gl = gl_net('421')

    advances = StaffAdvance.objects.filter(
        is_deleted=False,
        status=AdvanceStatus.DISBURSED,
    ).select_related('staff')

    adv_rows = sorted([
        {
            'name':    adv.staff.get_full_name(),
            'ref':     adv.staff.get_role_display() if hasattr(adv.staff, 'get_role_display') else '',
            'billed':  Decimal(str(adv.amount_approved)),
            'paid':    D0,
            'balance': Decimal(str(adv.amount_approved)),
        }
        for adv in advances
    ], key=lambda r: r['name'])
    adv_sub = sum(r['balance'] for r in adv_rows) or D0

    sections = [
        {
            'code':      '411',
            'name':      'Clients — Créances patients & corporatifs',
            'note':      'Outstanding patient invoices (Issued + Partially Paid) as of date',
            'rows':      ar_rows,
            'subtotal':  ar_sub,
            'gl_bal':    ar_gl,
            'gl_display': ar_gl,
            'balanced':  abs(ar_sub - ar_gl) < Decimal('1'),
            'diff':      ar_sub - ar_gl,
            'col_a':     'Invoiced',
            'col_b':     'Collected',
            'side':      'DR',
        },
        {
            'code':      '401',
            'name':      'Fournisseurs — Dettes envers fournisseurs',
            'note':      'Outstanding vendor bills (Pending + Partial + Overdue) as of date',
            'rows':      ap_rows,
            'subtotal':  ap_sub,
            'gl_bal':    ap_gl_abs,
            'gl_display': ap_gl_abs,
            'balanced':  abs(ap_sub - ap_gl_abs) < Decimal('1'),
            'diff':      ap_sub - ap_gl_abs,
            'col_a':     'Bill Amount',
            'col_b':     'Paid',
            'side':      'CR',
        },
        {
            'code':      '421',
            'name':      'Personnel — Avances non remboursées',
            'note':      'Staff advances with status DISBURSED (not yet settled)',
            'rows':      adv_rows,
            'subtotal':  adv_sub,
            'gl_bal':    adv_gl,
            'gl_display': adv_gl,
            'balanced':  abs(adv_sub - adv_gl) < Decimal('1'),
            'diff':      adv_sub - adv_gl,
            'col_a':     'Advance',
            'col_b':     'Settled',
            'side':      'DR',
        },
    ]

    if request.GET.get('export') == 'csv' or request.GET.get('format') == 'csv':
        import csv
        from django.http import HttpResponse
        resp = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        resp['Content-Disposition'] = f'attachment; filename="auxiliary_balance_{as_of}.csv"'
        w = csv.writer(resp)
        for sec in sections:
            w.writerow([])
            w.writerow([f'{sec["code"]} — {sec["name"]}'])
            w.writerow(['Ref / Code', 'Name', sec['col_a'], sec['col_b'], 'Balance'])
            for row in sec['rows']:
                w.writerow([row['ref'], row['name'], row['billed'], row['paid'], row['balance']])
            w.writerow(['', 'SUBTOTAL (Subsidiary)', '', '', sec['subtotal']])
            w.writerow(['', f'GL Balance ({sec["code"]}xxx)', '', '', sec['gl_bal']])
            w.writerow(['', 'Difference', '', '', sec['diff']])
        return resp
    if request.GET.get('format') == 'excel':
        hdr = _hospital_header(f'Auxiliary Balance — as of {as_of}')
        data_rows = [['Section', 'Code', 'Ref/Code', 'Name', 'Billed/Col A', 'Paid/Col B', 'Balance']]
        for sec in sections:
            for row in sec['rows']:
                data_rows.append([sec['name'], sec['code'], row['ref'], row['name'],
                                  float(row['billed'] or 0), float(row['paid'] or 0), float(row['balance'] or 0)])
            data_rows.append([f'SUBTOTAL — {sec["name"]}', '', '', '', '', '', float(sec['subtotal'] or 0)])
        return _excel_response(f'auxiliary_balance_{as_of}.xlsx', hdr, data_rows, sheet_name='Auxiliary Balance')

    from apps.accounts.models import HospitalConfig
    return render(request, 'billing/auxiliary_balance.html', {
        'sections':  sections,
        'as_of':     as_of,
        'today':     today,
        'hconfig':   HospitalConfig.get(),
    })


# ── Voucher-Wise Balance ───────────────────────────────────────────────────────

@login_required
def voucher_wise_balance(request):
    if not _can_access_gl(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    from datetime import date as _date
    from django.db.models import Sum as _Sum
    today = _date.today()
    date_from_str = request.GET.get('date_from', today.replace(day=1).isoformat())
    date_to_str   = request.GET.get('date_to',   today.isoformat())
    jt_filter     = request.GET.get('journal_type', '')
    try:
        df = _date.fromisoformat(date_from_str)
        dt = _date.fromisoformat(date_to_str)
    except ValueError:
        df = today.replace(day=1)
        dt = today

    qs = JournalEntry.objects.filter(
        is_deleted=False, entry_date__range=[df, dt]
    ).select_related('journal_type').order_by('entry_date', 'entry_number')
    if jt_filter:
        qs = qs.filter(journal_type_id=jt_filter)

    rows = []
    grand_dr = grand_cr = 0
    for entry in qs:
        dr = entry.lines.aggregate(t=_Sum('debit_amount'))['t'] or 0
        cr = entry.lines.aggregate(t=_Sum('credit_amount'))['t'] or 0
        diff = abs(dr - cr)
        rows.append({'entry': entry, 'total_dr': dr, 'total_cr': cr,
                     'balanced': diff < Decimal('0.01'), 'diff': diff})
        grand_dr += dr
        grand_cr += cr

    if request.GET.get('export') == 'csv' or request.GET.get('format') == 'csv':
        import csv
        from django.http import HttpResponse as _HR
        resp = _HR(content_type='text/csv')
        resp['Content-Disposition'] = f'attachment; filename="voucher_balance_{date_from_str}_{date_to_str}.csv"'
        w = csv.writer(resp)
        w.writerow(['Date', 'Voucher #', 'Type', 'Description', 'Total Debits', 'Total Credits', 'Balanced'])
        for r in rows:
            w.writerow([r['entry'].entry_date, r['entry'].entry_number,
                        r['entry'].journal_type.code if r['entry'].journal_type else '',
                        r['entry'].description, r['total_dr'], r['total_cr'], r['balanced']])
        return resp
    if request.GET.get('format') == 'excel':
        hdr = _hospital_header(f'Voucher-Wise Balance — {date_from_str} to {date_to_str}')
        data_rows = [['Date', 'Voucher #', 'Type', 'Description', 'Total Debits (XAF)', 'Total Credits (XAF)', 'Balanced']]
        for r in rows:
            data_rows.append([str(r['entry'].entry_date), r['entry'].entry_number,
                              r['entry'].journal_type.code if r['entry'].journal_type else '',
                              r['entry'].description, float(r['total_dr']), float(r['total_cr']),
                              'Yes' if r['balanced'] else 'No'])
        data_rows.append(['GRAND TOTAL', '', '', '', float(grand_dr), float(grand_cr), ''])
        return _excel_response(f'voucher_balance_{date_from_str}_{date_to_str}.xlsx', hdr, data_rows, sheet_name='Voucher Balance')

    return render(request, 'billing/voucher_wise_balance.html', {
        'rows': rows, 'grand_dr': grand_dr, 'grand_cr': grand_cr,
        'date_from': df, 'date_to': dt,
        'date_from_str': date_from_str, 'date_to_str': date_to_str,
        'journal_types': JournalType.objects.filter(is_deleted=False).order_by('code'),
    })


# ── AP Aging ───────────────────────────────────────────────────────────────────

@login_required
def ap_aging_report(request):
    if not _can_authorize_billing(request.user) and not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    from datetime import date as _date
    from .models import APBill, APBillStatus
    today = _date.today()

    bills = APBill.objects.filter(
        is_deleted=False, status__in=['PENDING', 'PARTIAL']
    ).select_related('vendor').order_by('vendor__name', 'due_date')

    rows = []
    summary = {'current': 0, 'days1_30': 0, 'days31_60': 0, 'days61_90': 0, 'days91_plus': 0}
    grand_outstanding = 0

    for bill in bills:
        paid = bill.total_paid
        outstanding = bill.balance_due
        if outstanding <= 0:
            continue
        due = bill.due_date or bill.bill_date
        days_overdue = (today - due).days
        is_overdue = days_overdue > 0
        if days_overdue <= 0:
            bucket = 'current'
            summary['current'] += outstanding
        elif days_overdue <= 30:
            bucket = 'd1_30'
            summary['days1_30'] += outstanding
        elif days_overdue <= 60:
            bucket = 'd31_60'
            summary['days31_60'] += outstanding
        elif days_overdue <= 90:
            bucket = 'd61_90'
            summary['days61_90'] = summary.get('days61_90', 0) + outstanding
        else:
            bucket = 'd91plus'
            summary['days91_plus'] += outstanding
        grand_outstanding += outstanding
        rows.append({'bill': bill, 'paid': paid, 'outstanding': outstanding,
                     'bucket': bucket, 'days_overdue': days_overdue, 'is_overdue': is_overdue})

    summary['days61_plus'] = summary.get('days61_90', 0) + summary['days91_plus']

    if request.GET.get('export') == 'csv':
        import csv
        from django.http import HttpResponse as _HR
        resp = _HR(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="ap_aging.csv"'
        w = csv.writer(resp)
        w.writerow(['Supplier', 'Bill #', 'Date', 'Due Date', 'Total', 'Paid', 'Outstanding', 'Current', '1-30', '31-60', '61-90', '91+'])
        for r in rows:
            b = r['bucket']
            w.writerow([r['bill'].vendor.name, r['bill'].bill_number, r['bill'].bill_date,
                        r['bill'].due_date, r['bill'].amount_due, r['paid'], r['outstanding'],
                        r['outstanding'] if b=='current' else 0, r['outstanding'] if b=='d1_30' else 0,
                        r['outstanding'] if b=='d31_60' else 0, r['outstanding'] if b=='d61_90' else 0,
                        r['outstanding'] if b=='d91plus' else 0])
        return resp

    return render(request, 'billing/ap_aging.html', {
        'rows': rows, 'summary': summary,
        'grand_outstanding': grand_outstanding, 'today': today,
    })


# ── Customer Ledger Summary ────────────────────────────────────────────────────

@login_required
def customer_ledger_summary(request):
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    from datetime import date as _date
    from django.db.models import Sum as _Sum
    today = _date.today()
    date_from_str = request.GET.get('date_from', today.replace(day=1).isoformat())
    date_to_str   = request.GET.get('date_to',   today.isoformat())
    show          = request.GET.get('show', 'all')
    try:
        df = _date.fromisoformat(date_from_str)
        dt = _date.fromisoformat(date_to_str)
    except ValueError:
        df = today.replace(day=1)
        dt = today

    from django.db.models import Sum as _Sum, Value, CharField, F, Q
    from django.db.models.functions import Concat
    from apps.patients.models import Patient

    # Group invoices by patient
    qs = Invoice.objects.filter(
        is_deleted=False, issue_date__range=[df, dt]
    ).exclude(status='VOID').select_related('patient')

    patient_map = {}
    for inv in qs:
        pid = inv.patient_id
        if pid not in patient_map:
            patient_map[pid] = {
                'name': inv.patient.full_name,
                'patient_id': inv.patient.patient_id,
                'total_invoiced': Decimal('0'),
                'total_paid': Decimal('0'),
            }
        patient_map[pid]['total_invoiced'] += inv.total or Decimal('0')
        patient_map[pid]['total_paid'] += inv.amount_paid or Decimal('0')

    rows = []
    grand_invoiced = grand_paid = grand_outstanding = Decimal('0')
    for data in sorted(patient_map.values(), key=lambda x: x['name']):
        outstanding = data['total_invoiced'] - data['total_paid']
        if show == 'outstanding' and outstanding <= 0:
            continue
        data['outstanding'] = outstanding
        rows.append(data)
        grand_invoiced += data['total_invoiced']
        grand_paid += data['total_paid']
        grand_outstanding += outstanding

    if request.GET.get('export') == 'csv':
        import csv
        from django.http import HttpResponse as _HR
        resp = _HR(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="customer_ledger_summary.csv"'
        w = csv.writer(resp)
        w.writerow(['Customer', 'Patient ID', 'Total Invoiced', 'Total Paid', 'Outstanding'])
        for r in rows:
            w.writerow([r['name'], r['patient_id'], r['total_invoiced'], r['total_paid'], r['outstanding']])
        return resp

    return render(request, 'billing/customer_ledger_summary.html', {
        'rows': rows, 'grand_invoiced': grand_invoiced,
        'grand_paid': grand_paid, 'grand_outstanding': grand_outstanding,
        'date_from': df, 'date_to': dt,
        'date_from_str': date_from_str, 'date_to_str': date_to_str, 'show': show,
    })


# ── Balance Sheet ─────────────────────────────────────────────────────────────

@login_required
def balance_sheet(request):
    if not _can_access_gl(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    date_to = request.GET.get('as_at') or request.GET.get('date_to') or str(timezone.localdate())

    # Bulk aggregate — one query
    bulk_agg = (
        JournalLine.objects.filter(
            entry__is_deleted=False, entry__entry_date__lte=date_to,
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

    def build_groups(acct_type):
        """Group accounts by first 2 digits of code → gives OHADA sub-classes."""
        accts = GLAccount.objects.filter(
            is_deleted=False, is_active=True, account_type=acct_type,
        ).order_by('code')
        groups_map = {}
        for a in accts:
            bal = get_balance(a)
            if bal == 0:
                continue
            prefix = a.code[:2] if len(a.code) >= 2 else a.code[:1]
            grp = groups_map.setdefault(prefix, {'label': '', 'rows': [], 'total': Decimal('0')})
            grp['rows'].append({'code': a.code, 'name': a.name, 'balance': bal})
            grp['total'] += bal
        # Build sorted list
        result = []
        ohada_labels = {
            '10': 'Capital', '11': 'Reserves', '12': 'Retained Earnings', '13': 'Net Result',
            '20': 'Intangible Assets', '21': 'Tangible Assets', '22': 'Land & Buildings',
            '23': 'Plant & Equipment', '24': 'Financial Assets', '28': 'Accumulated Depreciation',
            '30': 'Goods & Supplies', '31': 'Raw Materials', '32': 'Packaging',
            '38': 'Stock Provisions', '39': 'Inventory Provisions',
            '40': 'Accounts Payable', '41': 'Accounts Receivable', '42': 'Staff Payable',
            '43': 'Social Security', '44': 'Tax Payable', '46': 'Inter-company',
            '47': 'Deferred Revenue', '48': 'Other Liabilities', '49': 'Provisions',
            '50': 'Securities', '51': 'Bank Accounts', '52': 'Bank Accounts (Other)',
            '53': 'Treasury', '56': 'Bank Transfers', '57': 'Cash in Hand', '58': 'Internal Transfers',
            '60': 'Purchases', '61': 'External Services', '62': 'Other Services',
            '63': 'Taxes & Duties', '64': 'Staff Costs', '65': 'Other Expenses',
            '66': 'Financial Charges', '67': 'Extraordinary Charges', '68': 'Depreciation',
            '69': 'Income Tax',
            '70': 'Sales Revenue', '71': 'Production Stored', '72': 'Production Capitalized',
            '73': 'Variation in Stocks', '75': 'Other Revenue', '76': 'Financial Income',
            '77': 'Extraordinary Income', '78': 'Provisions Reversed', '79': 'Transfers',
        }
        for prefix in sorted(groups_map.keys()):
            grp = groups_map[prefix]
            grp['label'] = ohada_labels.get(prefix, f'Class {prefix}')
            result.append(grp)
        return result

    # Build grouped sections
    asset_groups = build_groups(AccountType.ASSET)
    liab_groups = build_groups(AccountType.LIABILITY)

    # Equity rows (flat)
    equity_accts = GLAccount.objects.filter(
        is_deleted=False, is_active=True, account_type=AccountType.EQUITY,
    ).order_by('code')
    equity_rows = [{'code': a.code, 'name': a.name, 'balance': get_balance(a)}
                   for a in equity_accts if get_balance(a) != 0]

    # Revenue & Expense for net income
    rev_accts = GLAccount.objects.filter(is_deleted=False, is_active=True, account_type=AccountType.REVENUE)
    exp_accts = GLAccount.objects.filter(is_deleted=False, is_active=True, account_type=AccountType.EXPENSE)
    total_revenue = sum(get_balance(a) for a in rev_accts)
    total_expense = sum(get_balance(a) for a in exp_accts)
    net_income = total_revenue - total_expense  # revenue balance is positive (cr - dr)

    total_assets = sum(g['total'] for g in asset_groups)
    total_liabilities = sum(g['total'] for g in liab_groups)
    total_equity_val = sum(r['balance'] for r in equity_rows) + net_income
    total_liab_equity = total_liabilities + total_equity_val
    diff = total_assets - total_liab_equity

    ctx = {
        'assets': asset_groups,
        'liabilities': liab_groups,
        'equity_rows': equity_rows,
        'net_income': net_income,
        'total_assets': total_assets,
        'total_liabilities': total_liabilities,
        'total_equity': total_equity_val,
        'total_liab_equity': total_liab_equity,
        'is_balanced': abs(diff) < Decimal('0.01'),
        'balance_diff': diff,
        'date_to': date_to,
    }
    fmt = request.GET.get('format', '')
    if fmt == 'csv':
        hdr = _hospital_header(f'Balance Sheet — as at {date_to}')
        rows = [['Section', 'Account', 'Balance (FCFA)']]
        for grp in asset_groups:
            for row in grp.get('rows', []):
                rows.append(['Assets — ' + grp.get('name',''), row.get('name',''), float(row.get('balance',0))])
        for grp in liab_groups:
            for row in grp.get('rows', []):
                rows.append(['Liabilities — ' + grp.get('name',''), row.get('name',''), float(row.get('balance',0))])
        for row in equity_rows:
            rows.append(['Equity', row.get('name',''), float(row.get('balance',0))])
        rows.append(['', 'TOTAL ASSETS', float(total_assets)])
        rows.append(['', 'TOTAL LIABILITIES + EQUITY', float(total_liab_equity)])
        return _csv_response(f'balance_sheet_{date_to}.csv', hdr, rows)
    if fmt == 'excel':
        hdr = _hospital_header(f'Balance Sheet — as at {date_to}')
        rows = [['Section', 'Account', 'Balance (FCFA)']]
        for grp in asset_groups:
            for row in grp.get('rows', []):
                rows.append(['Assets — ' + grp.get('name',''), row.get('name',''), float(row.get('balance',0))])
        for grp in liab_groups:
            for row in grp.get('rows', []):
                rows.append(['Liabilities — ' + grp.get('name',''), row.get('name',''), float(row.get('balance',0))])
        for row in equity_rows:
            rows.append(['Equity', row.get('name',''), float(row.get('balance',0))])
        rows.append(['', 'TOTAL ASSETS', float(total_assets)])
        rows.append(['', 'TOTAL LIABILITIES + EQUITY', float(total_liab_equity)])
        return _excel_response(f'balance_sheet_{date_to}.xlsx', hdr, rows, sheet_name='Balance Sheet')
    return render(request, 'billing/balance_sheet.html', ctx)


# ── Cash Flow Statement ───────────────────────────────────────────────────────

@login_required
def cash_flow_statement(request):
    if not _can_access_gl(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    from apps.billing.models import (
        Payment, Expense, APPayment, CashToBank,
        StaffAdvance, AssetRegister, CashTransfer, BankAccount,
    )
    today = timezone.localdate()
    first_of_month = today.replace(day=1)
    date_from = request.GET.get('date_from', str(first_of_month))
    date_to   = request.GET.get('date_to',   str(today))

    # ── OPERATING INFLOWS ──
    # Patient payments by method
    from django.db.models import Count as _Cnt
    pay_by_method = Payment.objects.filter(
        is_deleted=False,
        payment_date__date__gte=date_from, payment_date__date__lte=date_to,
    ).exclude(payment_method__in=('INSURANCE', 'NHIS', 'WAIVER')
    ).values('payment_method').annotate(total=Sum('amount')).order_by('-total')

    operating_inflows = []
    total_op_inflows = Decimal('0')
    method_labels = dict(PaymentMethod.choices) if hasattr(PaymentMethod, 'choices') else {}
    for pm in pay_by_method:
        amt = pm['total'] or Decimal('0')
        if amt > 0:
            label = method_labels.get(pm['payment_method'], pm['payment_method'])
            operating_inflows.append({'label': f'Patient Payments — {label}', 'amount': amt})
            total_op_inflows += amt

    # Insurance receipts
    insurance_receipts = Payment.objects.filter(
        is_deleted=False,
        payment_date__date__gte=date_from, payment_date__date__lte=date_to,
        payment_method__in=('INSURANCE', 'NHIS'),
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    if insurance_receipts > 0:
        operating_inflows.append({'label': 'Insurance Reimbursements', 'amount': insurance_receipts})
        total_op_inflows += insurance_receipts

    # ── OPERATING OUTFLOWS ──
    operating_outflows = []
    total_op_outflows = Decimal('0')

    # Expenses by category
    exp_by_cat = Expense.objects.filter(
        is_deleted=False, approved_by__isnull=False,
        date__gte=date_from, date__lte=date_to,
    ).values('category').annotate(total=Sum('amount')).order_by('-total')
    exp_cat_labels = dict(ExpenseCategory.choices) if hasattr(ExpenseCategory, 'choices') else {}
    for ec in exp_by_cat:
        amt = ec['total'] or Decimal('0')
        if amt > 0:
            label = exp_cat_labels.get(ec['category'], ec['category'])
            operating_outflows.append({'label': f'{label}', 'amount': amt})
            total_op_outflows += amt

    # AP vendor payments
    ap_total = APPayment.objects.filter(
        is_deleted=False, payment_date__gte=date_from, payment_date__lte=date_to,
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    if ap_total > 0:
        operating_outflows.append({'label': 'Supplier / Vendor Payments', 'amount': ap_total})
        total_op_outflows += ap_total

    net_operating = total_op_inflows - total_op_outflows

    # ── INVESTING ACTIVITIES ──
    investing_rows = []
    net_investing = Decimal('0')

    # Asset purchases (from GL class 2 debits in the period)
    asset_purchases = JournalLine.objects.filter(
        entry__is_deleted=False,
        entry__entry_date__gte=date_from, entry__entry_date__lte=date_to,
        account__code__startswith='2', debit_amount__gt=0,
    ).aggregate(t=Sum('debit_amount'))['t'] or Decimal('0')
    if asset_purchases > 0:
        investing_rows.append({'label': 'Purchase of Fixed Assets', 'amount': -asset_purchases})
        net_investing -= asset_purchases

    # Asset disposal proceeds (class 2 credits)
    asset_proceeds = JournalLine.objects.filter(
        entry__is_deleted=False,
        entry__entry_date__gte=date_from, entry__entry_date__lte=date_to,
        account__code__startswith='2', credit_amount__gt=0,
    ).aggregate(t=Sum('credit_amount'))['t'] or Decimal('0')
    if asset_proceeds > 0:
        investing_rows.append({'label': 'Proceeds from Asset Disposal', 'amount': asset_proceeds})
        net_investing += asset_proceeds

    # ── FINANCING ACTIVITIES ──
    financing_rows = []
    net_financing = Decimal('0')

    # Staff advances issued
    advances_issued = JournalLine.objects.filter(
        entry__is_deleted=False,
        entry__entry_date__gte=date_from, entry__entry_date__lte=date_to,
        account__code__startswith='42', debit_amount__gt=0,
    ).aggregate(t=Sum('debit_amount'))['t'] or Decimal('0')
    if advances_issued > 0:
        financing_rows.append({'label': 'Staff Advances Issued', 'amount': -advances_issued})
        net_financing -= advances_issued

    # Staff advances recovered
    advances_recovered = JournalLine.objects.filter(
        entry__is_deleted=False,
        entry__entry_date__gte=date_from, entry__entry_date__lte=date_to,
        account__code__startswith='42', credit_amount__gt=0,
    ).aggregate(t=Sum('credit_amount'))['t'] or Decimal('0')
    if advances_recovered > 0:
        financing_rows.append({'label': 'Staff Advances Recovered', 'amount': advances_recovered})
        net_financing += advances_recovered

    # Capital / equity movements (class 1)
    equity_dr = JournalLine.objects.filter(
        entry__is_deleted=False,
        entry__entry_date__gte=date_from, entry__entry_date__lte=date_to,
        account__code__startswith='1', debit_amount__gt=0,
    ).aggregate(t=Sum('debit_amount'))['t'] or Decimal('0')
    equity_cr = JournalLine.objects.filter(
        entry__is_deleted=False,
        entry__entry_date__gte=date_from, entry__entry_date__lte=date_to,
        account__code__startswith='1', credit_amount__gt=0,
    ).aggregate(t=Sum('credit_amount'))['t'] or Decimal('0')
    equity_net = equity_cr - equity_dr
    if equity_net != 0:
        financing_rows.append({'label': 'Capital / Equity Movements', 'amount': equity_net})
        net_financing += equity_net

    # ── OPENING / CLOSING CASH ──
    # Cash accounts = class 5 (Bank + Cash)
    cash_opening_lines = JournalLine.objects.filter(
        entry__is_deleted=False,
        entry__entry_date__lt=date_from,
        account__code__startswith='5',
    ).aggregate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))
    opening_cash = (cash_opening_lines['dr'] or Decimal('0')) - (cash_opening_lines['cr'] or Decimal('0'))

    net_change = net_operating + net_investing + net_financing
    closing_cash = opening_cash + net_change

    ctx = {
        'date_from': date_from, 'date_to': date_to,
        'operating_inflows': operating_inflows, 'operating_outflows': operating_outflows,
        'total_op_inflows': total_op_inflows, 'total_op_outflows': total_op_outflows,
        'net_operating': net_operating, 'investing_rows': investing_rows,
        'net_investing': net_investing, 'financing_rows': financing_rows,
        'net_financing': net_financing, 'opening_cash': opening_cash,
        'net_change': net_change, 'closing_cash': closing_cash,
    }
    fmt = request.GET.get('format', '')
    if fmt in ('csv', 'excel'):
        hdr = _hospital_header(f'Cash Flow Statement — {date_from} to {date_to}')
        rows = [['Section', 'Description', 'Amount (FCFA)']]
        for r in operating_inflows:
            rows.append(['Operating Inflows', r['label'], float(r['amount'])])
        for r in operating_outflows:
            rows.append(['Operating Outflows', r['label'], float(r['amount'])])
        rows.append(['', 'Net Operating Cash Flow', float(net_operating)])
        for r in investing_rows:
            rows.append(['Investing', r.get('label',''), float(r.get('amount',0))])
        rows.append(['', 'Net Investing Cash Flow', float(net_investing)])
        for r in financing_rows:
            rows.append(['Financing', r.get('label',''), float(r.get('amount',0))])
        rows.append(['', 'Net Financing Cash Flow', float(net_financing)])
        rows.append(['', 'Opening Cash Balance', float(opening_cash)])
        rows.append(['', 'NET CHANGE IN CASH', float(net_change)])
        rows.append(['', 'CLOSING CASH BALANCE', float(closing_cash)])
        if fmt == 'csv':
            return _csv_response(f'cash_flow_{date_from}_{date_to}.csv', hdr, rows)
        return _excel_response(f'cash_flow_{date_from}_{date_to}.xlsx', hdr, rows, sheet_name='Cash Flow')
    return render(request, 'billing/cash_flow.html', ctx)


# ═══════════════════════════════════════════════════════════════════════════════
# ACCOUNTS PAYABLE  —  Vendors, Bills, Payments
# ═══════════════════════════════════════════════════════════════════════════════
from .models import APVendor, APBill, APPayment, APBillStatus


def _can_access_ap(user):
    return user.role in (
        UserRole.ACCOUNTANT, UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR, UserRole.BILLING_OFFICER,
        UserRole.CEO, UserRole.ADMIN_DIRECTOR,
        UserRole.MEDICAL_DIRECTOR, UserRole.SUPER_ADMIN,
    ) or user.is_superuser


@login_required
def ap_vendor_list(request):
    if not _can_access_ap(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    vendors = APVendor.objects.filter(is_deleted=False).order_by('name')
    if request.GET.get('q'):
        vendors = vendors.filter(Q(name__icontains=request.GET.get('q', '')) | Q(vendor_code__icontains=request.GET.get('q', '')))
    from django.db.models import Sum as _S
    today = timezone.localdate()
    total_outstanding = APBill.objects.filter(is_deleted=False).exclude(
        status=APBillStatus.PAID
    ).aggregate(t=_S('amount_due'))['t'] or 0
    overdue_count = APBill.objects.filter(
        is_deleted=False, due_date__lt=today,
        status__in=[APBillStatus.DRAFT, APBillStatus.PARTIAL, APBillStatus.PENDING, APBillStatus.OVERDUE],
    ).count()
    active_vendors = APVendor.objects.filter(is_deleted=False, is_active=True).count()
    return render(request, 'billing/ap_vendor_list.html', {
        'vendors': vendors,
        'total_vendors': vendors.count(),
        'total_outstanding': total_outstanding,
        'overdue_count': overdue_count,
        'active_vendors': active_vendors,
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
                phone=request.POST.get('contact_phone') or request.POST.get('phone', ''),
                email=request.POST.get('email', ''),
                address=request.POST.get('address', ''),
                tax_id=request.POST.get('tax_number') or request.POST.get('tax_id', ''),
                payment_terms_days=int(request.POST.get('payment_terms') or request.POST.get('payment_terms_days') or 30),
                bank_name=request.POST.get('bank_name', ''),
                bank_account=request.POST.get('bank_account_number') or request.POST.get('bank_account', ''),
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
        vendor.phone = request.POST.get('contact_phone') or request.POST.get('phone', '')
        vendor.email = request.POST.get('email', '')
        vendor.address = request.POST.get('address', '')
        vendor.tax_id = request.POST.get('tax_number') or request.POST.get('tax_id', '')
        vendor.payment_terms_days = int(request.POST.get('payment_terms') or request.POST.get('payment_terms_days') or 30)
        vendor.bank_name = request.POST.get('bank_name', '')
        vendor.bank_account = request.POST.get('bank_account_number') or request.POST.get('bank_account', '')
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
    from apps.inventory.models import GoodsReceivedNote, GRNStatus
    vendors = APVendor.objects.filter(is_deleted=False, is_active=True).order_by('name')
    gl_accounts = GLAccount.objects.filter(is_deleted=False, is_active=True, account_type='EXPENSE').order_by('code')
    # Only GRNs that are ACCEPTED and not already fully billed
    open_grns = GoodsReceivedNote.objects.filter(
        status=GRNStatus.ACCEPTED, is_deleted=False
    ).select_related('purchase_order__vendor').order_by('-received_date')

    if request.method == 'POST':
        vendor_pk = request.POST.get('vendor') or request.POST.get('vendor_id')
        if not vendor_pk:
            messages.error(request, 'Please select a vendor.')
        else:
            vendor = get_object_or_404(APVendor, pk=vendor_pk)
            amount_due = Decimal(request.POST.get('amount_due') or '0')
            if amount_due <= 0:
                messages.error(request, 'Amount must be greater than zero.')
            else:
                from apps.billing.models import ExpenseCategory
                grn_pk = request.POST.get('grn') or None
                grn_obj = GoodsReceivedNote.objects.filter(pk=grn_pk, is_deleted=False).first() if grn_pk else None
                bill = APBill.objects.create(
                    vendor=vendor,
                    vendor_ref=request.POST.get('vendor_invoice_number') or request.POST.get('vendor_ref', ''),
                    category=request.POST.get('category', 'EXP_OTHER'),
                    description=request.POST.get('description', '').strip(),
                    amount_due=amount_due,
                    tax_amount=Decimal(request.POST.get('tax_amount') or '0'),
                    bill_date=request.POST.get('bill_date') or timezone.localdate(),
                    due_date=request.POST.get('due_date') or None,
                    gl_account=GLAccount.objects.filter(
                        pk=request.POST.get('expense_account') or request.POST.get('gl_account_id')
                    ).first(),
                    grn=grn_obj,
                    attachment_ref=request.POST.get('attachment_ref', ''),
                    notes=request.POST.get('notes', ''),
                    approved_by=request.user,
                    created_by=request.user,
                )
                if grn_obj:
                    messages.success(request, f'Bill {bill.bill_number} created and matched to GRN {grn_obj.grn_number}. GL: 408100 cleared → AP Vendors.')
                else:
                    messages.success(request, f'Bill {bill.bill_number} created. GL: Expense account debited → AP Vendors.')
                return redirect('billing:ap_bill_list')
    from apps.billing.models import ExpenseCategory
    return render(request, 'billing/ap_bill_form.html', {
        'vendors': vendors,
        'expense_accounts': gl_accounts,
        'gl_accounts': gl_accounts,
        'expense_categories': ExpenseCategory.choices,
        'open_grns': open_grns,
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
    """Create / edit cash desks — Chief Cashier, Senior Accountant, Finance Director, oversight roles."""
    return user.role in (
        UserRole.CHIEF_CASHIER,
        UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR,
        UserRole.CEO,
        UserRole.ADMIN_DIRECTOR,
        UserRole.MEDICAL_DIRECTOR,
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
    """Approve discount requests from cashiers — Chief Cashier and above, oversight roles can view."""
    return user.role in (
        UserRole.CHIEF_CASHIER,
        UserRole.ACCOUNTANT,
        UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR,
        UserRole.CEO,
        UserRole.ADMIN_DIRECTOR,
        UserRole.MEDICAL_DIRECTOR,
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
        ('STANDARD', 'Standard'), ('EXPRESS', 'Express'), ('VIP', 'VIP'), ('EVIP', 'Executive VIP'),
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
            ('STANDARD', 'Standard'), ('EXPRESS', 'Express'), ('VIP', 'VIP'), ('EVIP', 'Executive VIP'),
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


# ── Change Service Type (Changement Type Prestation) ─────────────────────────

@login_required
@require_POST
def invoice_change_service_type(request, invoice_id):
    """
    Cashier changes the billing/payment type on an invoice.
    Covers: Cash → Insurance (with scheme + auto-amount), Cash → Corporate,
            Insurance → Cash, etc.
    Allowed roles: cashier, chief_cashier, accountant, senior_accountant, finance_director.
    Only on DRAFT or ISSUED invoices.
    """
    from apps.hmo.models import InsuranceScheme
    from .models import CorporateAccount, InvoiceRoutingType

    u = request.user
    allowed = (
        u.is_cashier or u.is_chief_cashier or u.is_accountant
        or u.is_senior_accountant or u.is_finance_director or u.is_super_admin
    )
    if not allowed:
        return JsonResponse({'error': 'Access denied.'}, status=403)

    invoice = get_object_or_404(Invoice, pk=invoice_id, is_deleted=False)
    if invoice.status not in (InvoiceStatus.DRAFT, InvoiceStatus.ISSUED):
        return JsonResponse({'error': 'Can only change service type on DRAFT or ISSUED invoices.'}, status=400)

    new_type      = request.POST.get('new_type', '').strip()
    scheme_id     = request.POST.get('scheme_id', '').strip()
    corporate_id  = request.POST.get('corporate_id', '').strip()
    coverage_pct  = request.POST.get('coverage_pct', '').strip()
    reason        = request.POST.get('reason', '').strip()

    valid_types = [c[0] for c in InvoiceRoutingType.choices]
    if new_type not in valid_types:
        return JsonResponse({'error': f'Invalid type. Choose from: {", ".join(valid_types)}'}, status=400)
    if not reason:
        return JsonResponse({'error': 'Reason is required.'}, status=400)

    update_fields = ['routing_type', 'updated_at']
    old_type = invoice.routing_type

    # Reset any previous insurance / corporate linkage
    invoice.insurance_scheme = None
    invoice.insurance_amount = Decimal('0')
    invoice.corporate_account = None
    update_fields += ['insurance_scheme', 'insurance_amount', 'corporate_account']

    if new_type == InvoiceRoutingType.INSURANCE:
        scheme = None
        if scheme_id:
            try:
                scheme = InsuranceScheme.objects.get(pk=scheme_id, is_active=True)
            except InsuranceScheme.DoesNotExist:
                return JsonResponse({'error': 'Insurance scheme not found.'}, status=400)
        invoice.insurance_scheme = scheme
        # Auto-calculate insurance amount from coverage %
        try:
            pct = Decimal(coverage_pct) if coverage_pct else (scheme.coverage_pct if scheme else Decimal('80'))
        except Exception:
            pct = Decimal('80')
        pct = max(Decimal('0'), min(Decimal('100'), pct))
        if invoice.total > 0:
            invoice.insurance_amount = (invoice.total * pct / Decimal('100')).quantize(Decimal('1'))

    elif new_type == InvoiceRoutingType.TIER:
        # Switching back to cash/tier — insurance already cleared above
        pass

    elif new_type == InvoiceRoutingType.PHARMACY or new_type == InvoiceRoutingType.OPTICAL:
        pass  # Just a routing label change, no financial impact

    # Corporate account linkage (works alongside any routing_type)
    if corporate_id:
        try:
            corp = CorporateAccount.objects.get(pk=corporate_id, is_deleted=False, is_active=True)
            invoice.corporate_account = corp
        except CorporateAccount.DoesNotExist:
            return JsonResponse({'error': 'Corporate account not found.'}, status=400)

    invoice.routing_type = new_type
    invoice.save(update_fields=update_fields)

    # Append change note to invoice notes
    from django.utils.timezone import localtime
    note_line = (
        f"[{localtime().strftime('%d/%m/%Y %H:%M')}] {u.get_full_name() or u.username} "
        f"changed service type: {old_type or 'TIER'} → {new_type}. Reason: {reason}"
    )
    Invoice.objects.filter(pk=invoice.pk).update(
        notes=invoice.notes + ('\n' if invoice.notes else '') + note_line
    )

    return JsonResponse({
        'success': True,
        'new_type': new_type,
        'new_type_display': dict(InvoiceRoutingType.choices).get(new_type, new_type),
        'insurance_amount': int(invoice.insurance_amount),
        'patient_amount': int(invoice.patient_amount),
        'scheme_name': invoice.insurance_scheme.name if invoice.insurance_scheme else '',
    })


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
    """Supervisor view — pending discount approval requests + recent decisions."""
    if not _can_approve_discount(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from django.db.models import Prefetch
    pending = DiscountApproval.objects.filter(
        status=DiscountApprovalStatus.PENDING, is_deleted=False
    ).select_related('invoice', 'invoice__patient', 'requested_by').prefetch_related(
        Prefetch('invoice__items', queryset=InvoiceItem.objects.filter(is_deleted=False).order_by('created_at'))
    ).order_by('-created_at')
    recent = DiscountApproval.objects.exclude(
        status=DiscountApprovalStatus.PENDING
    ).filter(is_deleted=False).select_related(
        'invoice', 'invoice__patient', 'requested_by', 'approved_by'
    ).order_by('-decision_at')[:20]
    return render(request, 'billing/discount_approval_list.html', {
        'approvals': pending,
        'recent': recent,
    })


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
        # Notify cashier POS via WebSocket
        from apps.core.ws_notify import notify_queue
        notify_queue(
            f'discount-{approval.invoice_id}',
            action='discount_approved',
            data={
                'approved_amount': int(approved_amount),
                'new_total': int(approval.invoice.total),
                'new_balance': int(approval.invoice.balance_due),
                'decided_by': request.user.get_full_name() or request.user.username,
                'notes': notes,
            }
        )
    elif decision == 'REJECT':
        approval.status         = DiscountApprovalStatus.REJECTED
        approval.approved_by    = request.user
        approval.decision_at    = timezone.now()
        approval.decision_notes = notes
        approval.save()
        messages.info(request, 'Discount request rejected.')
        # Notify cashier POS via WebSocket
        from apps.core.ws_notify import notify_queue
        notify_queue(
            f'discount-{approval.invoice_id}',
            action='discount_rejected',
            data={
                'decided_by': request.user.get_full_name() or request.user.username,
                'notes': notes,
            }
        )
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


# ═══════════════════════════════════════════════════════════════════════════════
# ROLE-BASED ACCESS HELPERS  —  Finance module role segregation
# ═══════════════════════════════════════════════════════════════════════════════
# Per AEF Finance Policy Manual role hierarchy:
#   Cashier → Senior Cashier (Chief Cashier) → Accountant → Senior Accountant
#   → Finance Manager (Finance Director) → Admin Director → CEO
# Additional: Storekeeper, Procurement Officer, Insurance In-charge

def _can_manage_bank(user):
    """Bank operations — Accountant and above (view), Senior Accountant+ (modify)."""
    return user.role in (
        UserRole.ACCOUNTANT, UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR, UserRole.CHIEF_CASHIER,
        UserRole.BILLING_OFFICER, UserRole.CEO,
        UserRole.ADMIN_DIRECTOR, UserRole.MEDICAL_DIRECTOR,
        UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_do_reconciliation(user):
    """Bank reconciliation — Accountant (assists), Senior Accountant (prepares), Finance Manager (reviews)."""
    return user.role in (
        UserRole.ACCOUNTANT, UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR, UserRole.CEO,
        UserRole.ADMIN_DIRECTOR, UserRole.MEDICAL_DIRECTOR,
        UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_manage_cheques(user):
    """Cheque management — Accountant (writes), Senior Accountant (supervises), oversight roles (view)."""
    return user.role in (
        UserRole.ACCOUNTANT, UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR, UserRole.CHIEF_CASHIER,
        UserRole.BILLING_OFFICER, UserRole.CEO,
        UserRole.ADMIN_DIRECTOR, UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_manage_advances(user):
    """Staff advance approval — Finance Manager/CEO approves, Senior Accountant reviews."""
    return user.role in (
        UserRole.SENIOR_ACCOUNTANT, UserRole.FINANCE_DIRECTOR,
        UserRole.ADMIN_DIRECTOR, UserRole.CEO, UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_manage_cash_transfers(user):
    """Cash transfers — Cashier (initiates desk→safe), Chief Cashier (oversight), Accountant (confirms)."""
    return user.role in (
        UserRole.CASHIER, UserRole.CHIEF_CASHIER, UserRole.ACCOUNTANT,
        UserRole.SENIOR_ACCOUNTANT, UserRole.FINANCE_DIRECTOR,
        UserRole.BILLING_OFFICER, UserRole.CEO,
        UserRole.ADMIN_DIRECTOR, UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_manage_safe(user):
    """Safe balance — Chief Cashier and Accountant (dual-key per policy), oversight roles (view)."""
    return user.role in (
        UserRole.CHIEF_CASHIER, UserRole.ACCOUNTANT,
        UserRole.SENIOR_ACCOUNTANT, UserRole.FINANCE_DIRECTOR,
        UserRole.BILLING_OFFICER, UserRole.CEO,
        UserRole.ADMIN_DIRECTOR, UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_manage_assets_full(user):
    """Full asset management including disposal — Accountant and above."""
    return user.role in (
        UserRole.ACCOUNTANT, UserRole.SENIOR_ACCOUNTANT,
        UserRole.FINANCE_DIRECTOR, UserRole.CEO,
        UserRole.ADMIN_DIRECTOR, UserRole.MEDICAL_DIRECTOR,
        UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_view_variance_register(user):
    """Variance register — Chief Cashier, Accountant and above."""
    return user.role in (
        UserRole.CHIEF_CASHIER, UserRole.ACCOUNTANT,
        UserRole.SENIOR_ACCOUNTANT, UserRole.FINANCE_DIRECTOR,
        UserRole.BILLING_OFFICER, UserRole.CEO,
        UserRole.ADMIN_DIRECTOR, UserRole.MEDICAL_DIRECTOR,
        UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_request_advance(user):
    """Any staff member can request an advance."""
    return user.is_authenticated


# ═══════════════════════════════════════════════════════════════════════════════
# BANK ACCOUNT MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def bank_account_list(request):
    if not _can_manage_bank(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    accounts = BankAccount.objects.filter(is_deleted=False)
    return render(request, 'billing/bank_account_list.html', {'accounts': accounts})


@login_required
def bank_account_create(request):
    if not _can_manage_bank(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    gl_accounts = GLAccount.objects.filter(
        code__startswith='521', is_deleted=False
    ).order_by('code')
    if request.method == 'POST':
        acct = BankAccount(
            account_name=request.POST.get('account_name', '').strip(),
            bank_name=request.POST.get('bank_name', '').strip(),
            account_number=request.POST.get('account_number', '').strip(),
            branch=request.POST.get('branch', '').strip(),
            swift_code=request.POST.get('swift_code', '').strip(),
            currency=request.POST.get('currency', 'XAF').strip(),
            opening_balance=Decimal(request.POST.get('opening_balance', '0') or '0'),
            notes=request.POST.get('notes', '').strip(),
        )
        gl_id = request.POST.get('gl_account')
        if gl_id:
            acct.gl_account_id = gl_id
        acct.save()
        messages.success(request, f'Bank account "{acct.account_name}" created.')
        return redirect('billing:bank_account_list')
    return render(request, 'billing/bank_account_form.html', {
        'gl_accounts': gl_accounts, 'editing': False,
    })


@login_required
def bank_account_edit(request, account_id):
    if not _can_manage_bank(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    acct = get_object_or_404(BankAccount, pk=account_id, is_deleted=False)
    gl_accounts = GLAccount.objects.filter(
        code__startswith='521', is_deleted=False
    ).order_by('code')
    if request.method == 'POST':
        acct.account_name = request.POST.get('account_name', '').strip()
        acct.bank_name = request.POST.get('bank_name', '').strip()
        acct.account_number = request.POST.get('account_number', '').strip()
        acct.branch = request.POST.get('branch', '').strip()
        acct.swift_code = request.POST.get('swift_code', '').strip()
        acct.currency = request.POST.get('currency', 'XAF').strip()
        acct.opening_balance = Decimal(request.POST.get('opening_balance', '0') or '0')
        acct.notes = request.POST.get('notes', '').strip()
        acct.is_active = 'is_active' in request.POST
        gl_id = request.POST.get('gl_account')
        acct.gl_account_id = gl_id if gl_id else None
        acct.save()
        messages.success(request, f'Bank account "{acct.account_name}" updated.')
        return redirect('billing:bank_account_list')
    return render(request, 'billing/bank_account_form.html', {
        'account': acct, 'gl_accounts': gl_accounts, 'editing': True,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# BANK STATEMENT IMPORT
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def bank_statement_import(request):
    if not _can_do_reconciliation(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    bank_accounts = BankAccount.objects.filter(is_deleted=False, is_active=True)
    if request.method == 'POST':
        bank_id = request.POST.get('bank_account')
        bank_acct = get_object_or_404(BankAccount, pk=bank_id, is_deleted=False)
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            messages.error(request, 'Please upload a CSV file.')
            return redirect('billing:bank_statement_import')
        import csv, io
        decoded = csv_file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(decoded))
        count = 0
        skipped = 0
        for row in reader:
            try:
                BankStatement.objects.create(
                    bank_account=bank_acct,
                    statement_date=row.get('date', '').strip(),
                    reference=row.get('reference', '').strip(),
                    description=row.get('description', '').strip(),
                    debit_amount=Decimal(row.get('debit', '0').replace(',', '') or '0'),
                    credit_amount=Decimal(row.get('credit', '0').replace(',', '') or '0'),
                    balance=Decimal(row.get('balance', '0').replace(',', '') or '0'),
                    value_date=row.get('value_date', '').strip() or None,
                )
                count += 1
            except Exception as e:
                skipped += 1
                logger.warning(f"Skipped bank statement row: {e}")
                continue
        msg = f'{count} statement lines imported for {bank_acct}.'
        if skipped:
            msg += f' ({skipped} rows skipped due to errors.)'
        messages.success(request, msg)
        return redirect('billing:bank_reconciliation_list')
    return render(request, 'billing/bank_statement_import.html', {
        'bank_accounts': bank_accounts,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# BANK RECONCILIATION
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def bank_reconciliation_list(request):
    if not _can_do_reconciliation(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    recons = BankReconciliation.objects.filter(is_deleted=False).select_related(
        'bank_account', 'prepared_by', 'reviewed_by'
    )
    return render(request, 'billing/bank_reconciliation_list.html', {'recons': recons})


@login_required
def bank_reconciliation_create(request):
    if not _can_do_reconciliation(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    bank_accounts = BankAccount.objects.filter(is_deleted=False, is_active=True)
    if request.method == 'POST':
        recon = BankReconciliation(
            bank_account_id=request.POST.get('bank_account'),
            period_start=request.POST.get('period_start'),
            period_end=request.POST.get('period_end'),
            bank_statement_balance=Decimal(request.POST.get('bank_statement_balance', '0') or '0'),
            book_balance=Decimal(request.POST.get('book_balance', '0') or '0'),
            prepared_by=request.user,
            notes=request.POST.get('notes', '').strip(),
        )
        recon.save()
        messages.success(request, 'Bank reconciliation created.')
        return redirect('billing:bank_reconciliation_detail', recon_id=recon.pk)
    return render(request, 'billing/bank_reconciliation_form.html', {
        'bank_accounts': bank_accounts,
    })


@login_required
def bank_reconciliation_detail(request, recon_id):
    if not _can_do_reconciliation(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    recon = get_object_or_404(BankReconciliation, pk=recon_id, is_deleted=False)
    items = recon.items.all()

    if request.method == 'POST' and recon.status == BankReconciliationStatus.DRAFT:
        # Add reconciling item
        BankReconciliationItem.objects.create(
            reconciliation=recon,
            item_type=request.POST.get('item_type'),
            date=request.POST.get('date'),
            reference=request.POST.get('reference', '').strip(),
            description=request.POST.get('description', '').strip(),
            amount=Decimal(request.POST.get('amount', '0') or '0'),
            side=request.POST.get('side', 'BANK'),
        )
        # Recalculate adjusted balances
        bank_adj = sum(i.amount for i in recon.items.filter(side='BANK'))
        book_adj = sum(i.amount for i in recon.items.filter(side='BOOK'))
        recon.adjusted_bank_balance = recon.bank_statement_balance - bank_adj
        recon.adjusted_book_balance = recon.book_balance + book_adj
        recon.save()
        messages.success(request, 'Reconciling item added.')
        return redirect('billing:bank_reconciliation_detail', recon_id=recon.pk)

    bank_adj = sum(i.amount for i in items.filter(side='BANK'))
    book_adj = sum(i.amount for i in items.filter(side='BOOK'))
    return render(request, 'billing/bank_reconciliation_detail.html', {
        'recon': recon, 'items': items,
        'bank_adj': bank_adj, 'book_adj': book_adj,
        'item_types': ReconciliationItemType.choices,
    })


@login_required
@require_POST
def bank_reconciliation_complete(request, recon_id):
    if not _can_do_reconciliation(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    recon = get_object_or_404(BankReconciliation, pk=recon_id, is_deleted=False)
    if recon.status == BankReconciliationStatus.DRAFT:
        recon.status = BankReconciliationStatus.COMPLETED
        recon.save()
        messages.success(request, 'Reconciliation marked as completed.')
    return redirect('billing:bank_reconciliation_detail', recon_id=recon.pk)


@login_required
@require_POST
def bank_reconciliation_review(request, recon_id):
    """Finance Manager reviews and approves the reconciliation."""
    if not (request.user.role in (UserRole.FINANCE_DIRECTOR, UserRole.SUPER_ADMIN) or request.user.is_superuser):
        messages.error(request, 'Only Finance Manager can review reconciliations.')
        return redirect('billing:dashboard')
    recon = get_object_or_404(BankReconciliation, pk=recon_id, is_deleted=False)
    if recon.status == BankReconciliationStatus.COMPLETED:
        recon.status = BankReconciliationStatus.REVIEWED
        recon.reviewed_by = request.user
        recon.reviewed_at = timezone.now()
        recon.save()
        messages.success(request, 'Reconciliation reviewed and approved.')
    return redirect('billing:bank_reconciliation_detail', recon_id=recon.pk)


# ═══════════════════════════════════════════════════════════════════════════════
# CASH-TO-BANK DEPOSITS
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def cash_to_bank_list(request):
    if not _can_manage_cash_transfers(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    deposits = CashToBank.objects.filter(is_deleted=False).select_related(
        'bank_account', 'prepared_by', 'confirmed_by'
    )
    return render(request, 'billing/cash_to_bank_list.html', {'deposits': deposits})


@login_required
def cash_to_bank_create(request):
    if not _can_manage_cash_transfers(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    bank_accounts = BankAccount.objects.filter(is_deleted=False, is_active=True)
    if request.method == 'POST':
        dep = CashToBank(
            bank_account_id=request.POST.get('bank_account'),
            deposit_date=request.POST.get('deposit_date'),
            amount=Decimal(request.POST.get('amount', '0') or '0'),
            reference=request.POST.get('reference', '').strip(),
            prepared_by=request.user,
            notes=request.POST.get('notes', '').strip(),
        )
        dep.save()
        messages.success(request, f'Deposit of {dep.amount:,.0f} XAF recorded.')
        return redirect('billing:cash_to_bank_list')
    return render(request, 'billing/cash_to_bank_form.html', {
        'bank_accounts': bank_accounts,
        'today': timezone.localdate(),
    })


@login_required
@require_POST
def cash_to_bank_confirm(request, deposit_id):
    """Accountant confirms deposit was received at bank."""
    if not _can_manage_bank(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    dep = get_object_or_404(CashToBank, pk=deposit_id, is_deleted=False)
    if dep.status != CashToBankStatus.CONFIRMED:
        dep.status = CashToBankStatus.CONFIRMED
        dep.confirmed_by = request.user
        dep.confirmed_at = timezone.now()
        dep.save()
        # GL posting: Dr Bank / Cr Cash
        try:
            from apps.billing.gl_service import post_cash_to_bank
            post_cash_to_bank(dep, request.user)
        except Exception:
            logger.exception(f"GL post failed for cash-to-bank deposit {dep.pk}")
        messages.success(request, 'Deposit confirmed.')
    return redirect('billing:cash_to_bank_list')


# ═══════════════════════════════════════════════════════════════════════════════
# CHEQUE BOOK MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def chequebook_list(request):
    if not _can_manage_cheques(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    books = ChequeBook.objects.filter(is_deleted=False).select_related('bank_account')
    return render(request, 'billing/chequebook_list.html', {'books': books})


@login_required
def chequebook_create(request):
    if not _can_manage_cheques(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    bank_accounts = BankAccount.objects.filter(is_deleted=False, is_active=True)
    if request.method == 'POST':
        start = int(request.POST.get('start_number', 0))
        end = int(request.POST.get('end_number', 0))
        book = ChequeBook(
            bank_account_id=request.POST.get('bank_account'),
            series_prefix=request.POST.get('series_prefix', '').strip(),
            start_number=start,
            end_number=end,
            current_number=start,
            received_date=request.POST.get('received_date'),
            notes=request.POST.get('notes', '').strip(),
        )
        book.save()
        messages.success(request, f'Cheque book #{start}-{end} created.')
        return redirect('billing:chequebook_list')
    return render(request, 'billing/chequebook_form.html', {
        'bank_accounts': bank_accounts,
        'today': timezone.localdate(),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# CHEQUE REGISTER
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def cheque_register(request):
    if not _can_manage_cheques(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    cheques = ChequeRegister.objects.filter(is_deleted=False).select_related(
        'cheque_book', 'bank_account', 'issued_by'
    )[:200]
    return render(request, 'billing/cheque_register.html', {'cheques': cheques})


@login_required
def cheque_issue(request):
    if not _can_manage_cheques(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    books = ChequeBook.objects.filter(is_deleted=False, is_exhausted=False).select_related('bank_account')
    if request.method == 'POST':
        from django.db import transaction
        book_id = request.POST.get('cheque_book')
        book = get_object_or_404(ChequeBook, pk=book_id, is_deleted=False)
        with transaction.atomic():
            # Lock the cheque book row to prevent duplicate numbers
            book = ChequeBook.objects.select_for_update().get(pk=book.pk)
            cheque_number = str(book.current_number)
            if book.series_prefix:
                cheque_number = f"{book.series_prefix}{cheque_number}"
            chq = ChequeRegister(
                cheque_book=book,
                cheque_number=cheque_number,
                bank_account=book.bank_account,
                payee=request.POST.get('payee', '').strip(),
                amount=Decimal(request.POST.get('amount', '0') or '0'),
                issue_date=request.POST.get('issue_date'),
                reason=request.POST.get('reason', '').strip(),
                issued_by=request.user,
            )
            chq.save()
            # Advance cheque book counter
            book.current_number += 1
            if book.current_number > book.end_number:
                book.is_exhausted = True
            book.save()
        messages.success(request, f'Cheque #{cheque_number} issued to {chq.payee}.')
        return redirect('billing:cheque_register')
    return render(request, 'billing/cheque_issue.html', {
        'books': books, 'today': timezone.localdate(),
    })


@login_required
@require_POST
def cheque_void(request, cheque_id):
    if not _can_manage_cheques(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    chq = get_object_or_404(ChequeRegister, pk=cheque_id, is_deleted=False)
    if chq.status == ChequeStatus.ISSUED:
        chq.status = ChequeStatus.VOIDED
        chq.voided_by = request.user
        chq.voided_at = timezone.now()
        chq.reason = request.POST.get('reason', chq.reason)
        chq.save()
        messages.success(request, f'Cheque #{chq.cheque_number} voided.')
    return redirect('billing:cheque_register')


@login_required
@require_POST
def cheque_clear(request, cheque_id):
    if not _can_manage_cheques(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    chq = get_object_or_404(ChequeRegister, pk=cheque_id, is_deleted=False)
    if chq.status == ChequeStatus.ISSUED:
        chq.status = ChequeStatus.CLEARED
        chq.cleared_date = request.POST.get('cleared_date') or timezone.localdate()
        chq.save()
        messages.success(request, f'Cheque #{chq.cheque_number} marked as cleared.')
    return redirect('billing:cheque_register')


# ═══════════════════════════════════════════════════════════════════════════════
# STAFF ADVANCES (Salary & Business)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def advance_list(request):
    """View advances — staff sees own, managers see all."""
    user = request.user
    if _can_manage_advances(user):
        advances = StaffAdvance.objects.filter(is_deleted=False).select_related('staff', 'approved_by')
    else:
        advances = StaffAdvance.objects.filter(staff=user, is_deleted=False)
    return render(request, 'billing/advance_list.html', {
        'advances': advances,
        'can_approve': _can_manage_advances(user),
    })


@login_required
def advance_request(request):
    if request.method == 'POST':
        adv = StaffAdvance(
            staff=request.user,
            advance_type=request.POST.get('advance_type', AdvanceType.SALARY),
            amount_requested=Decimal(request.POST.get('amount_requested', '0') or '0'),
            purpose=request.POST.get('purpose', '').strip(),
        )
        # Business advance: check no outstanding
        if adv.advance_type == AdvanceType.BUSINESS:
            outstanding = StaffAdvance.objects.filter(
                staff=request.user, advance_type=AdvanceType.BUSINESS,
                status__in=[AdvanceStatus.REQUESTED, AdvanceStatus.APPROVED, AdvanceStatus.DISBURSED],
                is_deleted=False,
            ).exists()
            if outstanding:
                messages.error(request, 'You already have an outstanding business advance. Settle it first.')
                return redirect('billing:advance_list')
        adv.save()
        messages.success(request, 'Advance request submitted.')
        return redirect('billing:advance_list')
    return render(request, 'billing/advance_form.html', {
        'advance_types': AdvanceType.choices,
    })


@login_required
def advance_detail(request, advance_id):
    adv = get_object_or_404(StaffAdvance, pk=advance_id, is_deleted=False)
    # Staff can see own, managers can see all
    if adv.staff != request.user and not _can_manage_advances(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:advance_list')
    return render(request, 'billing/advance_detail.html', {
        'advance': adv,
        'can_approve': _can_manage_advances(request.user),
    })


@login_required
@require_POST
def advance_approve(request, advance_id):
    if not _can_manage_advances(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    adv = get_object_or_404(StaffAdvance, pk=advance_id, is_deleted=False)
    if adv.status == AdvanceStatus.REQUESTED:
        adv.status = AdvanceStatus.APPROVED
        adv.amount_approved = Decimal(request.POST.get('amount_approved', '0') or '0') or adv.amount_requested
        adv.approved_by = request.user
        adv.approved_at = timezone.now()
        adv.save()
        messages.success(request, f'Advance approved for {adv.amount_approved:,.0f} XAF.')
    return redirect('billing:advance_detail', advance_id=adv.pk)


@login_required
@require_POST
def advance_reject(request, advance_id):
    if not _can_manage_advances(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    adv = get_object_or_404(StaffAdvance, pk=advance_id, is_deleted=False)
    if adv.status == AdvanceStatus.REQUESTED:
        adv.status = AdvanceStatus.REJECTED
        adv.notes = request.POST.get('notes', '')
        adv.approved_by = request.user
        adv.approved_at = timezone.now()
        adv.save()
        messages.success(request, 'Advance request rejected.')
    return redirect('billing:advance_list')


@login_required
@require_POST
def advance_disburse(request, advance_id):
    if not _can_manage_cash_transfers(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    adv = get_object_or_404(StaffAdvance, pk=advance_id, is_deleted=False)
    if adv.status == AdvanceStatus.APPROVED:
        from datetime import timedelta
        adv.status = AdvanceStatus.DISBURSED
        adv.disbursed_date = timezone.localdate()
        adv.payment_method = request.POST.get('payment_method', PaymentMethod.CASH)
        adv.reference = request.POST.get('reference', '').strip()
        if adv.advance_type == AdvanceType.BUSINESS:
            adv.settlement_due = adv.disbursed_date + timedelta(days=5)
        adv.save()
        # GL posting: Dr Staff Advance / Cr Cash or Bank
        try:
            from apps.billing.gl_service import post_advance_disbursement
            post_advance_disbursement(adv, request.user)
        except Exception:
            logger.exception(f"GL post failed for advance disburse {adv.pk}")
        messages.success(request, f'Advance disbursed to {adv.staff.get_full_name()}.')
    return redirect('billing:advance_detail', advance_id=adv.pk)


@login_required
@require_POST
def advance_settle(request, advance_id):
    if not _can_manage_advances(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    adv = get_object_or_404(StaffAdvance, pk=advance_id, is_deleted=False)
    if adv.status == AdvanceStatus.DISBURSED:
        adv.status = AdvanceStatus.SETTLED
        adv.settled_date = timezone.localdate()
        adv.notes = request.POST.get('settlement_notes', adv.notes)
        adv.save()
        # GL posting: Dr Cash / Cr Staff Advance
        try:
            from apps.billing.gl_service import post_advance_settlement
            post_advance_settlement(adv, request.user)
        except Exception:
            logger.exception(f"GL post failed for advance settle {adv.pk}")
        messages.success(request, f'Advance settled for {adv.staff.get_full_name()}.')
    return redirect('billing:advance_list')


# ═══════════════════════════════════════════════════════════════════════════════
# CASH TRANSFERS (Desk → Safe, Safe → Bank, Desk → Desk, Float Issue)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def cash_transfer_list(request):
    if not _can_manage_cash_transfers(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    transfers = CashTransfer.objects.filter(is_deleted=False).select_related(
        'from_desk', 'to_desk', 'initiated_by', 'confirmed_by'
    )[:200]
    return render(request, 'billing/cash_transfer_list.html', {'transfers': transfers})


@login_required
def cash_transfer_create(request):
    if not _can_manage_cash_transfers(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    desks = CashDesk.objects.filter(is_deleted=False, is_active=True)

    # Auto-detect cashier's current open session desk for pre-fill
    my_desk = None
    if request.user.role == UserRole.CASHIER:
        open_session = CashierSession.objects.filter(
            cashier=request.user, closed_at__isnull=True, is_deleted=False
        ).select_related('cash_desk').first()
        if open_session:
            my_desk = open_session.cash_desk

    if request.method == 'POST':
        xfer = CashTransfer(
            transfer_type=request.POST.get('transfer_type'),
            amount=Decimal(request.POST.get('amount', '0') or '0'),
            initiated_by=request.user,
            reference=request.POST.get('reference', '').strip(),
            notes=request.POST.get('notes', '').strip(),
        )
        from_desk_id = request.POST.get('from_desk')
        to_desk_id = request.POST.get('to_desk')
        if from_desk_id:
            xfer.from_desk_id = from_desk_id
        if to_desk_id:
            xfer.to_desk_id = to_desk_id
        xfer.save()
        messages.success(request, f'Cash transfer of {xfer.amount:,.0f} XAF recorded.')
        return redirect('billing:cash_transfer_list')

    # Default type for cashiers is Desk → Head Teller
    default_type = TransferType.DESK_TO_TELLER if request.user.role == UserRole.CASHIER else ''
    return render(request, 'billing/cash_transfer_form.html', {
        'desks': desks,
        'transfer_types': TransferType.choices,
        'my_desk': my_desk,
        'default_type': default_type,
        'is_cashier': request.user.role == UserRole.CASHIER,
    })


@login_required
@require_POST
def cash_transfer_confirm(request, transfer_id):
    if not _can_manage_safe(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    xfer = get_object_or_404(CashTransfer, pk=transfer_id, is_deleted=False)
    if xfer.status == TransferStatus.PENDING:
        xfer.status = TransferStatus.CONFIRMED
        xfer.confirmed_by = request.user
        xfer.confirmed_at = timezone.now()
        xfer.save()

        # GL: post cash transfer journal entry
        from apps.billing import gl_service
        gl_service.post_cash_transfer(xfer, user=request.user)

        messages.success(request, 'Cash transfer confirmed.')
    return redirect('billing:cash_transfer_list')


# ═══════════════════════════════════════════════════════════════════════════════
# SAFE BALANCE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def safe_balance_list(request):
    if not _can_manage_safe(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    balances = SafeBalance.objects.filter(is_deleted=False)[:90]
    return render(request, 'billing/safe_balance_list.html', {'balances': balances})


@login_required
def safe_balance_record(request):
    if not _can_manage_safe(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    if request.method == 'POST':
        sb = SafeBalance(
            date=request.POST.get('date'),
            opening_balance=Decimal(request.POST.get('opening_balance', '0') or '0'),
            total_deposits=Decimal(request.POST.get('total_deposits', '0') or '0'),
            total_withdrawals=Decimal(request.POST.get('total_withdrawals', '0') or '0'),
            closing_balance=Decimal(request.POST.get('closing_balance', '0') or '0'),
            counted_by=request.user,
            notes=request.POST.get('notes', '').strip(),
        )
        sb.save()
        if sb.exceeds_limit:
            messages.warning(
                request,
                f'WARNING: Safe closing balance ({sb.closing_balance:,.0f} XAF) exceeds '
                f'the {SafeBalance.SAFE_MAX_BALANCE:,.0f} XAF policy limit! Arrange bank deposit immediately.'
            )
        else:
            messages.success(request, f'Safe balance for {sb.date} recorded.')
        return redirect('billing:safe_balance_list')
    # Pre-fill opening from previous day's closing
    last = SafeBalance.objects.filter(is_deleted=False).first()
    return render(request, 'billing/safe_balance_form.html', {
        'today': timezone.localdate(),
        'last_closing': last.closing_balance if last else 0,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# CASH VARIANCE REGISTER
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def variance_register(request):
    if not _can_view_variance_register(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    variances = CashVarianceRegister.objects.filter(is_deleted=False).select_related(
        'cashier', 'resolved_by'
    )
    unresolved = variances.filter(is_resolved=False).count()
    return render(request, 'billing/variance_register.html', {
        'variances': variances[:200],
        'unresolved': unresolved,
    })


@login_required
@require_POST
def variance_resolve(request, variance_id):
    if not _can_manage_advances(request.user):  # Senior Accountant+ resolves
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    var = get_object_or_404(CashVarianceRegister, pk=variance_id, is_deleted=False)
    if not var.is_resolved:
        var.resolution = request.POST.get('resolution', '').strip()
        var.resolved_by = request.user
        var.resolved_at = timezone.now()
        var.is_resolved = True
        var.save()

        # GL: post cash variance entry (shortage or overage)
        from apps.billing import gl_service
        gl_service.post_cash_variance(var, user=request.user)

        messages.success(request, f'Variance for {var.cashier.get_full_name()} resolved.')
    return redirect('billing:variance_register')


# ═══════════════════════════════════════════════════════════════════════════════
# ASSET DISPOSAL WORKFLOW
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def asset_disposal_list(request):
    if not _can_manage_assets_full(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    disposals = AssetDisposal.objects.filter(is_deleted=False).select_related(
        'asset', 'requested_by', 'approved_by'
    )
    return render(request, 'billing/asset_disposal_list.html', {'disposals': disposals})


@login_required
def asset_dispose(request, asset_id):
    if not _can_manage_assets_full(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    asset = get_object_or_404(AssetRegister, pk=asset_id, is_deleted=False)
    if request.method == 'POST':
        disp = AssetDisposal(
            asset=asset,
            disposal_method=request.POST.get('disposal_method'),
            reason=request.POST.get('reason', '').strip(),
            estimated_value=Decimal(request.POST.get('estimated_value', '0') or '0'),
            requested_by=request.user,
        )
        disp.save()
        messages.success(request, f'Disposal request for "{asset.name}" submitted.')
        return redirect('billing:asset_disposal_list')
    return render(request, 'billing/asset_disposal_form.html', {
        'asset': asset,
        'disposal_methods': DisposalMethod.choices,
    })


@login_required
@require_POST
def asset_disposal_approve(request, disposal_id):
    if not (request.user.role in (UserRole.FINANCE_DIRECTOR, UserRole.ADMIN_DIRECTOR, UserRole.SUPER_ADMIN) or request.user.is_superuser):
        messages.error(request, 'Only Finance Director or Admin Director can approve disposals.')
        return redirect('billing:dashboard')
    disp = get_object_or_404(AssetDisposal, pk=disposal_id, is_deleted=False)
    action = request.POST.get('action', 'approve')
    if action == 'approve' and disp.status == DisposalStatus.REQUESTED:
        disp.status = DisposalStatus.APPROVED
        disp.approved_by = request.user
        disp.approved_at = timezone.now()
        disp.save()
        messages.success(request, f'Disposal of "{disp.asset.name}" approved.')
    elif action == 'reject' and disp.status == DisposalStatus.REQUESTED:
        disp.status = DisposalStatus.REJECTED
        disp.approved_by = request.user
        disp.approved_at = timezone.now()
        disp.notes = request.POST.get('notes', disp.notes)
        disp.save()
        messages.success(request, 'Disposal request rejected.')
    elif action == 'complete' and disp.status == DisposalStatus.APPROVED:
        disp.status = DisposalStatus.COMPLETED
        disp.disposal_date = timezone.localdate()
        disp.actual_proceeds = Decimal(request.POST.get('actual_proceeds', '0') or '0')
        disp.buyer_info = request.POST.get('buyer_info', '').strip()
        disp.save()
        # Update asset status
        asset = disp.asset
        asset.status = AssetStatus.DISPOSED
        asset.save()
        # GL posting: Dr Accum Depreciation + Cash / Cr Fixed Asset + Gain/Loss
        try:
            from apps.billing.gl_service import post_asset_disposal
            post_asset_disposal(disp, request.user)
        except Exception:
            logger.exception(f"GL post failed for asset disposal {disp.pk}")
        messages.success(request, f'Asset "{asset.name}" disposed and removed from register.')
    return redirect('billing:asset_disposal_list')


# ═══════════════════════════════════════════════════════════════════════════════
# BUDGET ANNUAL CREATE + YTD REPORT
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def budget_annual_create(request):
    if not _can_manage_bank(request.user):  # Senior Accountant+
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    from .models import ExpenseCategory
    if request.method == 'POST':
        fiscal_year = int(request.POST.get('fiscal_year', timezone.localdate().year))
        categories = request.POST.getlist('category[]')
        amounts = request.POST.getlist('annual_amount[]')
        created = 0
        for cat, amt in zip(categories, amounts):
            if not amt:
                continue
            annual = Decimal(amt)
            monthly = (annual / 12).quantize(Decimal('1'))
            for month in range(1, 13):
                Budget.objects.get_or_create(
                    budget_type=BudgetType.EXPENSE,
                    category=cat,
                    year=fiscal_year,
                    month=month,
                    defaults={'budgeted_amount': monthly, 'notes': 'Auto-created from annual budget wizard'},
                )
            created += 1
        messages.success(request, f'{created} annual budget lines created for FY {fiscal_year}.')
        return redirect('billing:budget_list')
    categories = ExpenseCategory.choices
    return render(request, 'billing/budget_annual_create.html', {
        'categories': categories,
        'current_year': timezone.localdate().year,
    })


@login_required
def budget_ytd_report(request):
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    year = int(request.GET.get('year', timezone.localdate().year))
    current_month = timezone.localdate().month if year == timezone.localdate().year else 12
    budgets = Budget.objects.filter(year=year, is_deleted=False).order_by('category', 'month')
    # Aggregate by category
    from collections import defaultdict
    cat_data = defaultdict(lambda: {'budget': Decimal('0'), 'actual': Decimal('0')})
    for b in budgets:
        if b.month <= current_month:
            cat_data[b.category]['budget'] += b.budgeted_amount
            if hasattr(b, 'actual_amount'):
                cat_data[b.category]['actual'] += (b.actual_amount or 0)
    # Calculate actual from expenses
    from .models import Expense
    expenses = (
        Expense.objects.filter(
            date__year=year, date__month__lte=current_month,
            is_deleted=False, approved_by__isnull=False,
        )
        .values('category')
        .annotate(total=Sum('amount'))
    )
    for exp in expenses:
        if exp['category'] in cat_data:
            cat_data[exp['category']]['actual'] = exp['total']
        else:
            cat_data[exp['category']] = {'budget': Decimal('0'), 'actual': exp['total']}

    rows = []
    for cat, data in sorted(cat_data.items()):
        variance = data['budget'] - data['actual']
        pct = (data['actual'] / data['budget'] * 100) if data['budget'] else 0
        rows.append({
            'category': cat,
            'budget': data['budget'],
            'actual': data['actual'],
            'variance': variance,
            'pct': round(pct, 1),
        })
    return render(request, 'billing/reports/budget_ytd.html', {
        'rows': rows, 'year': year, 'current_month': current_month,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# DAILY LIQUIDITY REPORT
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def report_daily_liquidity(request):
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    today = timezone.localdate()
    # Safe balance
    safe = SafeBalance.objects.filter(date=today, is_deleted=False).first()
    # Bank balances
    bank_accounts = BankAccount.objects.filter(is_deleted=False, is_active=True)
    bank_data = []
    for ba in bank_accounts:
        last_stmt = ba.statements.filter(is_deleted=False).order_by('-statement_date').first()
        bank_data.append({
            'account': ba,
            'last_balance': last_stmt.balance if last_stmt else ba.opening_balance,
            'last_date': last_stmt.statement_date if last_stmt else None,
        })
    # Outstanding cheques
    outstanding_cheques = ChequeRegister.objects.filter(
        status=ChequeStatus.ISSUED, is_deleted=False
    ).aggregate(total=Sum('amount'))['total'] or 0
    # Pending deposits
    pending_deposits = CashToBank.objects.filter(
        status__in=[CashToBankStatus.PENDING, CashToBankStatus.DEPOSITED],
        is_deleted=False,
    ).aggregate(total=Sum('amount'))['total'] or 0
    # Today's collections
    today_collections = Payment.objects.filter(
        payment_date__date=today, is_deleted=False
    ).aggregate(total=Sum('amount'))['total'] or 0

    total_bank = sum(b['last_balance'] for b in bank_data)
    safe_balance = safe.closing_balance if safe else 0
    total_liquidity = total_bank + safe_balance - outstanding_cheques

    return render(request, 'billing/reports/daily_liquidity.html', {
        'today': today,
        'safe': safe,
        'safe_balance': safe_balance,
        'bank_data': bank_data,
        'total_bank': total_bank,
        'outstanding_cheques': outstanding_cheques,
        'pending_deposits': pending_deposits,
        'today_collections': today_collections,
        'total_liquidity': total_liquidity,
        'safe_limit': SafeBalance.SAFE_MAX_BALANCE,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# SURGERY REVENUE ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def report_surgery_revenue(request):
    if not _can_view_pl(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    from django.db.models import Count
    from django.db.models.functions import TruncMonth
    df = request.GET.get('date_from', '')
    dt = request.GET.get('date_to', '')
    today = timezone.localdate()
    if not df:
        df = today.replace(day=1).isoformat()
    if not dt:
        dt = today.isoformat()

    items = InvoiceItem.objects.filter(
        invoice__is_deleted=False,
        invoice__status__in=[InvoiceStatus.PAID, InvoiceStatus.PARTIALLY_PAID],
        category=ServiceCategory.SURGICAL,
        is_deleted=False,
        invoice__created_at__date__gte=df,
        invoice__created_at__date__lte=dt,
    )

    # By service name
    by_service = (
        items.values('description')
        .annotate(count=Count('id'), total=Sum(F('quantity') * F('unit_price')))
        .order_by('-total')
    )

    # By month
    by_month = (
        items.annotate(month=TruncMonth('invoice__created_at'))
        .values('month')
        .annotate(total=Sum(F('quantity') * F('unit_price')), count=Count('id'))
        .order_by('month')
    )

    grand_total = items.aggregate(total=Sum(F('quantity') * F('unit_price')))['total'] or 0
    grand_count = items.count()

    return render(request, 'billing/reports/surgery_revenue.html', {
        'by_service': by_service,
        'by_month': by_month,
        'grand_total': grand_total,
        'grand_count': grand_count,
        'date_from': df,
        'date_to': dt,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# REVENUE BY DEPARTMENT
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def report_revenue_by_department(request):
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    from django.db.models import Count
    df = request.GET.get('date_from', '')
    dt = request.GET.get('date_to', '')
    today = timezone.localdate()
    if not df:
        df = today.replace(day=1).isoformat()
    if not dt:
        dt = today.isoformat()

    items = InvoiceItem.objects.filter(
        invoice__is_deleted=False,
        invoice__status__in=[InvoiceStatus.PAID, InvoiceStatus.PARTIALLY_PAID],
        is_deleted=False,
        invoice__created_at__date__gte=df,
        invoice__created_at__date__lte=dt,
    )

    by_dept = (
        items.values('category')
        .annotate(count=Count('id'), total=Sum(F('quantity') * F('unit_price')))
        .order_by('-total')
    )

    grand_total = items.aggregate(total=Sum(F('quantity') * F('unit_price')))['total'] or 0

    return render(request, 'billing/reports/revenue_by_department.html', {
        'by_dept': by_dept,
        'grand_total': grand_total,
        'date_from': df,
        'date_to': dt,
        'categories': ServiceCategory.choices,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# DONOR REPORT
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def report_donor(request):
    if not _can_view_pl(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    from .models import Expense, ExpenseCategory
    df = request.GET.get('date_from', '')
    dt = request.GET.get('date_to', '')
    today = timezone.localdate()
    if not df:
        df = today.replace(month=1, day=1).isoformat()
    if not dt:
        dt = today.isoformat()

    # Revenue
    revenue = Payment.objects.filter(
        payment_date__date__gte=df, payment_date__date__lte=dt,
        is_deleted=False,
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Expenses by category
    expenses = (
        Expense.objects.filter(
            date__gte=df, date__lte=dt, is_deleted=False, approved_by__isnull=False,
        )
        .values('category')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    total_expense = sum(e['total'] for e in expenses)

    # Budget comparison
    year = today.year
    budgets = Budget.objects.filter(year=year, is_deleted=False)
    total_budget = budgets.aggregate(total=Sum('budgeted_amount'))['total'] or 0

    return render(request, 'billing/reports/donor_report.html', {
        'revenue': revenue,
        'expenses': expenses,
        'total_expense': total_expense,
        'total_budget': total_budget,
        'budget_utilization': round(total_expense / total_budget * 100, 1) if total_budget else 0,
        'net_position': revenue - total_expense,
        'date_from': df,
        'date_to': dt,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# DSF — Declaration Statistique et Fiscale (Cameroon annual tax return)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def report_dsf(request):
    if not _can_view_pl(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    from .models import Expense
    year = int(request.GET.get('year', timezone.localdate().year))

    # Total revenue
    revenue = Payment.objects.filter(
        payment_date__year=year, is_deleted=False,
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Expenses by category
    expenses = (
        Expense.objects.filter(
            date__year=year, is_deleted=False, approved_by__isnull=False,
        )
        .values('category')
        .annotate(total=Sum('amount'))
        .order_by('category')
    )
    total_expense = sum(e['total'] for e in expenses)

    # Asset depreciation
    assets = AssetRegister.objects.filter(is_deleted=False, status=AssetStatus.ACTIVE)
    total_depreciation = sum(a.annual_depreciation for a in assets)

    # GL summary by OHADA class
    from .models import JournalLine
    from django.db.models.functions import Left
    gl_summary = (
        JournalLine.objects.filter(
            entry__entry_date__year=year, entry__is_deleted=False,
        )
        .annotate(acct_class=Left('account__code', 1))
        .values('acct_class')
        .annotate(total_dr=Sum('debit_amount'), total_cr=Sum('credit_amount'))
        .order_by('acct_class')
    )

    return render(request, 'billing/reports/dsf.html', {
        'year': year,
        'revenue': revenue,
        'expenses': expenses,
        'total_expense': total_expense,
        'total_depreciation': total_depreciation,
        'net_result': revenue - total_expense,
        'gl_summary': gl_summary,
        'asset_count': assets.count(),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# AP AGING REPORT  —  Accounts Payable Aging by Vendor
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def report_ap_aging(request):
    """Accounts Payable aging — outstanding vendor bills by age bucket."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    today = timezone.localdate()
    bills = APBill.objects.filter(
        is_deleted=False,
        status__in=[APBillStatus.PENDING, APBillStatus.PARTIAL, APBillStatus.OVERDUE],
    ).select_related('vendor').order_by('due_date')

    rows = []
    totals = {'current': Decimal('0'), 'days_30': Decimal('0'), 'days_60': Decimal('0'),
              'days_90': Decimal('0'), 'over_90': Decimal('0'), 'total': Decimal('0')}
    for bill in bills:
        balance = bill.balance_due
        if balance <= 0:
            continue
        due = bill.due_date or bill.bill_date
        age = (today - due).days
        bucket = 'current'
        if age > 90:
            bucket = 'over_90'
        elif age > 60:
            bucket = 'days_90'
        elif age > 30:
            bucket = 'days_60'
        elif age > 0:
            bucket = 'days_30'
        rows.append({
            'bill': bill, 'vendor': bill.vendor.name, 'balance': balance,
            'due_date': due, 'age_days': max(age, 0), 'bucket': bucket,
        })
        totals[bucket] += balance
        totals['total'] += balance

    ctx_ap = {'rows': rows, 'totals': totals, 'today': today}
    fmt = request.GET.get('format')
    if fmt in ('csv', 'excel'):
        hdr = _hospital_header(f'AP Aging Report — as of {today}')
        cols = ['Vendor', 'Bill Ref', 'Due Date', 'Balance (FCFA)', 'Age (days)', 'Bucket']
        data = [cols] + [
            [r['vendor'], getattr(r['bill'], 'reference', ''), str(r['due_date']),
             f"{float(r['balance']):.0f}", r['age_days'], r['bucket'].replace('_', ' ')]
            for r in rows
        ]
        if fmt == 'csv':
            return _csv_response(f'ap_aging_{today}.csv', hdr, data)
        return _excel_response(f'ap_aging_{today}.xlsx', hdr, data, sheet_name='AP Aging')
    return render(request, 'billing/reports/ap_aging.html', ctx_ap)


# ═══════════════════════════════════════════════════════════════════════════════
# MONTHLY FINANCIAL SUMMARY  —  Period-end consolidated report
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def report_monthly_summary(request):
    """Monthly financial summary — revenue, expenses, net, with variance vs budget."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    import calendar
    today = timezone.localdate()
    year  = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))

    first_day = today.replace(year=year, month=month, day=1)
    last_day_num = calendar.monthrange(year, month)[1]
    last_day = first_day.replace(day=last_day_num)

    # Revenue
    revenue = Payment.objects.filter(
        is_deleted=False, payment_date__date__gte=first_day, payment_date__date__lte=last_day,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    # Revenue by payment method
    revenue_by_method = (
        Payment.objects.filter(
            is_deleted=False, payment_date__date__gte=first_day, payment_date__date__lte=last_day,
        ).values('payment_method').annotate(total=Sum('amount')).order_by('-total')
    )

    # Expenses by category
    from .models import Expense, ExpenseCategory
    expenses = (
        Expense.objects.filter(
            is_deleted=False, approved_by__isnull=False, date__gte=first_day, date__lte=last_day,
        ).values('category').annotate(total=Sum('amount')).order_by('category')
    )
    total_expense = sum(e['total'] for e in expenses)

    # Budget comparison
    budgets = Budget.objects.filter(
        is_deleted=False, month=month, year=year,
    )
    total_budget = budgets.aggregate(total=Sum('budgeted_amount'))['total'] or Decimal('0')

    # Invoice stats
    invoices_issued = Invoice.objects.filter(
        is_deleted=False, issue_date__gte=first_day, issue_date__lte=last_day,
    ).count()
    invoices_paid = Invoice.objects.filter(
        is_deleted=False, issue_date__gte=first_day, issue_date__lte=last_day,
        status=InvoiceStatus.PAID,
    ).count()

    # AP payments
    ap_paid = APPayment.objects.filter(
        is_deleted=False, payment_date__gte=first_day, payment_date__lte=last_day,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    net_position = revenue - total_expense - ap_paid

    from .models import PaymentMethod, ExpenseCategory
    ctx_ms = {
        'year': year, 'month': month,
        'month_name': calendar.month_name[month],
        'revenue': revenue,
        'revenue_by_method': revenue_by_method,
        'expenses': expenses,
        'total_expense': total_expense,
        'total_budget': total_budget,
        'budget_utilization': round(float(total_expense) / float(total_budget) * 100, 1) if total_budget else 0,
        'invoices_issued': invoices_issued,
        'invoices_paid': invoices_paid,
        'ap_paid': ap_paid,
        'net_position': net_position,
        'method_labels': dict(PaymentMethod.choices),
        'cat_labels': dict(ExpenseCategory.choices),
    }
    fmt = request.GET.get('format')
    if fmt in ('csv', 'excel'):
        label = f"{calendar.month_name[month]} {year}"
        hdr = _hospital_header(f'Monthly Financial Summary — {label}')
        cat_l = dict(ExpenseCategory.choices)
        rows = [['Description', 'Amount (FCFA)']]
        rows.append(['Total Revenue', f'{float(revenue):.0f}'])
        rows.append(['Total Expenses', f'{float(total_expense):.0f}'])
        rows.append(['Net Position', f'{float(net_position):.0f}'])
        rows.append(['', ''])
        rows.append(['Expenses by Category', ''])
        for e in expenses:
            rows.append([cat_l.get(e['category'], e['category']), f'{float(e["total"]):.0f}'])
        if fmt == 'csv':
            return _csv_response(f'monthly_summary_{year}_{month:02d}.csv', hdr, rows)
        return _excel_response(f'monthly_summary_{year}_{month:02d}.xlsx', hdr, rows, sheet_name='Monthly Summary')
    return render(request, 'billing/reports/monthly_summary.html', ctx_ms)


# ═══════════════════════════════════════════════════════════════════════════════
# TVA / VAT RETURN  —  Tax Report (Cameroon TVA at 19.25%)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def report_tva(request):
    """TVA (VAT) return — output tax on services vs input tax on purchases."""
    if not _can_view_pl(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    import calendar
    today = timezone.localdate()
    year  = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))

    first_day = today.replace(year=year, month=month, day=1)
    last_day_num = calendar.monthrange(year, month)[1]
    last_day = first_day.replace(day=last_day_num)

    TVA_RATE = Decimal('0.1925')  # Cameroon TVA = 19.25%

    # Output TVA — on revenue (services rendered)
    revenue = Payment.objects.filter(
        is_deleted=False, payment_date__date__gte=first_day, payment_date__date__lte=last_day,
    ).exclude(payment_method__in=('WAIVER',)).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    output_tva = (revenue * TVA_RATE / (1 + TVA_RATE)).quantize(Decimal('1'))

    # Input TVA — on purchases (AP bills with tax)
    input_tva = APBill.objects.filter(
        is_deleted=False, bill_date__gte=first_day, bill_date__lte=last_day,
    ).aggregate(total=Sum('tax_amount'))['total'] or Decimal('0')

    net_tva = output_tva - input_tva

    # Breakdown by service category
    revenue_by_cat = (
        Payment.objects.filter(
            is_deleted=False, payment_date__date__gte=first_day, payment_date__date__lte=last_day,
        ).exclude(payment_method__in=('WAIVER',))
        .values('invoice__items__category')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )

    return render(request, 'billing/reports/tva_return.html', {
        'year': year, 'month': month,
        'month_name': calendar.month_name[month],
        'tva_rate': '19.25',
        'revenue': revenue,
        'output_tva': output_tva,
        'input_tva': input_tva,
        'net_tva': net_tva,
        'revenue_by_cat': revenue_by_cat,
        'status': 'PAYABLE' if net_tva > 0 else 'CREDIT',
    })


# ═══════════════════════════════════════════════════════════════════════════════
# FINANCIAL AUDIT TRAIL  —  Who did what, when
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def report_audit_trail(request):
    """Financial audit trail — all journal entries with who posted, when, and why."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    from .models import JournalEntry
    today = timezone.localdate()
    date_from = request.GET.get('date_from', str(today.replace(day=1)))
    date_to   = request.GET.get('date_to', str(today))
    source    = request.GET.get('source', '')

    entries = JournalEntry.objects.filter(
        is_deleted=False,
        entry_date__gte=date_from,
        entry_date__lte=date_to,
    ).select_related('created_by').prefetch_related('lines__account').order_by('-entry_date', '-created_at')

    if source:
        entries = entries.filter(source_type=source)

    source_types = (
        JournalEntry.objects.filter(is_deleted=False)
        .values_list('source_type', flat=True).distinct().order_by('source_type')
    )

    return render(request, 'billing/reports/audit_trail.html', {
        'entries': entries[:200],
        'date_from': date_from,
        'date_to': date_to,
        'source': source,
        'source_types': source_types,
        'total_count': entries.count(),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# FISCAL PERIOD MANAGEMENT  —  Open / Close / Lock monthly periods
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def fiscal_period_list(request):
    """List all fiscal periods with status."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    import calendar as cal
    today = timezone.localdate()

    # Auto-create periods for current year if they don't exist
    for m in range(1, 13):
        FiscalPeriod.objects.get_or_create(year=today.year, month=m)

    periods = FiscalPeriod.objects.filter(
        is_deleted=False
    ).order_by('-year', '-month')[:36]  # 3 years

    return render(request, 'billing/fiscal_period_list.html', {
        'periods': periods,
    })


@login_required
@require_POST
def fiscal_period_action(request, period_id):
    """Close or reopen a fiscal period."""
    if not (request.user.role in (
        UserRole.SENIOR_ACCOUNTANT, UserRole.FINANCE_DIRECTOR, UserRole.SUPER_ADMIN,
    ) or request.user.is_superuser):
        messages.error(request, 'Access denied.')
        return redirect('billing:fiscal_period_list')

    period = get_object_or_404(FiscalPeriod, pk=period_id, is_deleted=False)
    action = request.POST.get('action')

    if action == 'close' and period.status == FiscalPeriodStatus.OPEN:
        period.status = FiscalPeriodStatus.CLOSED
        period.closed_by = request.user
        period.closed_at = timezone.now()
        period.save(update_fields=['status', 'closed_by', 'closed_at', 'updated_at'])
        messages.success(request, f"Period {period} closed successfully.")
    elif action == 'reopen' and period.status == FiscalPeriodStatus.CLOSED:
        if not (request.user.is_finance_director or request.user.is_super_admin):
            messages.error(request, "Only Finance Director can reopen a closed period.")
            return redirect('billing:fiscal_period_list')
        period.status = FiscalPeriodStatus.OPEN
        period.closed_by = None
        period.closed_at = None
        period.save(update_fields=['status', 'closed_by', 'closed_at', 'updated_at'])
        messages.success(request, f"Period {period} reopened.")
    elif action == 'lock' and period.status == FiscalPeriodStatus.CLOSED:
        if not (request.user.is_finance_director or request.user.is_super_admin):
            messages.error(request, "Only Finance Director can lock a period.")
            return redirect('billing:fiscal_period_list')
        period.status = FiscalPeriodStatus.LOCKED
        period.locked_by = request.user
        period.locked_at = timezone.now()
        period.save(update_fields=['status', 'locked_by', 'locked_at', 'updated_at'])
        messages.warning(request, f"Period {period} LOCKED permanently. No further changes allowed.")
    else:
        messages.error(request, "Invalid action for this period status.")

    return redirect('billing:fiscal_period_list')


# ═══════════════════════════════════════════════════════════════════════════════
# FINANCE DIRECTOR STRATEGIC DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def finance_director_dashboard(request):
    """Executive financial dashboard with KPIs, ratios, and trend charts."""
    if not _can_view_pl(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')

    today = timezone.localdate()
    first_of_month = today.replace(day=1)
    first_of_year = today.replace(month=1, day=1)

    # ── Revenue KPIs ──
    revenue_today = Payment.objects.filter(
        is_deleted=False, payment_date__date=today,
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    revenue_month = Payment.objects.filter(
        is_deleted=False, payment_date__date__gte=first_of_month,
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    revenue_ytd = Payment.objects.filter(
        is_deleted=False, payment_date__date__gte=first_of_year,
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    # ── Expense KPIs ──
    from .models import Expense
    expenses_month = Expense.objects.filter(
        is_deleted=False, approved_by__isnull=False, date__gte=first_of_month,
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    expenses_ytd = Expense.objects.filter(
        is_deleted=False, approved_by__isnull=False, date__gte=first_of_year,
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    # ── AR / AP totals ──
    ar_outstanding = Invoice.objects.filter(
        is_deleted=False, status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
    ).count()
    ar_total = Decimal('0')
    for inv in Invoice.objects.filter(
        is_deleted=False, status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
    ):
        ar_total += inv.balance_due

    ap_outstanding = APBill.objects.filter(
        is_deleted=False, status__in=[APBillStatus.PENDING, APBillStatus.PARTIAL, APBillStatus.OVERDUE],
    ).aggregate(total=Sum('amount_due'))['total'] or Decimal('0')
    ap_paid_total = APPayment.objects.filter(
        is_deleted=False,
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    # ── Financial Ratios ──
    # Current Ratio = Current Assets / Current Liabilities
    # Operating Margin = (Revenue - Expenses) / Revenue
    operating_margin = 0
    if revenue_ytd > 0:
        operating_margin = round(float(revenue_ytd - expenses_ytd) / float(revenue_ytd) * 100, 1)

    # ── Cash Position ──
    safe_latest = SafeBalance.objects.filter(is_deleted=False).order_by('-date').first()
    safe_balance = safe_latest.closing_balance if safe_latest else Decimal('0')

    bank_total = BankAccount.objects.filter(
        is_deleted=False, is_active=True,
    ).aggregate(t=Sum('opening_balance'))['t'] or Decimal('0')

    total_liquidity = safe_balance + bank_total

    # ── Monthly Revenue & Expense Trend (last 12 months) ──
    import calendar
    from django.db.models.functions import TruncMonth
    twelve_months_ago = first_of_year.replace(year=today.year - 1)
    monthly_revenue = (
        Payment.objects.filter(is_deleted=False, payment_date__date__gte=twelve_months_ago)
        .annotate(m=TruncMonth('payment_date'))
        .values('m')
        .annotate(total=Sum('amount'))
        .order_by('m')
    )
    monthly_expenses = dict(
        Expense.objects.filter(is_deleted=False, approved_by__isnull=False, date__gte=twelve_months_ago)
        .annotate(m=TruncMonth('date'))
        .values('m')
        .annotate(total=Sum('amount'))
        .order_by('m')
        .values_list('m', 'total')
    )
    trend_labels = []
    trend_data = []
    trend_expenses = []
    for row in monthly_revenue:
        dt = row['m']
        if hasattr(dt, 'date'):
            dt = dt.date()
        trend_labels.append(f"{calendar.month_abbr[dt.month]} {dt.year}")
        trend_data.append(float(row['total']))
        exp_val = monthly_expenses.get(row['m'], Decimal('0'))
        trend_expenses.append(float(exp_val))

    # ── Top 5 Revenue Categories (this month) ──
    from django.db.models import F, Count
    top_categories = list(
        InvoiceItem.objects.filter(
            is_deleted=False,
            invoice__is_deleted=False,
            invoice__status__in=[InvoiceStatus.PAID, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.ISSUED],
            invoice__created_at__date__gte=first_of_month,
        )
        .values('category')
        .annotate(total=Sum(F('quantity') * F('unit_price')))
        .order_by('-total')[:5]
    )
    cat_labels = [r['category'] or 'Uncategorized' for r in top_categories]
    cat_data = [float(r['total']) for r in top_categories]

    # ── Invoice counts by status (this month) ──
    inv_counts = dict(
        Invoice.objects.filter(is_deleted=False, created_at__date__gte=first_of_month)
        .values_list('status')
        .annotate(c=Count('id'))
        .values_list('status', 'c')
    )
    invoices_paid = inv_counts.get(InvoiceStatus.PAID, 0)
    invoices_partial = inv_counts.get(InvoiceStatus.PARTIALLY_PAID, 0)
    invoices_unpaid = inv_counts.get(InvoiceStatus.ISSUED, 0)
    invoices_void = inv_counts.get(InvoiceStatus.CANCELLED, 0) + inv_counts.get(InvoiceStatus.WAIVED, 0)

    # ── Collection Rate (billed vs collected this month) ──
    from django.db.models import F as _F
    billed_month = InvoiceItem.objects.filter(
        is_deleted=False, invoice__is_deleted=False, invoice__created_at__date__gte=first_of_month,
    ).aggregate(t=Sum(_F('quantity') * _F('unit_price')))['t'] or Decimal('0')
    collection_rate = 0
    if billed_month > 0:
        collection_rate = round(float(revenue_month) / float(billed_month) * 100, 1)

    # ── Revenue by Payment Method (this month) ──
    pay_method_data = list(
        Payment.objects.filter(is_deleted=False, payment_date__date__gte=first_of_month)
        .values('payment_method')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    pm_labels = [dict(PaymentMethod.choices).get(r['payment_method'], r['payment_method']) for r in pay_method_data]
    pm_data = [float(r['total']) for r in pay_method_data]

    # ── Budget vs Actual (current month) ──
    from .models import Budget, BudgetType
    budget_revenue = Budget.objects.filter(
        is_deleted=False, year=today.year, month=today.month, budget_type=BudgetType.REVENUE,
    ).aggregate(t=Sum('budgeted_amount'))['t'] or Decimal('0')
    budget_expense = Budget.objects.filter(
        is_deleted=False, year=today.year, month=today.month, budget_type=BudgetType.EXPENSE,
    ).aggregate(t=Sum('budgeted_amount'))['t'] or Decimal('0')
    rev_variance = revenue_month - budget_revenue
    exp_variance = expenses_month - budget_expense

    # ── Patient Volume (today + this month) ──
    from apps.patients.models import Visit
    visits_today = Visit.objects.filter(is_deleted=False, created_at__date=today).count()
    visits_month = Visit.objects.filter(is_deleted=False, created_at__date__gte=first_of_month).count()

    # ── Insurance Receivables by Scheme ──
    from apps.hmo.models import Claim, ClaimStatus
    insurance_receivables = list(
        Claim.objects.filter(
            is_deleted=False,
            status__in=[ClaimStatus.SUBMITTED, ClaimStatus.APPROVED, ClaimStatus.PARTIAL],
        )
        .values(scheme_name=F('member__scheme__name'))
        .annotate(owed=Sum(F('claimed_amount') - F('paid_amount')))
        .order_by('-owed')[:5]
    )
    insurance_total_owed = sum(r['owed'] for r in insurance_receivables) if insurance_receivables else Decimal('0')

    # ── Today's Cashier Desk Performance ──
    desk_performance = list(
        Payment.objects.filter(is_deleted=False, payment_date__date=today)
        .values(cashier=F('received_by__first_name'))
        .annotate(collected=Sum('amount'), txn_count=Count('id'))
        .order_by('-collected')[:6]
    )

    # ── Pending Approvals ──
    pending_expenses = Expense.objects.filter(
        is_deleted=False, approved_by__isnull=True,
    ).count()
    pending_advances = StaffAdvance.objects.filter(
        is_deleted=False, status=AdvanceStatus.REQUESTED,
    ).count()
    overdue_advances = StaffAdvance.objects.filter(
        is_deleted=False, status=AdvanceStatus.DISBURSED,
    ).exclude(settlement_due__isnull=True).filter(
        settlement_due__lt=today,
    ).count()
    unresolved_variances = CashVarianceRegister.objects.filter(
        is_deleted=False, is_resolved=False,
    ).count()

    # ── Unreconciled bank periods ──
    pending_reconciliations = BankReconciliation.objects.filter(
        is_deleted=False, status=BankReconciliationStatus.DRAFT,
    ).count()

    return render(request, 'billing/reports/finance_director_dashboard.html', {
        'revenue_today': revenue_today,
        'revenue_month': revenue_month,
        'revenue_ytd': revenue_ytd,
        'expenses_month': expenses_month,
        'expenses_ytd': expenses_ytd,
        'net_month': revenue_month - expenses_month,
        'net_ytd': revenue_ytd - expenses_ytd,
        'ar_outstanding': ar_outstanding,
        'ar_total': ar_total,
        'ap_outstanding': ap_outstanding,
        'operating_margin': operating_margin,
        'safe_balance': safe_balance,
        'bank_total': bank_total,
        'total_liquidity': total_liquidity,
        'trend_labels': json.dumps(trend_labels),
        'trend_data': json.dumps(trend_data),
        'trend_expenses': json.dumps(trend_expenses),
        'cat_labels': json.dumps(cat_labels),
        'cat_data': json.dumps(cat_data),
        'invoices_paid': invoices_paid,
        'invoices_partial': invoices_partial,
        'invoices_unpaid': invoices_unpaid,
        'invoices_void': invoices_void,
        'collection_rate': collection_rate,
        'billed_month': billed_month,
        'pm_labels': json.dumps(pm_labels),
        'pm_data': json.dumps(pm_data),
        'budget_revenue': budget_revenue,
        'budget_expense': budget_expense,
        'rev_variance': rev_variance,
        'exp_variance': exp_variance,
        'visits_today': visits_today,
        'visits_month': visits_month,
        'insurance_receivables': insurance_receivables,
        'insurance_total_owed': insurance_total_owed,
        'desk_performance': desk_performance,
        'pending_expenses': pending_expenses,
        'pending_advances': pending_advances,
        'overdue_advances': overdue_advances,
        'unresolved_variances': unresolved_variances,
        'pending_reconciliations': pending_reconciliations,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# SENIOR ACCOUNTANT DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def senior_accountant_dashboard(request):
    """Senior accountant operations dashboard — GL health, pending approvals, reconciliation status."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')

    today = timezone.localdate()
    first_of_month = today.replace(day=1)

    # ── Revenue / Expense KPIs ──
    revenue_today = Payment.objects.filter(
        is_deleted=False, payment_date__date=today,
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    revenue_month = Payment.objects.filter(
        is_deleted=False, payment_date__date__gte=first_of_month,
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    from .models import Expense
    expenses_month = Expense.objects.filter(
        is_deleted=False, approved_by__isnull=False, date__gte=first_of_month,
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    # ── AP summary ──
    ap_pending_count = APBill.objects.filter(
        is_deleted=False, status__in=[APBillStatus.PENDING, APBillStatus.PARTIAL],
    ).count()
    ap_pending_total = APBill.objects.filter(
        is_deleted=False, status__in=[APBillStatus.PENDING, APBillStatus.PARTIAL],
    ).aggregate(t=Sum('amount_due'))['t'] or Decimal('0')
    ap_overdue = APBill.objects.filter(
        is_deleted=False, status=APBillStatus.OVERDUE,
    ).count()

    # ── Reconciliation status ──
    draft_recons = BankReconciliation.objects.filter(
        is_deleted=False, status=BankReconciliationStatus.DRAFT,
    ).count()
    completed_recons = BankReconciliation.objects.filter(
        is_deleted=False, status=BankReconciliationStatus.COMPLETED,
    ).count()

    # ── GL Health ──
    from .models import JournalEntry
    unposted_entries = JournalEntry.objects.filter(
        is_deleted=False, is_posted=False,
    ).count()

    # ── Fiscal Periods ──
    open_periods = FiscalPeriod.objects.filter(
        is_deleted=False, status=FiscalPeriodStatus.OPEN,
    ).order_by('-year', '-month')[:3]

    # ── Pending items ──
    pending_expenses = Expense.objects.filter(
        is_deleted=False, approved_by__isnull=True,
    ).count()
    pending_advances = StaffAdvance.objects.filter(
        is_deleted=False, status=AdvanceStatus.REQUESTED,
    ).count()

    # ── Budget burn ──
    import calendar
    total_budget_month = Budget.objects.filter(
        is_deleted=False, year=today.year, month=today.month,
    ).aggregate(t=Sum('budgeted_amount'))['t'] or Decimal('0')
    budget_burn = round(float(expenses_month) / float(total_budget_month) * 100, 1) if total_budget_month else 0

    # ── Recent journal entries ──
    recent_entries = JournalEntry.objects.filter(
        is_deleted=False,
    ).select_related('created_by').order_by('-created_at')[:10]

    return render(request, 'billing/reports/senior_accountant_dashboard.html', {
        'revenue_today': revenue_today,
        'revenue_month': revenue_month,
        'expenses_month': expenses_month,
        'net_month': revenue_month - expenses_month,
        'ap_pending_count': ap_pending_count,
        'ap_pending_total': ap_pending_total,
        'ap_overdue': ap_overdue,
        'draft_recons': draft_recons,
        'completed_recons': completed_recons,
        'unposted_entries': unposted_entries,
        'open_periods': open_periods,
        'pending_expenses': pending_expenses,
        'pending_advances': pending_advances,
        'total_budget_month': total_budget_month,
        'budget_burn': budget_burn,
        'recent_entries': recent_entries,
    })


# ══════════════════════════════════════════════════════════════════════════════
# GL MAPPING SETTINGS — configurable account mapping (System Admin)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def gl_mapping_list(request):
    """GL Mapping settings page — view and edit all transaction-to-GL-account mappings."""
    if not request.user.is_super_admin:
        return HttpResponseForbidden('Super Admin access required.')

    from .models import GLMapping, GLMappingCategory, GLAccount

    # ── CSV export ─────────────────────────────────────────────────────────────
    if request.GET.get('export') == 'csv':
        import csv
        from django.http import HttpResponse as _HR
        from django.utils import timezone as _tz
        resp = _HR(content_type='text/csv')
        resp['Content-Disposition'] = f'attachment; filename="gl_mappings_{_tz.localdate()}.csv"'
        writer = csv.writer(resp)
        writer.writerow(['Category', 'Source Key', 'Description', 'GL Account Code', 'GL Account Name', 'Notes'])
        for m in GLMapping.objects.filter(is_active=True).select_related('gl_account').order_by('category', 'source_key'):
            writer.writerow([
                m.category,
                m.source_key,
                m.label,
                m.gl_account.code if m.gl_account else '',
                m.gl_account.name if m.gl_account else '',
                m.notes or '',
            ])
        return resp

    if request.method == 'POST':
        # Save all mapping changes
        mapping_ids = request.POST.getlist('mapping_id')
        for mid in mapping_ids:
            try:
                m = GLMapping.objects.get(pk=mid)
                new_account_id = request.POST.get(f'gl_account_{mid}')
                new_notes = request.POST.get(f'notes_{mid}', '').strip()
                if new_account_id:
                    m.gl_account_id = new_account_id
                m.notes = new_notes
                m.save(update_fields=['gl_account_id', 'notes', 'updated_at'])
            except (GLMapping.DoesNotExist, ValueError):
                continue
        messages.success(request, 'GL mappings updated successfully.')
        return redirect('billing:gl_mapping_list')

    mappings = GLMapping.objects.filter(is_active=True).select_related('gl_account').order_by('category', 'source_key')
    accounts = GLAccount.objects.filter(is_active=True).order_by('code')

    # Group by category for display
    grouped = {}
    for cat_val, cat_label in GLMappingCategory.choices:
        grouped[cat_val] = {
            'label': cat_label,
            'mappings': [m for m in mappings if m.category == cat_val],
        }

    return render(request, 'billing/gl_mapping_list.html', {
        'grouped': grouped,
        'accounts': accounts,
    })


@login_required
@require_POST
def gl_mapping_seed(request):
    """Seed/reset GL mappings from hardcoded defaults in gl_service.py."""
    if not request.user.is_super_admin:
        return HttpResponseForbidden('Super Admin access required.')

    from .models import GLMapping, GLMappingCategory, GLAccount

    DEFAULTS = [
        # Revenue mappings
        ('REVENUE', 'CONSULT',   'Consultations',           '701000'),
        ('REVENUE', 'CLINICAL',  'Clinical Exam',           '701000'),
        ('REVENUE', 'INVEST',    'Investigations',          '702000'),
        ('REVENUE', 'LAB',       'Laboratory',              '703000'),
        ('REVENUE', 'PHARMACY',  'Pharmacy Sales',          '704000'),
        ('REVENUE', 'OPTICAL',   'Optical Sales',           '705000'),
        ('REVENUE', 'SURGICAL',  'Surgical Procedures',     '706000'),
        ('REVENUE', 'ADMISSION', 'Inpatient Admissions',    '707000'),
        ('REVENUE', 'REG',       'Registration Fees',       '708000'),
        ('REVENUE', 'OTHER',     'Other Revenue',           '709000'),
        # Payment method mappings
        ('PAYMENT', 'CASH',      'Cash',                    '572000'),
        ('PAYMENT', 'CARD',      'POS / Card',              '521000'),
        ('PAYMENT', 'TRANSFER',  'Bank Transfer',           '521000'),
        ('PAYMENT', 'MOBILE',    'Mobile Money',            '521100'),
        ('PAYMENT', 'INSURANCE', 'Insurance',               '412000'),
        ('PAYMENT', 'NHIS',      'NHIS',                    '412000'),
        # Expense mappings
        ('EXPENSE', 'SUPPLIES',  'Supplies',                '602000'),
        ('EXPENSE', 'UTILITIES', 'Utilities',               '642000'),
        ('EXPENSE', 'SALARY',    'Salaries',                '621000'),
        ('EXPENSE', 'RENT',      'Rent',                    '641000'),
        ('EXPENSE', 'EQUIPMENT', 'Equipment',               '643000'),
        ('EXPENSE', 'DRUGS',     'Drug Purchases (COGS)',   '601000'),
        ('EXPENSE', 'TRANSPORT', 'Transport',               '653000'),
        ('EXPENSE', 'ADMIN',     'Administration',          '651000'),
        ('EXPENSE', 'MARKETING', 'Marketing',               '652000'),
        ('EXPENSE', 'EXP_OTHER', 'Other Expenses',          '658000'),
        # System accounts
        ('SYSTEM', 'CASH_ACCOUNT',       'Main Cash Drawer',            '572000'),
        ('SYSTEM', 'BANK_ACCOUNT',       'Bank Account',                '521000'),
        ('SYSTEM', 'MOBILE_MONEY',       'Mobile Money Account',        '521100'),
        ('SYSTEM', 'AR_PATIENT',         'Patient Accounts Receivable', '411000'),
        ('SYSTEM', 'AR_INSURANCE',       'Insurance Receivable',        '412000'),
        ('SYSTEM', 'AR_CORPORATE',       'Corporate Receivable',        '413000'),
        ('SYSTEM', 'AP_VENDORS',         'Accounts Payable (Suppliers)','401000'),
        ('SYSTEM', 'PATIENT_DEPOSITS',   'Patient Wallet / Deposits',   '499000'),
        ('SYSTEM', 'STAFF_ADVANCES',     'Staff Advances Receivable',   '421000'),
        ('SYSTEM', 'LOSS_ON_DISPOSAL',   'Loss on Asset Disposal',      '654000'),
        ('SYSTEM', 'GAIN_ON_DISPOSAL',   'Gain on Asset Disposal',      '754000'),
        ('SYSTEM', 'ACCUM_DEPRECIATION', 'Accumulated Depreciation',    '281000'),
        ('SYSTEM', 'FIXED_ASSETS',       'Fixed Assets (Equipment)',     '241000'),
    ]

    created = 0
    for cat, key, label, code in DEFAULTS:
        acct = GLAccount.objects.filter(code=code, is_active=True).first()
        if not acct:
            continue
        _, was_created = GLMapping.objects.update_or_create(
            category=cat, source_key=key,
            defaults={'label': label, 'gl_account': acct, 'is_active': True,
                      'created_by': request.user},
        )
        if was_created:
            created += 1

    messages.success(request, f'GL mappings seeded — {created} new, {len(DEFAULTS) - created} updated.')
    return redirect('billing:gl_mapping_list')


# ── Asset Maintenance ─────────────────────────────────────────────────────────

def _can_manage_maintenance(user):
    return user.is_superuser or user.role in (
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR, UserRole.FINANCE_DIRECTOR,
        UserRole.SENIOR_ACCOUNTANT,
    )


@login_required
def maintenance_list(request):
    if not _can_manage_maintenance(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from .models import MaintenanceWorkOrder, MaintenanceSchedule
    from django.utils import timezone as _tz
    today = _tz.now().date()
    wos = MaintenanceWorkOrder.objects.select_related('asset', 'performed_by').order_by('-created_at')
    overdue = MaintenanceSchedule.objects.filter(
        next_due__lt=today, is_active=True, is_deleted=False
    ).select_related('asset').count()
    status_filter = request.GET.get('status', '')
    if status_filter:
        wos = wos.filter(status=status_filter)
    from .models import MaintenanceStatus
    return render(request, 'billing/maintenance_list.html', {
        'wos': wos,
        'overdue_count': overdue,
        'status_filter': status_filter,
        'statuses': MaintenanceStatus.choices,
    })


@login_required
def maintenance_schedule_list(request):
    if not _can_manage_maintenance(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from .models import MaintenanceSchedule
    from django.utils import timezone as _tz
    today = _tz.now().date()
    schedules = MaintenanceSchedule.objects.filter(is_deleted=False).select_related('asset', 'assigned_to').order_by('next_due')
    return render(request, 'billing/maintenance_schedule_list.html', {
        'schedules': schedules,
        'today': today,
    })


@login_required
def maintenance_wo_create(request, asset_id):
    if not _can_manage_maintenance(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from .models import AssetRegister, MaintenanceSchedule, MaintenanceWorkOrder, MaintenanceType
    asset = get_object_or_404(AssetRegister, pk=asset_id)
    schedules = MaintenanceSchedule.objects.filter(asset=asset, is_active=True, is_deleted=False)
    if request.method == 'POST':
        mtype = request.POST.get('maintenance_type', 'PREVENTIVE')
        desc = request.POST.get('description', '').strip()
        est_cost = request.POST.get('estimated_cost', '0') or '0'
        schedule_id = request.POST.get('schedule_id') or None
        if not desc:
            messages.error(request, 'Description is required.')
        else:
            MaintenanceWorkOrder.objects.create(
                asset=asset,
                schedule_id=schedule_id,
                maintenance_type=mtype,
                description=desc,
                estimated_cost=est_cost,
                created_by=request.user,
            )
            messages.success(request, 'Work order created.')
            return redirect('billing:maintenance_list')
    return render(request, 'billing/maintenance_wo_form.html', {
        'asset': asset,
        'schedules': schedules,
        'maintenance_types': MaintenanceType.choices,
    })


@login_required
def maintenance_wo_complete(request, wo_id):
    if not _can_manage_maintenance(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:maintenance_list')
    from .models import MaintenanceWorkOrder, MaintenanceStatus
    from django.utils import timezone as _tz
    wo = get_object_or_404(MaintenanceWorkOrder, pk=wo_id)
    if request.method == 'POST':
        status = request.POST.get('status', 'DONE')
        actual_cost = request.POST.get('actual_cost', '0') or '0'
        findings = request.POST.get('findings', '').strip()
        parts_used = request.POST.get('parts_used', '').strip()
        wo.status = status
        wo.actual_cost = actual_cost
        wo.findings = findings
        wo.parts_used = parts_used
        wo.performed_by = request.user
        if status == 'DONE':
            wo.completed_at = _tz.now()
            # Update schedule last_done + next_due
            if wo.schedule:
                from dateutil.relativedelta import relativedelta
                sched = wo.schedule
                sched.last_done = _tz.now().date()
                freq_map = {
                    'MONTHLY': relativedelta(months=1),
                    'QUARTERLY': relativedelta(months=3),
                    'BIANNUAL': relativedelta(months=6),
                    'ANNUAL': relativedelta(years=1),
                    'AS_NEEDED': relativedelta(years=1),
                }
                sched.next_due = _tz.now().date() + freq_map.get(sched.frequency, relativedelta(years=1))
                sched.save()
        wo.save()
        messages.success(request, f'Work order {wo.wo_number} updated to {wo.get_status_display()}.')
    return redirect('billing:maintenance_list')


@login_required
def maintenance_schedule_create(request, asset_id):
    if not _can_manage_maintenance(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from .models import AssetRegister, MaintenanceSchedule, MaintenanceFrequency
    asset = get_object_or_404(AssetRegister, pk=asset_id)
    if request.method == 'POST':
        frequency = request.POST.get('frequency', 'ANNUAL')
        next_due = request.POST.get('next_due')
        desc = request.POST.get('description', '').strip()
        assigned_id = request.POST.get('assigned_to') or None
        MaintenanceSchedule.objects.create(
            asset=asset,
            frequency=frequency,
            next_due=next_due,
            description=desc,
            assigned_to_id=assigned_id,
        )
        messages.success(request, f'Maintenance schedule created for {asset.asset_name}.')
        return redirect('billing:maintenance_schedule_list')
    from apps.accounts.models import User
    staff = User.objects.filter(is_active=True, is_deleted=False).order_by('last_name')
    return render(request, 'billing/maintenance_schedule_form.html', {
        'asset': asset,
        'frequencies': MaintenanceFrequency.choices,
        'staff': staff,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Month-End Close
# ─────────────────────────────────────────────────────────────────────────────
_MONTH_END_TASKS = [
    'Verify all cashier sessions are closed and reconciled',
    'Confirm all bank deposits are recorded',
    'Complete bank reconciliation for all accounts',
    'Verify all outstanding cheques',
    'Post all manual journal entries',
    'Run monthly depreciation (DepreciationRun)',
    'Reconcile petty cash funds',
    'Confirm all AP bills are recorded',
    'Review and approve staff advances',
    'Reconcile AR aging — follow up overdue invoices',
    'Run payroll for the month',
    'Post CNPS contributions',
    'Post IRPP to DGI',
    'Review budget vs actual variances',
    'Prepare TVA return',
    'Lock fiscal period',
]


@login_required
def month_end_list(request):
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from .models import MonthEndClose
    closes = MonthEndClose.objects.prefetch_related('tasks').order_by('-period_year', '-period_month')
    return render(request, 'billing/month_end_list.html', {'closes': closes})


@login_required
def month_end_create(request):
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from .models import MonthEndClose, MonthEndCloseTask, MonthEndCloseStatus
    if request.method == 'POST':
        month = int(request.POST.get('period_month', 0))
        year  = int(request.POST.get('period_year', 0))
        if not (1 <= month <= 12) or year < 2000:
            messages.error(request, 'Invalid period.')
        elif MonthEndClose.objects.filter(period_month=month, period_year=year).exists():
            messages.error(request, 'A close checklist already exists for this period.')
        else:
            close = MonthEndClose.objects.create(
                period_month=month, period_year=year,
                status=MonthEndCloseStatus.OPEN,
                started_by=request.user,
                created_by=request.user,
            )
            for i, task_name in enumerate(_MONTH_END_TASKS):
                MonthEndCloseTask.objects.create(close=close, task_name=task_name, task_order=i)
            messages.success(request, f'Month-end checklist created for {close.period_label}.')
            return redirect('billing:month_end_detail', close_id=close.pk)
    today = timezone.localdate()
    return render(request, 'billing/month_end_form.html', {
        'today': today,
        'months': [(i, __import__('calendar').month_name[i]) for i in range(1, 13)],
    })


@login_required
def month_end_detail(request, close_id):
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from .models import MonthEndClose, MonthEndCloseStatus
    close = get_object_or_404(MonthEndClose, pk=close_id, is_deleted=False)
    tasks = close.tasks.order_by('task_order')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'toggle_task':
            task_id = request.POST.get('task_id')
            task = close.tasks.filter(pk=task_id).first()
            if task:
                task.is_completed = not task.is_completed
                if task.is_completed:
                    task.completed_by = request.user
                    task.completed_at = timezone.now()
                else:
                    task.completed_by = None
                    task.completed_at = None
                task.save()
                if close.status == MonthEndCloseStatus.OPEN:
                    close.status = MonthEndCloseStatus.IN_PROGRESS
                    close.save()
        elif action == 'close_period' and _can_approve_expense(request.user):
            if tasks.filter(is_completed=False).exists():
                messages.error(request, 'All tasks must be completed before closing the period.')
            else:
                close.status = MonthEndCloseStatus.CLOSED
                close.closed_by = request.user
                close.closed_at = timezone.now()
                close.save()
                messages.success(request, f'{close.period_label} closed successfully.')
        return redirect('billing:month_end_detail', close_id=close_id)

    return render(request, 'billing/month_end_detail.html', {
        'close': close,
        'tasks': tasks,
        'can_close': _can_approve_expense(request.user),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Cash Count Sheet
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def cash_count_list(request):
    if not (request.user.role in ('cashier', 'chief_cashier') or _can_view_financial_reports(request.user)):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from .models import CashCountSheet
    qs = CashCountSheet.objects.select_related('cashier', 'verified_by').order_by('-count_date', '-created_at')
    if request.user.role == 'cashier':
        qs = qs.filter(cashier=request.user)
    return render(request, 'billing/cash_count_list.html', {'sheets': qs[:100]})


@login_required
def cash_count_create(request):
    from .models import CashCountSheet, CashierSession, SessionStatus
    if not (request.user.role in ('cashier', 'chief_cashier') or _can_view_financial_reports(request.user)):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    session = CashierSession.objects.filter(
        cashier=request.user, status=SessionStatus.OPEN, is_deleted=False
    ).order_by('-opened_at').first()

    if request.method == 'POST':
        denoms = {
            'denom_10000': int(request.POST.get('d10000', 0) or 0),
            'denom_5000':  int(request.POST.get('d5000',  0) or 0),
            'denom_2000':  int(request.POST.get('d2000',  0) or 0),
            'denom_1000':  int(request.POST.get('d1000',  0) or 0),
            'denom_500':   int(request.POST.get('d500',   0) or 0),
            'denom_200':   int(request.POST.get('d200',   0) or 0),
            'denom_100':   int(request.POST.get('d100',   0) or 0),
            'denom_50':    int(request.POST.get('d50',    0) or 0),
            'denom_25':    int(request.POST.get('d25',    0) or 0),
            'denom_10':    int(request.POST.get('d10',    0) or 0),
        }
        expected = Decimal(request.POST.get('expected', '0') or '0')
        sheet = CashCountSheet(**denoms)
        sheet.cashier = request.user
        sheet.session = session
        sheet.count_date = timezone.localdate()
        sheet.total_expected = expected
        sheet.total_counted = sheet.compute_total()
        sheet.variance = sheet.total_counted - sheet.total_expected
        sheet.notes = request.POST.get('notes', '')
        sheet.created_by = request.user
        sheet.save()
        # Auto-create variance register entry if variance != 0
        if sheet.variance != 0 and session:
            try:
                from .models import CashVarianceRegister
                CashVarianceRegister.objects.get_or_create(
                    session=session,
                    defaults={
                        'cashier': request.user,
                        'variance_date': timezone.localdate(),
                        'expected_amount': expected,
                        'declared_amount': sheet.total_counted,
                        'variance_amount': sheet.variance,
                        'created_by': request.user,
                    }
                )
            except Exception:
                pass
        messages.success(request, f'Cash count recorded. Variance: {sheet.variance:,.0f} FCFA')
        return redirect('billing:cash_count_list')

    # Expected = session total collected
    expected = 0
    if session:
        expected = int(session.total_collected or 0)
    return render(request, 'billing/cash_count_form.html', {
        'session': session,
        'expected': expected,
        'today': timezone.localdate(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Depreciation Run
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def depreciation_run_list(request):
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from .models import DepreciationRun
    runs = DepreciationRun.objects.select_related('run_by', 'journal_entry').order_by('-period_year', '-period_month')
    return render(request, 'billing/depreciation_run_list.html', {'runs': runs})


@login_required
def depreciation_run_create(request):
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from .models import DepreciationRun, DepreciationEntry, AssetRegister, AssetStatus, DepreciationRunStatus
    from django.db import transaction
    if request.method == 'POST':
        month = int(request.POST.get('period_month', 0))
        year  = int(request.POST.get('period_year', 0))
        if not (1 <= month <= 12) or year < 2000:
            messages.error(request, 'Invalid period.')
        elif DepreciationRun.objects.filter(period_month=month, period_year=year).exists():
            messages.error(request, 'Depreciation run already exists for this period.')
        else:
            assets = AssetRegister.objects.filter(
                is_deleted=False,
                status__in=[AssetStatus.ACTIVE, AssetStatus.IN_USE],
            )
            total = Decimal('0')
            entries_data = []
            for asset in assets:
                if asset.is_fully_depreciated:
                    continue
                monthly_dep = asset.annual_depreciation / 12
                if monthly_dep <= 0:
                    continue
                accum_before = asset.accumulated_depreciation
                accum_after  = accum_before + monthly_dep
                nbv          = max(Decimal('0'), asset.purchase_price - accum_after)
                entries_data.append((asset, monthly_dep, accum_before, accum_after, nbv))
                total += monthly_dep

            if not entries_data:
                messages.warning(request, 'No active depreciable assets found.')
            else:
                with transaction.atomic():
                    run = DepreciationRun.objects.create(
                        period_month=month, period_year=year,
                        status=DepreciationRunStatus.DRAFT,
                        total_depreciation=total,
                        run_by=request.user,
                        created_by=request.user,
                    )
                    for asset, dep, ab, aa, nbv in entries_data:
                        DepreciationEntry.objects.create(
                            run=run, asset=asset,
                            depreciation_amount=dep,
                            accumulated_before=ab,
                            accumulated_after=aa,
                            net_book_value=nbv,
                        )
                messages.success(request, f'Depreciation run created: {run} — {len(entries_data)} assets, {total:,.0f} FCFA total.')
                return redirect('billing:depreciation_run_detail', run_id=run.pk)
    today = timezone.localdate()
    return render(request, 'billing/depreciation_run_form.html', {
        'months': [(i, __import__('calendar').month_name[i]) for i in range(1, 13)],
        'today': today,
    })


@login_required
def depreciation_run_detail(request, run_id):
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from .models import DepreciationRun, DepreciationRunStatus
    run = get_object_or_404(DepreciationRun, pk=run_id, is_deleted=False)
    entries = run.entries.select_related('asset').order_by('asset__asset_name')

    if request.method == 'POST' and request.POST.get('action') == 'post' and _can_approve_expense(request.user):
        if run.status == DepreciationRunStatus.DRAFT:
            try:
                _post_depreciation_gl(run, entries, request.user)
                run.status = DepreciationRunStatus.POSTED
                run.save()
                messages.success(request, f'Depreciation GL entries posted for {run}.')
            except Exception as e:
                messages.error(request, f'GL posting failed: {e}')
        return redirect('billing:depreciation_run_detail', run_id=run_id)

    return render(request, 'billing/depreciation_run_detail.html', {
        'run': run,
        'entries': entries,
        'can_post': _can_approve_expense(request.user),
    })


def _post_depreciation_gl(run, entries, user):
    from .models import JournalEntry, JournalLine, GLAccount, JournalEntryStatus
    dep_exp = GLAccount.objects.filter(code__startswith='681', is_deleted=False).first()  # 681000 Dotations amortissements
    acc_dep = GLAccount.objects.filter(code__startswith='28',  is_deleted=False).first()  # 28xxxx Amortissements cumulés
    if not dep_exp or not acc_dep:
        raise ValueError('GL accounts 681xxx (depreciation expense) and 28xxx (accumulated depreciation) not configured.')
    journal = JournalEntry.objects.create(
        entry_date=timezone.localdate(),
        reference=f'DEP-{run.period_year}-{run.period_month:02d}',
        description=f'Monthly depreciation {run.period_label} — {entries.count()} assets',
        status=JournalEntryStatus.POSTED,
        created_by=user,
    )
    run.journal_entry = journal
    run.save(update_fields=['journal_entry'])
    lines = []
    for dep_entry in entries:
        lines.append(JournalLine(entry=journal, account=dep_exp,
                                  debit_amount=dep_entry.depreciation_amount, credit_amount=0,
                                  description=f'Amortissement {dep_entry.asset.asset_name}'))
        lines.append(JournalLine(entry=journal, account=acc_dep,
                                  debit_amount=0, credit_amount=dep_entry.depreciation_amount,
                                  description=f'Amortissement cumulé {dep_entry.asset.asset_name}'))
    JournalLine.objects.bulk_create(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Withholding Tax
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def withholding_tax_list(request):
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from .models import WithholdingTax
    qs = WithholdingTax.objects.select_related('ap_bill').order_by('-transaction_date')
    # Filter
    remitted = request.GET.get('remitted', '')
    if remitted == '1':
        qs = qs.filter(is_remitted=True)
    elif remitted == '0':
        qs = qs.filter(is_remitted=False)
    from django.db.models import Sum as _S
    totals = qs.aggregate(gross=_S('gross_amount'), wht=_S('wht_amount'), net=_S('net_paid'))
    pending_total = WithholdingTax.objects.filter(is_remitted=False, is_deleted=False).aggregate(t=_S('wht_amount'))['t'] or 0
    return render(request, 'billing/withholding_tax_list.html', {
        'taxes': qs[:200],
        'totals': totals,
        'pending_total': pending_total,
        'remitted_filter': remitted,
    })


@login_required
def withholding_tax_create(request):
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from .models import WithholdingTax, WHTType, APBill
    if request.method == 'POST':
        try:
            gross = Decimal(request.POST.get('gross_amount', '0'))
            rate  = Decimal(request.POST.get('wht_rate', '5.50'))
            wht   = (gross * rate / 100).quantize(Decimal('1'))
            bill_id = request.POST.get('ap_bill_id') or None
            bill = APBill.objects.filter(pk=bill_id).first() if bill_id else None
            WithholdingTax.objects.create(
                transaction_date=request.POST.get('transaction_date'),
                supplier_name=request.POST.get('supplier_name', '').strip(),
                ap_bill=bill,
                tax_type=request.POST.get('tax_type', WHTType.TSR),
                gross_amount=gross,
                wht_rate=rate,
                wht_amount=wht,
                net_paid=gross - wht,
                reference=request.POST.get('reference', '').strip(),
                notes=request.POST.get('notes', '').strip(),
                created_by=request.user,
            )
            messages.success(request, f'Withholding tax recorded: {wht:,.0f} FCFA')
            return redirect('billing:withholding_tax_list')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    from .models import WHTType, APBill
    bills = APBill.objects.filter(is_deleted=False).order_by('-bill_date')[:50]
    return render(request, 'billing/withholding_tax_form.html', {
        'wht_types': WHTType.choices,
        'bills': bills,
        'today': timezone.localdate(),
    })


@login_required
def withholding_tax_remit(request, wht_id):
    """Mark a withholding tax as remitted to DGI."""
    if not _can_approve_expense(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:withholding_tax_list')
    from .models import WithholdingTax
    wht = get_object_or_404(WithholdingTax, pk=wht_id, is_deleted=False)
    if request.method == 'POST':
        wht.is_remitted = True
        wht.remittance_date = request.POST.get('remittance_date') or timezone.localdate()
        wht.remittance_ref  = request.POST.get('remittance_ref', '').strip()
        wht.save()
        messages.success(request, f'WHT marked as remitted to DGI.')
    return redirect('billing:withholding_tax_list')


# ─────────────────────────────────────────────────────────────────────────────
# SYSCOHADA Financial Statements
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def syscohada_bilan(request):
    """OHADA-formatted Balance Sheet (Bilan SYSCOHADA)."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from .models import GLAccount, JournalLine
    from django.db.models import Sum as _S, F, Case, When, Value, DecimalField as _DF
    today = timezone.localdate()
    as_of = request.GET.get('as_of', str(today))
    try:
        from datetime import date as _d
        as_of_date = _d.fromisoformat(as_of)
    except Exception:
        as_of_date = today

    # Get all account balances up to as_of_date
    balances = {}
    for row in JournalLine.objects.filter(
        entry__entry_date__lte=as_of_date,
        entry__status='POSTED',
    ).values('account__code', 'account__name', 'account__account_type').annotate(
        total_dr=_S('debit_amount'), total_cr=_S('credit_amount')
    ):
        code = row['account__code'] or ''
        net = float(row['total_dr'] or 0) - float(row['total_cr'] or 0)
        balances[code] = {'name': row['account__name'], 'type': row['account__account_type'], 'net': net}

    def _sum_prefix(prefix):
        return sum(v['net'] for k, v in balances.items() if k.startswith(prefix))

    # ACTIF (Assets)
    immobilisations = {
        'Frais établissement': _sum_prefix('201'),
        'Immob. incorporelles': _sum_prefix('21'),
        'Immob. corporelles': _sum_prefix('22') + _sum_prefix('23') + _sum_prefix('24'),
        'Immob. financières': _sum_prefix('26') + _sum_prefix('27'),
        'Amortissements (-)': _sum_prefix('28') + _sum_prefix('29'),
    }
    actif_immo = sum(immobilisations.values())

    actif_circ = {
        'Stocks': _sum_prefix('31') + _sum_prefix('32') + _sum_prefix('33') + _sum_prefix('34') + _sum_prefix('35'),
        'Créances clients (AR)': _sum_prefix('41'),
        'Autres créances': _sum_prefix('42') + _sum_prefix('43') + _sum_prefix('44') + _sum_prefix('45'),
        'Avances personnel': _sum_prefix('421'),
        'Provisions créances (-)': _sum_prefix('49'),
    }
    actif_ct = sum(actif_circ.values())

    tresorerie_actif = {
        'Caisse': _sum_prefix('57'),
        'Banques': _sum_prefix('52'),
        'Chèques à encaisser': _sum_prefix('515'),
    }
    tres_a = sum(tresorerie_actif.values())

    total_actif = actif_immo + actif_ct + tres_a

    # PASSIF (Liabilities + Equity)
    capitaux = {
        'Capital social': _sum_prefix('101'),
        'Réserves': _sum_prefix('11') + _sum_prefix('12') + _sum_prefix('13'),
        'Résultat exercice': _sum_prefix('12') + _sum_prefix('13'),
        'Subventions': _sum_prefix('14'),
        'Provisions réglementées': _sum_prefix('15'),
    }
    cap_propres = -sum(capitaux.values())  # credit balances are negative in our model

    dettes_lt = {
        'Emprunts LT': _sum_prefix('161') + _sum_prefix('162') + _sum_prefix('163'),
        'Dettes envers établissements crédit': _sum_prefix('164'),
    }
    dettes_lt_total = -sum(dettes_lt.values())

    dettes_ct = {
        'Fournisseurs (AP)': _sum_prefix('40'),
        'Personnel': _sum_prefix('42'),
        'Organismes sociaux (CNPS)': _sum_prefix('43'),
        'État & impôts': _sum_prefix('44') + _sum_prefix('447'),
        'Autres dettes CT': _sum_prefix('46') + _sum_prefix('47') + _sum_prefix('48'),
    }
    dettes_ct_total = -sum(dettes_ct.values())

    tresorerie_passif = {
        'Concours bancaires': _sum_prefix('519'),
        'Découverts': _sum_prefix('561'),
    }
    tres_p = -sum(tresorerie_passif.values())

    total_passif = cap_propres + dettes_lt_total + dettes_ct_total + tres_p

    return render(request, 'billing/reports/syscohada_bilan.html', {
        'as_of_date': as_of_date,
        'immobilisations': immobilisations,
        'actif_immo': actif_immo,
        'actif_circ': actif_circ,
        'actif_ct': actif_ct,
        'tresorerie_actif': tresorerie_actif,
        'tres_a': tres_a,
        'total_actif': total_actif,
        'capitaux': capitaux,
        'cap_propres': cap_propres,
        'dettes_lt': dettes_lt,
        'dettes_lt_total': dettes_lt_total,
        'dettes_ct': dettes_ct,
        'dettes_ct_total': dettes_ct_total,
        'tresorerie_passif': tresorerie_passif,
        'tres_p': tres_p,
        'total_passif': total_passif,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Rolling Cash Flow Forecast (30/60/90 days)
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def cash_flow_forecast(request):
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from .models import (Invoice, InvoiceStatus, APBill, APBillStatus,
                         BankAccount, SafeBalance, StaffAdvance, AdvanceStatus)
    from datetime import timedelta
    from django.db.models import Sum as _S, F, ExpressionWrapper, DecimalField as _DF

    today = timezone.localdate()

    # Current liquidity position
    bank_total = BankAccount.objects.filter(is_active=True, is_deleted=False).aggregate(
        t=_S('opening_balance'))['t'] or 0
    latest_safe = SafeBalance.objects.filter(is_deleted=False).order_by('-date').first()
    safe_balance = latest_safe.closing_balance if latest_safe else 0
    current_cash = float(safe_balance) + float(bank_total)

    # Invoice subtotal is a property not a DB field — sum via items (unit_price * quantity)
    _inv_total_expr = ExpressionWrapper(
        F('items__unit_price') * F('items__quantity'),
        output_field=_DF(max_digits=14, decimal_places=2),
    )

    # Expected inflows: outstanding invoices (AR)
    ar_30 = Invoice.objects.filter(
        status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
        is_deleted=False, issue_date__gte=today - timedelta(days=30)
    ).aggregate(t=_S(_inv_total_expr))['t'] or 0

    ar_60 = Invoice.objects.filter(
        status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
        is_deleted=False, issue_date__gte=today - timedelta(days=60),
        issue_date__lt=today - timedelta(days=30)
    ).aggregate(t=_S(_inv_total_expr))['t'] or 0

    ar_90 = Invoice.objects.filter(
        status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
        is_deleted=False, issue_date__gte=today - timedelta(days=90),
        issue_date__lt=today - timedelta(days=60)
    ).aggregate(t=_S(_inv_total_expr))['t'] or 0

    # Expected outflows: AP bills due
    ap_30 = APBill.objects.filter(
        status__in=[APBillStatus.PENDING, APBillStatus.PARTIAL],
        due_date__lte=today + timedelta(days=30), is_deleted=False
    ).aggregate(t=_S('amount_due'))['t'] or 0

    ap_60 = APBill.objects.filter(
        status__in=[APBillStatus.PENDING, APBillStatus.PARTIAL],
        due_date__gt=today + timedelta(days=30),
        due_date__lte=today + timedelta(days=60), is_deleted=False
    ).aggregate(t=_S('amount_due'))['t'] or 0

    ap_90 = APBill.objects.filter(
        status__in=[APBillStatus.PENDING, APBillStatus.PARTIAL],
        due_date__gt=today + timedelta(days=60),
        due_date__lte=today + timedelta(days=90), is_deleted=False
    ).aggregate(t=_S('amount_due'))['t'] or 0

    # Outstanding advances
    advances_out = StaffAdvance.objects.filter(
        status=AdvanceStatus.DISBURSED, is_deleted=False
    ).aggregate(t=_S('amount_approved'))['t'] or 0

    def _fmt_period(days):
        return (today + timedelta(days=days)).strftime('%d %b %Y')

    return render(request, 'billing/reports/cash_flow_forecast.html', {
        'today': today,
        'current_cash': current_cash,
        'safe_balance': safe_balance,
        'bank_total': bank_total,
        'ar_30': ar_30, 'ar_60': ar_60, 'ar_90': ar_90,
        'ap_30': ap_30, 'ap_60': ap_60, 'ap_90': ap_90,
        'advances_out': advances_out,
        'net_30': float(ar_30) - float(ap_30),
        'net_60': float(ar_30) + float(ar_60) - float(ap_30) - float(ap_60),
        'net_90': float(ar_30) + float(ar_60) + float(ar_90) - float(ap_30) - float(ap_60) - float(ap_90),
        'end_30': _fmt_period(30),
        'end_60': _fmt_period(60),
        'end_90': _fmt_period(90),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# SURGICAL COST SUMMARY  —  Per-case cost breakdown for Finance Director
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def surgical_cost_summary(request):
    """
    Per-case surgical cost breakdown: ward stay + theatre + drugs + total billed vs collected.
    Finance Director view — OHADA cost accounting for each surgical case.
    """
    if not _can_view_pl(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')

    from apps.ipd.models import Admission, AdmissionStatus
    from apps.ipd.models import SurgicalBooking
    import datetime

    today = timezone.localdate()
    date_from = request.GET.get('date_from', today.replace(day=1).isoformat())
    date_to = request.GET.get('date_to', today.isoformat())
    surgeon_filter = request.GET.get('surgeon', '')

    try:
        _df = datetime.date.fromisoformat(date_from)
        _dt = datetime.date.fromisoformat(date_to)
    except ValueError:
        _df = today.replace(day=1)
        _dt = today
        date_from = _df.isoformat()
        date_to = _dt.isoformat()

    # Completed surgical bookings in period
    bookings_qs = SurgicalBooking.objects.filter(
        is_deleted=False,
        status='COMPLETED',
        surgery_date__date__gte=_df,
        surgery_date__date__lte=_dt,
    ).select_related('patient', 'surgeon', 'invoice')

    if surgeon_filter:
        bookings_qs = bookings_qs.filter(surgeon_id=surgeon_filter)

    cases = []
    grand_ward = 0
    grand_theatre = 0
    grand_drugs = 0
    grand_billed = 0
    grand_collected = 0

    for bk in bookings_qs.order_by('surgery_date'):
        # Ward stay cost from admission
        admission = Admission.objects.filter(
            surgical_booking=bk, is_deleted=False
        ).select_related('bed__ward').first()

        ward_days = 0
        ward_rate = 0
        ward_cost = 0
        if admission:
            if admission.discharge_date and admission.admission_date:
                delta = admission.discharge_date.date() - admission.admission_date.date()
                ward_days = max(delta.days, 1)
            elif admission.admission_date:
                ward_days = (today - admission.admission_date.date())
                ward_days = max(ward_days.days, 1) if hasattr(ward_days, 'days') else 1
            ward_rate = float(admission.bed.nightly_rate) if admission.bed else 0
            ward_cost = ward_days * ward_rate

        # Theatre cost (SURGICAL items on invoice)
        theatre_cost = 0
        drugs_cost = 0
        total_billed = 0
        total_collected = 0

        if bk.invoice:
            inv = bk.invoice
            items = inv.items.filter(is_deleted=False)
            for item in items:
                line_total = float(item.quantity) * float(item.unit_price)
                total_billed += line_total
                if item.category == ServiceCategory.SURGICAL:
                    theatre_cost += line_total
                elif item.category == ServiceCategory.PHARMACY:
                    drugs_cost += line_total
            # Payments
            total_collected = float(
                inv.payments.filter(is_deleted=False).aggregate(t=Sum('amount'))['t'] or 0
            )

        case_total = ward_cost + theatre_cost + drugs_cost
        grand_ward += ward_cost
        grand_theatre += theatre_cost
        grand_drugs += drugs_cost
        grand_billed += total_billed
        grand_collected += total_collected

        cases.append({
            'booking': bk,
            'patient': bk.patient,
            'surgery_date': bk.surgery_date,
            'procedure': bk.get_procedure_display() if hasattr(bk, 'get_procedure_display') else bk.procedure,
            'surgeon': bk.surgeon,
            'ward_days': ward_days,
            'ward_rate': ward_rate,
            'ward_cost': ward_cost,
            'theatre_cost': theatre_cost,
            'drugs_cost': drugs_cost,
            'case_total': case_total,
            'total_billed': total_billed,
            'total_collected': total_collected,
            'outstanding': total_billed - total_collected,
            'admission': admission,
        })

    # Surgeon list for filter
    from apps.accounts.models import User, UserRole
    surgeons = User.objects.filter(role=UserRole.OPHTHALMOLOGIST, is_active=True).order_by('last_name')

    return render(request, 'billing/reports/surgical_cost_summary.html', {
        'cases': cases,
        'date_from': date_from,
        'date_to': date_to,
        'surgeon_filter': surgeon_filter,
        'surgeons': surgeons,
        'total_cases': len(cases),
        'grand_ward': grand_ward,
        'grand_theatre': grand_theatre,
        'grand_drugs': grand_drugs,
        'grand_billed': grand_billed,
        'grand_collected': grand_collected,
        'grand_outstanding': grand_billed - grand_collected,
        'today': today,
    })


# ══════════════════════════════════════════════════════════════════════════════
# ENHANCED CASH MANAGEMENT
# CashOperationType / CashWithdrawal / CashDeskSupply
# ══════════════════════════════════════════════════════════════════════════════

from .models import (
    CashOperationType, CashOperationCategory,
    CashWithdrawal, CashWithdrawalLine, CashDeskSupply, CashDeskSupplyDirection,
    CashDesk, GLAccount, BankAccount,
)


def _can_manage_cash(user):
    return (user.is_super_admin or user.is_finance_director or
            user.is_senior_accountant or user.is_accountant or
            user.is_chief_cashier)


# ── Cash Operation Types (Settings) ──────────────────────────────────────────

@login_required
def cash_operation_type_list(request):
    if not _can_manage_cash(request.user):
        return HttpResponseForbidden()
    types = CashOperationType.objects.select_related('default_gl_account').order_by('category', 'code')
    return render(request, 'billing/cash_operation_type_list.html', {
        'types': types,
        'categories': CashOperationCategory.choices,
    })


@login_required
def cash_operation_type_create(request):
    if not _can_manage_cash(request.user):
        return HttpResponseForbidden()
    gl_accounts = GLAccount.objects.filter(is_active=True, is_deleted=False).order_by('code')
    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        name = request.POST.get('name', '').strip()
        category = request.POST.get('category', '')
        gl_id = request.POST.get('default_gl_account') or None
        narration = request.POST.get('auto_narration_template', '').strip()
        if not code or not name:
            messages.error(request, 'Code and Name are required.')
        else:
            obj, created = CashOperationType.objects.get_or_create(
                code=code,
                defaults=dict(
                    name=name, category=category,
                    default_gl_account_id=gl_id,
                    auto_narration_template=narration,
                )
            )
            if not created:
                messages.error(request, f'Code {code} already exists.')
            else:
                messages.success(request, f'Type {code} — {name} created.')
                return redirect('billing:cash_operation_type_list')
    return render(request, 'billing/cash_operation_type_form.html', {
        'gl_accounts': gl_accounts,
        'categories': CashOperationCategory.choices,
    })


@login_required
def cash_operation_type_edit(request, type_id):
    if not _can_manage_cash(request.user):
        return HttpResponseForbidden()
    obj = get_object_or_404(CashOperationType, pk=type_id)
    gl_accounts = GLAccount.objects.filter(is_active=True, is_deleted=False).order_by('code')
    if request.method == 'POST':
        obj.name = request.POST.get('name', '').strip()
        obj.category = request.POST.get('category', obj.category)
        obj.default_gl_account_id = request.POST.get('default_gl_account') or None
        obj.auto_narration_template = request.POST.get('auto_narration_template', '').strip()
        obj.is_active = request.POST.get('is_active') == 'on'
        obj.save()
        messages.success(request, f'Type {obj.code} updated.')
        return redirect('billing:cash_operation_type_list')
    return render(request, 'billing/cash_operation_type_form.html', {
        'obj': obj,
        'gl_accounts': gl_accounts,
        'categories': CashOperationCategory.choices,
    })


# ── Cash Withdrawals ──────────────────────────────────────────────────────────

@login_required
def cash_withdrawal_list(request):
    if not _can_manage_cash(request.user):
        return HttpResponseForbidden()
    qs = CashWithdrawal.objects.filter(is_deleted=False).select_related(
        'cash_desk', 'operation_type', 'patient', 'recorded_by'
    ).order_by('-withdrawal_date', '-created_at')[:200]
    return render(request, 'billing/cash_withdrawal_list.html', {'withdrawals': qs})


@login_required
def cash_withdrawal_create(request):
    """Single-line cash withdrawal (Retrait Espèces)."""
    if not _can_manage_cash(request.user):
        return HttpResponseForbidden()
    desks = CashDesk.objects.filter(is_active=True, is_deleted=False).order_by('name')
    types = CashOperationType.objects.filter(
        is_active=True, is_deleted=False,
        category=CashOperationCategory.WITHDRAWAL
    ).select_related('default_gl_account')
    gl_accounts = GLAccount.objects.filter(is_active=True, is_deleted=False).order_by('code')

    if request.method == 'POST':
        desk_id = request.POST.get('cash_desk')
        type_id = request.POST.get('operation_type') or None
        gl_id   = request.POST.get('gl_account') or None
        reason  = request.POST.get('reason', '').strip()
        amount  = request.POST.get('amount', '0')
        ref     = request.POST.get('reference', '').strip()
        date_str = request.POST.get('withdrawal_date', '') or timezone.localdate().isoformat()
        try:
            amount = Decimal(amount)
        except Exception:
            amount = Decimal('0')
        if amount <= 0:
            messages.error(request, 'Amount must be greater than zero.')
        else:
            w = CashWithdrawal.objects.create(
                cash_desk_id=desk_id,
                operation_type_id=type_id,
                gl_account_id=gl_id,
                reason=reason,
                total_amount=amount,
                reference=ref,
                withdrawal_date=date_str,
                is_multi_line=False,
                recorded_by=request.user,
            )
            messages.success(request, f'Withdrawal {w.bordereau_number} recorded — {amount:,.0f} FCFA.')
            return redirect('billing:cash_withdrawal_list')

    return render(request, 'billing/cash_withdrawal_form.html', {
        'desks': desks, 'types': types, 'gl_accounts': gl_accounts,
        'today': timezone.localdate(),
    })


@login_required
def cash_withdrawal_multi_create(request):
    """Multi-line cash withdrawal (Retrait Multiple)."""
    if not _can_manage_cash(request.user):
        return HttpResponseForbidden()
    desks = CashDesk.objects.filter(is_active=True, is_deleted=False).order_by('name')
    types = CashOperationType.objects.filter(
        is_active=True, is_deleted=False
    ).select_related('default_gl_account')
    gl_accounts = GLAccount.objects.filter(is_active=True, is_deleted=False).order_by('code')

    if request.method == 'POST':
        desk_id      = request.POST.get('cash_desk')
        type_id      = request.POST.get('operation_type') or None
        intitule     = request.POST.get('intitule_compte', '').strip()
        libelle_ctp  = request.POST.get('libelle_ctp', '').strip()
        date_str     = request.POST.get('withdrawal_date', '') or timezone.localdate().isoformat()

        gl_ids      = request.POST.getlist('line_gl_account[]')
        libelles    = request.POST.getlist('line_libelle[]')
        refs        = request.POST.getlist('line_reference[]')
        amounts_raw = request.POST.getlist('line_amount[]')

        lines = []
        total = Decimal('0')
        for i in range(len(amounts_raw)):
            try:
                amt = Decimal(amounts_raw[i] or '0')
            except Exception:
                amt = Decimal('0')
            if amt > 0:
                lines.append({
                    'gl_account_id': gl_ids[i] if i < len(gl_ids) else None,
                    'libelle': libelles[i] if i < len(libelles) else '',
                    'reference': refs[i] if i < len(refs) else '',
                    'amount': amt,
                })
                total += amt

        if not lines:
            messages.error(request, 'Add at least one line with an amount.')
        else:
            w = CashWithdrawal.objects.create(
                cash_desk_id=desk_id,
                operation_type_id=type_id,
                total_amount=total,
                withdrawal_date=date_str,
                is_multi_line=True,
                intitule_compte=intitule,
                libelle_ctp=libelle_ctp,
                recorded_by=request.user,
            )
            for line in lines:
                CashWithdrawalLine.objects.create(withdrawal=w, **line)
            messages.success(request, f'Multi withdrawal {w.bordereau_number} — {total:,.0f} FCFA recorded.')
            return redirect('billing:cash_withdrawal_list')

    return render(request, 'billing/cash_withdrawal_multi_form.html', {
        'desks': desks, 'types': types, 'gl_accounts': gl_accounts,
        'today': timezone.localdate(),
    })


@login_required
def cash_withdrawal_patient(request):
    """Patient-linked cash withdrawal (Retrait Patient)."""
    if not _can_manage_cash(request.user):
        return HttpResponseForbidden()
    desks = CashDesk.objects.filter(is_active=True, is_deleted=False).order_by('name')
    types = CashOperationType.objects.filter(
        is_active=True, is_deleted=False,
        category=CashOperationCategory.PATIENT_REFUND
    )
    gl_accounts = GLAccount.objects.filter(is_active=True, is_deleted=False).order_by('code')

    if request.method == 'POST':
        desk_id    = request.POST.get('cash_desk')
        type_id    = request.POST.get('operation_type') or None
        patient_id = request.POST.get('patient_id') or None
        gl_id      = request.POST.get('gl_account') or None
        reason     = request.POST.get('reason', '').strip()
        amount     = request.POST.get('amount', '0')
        ref        = request.POST.get('reference', '').strip()
        try:
            amount = Decimal(amount)
        except Exception:
            amount = Decimal('0')
        if amount <= 0:
            messages.error(request, 'Amount must be greater than zero.')
        else:
            w = CashWithdrawal.objects.create(
                cash_desk_id=desk_id,
                operation_type_id=type_id,
                patient_id=patient_id,
                gl_account_id=gl_id,
                reason=reason,
                total_amount=amount,
                reference=ref,
                withdrawal_date=timezone.localdate(),
                is_multi_line=False,
                recorded_by=request.user,
            )
            messages.success(request, f'Patient withdrawal {w.bordereau_number} recorded.')
            return redirect('billing:cash_withdrawal_list')

    from apps.patients.models import Patient as Pat
    patients = Pat.objects.filter(is_deleted=False).order_by('last_name', 'first_name')[:500]
    return render(request, 'billing/cash_withdrawal_patient_form.html', {
        'desks': desks, 'types': types, 'gl_accounts': gl_accounts,
        'patients': patients, 'today': timezone.localdate(),
    })


@login_required
def cash_withdrawal_reverse(request):
    """Reverse (extourne) a multi-line cash withdrawal."""
    if not (request.user.is_finance_director or request.user.is_senior_accountant
            or request.user.is_super_admin):
        return HttpResponseForbidden()
    desks = CashDesk.objects.filter(is_active=True, is_deleted=False).order_by('name')

    if request.method == 'POST':
        bordereau = request.POST.get('bordereau_number', '').strip().upper()
        date_str  = request.POST.get('date', '') or timezone.localdate().isoformat()
        libelle   = request.POST.get('libelle', '').strip()
        desk_id   = request.POST.get('cash_desk') or None

        try:
            original = CashWithdrawal.objects.get(bordereau_number=bordereau, is_deleted=False)
        except CashWithdrawal.DoesNotExist:
            messages.error(request, f'No withdrawal found with bordereau {bordereau}.')
            return redirect('billing:cash_withdrawal_reverse')

        if original.is_reversed:
            messages.error(request, f'{bordereau} has already been reversed.')
            return redirect('billing:cash_withdrawal_list')

        reversal = CashWithdrawal.objects.create(
            cash_desk_id=desk_id or original.cash_desk_id,
            operation_type=original.operation_type,
            gl_account=original.gl_account,
            reason=f'EXTOURNE — {libelle or bordereau}',
            total_amount=original.total_amount,
            withdrawal_date=date_str,
            is_multi_line=original.is_multi_line,
            is_reversed=False,
            reversal_ref=original.bordereau_number,
            recorded_by=request.user,
        )
        # Copy lines if multi
        for line in original.lines.all():
            CashWithdrawalLine.objects.create(
                withdrawal=reversal,
                gl_account=line.gl_account,
                auto_libelle=line.auto_libelle,
                libelle=line.libelle,
                reference=line.reference,
                amount=line.amount,
            )
        original.is_reversed = True
        original.save(update_fields=['is_reversed', 'updated_at'])
        messages.success(request, f'Reversal {reversal.bordereau_number} created for {bordereau}.')
        return redirect('billing:cash_withdrawal_list')

    return render(request, 'billing/cash_withdrawal_reverse.html', {
        'desks': desks, 'today': timezone.localdate(),
    })


# ── Cash Desk Supply ──────────────────────────────────────────────────────────

@login_required
def cash_desk_supply_list(request):
    if not _can_manage_cash(request.user):
        return HttpResponseForbidden()
    qs = CashDeskSupply.objects.filter(is_deleted=False).select_related(
        'cash_desk', 'bank_account', 'recorded_by'
    ).order_by('-supply_date', '-created_at')[:200]
    return render(request, 'billing/cash_desk_supply_list.html', {'supplies': qs})


@login_required
def cash_desk_supply_create(request):
    """Saisie Approvisionnement Caisse — fund or drain a cash desk."""
    if not _can_manage_cash(request.user):
        return HttpResponseForbidden()
    desks    = CashDesk.objects.filter(is_active=True, is_deleted=False).order_by('name')
    types    = CashOperationType.objects.filter(is_active=True, is_deleted=False).order_by('code')
    banks    = BankAccount.objects.filter(is_active=True, is_deleted=False).order_by('bank_name')

    if request.method == 'POST':
        desk_id   = request.POST.get('cash_desk')
        type_id   = request.POST.get('operation_type') or None
        bank_id   = request.POST.get('bank_account') or None
        reason    = request.POST.get('reason', '').strip()
        direction = request.POST.get('direction', CashDeskSupplyDirection.ENTREE)
        amount    = request.POST.get('amount', '0')
        ref       = request.POST.get('reference', '').strip()
        date_str  = request.POST.get('supply_date', '') or timezone.localdate().isoformat()
        try:
            amount = Decimal(amount)
        except Exception:
            amount = Decimal('0')
        if amount <= 0:
            messages.error(request, 'Amount must be greater than zero.')
        else:
            s = CashDeskSupply.objects.create(
                cash_desk_id=desk_id,
                operation_type_id=type_id,
                bank_account_id=bank_id,
                reason=reason,
                direction=direction,
                amount=amount,
                reference=ref,
                supply_date=date_str,
                recorded_by=request.user,
            )
            messages.success(request, f'Supply {s.supply_number} recorded — {amount:,.0f} FCFA ({direction}).')
            return redirect('billing:cash_desk_supply_list')

    return render(request, 'billing/cash_desk_supply_form.html', {
        'desks': desks, 'types': types, 'banks': banks,
        'directions': CashDeskSupplyDirection.choices,
        'today': timezone.localdate(),
    })


@login_required
def gross_profit_report(request):
    """Monthly Gross Profit: REVENUE vs COGS (Supplies + Drugs)."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    from datetime import date as _date
    import calendar
    from .models import Expense, ExpenseCategory
    today = _date.today()
    year = int(request.GET.get('year', today.year))

    min_year = Invoice.objects.filter(is_deleted=False).order_by('issue_date').values_list('issue_date__year', flat=True).first() or today.year
    year_range = list(range(min_year, today.year + 2))

    months = []
    for m in range(1, 13):
        revenue = Invoice.objects.filter(
            is_deleted=False, issue_date__year=year, issue_date__month=m
        ).exclude(status='VOID').aggregate(t=Sum('total'))['t'] or Decimal('0')
        cogs = Expense.objects.filter(
            is_deleted=False, date__year=year, date__month=m,
            category__in=[ExpenseCategory.SUPPLIES, ExpenseCategory.DRUGS]
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        gross   = revenue - cogs
        gp_pct  = round(float(gross) / float(revenue) * 100, 1) if revenue > 0 else 0
        months.append({'month': calendar.month_abbr[m], 'revenue': revenue, 'cogs': cogs, 'gross_profit': gross, 'gp_pct': gp_pct})

    total_revenue = sum(r['revenue'] for r in months)
    total_cogs    = sum(r['cogs']    for r in months)
    total_gross   = total_revenue - total_cogs
    total_gp_pct  = round(float(total_gross) / float(total_revenue) * 100, 1) if total_revenue > 0 else 0

    return render(request, 'billing/reports/gross_profit.html', {
        'months': months, 'year': year, 'year_range': year_range,
        'total_revenue': total_revenue, 'total_cogs': total_cogs,
        'total_gross': total_gross, 'total_gp_pct': total_gp_pct,
    })


@login_required
def gross_net_profit_report(request):
    """Monthly Gross & Net Profit: REVENUE, COGS, GP, GP%, all EXPENSES, NP, NP%."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    from datetime import date as _date
    import calendar
    from .models import Expense, ExpenseCategory
    today = _date.today()
    year = int(request.GET.get('year', today.year))

    min_year = Invoice.objects.filter(is_deleted=False).order_by('issue_date').values_list('issue_date__year', flat=True).first() or today.year
    year_range = list(range(min_year, today.year + 2))

    months = []
    for m in range(1, 13):
        revenue = Invoice.objects.filter(
            is_deleted=False, issue_date__year=year, issue_date__month=m
        ).exclude(status='VOID').aggregate(t=Sum('total'))['t'] or Decimal('0')
        cogs = Expense.objects.filter(
            is_deleted=False, date__year=year, date__month=m,
            category__in=[ExpenseCategory.SUPPLIES, ExpenseCategory.DRUGS]
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        total_exp = Expense.objects.filter(
            is_deleted=False, date__year=year, date__month=m
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        gross   = revenue - cogs
        net     = revenue - total_exp
        gp_pct  = round(float(gross) / float(revenue) * 100, 1) if revenue > 0 else 0
        np_pct  = round(float(net)   / float(revenue) * 100, 1) if revenue > 0 else 0
        months.append({
            'month': calendar.month_abbr[m],
            'revenue': revenue, 'cogs': cogs, 'gross_profit': gross, 'gp_pct': gp_pct,
            'expenses': total_exp, 'net_profit': net, 'np_pct': np_pct,
        })

    total_revenue = sum(r['revenue']  for r in months)
    total_cogs    = sum(r['cogs']     for r in months)
    total_gross   = total_revenue - total_cogs
    total_exp     = sum(r['expenses'] for r in months)
    total_net     = total_revenue - total_exp
    total_gp_pct  = round(float(total_gross) / float(total_revenue) * 100, 1) if total_revenue > 0 else 0
    total_np_pct  = round(float(total_net)   / float(total_revenue) * 100, 1) if total_revenue > 0 else 0

    return render(request, 'billing/reports/gross_net_profit.html', {
        'months': months, 'year': year, 'year_range': year_range,
        'total_revenue': total_revenue, 'total_cogs': total_cogs,
        'total_gross': total_gross, 'total_gp_pct': total_gp_pct,
        'total_exp': total_exp, 'total_net': total_net, 'total_np_pct': total_np_pct,
    })


@login_required
def profitability_analysis(request):
    """Per-customer profitability: CUSTOMER, SUBTOTAL, DISCOUNT, REVENUE, % OF TOTAL."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    from datetime import date as _date
    today = _date.today()
    date_from_str = request.GET.get('date_from', today.replace(day=1).isoformat())
    date_to_str   = request.GET.get('date_to',   today.isoformat())
    try:
        df = _date.fromisoformat(date_from_str)
        dt = _date.fromisoformat(date_to_str)
    except ValueError:
        df = today.replace(day=1); dt = today

    qs = Invoice.objects.filter(
        is_deleted=False, issue_date__range=[df, dt]
    ).exclude(status__in=['VOID', 'DRAFT']).select_related('patient')

    patient_map = {}
    for inv in qs:
        pid = inv.patient_id
        if pid not in patient_map:
            patient_map[pid] = {
                'name': inv.patient.full_name,
                'patient_id': inv.patient.patient_id,
                'subtotal': Decimal('0'),
                'discount': Decimal('0'),
                'revenue': Decimal('0'),
            }
        patient_map[pid]['subtotal']  += inv.total or Decimal('0')
        patient_map[pid]['discount']  += inv.discount_amount or Decimal('0')
        patient_map[pid]['revenue']   += inv.amount_paid or Decimal('0')

    rows = sorted(patient_map.values(), key=lambda x: x['revenue'], reverse=True)
    grand_revenue = sum(r['revenue'] for r in rows)
    for r in rows:
        r['pct'] = round(float(r['revenue']) / float(grand_revenue) * 100, 1) if grand_revenue > 0 else 0

    fmt = request.GET.get('format', '')
    if fmt in ('csv', 'excel'):
        hdr = _hospital_header(f'Profitability Analysis — {date_from_str} to {date_to_str}')
        data_rows = [['Customer', 'Patient ID', 'Subtotal (XAF)', 'Discount (XAF)', 'Revenue (XAF)', '% of Total']]
        for r in rows:
            data_rows.append([r['name'], r['patient_id'], float(r['subtotal']), float(r['discount']), float(r['revenue']), r['pct']])
        if fmt == 'csv':
            return _csv_response(f'profitability_{date_from_str}_{date_to_str}.csv', hdr, data_rows)
        return _excel_response(f'profitability_{date_from_str}_{date_to_str}.xlsx', hdr, data_rows, sheet_name='Profitability')

    return render(request, 'billing/reports/profitability_analysis.html', {
        'rows': rows, 'grand_revenue': grand_revenue,
        'date_from': df, 'date_to': dt,
        'date_from_str': date_from_str, 'date_to_str': date_to_str,
    })


@login_required
def ar_summary_report(request):
    """AR Summary per customer: CUSTOMER, OUTSTANDING, CURRENT, 1-30, 31-60, 61-90, 91+."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    from datetime import date as _date
    today = _date.today()

    unpaid = Invoice.objects.filter(
        is_deleted=False, status__in=['UNPAID', 'PARTIAL']
    ).select_related('patient')

    patient_map = {}
    for inv in unpaid:
        balance = (inv.total or Decimal('0')) - (inv.amount_paid or Decimal('0'))
        if balance <= 0:
            continue
        pid = inv.patient_id
        if pid not in patient_map:
            patient_map[pid] = {
                'name': inv.patient.full_name,
                'patient_id': inv.patient.patient_id,
                'outstanding': Decimal('0'),
                'current': Decimal('0'),
                'd30': Decimal('0'),
                'd60': Decimal('0'),
                'd90': Decimal('0'),
                'd91': Decimal('0'),
            }
        patient_map[pid]['outstanding'] += balance
        age = (today - inv.issue_date).days
        if   age <= 30:  patient_map[pid]['current'] += balance
        elif age <= 60:  patient_map[pid]['d30']     += balance
        elif age <= 90:  patient_map[pid]['d60']     += balance
        elif age <= 120: patient_map[pid]['d90']     += balance
        else:            patient_map[pid]['d91']     += balance

    rows = sorted(patient_map.values(), key=lambda x: x['outstanding'], reverse=True)
    grand = {k: sum(r[k] for r in rows) for k in ('outstanding', 'current', 'd30', 'd60', 'd90', 'd91')}

    fmt = request.GET.get('format', '')
    if fmt in ('csv', 'excel'):
        hdr = _hospital_header(f'AR Summary — As of {today}')
        data_rows = [['Customer', 'Patient ID', 'Outstanding (XAF)', 'Current (0-30)', '31-60', '61-90', '91-120', '121+']]
        for r in rows:
            data_rows.append([r['name'], r['patient_id'], float(r['outstanding']), float(r['current']), float(r['d30']), float(r['d60']), float(r['d90']), float(r['d91'])])
        if fmt == 'csv':
            return _csv_response(f'ar_summary_{today}.csv', hdr, data_rows)
        return _excel_response(f'ar_summary_{today}.xlsx', hdr, data_rows, sheet_name='AR Summary')

    return render(request, 'billing/ar_summary.html', {
        'rows': rows, 'grand': grand, 'today': today,
    })


@login_required
def supplier_ledger_summary(request):
    """Supplier Ledger Summary: SUPPLIER, OPENING BALANCE, TOTAL DEBITS, TOTAL CREDITS, CLOSING BALANCE."""
    if not _can_view_financial_reports(request.user):
        messages.error(request, 'Access denied.')
        return redirect('billing:dashboard')
    from datetime import date as _date
    from .models import APVendor, APPayment
    today = _date.today()
    date_from_str = request.GET.get('date_from', today.replace(day=1).isoformat())
    date_to_str   = request.GET.get('date_to',   today.isoformat())
    try:
        df = _date.fromisoformat(date_from_str)
        dt = _date.fromisoformat(date_to_str)
    except ValueError:
        df = today.replace(day=1); dt = today

    vendors = APVendor.objects.filter(is_deleted=False, is_active=True).order_by('name')
    rows = []
    grand_debits = grand_credits = grand_closing = Decimal('0')

    for v in vendors:
        bills_before = v.bills.filter(is_deleted=False, bill_date__lt=df).aggregate(t=Sum('amount_due'))['t'] or Decimal('0')
        paid_before  = APPayment.objects.filter(bill__vendor=v, is_deleted=False, payment_date__lt=df).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        opening  = max(bills_before - paid_before, Decimal('0'))
        debits   = v.bills.filter(is_deleted=False, bill_date__range=[df, dt]).aggregate(t=Sum('amount_due'))['t'] or Decimal('0')
        credits  = APPayment.objects.filter(bill__vendor=v, is_deleted=False, payment_date__range=[df, dt]).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        closing  = opening + debits - credits
        if opening == 0 and debits == 0 and credits == 0:
            continue
        rows.append({'vendor': v.name, 'vendor_code': v.vendor_code, 'opening': opening, 'debits': debits, 'credits': credits, 'closing': closing})
        grand_debits  += debits
        grand_credits += credits
        grand_closing += closing

    fmt = request.GET.get('format', '')
    if fmt in ('csv', 'excel'):
        hdr = _hospital_header(f'Supplier Ledger Summary — {date_from_str} to {date_to_str}')
        data_rows = [['Supplier', 'Code', 'Opening Balance (XAF)', 'Total Debits (XAF)', 'Total Credits (XAF)', 'Closing Balance (XAF)']]
        for r in rows:
            data_rows.append([r['vendor'], r['vendor_code'], float(r['opening']), float(r['debits']), float(r['credits']), float(r['closing'])])
        if fmt == 'csv':
            return _csv_response(f'supplier_ledger_{date_from_str}_{date_to_str}.csv', hdr, data_rows)
        return _excel_response(f'supplier_ledger_{date_from_str}_{date_to_str}.xlsx', hdr, data_rows, sheet_name='Supplier Ledger')

    return render(request, 'billing/supplier_ledger_summary.html', {
        'rows': rows, 'grand_debits': grand_debits, 'grand_credits': grand_credits, 'grand_closing': grand_closing,
        'date_from': df, 'date_to': dt, 'date_from_str': date_from_str, 'date_to_str': date_to_str,
    })


@login_required
def cash_desk_balance_ajax(request):
    """AJAX: return current session cash balance for a desk."""
    desk_id = request.GET.get('desk_id')
    if not desk_id:
        return JsonResponse({'balance': 0, 'label': '0 FCFA'})
    from .models import CashierSession, SessionStatus
    from django.db.models import Sum
    session = CashierSession.objects.filter(
        cash_desk_id=desk_id,
        status=SessionStatus.OPEN,
        is_deleted=False,
    ).order_by('-opened_at').first()
    if not session:
        return JsonResponse({'balance': 0, 'label': '0 FCFA', 'session': None})
    from .models import Payment, PaymentMethod
    cash_in = session.payments.filter(
        method=PaymentMethod.CASH, is_deleted=False
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    balance = session.opening_float + cash_in
    return JsonResponse({
        'balance': float(balance),
        'label': f'{balance:,.0f} FCFA',
        'session': str(session.pk),
    })
