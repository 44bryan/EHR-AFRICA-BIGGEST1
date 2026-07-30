from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone
from .models import Frame, Lens, OpticalOrder, OpticalOrderStatus


@login_required
def dashboard(request):
    def count(status):
        return OpticalOrder.objects.filter(status=status, is_deleted=False).count()

    pipeline_stages = [
        (count(OpticalOrderStatus.ORDERED),        'New Orders',        '#2563eb'),
        (count(OpticalOrderStatus.LAB_PROCESSING), 'At Lab',            '#d97706'),
        (count(OpticalOrderStatus.READY),          'Ready to Collect',  '#059669'),
        (count(OpticalOrderStatus.DELIVERED),      'Delivered',         '#6b7280'),
    ]

    today = timezone.localdate()
    from apps.patients.models import Visit
    from django.db.models import Case, When, IntegerField, Value as _V
    _tier_order = Case(When(service_tier='VIP', then=_V(3)), When(service_tier='FAST_TRACK', then=_V(2)),
                       When(service_tier='EXPRESS', then=_V(1)), default=_V(0), output_field=IntegerField())
    _pt = getattr(request.user, 'patient_tier', 'ALL')
    _opt_qs = Visit.objects.filter(visit_date__date=today, status='OPTICAL', is_deleted=False)
    if _pt == 'VIP':
        _opt_qs = _opt_qs.filter(service_tier='VIP')
    elif _pt == 'EXPRESS':
        _opt_qs = _opt_qs.filter(service_tier__in=['EXPRESS', 'FAST_TRACK'])
    elif _pt == 'STANDARD':
        _opt_qs = _opt_qs.filter(service_tier='STANDARD')
    # _pt == 'ALL' → no filter
    waiting_visits = list(
        _opt_qs.select_related('patient', 'attending_doctor')
        .annotate(_tier_order=_tier_order).order_by('-_tier_order', 'visit_date')
    )

    context = {
        'total_frames': Frame.objects.filter(is_active=True, is_deleted=False).count(),
        'total_lenses': Lens.objects.filter(is_active=True, is_deleted=False).count(),
        'pending_orders': OpticalOrder.objects.filter(
            status__in=[OpticalOrderStatus.ORDERED, OpticalOrderStatus.LAB_PROCESSING],
            is_deleted=False
        ).count(),
        'ready_orders': count(OpticalOrderStatus.READY),
        'recent_orders': OpticalOrder.objects.filter(is_deleted=False).select_related(
            'patient', 'frame', 'lens'
        ).order_by('-ordered_date')[:15],
        'pipeline_stages': pipeline_stages,
        'waiting_visits': waiting_visits,
        'today': today,
    }
    return render(request, 'opticals/dashboard.html', context)


@login_required
def frame_list(request):
    frames = Frame.objects.filter(is_deleted=False).order_by('brand', 'model')
    return render(request, 'opticals/frame_list.html', {'frames': frames})


@login_required
def frame_create(request):
    from apps.accounts.models import UserRole
    if not (request.user.is_super_admin or request.user.is_medical_director or
            request.user.role in (UserRole.ADMIN, UserRole.OPTICAL_DISPENSER)):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    if request.method == 'POST':
        brand = request.POST.get('brand', '').strip()
        model = request.POST.get('model', '').strip()
        if not brand or not model:
            messages.error(request, 'Brand and model are required.')
        else:
            from decimal import Decimal, InvalidOperation
            def _dec(key, default=0):
                try:
                    return Decimal(request.POST.get(key, '') or default)
                except InvalidOperation:
                    return Decimal(default)
            frame = Frame.objects.create(
                brand=brand,
                model=model,
                color=request.POST.get('color', '').strip(),
                shape=request.POST.get('shape', ''),
                material=request.POST.get('material', '').strip(),
                sku=request.POST.get('sku', '').strip() or None,
                cost_price=_dec('cost_price'),
                selling_price=_dec('selling_price'),
                quantity_in_stock=int(request.POST.get('quantity_in_stock', 0) or 0),
                is_active=True,
                created_by=request.user,
            )
            messages.success(request, f'Frame "{frame}" added to catalogue.')
            return redirect('opticals:frame_list')
    from .models import FrameShape
    return render(request, 'opticals/frame_form.html', {'frame_shapes': FrameShape.choices})


