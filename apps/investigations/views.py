from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Q, Count
from .models import (
    InvestigationOrder, InvestigationResult, InvestigationType, InvestigationFile,
    Device, DeviceDowntime, AcquisitionRecord, BiometryRecord,
    ImagingStudy, ImagingModality, InvestigationResultAmendment,
    VisitInvestigationPlan, VisitInvestigationStep, ContrastReactionLog,
    InvestigationCategory, PaymentStatus, AcquisitionStatus, ReportStatus, Laterality,
)
from .forms import (
    InvestigationOrderForm, InvestigationResultForm,
    MultiExamOrderForm, STRUCTURED_RESULT_FORMS,
)
from apps.consultations.models import Consultation
from apps.core.context_processors import qms_active as _qms_active


# ══════════════════════════════════════════════════════════════════════════════
# ACCESS HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _is_invest_staff(user):
    return (user.is_investigation_tech or user.is_medical_director
            or user.is_super_admin or user.is_admin_director
            or user.role in ('optometrist', 'pediatric_refractionist', 'orthoptist'))


def _is_invest_viewer(user):
    return (_is_invest_staff(user) or user.is_ceo
            or user.is_finance_director)


# ══════════════════════════════════════════════════════════════════════════════
# WORKSTATION
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def investigation_workstation_view(request):
    """
    Investigation Technician Workstation — Clinical Pipeline.
    Only shows PAID orders. Pipeline: Checked In → Preparing → In Progress → Done.
    """
    today = timezone.localdate()
    now_dt = timezone.now()

    # ── All active orders (paid only — unpaid are not the tech's concern) ─────
    _base_qs = InvestigationOrder.objects.filter(
        is_deleted=False,
    ).select_related(
        'patient', 'investigation_type', 'ordered_by', 'device', 'checked_in_by',
        'assigned_to',
    )

    # ── Per-role category filtering ─────────────────────────────────────────
    # Optometrists see only REFRACTION orders (+ assigned to them)
    # Orthoptists see only ORTHOPTICS orders (+ assigned to them)
    # Investigation techs see everything EXCEPT optometry categories
    # Admins/directors see everything
    user = request.user
    _OPTOMETRY_CATS = {'REFRACTION', 'LOW_VISION'}
    _ORTHOPTICS_CATS = {'ORTHOPTICS'}

    if user.role in ('optometrist', 'pediatric_refractionist'):
        # Optometrist: see orders assigned to them OR unassigned optometry orders
        _base_qs = _base_qs.filter(
            Q(assigned_to=user) |
            Q(assigned_to__isnull=True, investigation_type__category__in=_OPTOMETRY_CATS)
        )
    elif user.role == 'orthoptist':
        # Orthoptist: see orders assigned to them OR unassigned orthoptics orders
        _base_qs = _base_qs.filter(
            Q(assigned_to=user) |
            Q(assigned_to__isnull=True, investigation_type__category__in=_ORTHOPTICS_CATS)
        )
    elif user.is_investigation_tech:
        # Regular investigation tech: see everything EXCEPT optometry categories
        _base_qs = _base_qs.exclude(
            investigation_type__category__in=(_OPTOMETRY_CATS | _ORTHOPTICS_CATS)
        )
    # else: admin/director/super_admin — see everything (no filter)

    # Only paid orders are actionable — filter by payment_status
    _paid_statuses = PaymentStatus.actionable_statuses()

    # ── Pipeline stages ──────────────────────────────────────────────────────
    # 1. Checked In — patient arrived, waiting for exam
    checked_in_orders = list(
        _base_qs.filter(
            acquisition_status=AcquisitionStatus.CHECKED_IN,
            payment_status__in=_paid_statuses,
            status__in=['ORDERED', 'SCHEDULED', 'IN_PROGRESS'],
        ).order_by('urgency', 'checked_in_at')
    )

    # 2. Preparing — dilation / prep in progress
    preparing_orders = list(
        _base_qs.filter(
            acquisition_status=AcquisitionStatus.PATIENT_PREPARED,
            payment_status__in=_paid_statuses,
            status__in=['ORDERED', 'SCHEDULED', 'IN_PROGRESS'],
        ).order_by('urgency', 'updated_at')
    )
    # Estimate ready time for dilating patients (dilation ~25min)
    for o in preparing_orders:
        if o.dilation_time:
            from datetime import timedelta
            o.est_ready = o.dilation_time + timedelta(minutes=25)
            o.mins_remaining = max(0, int((o.est_ready - now_dt).total_seconds() / 60))
        else:
            o.est_ready = None
            o.mins_remaining = None

    # 3. In Progress — exam happening now
    in_progress_orders = list(
        _base_qs.filter(
            acquisition_status=AcquisitionStatus.IN_PROGRESS,
            payment_status__in=_paid_statuses,
            status=InvestigationOrder.Status.IN_PROGRESS,
        ).order_by('updated_at')
    )

    # 4. Paid but NOT yet checked in — "Expected Arrivals"
    expected_arrivals = list(
        _base_qs.filter(
            acquisition_status=AcquisitionStatus.SCHEDULED,
            payment_status__in=_paid_statuses,
            status__in=['ORDERED', 'SCHEDULED'],
        ).order_by('urgency', 'created_at')
    )

    # 5. Quality failed — needs repeat
    quality_failed = list(
        _base_qs.filter(
            acquisition_status=AcquisitionStatus.QUALITY_FAILED,
            status__in=['IN_PROGRESS', 'ORDERED'],
        ).order_by('-updated_at')[:20]
    )

    # 6. Completed today
    completed_today = list(
        InvestigationOrder.objects.filter(
            status=InvestigationOrder.Status.COMPLETED,
            is_deleted=False,
            updated_at__date=today,
        ).select_related(
            'patient', 'investigation_type', 'ordered_by'
        ).prefetch_related('result__files').order_by('-updated_at')[:30]
    )

    # ── Dilation info for pipeline orders ────────────────────────────────────
    for o in (checked_in_orders + preparing_orders + in_progress_orders + expected_arrivals):
        o.dilation_req = getattr(o.investigation_type, 'dilation_requirement', 'INDIFFERENT') or 'INDIFFERENT'

    # ── Elapsed time since check-in ──────────────────────────────────────────
    for o in checked_in_orders:
        if o.checked_in_at:
            delta = now_dt - o.checked_in_at
            o.wait_minutes = int(delta.total_seconds() / 60)
        else:
            o.wait_minutes = 0

    # ── TAT for completed orders ─────────────────────────────────────────────
    for o in completed_today:
        if hasattr(o, 'result') and o.result and o.result.result_date:
            delta = o.result.result_date - o.created_at
            o.tat_minutes = int(delta.total_seconds() / 60)
        else:
            o.tat_minutes = None

    # ── Stat counts ──────────────────────────────────────────────────────────
    return render(request, 'investigations/workstation.html', {
        'checked_in_orders': checked_in_orders,
        'preparing_orders': preparing_orders,
        'in_progress_orders': in_progress_orders,
        'expected_arrivals': expected_arrivals,
        'quality_failed': quality_failed,
        'completed_today': completed_today,
        'checked_in_count': len(checked_in_orders),
        'preparing_count': len(preparing_orders),
        'in_progress_count': len(in_progress_orders),
        'expected_count': len(expected_arrivals),
        'quality_failed_count': len(quality_failed),
        'completed_count': len(completed_today),
        'today': today,
    })


# ══════════════════════════════════════════════════════════════════════════════
# CHECK-IN & PREPARATION
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def check_in_view(request, pk):
    """Check in patient — they have physically arrived at imaging/investigation."""
    if not request.user.can_record_investigation_results():
        return HttpResponseForbidden()
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)
    if order.acquisition_status == AcquisitionStatus.SCHEDULED:
        order.acquisition_status = AcquisitionStatus.CHECKED_IN
        order.checked_in_at = timezone.now()
        order.checked_in_by = request.user
        order.save(update_fields=['acquisition_status', 'checked_in_at', 'checked_in_by', 'updated_at'])
        messages.success(request, f'{order.patient.full_name} checked in for {order.investigation_type.name}.')
    return redirect('investigations:workstation')


@login_required
@require_POST
def prepare_patient_view(request, pk):
    """Move patient to PATIENT_PREPARED — dilation started or other prep."""
    if not request.user.can_record_investigation_results():
        return HttpResponseForbidden()
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)
    if order.acquisition_status in (AcquisitionStatus.CHECKED_IN, AcquisitionStatus.SCHEDULED):
        order.acquisition_status = AcquisitionStatus.PATIENT_PREPARED
        if not order.checked_in_at:
            order.checked_in_at = timezone.now()
            order.checked_in_by = request.user
        # Record dilation start if applicable
        dilation_agent = request.POST.get('dilation_agent', '').strip()
        if dilation_agent:
            order.dilation_status = 'dilating'
            order.dilation_time = timezone.now()
            order.dilation_agent = dilation_agent
            order.save(update_fields=[
                'acquisition_status', 'checked_in_at', 'checked_in_by',
                'dilation_status', 'dilation_time', 'dilation_agent', 'updated_at',
            ])
        else:
            order.save(update_fields=['acquisition_status', 'checked_in_at', 'checked_in_by', 'updated_at'])
        messages.success(request, f'{order.patient.full_name} — preparation started.')
    return redirect('investigations:workstation')


@login_required
@require_POST
def bulk_check_in_view(request):
    """Bulk check-in multiple patients at once."""
    if not request.user.can_record_investigation_results():
        return HttpResponseForbidden()
    order_ids = request.POST.getlist('order_ids')
    if order_ids:
        now = timezone.now()
        updated = InvestigationOrder.objects.filter(
            pk__in=order_ids,
            acquisition_status=AcquisitionStatus.SCHEDULED,
            is_deleted=False,
        ).update(
            acquisition_status=AcquisitionStatus.CHECKED_IN,
            checked_in_at=now,
            checked_in_by=request.user,
            updated_at=now,
        )
        messages.success(request, f'{updated} patient(s) checked in.')
    return redirect('investigations:workstation')


# ══════════════════════════════════════════════════════════════════════════════
# LIST & ORDER
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def investigation_list_view(request):
    orders = InvestigationOrder.objects.select_related(
        'patient', 'investigation_type', 'ordered_by', 'assigned_to', 'device'
    ).filter(is_deleted=False)

    if not (request.user.is_medical_director or request.user.is_admin_staff or request.user.is_investigation_tech):
        orders = orders.filter(ordered_by=request.user)

    status_filter = request.GET.get('status', '')
    patient_filter = request.GET.get('patient', '')
    eye_filter = request.GET.get('eye', '')
    if status_filter:
        orders = orders.filter(status=status_filter)
    if patient_filter:
        orders = orders.filter(patient__patient_id=patient_filter)
    if eye_filter:
        orders = orders.filter(eye=eye_filter)

    return render(request, 'investigations/list.html', {
        'orders': orders[:100],
        'status_choices': InvestigationOrder.Status.choices,
        'laterality_choices': Laterality.choices,
        'status_filter': status_filter,
        'patient_filter': patient_filter,
        'eye_filter': eye_filter,
    })


def _check_insurance_preauth(patient, visit):
    """Check if patient's insurance requires pre-auth and if it's approved.
    Returns (needs_preauth, has_valid_preauth, warning_message)."""
    if not visit or visit.billing_type not in ('HMO', 'INSURANCE'):
        return False, True, ''
    try:
        from apps.hmo.models import InsuredMember, PreAuthorization, PreAuthStatus
        member = InsuredMember.objects.filter(
            patient=patient, is_active=True
        ).select_related('scheme').first()
        if not member or not member.scheme.pre_auth_required:
            return False, True, ''
        # Scheme requires pre-auth — check for valid approval
        valid_auth = PreAuthorization.objects.filter(
            member=member,
            status=PreAuthStatus.APPROVED,
        ).filter(
            Q(valid_until__gte=timezone.localdate()) | Q(valid_until__isnull=True)
        ).filter(
            Q(visit=visit) | Q(visit__isnull=True)
        ).exists()
        if valid_auth:
            return True, True, ''
        # Check if pending
        pending = PreAuthorization.objects.filter(
            member=member, status=PreAuthStatus.PENDING
        ).exists()
        if pending:
            return True, False, (
                f'Insurance pre-authorisation is PENDING for {member.scheme.name}. '
                f'Investigation orders are blocked until pre-auth is approved.'
            )
        return True, False, (
            f'No approved pre-authorisation found for {member.scheme.name} ({member.member_number}). '
            f'Please request pre-auth before ordering investigations for insured patients.'
        )
    except ImportError:
        return False, True, ''


