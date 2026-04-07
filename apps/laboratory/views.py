from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden
from django.utils import timezone
from django.db.models import Count, Avg, Q
from datetime import timedelta
from .models import LabOrder, LabOrderItem, LabResult, LabTestType, SampleCollection
from .forms import LabOrderForm, LabResultFormSet, SampleCollectionForm
from apps.consultations.models import Consultation


@login_required
def lab_dashboard(request):
    """Lab technician workstation dashboard."""
    if not (request.user.is_lab_tech or request.user.is_medical_director or request.user.is_admin_staff):
        return HttpResponseForbidden()

    today = timezone.localdate()
    month_start = today.replace(day=1)

    # Today's pending work
    pending_orders = LabOrder.objects.filter(
        is_deleted=False,
        status__in=['ORDERED', 'SAMPLE_COLLECTED', 'PROCESSING'],
    ).select_related('patient', 'ordered_by').order_by('-created_at')

    # Today's completed
    completed_today = LabOrder.objects.filter(
        status='COMPLETED', is_deleted=False,
        updated_at__date=today,
    ).count()

    # Critical results this month (unverified)
    critical_unverified = LabResult.objects.filter(
        is_critical=True, is_verified=False,
        is_deleted=False,
    ).select_related('order_item__order__patient', 'order_item__test_type')

    # Abnormal this month
    abnormal_count = LabResult.objects.filter(
        is_abnormal=True, is_deleted=False,
        created_at__date__gte=month_start,
    ).count()

    # Stats by category this month
    category_stats = (
        LabOrderItem.objects.filter(
            order__is_deleted=False,
            order__created_at__date__gte=month_start,
        )
        .values('test_type__category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # Turnaround time (ordered → completed, last 30 days)
    # We approximate using created_at vs updated_at for completed orders
    completed_this_month = LabOrder.objects.filter(
        status='COMPLETED', is_deleted=False,
        updated_at__date__gte=month_start,
    ).count()

    context = {
        'pending_orders': pending_orders,
        'pending_count': pending_orders.count(),
        'completed_today': completed_today,
        'completed_this_month': completed_this_month,
        'critical_unverified': critical_unverified,
        'critical_count': critical_unverified.count(),
        'abnormal_count': abnormal_count,
        'category_stats': category_stats,
        'today': today,
    }
    return render(request, 'laboratory/dashboard.html', context)


@login_required
def lab_list_view(request):
    orders = LabOrder.objects.select_related('patient', 'ordered_by').filter(is_deleted=False)

    if not (request.user.is_medical_director or request.user.is_admin_staff or request.user.is_lab_tech):
        orders = orders.filter(ordered_by=request.user)

    status_filter = request.GET.get('status', '')
    if status_filter:
        orders = orders.filter(status=status_filter)

    urgency_filter = request.GET.get('urgency', '')
    if urgency_filter:
        orders = orders.filter(urgency=urgency_filter)

    orders = orders.order_by('-created_at')

    return render(request, 'laboratory/list.html', {
        'orders': orders[:200],
        'status_choices': LabOrder.Status.choices,
        'urgency_choices': [('ROUTINE','Routine'),('URGENT','Urgent'),('EMERGENCY','Emergency')],
        'status_filter': status_filter,
        'urgency_filter': urgency_filter,
    })


@login_required
def lab_stats_view(request):
    """Monthly statistics for lab — for medical director."""
    if not (request.user.is_medical_director or request.user.is_admin_staff or request.user.is_lab_tech):
        return HttpResponseForbidden()

    today = timezone.localdate()
    month_start = today.replace(day=1)

    # Monthly test volume by category
    category_volume = (
        LabOrderItem.objects.filter(
            order__is_deleted=False,
            order__created_at__date__gte=month_start,
        )
        .values('test_type__category', 'test_type__name')
        .annotate(count=Count('id'))
        .order_by('test_type__category', '-count')
    )

    # Most ordered tests
    top_tests = (
        LabOrderItem.objects.filter(
            order__is_deleted=False,
            order__created_at__date__gte=month_start,
        )
        .values('test_type__name', 'test_type__code')
        .annotate(count=Count('id'))
        .order_by('-count')[:15]
    )

    # Abnormal rate per test
    abnormal_by_test = (
        LabResult.objects.filter(
            is_deleted=False,
            created_at__date__gte=month_start,
        )
        .values('order_item__test_type__name')
        .annotate(
            total=Count('id'),
            abnormal=Count('id', filter=Q(is_abnormal=True)),
            critical=Count('id', filter=Q(is_critical=True)),
        )
        .filter(total__gt=0)
        .order_by('-abnormal')[:10]
    )

    # Daily volume last 14 days
    daily_volume = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        cnt = LabOrder.objects.filter(
            is_deleted=False, created_at__date=d
        ).count()
        daily_volume.append({'date': d.strftime('%d %b'), 'count': cnt})

    # Total this month
    total_orders = LabOrder.objects.filter(
        is_deleted=False, created_at__date__gte=month_start
    ).count()
    total_items = LabOrderItem.objects.filter(
        order__is_deleted=False, order__created_at__date__gte=month_start
    ).count()
    total_abnormal = LabResult.objects.filter(
        is_abnormal=True, is_deleted=False, created_at__date__gte=month_start
    ).count()
    total_critical = LabResult.objects.filter(
        is_critical=True, is_deleted=False, created_at__date__gte=month_start
    ).count()

    import json
    context = {
        'category_volume': category_volume,
        'top_tests': top_tests,
        'abnormal_by_test': abnormal_by_test,
        'daily_volume': daily_volume,
        'daily_volume_json': json.dumps(daily_volume),
        'total_orders': total_orders,
        'total_items': total_items,
        'total_abnormal': total_abnormal,
        'total_critical': total_critical,
        'month_start': month_start,
        'today': today,
    }
    return render(request, 'laboratory/stats.html', context)


@login_required
def verify_result(request, result_id):
    """Lab senior / director verifies a result."""
    if not (request.user.is_medical_director or request.user.is_lab_tech):
        return HttpResponseForbidden()
    result = get_object_or_404(LabResult, pk=result_id, is_deleted=False)
    result.is_verified = True
    result.verified_by = request.user
    result.verified_at = timezone.now()
    result.save(update_fields=['is_verified', 'verified_by', 'verified_at', 'updated_at'])
    messages.success(request, 'Result verified.')
    return redirect('laboratory:detail', pk=result.order_item.order.pk)


@login_required
def lab_order_view(request, consultation_pk):
    if not request.user.can_order_investigations():
        return HttpResponseForbidden()

    consultation = get_object_or_404(Consultation, pk=consultation_pk)
    test_types = LabTestType.objects.filter(is_active=True).order_by('category', 'name')

    if request.method == 'POST':
        form = LabOrderForm(request.POST)
        selected_tests = request.POST.getlist('test_types')
        if form.is_valid() and selected_tests:
            order = form.save(commit=False)
            order.consultation = consultation
            order.patient = consultation.patient
            order.ordered_by = request.user
            order.created_by = request.user
            order.save()
            for test_id in selected_tests:
                LabOrderItem.objects.create(order=order, test_type_id=test_id)
            # Auto-billing
            try:
                from apps.billing.utils import bill_lab_order
                bill_lab_order(order, created_by=request.user)
            except Exception:
                pass
            messages.success(request, f'Lab order created with {len(selected_tests)} test(s).')
            return redirect('consultations:detail', pk=consultation_pk)
        elif not selected_tests:
            messages.error(request, 'Please select at least one test.')
    else:
        form = LabOrderForm()

    return render(request, 'laboratory/order_form.html', {
        'form': form,
        'consultation': consultation,
        'test_types': test_types,
        'categories': LabTestType.objects.values_list('category', flat=True).distinct(),
    })


@login_required
def lab_detail_view(request, pk):
    order = get_object_or_404(
        LabOrder.objects.prefetch_related('items__test_type', 'items__result'),
        pk=pk, is_deleted=False
    )
    sample = getattr(order, 'sample_collection', None)
    return render(request, 'laboratory/detail.html', {
        'order': order,
        'sample': sample,
    })


@login_required
def collect_sample_view(request, pk):
    order = get_object_or_404(LabOrder, pk=pk)
    if hasattr(order, 'sample_collection'):
        messages.info(request, 'Sample already collected.')
        return redirect('laboratory:detail', pk=pk)

    if request.method == 'POST':
        form = SampleCollectionForm(request.POST)
        if form.is_valid():
            sc = form.save(commit=False)
            sc.order = order
            sc.collected_by = request.user
            sc.created_by = request.user
            sc.save()
            order.status = LabOrder.Status.SAMPLE_COLLECTED
            order.save(update_fields=['status'])
            messages.success(request, 'Sample collection recorded.')
            return redirect('laboratory:detail', pk=pk)
    else:
        form = SampleCollectionForm()

    return render(request, 'laboratory/collect_sample.html', {'form': form, 'order': order})


@login_required
def enter_results_view(request, pk):
    if not (request.user.is_lab_tech or request.user.is_medical_director):
        return HttpResponseForbidden()

    order = get_object_or_404(
        LabOrder.objects.prefetch_related('items__test_type'),
        pk=pk
    )
    items = list(order.items.all())

    if request.method == 'POST':
        all_valid = True
        for item in items:
            value = request.POST.get(f'result_value_{item.pk}', '').strip()
            if value:
                result, _ = LabResult.objects.get_or_create(
                    order_item=item,
                    defaults={
                        'performed_by': request.user,
                        'created_by': request.user,
                    }
                )
                result.result_value = value
                result.result_unit = request.POST.get(f'result_unit_{item.pk}', '')
                result.reference_range = request.POST.get(f'ref_range_{item.pk}', '')
                result.is_abnormal = request.POST.get(f'is_abnormal_{item.pk}') == 'on'
                result.is_critical = request.POST.get(f'is_critical_{item.pk}') == 'on'
                result.comment = request.POST.get(f'comment_{item.pk}', '')
                result.performed_by = request.user
                result.save()
                item.status = LabOrder.Status.COMPLETED
                item.save(update_fields=['status'])

        order.status = LabOrder.Status.COMPLETED
        order.save(update_fields=['status'])
        messages.success(request, 'Results saved successfully.')
        return redirect('laboratory:detail', pk=pk)

    return render(request, 'laboratory/results_form.html', {
        'order': order,
        'items': items,
    })