@login_required
def frame_edit(request, frame_id):
    from apps.accounts.models import UserRole
    if not (request.user.is_super_admin or request.user.is_medical_director or
            request.user.role in (UserRole.ADMIN, UserRole.OPTICAL_DISPENSER)):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    frame = get_object_or_404(Frame, id=frame_id, is_deleted=False)
    if request.method == 'POST':
        from decimal import Decimal, InvalidOperation
        def _dec(key, default=0):
            try:
                return Decimal(request.POST.get(key, '') or default)
            except InvalidOperation:
                return Decimal(default)
        frame.brand = request.POST.get('brand', frame.brand).strip()
        frame.model = request.POST.get('model', frame.model).strip()
        frame.color = request.POST.get('color', '').strip()
        frame.shape = request.POST.get('shape', '')
        frame.material = request.POST.get('material', '').strip()
        frame.sku = request.POST.get('sku', '').strip() or None
        frame.cost_price = _dec('cost_price', frame.cost_price)
        frame.selling_price = _dec('selling_price', frame.selling_price)
        frame.quantity_in_stock = int(request.POST.get('quantity_in_stock', frame.quantity_in_stock) or 0)
        frame.is_active = 'is_active' in request.POST
        frame.save()
        messages.success(request, f'Frame "{frame}" updated.')
        return redirect('opticals:frame_list')
    from .models import FrameShape
    return render(request, 'opticals/frame_form.html', {'frame': frame, 'frame_shapes': FrameShape.choices})


@login_required
def lens_list(request):
    lenses = Lens.objects.filter(is_deleted=False).order_by('name')
    return render(request, 'opticals/lens_list.html', {'lenses': lenses})


@login_required
def lens_create(request):
    from apps.accounts.models import UserRole
    if not (request.user.is_super_admin or request.user.is_medical_director or
            request.user.role in (UserRole.ADMIN, UserRole.OPTICAL_DISPENSER)):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        lens_type = request.POST.get('lens_type', '').strip()
        if not name or not lens_type:
            messages.error(request, 'Name and lens type are required.')
        else:
            from decimal import Decimal, InvalidOperation
            def _dec(key, default=0):
                try:
                    return Decimal(request.POST.get(key, '') or default)
                except InvalidOperation:
                    return Decimal(default)
            lens = Lens.objects.create(
                name=name,
                lens_type=lens_type,
                material=request.POST.get('material', '').strip(),
                coating=request.POST.get('coating', '').strip(),
                cost_price=_dec('cost_price'),
                selling_price=_dec('selling_price'),
                is_active=True,
                created_by=request.user,
            )
            messages.success(request, f'Lens "{lens}" added to catalogue.')
            return redirect('opticals:lens_list')
    return render(request, 'opticals/lens_form.html', {'lens_types': LensType.choices})


@login_required
def lens_edit(request, lens_id):
    from apps.accounts.models import UserRole
    if not (request.user.is_super_admin or request.user.is_medical_director or
            request.user.role in (UserRole.ADMIN, UserRole.OPTICAL_DISPENSER)):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    lens = get_object_or_404(Lens, id=lens_id, is_deleted=False)
    if request.method == 'POST':
        from decimal import Decimal, InvalidOperation
        def _dec(key, default=0):
            try:
                return Decimal(request.POST.get(key, '') or default)
            except InvalidOperation:
                return Decimal(default)
        lens.name = request.POST.get('name', lens.name).strip()
        lens.lens_type = request.POST.get('lens_type', lens.lens_type)
        lens.material = request.POST.get('material', '').strip()
        lens.coating = request.POST.get('coating', '').strip()
        lens.cost_price = _dec('cost_price', lens.cost_price)
        lens.selling_price = _dec('selling_price', lens.selling_price)
        lens.is_active = 'is_active' in request.POST
        lens.save()
        messages.success(request, f'Lens "{lens}" updated.')
        return redirect('opticals:lens_list')
    return render(request, 'opticals/lens_form.html', {'lens': lens, 'lens_types': LensType.choices})


