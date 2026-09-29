from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db.models import F
from django.utils import timezone
from .models import (
    Frame, Lens, LensType, OpticalOrder, OpticalOrderStatus,
    ContactLensFitting, LowVisionAidDispensing, LensPriceMatrix,
    CoatingType, PowerBand, OpticalWarranty, WarrantyStatus,
    OpticalRepair, RepairType, RepairStatus,
    FrameSupplier, FrameGoodsReceived, FrameGRNStatus, FrameGRNItem,
    FrameStocktake, FrameStocktakeStatus, FrameStocktakeItem,
    FrameMinStockAlert,
)


def _can_access_optical(user):
    """Optical shop, cashiers collecting optical payments, store keeper, and admin roles."""
    from apps.accounts.models import UserRole
    return user.role in (
        UserRole.OPTICAL_DISPENSER, UserRole.OPTOMETRIST, UserRole.ORTHOPTIST,
        UserRole.LOW_VISION_SPECIALIST, UserRole.CASHIER, UserRole.CHIEF_CASHIER,
        UserRole.STORE_KEEPER, UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR,
        UserRole.MEDICAL_DIRECTOR, UserRole.CEO, UserRole.ADMIN,
    )


@login_required
def dashboard(request):
    if not _can_access_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Access denied — optical shop roles only.')
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
    _tier_order = Case(When(service_tier='VIP', then=_V(3)),
                       When(service_tier='EXPRESS', then=_V(2)), default=_V(0), output_field=IntegerField())
    _pt = getattr(request.user, 'patient_tier', 'ALL')
    _opt_qs = Visit.objects.filter(visit_date__date=today, status='OPTICAL', is_deleted=False)
    if _pt == 'VIP':
        _opt_qs = _opt_qs.filter(service_tier='VIP')
    elif _pt == 'EXPRESS':
        _opt_qs = _opt_qs.filter(service_tier='EXPRESS')
    elif _pt == 'STANDARD':
        _opt_qs = _opt_qs.filter(service_tier='STANDARD')
    # _pt == 'ALL' → no filter
    waiting_visits = list(
        _opt_qs.select_related('patient', 'attending_doctor')
        .annotate(_tier_order=_tier_order).order_by('-_tier_order', 'visit_date')
    )

    # Uncollected aging alert
    from datetime import timedelta
    ready_qs = OpticalOrder.objects.filter(status=OpticalOrderStatus.READY, is_deleted=False)
    uncollected_total = ready_qs.count()
    overdue_14 = sum(
        1 for o in ready_qs.only('expected_date', 'ordered_date')
        if (today - (o.expected_date or (o.ordered_date + timedelta(days=3)))).days > 14
    )

    # Dashboard enhancements: this month stats
    from django.db.models import Sum, Count
    month_start = today.replace(day=1)
    month_orders = OpticalOrder.objects.filter(
        is_deleted=False, ordered_date__gte=month_start, ordered_date__lte=today,
    )
    month_total = month_orders.count()
    month_delivered = month_orders.filter(status=OpticalOrderStatus.DELIVERED).count()
    month_revenue = month_orders.filter(status=OpticalOrderStatus.DELIVERED).aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    conversion_rate = round(month_delivered / month_total * 100, 1) if month_total else 0

    # Top 5 frames this month
    top_frames = list(
        month_orders.filter(frame__isnull=False)
        .values('frame__brand', 'frame__model')
        .annotate(count=Count('id'))
        .order_by('-count')[:5]
    )

    # Stock value: frames
    frame_stock_value = Frame.objects.filter(
        is_active=True, is_deleted=False, quantity_in_stock__gt=0
    ).aggregate(val=Sum(F('selling_price') * F('quantity_in_stock')))['val'] or 0

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
        'uncollected_total': uncollected_total,
        'overdue_14': overdue_14,
        'month_revenue': month_revenue,
        'conversion_rate': conversion_rate,
        'top_frames': top_frames,
        'frame_stock_value': frame_stock_value,
        'today': today,
    }
    return render(request, 'opticals/dashboard.html', context)


@login_required
def frame_list(request):
    if not _can_access_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
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
    if not _can_access_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
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

        # Parse measurement fields
        def _dec_field(name):
            v = request.POST.get(name, '').strip()
            if v:
                try:
                    return float(v)
                except (ValueError, TypeError):
                    pass
            return None

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
            mono_pd_re=_dec_field('mono_pd_re'),
            mono_pd_le=_dec_field('mono_pd_le'),
            fitting_height_re=_dec_field('fitting_height_re'),
            fitting_height_le=_dec_field('fitting_height_le'),
            vertex_distance=_dec_field('vertex_distance'),
            pantoscopic_tilt=_dec_field('pantoscopic_tilt'),
            wrap_angle=_dec_field('wrap_angle'),
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
    if not _can_access_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    orders = list(OpticalOrder.objects.filter(is_deleted=False).select_related('patient', 'frame', 'lens').order_by('-ordered_date'))
    return render(request, 'opticals/order_list.html', {'orders': orders, 'show_unpaid': False})


@login_required
def order_list_unpaid(request):
    """Outstanding optical orders — dedicated URL avoids HTMX hx-boost dropping query params."""
    if not _can_access_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    all_orders = OpticalOrder.objects.filter(is_deleted=False).select_related('patient', 'frame', 'lens').order_by('-ordered_date')
    orders = [o for o in all_orders if o.balance_due > 0 and o.status != OpticalOrderStatus.CANCELLED]
    return render(request, 'opticals/order_list.html', {'orders': orders, 'show_unpaid': True})


@login_required
def order_detail(request, order_id):
    if not _can_access_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
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
            # Auto-create warranty
            try:
                from datetime import timedelta
                if not hasattr(order, 'warranty'):
                    OpticalWarranty.objects.create(
                        order=order,
                        start_date=timezone.localdate(),
                        end_date=timezone.localdate() + timedelta(days=365),
                        created_by=request.user,
                    )
            except Exception:
                pass
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
        # Restore frame stock on cancellation
        if order.status == OpticalOrderStatus.CANCELLED and old_status != OpticalOrderStatus.CANCELLED:
            if order.frame_id:
                Frame.objects.filter(id=order.frame_id).update(
                    quantity_in_stock=F('quantity_in_stock') + 1
                )
            # Un-mark Rx so it can be re-dispensed
            if order.optical_prescription:
                order.optical_prescription.is_dispensed = False
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
    if not _can_access_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    order = get_object_or_404(OpticalOrder, id=order_id, is_deleted=False)
    return render(request, 'opticals/order_receipt.html', {'order': order})