@login_required
def investigation_order_view(request, consultation_pk):
    if not request.user.can_order_investigations():
        return HttpResponseForbidden()

    consultation = get_object_or_404(Consultation, pk=consultation_pk, is_deleted=False)

    # ── Insurance pre-auth gate ──
    _needs_preauth, _has_preauth, _preauth_msg = _check_insurance_preauth(
        consultation.patient, consultation.visit
    )
    if _needs_preauth and not _has_preauth:
        messages.warning(request, _preauth_msg)

    if request.method == 'POST':
        # Block order submission if pre-auth required but missing
        if _needs_preauth and not _has_preauth:
            messages.error(request, 'Cannot order investigations — insurance pre-authorisation required.')
            return redirect('investigations:order', consultation_pk=consultation_pk)

        form = InvestigationOrderForm(request.POST)
        payment_waived = request.POST.get('payment_waived') == '1'
        waive_reason = request.POST.get('waive_reason', '').strip()
        if form.is_valid():
            if payment_waived and not waive_reason:
                messages.error(request, 'A reason is required when waiving payment. This is logged for audit.')
            else:
                order = form.save(commit=False)
                order.consultation = consultation
                order.patient = consultation.patient
                order.ordered_by = request.user
                order.created_by = request.user

                # Laterality enforcement — block NA when investigation type requires it
                inv_type = order.investigation_type
                if inv_type.laterality_required and order.eye == Laterality.NA:
                    messages.error(
                        request,
                        f'{inv_type.name} requires laterality (OD/OS/OU). '
                        f'"Not Applicable" is not allowed for this investigation type.'
                    )
                    return render(request, 'investigations/order_form.html', {
                        'form': form, 'consultation': consultation,
                        'types': InvestigationType.objects.filter(is_active=True).order_by('category', 'name'),
                    })

                # Payment status from waiver
                if payment_waived:
                    order.payment_status = PaymentStatus.WAIVED
                    order.payment_authorized_by = request.user
                    order.payment_authorized_at = timezone.now()
                    order.payment_authorization_reason = waive_reason

                # Prior study check
                prior_count = InvestigationOrder.objects.filter(
                    patient=consultation.patient,
                    investigation_type=order.investigation_type,
                    status='COMPLETED',
                    is_deleted=False,
                ).count()
                if prior_count > 0 and not request.POST.get('prior_acknowledged'):
                    latest = InvestigationOrder.objects.filter(
                        patient=consultation.patient,
                        investigation_type=order.investigation_type,
                        status='COMPLETED',
                        is_deleted=False,
                    ).order_by('-created_at').first()
                    order.prior_study_warning = True
                    order.prior_study_warning_text = (
                        f'{prior_count} prior {order.investigation_type.name} study(ies). '
                        f'Last: {latest.created_at.strftime("%d %b %Y") if latest else "?"}'
                    )

                # Default device from investigation type
                inv_type = order.investigation_type
                if inv_type.default_device and not order.device:
                    order.device = inv_type.default_device

                # ── Duplicate order prevention ──────────────────────────────
                # Block if same exam type already ordered today for this patient
                # (regardless of who ordered it — nurse or doctor)
                _today = timezone.localdate()
                _existing = InvestigationOrder.objects.filter(
                    patient=consultation.patient,
                    investigation_type=inv_type,
                    created_at__date=_today,
                    is_deleted=False,
                ).exclude(status='CANCELLED')
                if _existing.exists():
                    _ex = _existing.first()
                    messages.warning(
                        request,
                        f'{inv_type.name} was already ordered today '
                        f'(by {_ex.ordered_by.get_full_name() if _ex.ordered_by else "Triage"}, '
                        f'{_ex.get_status_display()}). '
                        f'Duplicate order not created.'
                    )
                    return redirect('consultations:detail', pk=consultation.pk)

                order.save()

                # ── Payment check: skip work order + route directly if already paid ──
                # Strategy: check BOTH (a) existing paid InvestigationOrder for same
                # exam type today AND (b) invoice item description matching.
                # This prevents double-charging even if descriptions differ slightly.
                _already_paid = False
                if not payment_waived:
                    try:
                        # Method 1: Existing PAID order for same exam type today
                        _paid_order_exists = InvestigationOrder.objects.filter(
                            patient=consultation.patient,
                            investigation_type=inv_type,
                            created_at__date=_today,
                            payment_status=PaymentStatus.PAID,
                            is_deleted=False,
                        ).exclude(pk=order.pk).exists()
                        if _paid_order_exists:
                            _already_paid = True

                        # Method 2: Invoice item description match (fallback for
                        # exams paid at cashier before any order was created)
                        if not _already_paid:
                            from apps.billing.models import Invoice, InvoiceItem, InvoiceStatus as _InvSt
                            _paid_invs = Invoice.objects.filter(
                                patient=consultation.patient, issue_date=_today,
                                status__in=[_InvSt.PAID, _InvSt.PARTIALLY_PAID],
                                is_deleted=False,
                            )
                            _paid_descs = set()
                            for _pi in _paid_invs:
                                _paid_descs.update(
                                    InvoiceItem.objects.filter(
                                        invoice=_pi, is_deleted=False,
                                        category__in=['INVEST', 'CONSULT', 'CLINICAL'],
                                    ).values_list('description', flat=True)
                                )
                            if _paid_descs:
                                _exam_name_lc = inv_type.name.lower()
                                _exam_code_lc = (inv_type.code or '').lower()
                                # Match by name OR code substring in any paid description
                                if any(
                                    _exam_name_lc in d.lower() or
                                    (_exam_code_lc and _exam_code_lc in d.lower())
                                    for d in _paid_descs
                                ):
                                    _already_paid = True

                        if _already_paid:
                            order.payment_status = PaymentStatus.PAID
                            order.save(update_fields=['payment_status'])
                    except Exception:
                        pass

                # ServiceWorkOrder for billing — only if NOT already paid
                if not _already_paid:
                    try:
                        from apps.billing.models import ServiceWorkOrder, WorkOrderStatus, ServiceCategory
                        import logging as _logging
                        _log = _logging.getLogger('ehr.investigations')
                        wo_status = WorkOrderStatus.PENDING if payment_waived else WorkOrderStatus.PENDING_PAYMENT
                        # Calculate quantity: ×2 for OU when billed_per_eye
                        qty = 2 if (inv_type.billed_per_eye and order.eye == Laterality.OU) else 1
                        total_price = inv_type.unit_price * qty
                        price_note = f'{inv_type.unit_price:,.0f} FCFA' + (f' × 2 eyes = {total_price:,.0f} FCFA' if qty == 2 else '')
                        wo_notes = f'Payment waived — {waive_reason}' if payment_waived else price_note
                        _CLINICAL_CATS = {'REFRACTION', 'LOW_VISION', 'ORTHOPTICS'}
                        _wo_cat = ServiceCategory.CLINICAL_EXAM if inv_type.category in _CLINICAL_CATS else ServiceCategory.INVESTIGATION
                        _wo_label = 'Clinical Exam' if inv_type.category in _CLINICAL_CATS else 'Investigation'
                        ServiceWorkOrder.objects.create(
                            patient=consultation.patient,
                            consultation=consultation,
                            category=_wo_cat,
                            description=f'{_wo_label}: {inv_type.name} ({order.get_eye_display()}) — {price_note}',
                            status=wo_status,
                            notes=wo_notes,
                            created_by=request.user,
                        )
                    except Exception as exc:
                        import logging as _logging
                        _logging.getLogger('ehr.investigations').error(
                            'ServiceWorkOrder creation failed for investigation %s: %s', order.pk, exc,
                        )

                # Route: waived OR already paid → direct to examiner, else → cashier
                try:
                    if payment_waived or _already_paid:
                        from apps.core.patient_flow import auto_route_to_investigation
                        auto_route_to_investigation(consultation, ordered_by=request.user, category=inv_type.category)
                    else:
                        # Route to cashier — after payment, billing bridge routes to examiner
                        from apps.core.patient_flow import _auto_route_to_dept
                        visit = getattr(consultation, 'visit', None)
                        if visit and visit.status not in ('AT_CASHIER', 'BILLING', 'COMPLETED', 'DISCHARGED'):
                            _auto_route_to_dept(
                                visit=visit,
                                visit_status='AT_CASHIER',
                                qms_service_type='CASHIER',
                                dept_code='CASHIER',
                                triggered_by=request.user,
                                notes=f'Routed to cashier for {inv_type.name} payment.',
                            )
                except Exception as exc:
                    import logging as _logging
                    _logging.getLogger('ehr.investigations').warning(
                        'Auto-route after investigation order failed for order %s: %s', order.pk, exc,
                    )

                # Notify WebSocket — doctor workstation loses patient, target gains patient
                try:
                    from apps.core.ws_notify import notify_queue as _ws_nq_ord
                    _ws_nq_ord('workstation')
                    _ws_nq_ord('invest')
                    if not payment_waived and not _already_paid:
                        _ws_nq_ord('cashier')
                except Exception:
                    pass

                _route_msg = 'examiner queue (already paid)' if _already_paid else ('cashier for payment' if not payment_waived else 'examiner queue')
                messages.success(
                    request,
                    f'Investigation ordered: {inv_type.name} ({order.get_eye_display()}). '
                    f'Patient routed to {_route_msg}.'
                )
                return redirect('consultations:detail', pk=consultation_pk)
    else:
        form = InvestigationOrderForm()

    # Group types by category
    from itertools import groupby
    OPTOMETRY_CATS = {'ORTHOPTICS', 'LOW_VISION', 'REFRACTION', 'SPECULAR'}
    is_optometry = request.GET.get('cat') == 'optometry'
    _qs = InvestigationType.objects.filter(is_active=True)
    if is_optometry:
        _qs = _qs.filter(category__in=OPTOMETRY_CATS)
    else:
        _qs = _qs.exclude(category__in=OPTOMETRY_CATS)
    _all_types = _qs.order_by('category', 'name')
    _grouped = []
    _cat_labels = dict(InvestigationCategory.choices)
    for cat, items in groupby(_all_types, key=lambda t: t.category):
        label = _cat_labels.get(cat, (cat or 'Other').replace('_', ' ').title())
        _grouped.append((label, list(items)))

    # Prior studies for this patient
    prior_orders = InvestigationOrder.objects.filter(
        patient=consultation.patient,
        status='COMPLETED',
        is_deleted=False,
    ).select_related('investigation_type').order_by('-created_at')[:20]

    return render(request, 'investigations/order_form.html', {
        'form': form,
        'consultation': consultation,
        'grouped_types': _grouped,
        'is_optometry': is_optometry,
        'prior_orders': prior_orders,
    })


# ══════════════════════════════════════════════════════════════════════════════
# DETAIL
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def investigation_detail_view(request, pk):
    order = get_object_or_404(
        InvestigationOrder.objects.select_related(
            'patient', 'investigation_type', 'ordered_by', 'assigned_to',
            'device', 'payment_authorized_by', 'consent_obtained_by',
        ),
        pk=pk, is_deleted=False,
    )
    result = getattr(order, 'result', None)
    acquisition = getattr(order, 'acquisition', None)
    biometry = getattr(order, 'biometry', None)
    contrast_reactions = order.contrast_reactions.all() if order.investigation_type.contrast_involved else []
    amendments = result.amendments.all() if result else []

    # Prior studies for comparison
    prior_orders = InvestigationOrder.objects.filter(
        patient=order.patient,
        investigation_type=order.investigation_type,
        status='COMPLETED',
        is_deleted=False,
    ).exclude(pk=pk).select_related('result').order_by('-created_at')[:5]

    _OPTOMETRY_CATS = {'REFRACTION', 'LOW_VISION', 'ORTHOPTICS'}
    is_optometry = order.investigation_type.category in _OPTOMETRY_CATS
    exam_code = order.investigation_type.code or ''

    return render(request, 'investigations/detail.html', {
        'order': order,
        'result': result,
        'acquisition': acquisition,
        'biometry': biometry,
        'contrast_reactions': contrast_reactions,
        'amendments': amendments,
        'prior_orders': prior_orders,
        'is_optometry': is_optometry,
        'exam_code': exam_code,
    })


@login_required
def print_request_slip_view(request, pk):
    """Print a request slip for the patient to carry to the investigation room."""
    order = get_object_or_404(
        InvestigationOrder.objects.select_related(
            'patient', 'investigation_type', 'ordered_by', 'consultation',
        ),
        pk=pk, is_deleted=False,
    )
    # Fetch other pending orders for same patient/visit to print all at once
    sibling_orders = list(
        InvestigationOrder.objects.filter(
            patient=order.patient,
            consultation=order.consultation,
            status__in=['ORDERED', 'SCHEDULED', 'IN_PROGRESS'],
            is_deleted=False,
        ).exclude(pk=pk).select_related('investigation_type').order_by('created_at')
    )
    from apps.accounts.models import HospitalConfig
    hospital = HospitalConfig.get()
    return render(request, 'investigations/request_slip.html', {
        'order': order,
        'sibling_orders': sibling_orders,
        'hospital': hospital,
    })


# ══════════════════════════════════════════════════════════════════════════════
# ACQUISITION WORKFLOW — Quality gating at the chair
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def start_investigation_view(request, pk):
    """Begin acquisition — creates AcquisitionRecord, sets acquisition_status to IN_PROGRESS."""
    if not request.user.can_record_investigation_results():
        return HttpResponseForbidden()
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)

    if order.status == InvestigationOrder.Status.ORDERED:
        order.status = InvestigationOrder.Status.IN_PROGRESS
        order.acquisition_status = AcquisitionStatus.IN_PROGRESS
        order.save(update_fields=['status', 'acquisition_status', 'updated_at'])

    # Create acquisition record if not exists
    if not hasattr(order, 'acquisition'):
        AcquisitionRecord.objects.create(
            order=order,
            performed_by=request.user,
            device=order.device,
            device_serial=order.device.serial_number if order.device else '',
            started_at=timezone.now(),
            laterality_confirmed=order.eye,
            created_by=request.user,
        )

    return redirect('investigations:workstation')


@login_required
@require_POST
def complete_acquisition_view(request, pk):
    """
    Complete acquisition with quality gating.
    Technician submits quality metrics; system auto-checks against thresholds.
    """
    if not request.user.can_record_investigation_results():
        return HttpResponseForbidden()
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)

    acq, created = AcquisitionRecord.objects.get_or_create(
        order=order,
        defaults={
            'performed_by': request.user,
            'device': order.device,
            'started_at': timezone.now(),
            'created_by': request.user,
        }
    )

    # Update acquisition fields from POST
    acq.performed_by = request.user
    acq.completed_at = timezone.now()
    acq.laterality_confirmed = request.POST.get('laterality_confirmed', order.eye)
    acq.dilation_status_at_acquisition = request.POST.get('dilation_status', '')
    acq.protocol_used = request.POST.get('protocol_used', '')

    # Quality metrics
    qm = request.POST.get('quality_metric_value', '').strip()
    if qm:
        from decimal import Decimal, InvalidOperation
        try:
            acq.quality_metric_value = Decimal(qm)
        except (InvalidOperation, ValueError):
            pass

    # VF specific
    for fld in ('fixation_losses_percent', 'false_positive_percent', 'false_negative_percent'):
        val = request.POST.get(fld, '').strip()
        if val:
            from decimal import Decimal, InvalidOperation
            try:
                setattr(acq, fld, Decimal(val))
            except (InvalidOperation, ValueError):
                pass

    # OCT specific
    ss = request.POST.get('signal_strength', '').strip()
    if ss:
        from decimal import Decimal, InvalidOperation
        try:
            acq.signal_strength = Decimal(ss)
        except (InvalidOperation, ValueError):
            pass

    acq.quality_notes = request.POST.get('quality_notes', '')
    acq.save()

    # Auto quality check
    passed, reason = acq.check_quality()
    if passed:
        acq.quality_passed = True
        acq.save(update_fields=['quality_passed'])
        order.acquisition_status = AcquisitionStatus.ACQUIRED
        order.save(update_fields=['acquisition_status', 'updated_at'])
        messages.success(request, f'Acquisition completed — quality passed.')
    else:
        acq.quality_passed = False
        acq.quality_notes = (acq.quality_notes or '') + f'\nAuto-fail: {reason}'
        acq.save(update_fields=['quality_passed', 'quality_notes'])
        order.acquisition_status = AcquisitionStatus.QUALITY_FAILED
        order.save(update_fields=['acquisition_status', 'updated_at'])
        messages.warning(request, f'Quality check FAILED: {reason}. Consider repeat acquisition.')

    return redirect('investigations:detail', pk=pk)