@login_required
def create_order(request):
    frames = Frame.objects.filter(is_active=True, is_deleted=False, quantity_in_stock__gt=0).order_by('brand', 'model')
    lenses = Lens.objects.filter(is_active=True, is_deleted=False).order_by('name')

    if request.method == 'POST':
        from apps.patients.models import Patient
        from apps.prescriptions.models import OpticalPrescription

        patient_id = request.POST.get('patient_id')
        if not patient_id:
            messages.error(request, 'Please select a patient.')
            return render(request, 'opticals/create_order.html', {'frames': frames, 'lenses': lenses})

        patient = get_object_or_404(Patient, id=patient_id, is_deleted=False)
        rx_id = request.POST.get('prescription_id')
        rx = OpticalPrescription.objects.filter(id=rx_id).first() if rx_id else None

        frame_id = request.POST.get('frame_id')
        lens_id = request.POST.get('lens_id')
        frame = Frame.objects.filter(id=frame_id, is_deleted=False).first() if frame_id else None
        lens = Lens.objects.filter(id=lens_id, is_deleted=False).first() if lens_id else None

        try:
            frame_price = float(request.POST.get('frame_price') or (frame.selling_price if frame else 0))
            lens_price = float(request.POST.get('lens_price') or (lens.selling_price if lens else 0))
            fitting_charge = float(request.POST.get('fitting_charge') or 0)
        except (ValueError, TypeError):
            frame_price = lens_price = fitting_charge = 0

        order = OpticalOrder.objects.create(
            patient=patient,
            optical_prescription=rx,
            frame=frame,
            lens=lens,
            frame_price=frame_price,
            lens_price=lens_price,
            fitting_charge=fitting_charge,
            special_instructions=request.POST.get('special_instructions', ''),
            expected_date=request.POST.get('expected_date') or None,
            deposit_paid=request.POST.get('deposit_paid') or 0,
            created_by=request.user,
        )

        # Mark linked prescription as dispensed as soon as an order is placed
        if rx:
            rx.is_dispensed = True
            rx.save(update_fields=['is_dispensed'])

        # Deduct frame stock
        if frame:
            frame.quantity_in_stock = max(0, frame.quantity_in_stock - 1)
            frame.save(update_fields=['quantity_in_stock'])
            # Low stock alert when frame runs out
            if frame.quantity_in_stock == 0:
                try:
                    from apps.notifications.utils import notify
                    from apps.notifications.models import NotificationType, NotificationPriority
                    from apps.accounts.models import UserRole as _UR
                    for mgr in __import__('apps.accounts.models', fromlist=['User']).User.objects.filter(
                        role__in=[_UR.OPTICAL_DISPENSER, _UR.MEDICAL_DIRECTOR, _UR.ADMIN],
                        is_active=True,
                    ):
                        notify(
                            recipient=mgr,
                            title=f'Frame out of stock — {frame}',
                            message=f'The last unit of "{frame}" was just dispensed. Current stock: 0. Please reorder.',
                            link='/opticals/frames/',
                            notification_type=NotificationType.GENERAL,
                            priority=NotificationPriority.HIGH,
                        )
                except Exception:
                    pass

        # ── Auto-billing: add optical items to patient invoice ────────────────
        try:
            from apps.billing.utils import add_billing_item
            from apps.billing.models import ServiceCategory
            if frame_price > 0:
                add_billing_item(
                    patient=patient,
                    description=f'Frame — {frame}' if frame else 'Spectacle Frame',
                    category=ServiceCategory.OPTICAL,
                    unit_price=frame_price,
                    created_by=request.user,
                )
            if lens_price > 0:
                add_billing_item(
                    patient=patient,
                    description=f'Lenses — {lens}' if lens else 'Prescription Lenses',
                    category=ServiceCategory.OPTICAL,
                    unit_price=lens_price,
                    created_by=request.user,
                )
            if fitting_charge > 0:
                add_billing_item(
                    patient=patient,
                    description='Lens Fitting Charge',
                    category=ServiceCategory.OPTICAL,
                    unit_price=fitting_charge,
                    created_by=request.user,
                )
        except Exception:
            pass  # Billing failure must not block the optical order

        # ── Record initial payment transaction if money was collected ────────
        collection_mode = request.POST.get('collection_mode', 'deposit')
        initial_deposit = float(request.POST.get('deposit_paid') or 0)
        if initial_deposit > 0 or collection_mode == 'now':
            try:
                from apps.billing.models import Payment, PaymentMethod
                from apps.billing.utils import get_or_create_today_invoice
                pay_amount = order.total_amount if collection_mode == 'now' else initial_deposit
                if pay_amount > 0:
                    _invoice = get_or_create_today_invoice(patient, created_by=request.user)
                    _method = request.POST.get('payment_method', PaymentMethod.CASH)
                    Payment.objects.create(
                        invoice=_invoice,
                        payment_method=_method,
                        amount=pay_amount,
                        reference=request.POST.get('reference', '').strip(),
                        notes=f'Optical Order {order.order_number}',
                        received_by=request.user,
                        created_by=request.user,
                    )
            except Exception:
                pass

        # ── "Pay in Full & Take Now" — auto-deliver if fully paid and in stock ──
        if collection_mode == 'now':
            order.status = OpticalOrderStatus.DELIVERED
            order.delivered_date = timezone.localdate()
            order.delivered_to = request.user
            order.save(update_fields=['status', 'delivered_date', 'delivered_to'])
            # Complete the visit
            try:
                from apps.patients.models import Visit
                visit = Visit.objects.filter(
                    patient=patient, status='OPTICAL', is_deleted=False,
                ).order_by('-visit_date').first()
                if visit:
                    visit.status = 'COMPLETED'
                    visit.save(update_fields=['status', 'updated_at'])
            except Exception:
                pass
            messages.success(
                request,
                f'Optical order {order.order_number} — payment collected and glasses handed over to {patient.full_name}.'
            )
        else:
            messages.success(request, f'Optical order {order.order_number} created and billed.')
        return redirect('opticals:order_detail', order_id=order.id)

    # Pre-fill patient and prescription from query params
    patient = None
    rx = None
    patient_id = request.GET.get('patient')
    rx_id = request.GET.get('prescription')
    if patient_id:
        from apps.patients.models import Patient
        from apps.prescriptions.models import OpticalPrescription
        patient = Patient.objects.filter(id=patient_id, is_deleted=False).first()
        if patient:
            if rx_id:
                rx = OpticalPrescription.objects.filter(
                    id=rx_id, patient=patient, is_deleted=False
                ).first()
            if not rx:
                rx = OpticalPrescription.objects.filter(
                    patient=patient, is_deleted=False
                ).order_by('-created_at').first()

    return render(request, 'opticals/create_order.html', {
        'frames': frames, 'lenses': lenses, 'patient': patient, 'rx': rx,
    })