@login_required
def order_quotation(request, order_id):
    """Printable price quotation slip — given to patient to take to the cashier."""
    if not _can_access_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
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
    # On delivery: mark visit COMPLETED + Rx dispensed
    if new_status == OpticalOrderStatus.DELIVERED:
        try:
            from apps.patients.models import Visit
            visit = Visit.objects.filter(
                patient=order.patient, status='OPTICAL', is_deleted=False,
            ).order_by('-visit_date').first()
            if visit:
                visit.status = 'COMPLETED'
                visit.save(update_fields=['status', 'updated_at'])
        except Exception:
            pass
        if order.optical_prescription:
            order.optical_prescription.is_dispensed = True
            order.optical_prescription.save(update_fields=['is_dispensed'])
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

    # Top frames — Frame model uses 'model' + 'brand' fields (no 'name' field)
    top_frames = list(
        base.filter(frame__isnull=False)
        .values('frame__model', 'frame__brand')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )

    # Tier breakdown — join to same-day visit
    try:
        from apps.patients.models import Visit
        from django.db.models import OuterRef, Subquery, CharField
        tier_subq = Visit.objects.filter(
            patient=OuterRef('patient'),
            visit_date__date=OuterRef('ordered_date'),
            is_deleted=False,
        ).order_by('-visit_date').values('service_tier')[:1]
        tier_raw = (
            base.annotate(tier=Subquery(tier_subq, output_field=CharField()))
            .values('tier')
            .annotate(count=Count('id'))
        )
        tier_map = {row['tier'] or 'STANDARD': row['count'] for row in tier_raw}
        tier_stats = [
            {'label': 'Standard',   'key': 'STANDARD',   'color': '#0d6efd', 'count': tier_map.get('STANDARD', 0)},
            {'label': 'Express',    'key': 'EXPRESS',    'color': '#fd7e14', 'count': tier_map.get('EXPRESS', 0)},
            {'label': 'VIP',        'key': 'VIP',        'color': '#6f42c1', 'count': tier_map.get('VIP', 0)},
        ]
        tier_json = json.dumps({
            'labels': [t['label'] for t in tier_stats],
            'data':   [t['count'] for t in tier_stats],
            'colors': [t['color'] for t in tier_stats],
        })
    except Exception:
        tier_stats = []
        tier_json  = json.dumps({'labels': [], 'data': [], 'colors': []})

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
        'tier_stats': tier_stats,
        'tier_json': tier_json,
        'today': today,
    }
    if request.GET.get('pdf'):
        from apps.reports.views import render_pdf
        context['pdf_filename'] = 'opticals-stats.pdf'
        return render_pdf('opticals/stats_pdf.html', context)
    return render(request, 'opticals/stats.html', context)


@login_required
def patient_search(request):
    """Optical patient search — find patient and see their optical history."""
    if not _can_access_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
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


# ── Contact Lens Fitting ──────────────────────────────────────────────────────

@login_required
def cl_fitting_list(request):
    """All contact lens fittings — orthoptist / optometrist view."""
    from apps.accounts.models import UserRole
    allowed = {UserRole.ORTHOPTIST, UserRole.OPTOMETRIST, UserRole.LOW_VISION_SPECIALIST,
               UserRole.SUPER_ADMIN, UserRole.MEDICAL_DIRECTOR, UserRole.OPTICAL_DISPENSER}
    if request.user.role not in allowed:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    fittings = ContactLensFitting.objects.filter(is_deleted=False).select_related(
        'patient', 'fitted_by', 'optical_prescription'
    ).order_by('-fitting_date')

    follow_up_due = fittings.filter(
        next_follow_up__lte=timezone.localdate(),
        next_follow_up__isnull=False,
    ).count()

    return render(request, 'opticals/cl_fitting_list.html', {
        'fittings': fittings[:100],
        'follow_up_due': follow_up_due,
    })


@login_required
def cl_fitting_create(request, patient_id=None):
    """Create a new contact lens fitting record."""
    from apps.accounts.models import UserRole
    allowed = {UserRole.ORTHOPTIST, UserRole.OPTOMETRIST, UserRole.SUPER_ADMIN, UserRole.MEDICAL_DIRECTOR}
    if request.user.role not in allowed:
        messages.error(request, 'Only orthoptists and optometrists can record contact lens fittings.')
        return redirect('opticals:cl_fitting_list')

    from apps.patients.models import Patient
    from apps.prescriptions.models import OpticalPrescription

    patient = None
    if patient_id:
        patient = get_object_or_404(Patient, id=patient_id)

    if request.method == 'POST':
        patient = get_object_or_404(Patient, id=request.POST.get('patient'))
        rx_id = request.POST.get('optical_prescription')
        optical_rx = OpticalPrescription.objects.filter(id=rx_id).first() if rx_id else None

        def decimal_or_none(val):
            if not val:
                return None
            try:
                from decimal import Decimal
                return Decimal(val)
            except Exception:
                return None

        import datetime
        fitting = ContactLensFitting.objects.create(
            patient=patient,
            fitted_by=request.user,
            optical_prescription=optical_rx,
            lens_type=request.POST.get('lens_type', ''),
            brand=request.POST.get('brand', ''),
            fitting_date=request.POST.get('fitting_date') or timezone.localdate(),
            # RE params
            re_sphere=decimal_or_none(request.POST.get('re_sphere')),
            re_cylinder=decimal_or_none(request.POST.get('re_cylinder')),
            re_axis=request.POST.get('re_axis') or None,
            re_add=decimal_or_none(request.POST.get('re_add')),
            re_base_curve=decimal_or_none(request.POST.get('re_base_curve')),
            re_diameter=decimal_or_none(request.POST.get('re_diameter')),
            # LE params
            le_sphere=decimal_or_none(request.POST.get('le_sphere')),
            le_cylinder=decimal_or_none(request.POST.get('le_cylinder')),
            le_axis=request.POST.get('le_axis') or None,
            le_add=decimal_or_none(request.POST.get('le_add')),
            le_base_curve=decimal_or_none(request.POST.get('le_base_curve')),
            le_diameter=decimal_or_none(request.POST.get('le_diameter')),
            # Dispensing
            quantity_dispensed=int(request.POST.get('quantity_dispensed', 1)),
            price_per_unit=decimal_or_none(request.POST.get('price_per_unit')) or 0,
            care_solution_included='care_solution_included' in request.POST,
            care_solution_price=decimal_or_none(request.POST.get('care_solution_price')) or 0,
            # Follow-up
            next_follow_up=request.POST.get('next_follow_up') or None,
            fitting_assessment=request.POST.get('fitting_assessment', ''),
            over_refraction_va=request.POST.get('over_refraction_va', ''),
            patient_education_given='patient_education_given' in request.POST,
            is_successful='is_successful' in request.POST,
            follow_up_notes=request.POST.get('follow_up_notes', ''),
        )
        messages.success(request, f'Contact lens fitting {fitting.fitting_number} recorded.')
        return redirect('opticals:cl_fitting_list')

    from apps.prescriptions.models import OpticalPrescription
    rxs = OpticalPrescription.objects.filter(
        patient=patient, is_deleted=False
    ).order_by('-prescription_date')[:10] if patient else []

    from .models import ContactLensType
    return render(request, 'opticals/cl_fitting_form.html', {
        'patient': patient,
        'lens_types': ContactLensType.choices,
        'rxs': rxs,
        'today': timezone.localdate(),
    })


