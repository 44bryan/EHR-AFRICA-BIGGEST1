from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Q
from .models import InvestigationOrder, InvestigationResult, InvestigationType, InvestigationFile
from .forms import InvestigationOrderForm, InvestigationResultForm
from apps.consultations.models import Consultation
from apps.core.context_processors import qms_active as _qms_active


@login_required
def investigation_workstation_view(request):
    """
    Investigation Technician Workstation.
    Shows:
      - Patients routed here via QMS (queued) — may not have a formal order yet
      - Pending/in-progress investigation orders
      - Completed today
    """
    from apps.patients.models import Visit

    today = timezone.localdate()

    # ── Patients queued via QMS (from ordering OR direct routing) ──────────
    if _qms_active():
        try:
            from apps.qms.models import QueueToken, TokenStatus
            _invest_qs = QueueToken.objects.filter(
                service_type='INVEST',
                status__in=[TokenStatus.WAITING, TokenStatus.CALLED, TokenStatus.SERVING],
                token_date=today,
            )
            _pt = getattr(request.user, 'patient_tier', 'ALL')
            if _pt == 'VIP':
                _invest_qs = _invest_qs.filter(service_tier='VIP')
            elif _pt == 'EXPRESS':
                _invest_qs = _invest_qs.filter(service_tier__in=['EXPRESS', 'FAST_TRACK'])
            elif _pt == 'STANDARD':
                _invest_qs = _invest_qs.filter(service_tier='STANDARD')
            # _pt == 'ALL' → no filter
            queued_tokens = list(
                _invest_qs.select_related('visit__patient', 'visit__attending_doctor')
                .order_by('-priority', 'issued_at')
            )
        except Exception:
            queued_tokens = []
    else:
        queued_tokens = []
    # Attach the first pending order to each token so the template can link directly
    if queued_tokens:
        pending_by_patient = {}
        patient_ids = [t.visit.patient_id for t in queued_tokens if t.visit and t.visit.patient_id]
        for order in InvestigationOrder.objects.filter(
            patient__patient_id__in=patient_ids,
            status__in=[InvestigationOrder.Status.ORDERED, InvestigationOrder.Status.IN_PROGRESS],
            is_deleted=False,
        ).select_related('patient').order_by('urgency', 'created_at'):
            pid = order.patient.patient_id
            if pid not in pending_by_patient:
                pending_by_patient[pid] = order
        for token in queued_tokens:
            if token.visit and token.visit.patient_id:
                token.pending_order = pending_by_patient.get(token.visit.patient_id)
            else:
                token.pending_order = None
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

    # ── Payment status — checked via ServiceWorkOrder ─────────────────────────
    # PENDING_PAYMENT = doctor ordered, patient hasn't paid yet
    # PENDING         = invoice paid → cleared for service
    try:
        from apps.billing.models import ServiceWorkOrder, WorkOrderStatus, ServiceCategory
        patient_ids = [o.patient_id for o in pending_orders]
        paid_patient_ids = set(
            ServiceWorkOrder.objects.filter(
                patient_id__in=patient_ids,
                category=ServiceCategory.INVESTIGATION,
                status=WorkOrderStatus.PENDING,
                is_deleted=False,
            ).values_list('patient_id', flat=True)
        )
        unpaid_patient_ids = set(
            ServiceWorkOrder.objects.filter(
                patient_id__in=patient_ids,
                category=ServiceCategory.INVESTIGATION,
                status=WorkOrderStatus.PENDING_PAYMENT,
                is_deleted=False,
            ).values_list('patient_id', flat=True)
        )
        for order in pending_orders:
            pid = order.patient_id
            if pid in paid_patient_ids:
                order.is_paid = True
            elif pid in unpaid_patient_ids:
                order.is_paid = False
            else:
                order.is_paid = None  # No work order — legacy or direct order
    except Exception:
        for order in pending_orders:
            order.is_paid = None

    urgent = [o for o in pending_orders if o.urgency in ('URGENT', 'EMERGENCY')]
    routine = [o for o in pending_orders if o.urgency not in ('URGENT', 'EMERGENCY')]
    in_progress_count = sum(1 for o in pending_orders if o.status == InvestigationOrder.Status.IN_PROGRESS)
    ordered_count = sum(1 for o in pending_orders if o.status == InvestigationOrder.Status.ORDERED)

    return render(request, 'investigations/workstation.html', {
        'queued_no_order': queued_no_order,
        'urgent_orders': urgent,
        'routine_orders': routine,
        'completed_today': completed_today,
        'queued_count': len(queued_no_order),
        'pending_count': len(pending_orders),
        'in_progress_count': in_progress_count,
        'ordered_count': ordered_count,
        'completed_count': len(completed_today),
        'today': today,
    })


