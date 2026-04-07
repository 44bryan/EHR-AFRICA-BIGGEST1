from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import Frame, Lens, OpticalOrder, OpticalOrderStatus


@login_required
def dashboard(request):
    context = {
        'total_frames': Frame.objects.filter(is_active=True, is_deleted=False).count(),
        'total_lenses': Lens.objects.filter(is_active=True, is_deleted=False).count(),
        'pending_orders': OpticalOrder.objects.filter(
            status__in=[OpticalOrderStatus.ORDERED, OpticalOrderStatus.LAB_PROCESSING],
            is_deleted=False
        ).count(),
        'ready_orders': OpticalOrder.objects.filter(
            status=OpticalOrderStatus.READY, is_deleted=False
        ).count(),
        'recent_orders': OpticalOrder.objects.filter(is_deleted=False).select_related(
            'patient', 'frame', 'lens'
        ).order_by('-ordered_date')[:10],
    }
    return render(request, 'opticals/dashboard.html', context)


@login_required
def frame_list(request):
    frames = Frame.objects.filter(is_deleted=False, is_active=True).order_by('brand', 'model')
    return render(request, 'opticals/frame_list.html', {'frames': frames})


@login_required
def lens_list(request):
    lenses = Lens.objects.filter(is_deleted=False, is_active=True).order_by('name')
    return render(request, 'opticals/lens_list.html', {'lenses': lenses})


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

        # Deduct frame stock
        if frame:
            frame.quantity_in_stock = max(0, frame.quantity_in_stock - 1)
            frame.save(update_fields=['quantity_in_stock'])

        messages.success(request, f'Optical order {order.order_number} created.')
        return redirect('opticals:order_detail', order_id=order.id)

    # Pre-fill patient from query param
    patient = None
    rx = None
    patient_id = request.GET.get('patient')
    if patient_id:
        from apps.patients.models import Patient
        from apps.prescriptions.models import OpticalPrescription
        patient = Patient.objects.filter(id=patient_id, is_deleted=False).first()
        if patient:
            rx = OpticalPrescription.objects.filter(patient=patient, is_deleted=False).order_by('-created_at').first()

    return render(request, 'opticals/create_order.html', {
        'frames': frames, 'lenses': lenses, 'patient': patient, 'rx': rx,
    })


@login_required
def order_list(request):
    orders = OpticalOrder.objects.filter(is_deleted=False).select_related(
        'patient', 'frame', 'lens'
    ).order_by('-ordered_date')
    return render(request, 'opticals/order_list.html', {'orders': orders})


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(OpticalOrder, id=order_id, is_deleted=False)
    return render(request, 'opticals/order_detail.html', {'order': order})


@login_required
def update_order_status(request, order_id):
    order = get_object_or_404(OpticalOrder, id=order_id, is_deleted=False)
    if request.method == 'POST':
        order.status = request.POST['status']
        if order.status == OpticalOrderStatus.DELIVERED:
            from django.utils import timezone
            order.delivered_date = timezone.localdate()
            order.delivered_to = request.user
        order.save()
        messages.success(request, 'Order status updated.')
        return redirect('opticals:order_detail', order_id=order.id)
    return render(request, 'opticals/update_status.html', {
        'order': order,
        'statuses': OpticalOrderStatus.choices,
    })