@login_required
@require_POST
def repeat_acquisition_view(request, pk):
    """Mark acquisition for repeat — resets acquisition status, creates new record."""
    if not request.user.can_record_investigation_results():
        return HttpResponseForbidden()
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)

    old_acq = getattr(order, 'acquisition', None)
    repeat_count = 0
    if old_acq:
        repeat_count = old_acq.repeat_count + 1
        # Preserve previous attempt data in order notes before deleting
        prev_summary = (
            f'[Repeat #{repeat_count}] Previous acquisition by {old_acq.performed_by} '
            f'at {old_acq.started_at.strftime("%d %b %Y %H:%M") if old_acq.started_at else "?"}'
            f' — Quality: {"PASS" if old_acq.quality_passed else "FAIL"}'
            f' (metric: {old_acq.quality_metric_value or "N/A"})'
            f' — Notes: {old_acq.quality_notes or "none"}'
        )
        order.notes = (order.notes or '') + f'\n{prev_summary}'
        order.save(update_fields=['notes', 'updated_at'])
        old_acq.delete()

    # Create fresh acquisition record
    AcquisitionRecord.objects.create(
        order=order,
        performed_by=request.user,
        device=order.device,
        started_at=timezone.now(),
        laterality_confirmed=order.eye,
        is_repeat=True,
        repeat_reason=request.POST.get('repeat_reason', ''),
        repeat_count=repeat_count,
        created_by=request.user,
    )
    order.acquisition_status = AcquisitionStatus.REPEAT
    order.save(update_fields=['acquisition_status', 'updated_at'])

    messages.info(request, f'Repeat acquisition #{repeat_count} started.')
    return redirect('investigations:detail', pk=pk)


@login_required
@require_POST
def override_quality_view(request, pk):
    """Senior tech / MD can override a quality failure."""
    u = request.user
    if not (u.is_medical_director or u.is_super_admin):
        return HttpResponseForbidden()
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)
    acq = getattr(order, 'acquisition', None)
    if acq:
        acq.quality_passed = True
        acq.quality_notes = (acq.quality_notes or '') + f'\n[Quality override by {u.get_full_name()}]'
        acq.save(update_fields=['quality_passed', 'quality_notes'])
    order.acquisition_status = AcquisitionStatus.ACQUIRED
    order.save(update_fields=['acquisition_status', 'updated_at'])
    messages.success(request, 'Quality override applied.')
    return redirect('investigations:detail', pk=pk)


# ══════════════════════════════════════════════════════════════════════════════
# RESULT ENTRY & REPORTING
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def add_result_view(request, pk):
    if not request.user.can_record_investigation_results():
        return HttpResponseForbidden("Only Investigation Technicians can enter results.")
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)
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
            # Structured result fields
            structured = {}
            structured_keys = [
                # Visual field
                'vf_md_od', 'vf_md_os', 'vf_psd_od', 'vf_psd_os',
                'vf_vfi_od', 'vf_vfi_os', 'vf_ght_od', 'vf_ght_os',
                'vf_fixation', 'vf_false_pos', 'vf_false_neg', 'vf_reliability',
                'vf_progression', 'vf_comments',
                # OCT
                'cmt_od', 'cmt_os', 'cube_vol_od', 'cube_vol_os',
                'rnfl_avg_od', 'rnfl_avg_os', 'rnfl_sup_od', 'rnfl_sup_os',
                'rnfl_inf_od', 'rnfl_inf_os', 'rnfl_nas_od', 'rnfl_temp_od',
                'gcc_avg_od', 'gcc_avg_os', 'cd_ratio_od', 'cd_ratio_os',
                'rim_area_od', 'rim_area_os', 'signal_strength', 'scan_quality',
                # Fundus photo
                'cdr_od', 'cdr_os', 'disc_colour_od', 'disc_colour_os',
                'macula_od', 'macula_os', 'vessels_od', 'vessels_os',
                'periphery_od', 'periphery_os',
                # FFA
                'ffa_arterial', 'ffa_av', 'ffa_venous', 'ffa_late',
                'ffa_od', 'ffa_os', 'ffa_leakage', 'ffa_ischaemia', 'ffa_reaction',
                # B-Scan
                'bscan_vitreous', 'bscan_retina', 'bscan_od', 'bscan_os',
                'bscan_globe', 'bscan_choroid', 'bscan_axial',
                # Biometry
                'axial_length_od', 'axial_length_os', 'k1_od', 'k1_os',
                'k2_od', 'k2_os', 'acd_od', 'acd_os', 'iol_od', 'iol_os',
                'target_ref_od', 'target_ref_os', 'biometry_formula',
                'iol_model', 'a_constant', 'biometry_notes',
                # Pachymetry
                'cct_od', 'cct_os', 'pachy_method', 'iop_correction',
                # Topography
                'simk1_od', 'simk2_od', 'simk1_os', 'simk2_os',
                'astig_od', 'axis_od', 'astig_os', 'axis_os',
                'topo_pattern', 'thinnest_od', 'thinnest_os',
                # Specular microscopy
                'ecd_od', 'ecd_os', 'cv_od', 'cv_os', 'hex_od', 'hex_os',
                'spec_cct_od', 'spec_cct_os',
                # Generic
                'findings_od', 'findings_os', 'other_findings',
            ]
            for key in structured_keys:
                val = request.POST.get(key, '').strip()
                if val:
                    structured[key] = val
            if structured:
                result.result_data = structured

            # Report status
            result.reported_by = request.user
            result.reported_at = timezone.now()
            result.save()

            # ── Critical value auto-check ──
            rules = order.investigation_type.critical_value_rules or {}
            if rules and structured:
                critical_flags = []
                for field_key, rule in rules.items():
                    val_str = structured.get(field_key)
                    if not val_str:
                        continue
                    try:
                        val = float(val_str)
                    except (ValueError, TypeError):
                        continue
                    lo = rule.get('min')
                    hi = rule.get('max')
                    label = rule.get('label', field_key)
                    if lo is not None and val < float(lo):
                        critical_flags.append(f'{label}={val} (min {lo})')
                    if hi is not None and val > float(hi):
                        critical_flags.append(f'{label}={val} (max {hi})')
                if critical_flags:
                    result.is_critical = True
                    result.critical_value_text = '; '.join(critical_flags)[:255]
                    result.save(update_fields=['is_critical', 'critical_value_text'])

            # ── Save acquisition record fields ──
            protocol = request.POST.get('protocol_used', '').strip()
            cooperation = request.POST.get('cooperation_level', '').strip()
            tech_obs = request.POST.get('technician_observations', '').strip()
            if protocol or cooperation or tech_obs:
                acq, _ = AcquisitionRecord.objects.get_or_create(
                    order=order,
                    defaults={'performed_by': request.user, 'created_by': request.user},
                )
                if protocol:
                    acq.protocol_used = protocol
                if cooperation:
                    acq.cooperation_level = cooperation
                if tech_obs:
                    acq.technician_observations = tech_obs
                acq.save()

            order.status = InvestigationOrder.Status.COMPLETED
            order.report_status = ReportStatus.REPORTED
            order.save(update_fields=['status', 'report_status', 'updated_at'])

            # File upload
            uploaded_file = request.FILES.get('result_file')
            if uploaded_file:
                file_laterality = request.POST.get('file_laterality', Laterality.NA)
                InvestigationFile.objects.create(
                    result=result,
                    file=uploaded_file,
                    file_type='IMAGE' if uploaded_file.content_type.startswith('image') else 'PDF',
                    laterality=file_laterality,
                    uploaded_by=request.user,
                )

            # Notify ordering doctor
            try:
                from apps.notifications.utils import notify
                from apps.notifications.models import NotificationType, NotificationPriority
                if order.ordered_by:
                    priority = NotificationPriority.URGENT if result.is_critical else NotificationPriority.HIGH
                    prefix = 'CRITICAL — ' if result.is_critical else ''
                    notify(
                        recipient=order.ordered_by,
                        title=f'{prefix}Result ready: {order.investigation_type.name} — {order.patient.full_name}',
                        message=(
                            f'{order.investigation_type.name} ({order.get_eye_display()}) result entered by '
                            f'{request.user.get_full_name() or request.user.username}. '
                            f'Patient: {order.patient.full_name} ({order.patient.patient_id})'
                            f'{" — " + result.critical_value_text if result.is_critical else ""}'
                        ),
                        link=f'/investigations/{order.pk}/',
                        notification_type=NotificationType.GENERAL,
                        priority=priority,
                    )
            except Exception:
                pass

            # Check auto-return to doctor (all exams done?)
            try:
                visit = getattr(order.consultation, 'visit', None) if order.consultation else None
                if visit:
                    from apps.core.patient_flow import check_and_autoreturn_to_doctor
                    check_and_autoreturn_to_doctor(visit, triggered_by=request.user)
            except Exception:
                pass

            messages.success(request, 'Investigation result recorded.')
            return redirect('investigations:workstation')
    else:
        form = InvestigationResultForm()

    # Imaging subtype for conditional fields — map category then refine by code/name
    cat = order.investigation_type.category
    code_up = order.investigation_type.code.upper()
    name_up = order.investigation_type.name.upper()
    CATEGORY_SUBTYPE_MAP = {
        'OCT': 'OCT', 'BIOMETRY': 'BIOMETRY', 'PACHYMETRY': 'PACHYMETRY',
        'TOPOGRAPHY': 'TOPOGRAPHY', 'SPECULAR': 'SPECULAR',
        'VISUAL_FIELD': 'VF', 'PERIMETRY': 'VF', 'ANGIOGRAPHY': 'FFA',
        'FUNDUS_PHOTO': 'FUNDUS',
    }
    imaging_subtype = CATEGORY_SUBTYPE_MAP.get(cat, 'GENERIC')
    if imaging_subtype == 'GENERIC' and cat == 'IMAGING':
        if 'OCT' in code_up or 'OCT' in name_up:
            imaging_subtype = 'OCT'
        elif 'BSCAN' in code_up or 'B_SCAN' in code_up or 'B-SCAN' in name_up or 'BSCAN' in name_up:
            imaging_subtype = 'BSCAN'
        elif 'FFA' in code_up or 'FLUORESCEIN' in name_up or 'ANGIOGRAPHY' in name_up:
            imaging_subtype = 'FFA'
        elif 'FUNDUS' in code_up or 'FUNDUS' in name_up or 'PHOTO' in name_up:
            imaging_subtype = 'FUNDUS'

    # Prior results for comparison
    prev_results = list(
        InvestigationOrder.objects.filter(
            patient=order.patient,
            investigation_type=order.investigation_type,
            status='COMPLETED',
            is_deleted=False,
        ).exclude(pk=order.pk)
        .select_related('result')
        .order_by('-created_at')[:5]
    )

    protocols = order.investigation_type.available_protocols or []

    return render(request, 'investigations/result_form.html', {
        'form': form,
        'order': order,
        'imaging_subtype': imaging_subtype,
        'prev_results': prev_results,
        'protocols': protocols,
    })


@login_required
def verify_result_view(request, pk):
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)
    can_verify = (
        request.user.can_record_investigation_results()
        or request.user.is_doctor
        or request.user.is_medical_director
    )
    if not can_verify:
        return HttpResponseForbidden()

    result = get_object_or_404(InvestigationResult, order=order, is_deleted=False)
    if result.is_verified:
        messages.info(request, 'This result has already been verified.')
        return redirect('investigations:detail', pk=pk)

    result.is_verified = True
    result.verified_by = request.user
    result.verified_at = timezone.now()
    result.save(update_fields=['is_verified', 'verified_by', 'verified_at', 'updated_at'])

    order.report_status = ReportStatus.VERIFIED
    order.save(update_fields=['report_status', 'updated_at'])

    messages.success(request, f'Result verified by {request.user.get_full_name()}.')

    # Auto-return to doctor queue
    try:
        visit = order.consultation.visit if order.consultation else None
        if visit:
            from apps.core.patient_flow import check_and_autoreturn_to_doctor
            check_and_autoreturn_to_doctor(visit, triggered_by=request.user)
    except Exception as exc:
        import logging as _logging
        _logging.getLogger('ehr.investigations').warning(
            'Auto-return to doctor failed for order %s: %s', order.pk, exc,
        )
    return redirect('investigations:detail', pk=pk)


@login_required
@require_POST
def acknowledge_result_view(request, pk):
    """Ordering doctor acknowledges they've seen the result."""
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)
    result = get_object_or_404(InvestigationResult, order=order, is_deleted=False)

    if result.acknowledged_by:
        messages.info(request, 'Already acknowledged.')
        return redirect('investigations:detail', pk=pk)

    result.acknowledged_by = request.user
    result.acknowledged_at = timezone.now()
    result.save(update_fields=['acknowledged_by', 'acknowledged_at', 'updated_at'])
    messages.success(request, 'Result acknowledged.')
    return redirect('investigations:detail', pk=pk)


@login_required
@require_POST
def amend_result_view(request, pk):
    """Amend a verified result — creates version trail."""
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)
    result = get_object_or_404(InvestigationResult, order=order, is_deleted=False)

    u = request.user
    if not (u.is_medical_director or u.is_super_admin or u.can_record_investigation_results()):
        return HttpResponseForbidden()

    reason = request.POST.get('amendment_reason', '').strip()
    if not reason:
        messages.error(request, 'Amendment reason is required.')
        return redirect('investigations:detail', pk=pk)

    # Save amendment trail
    InvestigationResultAmendment.objects.create(
        result=result,
        previous_interpretation=result.interpretation,
        previous_data=result.result_data,
        reason=reason,
        amended_by=u,
        version_number=result.version_number,
        created_by=u,
    )

    # Update result
    result.interpretation = request.POST.get('interpretation', result.interpretation)
    new_normal = request.POST.get('is_normal', '')
    if new_normal == 'True':
        result.is_normal = True
    elif new_normal == 'False':
        result.is_normal = False
    result.version_number += 1
    result.save()

    order.report_status = ReportStatus.AMENDED
    order.save(update_fields=['report_status', 'updated_at'])

    messages.success(request, f'Result amended (v{result.version_number}). Previous version preserved.')
    return redirect('investigations:detail', pk=pk)


# ══════════════════════════════════════════════════════════════════════════════
# PAYMENT AUTHORIZATION
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def authorize_payment_view(request, pk):
    """Authorize payment bypass (STAT, waiver, insurance, etc.)."""
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)
    u = request.user

    new_status = request.POST.get('payment_status', '')
    reason = request.POST.get('reason', '').strip()

    allowed_statuses = [s[0] for s in PaymentStatus.choices if s[0] != PaymentStatus.UNPAID]
    if new_status not in allowed_statuses:
        messages.error(request, 'Invalid payment status.')
        return redirect('investigations:detail', pk=pk)

    if new_status in (PaymentStatus.WAIVED, PaymentStatus.STAT_OVERRIDE, PaymentStatus.FREE_REPEAT) and not reason:
        messages.error(request, 'Reason required for this payment authorization type.')
        return redirect('investigations:detail', pk=pk)

    order.payment_status = new_status
    order.payment_authorized_by = u
    order.payment_authorized_at = timezone.now()
    order.payment_authorization_reason = reason
    order.save(update_fields=[
        'payment_status', 'payment_authorized_by', 'payment_authorized_at',
        'payment_authorization_reason', 'updated_at',
    ])

    messages.success(request, f'Payment status updated to {order.get_payment_status_display()}.')
    return redirect('investigations:detail', pk=pk)