@login_required
def order_list(request):
    orders = list(OpticalOrder.objects.filter(is_deleted=False).select_related('patient', 'frame', 'lens').order_by('-ordered_date'))
    return render(request, 'opticals/order_list.html', {'orders': orders, 'show_unpaid': False})


@login_required
def order_list_unpaid(request):
    """Outstanding optical orders — dedicated URL avoids HTMX hx-boost dropping query params."""
    all_orders = OpticalOrder.objects.filter(is_deleted=False).select_related('patient', 'frame', 'lens').order_by('-ordered_date')
    orders = [o for o in all_orders if o.balance_due > 0 and o.status != OpticalOrderStatus.CANCELLED]
    return render(request, 'opticals/order_list.html', {'orders': orders, 'show_unpaid': True})


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(OpticalOrder, id=order_id, is_deleted=False)
    from apps.billing.models import Payment
    payments = list(
        Payment.objects.filter(
            invoice__patient=order.patient,
            notes__icontains=order.order_number,
            is_deleted=False,
        ).select_related('received_by').order_by('payment_date')
    )
    # Only cashier/chief_cashier/medical_director/super_admin can collect optical payment.
    # Optical dispenser sees the order details but NOT the payment collection form.
    user = request.user
    can_collect_payment = (
        user.is_cashier or user.is_chief_cashier or
        user.is_medical_director or user.is_super_admin
    )
    return render(request, 'opticals/order_detail.html', {
        'order': order,
        'payments': payments,
        'can_collect_payment': can_collect_payment,
    })


