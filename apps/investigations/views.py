from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden
from django.utils import timezone
from django.db.models import Q
from .models import InvestigationOrder, InvestigationResult, InvestigationType, InvestigationFile
from .forms import InvestigationOrderForm, InvestigationResultForm
from apps.consultations.models import Consultation


@login_required
def investigation_workstation_view(request):
    """
    Investigation Technician Workstation.
    Shows:
      - Patients routed here via QMS (queued) — may not have a formal order yet
      - Pending/in-progress investigation orders
      - Completed today
    """
    from apps.qms.models import QueueToken, TokenStatus
    from apps.patients.models import Visit

    today = timezone.localdate()

    # ── Patients queued via QMS (from ordering OR direct routing) ──────────
    queued_tokens = list(
        QueueToken.objects.filter(
            service_type='INVEST',
            status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
            issued_at__date=today,
        ).select_related('visit__patient', 'visit__attending_doctor')
        .order_by('issued_at')
    )
    queued_no_order = queued_tokens  # Show all — technician calls & records

    pending_orders = list(
        InvestigationOrder.objects.filter(
            status__in=[InvestigationOrder.Status.ORDERED, InvestigationOrder.Status.IN_PROGRESS],
            is_deleted=False,
        ).select_related(
            'patient', 'investigation_type', 'ordered_by', 'consultation'
        ).order_by('urgency', 'created_at')
    )

    completed_today = list(
        InvestigationOrder.objects.filter(
            status=InvestigationOrder.Status.COMPLETED,
            is_deleted=False,
            updated_at__date=today,
        ).select_related(
            'patient', 'investigation_type', 'ordered_by'
        ).prefetch_related('result__files').order_by('-updated_at')[:30]
    )

    urgent = [o for o in pending_orders if o.urgency in ('URGENT', 'EMERGENCY')]
    routine = [o for o in pending_orders if o.urgency not in ('URGENT', 'EMERGENCY')]

    return render(request, 'investigations/workstation.html', {
        'queued_no_order': queued_no_order,
        'urgent_orders': urgent,
        'routine_orders': routine,
        'completed_today': completed_today,
        'queued_count': len(queued_no_order),
        'pending_count': len(pending_orders),
        'completed_count': len(completed_today),
        'today': today,
    })


@login_required
def investigation_list_view(request):
    orders = InvestigationOrder.objects.select_related(
        'patient', 'investigation_type', 'ordered_by', 'assigned_to'
    ).filter(is_deleted=False)

    # Lab techs / investigation staff see all; others see their orders
    if not (request.user.is_medical_director or request.user.is_admin_staff):
        if request.user.is_lab_tech:
            pass  # see all
        else:
            orders = orders.filter(ordered_by=request.user)

    status_filter = request.GET.get('status', '')
    patient_filter = request.GET.get('patient', '')
    if status_filter:
        orders = orders.filter(status=status_filter)
    if patient_filter:
        orders = orders.filter(patient__patient_id=patient_filter)

    return render(request, 'investigations/list.html', {
        'orders': orders[:100],
        'status_choices': InvestigationOrder.Status.choices,
        'status_filter': status_filter,
        'patient_filter': patient_filter,
    })