# ══════════════════════════════════════════════════════════════════════════════
# CONTRAST PROCEDURE SAFETY (FFA / ICG)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def contrast_safety_view(request, pk):
    """Contrast safety checklist — consent, allergy, pregnancy, resuscitation trolley."""
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)

    if not order.investigation_type.contrast_involved:
        messages.info(request, 'This investigation does not involve contrast.')
        return redirect('investigations:detail', pk=pk)

    if request.method == 'POST':
        order.consent_obtained = request.POST.get('consent_obtained') == '1'
        if order.consent_obtained:
            order.consent_obtained_by = request.user
            order.consent_obtained_at = timezone.now()
        order.allergy_check_done = request.POST.get('allergy_check_done') == '1'
        preg = request.POST.get('pregnancy_check_done', '')
        if preg == '1':
            order.pregnancy_check_done = True
        elif preg == '0':
            order.pregnancy_check_done = False
        elif preg == 'na':
            order.pregnancy_check_done = None
        order.resuscitation_trolley_checked = request.POST.get('resuscitation_trolley_checked') == '1'
        order.contrast_dye_batch = request.POST.get('contrast_dye_batch', '')
        vol = request.POST.get('contrast_volume_ml', '').strip()
        if vol:
            from decimal import Decimal, InvalidOperation
            try:
                order.contrast_volume_ml = Decimal(vol)
            except (InvalidOperation, ValueError):
                pass
        order.save()
        messages.success(request, 'Contrast safety checklist saved.')
        return redirect('investigations:detail', pk=pk)

    # Check patient allergy history
    allergies = []
    try:
        from apps.patients.models import PatientAllergy
        allergies = list(PatientAllergy.objects.filter(
            patient=order.patient, is_deleted=False
        ))
    except Exception:
        pass

    return render(request, 'investigations/contrast_safety.html', {
        'order': order,
        'allergies': allergies,
    })


@login_required
@require_POST
def contrast_reaction_view(request, pk):
    """Log an adverse contrast reaction."""
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)

    ContrastReactionLog.objects.create(
        order=order,
        patient=order.patient,
        dye_used=request.POST.get('dye_used', ''),
        dye_batch=order.contrast_dye_batch,
        dye_volume_ml=order.contrast_volume_ml,
        severity=request.POST.get('severity', 'MILD'),
        symptoms=request.POST.get('symptoms', ''),
        treatment_given=request.POST.get('treatment_given', ''),
        outcome=request.POST.get('outcome', ''),
        photographer=request.user,
        escalated=request.POST.get('escalated') == '1',
        escalated_to=request.POST.get('escalated_to', ''),
        created_by=request.user,
    )

    order.contrast_adverse_reaction = request.POST.get('symptoms', '')
    order.save(update_fields=['contrast_adverse_reaction', 'updated_at'])

    messages.warning(request, 'Adverse reaction logged. Review patient status immediately.')
    return redirect('investigations:detail', pk=pk)


# ══════════════════════════════════════════════════════════════════════════════
# BIOMETRY — IOL Calculation Safety Workflow
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def biometry_record_view(request, pk):
    """Record biometry measurements with safety checks."""
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)
    if not request.user.can_record_investigation_results():
        return HttpResponseForbidden()

    biometry = getattr(order, 'biometry', None)

    if request.method == 'POST':
        from decimal import Decimal, InvalidOperation

        if not biometry:
            biometry = BiometryRecord(order=order, created_by=request.user)

        biometry.measured_by = request.user

        # Parse decimal fields
        decimal_fields = [
            'axial_length_od', 'axial_length_os',
            'k1_od', 'k2_od', 'k1_os', 'k2_os',
            'acd_od', 'acd_os', 'wtw',
            'lens_thickness_od', 'lens_thickness_os',
            'a_constant',
            'iol_power_od', 'iol_power_os',
            'target_refraction_od', 'target_refraction_os',
            'signal_quality_od', 'signal_quality_os',
        ]
        for fld in decimal_fields:
            val = request.POST.get(fld, '').strip()
            if val:
                try:
                    setattr(biometry, fld, Decimal(val))
                except (InvalidOperation, ValueError):
                    pass

        # Integer fields
        for fld in ('valid_measurements_od', 'valid_measurements_os'):
            val = request.POST.get(fld, '').strip()
            if val:
                try:
                    setattr(biometry, fld, int(val))
                except ValueError:
                    pass

        # String fields
        biometry.al_method = request.POST.get('al_method', '')
        biometry.formula_primary = request.POST.get('formula_primary', '')
        biometry.formula_secondary = request.POST.get('formula_secondary', '')
        biometry.iol_model = request.POST.get('iol_model', '')

        # Safety checks (boolean)
        biometry.al_plausibility_check = request.POST.get('al_plausibility_check') == '1'
        biometry.k_consistency_check = request.POST.get('k_consistency_check') == '1'
        biometry.refraction_crosscheck_done = request.POST.get('refraction_crosscheck_done') == '1'

        biometry.save()  # auto inter-eye AL check in save()

        if biometry.inter_eye_al_flagged:
            messages.warning(
                request,
                f'Inter-eye axial length difference {biometry.inter_eye_al_difference}mm '
                f'exceeds 0.3mm threshold. Please verify measurements.'
            )
        else:
            messages.success(request, 'Biometry measurements saved.')

        return redirect('investigations:detail', pk=pk)

    return render(request, 'investigations/biometry_form.html', {
        'order': order,
        'biometry': biometry,
    })


@login_required
@require_POST
def biometry_surgeon_signoff_view(request, pk):
    """Surgeon reviews and approves biometry/IOL selection."""
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)
    biometry = get_object_or_404(BiometryRecord, order=order)

    if not request.user.is_doctor:
        return HttpResponseForbidden()

    biometry.surgeon = request.user
    biometry.surgeon_approved = True
    biometry.surgeon_approved_at = timezone.now()
    biometry.surgeon_notes = request.POST.get('surgeon_notes', '')
    biometry.save(update_fields=[
        'surgeon', 'surgeon_approved', 'surgeon_approved_at', 'surgeon_notes', 'updated_at',
    ])
    messages.success(request, f'Biometry approved by {request.user.get_full_name()}.')
    return redirect('investigations:detail', pk=pk)


@login_required
@require_POST
def biometry_second_verify_view(request, pk):
    """Second-person verification of biometry (different from original measurer)."""
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)
    biometry = get_object_or_404(BiometryRecord, order=order)

    if request.user == biometry.measured_by:
        messages.error(request, 'Second verification must be by a different person.')
        return redirect('investigations:detail', pk=pk)

    biometry.second_verified_by = request.user
    biometry.second_verified_at = timezone.now()
    biometry.save(update_fields=['second_verified_by', 'second_verified_at', 'updated_at'])
    messages.success(request, 'Second-person verification completed.')
    return redirect('investigations:detail', pk=pk)


@login_required
@require_POST
def biometry_lock_view(request, pk):
    """Lock biometry once surgery is booked — prevents further changes."""
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)
    biometry = get_object_or_404(BiometryRecord, order=order)

    if not (request.user.is_doctor or request.user.is_super_admin):
        return HttpResponseForbidden()

    biometry.is_locked = True
    biometry.locked_at = timezone.now()
    biometry.locked_reason = request.POST.get('lock_reason', 'Surgery booked')
    biometry.save(update_fields=['is_locked', 'locked_at', 'locked_reason', 'updated_at'])
    messages.success(request, 'Biometry locked for surgery.')
    return redirect('investigations:detail', pk=pk)


@login_required
@require_POST
def biometry_postop_view(request, pk):
    """Record post-op refraction for prediction error calculation."""
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)
    biometry = get_object_or_404(BiometryRecord, order=order)

    from decimal import Decimal, InvalidOperation
    for fld in ('post_op_refraction_od', 'post_op_refraction_os'):
        val = request.POST.get(fld, '').strip()
        if val:
            try:
                setattr(biometry, fld, Decimal(val))
            except (InvalidOperation, ValueError):
                pass

    biometry.post_op_recorded_at = timezone.now()
    biometry.save()  # auto-calculates prediction error in save()

    messages.success(request, 'Post-op refraction recorded. Prediction error calculated.')
    return redirect('investigations:detail', pk=pk)


# ══════════════════════════════════════════════════════════════════════════════
# DEVICE MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def device_list_view(request):
    """List all investigation devices."""
    if not _is_invest_staff(request.user):
        return HttpResponseForbidden()
    devices = Device.objects.filter(is_deleted=False).order_by('category', 'name')
    return render(request, 'investigations/device_list.html', {'devices': devices})


@login_required
def device_detail_view(request, pk):
    """Device detail with downtimes and recent orders."""
    if not _is_invest_staff(request.user):
        return HttpResponseForbidden()
    device = get_object_or_404(Device, pk=pk, is_deleted=False)
    downtimes = device.downtimes.order_by('-start')[:20]
    recent_orders = InvestigationOrder.objects.filter(
        device=device, is_deleted=False
    ).select_related('patient', 'investigation_type').order_by('-created_at')[:20]
    default_types = device.default_for_types.filter(is_active=True)
    return render(request, 'investigations/device_detail.html', {
        'device': device,
        'downtimes': downtimes,
        'recent_orders': recent_orders,
        'default_types': default_types,
    })


@login_required
def device_create_view(request):
    """Create or edit a device."""
    if not (request.user.is_super_admin or request.user.is_admin_director):
        return HttpResponseForbidden()

    if request.method == 'POST':
        from .models import InvestigationCategory
        device = Device(created_by=request.user)
        device.name = request.POST.get('name', '')
        device.code = request.POST.get('code', '')
        device.manufacturer = request.POST.get('manufacturer', '')
        device.model_number = request.POST.get('model_number', '')
        device.serial_number = request.POST.get('serial_number', '')
        device.room = request.POST.get('room', '')
        device.category = request.POST.get('category', 'OTHER')
        device.is_dicom_capable = request.POST.get('is_dicom_capable') == '1'
        device.dicom_ae_title = request.POST.get('dicom_ae_title', '')
        slot_dur = request.POST.get('slot_duration_minutes', '15')
        device.slot_duration_minutes = int(slot_dur) if slot_dur.isdigit() else 15
        cal = request.POST.get('last_calibration_date', '')
        if cal:
            device.last_calibration_date = cal
        ncal = request.POST.get('next_calibration_due', '')
        if ncal:
            device.next_calibration_due = ncal
        device.notes = request.POST.get('notes', '')
        device.save()
        messages.success(request, f'Device "{device.name}" created.')
        return redirect('investigations:device_detail', pk=device.pk)

    from .models import InvestigationCategory
    return render(request, 'investigations/device_form.html', {
        'categories': InvestigationCategory.choices,
    })


@login_required
def device_edit_view(request, pk):
    """Edit an existing device."""
    if not (request.user.is_super_admin or request.user.is_admin_director):
        return HttpResponseForbidden()

    device = get_object_or_404(Device, pk=pk, is_deleted=False)

    if request.method == 'POST':
        device.name = request.POST.get('name', device.name)
        device.code = request.POST.get('code', device.code)
        device.manufacturer = request.POST.get('manufacturer', '')
        device.model_number = request.POST.get('model_number', '')
        device.serial_number = request.POST.get('serial_number', '')
        device.room = request.POST.get('room', '')
        device.category = request.POST.get('category', device.category)
        device.is_dicom_capable = request.POST.get('is_dicom_capable') == '1'
        device.dicom_ae_title = request.POST.get('dicom_ae_title', '')
        slot_dur = request.POST.get('slot_duration_minutes', '15')
        device.slot_duration_minutes = int(slot_dur) if slot_dur.isdigit() else 15
        device.is_active = request.POST.get('is_active') != '0'
        cal = request.POST.get('last_calibration_date', '')
        if cal:
            device.last_calibration_date = cal
        ncal = request.POST.get('next_calibration_due', '')
        if ncal:
            device.next_calibration_due = ncal
        device.notes = request.POST.get('notes', '')
        device.save()
        messages.success(request, f'Device "{device.name}" updated.')
        return redirect('investigations:device_detail', pk=device.pk)

    from .models import InvestigationCategory
    return render(request, 'investigations/device_form.html', {
        'device': device,
        'categories': InvestigationCategory.choices,
    })


@login_required
@require_POST
def device_downtime_view(request, pk):
    """Record a maintenance downtime for a device."""
    if not _is_invest_staff(request.user):
        return HttpResponseForbidden()
    device = get_object_or_404(Device, pk=pk, is_deleted=False)

    start = request.POST.get('start', '')
    end = request.POST.get('end', '')
    reason = request.POST.get('reason', '')

    if start and end and reason:
        DeviceDowntime.objects.create(
            device=device,
            start=start,
            end=end,
            reason=reason,
            created_by=request.user,
        )
        messages.success(request, f'Downtime recorded for {device.name}.')
    else:
        messages.error(request, 'Start, end, and reason are required.')

    return redirect('investigations:device_detail', pk=device.pk)