@login_required
def update_order_status(request, order_id):
    user = request.user
    if not (user.is_optical_dispenser or user.is_cashier or user.is_chief_cashier
            or user.is_medical_director or user.is_super_admin):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    order = get_object_or_404(OpticalOrder, id=order_id, is_deleted=False)
    if request.method == 'POST':
        old_status = order.status
        order.status = request.POST.get('status', order.status)
        if order.status == OpticalOrderStatus.DELIVERED:
            order.delivered_date = timezone.localdate()
            order.delivered_to = request.user
            # Mark visit as COMPLETED when glasses are handed to patient
            try:
                from apps.patients.models import Visit
                visit = Visit.objects.filter(
                    patient=order.patient,
                    status='OPTICAL',
                    is_deleted=False,
                ).order_by('-visit_date').first()
                if visit:
                    visit.status = 'COMPLETED'
                    visit.save(update_fields=['status', 'updated_at'])
            except Exception:
                pass
            # Mark linked prescription as dispensed
            if order.optical_prescription:
                order.optical_prescription.is_dispensed = True
                order.optical_prescription.save(update_fields=['is_dispensed'])
        order.save()
        # Notify ordering doctor when order is ready for collection
        if order.status == OpticalOrderStatus.READY and old_status != OpticalOrderStatus.READY:
            try:
                from apps.notifications.utils import notify
                from apps.notifications.models import NotificationType, NotificationPriority
                doctor = getattr(order.optical_prescription, 'prescribed_by', None) if order.optical_prescription else None
                if doctor:
                    notify(
                        recipient=doctor,
                        title=f'Optical glasses ready — {order.patient.full_name}',
                        message=f'Order {order.order_number} is ready for collection at the optical shop.',
                        link=f'/opticals/orders/{order.id}/',
                        notification_type=NotificationType.GENERAL,
                        priority=NotificationPriority.NORMAL,
                    )
            except Exception:
                pass
        messages.success(request, 'Order status updated.')
        return redirect('opticals:order_detail', order_id=order.id)
    return render(request, 'opticals/update_status.html', {
        'order': order,
        'statuses': OpticalOrderStatus.choices,
    })


@login_required
@require_POST
def collect_payment(request, order_id):
    """
    Optical cashier collects payment — only cashier/chief_cashier/super_admin/medical_director allowed.
    Dispenser creates orders and prints quotes; cashier handles money.
    """
    from decimal import Decimal, InvalidOperation
    from apps.billing.models import Payment, PaymentMethod, InvoiceStatus, ServiceCategory
    from apps.billing.utils import get_or_create_today_invoice, add_billing_item
    from django.http import HttpResponseForbidden

    user = request.user
    if not (user.is_cashier or user.is_chief_cashier or user.is_medical_director or user.is_super_admin):
        messages.error(request, 'Only the optical cashier can collect payments.')
        return redirect('opticals:order_detail', order_id=order_id)

    order = get_object_or_404(OpticalOrder, id=order_id, is_deleted=False)

    from apps.accounts.models import UserRole

    payment_method = request.POST.get('payment_method', PaymentMethod.CASH)
    amount_str = request.POST.get('amount', '').strip()
    try:
        amount = Decimal(amount_str) if amount_str else Decimal(str(order.balance_due))
    except InvalidOperation:
        messages.error(request, 'Invalid payment amount.')
        return redirect('opticals:order_detail', order_id=order.id)

    if amount <= 0:
        messages.error(request, 'Payment amount must be greater than zero.')
        return redirect('opticals:order_detail', order_id=order.id)

    # Build invoice items for optical order (idempotent — only add if not already billed)
    invoice = get_or_create_today_invoice(order.patient, created_by=request.user)
    existing_optical_items = invoice.items.filter(
        category=ServiceCategory.OPTICAL, is_deleted=False
    )
    if not existing_optical_items.exists():
        if order.frame_price and order.frame_price > 0:
            add_billing_item(
                patient=order.patient,
                description=f'Frame — {order.frame}' if order.frame else 'Spectacle Frame',
                category=ServiceCategory.OPTICAL,
                unit_price=order.frame_price,
                created_by=request.user,
            )
        if order.lens_price and order.lens_price > 0:
            add_billing_item(
                patient=order.patient,
                description=f'Lenses — {order.lens}' if order.lens else 'Prescription Lenses',
                category=ServiceCategory.OPTICAL,
                unit_price=order.lens_price,
                created_by=request.user,
            )
        if order.fitting_charge and order.fitting_charge > 0:
            add_billing_item(
                patient=order.patient,
                description='Lens Fitting',
                category=ServiceCategory.OPTICAL,
                unit_price=order.fitting_charge,
                created_by=request.user,
            )

    # Record payment at optical counter
    Payment.objects.create(
        invoice=invoice,
        payment_method=payment_method,
        amount=amount,
        reference=request.POST.get('reference', '').strip(),
        notes=f'Optical Order {order.order_number}',
        received_by=request.user,
        created_by=request.user,
    )

    # Update deposit_paid on the optical order
    order.deposit_paid = (order.deposit_paid or 0) + amount
    order.save(update_fields=['deposit_paid'])

    messages.success(
        request,
        f'Payment of {int(amount):,} FCFA collected at optical counter for order {order.order_number}.'
    )
    return redirect('opticals:order_detail', order_id=order.id)