# ── Low Vision Aid Dispensing ─────────────────────────────────────────────────

@login_required
def lva_dispensing_list(request):
    """All low vision aid dispensings — LV specialist view."""
    from apps.accounts.models import UserRole
    allowed = {UserRole.LOW_VISION_SPECIALIST, UserRole.ORTHOPTIST, UserRole.OPTOMETRIST,
               UserRole.SUPER_ADMIN, UserRole.MEDICAL_DIRECTOR}
    if request.user.role not in allowed:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    dispensings = LowVisionAidDispensing.objects.filter(is_deleted=False).select_related(
        'patient', 'dispensed_by'
    ).order_by('-dispensing_date')

    return render(request, 'opticals/lva_dispensing_list.html', {
        'dispensings': dispensings[:100],
    })


@login_required
def lva_dispensing_create(request, patient_id=None):
    """Record a low vision aid dispensing."""
    from apps.accounts.models import UserRole
    allowed = {UserRole.LOW_VISION_SPECIALIST, UserRole.ORTHOPTIST, UserRole.SUPER_ADMIN, UserRole.MEDICAL_DIRECTOR}
    if request.user.role not in allowed:
        messages.error(request, 'Only low vision specialists can record LVA dispensings.')
        return redirect('opticals:lva_dispensing_list')

    from apps.patients.models import Patient

    patient = get_object_or_404(Patient, id=patient_id) if patient_id else None

    if request.method == 'POST':
        patient = get_object_or_404(Patient, id=request.POST.get('patient'))

        def decimal_or_none(val):
            if not val:
                return None
            try:
                from decimal import Decimal
                return Decimal(val)
            except Exception:
                return None

        dispensing = LowVisionAidDispensing.objects.create(
            patient=patient,
            dispensed_by=request.user,
            dispensing_date=request.POST.get('dispensing_date') or timezone.localdate(),
            distance_va_re=request.POST.get('distance_va_re', ''),
            distance_va_le=request.POST.get('distance_va_le', ''),
            near_va_re=request.POST.get('near_va_re', ''),
            near_va_le=request.POST.get('near_va_le', ''),
            vision_goal=request.POST.get('vision_goal', ''),
            aid_type=request.POST.get('aid_type', ''),
            aid_brand_model=request.POST.get('aid_brand_model', ''),
            magnification=request.POST.get('magnification', ''),
            va_achieved_with_aid=request.POST.get('va_achieved_with_aid', ''),
            unit_price=decimal_or_none(request.POST.get('unit_price')) or 0,
            quantity=int(request.POST.get('quantity', 1)),
            training_given=request.POST.get('training_given', ''),
            follow_up_date=request.POST.get('follow_up_date') or None,
            notes=request.POST.get('notes', ''),
            patient_satisfied='patient_satisfied' in request.POST,
        )
        messages.success(request, f'LVA dispensing {dispensing.dispensing_number} recorded.')
        return redirect('opticals:lva_dispensing_list')

    from .models import LowVisionAidType
    return render(request, 'opticals/lva_dispensing_form.html', {
        'patient': patient,
        'aid_types': LowVisionAidType.choices,
        'today': timezone.localdate(),
    })


# ── Optical Lab Job Card ──────────────────────────────────────────────────────

def _can_manage_optical(user):
    return user.role in ('optical_dispenser', 'store_keeper', 'super_admin', 'admin', 'admin_director', 'medical_director')


@login_required
def lab_job_queue(request):
    """Lab queue — shows all orders currently in the glazing/fabrication pipeline."""
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    from .models import OpticalLabJob, LabJobStatus
    status_filter = request.GET.get('status', '')
    qs = OpticalLabJob.objects.filter(is_deleted=False).select_related('order__patient', 'sent_by', 'received_by')
    if status_filter:
        qs = qs.filter(status=status_filter)
    else:
        qs = qs.exclude(status=LabJobStatus.COLLECTED)

    today = timezone.localdate()
    return render(request, 'opticals/lab_queue.html', {
        'jobs': qs[:200],
        'status_choices': LabJobStatus.choices,
        'status_filter': status_filter,
        'today': today,
    })


@login_required
def send_to_lab(request, order_id):
    """Send an optical order to the lab / mark as in fabrication."""
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    from .models import OpticalOrder, OpticalLabJob, LabJobStatus, OpticalOrderStatus
    order = get_object_or_404(OpticalOrder, id=order_id, is_deleted=False)

    if request.method == 'POST':
        job, _ = OpticalLabJob.objects.get_or_create(order=order)
        job.lab_name = request.POST.get('lab_name', 'In-House Glazing Lab').strip()
        job.job_number = request.POST.get('job_number', '').strip()
        job.sent_date = request.POST.get('sent_date') or timezone.localdate()
        job.expected_return_date = request.POST.get('expected_return_date') or None
        job.special_notes = request.POST.get('special_notes', '').strip()
        job.status = LabJobStatus.SENT
        job.sent_by = request.user
        job.save()

        order.status = OpticalOrderStatus.LAB_PROCESSING
        order.save(update_fields=['status'])

        messages.success(request, f'Order {order.order_number} sent to lab — Job #{job.job_number or "—"}.')
        return redirect('opticals:lab_job_queue')

    return render(request, 'opticals/lab_send_form.html', {
        'order': order,
        'today': timezone.localdate(),
    })