@login_required
def investigation_list_view(request):
    orders = InvestigationOrder.objects.select_related(
        'patient', 'investigation_type', 'ordered_by', 'assigned_to'
    ).filter(is_deleted=False)

    # Investigation techs / medical director see all; others see only their orders
    if not (request.user.is_medical_director or request.user.is_admin_staff or request.user.is_investigation_tech):
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
        payment_waived = request.POST.get('payment_waived') == '1'
        waive_reason = request.POST.get('waive_reason', '').strip()
        if form.is_valid():
            # Strict: waive reason is mandatory when payment is waived
            if payment_waived and not waive_reason:
                messages.error(request, 'A reason is required when waiving payment. This is logged for audit.')
            else:
                order = form.save(commit=False)
                order.consultation = consultation
                order.patient = consultation.patient
                order.ordered_by = request.user
                order.created_by = request.user
                order.save()
                try:
                    from apps.billing.models import ServiceWorkOrder, WorkOrderStatus, ServiceCategory
                    wo_status = WorkOrderStatus.PENDING if payment_waived else WorkOrderStatus.PENDING_PAYMENT
                    wo_notes = f'Payment waived — {waive_reason}' if payment_waived else ''
                    ServiceWorkOrder.objects.create(
                        patient=consultation.patient,
                        consultation=consultation,
                        category=ServiceCategory.INVESTIGATION,
                        description=f'Investigation: {order.investigation_type.name}',
                        status=wo_status,
                        notes=wo_notes,
                        created_by=request.user,
                    )
                except Exception:
                    pass  # Never block the doctor
                # Auto-route patient to investigation queue
                try:
                    from apps.core.patient_flow import auto_route_to_investigation
                    auto_route_to_investigation(consultation, ordered_by=request.user)
                except Exception:
                    pass
                messages.success(
                    request,
                    f'Investigation ordered: {order.investigation_type.name}. '
                    'Patient has been routed to the investigation queue automatically.'
                )
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
    if not request.user.can_record_investigation_results():
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Only Investigation Technicians can enter results.")
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
            # Notify the ordering doctor that the result is ready
            try:
                from apps.notifications.utils import notify
                from apps.notifications.models import NotificationType, NotificationPriority
                if order.ordered_by:
                    file_note = ' (PDF attached)' if request.FILES.get('result_file') else ''
                    notify(
                        recipient=order.ordered_by,
                        title=f'Result ready: {order.investigation_type.name} — {order.patient.full_name}',
                        message=(
                            f'{order.investigation_type.name} result entered by '
                            f'{request.user.get_full_name() or request.user.username}{file_note}. '
                            f'Patient: {order.patient.full_name} ({order.patient.patient_id})'
                        ),
                        link=f'/investigations/{order.pk}/',
                        notification_type=NotificationType.GENERAL,
                        priority=NotificationPriority.HIGH,
                    )
            except Exception:
                pass  # Never block the technician
            messages.success(request, 'Investigation result recorded.')
            return redirect('investigations:workstation')
    else:
        form = InvestigationResultForm()

    # Compute imaging sub-type so template shows the correct fields (not OCT for everything)
    imaging_subtype = 'GENERIC'
    if order.investigation_type.category == 'IMAGING':
        code_up = order.investigation_type.code.upper()
        name_up = order.investigation_type.name.upper()
        if 'OCT' in code_up or 'OCT' in name_up:
            imaging_subtype = 'OCT'
        elif ('BSCAN' in code_up or 'B_SCAN' in code_up or
              'B-SCAN' in name_up or 'B SCAN' in name_up or
              'BSCAN' in name_up or 'ULTRASOUND' in name_up):
            imaging_subtype = 'BSCAN'
        elif 'FFA' in code_up or 'FLUORESCEIN' in name_up or 'ANGIOGRAPHY' in name_up:
            imaging_subtype = 'FFA'
        elif 'FUNDUS' in code_up or 'FUNDUS' in name_up or 'PHOTO' in name_up:
            imaging_subtype = 'FUNDUS'

    # Last 5 completed results for the same test type on this patient (for comparison)
    from .models import InvestigationOrder as _IO
    prev_results = list(
        _IO.objects.filter(
            patient=order.patient,
            investigation_type=order.investigation_type,
            status='COMPLETED',
            is_deleted=False,
        ).exclude(pk=order.pk)
        .select_related('result')
        .order_by('-created_at')[:5]
    )

    return render(request, 'investigations/result_form.html', {
        'form': form,
        'order': order,
        'imaging_subtype': imaging_subtype,
        'prev_results': prev_results,
    })