@login_required
@require_POST
def frame_receive_stock(request, frame_id):
    """Receive a new batch of frames — increments quantity_in_stock."""
    from apps.accounts.models import UserRole
    if not (request.user.is_super_admin or request.user.is_medical_director or
            request.user.role in (UserRole.ADMIN, UserRole.OPTICAL_DISPENSER)):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    frame = get_object_or_404(Frame, id=frame_id, is_deleted=False)
    try:
        qty = int(request.POST.get('quantity', 0) or 0)
    except (ValueError, TypeError):
        qty = 0
    if qty <= 0:
        messages.error(request, 'Quantity received must be a positive number.')
        return redirect('opticals:frame_list')
    frame.quantity_in_stock += qty
    frame.save(update_fields=['quantity_in_stock'])
    messages.success(request, f'+{qty} units of "{frame}" added to stock. New stock: {frame.quantity_in_stock}.')
    return redirect('opticals:frame_list')


@login_required
def order_receipt(request, order_id):
    """Printable optical order receipt for patient."""
    order = get_object_or_404(OpticalOrder, id=order_id, is_deleted=False)
    return render(request, 'opticals/order_receipt.html', {'order': order})


@login_required
def order_quotation(request, order_id):
    """Printable price quotation slip — given to patient to take to the cashier."""
    order = get_object_or_404(OpticalOrder, id=order_id, is_deleted=False)
    from apps.accounts.models import HospitalConfig
    hospital = HospitalConfig.get()
    return render(request, 'opticals/order_quotation.html', {'order': order, 'hospital': hospital})


@login_required
@require_POST
def quick_update_status(request, order_id):
    """AJAX quick status update from dashboard (Mark Ready / Mark Delivered)."""
    from django.http import JsonResponse
    if not (request.user.is_optical_dispenser or request.user.is_super_admin or request.user.is_medical_director):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    order = get_object_or_404(OpticalOrder, id=order_id, is_deleted=False)
    new_status = request.POST.get('status', '').strip()
    allowed = ['LAB', 'READY', 'DELIVERED']
    if new_status not in allowed:
        return JsonResponse({'error': 'Invalid status'}, status=400)
    order.status = new_status
    if new_status == OpticalOrderStatus.DELIVERED:
        order.delivered_date = timezone.localdate()
        order.delivered_to = request.user
    order.save(update_fields=['status', 'updated_at'] + (['delivered_date', 'delivered_to'] if new_status == OpticalOrderStatus.DELIVERED else []))
    return JsonResponse({'success': True, 'status': order.get_status_display()})