@login_required
def investigation_order_view(request, consultation_pk):
    if not request.user.can_order_investigations():
        return HttpResponseForbidden()

    consultation = get_object_or_404(Consultation, pk=consultation_pk)
    if request.method == 'POST':
        form = InvestigationOrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.consultation = consultation
            order.patient = consultation.patient
            order.ordered_by = request.user
            order.created_by = request.user
            order.save()
            # Auto-billing
            try:
                from apps.billing.utils import bill_investigation
                bill_investigation(order, created_by=request.user)
            except Exception:
                pass

            # Auto-create QMS token so patient appears in investigation queue
            try:
                from apps.qms.models import (
                    QueueToken, DailyTokenSequence, IssuancePoint, TokenStatus
                )
                visit = consultation.visit
                if visit:
                    token_number = DailyTokenSequence.next_dept_token('INVEST')
                    QueueToken.objects.create(
                        token_number=token_number,
                        service_type='INVEST',
                        patient=consultation.patient,
                        visit=visit,
                        service_tier=visit.service_tier if hasattr(visit, 'service_tier') else 'STANDARD',
                        issuance_point=IssuancePoint.SYSTEM,
                        status=TokenStatus.WAITING,
                        created_by=request.user,
                    )
                    # Update visit status and department
                    from apps.patients.models import VisitStatus
                    from apps.departments.models import Department
                    invest_dept = Department.objects.filter(code='INVEST', is_active=True).first()
                    visit.status = 'INVESTIGATION'
                    if invest_dept:
                        visit.department = invest_dept
                    visit.save(update_fields=['status', 'department', 'updated_at'] if invest_dept else ['status', 'updated_at'])
            except Exception:
                pass  # Never block the doctor if QMS fails

            messages.success(request, f'Investigation ordered: {order.investigation_type.name}. Patient queued at Investigation.')
            return redirect('consultations:detail', pk=consultation_pk)
    else:
        form = InvestigationOrderForm()

    return render(request, 'investigations/order_form.html', {
        'form': form,
        'consultation': consultation,
        'investigation_types': InvestigationType.objects.filter(is_active=True).order_by('category', 'name'),
    })


@login_required
def investigation_detail_view(request, pk):
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)
    result = getattr(order, 'result', None)
    return render(request, 'investigations/detail.html', {
        'order': order,
        'result': result,
    })


@login_required
def add_result_view(request, pk):
    order = get_object_or_404(InvestigationOrder, pk=pk)
    if hasattr(order, 'result'):
        messages.info(request, 'Result already recorded. Use edit instead.')
        return redirect('investigations:detail', pk=pk)

    if request.method == 'POST':
        form = InvestigationResultForm(request.POST)
        if form.is_valid():
            result = form.save(commit=False)
            result.order = order
            result.performed_by = request.user
            result.created_by = request.user
            # Save structured result fields from POST into result_data JSON
            structured = {}
            structured_keys = [
                'vf_type','vf_md_od','vf_md_os','vf_psd_od','vf_psd_os',
                'vf_ght_od','vf_ght_os','vf_progression','vf_comments',
                'rnfl_avg_od','rnfl_avg_os','rnfl_inf_od','rnfl_inf_os',
                'rnfl_interp','rim_area_od','rim_area_os',
                'fundus_photo_od','fundus_photo_os',
                'bscan_od','bscan_os',
                'axial_length_od','axial_length_os','k1_od','k1_os',
                'k2_od','k2_os','iol_od','iol_os','biometry_notes',
                'pachymetry_od','pachymetry_os',
                'other_findings',
            ]
            for key in structured_keys:
                val = request.POST.get(key, '').strip()
                if val:
                    structured[key] = val
            if structured:
                result.result_data = structured
            result.save()
            order.status = InvestigationOrder.Status.COMPLETED
            order.save(update_fields=['status'])
            # Handle file upload
            uploaded_file = request.FILES.get('result_file')
            if uploaded_file:
                InvestigationFile.objects.create(
                    result=result,
                    file=uploaded_file,
                    file_type='IMAGE' if uploaded_file.content_type.startswith('image') else 'PDF',
                    uploaded_by=request.user,
                )
            messages.success(request, 'Investigation result recorded.')
            return redirect('investigations:workstation')
    else:
        form = InvestigationResultForm()

    return render(request, 'investigations/result_form.html', {
        'form': form,
        'order': order,
    })


@login_required
def verify_result_view(request, pk):
    order = get_object_or_404(InvestigationOrder, pk=pk)
    if not (request.user.is_doctor or request.user.is_medical_director):
        return HttpResponseForbidden()

    result = get_object_or_404(InvestigationResult, order=order)
    result.is_verified = True
    result.verified_by = request.user
    result.verified_at = timezone.now()
    result.save(update_fields=['is_verified', 'verified_by', 'verified_at'])
    messages.success(request, 'Investigation result verified.')
    return redirect('investigations:detail', pk=pk)