@login_required
def verify_result_view(request, pk):
    order = get_object_or_404(InvestigationOrder, pk=pk)
    # Technician verifies to print & give to patient; doctor/MD can also verify
    can_verify = (
        request.user.can_record_investigation_results()
        or request.user.is_doctor
        or request.user.is_medical_director
    )
    if not can_verify:
        return HttpResponseForbidden()

    result = get_object_or_404(InvestigationResult, order=order)
    if result.is_verified:
        messages.info(request, 'This result has already been verified.')
        return redirect('investigations:detail', pk=pk)
    result.is_verified = True
    result.verified_by = request.user
    result.verified_at = timezone.now()
    result.save(update_fields=['is_verified', 'verified_by', 'verified_at', 'updated_at'])
    messages.success(request, f'Result verified by {request.user.get_full_name()}.')
    # Check if all results are done — auto-return patient to doctor queue
    try:
        visit = order.consultation.visit if order.consultation else None
        if visit:
            from apps.core.patient_flow import check_and_autoreturn_to_doctor
            check_and_autoreturn_to_doctor(visit, triggered_by=request.user)
    except Exception:
        pass
    return redirect('investigations:detail', pk=pk)


# ── DICOM Imaging Studies ──────────────────────────────────────────────────────

@login_required
def imaging_study_list(request):
    """All imaging studies — filterable by modality, patient, date range."""
    from .models import ImagingStudy, ImagingModality
    from django.db.models import Q

    qs = ImagingStudy.objects.filter(is_deleted=False).select_related('patient', 'ordered_by')
    q = request.GET.get('q', '')
    modality = request.GET.get('modality', '')
    reported = request.GET.get('reported', '')

    if q:
        qs = qs.filter(Q(patient__first_name__icontains=q) | Q(patient__last_name__icontains=q)
                       | Q(description__icontains=q) | Q(accession_number__icontains=q))
    if modality:
        qs = qs.filter(modality=modality)
    if reported == '1':
        qs = qs.filter(is_reported=True)
    elif reported == '0':
        qs = qs.filter(is_reported=False)

    from django.core.paginator import Paginator
    page_obj = Paginator(qs.order_by('-study_date', '-created_at'), 25).get_page(request.GET.get('page'))
    return render(request, 'investigations/imaging_list.html', {
        'page_obj': page_obj,
        'modalities': ImagingModality.choices,
        'q': q, 'modality': modality, 'reported': reported,
    })