@login_required
def lab_job_action(request, job_id):
    """Mark a lab job as returned / ready / collected."""
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    from .models import OpticalLabJob, LabJobStatus, OpticalOrderStatus
    job = get_object_or_404(OpticalLabJob, id=job_id, is_deleted=False)
    action = request.POST.get('action', '')

    if action == 'returned':
        job.status = LabJobStatus.RETURNED
        job.actual_return_date = timezone.localdate()
        job.received_by = request.user
        job.save()
        messages.success(request, f'Job marked as returned from lab.')

    elif action == 'ready':
        # Require QC verification before marking as ready for collection
        if not job.order.qc_verified:
            messages.warning(request, f'Order {job.order.order_number} must pass QC verification before marking as ready.')
            return redirect('opticals:order_detail', order_id=job.order.id)
        job.status = LabJobStatus.READY
        job.order.status = OpticalOrderStatus.READY
        job.order.save(update_fields=['status'])
        job.save()
        # Notify ordering doctor
        try:
            from apps.notifications.utils import notify
            from apps.notifications.models import NotificationType, NotificationPriority
            doctor = getattr(job.order.optical_prescription, 'prescribed_by', None) if job.order.optical_prescription else None
            if doctor:
                notify(
                    recipient=doctor,
                    title=f'Optical glasses ready — {job.order.patient.full_name}',
                    message=f'Order {job.order.order_number} passed QC and is ready for collection.',
                    link=f'/opticals/orders/{job.order.id}/',
                    notification_type=NotificationType.GENERAL,
                    priority=NotificationPriority.NORMAL,
                )
        except Exception:
            pass
        messages.success(request, f'Order {job.order.order_number} is ready for collection.')

    elif action == 'collected':
        # Payment gate — warn (but allow override) if balance outstanding
        if job.order.balance_due > 0 and 'force_collect' not in request.POST:
            messages.warning(
                request,
                f'Order {job.order.order_number} has outstanding balance of {int(job.order.balance_due):,} FCFA. '
                f'Collect payment first or use the order detail page to force-deliver.'
            )
            return redirect('opticals:order_detail', order_id=job.order.id)
        job.status = LabJobStatus.COLLECTED
        job.order.status = OpticalOrderStatus.DELIVERED
        job.order.delivered_date = timezone.localdate()
        job.order.delivered_to = request.user
        job.order.save(update_fields=['status', 'delivered_date', 'delivered_to'])
        job.save()
        # Mark visit COMPLETED + Rx dispensed
        try:
            from apps.patients.models import Visit
            visit = Visit.objects.filter(
                patient=job.order.patient, status='OPTICAL', is_deleted=False,
            ).order_by('-visit_date').first()
            if visit:
                visit.status = 'COMPLETED'
                visit.save(update_fields=['status', 'updated_at'])
        except Exception:
            pass
        if job.order.optical_prescription:
            job.order.optical_prescription.is_dispensed = True
            job.order.optical_prescription.save(update_fields=['is_dispensed'])
        messages.success(request, f'Order {job.order.order_number} collected by patient.')

    elif action == 'cancel':
        job.status = LabJobStatus.CANCELLED
        job.order.status = OpticalOrderStatus.CANCELLED
        job.order.save(update_fields=['status'])
        job.save()
        # Restore frame stock
        if job.order.frame_id:
            Frame.objects.filter(id=job.order.frame_id).update(
                quantity_in_stock=F('quantity_in_stock') + 1
            )
        # Un-mark Rx
        if job.order.optical_prescription:
            job.order.optical_prescription.is_dispensed = False
            job.order.optical_prescription.save(update_fields=['is_dispensed'])
        messages.warning(request, 'Lab job cancelled — frame stock restored.')

    return redirect('opticals:lab_job_queue')


# ═══════════════════════════════════════════════════════════════════════════════
# QC VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def qc_verify(request, order_id):
    """
    QC verification step — dispenser checks power, alignment, cosmetic finish.
    Marks the order as QC-passed and records notes.
    """
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    order = get_object_or_404(OpticalOrder, id=order_id, is_deleted=False)
    notes = request.POST.get('qc_notes', '').strip()

    order.qc_verified = True
    order.qc_verified_by = request.user
    order.qc_verified_at = timezone.now()
    order.qc_notes = notes
    order.save(update_fields=['qc_verified', 'qc_verified_by', 'qc_verified_at', 'qc_notes'])

    messages.success(request, f'QC verification passed for order {order.order_number}.')
    return redirect('opticals:order_detail', order_id=order.id)


@login_required
@require_POST
def qc_fail(request, order_id):
    """Mark an order as QC-failed — needs rework."""
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    order = get_object_or_404(OpticalOrder, id=order_id, is_deleted=False)
    notes = request.POST.get('qc_notes', '').strip()

    order.qc_verified = False
    order.qc_verified_by = None
    order.qc_verified_at = None
    order.qc_notes = f'[QC FAILED] {notes}'
    order.save(update_fields=['qc_verified', 'qc_verified_by', 'qc_verified_at', 'qc_notes'])

    # Send back to lab
    try:
        from .models import OpticalLabJob, LabJobStatus
        job = order.lab_job
        if job.status in (LabJobStatus.RETURNED, LabJobStatus.READY):
            job.status = LabJobStatus.SENT
            job.save(update_fields=['status'])
            order.status = OpticalOrderStatus.LAB_PROCESSING
            order.save(update_fields=['status'])
    except Exception:
        pass

    messages.warning(request, f'QC failed for {order.order_number} — sent back to lab for rework.')
    return redirect('opticals:order_detail', order_id=order.id)