# ══════════════════════════════════════════════════════════════════════════════
# DILATION-AWARE VISIT PLAN
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def visit_plan_view(request, patient_id):
    """Create/view a dilation-aware investigation plan for a patient visit."""
    from apps.patients.models import Patient

    patient = get_object_or_404(Patient, patient_id=patient_id, is_deleted=False)
    today = timezone.localdate()

    if request.method == 'POST':
        # Get selected order IDs
        order_ids = request.POST.getlist('order_ids')
        if not order_ids:
            messages.error(request, 'Select at least one investigation.')
            return redirect('investigations:visit_plan', patient_id=patient_id)

        orders = list(InvestigationOrder.objects.filter(
            pk__in=order_ids, is_deleted=False
        ).select_related('investigation_type'))

        # Create plan
        plan = VisitInvestigationPlan.objects.create(
            patient=patient,
            visit_date=today,
            planned_by=request.user,
            notes=request.POST.get('notes', ''),
            created_by=request.user,
        )

        # Auto-sequence: pre-dilation first, then dilation-indifferent, then post-dilation
        from .models import DilationRequirement
        pre = [o for o in orders if o.investigation_type.dilation_requirement == DilationRequirement.BEFORE]
        indiff = [o for o in orders if o.investigation_type.dilation_requirement == DilationRequirement.INDIFFERENT]
        post = [o for o in orders if o.investigation_type.dilation_requirement == DilationRequirement.AFTER]

        seq = 1
        for order in pre:
            VisitInvestigationStep.objects.create(
                plan=plan, order=order, sequence=seq,
                phase=VisitInvestigationStep.Phase.PRE_DILATION,
                estimated_duration_minutes=order.investigation_type.typical_duration_minutes,
            )
            order.slot_sequence = seq
            order.save(update_fields=['slot_sequence'])
            seq += 1

        for order in indiff:
            VisitInvestigationStep.objects.create(
                plan=plan, order=order, sequence=seq,
                phase=VisitInvestigationStep.Phase.PRE_DILATION,
                estimated_duration_minutes=order.investigation_type.typical_duration_minutes,
            )
            order.slot_sequence = seq
            order.save(update_fields=['slot_sequence'])
            seq += 1

        # Dilation wait marker
        if post:
            VisitInvestigationStep.objects.create(
                plan=plan,
                order=post[0],  # placeholder
                sequence=seq,
                phase=VisitInvestigationStep.Phase.DILATION_WAIT,
                estimated_duration_minutes=20,
            )
            seq += 1

        for order in post:
            VisitInvestigationStep.objects.create(
                plan=plan, order=order, sequence=seq,
                phase=VisitInvestigationStep.Phase.POST_DILATION,
                estimated_duration_minutes=order.investigation_type.typical_duration_minutes,
            )
            order.slot_sequence = seq
            order.save(update_fields=['slot_sequence'])
            seq += 1

        messages.success(request, f'Investigation plan created with {seq - 1} steps.')
        return redirect('investigations:visit_plan_detail', plan_pk=plan.pk)

    # GET — show pending orders for this patient
    pending_orders = InvestigationOrder.objects.filter(
        patient=patient,
        status__in=[InvestigationOrder.Status.ORDERED, InvestigationOrder.Status.SCHEDULED],
        is_deleted=False,
    ).select_related('investigation_type').order_by('investigation_type__dilation_requirement', 'created_at')

    existing_plans = VisitInvestigationPlan.objects.filter(
        patient=patient, is_deleted=False, visit_date=today,
    ).prefetch_related('steps__order__investigation_type')

    return render(request, 'investigations/visit_plan.html', {
        'patient': patient,
        'pending_orders': pending_orders,
        'existing_plans': existing_plans,
        'today': today,
    })


@login_required
def visit_plan_detail_view(request, plan_pk):
    """View a visit investigation plan with dilation-aware sequencing."""
    plan = get_object_or_404(
        VisitInvestigationPlan.objects.prefetch_related(
            'steps__order__investigation_type',
            'steps__order__device',
        ),
        pk=plan_pk, is_deleted=False,
    )
    steps = plan.steps.all()
    return render(request, 'investigations/visit_plan_detail.html', {
        'plan': plan,
        'steps': steps,
    })


@login_required
@require_POST
def visit_plan_complete_step_view(request, step_pk):
    """Mark a step in the visit plan as completed."""
    step = get_object_or_404(VisitInvestigationStep, pk=step_pk)
    step.is_completed = True
    step.completed_at = timezone.now()
    step.save(update_fields=['is_completed', 'completed_at'])

    # Check if all steps done
    plan = step.plan
    if not plan.steps.filter(is_completed=False).exists():
        plan.is_completed = True
        plan.save(update_fields=['is_completed'])

    return redirect('investigations:visit_plan_detail', plan_pk=plan.pk)


# ══════════════════════════════════════════════════════════════════════════════
# DILATION TRACKING
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def record_dilation_view(request, pk):
    """Record dilation for a patient's investigation order."""
    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)
    order.dilation_status = request.POST.get('dilation_status', 'dilating')
    order.dilation_time = timezone.now()
    order.dilation_agent = request.POST.get('dilation_agent', '')
    order.save(update_fields=['dilation_status', 'dilation_time', 'dilation_agent', 'updated_at'])
    messages.success(request, f'Dilation recorded: {order.dilation_agent}')

    # Update all other pending orders for same patient on same day
    InvestigationOrder.objects.filter(
        patient=order.patient,
        status__in=[InvestigationOrder.Status.ORDERED, InvestigationOrder.Status.IN_PROGRESS],
        is_deleted=False,
    ).exclude(pk=pk).update(
        dilation_status=order.dilation_status,
        dilation_time=order.dilation_time,
        dilation_agent=order.dilation_agent,
    )

    return redirect('investigations:detail', pk=pk)


# ══════════════════════════════════════════════════════════════════════════════
# BULK START & CANCEL
# ══════════════════════════════════════════════════════════════════════════════

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
    ).update(status=InvestigationOrder.Status.IN_PROGRESS, acquisition_status=AcquisitionStatus.IN_PROGRESS)
    messages.success(request, f'{updated} test(s) marked as In Progress.')
    return redirect('investigations:workstation')