@login_required
def imaging_study_create(request):
    """Create a new imaging study record and link to viewer."""
    from .models import ImagingStudy, ImagingModality
    from apps.patients.models import Patient
    from apps.consultations.models import Consultation

    if request.method == 'POST':
        patient_id = request.POST.get('patient_id', '').strip()
        patient = get_object_or_404(Patient, patient_id=patient_id, is_deleted=False)
        consultation_id = request.POST.get('consultation_id', '').strip()
        consultation = None
        if consultation_id:
            from django.core.exceptions import ValidationError
            try:
                consultation = Consultation.objects.get(id=consultation_id, is_deleted=False)
            except (Consultation.DoesNotExist, ValidationError):
                pass

        study = ImagingStudy.objects.create(
            patient=patient,
            consultation=consultation,
            modality=request.POST.get('modality', 'OTHER'),
            description=request.POST.get('description', '').strip(),
            study_uid=request.POST.get('study_uid', '').strip(),
            accession_number=request.POST.get('accession_number', '').strip(),
            series_count=int(request.POST.get('series_count', 1) or 1),
            viewer_url=request.POST.get('viewer_url', '').strip(),
            study_date=request.POST.get('study_date') or timezone.localdate(),
            ordered_by=request.user,
            created_by=request.user,
        )
        messages.success(request, f'Imaging study registered: {study}')
        return redirect('investigations:imaging_detail', study_id=study.id)

    # GET — patient pre-fill from query param
    patient_id = request.GET.get('patient', '')
    consultation_id = request.GET.get('consultation', '')
    patient = None
    if patient_id:
        try:
            patient = Patient.objects.get(patient_id=patient_id, is_deleted=False)
        except Patient.DoesNotExist:
            pass

    from .models import ImagingModality
    return render(request, 'investigations/imaging_create.html', {
        'modalities': ImagingModality.choices,
        'patient': patient,
        'consultation_id': consultation_id,
        'today': timezone.localdate(),
    })


@login_required
def imaging_study_detail(request, study_id):
    from .models import ImagingStudy
    study = get_object_or_404(ImagingStudy, id=study_id, is_deleted=False)
    return render(request, 'investigations/imaging_detail.html', {'study': study})


@login_required
def imaging_study_report(request, study_id):
    """Save / update the radiology/imaging report for a study."""
    from .models import ImagingStudy
    study = get_object_or_404(ImagingStudy, id=study_id, is_deleted=False)
    if request.method == 'POST':
        study.report = request.POST.get('report', '').strip()
        study.is_reported = True
        study.reported_by = request.user
        study.save(update_fields=['report', 'is_reported', 'reported_by', 'updated_at'])
        messages.success(request, 'Imaging report saved.')
        return redirect('investigations:imaging_detail', study_id=study.id)
    return redirect('investigations:imaging_detail', study_id=study.id)


@login_required
def patient_imaging_list(request, patient_id):
    """All imaging studies for a specific patient — used in patient detail tab."""
    from .models import ImagingStudy
    from apps.patients.models import Patient
    patient = get_object_or_404(Patient, patient_id=patient_id, is_deleted=False)
    studies = ImagingStudy.objects.filter(
        patient=patient, is_deleted=False
    ).select_related('ordered_by', 'consultation').order_by('-study_date', '-created_at')
    return render(request, 'investigations/patient_imaging.html', {
        'patient': patient,
        'studies': studies,
    })


@login_required
@require_POST
def start_investigation_view(request, pk):
    """Mark an investigation order as IN_PROGRESS — called when tech starts the test on the machine."""
    if not request.user.can_record_investigation_results():
        return HttpResponseForbidden()
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)
    if order.status == InvestigationOrder.Status.ORDERED:
        order.status = InvestigationOrder.Status.IN_PROGRESS
        order.save(update_fields=['status', 'updated_at'])
    return redirect('investigations:workstation')