# ═══════════════════════════════════════════════════════════════════════════════
# UNCOLLECTED AGING REPORT
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def uncollected_orders(request):
    """
    Orders stuck in READY status — bucketed by age (7 / 14 / 30+ days).
    Helps optical shop follow up with patients who haven't collected their glasses.
    """
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    from datetime import timedelta
    today = timezone.localdate()
    ready_orders = list(
        OpticalOrder.objects.filter(
            status=OpticalOrderStatus.READY, is_deleted=False,
        ).select_related('patient', 'frame', 'lens')
        .order_by('ordered_date')
    )

    buckets = {'0_7': [], '8_14': [], '15_30': [], '31_plus': []}
    for o in ready_orders:
        # Age = days since the order was first marked READY
        # Use expected_date if set, else ordered_date + 3 days as proxy
        ready_since = o.expected_date or (o.ordered_date + timedelta(days=3))
        days_waiting = (today - ready_since).days
        o._days_waiting = max(0, days_waiting)
        if days_waiting <= 7:
            buckets['0_7'].append(o)
        elif days_waiting <= 14:
            buckets['8_14'].append(o)
        elif days_waiting <= 30:
            buckets['15_30'].append(o)
        else:
            buckets['31_plus'].append(o)

    return render(request, 'opticals/uncollected_orders.html', {
        'buckets': buckets,
        'total': len(ready_orders),
        'today': today,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# LENS PRICE MATRIX
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def lens_price_matrix(request):
    """View / manage the lens price lookup table."""
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    entries = LensPriceMatrix.objects.filter(is_deleted=False).order_by(
        'lens_type', 'refractive_index', 'coating', 'power_band'
    )

    # Group by lens_type for tabbed display
    grouped = {}
    for e in entries:
        grouped.setdefault(e.get_lens_type_display(), []).append(e)

    return render(request, 'opticals/lens_price_matrix.html', {
        'grouped': grouped,
        'total': entries.count(),
        'lens_types': LensType.choices,
        'coatings': CoatingType.choices,
        'power_bands': PowerBand.choices,
    })


@login_required
def lens_price_matrix_save(request):
    """Create or update a lens price matrix entry."""
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    if request.method == 'POST':
        from decimal import Decimal, InvalidOperation
        lens_type = request.POST.get('lens_type', '')
        try:
            index_val = Decimal(request.POST.get('refractive_index', ''))
        except (InvalidOperation, TypeError):
            messages.error(request, 'Invalid refractive index.')
            return redirect('opticals:lens_price_matrix')
        coating = request.POST.get('coating', CoatingType.NONE)
        power_band = request.POST.get('power_band', PowerBand.LOW)
        try:
            price = Decimal(request.POST.get('price', ''))
        except (InvalidOperation, TypeError):
            messages.error(request, 'Invalid price.')
            return redirect('opticals:lens_price_matrix')

        entry, created = LensPriceMatrix.objects.update_or_create(
            lens_type=lens_type,
            refractive_index=index_val,
            coating=coating,
            power_band=power_band,
            defaults={'price': price, 'is_deleted': False, 'created_by': request.user},
        )
        action = 'added' if created else 'updated'
        messages.success(request, f'Price matrix entry {action}: {entry}')

    return redirect('opticals:lens_price_matrix')


@login_required
@require_POST
def lens_price_matrix_delete(request, entry_id):
    """Soft-delete a lens price matrix entry."""
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    entry = get_object_or_404(LensPriceMatrix, id=entry_id, is_deleted=False)
    entry.is_deleted = True
    entry.save(update_fields=['is_deleted'])
    messages.success(request, f'Price matrix entry removed.')
    return redirect('opticals:lens_price_matrix')


@login_required
def lens_price_lookup_ajax(request):
    """AJAX: look up lens price given type, index, coating, power band."""
    from django.http import JsonResponse
    lt = request.GET.get('lens_type', '')
    ri = request.GET.get('refractive_index', '')
    co = request.GET.get('coating', '')
    pb = request.GET.get('power_band', '')
    entry = LensPriceMatrix.objects.filter(
        lens_type=lt, refractive_index=ri, coating=co, power_band=pb, is_deleted=False
    ).first()
    if entry:
        return JsonResponse({'price': float(entry.price), 'found': True})
    return JsonResponse({'price': 0, 'found': False})


# ═══════════════════════════════════════════════════════════════════════════════
# WARRANTY & AFTER-SALES
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def repair_list(request):
    """All repair / after-sales jobs."""
    if not _can_access_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    status_filter = request.GET.get('status', '')
    qs = OpticalRepair.objects.filter(is_deleted=False).select_related(
        'patient', 'order', 'received_by'
    )
    if status_filter:
        qs = qs.filter(status=status_filter)
    else:
        qs = qs.exclude(status=RepairStatus.CANCELLED)

    # Remake rate KPI: remakes / total delivered this month
    from django.db.models import Count
    today = timezone.localdate()
    month_start = today.replace(day=1)
    month_delivered = OpticalOrder.objects.filter(
        is_deleted=False, status=OpticalOrderStatus.DELIVERED,
        delivered_date__gte=month_start, delivered_date__lte=today,
    ).count()
    month_remakes = OpticalRepair.objects.filter(
        is_deleted=False, repair_type=RepairType.LENS_REMAKE,
        received_date__gte=month_start, received_date__lte=today,
    ).count()
    remake_rate = round(month_remakes / month_delivered * 100, 1) if month_delivered else 0

    return render(request, 'opticals/repair_list.html', {
        'repairs': qs[:200],
        'status_choices': RepairStatus.choices,
        'status_filter': status_filter,
        'remake_rate': remake_rate,
        'month_remakes': month_remakes,
        'month_delivered': month_delivered,
    })


@login_required
def repair_create(request):
    """Record a new repair / after-sales job."""
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    if request.method == 'POST':
        from apps.patients.models import Patient
        from decimal import Decimal, InvalidOperation
        patient = get_object_or_404(Patient, id=request.POST.get('patient_id'), is_deleted=False)
        order_id = request.POST.get('order_id')
        order = OpticalOrder.objects.filter(id=order_id, is_deleted=False).first() if order_id else None

        try:
            cost = Decimal(request.POST.get('cost', '0') or '0')
        except (InvalidOperation, TypeError):
            cost = 0

        is_warranty = 'is_warranty_claim' in request.POST
        # If warranty claim, check warranty validity
        if is_warranty and order:
            try:
                w = order.warranty
                if not w.is_valid:
                    messages.warning(request, 'Warranty has expired or been voided. Processing as non-warranty repair.')
                    is_warranty = False
                else:
                    w.status = WarrantyStatus.CLAIMED
                    w.save(update_fields=['status'])
                    cost = 0  # Warranty repairs are free
            except OpticalWarranty.DoesNotExist:
                messages.warning(request, 'No warranty found for this order.')
                is_warranty = False

        repair = OpticalRepair.objects.create(
            patient=patient,
            order=order,
            repair_type=request.POST.get('repair_type', RepairType.OTHER),
            description=request.POST.get('description', ''),
            is_warranty_claim=is_warranty,
            cost=cost,
            received_date=request.POST.get('received_date') or timezone.localdate(),
            technician_notes=request.POST.get('technician_notes', ''),
            received_by=request.user,
            created_by=request.user,
        )
        messages.success(request, f'Repair job {repair.repair_number} created.')
        return redirect('opticals:repair_list')

    # GET — show form
    patient_id = request.GET.get('patient')
    order_id = request.GET.get('order')
    patient = None
    order = None
    if patient_id:
        from apps.patients.models import Patient
        patient = Patient.objects.filter(id=patient_id, is_deleted=False).first()
    if order_id:
        order = OpticalOrder.objects.filter(id=order_id, is_deleted=False).first()
        if order and not patient:
            patient = order.patient

    return render(request, 'opticals/repair_form.html', {
        'patient': patient,
        'order': order,
        'repair_types': RepairType.choices,
        'today': timezone.localdate(),
    })


@login_required
@require_POST
def repair_action(request, repair_id):
    """Update repair status."""
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    repair = get_object_or_404(OpticalRepair, id=repair_id, is_deleted=False)
    action = request.POST.get('action', '')

    if action == 'in_progress':
        repair.status = RepairStatus.IN_PROGRESS
    elif action == 'completed':
        repair.status = RepairStatus.COMPLETED
        repair.completed_date = timezone.localdate()
        repair.technician_notes = request.POST.get('technician_notes', repair.technician_notes)
    elif action == 'returned':
        repair.status = RepairStatus.RETURNED
        repair.returned_date = timezone.localdate()
    elif action == 'cancel':
        repair.status = RepairStatus.CANCELLED

    repair.save()
    messages.success(request, f'Repair {repair.repair_number} → {repair.get_status_display()}')
    return redirect('opticals:repair_list')


@login_required
def warranty_list(request):
    """View all optical warranties."""
    if not _can_access_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    warranties = OpticalWarranty.objects.filter(is_deleted=False).select_related(
        'order__patient', 'order__frame', 'order__lens'
    ).order_by('-start_date')

    today = timezone.localdate()
    # Mark expired warranties
    expired_count = 0
    for w in warranties:
        if w.status == WarrantyStatus.ACTIVE and w.end_date < today:
            w.status = WarrantyStatus.EXPIRED
            w.save(update_fields=['status'])
            expired_count += 1

    if expired_count:
        warranties = OpticalWarranty.objects.filter(is_deleted=False).select_related(
            'order__patient', 'order__frame', 'order__lens'
        ).order_by('-start_date')

    status_filter = request.GET.get('status', '')
    if status_filter:
        warranties = warranties.filter(status=status_filter)

    return render(request, 'opticals/warranty_list.html', {
        'warranties': warranties[:200],
        'status_choices': WarrantyStatus.choices,
        'status_filter': status_filter,
        'today': today,
    })


# ══════════════════════════════════════════════════════════════════════════════
# FRAME SUPPLIERS
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def supplier_list(request):
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    suppliers = FrameSupplier.objects.filter(is_deleted=False).order_by('name')
    return render(request, 'opticals/supplier_list.html', {'suppliers': suppliers})


@login_required
def supplier_create(request):
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Supplier name is required.')
        else:
            FrameSupplier.objects.create(
                name=name,
                contact_person=request.POST.get('contact_person', '').strip(),
                phone=request.POST.get('phone', '').strip(),
                email=request.POST.get('email', '').strip(),
                address=request.POST.get('address', '').strip(),
                website=request.POST.get('website', '').strip(),
                brands_carried=request.POST.get('brands_carried', '').strip(),
                payment_terms=request.POST.get('payment_terms', '').strip(),
                is_active=True,
                created_by=request.user,
            )
            messages.success(request, f'Supplier "{name}" added.')
            return redirect('opticals:supplier_list')
    return render(request, 'opticals/supplier_form.html', {})


@login_required
def supplier_edit(request, supplier_id):
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    supplier = get_object_or_404(FrameSupplier, id=supplier_id, is_deleted=False)
    if request.method == 'POST':
        supplier.name = request.POST.get('name', supplier.name).strip()
        supplier.contact_person = request.POST.get('contact_person', '').strip()
        supplier.phone = request.POST.get('phone', '').strip()
        supplier.email = request.POST.get('email', '').strip()
        supplier.address = request.POST.get('address', '').strip()
        supplier.website = request.POST.get('website', '').strip()
        supplier.brands_carried = request.POST.get('brands_carried', '').strip()
        supplier.payment_terms = request.POST.get('payment_terms', '').strip()
        supplier.is_active = 'is_active' in request.POST
        supplier.save()
        messages.success(request, f'Supplier "{supplier.name}" updated.')
        return redirect('opticals:supplier_list')
    return render(request, 'opticals/supplier_form.html', {'supplier': supplier})


# ══════════════════════════════════════════════════════════════════════════════
# GOODS RECEIVED NOTES (GRN)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def grn_list(request):
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    grns = FrameGoodsReceived.objects.filter(is_deleted=False).select_related(
        'supplier', 'received_by'
    ).prefetch_related('items')
    return render(request, 'opticals/grn_list.html', {'grns': grns[:200]})


@login_required
def grn_create(request):
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    if request.method == 'POST':
        supplier_id = request.POST.get('supplier')
        supplier = FrameSupplier.objects.filter(id=supplier_id, is_deleted=False).first() if supplier_id else None

        grn = FrameGoodsReceived.objects.create(
            supplier=supplier,
            supplier_invoice=request.POST.get('supplier_invoice', '').strip(),
            received_date=request.POST.get('received_date') or timezone.localdate(),
            received_by=request.user,
            status=FrameGRNStatus.DRAFT,
            notes=request.POST.get('notes', '').strip(),
            created_by=request.user,
        )

        # Parse line items
        frame_ids = request.POST.getlist('frame[]')
        quantities = request.POST.getlist('quantity[]')
        costs = request.POST.getlist('unit_cost[]')
        batches = request.POST.getlist('batch_number[]')

        from decimal import Decimal, InvalidOperation
        for i, fid in enumerate(frame_ids):
            if not fid:
                continue
            frame = Frame.objects.filter(id=fid, is_deleted=False).first()
            if not frame:
                continue
            try:
                qty = int(quantities[i]) if i < len(quantities) else 1
            except (ValueError, IndexError):
                qty = 1
            try:
                cost = Decimal(costs[i]) if i < len(costs) else Decimal(0)
            except (ValueError, IndexError, InvalidOperation):
                cost = Decimal(0)
            batch = batches[i].strip() if i < len(batches) else ''

            FrameGRNItem.objects.create(
                grn=grn, frame=frame, quantity=max(1, qty),
                unit_cost=cost, batch_number=batch,
            )

        messages.success(request, f'GRN {grn.grn_number} created with {grn.items.count()} line items.')
        return redirect('opticals:grn_detail', grn_id=grn.id)

    suppliers = FrameSupplier.objects.filter(is_active=True, is_deleted=False).order_by('name')
    frames = Frame.objects.filter(is_active=True, is_deleted=False).order_by('brand', 'model')
    return render(request, 'opticals/grn_create.html', {
        'suppliers': suppliers, 'frames': frames, 'today': timezone.localdate(),
    })


@login_required
def grn_detail(request, grn_id):
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    grn = get_object_or_404(FrameGoodsReceived, id=grn_id, is_deleted=False)
    items = grn.items.select_related('frame').all()
    return render(request, 'opticals/grn_detail.html', {'grn': grn, 'items': items})


@login_required
@require_POST
def grn_confirm(request, grn_id):
    """Confirm receipt — updates frame stock quantities."""
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    grn = get_object_or_404(FrameGoodsReceived, id=grn_id, is_deleted=False)
    if grn.status != FrameGRNStatus.DRAFT:
        messages.warning(request, 'This GRN has already been processed.')
        return redirect('opticals:grn_detail', grn_id=grn.id)

    # Update stock for each line item
    for item in grn.items.select_related('frame').all():
        Frame.objects.filter(id=item.frame_id).update(
            quantity_in_stock=F('quantity_in_stock') + item.quantity,
            cost_price=item.unit_cost if item.unit_cost > 0 else F('cost_price'),
        )

    grn.status = FrameGRNStatus.RECEIVED
    grn.save(update_fields=['status'])
    messages.success(request, f'GRN {grn.grn_number} confirmed — {grn.total_units} units added to stock.')
    return redirect('opticals:grn_detail', grn_id=grn.id)


# ══════════════════════════════════════════════════════════════════════════════
# FRAME STOCKTAKE
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def frame_stocktake_list(request):
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    stocktakes = FrameStocktake.objects.filter(is_deleted=False).select_related('conducted_by')
    return render(request, 'opticals/frame_stocktake_list.html', {'stocktakes': stocktakes[:100]})


@login_required
def frame_stocktake_create(request):
    """Create a new stocktake session pre-populated with all active frames."""
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    if request.method == 'POST':
        st = FrameStocktake.objects.create(
            title=request.POST.get('title', '').strip(),
            date=request.POST.get('date') or timezone.localdate(),
            conducted_by=request.user,
            notes=request.POST.get('notes', '').strip(),
            created_by=request.user,
        )
        # Pre-populate with all active frames
        active_frames = Frame.objects.filter(is_active=True, is_deleted=False)
        items = [
            FrameStocktakeItem(
                stocktake=st,
                frame=f,
                system_qty=f.quantity_in_stock,
            )
            for f in active_frames
        ]
        FrameStocktakeItem.objects.bulk_create(items)
        messages.success(request, f'Stocktake created with {len(items)} frame items. Enter your counts.')
        return redirect('opticals:frame_stocktake_detail', stocktake_id=st.id)

    return render(request, 'opticals/frame_stocktake_list.html', {
        'stocktakes': FrameStocktake.objects.filter(is_deleted=False).select_related('conducted_by')[:100],
        'show_create_modal': True,
    })


@login_required
def frame_stocktake_detail(request, stocktake_id):
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    st = get_object_or_404(FrameStocktake, id=stocktake_id, is_deleted=False)
    items = st.items.select_related('frame').all()

    if request.method == 'POST' and st.status == FrameStocktakeStatus.IN_PROGRESS:
        # Save counted quantities
        for item in items:
            val = request.POST.get(f'count_{item.id}', '').strip()
            if val != '':
                try:
                    item.counted_qty = int(val)
                    item.save(update_fields=['counted_qty'])
                except (ValueError, TypeError):
                    pass
        messages.success(request, 'Counts saved.')
        return redirect('opticals:frame_stocktake_detail', stocktake_id=st.id)

    return render(request, 'opticals/frame_stocktake_detail.html', {'stocktake': st, 'items': items})


@login_required
@require_POST
def frame_stocktake_finalize(request, stocktake_id):
    """Finalize stocktake — adjust system stock to match counted quantities."""
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    st = get_object_or_404(FrameStocktake, id=stocktake_id, is_deleted=False)
    if st.status != FrameStocktakeStatus.IN_PROGRESS:
        messages.warning(request, 'This stocktake has already been finalized.')
        return redirect('opticals:frame_stocktake_detail', stocktake_id=st.id)

    adjusted = 0
    for item in st.items.select_related('frame').all():
        if item.counted_qty is not None and item.variance != 0:
            item.frame.quantity_in_stock = item.counted_qty
            item.frame.save(update_fields=['quantity_in_stock'])
            adjusted += 1

    st.status = FrameStocktakeStatus.FINALIZED
    st.save(update_fields=['status'])
    messages.success(request, f'Stocktake finalized — {adjusted} frame stock levels adjusted.')
    return redirect('opticals:frame_stocktake_detail', stocktake_id=st.id)


# ══════════════════════════════════════════════════════════════════════════════
# MINIMUM STOCK ALERTS
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def min_stock_alerts(request):
    if not _can_manage_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    frames = Frame.objects.filter(is_active=True, is_deleted=False).order_by('brand', 'model')

    if request.method == 'POST':
        for frame in frames:
            val = request.POST.get(f'min_{frame.id}', '').strip()
            if val:
                try:
                    threshold = int(val)
                except (ValueError, TypeError):
                    continue
                alert, _ = FrameMinStockAlert.objects.get_or_create(
                    frame=frame, defaults={'created_by': request.user}
                )
                alert.min_quantity = max(0, threshold)
                if frame.quantity_in_stock <= threshold:
                    alert.status = 'ACTIVE'
                    alert.last_triggered = timezone.now()
                else:
                    alert.status = 'RESOLVED'
                alert.save()
        messages.success(request, 'Minimum stock thresholds updated.')
        return redirect('opticals:min_stock_alerts')

    # Build frame list with alert info
    alert_map = {a.frame_id: a for a in FrameMinStockAlert.objects.filter(frame__in=frames)}
    frame_data = []
    for f in frames:
        alert = alert_map.get(f.id)
        frame_data.append({
            'frame': f,
            'min_qty': alert.min_quantity if alert else 0,
            'is_triggered': f.quantity_in_stock <= (alert.min_quantity if alert else 0) if alert else False,
            'status': alert.status if alert else '',
        })
    triggered_count = sum(1 for d in frame_data if d['is_triggered'])

    return render(request, 'opticals/min_stock_alerts.html', {
        'frame_data': frame_data, 'triggered_count': triggered_count,
    })


# ══════════════════════════════════════════════════════════════════════════════
# SALES REPORT & ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def sales_report(request):
    if not (request.user.is_optical_dispenser or request.user.is_medical_director
            or request.user.is_super_admin or request.user.is_ceo
            or request.user.is_admin_director or request.user.is_finance_director):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    import json
    from datetime import date as _date, timedelta
    from django.db.models import Count, Sum, Avg, Q as _Q

    today = timezone.localdate()
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')

    try:
        from_dt = _date.fromisoformat(from_date) if from_date else today.replace(day=1)
        to_dt = _date.fromisoformat(to_date) if to_date else today
    except (ValueError, TypeError):
        from_dt = today.replace(day=1)
        to_dt = today

    base = OpticalOrder.objects.filter(
        is_deleted=False, ordered_date__gte=from_dt, ordered_date__lte=to_dt,
    )
    delivered = base.filter(status=OpticalOrderStatus.DELIVERED)

    # KPIs
    total_orders = base.count()
    total_revenue = delivered.aggregate(t=Sum('total_amount'))['t'] or 0
    avg_order_value = delivered.aggregate(a=Avg('total_amount'))['a'] or 0
    delivered_count = delivered.count()
    delivery_rate = round(delivered_count / total_orders * 100, 1) if total_orders else 0

    # Daily revenue chart
    daily_data = []
    d = from_dt
    while d <= to_dt:
        day_rev = OpticalOrder.objects.filter(
            is_deleted=False, ordered_date=d, status=OpticalOrderStatus.DELIVERED,
        ).aggregate(t=Sum('total_amount'))['t'] or 0
        daily_data.append({'date': d.strftime('%d %b'), 'revenue': float(day_rev)})
        d += timedelta(days=1)
    daily_json = json.dumps({
        'labels': [dd['date'] for dd in daily_data],
        'data': [dd['revenue'] for dd in daily_data],
    })

    # Revenue by frame brand
    brand_raw = list(
        delivered.filter(frame__isnull=False)
        .values('frame__brand')
        .annotate(revenue=Sum('frame_price'), count=Count('id'))
        .order_by('-revenue')[:10]
    )
    brand_json = json.dumps({
        'labels': [b['frame__brand'] for b in brand_raw],
        'data': [float(b['revenue'] or 0) for b in brand_raw],
    })

    # Lens type breakdown
    lens_raw = list(
        delivered.filter(lens__isnull=False)
        .values('lens__lens_type')
        .annotate(count=Count('id'), revenue=Sum('lens_price'))
        .order_by('-count')
    )
    lens_type_display = dict(LensType.choices)
    lens_type_json = json.dumps({
        'labels': [lens_type_display.get(l['lens__lens_type'], l['lens__lens_type']) for l in lens_raw],
        'data': [l['count'] for l in lens_raw],
    })

    # Top 10 frames by revenue
    top_frames = list(
        delivered.filter(frame__isnull=False)
        .values('frame__brand', 'frame__model', 'frame__cost_price')
        .annotate(units=Count('id'), revenue=Sum('frame_price'), avg_price=Avg('frame_price'))
        .order_by('-revenue')[:10]
    )

    # Profit margins
    frame_revenue = delivered.aggregate(t=Sum('frame_price'))['t'] or 0
    lens_revenue = delivered.aggregate(t=Sum('lens_price'))['t'] or 0
    fitting_revenue = delivered.aggregate(t=Sum('fitting_charge'))['t'] or 0
    # Approximate cost from frame cost_price
    total_cost = sum(
        (o.frame.cost_price if o.frame else 0) + (o.lens.cost_price if o.lens else 0)
        for o in delivered.select_related('frame', 'lens')
    )
    gross_profit = float(total_revenue) - float(total_cost)
    margin_pct = round(gross_profit / float(total_revenue) * 100, 1) if total_revenue else 0

    context = {
        'from_date': from_dt, 'to_date': to_dt,
        'total_orders': total_orders, 'total_revenue': total_revenue,
        'avg_order_value': avg_order_value, 'delivery_rate': delivery_rate,
        'delivered_count': delivered_count,
        'daily_json': daily_json, 'brand_json': brand_json,
        'lens_type_json': lens_type_json,
        'top_frames': top_frames,
        'frame_revenue': frame_revenue, 'lens_revenue': lens_revenue,
        'fitting_revenue': fitting_revenue,
        'total_cost': total_cost, 'gross_profit': gross_profit,
        'margin_pct': margin_pct,
        'today': today,
    }
    if request.GET.get('pdf'):
        from apps.reports.views import render_pdf
        context['pdf_filename'] = 'optical-sales-report.pdf'
        return render_pdf('opticals/sales_report.html', context)
    return render(request, 'opticals/sales_report.html', context)


# ══════════════════════════════════════════════════════════════════════════════
# PATIENT OPTICAL HISTORY CARD
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def patient_optical_history(request, patient_id):
    if not _can_access_optical(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    from apps.patients.models import Patient
    from apps.prescriptions.models import OpticalPrescription

    patient = get_object_or_404(Patient, id=patient_id, is_deleted=False)

    prescriptions = list(
        OpticalPrescription.objects.filter(patient=patient, is_deleted=False)
        .select_related('prescribed_by')
        .order_by('-prescription_date')
    )
    orders = list(
        OpticalOrder.objects.filter(patient=patient, is_deleted=False)
        .select_related('frame', 'lens')
        .order_by('-ordered_date')
    )
    cl_fittings = list(
        ContactLensFitting.objects.filter(patient=patient, is_deleted=False)
        .select_related('fitted_by')
        .order_by('-fitting_date')
    )
    lva_dispensings = list(
        LowVisionAidDispensing.objects.filter(patient=patient, is_deleted=False)
        .select_related('dispensed_by')
        .order_by('-dispensing_date')
    )
    repairs = list(
        OpticalRepair.objects.filter(patient=patient, is_deleted=False)
        .select_related('order', 'received_by')
        .order_by('-received_date')
    )
    warranties = list(
        OpticalWarranty.objects.filter(
            order__patient=patient, is_deleted=False,
        ).select_related('order').order_by('-start_date')
    )

    context = {
        'patient': patient,
        'prescriptions': prescriptions,
        'orders': orders,
        'cl_fittings': cl_fittings,
        'lva_dispensings': lva_dispensings,
        'repairs': repairs,
        'warranties': warranties,
    }
    if request.GET.get('pdf'):
        from apps.reports.views import render_pdf
        context['pdf_filename'] = f'optical-history-{patient.patient_id}.pdf'
        return render_pdf('opticals/patient_optical_history.html', context)
    return render(request, 'opticals/patient_optical_history.html', context)