@login_required
def cancel_investigation_order(request, pk):
    """Cancel a pending investigation order."""
    if request.method != 'POST':
        return redirect('investigations:detail', pk=pk)

    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)

    u = request.user
    can_cancel = (
        u == order.ordered_by
        or u.can_record_investigation_results()
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


# ══════════════════════════════════════════════════════════════════════════════
# DICOM IMAGING STUDIES
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def imaging_study_list(request):
    qs = ImagingStudy.objects.filter(is_deleted=False).select_related('patient', 'ordered_by')
    q = request.GET.get('q', '')
    modality = request.GET.get('modality', '')
    reported = request.GET.get('reported', '')
    eye_filter = request.GET.get('eye', '')

    if q:
        qs = qs.filter(Q(patient__first_name__icontains=q) | Q(patient__last_name__icontains=q)
                       | Q(description__icontains=q) | Q(accession_number__icontains=q))
    if modality:
        qs = qs.filter(modality=modality)
    if reported == '1':
        qs = qs.filter(is_reported=True)
    elif reported == '0':
        qs = qs.filter(is_reported=False)
    if eye_filter:
        qs = qs.filter(laterality=eye_filter)

    from django.core.paginator import Paginator
    page_obj = Paginator(qs.order_by('-study_date', '-created_at'), 25).get_page(request.GET.get('page'))
    return render(request, 'investigations/imaging_list.html', {
        'page_obj': page_obj,
        'modalities': ImagingModality.choices,
        'laterality_choices': Laterality.choices,
        'q': q, 'modality': modality, 'reported': reported, 'eye_filter': eye_filter,
    })


@login_required
def imaging_study_create(request):
    from apps.patients.models import Patient

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
            laterality=request.POST.get('laterality', Laterality.OU),
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

    patient_id = request.GET.get('patient', '')
    consultation_id = request.GET.get('consultation', '')
    patient = None
    if patient_id:
        try:
            patient = Patient.objects.get(patient_id=patient_id, is_deleted=False)
        except Patient.DoesNotExist:
            pass

    return render(request, 'investigations/imaging_create.html', {
        'modalities': ImagingModality.choices,
        'laterality_choices': Laterality.choices,
        'patient': patient,
        'consultation_id': consultation_id,
        'today': timezone.localdate(),
    })


@login_required
def imaging_study_detail(request, study_id):
    study = get_object_or_404(ImagingStudy, id=study_id, is_deleted=False)
    return render(request, 'investigations/imaging_detail.html', {'study': study})


@login_required
def imaging_study_report(request, study_id):
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
    from apps.patients.models import Patient
    patient = get_object_or_404(Patient, patient_id=patient_id, is_deleted=False)
    studies = ImagingStudy.objects.filter(
        patient=patient, is_deleted=False
    ).select_related('ordered_by', 'consultation').order_by('-study_date', '-created_at')
    return render(request, 'investigations/patient_imaging.html', {
        'patient': patient,
        'studies': studies,
    })


# ══════════════════════════════════════════════════════════════════════════════
# UNACKNOWLEDGED RESULTS
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def unacknowledged_results_view(request):
    """Show results ordered by this doctor that haven't been acknowledged yet."""
    results = InvestigationResult.objects.filter(
        order__ordered_by=request.user,
        acknowledged_by__isnull=True,
        is_deleted=False,
    ).select_related(
        'order__patient', 'order__investigation_type', 'performed_by'
    ).order_by('-result_date')

    return render(request, 'investigations/unacknowledged_results.html', {
        'results': results,
    })


# ══════════════════════════════════════════════════════════════════════════════
# STATISTICS & REPORTS (preserved from original)
# ══════════════════════════════════════════════════════════════════════════════

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
        _cached['today'] = timezone.now()
        if request.GET.get('pdf'):
            from apps.reports.views import render_pdf
            _cached['pdf_filename'] = 'investigation-stats.pdf'
            return render_pdf('investigations/stats_pdf.html', _cached)
        return render(request, 'investigations/stats.html', _cached)
    _cache_ttl = 300 if (year == today.year and month == today.month) else 86400

    # Imaging-only categories (exclude optometry: REFRACTION, ORTHOPTICS, LOW_VISION)
    _OPTOMETRY_CATS = ['REFRACTION', 'ORTHOPTICS', 'LOW_VISION']

    base = InvestigationOrder.objects.filter(
        is_deleted=False,
        created_at__date__gte=month_start,
        created_at__date__lte=month_end,
    ).exclude(investigation_type__category__in=_OPTOMETRY_CATS)

    # ── KPIs ──────────────────────────────────────────────────────────────────
    total_orders    = base.count()
    pending_count   = base.filter(status__in=['ORDERED', 'IN_PROGRESS']).count()
    completed_count = base.filter(status='COMPLETED').count()
    cancelled_count = base.filter(status='CANCELLED').count()
    urgent_count    = base.filter(urgency__in=['URGENT', 'EMERGENCY', 'STAT']).count()
    abnormal_count  = base.filter(result__is_normal=False).count()
    completion_rate = round(completed_count / total_orders * 100, 1) if total_orders else 0

    # ── Patient Flow Funnel ───────────────────────────────────────────────────
    prescribed_count = total_orders
    paid_count       = base.filter(payment_status__in=PaymentStatus.actionable_statuses()).count()
    unpaid_count     = base.filter(payment_status='UNPAID').count()
    showed_up_count  = base.filter(checked_in_at__isnull=False).count()
    paid_no_show     = base.filter(payment_status__in=PaymentStatus.actionable_statuses(), checked_in_at__isnull=True).exclude(status__in=['COMPLETED', 'CANCELLED']).count()
    show_rate        = round(showed_up_count / paid_count * 100, 1) if paid_count else 0

    # ── Average TAT (order → result) ─────────────────────────────────────────
    from django.db.models import Avg, F, ExpressionWrapper, DurationField
    tat_qs = base.filter(
        status='COMPLETED', result__isnull=False,
        result__result_date__isnull=False,
    ).annotate(
        tat=ExpressionWrapper(
            F('result__result_date') - F('created_at'),
            output_field=DurationField()
        )
    ).aggregate(avg_tat=Avg('tat'))
    avg_tat = tat_qs['avg_tat']
    if avg_tat:
        avg_tat_mins = int(avg_tat.total_seconds() / 60)
        if avg_tat_mins < 60:
            avg_tat_str = f'{avg_tat_mins}min'
        elif avg_tat_mins < 1440:
            avg_tat_str = f'{avg_tat_mins // 60}h {avg_tat_mins % 60}min'
        else:
            avg_tat_str = f'{avg_tat_mins // 1440}d {(avg_tat_mins % 1440) // 60}h'
    else:
        avg_tat_mins = 0
        avg_tat_str = '\u2014'

    # ── Repeat / Quality ──────────────────────────────────────────────────────
    repeat_count_val   = base.filter(acquisition__is_repeat=True).count()
    quality_fail_count = base.filter(acquisition_status='QUALITY_FAILED').count()
    repeat_rate = round(repeat_count_val / total_orders * 100, 1) if total_orders else 0

    # ── Laterality breakdown ─────────────────────────────────────────────────
    lat_raw = base.values('eye').annotate(count=Count('id')).order_by('-count')
    laterality_table = [{'label': r['eye'] or 'Not specified', 'count': r['count']} for r in lat_raw]

    # ── By category ───────────────────────────────────────────────────────────
    cat_raw = (
        base.values('investigation_type__category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    # Exclude generic 'IMAGING' — redundant since page is imaging-only
    category_data = [
        {'label': (r['investigation_type__category'] or '').replace('_', ' ').title(),
         'count': r['count']}
        for r in cat_raw
        if r['investigation_type__category'] and r['investigation_type__category'] != 'IMAGING'
    ]
    category_json = json.dumps(category_data)

    # ── By urgency ────────────────────────────────────────────────────────────
    routine_count   = base.filter(urgency='ROUTINE').count()
    emergency_count = base.filter(urgency='EMERGENCY').count()
    stat_count      = base.filter(urgency='STAT').count()
    urgency_json = json.dumps({
        'labels': ['Routine', 'Urgent', 'STAT', 'Emergency'],
        'data':   [routine_count, max(0, urgent_count - emergency_count - stat_count), stat_count, emergency_count],
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
    from django.db.models.functions import TruncDate
    daily_raw = (
        base.annotate(day=TruncDate('created_at'))
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

    # ── 12-month rolling trend ────────────────────────────────────────────────
    trend_12m = []
    for i in range(11, -1, -1):
        import datetime as _dt, calendar as _cal
        y = today.year
        m = today.month - i
        while m <= 0:
            m += 12
            y -= 1
        last = _cal.monthrange(y, m)[1]
        ms = _dt.date(y, m, 1)
        me = _dt.date(y, m, last)
        cnt = InvestigationOrder.objects.filter(
            is_deleted=False,
            created_at__date__gte=ms,
            created_at__date__lte=me,
        ).count()
        trend_12m.append({'label': ms.strftime('%b %Y'), 'count': cnt})
    trend_12m_json = json.dumps(trend_12m)

    # ── Outreach vs Clinic breakdown ───────────────────────────────────────────
    clinic_count   = base.filter(location='CLINIC').count()
    outreach_count = base.filter(location='OUTREACH').count()

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

    # ── Per exam type x sex x age group breakdown ────────────────────────────
    type_rows = list(
        base.values_list(
            'investigation_type__name', 'investigation_type__category',
            'patient__gender', 'patient__date_of_birth',
        )
    )
    type_breakdown = {}
    for name, category, gender, dob in type_rows:
        cat_label = (category or '').replace('_', ' ').title()
        if name not in type_breakdown:
            type_breakdown[name] = {
                'category': cat_label,
                'male': 0, 'female': 0,
                'child_male': 0, 'child_female': 0,
                'total': 0,
            }
        is_child = False
        if dob:
            try:
                is_child = (today - dob).days // 365 <= 14
            except Exception:
                pass
        type_breakdown[name]['total'] += 1
        if gender == 'M':
            type_breakdown[name]['male'] += 1
            if is_child:
                type_breakdown[name]['child_male'] += 1
        elif gender == 'F':
            type_breakdown[name]['female'] += 1
            if is_child:
                type_breakdown[name]['child_female'] += 1
    type_breakdown_list = sorted(
        [{
            'name': k,
            **v,
            'male_adult':   v['male']   - v['child_male'],
            'female_adult': v['female'] - v['child_female'],
        } for k, v in type_breakdown.items()],
        key=lambda x: x['total'], reverse=True
    )

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
    TIER_ORDER   = ['VIP', 'EXPRESS', 'STANDARD']
    TIER_DISPLAY = {'VIP': 'VIP', 'EXPRESS': 'Express', 'STANDARD': 'Standard'}
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

    laterality_json = json.dumps([{'label': r['label'], 'count': r['count']} for r in laterality_table])

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
        # Patient Flow Funnel
        'prescribed_count': prescribed_count, 'paid_count': paid_count,
        'unpaid_count': unpaid_count, 'showed_up_count': showed_up_count,
        'paid_no_show': paid_no_show, 'show_rate': show_rate,
        # TAT + Quality
        'avg_tat_str': avg_tat_str, 'avg_tat_mins': avg_tat_mins,
        'repeat_count_val': repeat_count_val, 'quality_fail_count': quality_fail_count,
        'repeat_rate': repeat_rate,
        # Laterality
        'laterality_table': laterality_table, 'laterality_json': laterality_json,
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
        'today': timezone.now(),
        # 12-month trend
        'trend_12m_json': trend_12m_json,
        # Outreach
        'clinic_count': clinic_count,
        'outreach_count': outreach_count,
        # Per exam type x sex x age
        'type_breakdown_list': type_breakdown_list,
    }
    cache.set(_cache_key, ctx, _cache_ttl)
    if request.GET.get('pdf'):
        from apps.reports.views import render_pdf
        ctx['pdf_filename'] = 'investigation-stats.pdf'
        return render_pdf('investigations/stats_pdf.html', ctx)
    return render(request, 'investigations/stats.html', ctx)


# ── Stats CSV Export ──────────────────────────────────────────────────────────

@login_required
def stats_csv_export_view(request):
    import csv
    from django.http import HttpResponse
    import datetime as _dt, calendar as _cal

    u = request.user
    if not (u.is_investigation_tech or u.is_medical_director or u.is_super_admin
            or u.is_admin_director or u.is_ceo):
        return HttpResponseForbidden()

    today = timezone.localdate()
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
        month_start = _dt.date(year, month, 1)
    except (ValueError, TypeError):
        month_start = today.replace(day=1)
        year, month = month_start.year, month_start.month
    last_day  = _cal.monthrange(year, month)[1]
    month_end = _dt.date(year, month, last_day)

    base = InvestigationOrder.objects.filter(
        is_deleted=False,
        created_at__date__gte=month_start,
        created_at__date__lte=month_end,
    )

    type_rows = list(base.values_list(
        'investigation_type__name', 'investigation_type__category',
        'patient__gender', 'patient__date_of_birth',
    ))
    bd = {}
    for name, category, gender, dob in type_rows:
        cat = (category or '').replace('_', ' ').title()
        if name not in bd:
            bd[name] = {'cat': cat, 'M': 0, 'F': 0, 'CM': 0, 'CF': 0, 'tot': 0}
        is_child = bool(dob) and (today - dob).days // 365 <= 14
        bd[name]['tot'] += 1
        if gender == 'M':
            bd[name]['M'] += 1
            if is_child: bd[name]['CM'] += 1
        elif gender == 'F':
            bd[name]['F'] += 1
            if is_child: bd[name]['CF'] += 1

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    fname = f"investigation_stats_{year}_{month:02d}.csv"
    response['Content-Disposition'] = f'attachment; filename="{fname}"'
    w = csv.writer(response)
    w.writerow([f'Eye Investigation Statistics — {month_start.strftime("%B %Y")}'])
    w.writerow(['Generated:', today.strftime('%d/%m/%Y')])
    w.writerow([])
    w.writerow(['Investigation Type', 'Category',
                'Male Adult (15+)', 'Male Child (0-14)',
                'Female Adult (15+)', 'Female Child (0-14)',
                'Total Male', 'Total Female', 'Grand Total'])
    for name, v in sorted(bd.items(), key=lambda x: -x[1]['tot']):
        w.writerow([name, v['cat'],
                    v['M'] - v['CM'], v['CM'],
                    v['F'] - v['CF'], v['CF'],
                    v['M'], v['F'], v['tot']])
    total = base.count()
    w.writerow([])
    w.writerow(['', '', '', '', '', '', '', 'TOTAL', total])
    w.writerow([])
    w.writerow(['Summary'])
    w.writerow(['Completed', base.filter(status='COMPLETED').count()])
    w.writerow(['Completion Rate %', f"{round(base.filter(status='COMPLETED').count() / total * 100, 1) if total else 0}%"])
    w.writerow(['Urgent / Emergency / STAT', base.filter(urgency__in=['URGENT','EMERGENCY','STAT']).count()])
    w.writerow(['Clinic', base.filter(location='CLINIC').count()])
    w.writerow(['Outreach', base.filter(location='OUTREACH').count()])
    return response


# ── Machine Revenue Report ────────────────────────────────────────────────────

@login_required
def machine_revenue_view(request):
    from django.db.models import Count, Sum, F, ExpressionWrapper, DecimalField as _Dec
    from django.utils import timezone as _tz
    import datetime as _dt, calendar as _cal

    u = request.user
    if not _is_invest_viewer(u):
        return HttpResponseForbidden()

    today = _tz.localdate()
    try:
        year = int(request.GET.get('year', today.year))
    except (ValueError, TypeError):
        year = today.year

    year_start = _dt.date(year, 1, 1)
    year_end   = _dt.date(year, 12, 31)

    rows = list(
        InvestigationOrder.objects.filter(
            is_deleted=False,
            status='COMPLETED',
            created_at__date__gte=year_start,
            created_at__date__lte=year_end,
        )
        .values(
            'investigation_type__name',
            'investigation_type__category',
            'investigation_type__unit_price',
            'location',
        )
        .annotate(count=Count('id'))
        .order_by('investigation_type__category', 'investigation_type__name')
    )

    from decimal import Decimal
    categories = {}
    grand_count = 0
    grand_revenue = Decimal('0')
    for r in rows:
        cat   = (r['investigation_type__category'] or '').replace('_', ' ').title()
        price = r['investigation_type__unit_price'] or Decimal('0')
        count = r['count']
        rev   = price * count
        grand_count   += count
        grand_revenue += rev
        if cat not in categories:
            categories[cat] = {'tests': [], 'subtotal_count': 0, 'subtotal_rev': Decimal('0')}
        existing = next((t for t in categories[cat]['tests'] if t['name'] == r['investigation_type__name']), None)
        if existing:
            existing['count'] += count
            existing['revenue'] += rev
            if r['location'] == 'OUTREACH':
                existing['outreach'] += count
            else:
                existing['clinic'] += count
        else:
            categories[cat]['tests'].append({
                'name':     r['investigation_type__name'],
                'price':    price,
                'count':    count,
                'revenue':  rev,
                'clinic':   count if r['location'] == 'CLINIC' else 0,
                'outreach': count if r['location'] == 'OUTREACH' else 0,
            })
        categories[cat]['subtotal_count'] += count
        categories[cat]['subtotal_rev']   += rev

    modality_rows = list(
        ImagingStudy.objects.filter(
            is_deleted=False,
            created_at__date__gte=year_start,
            created_at__date__lte=year_end,
        )
        .values('modality')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    modality_map = dict(ImagingModality.choices)
    modality_table = [
        {'modality': r['modality'], 'label': modality_map.get(r['modality'], r['modality']), 'count': r['count']}
        for r in modality_rows
    ]

    import json
    monthly_trend = []
    for i in range(11, -1, -1):
        y = today.year
        m = today.month - i
        while m <= 0:
            m += 12
            y -= 1
        last = _cal.monthrange(y, m)[1]
        ms = _dt.date(y, m, 1)
        me = _dt.date(y, m, last)
        cnt = InvestigationOrder.objects.filter(
            is_deleted=False, status='COMPLETED',
            created_at__date__gte=ms, created_at__date__lte=me,
        ).count()
        rev_q = InvestigationOrder.objects.filter(
            is_deleted=False, status='COMPLETED',
            created_at__date__gte=ms, created_at__date__lte=me,
        ).aggregate(
            rev=Sum(
                ExpressionWrapper(F('investigation_type__unit_price'), output_field=_Dec(max_digits=14, decimal_places=2))
            )
        )
        rev = float(rev_q['rev'] or 0)
        monthly_trend.append({'label': ms.strftime('%b %Y'), 'count': cnt, 'revenue': rev})
    trend_json = json.dumps(monthly_trend)

    prev_years = [year - i for i in range(1, 4)]

    return render(request, 'investigations/machine_revenue.html', {
        'year': year,
        'year_start': year_start,
        'year_end': year_end,
        'categories': categories,
        'grand_count': grand_count,
        'grand_revenue': grand_revenue,
        'modality_table': modality_table,
        'trend_json': trend_json,
        'prev_years': prev_years,
        'today': today,
    })


# ── Machine Revenue CSV Export ────────────────────────────────────────────────

@login_required
def machine_revenue_csv_view(request):
    import csv
    from django.http import HttpResponse
    from django.db.models import Count
    import datetime as _dt
    from decimal import Decimal

    u = request.user
    if not _is_invest_viewer(u):
        return HttpResponseForbidden()

    today = timezone.localdate()
    try:
        year = int(request.GET.get('year', today.year))
    except (ValueError, TypeError):
        year = today.year

    year_start = _dt.date(year, 1, 1)
    year_end   = _dt.date(year, 12, 31)

    rows = list(
        InvestigationOrder.objects.filter(
            is_deleted=False, status='COMPLETED',
            created_at__date__gte=year_start, created_at__date__lte=year_end,
        )
        .values('investigation_type__name', 'investigation_type__category',
                'investigation_type__unit_price', 'location')
        .annotate(count=Count('id'))
        .order_by('investigation_type__category', 'investigation_type__name')
    )

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="machine_revenue_{year}.csv"'
    w = csv.writer(response)
    w.writerow([f'Machine Revenue Report — {year}'])
    w.writerow(['Generated:', today.strftime('%d/%m/%Y')])
    w.writerow([])
    w.writerow(['Category', 'Investigation Type', 'Unit Price (FCFA)', 'Location', 'Count', 'Revenue (FCFA)'])
    grand_count = 0
    grand_rev = Decimal('0')
    for r in rows:
        cat   = (r['investigation_type__category'] or '').replace('_', ' ').title()
        price = r['investigation_type__unit_price'] or Decimal('0')
        cnt   = r['count']
        rev   = price * cnt
        grand_count += cnt
        grand_rev += rev
        w.writerow([cat, r['investigation_type__name'], float(price), r['location'], cnt, float(rev)])
    w.writerow([])
    w.writerow(['', '', '', 'TOTAL', grand_count, float(grand_rev)])
    return response


# ── Staff Throughput Report ───────────────────────────────────────────────────

@login_required
def staff_throughput_view(request):
    from django.db.models import Count, Avg, F, ExpressionWrapper, DurationField
    from django.utils import timezone as _tz
    import datetime as _dt, json

    u = request.user
    if not (u.is_investigation_tech or u.is_medical_director or u.is_super_admin
            or u.is_admin_director or u.is_ceo):
        return HttpResponseForbidden()

    today = _tz.localdate()
    try:
        days = int(request.GET.get('days', 30))
        if days not in (7, 14, 30, 60, 90):
            days = 30
    except (ValueError, TypeError):
        days = 30

    since = today - _dt.timedelta(days=days - 1)

    today_results = (
        InvestigationResult.objects
        .filter(is_deleted=False, result_date__date=today)
        .values('performed_by__id', 'performed_by__first_name', 'performed_by__last_name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    today_board = [
        {
            'name': f"{r['performed_by__first_name']} {r['performed_by__last_name']}".strip() or 'Unknown',
            'count': r['count'],
        }
        for r in today_results if r['performed_by__id']
    ]

    staff_summary_raw = (
        InvestigationResult.objects
        .filter(is_deleted=False, result_date__date__gte=since, result_date__date__lte=today)
        .values('performed_by__id', 'performed_by__first_name', 'performed_by__last_name')
        .annotate(
            total=Count('id'),
            verified=Count('id', filter=Q(is_verified=True)),
            abnormal=Count('id', filter=Q(is_normal=False)),
            avg_tat=Avg(ExpressionWrapper(
                F('result_date') - F('order__created_at'),
                output_field=DurationField()
            )),
        )
        .order_by('-total')
    )
    staff_summary = []
    for r in staff_summary_raw:
        if not r['performed_by__id']:
            continue
        total    = r['total']
        verified = r['verified']
        abnormal = r['abnormal']
        avg_tat  = r['avg_tat']

        avg_per_day   = round(total / days, 1) if days else 0
        verified_pct  = round(verified / total * 100) if total else 0
        abnormal_pct  = round(abnormal / total * 100) if total else 0

        tat_mins = int(avg_tat.total_seconds() / 60) if avg_tat else 0
        if tat_mins > 0:
            tat_str = f"{tat_mins // 60}h {tat_mins % 60}m" if tat_mins >= 60 else f"{tat_mins}m"
        else:
            tat_str = '—'

        staff_summary.append({
            'name':         f"{r['performed_by__first_name']} {r['performed_by__last_name']}".strip() or 'Unknown',
            'total':        total,
            'verified':     verified,
            'verified_pct': verified_pct,
            'abnormal':     abnormal,
            'abnormal_pct': abnormal_pct,
            'avg_per_day':  avg_per_day,
            'tat_mins':     tat_mins,
            'tat_str':      tat_str,
        })

    daily_raw = (
        InvestigationResult.objects
        .filter(is_deleted=False, result_date__date__gte=since, result_date__date__lte=today)
        .extra(select={'day': 'DATE(result_date)'})
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    daily_json = json.dumps([{'day': str(r['day']), 'count': r['count']} for r in daily_raw])

    top5 = [s['name'] for s in staff_summary[:5]]
    staff_daily = {}
    if top5:
        per_staff_daily = (
            InvestigationResult.objects
            .filter(is_deleted=False, result_date__date__gte=since, result_date__date__lte=today)
            .extra(select={'day': 'DATE(result_date)'})
            .values('day', 'performed_by__first_name', 'performed_by__last_name')
            .annotate(count=Count('id'))
            .order_by('day')
        )
        for r in per_staff_daily:
            name = f"{r['performed_by__first_name']} {r['performed_by__last_name']}".strip() or 'Unknown'
            if name not in top5:
                continue
            day = str(r['day'])
            if name not in staff_daily:
                staff_daily[name] = {}
            staff_daily[name][day] = r['count']

    date_labels = [(since + _dt.timedelta(days=i)).strftime('%d %b') for i in range(days)]
    date_keys   = [(since + _dt.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days)]

    CHART_COLORS = ['#6366f1', '#0d6efd', '#198754', '#ffc107', '#dc3545']
    staff_datasets = []
    for i, name in enumerate(top5):
        data = [staff_daily.get(name, {}).get(dk, 0) for dk in date_keys]
        staff_datasets.append({'label': name, 'data': data, 'borderColor': CHART_COLORS[i % len(CHART_COLORS)],
                               'backgroundColor': 'transparent', 'borderWidth': 2, 'pointRadius': 3, 'tension': 0.3})
    staff_chart_json = json.dumps({'labels': date_labels, 'datasets': staff_datasets})

    grand_total = sum(s['total'] for s in staff_summary)
    today_total = sum(t['count'] for t in today_board)

    return render(request, 'investigations/staff_throughput.html', {
        'today': today,
        'days': days,
        'since': since,
        'today_board': today_board,
        'today_total': today_total,
        'staff_summary': staff_summary,
        'grand_total': grand_total,
        'daily_json': daily_json,
        'staff_chart_json': staff_chart_json,
        'date_labels': date_labels,
    })


# ── Staff Throughput CSV Export ───────────────────────────────────────────────

@login_required
def staff_throughput_csv_view(request):
    import csv
    from django.http import HttpResponse
    import datetime as _dt

    u = request.user
    if not (u.is_investigation_tech or u.is_medical_director or u.is_super_admin
            or u.is_admin_director or u.is_ceo):
        return HttpResponseForbidden()

    today = timezone.localdate()
    try:
        days = int(request.GET.get('days', 30))
        if days not in (7, 14, 30, 60, 90):
            days = 30
    except (ValueError, TypeError):
        days = 30

    since = today - _dt.timedelta(days=days - 1)

    results = (
        InvestigationResult.objects.filter(
            is_deleted=False,
            result_date__date__gte=since,
        )
        .select_related('performed_by')
    )

    staff_data = {}
    for r in results:
        if not r.performed_by:
            continue
        name = r.performed_by.get_full_name() or r.performed_by.username
        if name not in staff_data:
            staff_data[name] = {'total': 0, 'verified': 0, 'abnormal': 0}
        staff_data[name]['total'] += 1
        if r.is_verified:
            staff_data[name]['verified'] += 1
        if r.is_normal is False:
            staff_data[name]['abnormal'] += 1

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="inv_staff_throughput_{days}d_{today}.csv"'
    w = csv.writer(response)
    w.writerow([f'Investigation Staff Throughput — ISO 15189 §5.1 — Last {days} Days'])
    w.writerow(['Period:', f'{since.strftime("%d/%m/%Y")} to {today.strftime("%d/%m/%Y")}'])
    w.writerow(['Generated:', today.strftime('%d/%m/%Y')])
    w.writerow([])
    w.writerow(['Technician', 'Total', 'Avg/Day', 'Verified', 'Ver%', 'Abnormal', 'Abn%', 'Avg TAT'])
    grand = 0
    for name, d in sorted(staff_data.items(), key=lambda x: -x[1]['total']):
        avg = round(d['total'] / days, 1)
        ver_pct = round(d['verified'] / d['total'] * 100) if d['total'] else 0
        abn_pct = round(d['abnormal'] / d['total'] * 100) if d['total'] else 0
        w.writerow([name, d['total'], avg, d['verified'], f"{ver_pct}%",
                    d['abnormal'], f"{abn_pct}%", d.get('tat_str', '—')])
        grand += d['total']
    w.writerow([])
    w.writerow(['TOTAL', grand, '', '', '', '', '', ''])
    return response


# ── Staff Throughput PDF Export ───────────────────────────────────────────────

@login_required
def staff_throughput_pdf_view(request):
    from django.db.models import Count, Avg, F, ExpressionWrapper, DurationField
    from django.utils import timezone as _tz
    import datetime as _dt

    u = request.user
    if not (u.is_investigation_tech or u.is_medical_director or u.is_super_admin
            or u.is_admin_director or u.is_ceo):
        return HttpResponseForbidden()

    today = _tz.localdate()
    try:
        days = int(request.GET.get('days', 30))
        if days not in (7, 14, 30, 60, 90):
            days = 30
    except (ValueError, TypeError):
        days = 30

    since = today - _dt.timedelta(days=days - 1)

    today_results = (
        InvestigationResult.objects
        .filter(is_deleted=False, result_date__date=today)
        .values('performed_by__id', 'performed_by__first_name', 'performed_by__last_name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    today_board = [
        {'name': f"{r['performed_by__first_name']} {r['performed_by__last_name']}".strip() or 'Unknown',
         'count': r['count']}
        for r in today_results if r['performed_by__id']
    ]

    staff_summary_raw = (
        InvestigationResult.objects
        .filter(is_deleted=False, result_date__date__gte=since, result_date__date__lte=today)
        .values('performed_by__id', 'performed_by__first_name', 'performed_by__last_name')
        .annotate(
            total=Count('id'),
            verified=Count('id', filter=Q(is_verified=True)),
            abnormal=Count('id', filter=Q(is_normal=False)),
            avg_tat=Avg(ExpressionWrapper(
                F('result_date') - F('order__created_at'),
                output_field=DurationField()
            )),
        )
        .order_by('-total')
    )

    staff_summary = []
    for r in staff_summary_raw:
        if not r['performed_by__id']:
            continue
        total    = r['total']
        verified = r['verified']
        abnormal = r['abnormal']
        avg_tat  = r['avg_tat']

        avg_per_day   = round(total / days, 1) if days else 0
        verified_pct  = round(verified / total * 100) if total else 0
        abnormal_pct  = round(abnormal / total * 100) if total else 0
        tat_mins = int(avg_tat.total_seconds() / 60) if avg_tat else 0
        tat_str = (f"{tat_mins // 60}h {tat_mins % 60}m" if tat_mins >= 60 else f"{tat_mins}m") if tat_mins > 0 else '—'

        staff_summary.append({
            'name':         f"{r['performed_by__first_name']} {r['performed_by__last_name']}".strip() or 'Unknown',
            'total':        total,
            'verified':     verified,
            'verified_pct': verified_pct,
            'abnormal':     abnormal,
            'abnormal_pct': abnormal_pct,
            'avg_per_day':  avg_per_day,
            'tat_mins':     tat_mins,
            'tat_str':      tat_str,
        })

    grand_total  = sum(s['total'] for s in staff_summary)
    today_total  = sum(t['count'] for t in today_board)

    from apps.reports.views import render_pdf
    ctx = {
        'today': today,
        'since': since,
        'days': days,
        'today_board': today_board,
        'today_total': today_total,
        'staff_summary': staff_summary,
        'grand_total': grand_total,
        'pdf_filename': f'investigation-staff-throughput-{days}d.pdf',
    }
    return render_pdf('investigations/staff_throughput_pdf.html', ctx)


# ══════════════════════════════════════════════════════════════════════════════
# MULTI-EXAM ORDERING — Doctor orders multiple exams at once
# ══════════════════════════════════════════════════════════════════════════════

# Categories that require a specific person to be assigned
_ASSIGNEE_CATS = {'REFRACTION', 'ORTHOPTICS', 'LOW_VISION'}
# Roles that can perform optometry/refraction exams
_OPTOMETRY_ROLES = {'optometrist', 'pediatric_refractionist', 'low_vision_specialist'}
# Roles that can perform orthoptics exams
_ORTHOPTICS_ROLES = {'orthoptist', 'pediatric_refractionist'}


@login_required
def multi_exam_order_view(request, consultation_pk):
    """
    Doctor orders multiple exams at once.
    For optometry/orthoptics: also selects who should perform the exam.
    For investigation/lab: shared queue, no specific assignee.
    """
    if not request.user.can_order_investigations():
        return HttpResponseForbidden()

    consultation = get_object_or_404(Consultation, pk=consultation_pk, is_deleted=False)
    from itertools import groupby as _groupby
    from apps.accounts.models import User, UserRole

    # Determine mode: optometry or investigation
    mode = request.GET.get('cat', 'investigation')  # 'optometry' or 'investigation'
    is_optometry = mode == 'optometry'

    OPTOMETRY_CATS = {'ORTHOPTICS', 'LOW_VISION', 'REFRACTION'}
    _qs = InvestigationType.objects.filter(is_active=True)
    if is_optometry:
        _qs = _qs.filter(category__in=OPTOMETRY_CATS)
    else:
        _qs = _qs.exclude(category__in=OPTOMETRY_CATS)
    _all_types = _qs.order_by('category', 'name')
    _cat_labels = dict(InvestigationCategory.choices)
    grouped_types = []
    for cat, items in _groupby(_all_types, key=lambda t: t.category):
        label = _cat_labels.get(cat, (cat or 'Other').replace('_', ' ').title())
        grouped_types.append((cat, label, list(items)))

    # Available assignees for optometry
    assignee_list = []
    if is_optometry:
        _roles = list(_OPTOMETRY_ROLES | _ORTHOPTICS_ROLES)
        assignee_list = list(
            User.objects.filter(
                role__in=_roles,
                is_active=True,
            ).order_by('role', 'first_name')
        )

    # ── Insurance pre-auth gate ──
    _needs_preauth, _has_preauth, _preauth_msg = _check_insurance_preauth(
        consultation.patient, consultation.visit
    )
    if _needs_preauth and not _has_preauth:
        messages.warning(request, _preauth_msg)

    if request.method == 'POST':
        # Block if pre-auth required but missing
        if _needs_preauth and not _has_preauth:
            messages.error(request, 'Cannot order investigations — insurance pre-authorisation required.')
            return redirect('investigations:multi_order', consultation_pk=consultation_pk)

        selected_type_ids = request.POST.getlist('investigation_types')
        urgency = request.POST.get('urgency', 'ROUTINE')
        eye = request.POST.get('eye', 'OU')
        clinical_indication = request.POST.get('clinical_indication', '').strip()
        notes = request.POST.get('notes', '').strip()
        assigned_to_id = request.POST.get('assigned_to', '').strip()
        payment_waived = request.POST.get('payment_waived') == '1'
        waive_reason = request.POST.get('waive_reason', '').strip()

        if not selected_type_ids:
            messages.error(request, 'Please select at least one exam type.')
        elif not clinical_indication:
            messages.error(request, 'Clinical indication is required.')
        elif payment_waived and not waive_reason:
            messages.error(request, 'A reason is required when waiving payment.')
        else:
            # Resolve assignee
            assigned_user = None
            if assigned_to_id:
                try:
                    assigned_user = User.objects.get(pk=assigned_to_id, is_active=True)
                except (User.DoesNotExist, ValueError):
                    pass

            inv_types = InvestigationType.objects.filter(pk__in=selected_type_ids, is_active=True)

            # ── Pre-check: what has the patient already paid for today? ──
            # Check ALL categories (INVEST + CONSULT) because refraction route
            # fee is billed as CONSULT "Refraction / Optometry"
            _paid_descs_multi = set()
            if not payment_waived:
                try:
                    from apps.billing.models import Invoice, InvoiceItem, InvoiceStatus as _InvSt
                    _today_m = timezone.localdate()
                    _paid_invs_m = Invoice.objects.filter(
                        patient=consultation.patient, issue_date=_today_m,
                        status=_InvSt.PAID, is_deleted=False,
                    )
                    for _pi_m in _paid_invs_m:
                        _paid_descs_multi.update(
                            InvoiceItem.objects.filter(
                                invoice=_pi_m, is_deleted=False,
                                category__in=['INVEST', 'CONSULT', 'CLINICAL'],
                            ).values_list('description', flat=True)
                        )
                except Exception:
                    pass

            created_orders = []
            _any_needs_payment = False
            for inv_type in inv_types:
                order = InvestigationOrder(
                    consultation=consultation,
                    visit=consultation.visit,
                    patient=consultation.patient,
                    ordered_by=request.user,
                    created_by=request.user,
                    investigation_type=inv_type,
                    urgency=urgency,
                    eye=eye,
                    clinical_indication=clinical_indication,
                    notes=notes,
                )

                # Assign to specific person for optometry categories
                if inv_type.category in _ASSIGNEE_CATS and assigned_user:
                    order.assigned_to = assigned_user

                # Payment — check if already paid today (exact name match only)
                _exam_already_paid = (
                    not payment_waived
                    and any(inv_type.name.lower() in d.lower() for d in _paid_descs_multi)
                )
                if payment_waived:
                    order.payment_status = PaymentStatus.WAIVED
                    order.payment_authorized_by = request.user
                    order.payment_authorized_at = timezone.now()
                    order.payment_authorization_reason = waive_reason
                elif _exam_already_paid:
                    order.payment_status = PaymentStatus.PAID

                # Default device
                if inv_type.default_device:
                    order.device = inv_type.default_device

                order.save()
                created_orders.append(order)

                # Create ServiceWorkOrder for billing — only if NOT already paid
                if not _exam_already_paid:
                    try:
                        from apps.billing.models import ServiceWorkOrder, WorkOrderStatus, ServiceCategory
                        wo_status = WorkOrderStatus.PENDING if payment_waived else WorkOrderStatus.PENDING_PAYMENT
                        qty = 2 if (inv_type.billed_per_eye and eye == 'OU') else 1
                        total_price = inv_type.unit_price * qty
                        price_note = f'{inv_type.unit_price:,.0f} FCFA' + (f' x 2 eyes = {total_price:,.0f} FCFA' if qty == 2 else '')
                        _CLINICAL_CATS_M = {'REFRACTION', 'LOW_VISION', 'ORTHOPTICS'}
                        _wo_cat_m = ServiceCategory.CLINICAL_EXAM if inv_type.category in _CLINICAL_CATS_M else ServiceCategory.INVESTIGATION
                        _wo_label_m = 'Clinical Exam' if inv_type.category in _CLINICAL_CATS_M else 'Investigation'
                        ServiceWorkOrder.objects.create(
                            patient=consultation.patient,
                            consultation=consultation,
                            category=_wo_cat_m,
                            description=f'{_wo_label_m}: {inv_type.name} ({order.get_eye_display()}) — {price_note}',
                            status=wo_status,
                            notes=f'Payment waived — {waive_reason}' if payment_waived else price_note,
                            created_by=request.user,
                        )
                        if not payment_waived:
                            _any_needs_payment = True
                    except Exception:
                        pass

            # Route: waived/all-paid → direct to examiner, unpaid → cashier
            try:
                _first_cat = created_orders[0].investigation_type.category if created_orders else None
                if payment_waived or not _any_needs_payment:
                    from apps.core.patient_flow import auto_route_to_investigation
                    auto_route_to_investigation(consultation, ordered_by=request.user, category=_first_cat)
                else:
                    from apps.core.patient_flow import _auto_route_to_dept
                    _visit = getattr(consultation, 'visit', None)
                    if _visit and _visit.status not in ('AT_CASHIER', 'BILLING', 'COMPLETED', 'DISCHARGED'):
                        _auto_route_to_dept(
                            visit=_visit,
                            visit_status='AT_CASHIER',
                            qms_service_type='CASHIER',
                            dept_code='CASHIER',
                            triggered_by=request.user,
                            notes=f'Routed to cashier for exam payment ({len(created_orders)} exam(s)).',
                        )
            except Exception:
                pass

            # Notify WebSocket — doctor workstation loses patient, target gains patient
            try:
                from apps.core.ws_notify import notify_queue as _ws_nq_multi
                _ws_nq_multi('workstation')
                _ws_nq_multi('invest')
                if _any_needs_payment:
                    _ws_nq_multi('cashier')
            except Exception:
                pass

            names = ', '.join(o.investigation_type.name for o in created_orders)
            if _any_needs_payment:
                _route_msg = 'cashier for payment'
            elif payment_waived:
                _route_msg = ('optometry' if is_optometry else 'investigation') + ' queue'
            else:
                _route_msg = ('optometry' if is_optometry else 'investigation') + ' queue (already paid)'
            messages.success(
                request,
                f'{len(created_orders)} exam(s) ordered: {names}. '
                f'Patient routed to {_route_msg}.'
            )
            return redirect('consultations:detail', pk=consultation_pk)

    return render(request, 'investigations/multi_order_form.html', {
        'consultation': consultation,
        'grouped_types': grouped_types,
        'is_optometry': is_optometry,
        'assignee_list': assignee_list,
        'urgency_choices': InvestigationOrder.Urgency.choices,
        'eye_choices': Laterality.choices,
    })


# ══════════════════════════════════════════════════════════════════════════════
# STRUCTURED RESULT ENTRY — Category-specific forms for optometry/orthoptics
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def structured_result_view(request, pk):
    """
    Enter structured results for optometry/orthoptics exams.
    Falls back to generic result form if no structured form exists for this type.
    """
    if not request.user.can_record_investigation_results():
        return HttpResponseForbidden()

    order = get_object_or_404(InvestigationOrder, pk=pk, is_deleted=False)

    if hasattr(order, 'result'):
        messages.info(request, 'Result already recorded.')
        return redirect('investigations:detail', pk=pk)

    inv_code = order.investigation_type.code
    FormClass = STRUCTURED_RESULT_FORMS.get(inv_code)

    if not FormClass:
        # No structured form — redirect to generic result form
        return redirect('investigations:add_result', pk=pk)

    # If multiple pending optometry orders exist for this patient, use combined form
    _OPTOM_CATS = {'REFRACTION', 'LOW_VISION', 'ORTHOPTICS'}
    sibling_count = InvestigationOrder.objects.filter(
        patient=order.patient, is_deleted=False,
        investigation_type__category__in=_OPTOM_CATS,
    ).exclude(
        status__in=['COMPLETED', 'CANCELLED'],
    ).exclude(result__isnull=False).count()
    if sibling_count > 1:
        return redirect('investigations:combined_result', patient_id=order.patient.patient_id)

    if request.method == 'POST':
        form = FormClass(request.POST)
        if form.is_valid():
            # Save structured data as JSON in InvestigationResult.result_data
            result_data = {}
            for field_name, value in form.cleaned_data.items():
                if value is not None and value != '':
                    if hasattr(value, 'isoformat'):
                        result_data[field_name] = value.isoformat()
                    else:
                        result_data[field_name] = str(value) if not isinstance(value, (int, float, bool)) else value

            interpretation = request.POST.get('interpretation', '').strip()
            _mgmt_plan = request.POST.get('management_plan', '').strip()
            if _mgmt_plan:
                result_data['management_plan'] = _mgmt_plan
            is_normal_val = request.POST.get('is_normal', '')
            is_normal = None
            if is_normal_val == 'True':
                is_normal = True
            elif is_normal_val == 'False':
                is_normal = False

            result = InvestigationResult(
                order=order,
                performed_by=request.user,
                created_by=request.user,
                result_data=result_data,
                interpretation=interpretation,
                is_normal=is_normal,
                reported_by=request.user,
                reported_at=timezone.now(),
            )
            result.save()

            # Create acquisition record
            acq, _ = AcquisitionRecord.objects.get_or_create(
                order=order,
                defaults={'performed_by': request.user, 'created_by': request.user},
            )
            acq.completed_at = timezone.now()
            acq.save(update_fields=['completed_at', 'updated_at'])

            # Update order status
            order.status = InvestigationOrder.Status.COMPLETED
            order.acquisition_status = AcquisitionStatus.ACQUIRED
            order.report_status = ReportStatus.REPORTED
            order.save(update_fields=['status', 'acquisition_status', 'report_status', 'updated_at'])

            # File upload
            uploaded_file = request.FILES.get('result_file')
            if uploaded_file:
                InvestigationFile.objects.create(
                    result=result,
                    file=uploaded_file,
                    file_type='IMAGE' if uploaded_file.content_type.startswith('image') else 'PDF',
                    laterality=order.eye,
                    uploaded_by=request.user,
                )

            # Notify ordering doctor
            try:
                from apps.notifications.utils import notify
                from apps.notifications.models import NotificationType, NotificationPriority
                if order.ordered_by:
                    notify(
                        recipient=order.ordered_by,
                        title=f'Result ready: {order.investigation_type.name} — {order.patient.full_name}',
                        message=(
                            f'{order.investigation_type.name} ({order.get_eye_display()}) result entered by '
                            f'{request.user.get_full_name() or request.user.username}.'
                        ),
                        link=f'/investigations/{order.pk}/',
                        notification_type=NotificationType.GENERAL,
                        priority=NotificationPriority.HIGH,
                    )
            except Exception:
                pass

            # Auto-verify optometry/orthoptics results (optometrist IS the expert)
            _AUTOVERIFY_CATS = {'REFRACTION', 'LOW_VISION', 'ORTHOPTICS'}
            if order.investigation_type.category in _AUTOVERIFY_CATS:
                result.is_verified = True
                result.verified_by = request.user
                result.verified_at = timezone.now()
                result.save(update_fields=['is_verified', 'verified_by', 'verified_at', 'updated_at'])

            # Check auto-return to doctor (all exams done?)
            try:
                visit = order.visit
                if not visit and order.consultation:
                    visit = getattr(order.consultation, 'visit', None)
                if visit:
                    from apps.core.patient_flow import check_and_autoreturn_to_doctor
                    check_and_autoreturn_to_doctor(visit, triggered_by=request.user)
            except Exception:
                pass

            # Notify WebSocket — result done, doctor workstation + invest update
            try:
                from apps.core.ws_notify import notify_queue as _ws_nq_res
                _ws_nq_res('workstation')
                _ws_nq_res('invest')
                _ws_nq_res('opd')
            except Exception:
                pass

            messages.success(request, f'Result recorded for {order.investigation_type.name}.')
            return redirect('investigations:workstation')
    else:
        form = FormClass()

    return render(request, 'investigations/structured_result_form.html', {
        'form': form,
        'order': order,
        'inv_type': order.investigation_type,
        'form_title': order.investigation_type.name,
        'patient': order.patient,
    })


@login_required
def combined_structured_result_view(request, patient_id):
    """
    Elastic combined exam form — shows ALL pending structured-form orders
    for a patient in one page with accordion sections. Saves all at once.
    Falls back to single-order form if only 1 order.
    """
    if not request.user.can_record_investigation_results():
        return HttpResponseForbidden()

    from apps.patients.models import Patient
    patient = get_object_or_404(Patient, patient_id=patient_id, is_deleted=False)

    # ── Gather all pending orders that have a structured form ──
    _OPTOM_CATS = {'REFRACTION', 'LOW_VISION', 'ORTHOPTICS'}
    pending_orders = list(
        InvestigationOrder.objects.filter(
            patient=patient,
            is_deleted=False,
            investigation_type__category__in=_OPTOM_CATS,
        ).exclude(
            status__in=['COMPLETED', 'CANCELLED'],
        ).exclude(
            result__isnull=False,  # already has a result
        ).select_related('investigation_type').order_by('created_at')
    )

    # Filter to orders that have a structured form mapping
    orders_with_forms = []
    for order in pending_orders:
        code = order.investigation_type.code
        FormClass = STRUCTURED_RESULT_FORMS.get(code)
        if FormClass:
            orders_with_forms.append((order, code, FormClass))

    if not orders_with_forms:
        messages.info(request, 'No pending exams with structured forms for this patient.')
        return redirect('investigations:workstation')

    # If only 1 order, redirect to the single form
    if len(orders_with_forms) == 1:
        return redirect('investigations:structured_result', pk=orders_with_forms[0][0].pk)

    # ── POST: save all results ──
    if request.method == 'POST':
        submitted_order_ids = request.POST.getlist('order_ids')
        all_valid = True
        form_instances = []

        for order, code, FormClass in orders_with_forms:
            prefix = f'ord_{str(order.pk)[:8]}'
            form = FormClass(request.POST, prefix=prefix)
            if not form.is_valid():
                all_valid = False
            form_instances.append((order, code, form))

        if all_valid:
            interpretation = request.POST.get('interpretation', '').strip()
            is_normal_val = request.POST.get('is_normal', '')
            is_normal = None
            if is_normal_val == 'True':
                is_normal = True
            elif is_normal_val == 'False':
                is_normal = False

            uploaded_file = request.FILES.get('result_file')
            _mgmt_plan_c = request.POST.get('management_plan', '').strip()
            _AUTOVERIFY_CATS = {'REFRACTION', 'LOW_VISION', 'ORTHOPTICS'}
            saved_count = 0

            for order, code, form in form_instances:
                # Check if any fields were actually filled
                result_data = {}
                for field_name, value in form.cleaned_data.items():
                    if value is not None and value != '':
                        if hasattr(value, 'isoformat'):
                            result_data[field_name] = value.isoformat()
                        else:
                            result_data[field_name] = str(value) if not isinstance(value, (int, float, bool)) else value
                if _mgmt_plan_c:
                    result_data['management_plan'] = _mgmt_plan_c

                result = InvestigationResult(
                    order=order,
                    performed_by=request.user,
                    created_by=request.user,
                    result_data=result_data,
                    interpretation=interpretation,
                    is_normal=is_normal,
                    reported_by=request.user,
                    reported_at=timezone.now(),
                )
                result.save()

                # Acquisition record
                acq, _ = AcquisitionRecord.objects.get_or_create(
                    order=order,
                    defaults={'performed_by': request.user, 'created_by': request.user},
                )
                acq.completed_at = timezone.now()
                acq.save(update_fields=['completed_at', 'updated_at'])

                # Update order status
                order.status = InvestigationOrder.Status.COMPLETED
                order.acquisition_status = AcquisitionStatus.ACQUIRED
                order.report_status = ReportStatus.REPORTED
                order.save(update_fields=['status', 'acquisition_status', 'report_status', 'updated_at'])

                # File upload (attach to first order only)
                if uploaded_file and saved_count == 0:
                    InvestigationFile.objects.create(
                        result=result,
                        file=uploaded_file,
                        file_type='IMAGE' if uploaded_file.content_type.startswith('image') else 'PDF',
                        laterality=order.eye,
                        uploaded_by=request.user,
                    )

                # Auto-verify
                if order.investigation_type.category in _AUTOVERIFY_CATS:
                    result.is_verified = True
                    result.verified_by = request.user
                    result.verified_at = timezone.now()
                    result.save(update_fields=['is_verified', 'verified_by', 'verified_at', 'updated_at'])

                # Notify ordering doctor
                try:
                    from apps.notifications.utils import notify
                    from apps.notifications.models import NotificationType, NotificationPriority
                    if order.ordered_by:
                        notify(
                            recipient=order.ordered_by,
                            title=f'Result ready: {order.investigation_type.name} — {patient.full_name}',
                            message=f'{order.investigation_type.name} result entered by {request.user.get_full_name() or request.user.username}.',
                            link=f'/investigations/{order.pk}/',
                            notification_type=NotificationType.GENERAL,
                            priority=NotificationPriority.HIGH,
                        )
                except Exception:
                    pass

                saved_count += 1

            # Auto-return to doctor (check once after all orders saved)
            try:
                visit = orders_with_forms[0][0].visit
                if not visit:
                    c = orders_with_forms[0][0].consultation
                    if c:
                        visit = getattr(c, 'visit', None)
                if visit:
                    from apps.core.patient_flow import check_and_autoreturn_to_doctor
                    check_and_autoreturn_to_doctor(visit, triggered_by=request.user)
            except Exception:
                pass

            # Notify WebSocket — results done, doctor workstation + invest update
            try:
                from apps.core.ws_notify import notify_queue as _ws_nq_cres
                _ws_nq_cres('workstation')
                _ws_nq_cres('invest')
                _ws_nq_cres('opd')
            except Exception:
                pass

            messages.success(request, f'{saved_count} exam result(s) recorded for {patient.full_name}.')
            return redirect('investigations:workstation')

    # ── GET: build form instances with prefixes ──
    order_forms = []
    clinical_indication = None
    for order, code, FormClass in orders_with_forms:
        prefix = f'ord_{str(order.pk)[:8]}'
        form = FormClass(prefix=prefix) if request.method == 'GET' else FormClass(request.POST, prefix=prefix)
        if order.clinical_indication and not clinical_indication:
            clinical_indication = order.clinical_indication
        order_forms.append({
            'order_pk': str(order.pk),
            'name': order.investigation_type.name,
            'code': code,
            'category': order.investigation_type.get_category_display(),
            'eye': order.get_eye_display(),
            'prefix': prefix,
            'form': form,
        })

    _OPTO_CATS = {'REFRACTION', 'LOW_VISION', 'ORTHOPTICS'}
    _is_optometry = any(
        o.investigation_type.category in _OPTO_CATS for o in pending_orders
    )
    return render(request, 'investigations/combined_result_form.html', {
        'patient': patient,
        'order_forms': order_forms,
        'clinical_indication': clinical_indication,
        'is_optometry': _is_optometry,
    })
