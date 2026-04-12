from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import Invoice, InvoiceItem, Payment, InvoiceStatus, ServiceCategory, PaymentMethod
from .utils import get_or_create_today_invoice
from apps.patients.models import Patient


@login_required
def billing_dashboard(request):
    from django.db.models import Count
    today = timezone.localdate()
    month_start = today.replace(day=1)

    # Revenue
    paid_today = Payment.objects.filter(
        payment_date__date=today, is_deleted=False
    ).aggregate(total=Sum('amount'))['total'] or 0

    paid_month = Payment.objects.filter(
        payment_date__date__gte=month_start, is_deleted=False
    ).aggregate(total=Sum('amount'))['total'] or 0

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
    recent_invoices = Invoice.objects.filter(
        is_deleted=False
    ).select_related('patient').order_by('-created_at')[:15]

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
        'payment_methods': PaymentMethod.choices,
        'statuses': InvoiceStatus.choices,
    }
    return render(request, 'billing/dashboard.html', context)


@login_required
def invoice_list(request):
    q = request.GET.get('q', '')
    status = request.GET.get('status', '')
    invoices = Invoice.objects.filter(is_deleted=False).select_related('patient')
    if q:
        invoices = invoices.filter(
            Q(invoice_number__icontains=q) |
            Q(patient__first_name__icontains=q) |
            Q(patient__last_name__icontains=q)
        )
    if status:
        invoices = invoices.filter(status=status)
    return render(request, 'billing/invoice_list.html', {
        'invoices': invoices.order_by('-created_at'),
        'search': q,
        'status': status,
        'statuses': InvoiceStatus.choices,
    })


@login_required
def invoice_detail(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id, is_deleted=False)
    return render(request, 'billing/invoice_detail.html', {
        'invoice': invoice,
        'payment_methods': PaymentMethod.choices,
    })


@login_required
def invoice_create(request):
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
        'patients': Patient.objects.filter(is_active=True).order_by('first_name'),
    })


@login_required
def add_payment(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id, is_deleted=False)
    if request.method == 'POST':
        amount = request.POST.get('amount')
        if not amount:
            messages.error(request, 'Amount is required.')
            return redirect('billing:invoice_detail', invoice_id=invoice.id)
        Payment.objects.create(
            invoice=invoice,
            payment_method=request.POST['payment_method'],
            amount=amount,
            reference=request.POST.get('reference', ''),
            notes=request.POST.get('notes', ''),
            received_by=request.user,
            created_by=request.user,
        )
        # Open the 15-day consultation window for this patient's current visit
        # if the invoice contains a CONSULT or REG item (first-time payment)
        _try_open_consultation_window(invoice)
        messages.success(request, f'Payment of {amount} FCFA recorded.')
        return redirect('billing:invoice_detail', invoice_id=invoice.id)
    return redirect('billing:invoice_detail', invoice_id=invoice.id)


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
    except Exception:
        pass


@login_required
def cancel_invoice(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id, is_deleted=False)
    if request.method == 'POST':
        invoice.status = InvoiceStatus.CANCELLED
        invoice.save()
        messages.warning(request, f'Invoice {invoice.invoice_number} cancelled.')
    return redirect('billing:invoice_detail', invoice_id=invoice.id)


# ─────────────────────────────────────────────────────────────────────────────
# POS (Point of Sale) — Cashier Station
# ─────────────────────────────────────────────────────────────────────────────

SERVICE_CATALOG = [
    {'name': 'New Patient Registration', 'category': 'REG',      'price': 5000},
    {'name': 'Standard Consultation',    'category': 'CONSULT',  'price': 15000},
    {'name': 'Express Consultation',     'category': 'CONSULT',  'price': 25000},
    {'name': 'VIP Consultation',         'category': 'CONSULT',  'price': 50000},
    {'name': 'Follow-up Consultation',   'category': 'CONSULT',  'price': 8000},
    {'name': 'Refraction / Optometry',   'category': 'CONSULT',  'price': 10000},
    {'name': 'Tonometry (IOP)',          'category': 'INVEST',   'price': 3000},
    {'name': 'OCT Scan',                 'category': 'INVEST',   'price': 35000},
    {'name': 'Visual Field Test',        'category': 'INVEST',   'price': 20000},
    {'name': 'Fundus Photography',       'category': 'INVEST',   'price': 15000},
    {'name': 'Biometry (A-scan)',        'category': 'INVEST',   'price': 15000},
    {'name': 'B-scan Ultrasound',        'category': 'INVEST',   'price': 15000},
    {'name': 'Blood Sugar Test',         'category': 'LAB',      'price': 3000},
    {'name': 'Full Blood Count',         'category': 'LAB',      'price': 8000},
    {'name': 'Sickle Cell Screen',       'category': 'LAB',      'price': 5000},
    {'name': 'Drug Dispensing',          'category': 'PHARMACY', 'price': 0},
    {'name': 'Glasses Frame',            'category': 'OPTICAL',  'price': 0},
    {'name': 'Prescription Lenses',      'category': 'OPTICAL',  'price': 0},
]


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
    from apps.qms.models import ServiceCounter, QueueToken, TokenStatus, ServiceType

    today = timezone.localdate()

    # 1 — Check this cashier's assigned counter
    counter = ServiceCounter.objects.filter(
        staff_assigned=request.user, is_active=True
    ).first()
    if counter and counter.current_serving:
        token = counter.current_serving
        if token.status in (TokenStatus.SERVING, TokenStatus.CALLED):
            return redirect('billing:cashier_pos', token_id=token.id)

    # 2 — Any CASHIER token CALLED or SERVING today (any counter)
    active_token = QueueToken.objects.filter(
        service_type=ServiceType.CASHIER,
        status__in=[TokenStatus.CALLED, TokenStatus.SERVING],
        token_date=today,
        is_deleted=False,
    ).select_related('patient').order_by('-priority', 'issued_at').first()
    if active_token:
        return redirect('billing:cashier_pos', token_id=active_token.id)

    # 3 — Any CASHIER token WAITING today → take the next one in queue
    waiting_token = QueueToken.objects.filter(
        service_type=ServiceType.CASHIER,
        status=TokenStatus.WAITING,
        token_date=today,
        is_deleted=False,
    ).order_by('-priority', 'issued_at').first()
    if waiting_token:
        return redirect('billing:cashier_pos', token_id=waiting_token.id)

    # 4 — Any open invoice today (patient is here to pay, no QMS token)
    open_invoice = Invoice.objects.filter(
        issue_date=today,
        is_deleted=False,
    ).exclude(
        status__in=[InvoiceStatus.PAID, InvoiceStatus.CANCELLED]
    ).select_related('patient').order_by('-created_at').first()
    if open_invoice:
        return redirect('billing:invoice_detail', invoice_id=open_invoice.pk)

    # 5 — Nothing active — show full invoice list
    return redirect('billing:invoice_list')