@login_required
@require_POST
def bulk_start_view(request):
    """Mark multiple investigation orders as IN_PROGRESS in one action."""
    if not request.user.can_record_investigation_results():
        return HttpResponseForbidden()
    pks = request.POST.getlist('order_ids')
    if not pks:
        messages.warning(request, 'No orders selected.')
        return redirect('investigations:workstation')
    updated = InvestigationOrder.objects.filter(
        pk__in=pks,
        status=InvestigationOrder.Status.ORDERED,
    ).update(status=InvestigationOrder.Status.IN_PROGRESS)
    messages.success(request, f'{updated} test(s) marked as In Progress.')
    return redirect('investigations:workstation')


@login_required
def cancel_investigation_order(request, pk):
    """
    Cancel a pending investigation order.
    Only allowed when status == ORDERED (not yet started).
    Permitted by: the ordering doctor, investigation tech, or medical director.
    """
    if request.method != 'POST':
        return redirect('investigations:detail', pk=pk)

    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)

    # Permission check
    from apps.accounts.models import UserRole
    u = request.user
    can_cancel = (
        u == order.ordered_by
        or u.can_record_investigation_results
        or u.is_medical_director
        or u.is_super_admin
        or u.is_admin_director
    )
    if not can_cancel:
        return HttpResponseForbidden()

    if order.status != InvestigationOrder.Status.ORDERED:
        messages.error(request, 'Only pending (Ordered) investigations can be cancelled.')
        return redirect('investigations:detail', pk=pk)

    reason = request.POST.get('cancel_reason', '').strip()
    order.status = InvestigationOrder.Status.CANCELLED
    order.notes = (order.notes or '') + (f'\n[Cancelled by {u.get_full_name()}: {reason}]' if reason else f'\n[Cancelled by {u.get_full_name()}]')
    order.save(update_fields=['status', 'notes', 'updated_at'])

    messages.success(request, f'Investigation "{order.investigation_type.name}" cancelled.')

    if order.consultation:
        return redirect('consultations:detail', pk=order.consultation.pk)
    return redirect('investigations:list')