@login_required
def optical_stats_view(request):
    """Monthly statistics for optical shop."""
    if not (request.user.is_optical_dispenser or request.user.is_medical_director
            or request.user.is_super_admin or request.user.is_ceo
            or request.user.is_admin_director):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    import json, calendar
    from datetime import date as _date, timedelta
    from django.db.models import Count, Sum, Q as _Q

    today = timezone.localdate()
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
        month_start = _date(year, month, 1)
    except (ValueError, TypeError):
        month_start = today.replace(day=1)
        year, month = month_start.year, month_start.month
    last_day  = calendar.monthrange(year, month)[1]
    month_end = _date(year, month, last_day)

    base = OpticalOrder.objects.filter(
        is_deleted=False,
        ordered_date__gte=month_start,
        ordered_date__lte=month_end,
    )

    total_orders    = base.count()
    delivered_count = base.filter(status=OpticalOrderStatus.DELIVERED).count()
    ready_count     = base.filter(status=OpticalOrderStatus.READY).count()
    lab_count       = base.filter(status=OpticalOrderStatus.LAB_PROCESSING).count()
    cancelled_count = base.filter(status=OpticalOrderStatus.CANCELLED).count()
    delivery_rate   = round(delivered_count / total_orders * 100, 1) if total_orders else 0

    revenue = base.filter(status=OpticalOrderStatus.DELIVERED).aggregate(
        total=Sum('total_amount')
    )['total'] or 0

    # Daily volume (last 14 days)
    daily_volume = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        cnt = OpticalOrder.objects.filter(is_deleted=False, ordered_date=d).count()
        daily_volume.append({'date': d.strftime('%d %b'), 'count': cnt})
    daily_json = json.dumps({'labels': [d['date'] for d in daily_volume], 'data': [d['count'] for d in daily_volume]})

    # Status breakdown
    status_json = json.dumps({
        'labels': ['Delivered', 'Ready', 'At Lab', 'Ordered', 'Cancelled'],
        'data':   [delivered_count, ready_count, lab_count,
                   total_orders - delivered_count - ready_count - lab_count - cancelled_count,
                   cancelled_count],
    })

    # Gender
    gender_raw = base.values('patient__gender').annotate(count=Count('id'))
    gender_map = {g['patient__gender']: g['count'] for g in gender_raw}
    male_count, female_count = gender_map.get('M', 0), gender_map.get('F', 0)
    gender_json = json.dumps([
        {'label': 'Male',   'count': male_count},
        {'label': 'Female', 'count': female_count},
    ])

    # Top frames
    top_frames = list(
        base.filter(frame__isnull=False)
        .values('frame__name', 'frame__brand')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )

    # Month nav
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1)  if month == 12 else (year, month + 1)

    context = {
        'year': year, 'month': month,
        'month_name': _date(year, month, 1).strftime('%B %Y'),
        'prev_year': prev_year, 'prev_month': prev_month,
        'next_year': next_year, 'next_month': next_month,
        'total_orders': total_orders,
        'delivered_count': delivered_count,
        'ready_count': ready_count,
        'lab_count': lab_count,
        'cancelled_count': cancelled_count,
        'delivery_rate': delivery_rate,
        'revenue': revenue,
        'daily_json': daily_json,
        'status_json': status_json,
        'gender_json': gender_json,
        'male_count': male_count,
        'female_count': female_count,
        'top_frames': top_frames,
        'today': today,
    }
    return render(request, 'opticals/stats.html', context)


@login_required
def patient_search(request):
    """Optical patient search — find patient and see their optical history."""
    from django.db.models import Q
    from apps.patients.models import Patient
    from apps.prescriptions.models import OpticalPrescription

    q = request.GET.get('q', '').strip()
    results = []
    if q:
        from apps.core.utils import patient_search_q
        patients = list(Patient.objects.filter(
            patient_search_q(q), is_deleted=False,
        ).order_by('last_name', 'first_name')[:15])
        for patient in patients:
            active_orders = list(
                OpticalOrder.objects.filter(patient=patient, is_deleted=False)
                .exclude(status=OpticalOrderStatus.CANCELLED)
                .select_related('frame', 'lens')
                .order_by('-ordered_date')[:5]
            )
            recent_rx = list(
                OpticalPrescription.objects.filter(patient=patient, is_deleted=False)
                .select_related('prescribed_by')
                .order_by('-prescription_date')[:3]
            )
            results.append({
                'patient': patient,
                'active_orders': active_orders,
                'recent_rx': recent_rx,
            })
    return render(request, 'opticals/patient_search.html', {'q': q, 'results': results})