@login_required
def cashier_pos(request, token_id):
    """Main POS view — displays the cashier point-of-sale interface."""
    from apps.qms.models import QueueToken
    token = get_object_or_404(QueueToken, id=token_id, is_deleted=False)
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
        prior_unpaid_invoices = Invoice.objects.filter(
            patient=patient,
            is_deleted=False,
        ).exclude(
            status__in=[InvoiceStatus.PAID, InvoiceStatus.CANCELLED, InvoiceStatus.WAIVED]
        ).exclude(
            id=invoice.id
        ).order_by('-created_at')[:5]

    return render(request, 'billing/cashier_pos.html', {
        'token': token,
        'patient': patient,
        'invoice': invoice,
        'items': items,
        'payments': payments,
        'categories': ServiceCategory.choices,
        'payment_methods': PaymentMethod.choices,
        'service_catalog': SERVICE_CATALOG,
        'today': timezone.localdate(),
        'active_consultation': active_consultation,
        'prior_unpaid_invoices': prior_unpaid_invoices,
    })


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


@login_required
@require_POST
def pos_remove_item(request, item_id):
    """AJAX: Soft-delete a line item."""
    item = get_object_or_404(InvoiceItem, id=item_id, is_deleted=False)
    invoice = item.invoice

    item.is_deleted = True
    item.save(update_fields=['is_deleted', 'updated_at'])

    invoice.refresh_from_db()
    return JsonResponse({
        'success': True,
        'subtotal': int(invoice.subtotal),
        'total': int(invoice.total),
        'balance_due': int(invoice.balance_due),
    })


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

    payment_method = request.POST.get('payment_method', PaymentMethod.CASH)
    try:
        amount = Decimal(request.POST.get('amount', '0') or '0')
    except InvalidOperation:
        return JsonResponse({'success': False, 'error': 'Invalid amount.'}, status=400)

    if amount <= 0:
        return JsonResponse({'success': False, 'error': 'Amount must be greater than zero.'}, status=400)

    reference = request.POST.get('reference', '').strip()

    Payment.objects.create(
        invoice=invoice,
        payment_method=payment_method,
        amount=amount,
        reference=reference,
        received_by=request.user,
        created_by=request.user,
    )
    # Payment.save() already calls invoice.update_status()
    _try_open_consultation_window(invoice)
    invoice.refresh_from_db()

    return JsonResponse({
        'success': True,
        'amount_paid': int(invoice.amount_paid),
        'balance_due': int(invoice.balance_due),
        'status': invoice.status,
        'is_paid': invoice.status == InvoiceStatus.PAID,
    })


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

        # 3 — Create triage token (tier-aware)
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

    from django.urls import reverse
    redirect_url = reverse('billing:receipt', kwargs={'invoice_id': str(invoice.id)})
    return JsonResponse({'success': True, 'redirect_url': redirect_url})


@login_required
def receipt_view(request, invoice_id):
    """Printable receipt page."""
    invoice = get_object_or_404(Invoice, id=invoice_id, is_deleted=False)
    items = invoice.items.filter(is_deleted=False).order_by('created_at')
    payments = invoice.payments.filter(is_deleted=False).order_by('payment_date')
    return render(request, 'billing/receipt.html', {
        'invoice': invoice,
        'items': items,
        'payments': payments,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Gap 5: Surgical Deposit Billing
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def surgical_deposit(request, booking_id):
    """
    Collect surgical deposit for a confirmed surgical booking.
    Creates or retrieves an invoice for the deposit and records payment.
    """
    from apps.ipd.models import SurgicalBooking
    booking = get_object_or_404(SurgicalBooking, id=booking_id, is_deleted=False)
    patient = booking.patient

    # Find existing deposit invoice or create one
    deposit_invoice = Invoice.objects.filter(
        patient=patient,
        items__description__icontains='Surgical Deposit',
        items__is_deleted=False,
        is_deleted=False,
    ).exclude(status=InvoiceStatus.CANCELLED).first()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_invoice' and not deposit_invoice:
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

    return render(request, 'billing/surgical_deposit.html', {
        'booking': booking,
        'patient': patient,
        'deposit_invoice': deposit_invoice,
        'items': items,
        'payments': payments,
        'payment_methods': PaymentMethod.choices,
        'balance_due': deposit_invoice.balance_due if deposit_invoice else booking.deposit_required or booking.total_amount or 0,
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