@login_required
def investigation_stats_view(request):
    """Monthly statistics for Eye Investigations — WHO-standard demographics included."""
    from django.db.models import Count, Q
    from django.core.cache import cache
    import json, calendar
    from datetime import date as _date

    u = request.user
    if not (u.is_investigation_tech or u.is_medical_director or u.is_super_admin
            or u.is_admin_director or u.is_ceo):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

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

    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    _cache_key = f'inv_stats_{year}_{month}'
    _cached = cache.get(_cache_key)
    if _cached:
        return render(request, 'investigations/stats.html', _cached)
    _cache_ttl = 300 if (year == today.year and month == today.month) else 86400

    base = InvestigationOrder.objects.filter(
        is_deleted=False,
        created_at__date__gte=month_start,
        created_at__date__lte=month_end,
    )

    # ── KPIs ──────────────────────────────────────────────────────────────────
    total_orders    = base.count()
    pending_count   = base.filter(status__in=['ORDERED', 'IN_PROGRESS']).count()
    completed_count = base.filter(status='COMPLETED').count()
    cancelled_count = base.filter(status='CANCELLED').count()
    urgent_count    = base.filter(urgency__in=['URGENT', 'EMERGENCY']).count()
    abnormal_count  = base.filter(result__is_normal=False).count()
    completion_rate = round(completed_count / total_orders * 100, 1) if total_orders else 0

    # ── By category ───────────────────────────────────────────────────────────
    cat_raw = (
        base.values('investigation_type__category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    category_data = [
        {'label': (r['investigation_type__category'] or '').replace('_', ' ').title(),
         'count': r['count']}
        for r in cat_raw if r['investigation_type__category']
    ]
    category_json = json.dumps(category_data)

    # ── By urgency ────────────────────────────────────────────────────────────
    routine_count   = base.filter(urgency='ROUTINE').count()
    emergency_count = base.filter(urgency='EMERGENCY').count()
    urgency_json = json.dumps({
        'labels': ['Routine', 'Urgent', 'Emergency'],
        'data':   [routine_count, max(0, urgent_count - emergency_count), emergency_count],
    })

    # ── By status ─────────────────────────────────────────────────────────────
    status_json = json.dumps([
        {'label': 'Ordered',     'count': base.filter(status='ORDERED').count()},
        {'label': 'In Progress', 'count': base.filter(status='IN_PROGRESS').count()},
        {'label': 'Completed',   'count': completed_count},
        {'label': 'Cancelled',   'count': cancelled_count},
    ])

    # ── Top 10 tests ──────────────────────────────────────────────────────────
    top_tests = [
        {
            'name': r['investigation_type__name'],
            'category_display': (r['investigation_type__category'] or '').replace('_', ' ').title(),
            'count': r['count'],
        }
        for r in base.values('investigation_type__name', 'investigation_type__category')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    ]

    # ── Abnormal rate by test ─────────────────────────────────────────────────
    from .models import InvestigationResult as _Result
    abnormal_by_test = []
    for row in (base.filter(result__isnull=False)
                    .values('investigation_type__name')
                    .annotate(total=Count('id'),
                              abnormal=Count('id', filter=Q(result__is_normal=False)))
                    .order_by('-abnormal')[:10]):
        total = row['total']
        abn   = row['abnormal']
        abnormal_by_test.append({
            'name':     row['investigation_type__name'],
            'total':    total,
            'abnormal': abn,
            'abn_rate': round(abn / total * 100, 1) if total else 0,
        })

    # ── Daily trend ───────────────────────────────────────────────────────────
    daily_raw = (
        base.extra(select={'day': 'DATE(created_at)'})
        .values('day').annotate(count=Count('id')).order_by('day')
    )
    daily_json = json.dumps([{'day': str(r['day']), 'count': r['count']} for r in daily_raw])

    # ── Gender breakdown + paediatric ─────────────────────────────────────────
    male_count   = base.filter(patient__gender='M').values('patient').distinct().count()
    female_count = base.filter(patient__gender='F').values('patient').distinct().count()
    gender_json = json.dumps([
        {'label': 'Male',   'count': male_count},
        {'label': 'Female', 'count': female_count},
    ])

    # ── WHO Age groups ────────────────────────────────────────────────────────
    WHO_BANDS = [('0–4', 0, 4), ('5–14', 5, 14), ('15–24', 15, 24),
                 ('25–34', 25, 34), ('35–44', 35, 44), ('45–54', 45, 54),
                 ('55–64', 55, 64), ('65+', 65, 999)]
    dobs = list(
        base.filter(patient__date_of_birth__isnull=False)
        .values_list('patient_id', 'patient__date_of_birth').distinct()
    )
    age_counts = {band[0]: 0 for band in WHO_BANDS}
    for _, dob in dobs:
        try:
            age = (today - dob).days // 365
            for label, lo, hi in WHO_BANDS:
                if lo <= age <= hi:
                    age_counts[label] += 1
                    break
        except Exception:
            pass
    paed_count  = age_counts.get('0–4', 0) + age_counts.get('5–14', 0)
    adult_count = sum(v for k, v in age_counts.items() if k not in ('0–4', '5–14'))
    age_json = json.dumps([{'label': k, 'count': v} for k, v in age_counts.items()])

    # ── M/F split by investigation category ──────────────────────────────────
    cat_gender_raw = (
        base.values('investigation_type__category', 'patient__gender')
        .annotate(count=Count('id'))
    )
    cat_gender = {}
    for row in cat_gender_raw:
        cat   = (row['investigation_type__category'] or '').replace('_', ' ').title()
        gdr   = row['patient__gender'] or 'U'
        count = row['count']
        if cat not in cat_gender:
            cat_gender[cat] = {'M': 0, 'F': 0}
        if gdr in ('M', 'F'):
            cat_gender[cat][gdr] += count

    # ── Orders by requesting department ──────────────────────────────────────
    dept_raw = list(
        base.values('consultation__department__name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    total_dept = sum(r['count'] for r in dept_raw)
    dept_table = [
        {
            'name':  r['consultation__department__name'] or 'Unknown',
            'count': r['count'],
            'pct':   round(r['count'] / total_dept * 100, 1) if total_dept else 0,
        }
        for r in dept_raw
    ]
    dept_json = json.dumps({
        'labels': [r['name'] for r in dept_table],
        'data':   [r['count'] for r in dept_table],
    })

    # ── Service tier breakdown ────────────────────────────────────────────────
    TIER_ORDER   = ['VIP', 'EXPRESS', 'FAST_TRACK', 'STANDARD']
    TIER_DISPLAY = {'VIP': 'VIP', 'EXPRESS': 'Express', 'FAST_TRACK': 'Fast Track', 'STANDARD': 'Standard'}
    completed_base = base.filter(status='COMPLETED')
    tier_rows = list(
        completed_base.values(
            'consultation__visit__service_tier',
            'patient__date_of_birth',
        )
    )
    tier_age = {}
    for row in tier_rows:
        tk  = row['consultation__visit__service_tier'] or 'STANDARD'
        dob = row['patient__date_of_birth']
        if tk not in tier_age:
            tier_age[tk] = {'children': 0, 'adults': 0, 'elderly': 0, 'total': 0}
        tier_age[tk]['total'] += 1
        if dob:
            try:
                age = (today - dob).days // 365
                if age <= 14:
                    tier_age[tk]['children'] += 1
                elif age <= 59:
                    tier_age[tk]['adults'] += 1
                else:
                    tier_age[tk]['elderly'] += 1
            except Exception:
                pass
    total_completed = sum(d['total'] for d in tier_age.values())
    tier_table = []
    for tk in TIER_ORDER:
        d = tier_age.get(tk, {'children': 0, 'adults': 0, 'elderly': 0, 'total': 0})
        if d['total'] > 0:
            tier_table.append({
                'tier': TIER_DISPLAY.get(tk, tk), 'key': tk,
                'pct': round(d['total'] / total_completed * 100, 1) if total_completed else 0,
                **d,
            })
    for tk, d in tier_age.items():
        if tk not in TIER_ORDER and d['total'] > 0:
            tier_table.append({
                'tier': tk, 'key': tk,
                'pct': round(d['total'] / total_completed * 100, 1) if total_completed else 0,
                **d,
            })
    tier_json = json.dumps({
        'labels': [r['tier'] for r in tier_table],
        'data':   [r['total'] for r in tier_table],
    })

    ctx = {
        'month_start': month_start, 'month_end': month_end,
        'year': year, 'month': month,
        'prev_year': prev_year, 'prev_month': prev_month,
        'next_year': next_year, 'next_month': next_month,
        # KPIs
        'total_orders': total_orders, 'pending_count': pending_count,
        'completed_count': completed_count, 'cancelled_count': cancelled_count,
        'urgent_count': urgent_count, 'abnormal_count': abnormal_count,
        'completion_rate': completion_rate,
        # Tables
        'top_tests': top_tests, 'abnormal_by_test': abnormal_by_test,
        'dept_table': dept_table, 'tier_table': tier_table,
        'total_completed': total_completed,
        # Demographics
        'male_count': male_count, 'female_count': female_count,
        'paed_count': paed_count, 'adult_count': adult_count,
        'age_counts': age_counts, 'cat_gender': cat_gender,
        # JSON
        'category_json': category_json, 'urgency_json': urgency_json,
        'status_json': status_json, 'daily_json': daily_json,
        'gender_json': gender_json, 'age_json': age_json,
        'dept_json': dept_json, 'tier_json': tier_json,
        'is_current_month': (year == today.year and month == today.month),
    }
    cache.set(_cache_key, ctx, _cache_ttl)
    return render(request, 'investigations/stats.html', ctx)
