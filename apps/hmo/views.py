"""
HMO / Insurance Claim Management views.

Access:
  - scheme/member management: admin_director, finance_director, senior_accountant, super_admin
  - pre-auth submission: cashier, receptionist, nurse roles
  - claim creation & submission: senior_accountant, finance_director
  - read-only: accountant, ceo, medical_director
"""
import json
import logging
from datetime import date
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, Count
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import UserRole
from .models import (
    InsuranceScheme, InsuredMember, PreAuthorization, PreAuthStatus,
    ClaimBatch, ClaimBatchStatus, Claim, ClaimStatus, ClaimItem,
)

logger = logging.getLogger('apps.hmo')


def _can_manage(user):
    return user.role in [
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR,
        UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT,
    ]


def _can_view(user):
    return user.role in [
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR,
        UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT,
        UserRole.ACCOUNTANT, UserRole.CEO, UserRole.MEDICAL_DIRECTOR,
        UserRole.CASHIER, UserRole.CHIEF_CASHIER,
        UserRole.RECEPTIONIST,
    ]


def _can_submit_preauth(user):
    """Receptionist / cashier / nursing roles can submit pre-auth at point of service."""
    return user.role in [
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR,
        UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT,
        UserRole.CASHIER, UserRole.CHIEF_CASHIER,
        UserRole.RECEPTIONIST, UserRole.NURSE, UserRole.WARD_NURSE,
    ]


# ── Dashboard / Overview ──────────────────────────────────────────────────────

@login_required
def hmo_dashboard(request):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    schemes = InsuranceScheme.objects.filter(is_deleted=False, is_active=True)
    today = timezone.localdate()

    stats = {
        'active_schemes': schemes.count(),
        'active_members': InsuredMember.objects.filter(is_deleted=False, is_active=True).count(),
        'pending_preauths': PreAuthorization.objects.filter(is_deleted=False, status=PreAuthStatus.PENDING).count(),
        'open_claims': Claim.objects.filter(is_deleted=False, status__in=[ClaimStatus.DRAFT, ClaimStatus.SUBMITTED]).count(),
        'batches_draft': ClaimBatch.objects.filter(is_deleted=False, status=ClaimBatchStatus.DRAFT).count(),
    }

    recent_claims = Claim.objects.filter(
        is_deleted=False
    ).select_related('member__patient', 'member__scheme').order_by('-created_at')[:10]

    pending_auths = PreAuthorization.objects.filter(
        is_deleted=False, status=PreAuthStatus.PENDING
    ).select_related('member__patient', 'member__scheme').order_by('-requested_at')[:8]

    return render(request, 'hmo/dashboard.html', {
        'stats': stats,
        'recent_claims': recent_claims,
        'pending_auths': pending_auths,
        'schemes': schemes,
    })


# ── Scheme Management ─────────────────────────────────────────────────────────

@login_required
def scheme_list(request):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    schemes = InsuranceScheme.objects.filter(is_deleted=False).order_by('name')
    return render(request, 'hmo/scheme_list.html', {'schemes': schemes})


@login_required
def scheme_create(request):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('hmo:scheme_list')

    if request.method == 'POST':
        p = request.POST
        scheme = InsuranceScheme.objects.create(
            name=p.get('name', '').strip(),
            code=p.get('code', '').strip().upper(),
            scheme_type=p.get('scheme_type', 'OTHER'),
            coverage_pct=p.get('coverage_pct', 80),
            pre_auth_required=bool(p.get('pre_auth_required')),
            max_annual_claim=p.get('max_annual_claim') or None,
            contact_phone=p.get('contact_phone', '').strip(),
            contact_email=p.get('contact_email', '').strip(),
            address=p.get('address', '').strip(),
            notes=p.get('notes', '').strip(),
        )
        messages.success(request, f'Scheme "{scheme.name}" created.')
        return redirect('hmo:scheme_list')

    from .models import SchemeType
    return render(request, 'hmo/scheme_form.html', {
        'scheme_types': SchemeType.choices,
        'action': 'Create',
    })


@login_required
def scheme_edit(request, scheme_id):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('hmo:scheme_list')

    scheme = get_object_or_404(InsuranceScheme, pk=scheme_id, is_deleted=False)

    if request.method == 'POST':
        p = request.POST
        scheme.name = p.get('name', '').strip()
        scheme.code = p.get('code', '').strip().upper()
        scheme.scheme_type = p.get('scheme_type', 'OTHER')
        scheme.coverage_pct = p.get('coverage_pct', 80)
        scheme.pre_auth_required = bool(p.get('pre_auth_required'))
        scheme.max_annual_claim = p.get('max_annual_claim') or None
        scheme.contact_phone = p.get('contact_phone', '').strip()
        scheme.contact_email = p.get('contact_email', '').strip()
        scheme.address = p.get('address', '').strip()
        scheme.notes = p.get('notes', '').strip()
        scheme.is_active = bool(p.get('is_active'))
        scheme.save()
        messages.success(request, f'Scheme "{scheme.name}" updated.')
        return redirect('hmo:scheme_list')

    from .models import SchemeType
    return render(request, 'hmo/scheme_form.html', {
        'scheme': scheme,
        'scheme_types': SchemeType.choices,
        'action': 'Edit',
    })


# ── Member Management ─────────────────────────────────────────────────────────

@login_required
def member_list(request):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    q = request.GET.get('q', '').strip()
    scheme_id = request.GET.get('scheme', '')
    qs = InsuredMember.objects.filter(is_deleted=False).select_related('patient', 'scheme')

    if q:
        qs = qs.filter(
            Q(patient__first_name__icontains=q) |
            Q(patient__last_name__icontains=q) |
            Q(member_number__icontains=q)
        )
    if scheme_id:
        qs = qs.filter(scheme_id=scheme_id)

    schemes = InsuranceScheme.objects.filter(is_deleted=False, is_active=True)
    return render(request, 'hmo/member_list.html', {
        'members': qs[:100],
        'schemes': schemes,
        'q': q,
        'selected_scheme': scheme_id,
    })


@login_required
def member_enrol(request, patient_id=None):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('hmo:member_list')

    from apps.patients.models import Patient
    patient = get_object_or_404(Patient, pk=patient_id, is_deleted=False) if patient_id else None

    if request.method == 'POST':
        p = request.POST
        pid = p.get('patient')
        try:
            pat = Patient.objects.get(pk=pid, is_deleted=False)
        except Patient.DoesNotExist:
            messages.error(request, 'Patient not found.')
            return redirect('hmo:member_enrol')

        scheme = get_object_or_404(InsuranceScheme, pk=p.get('scheme'), is_deleted=False)
        member, created = InsuredMember.objects.get_or_create(
            patient=pat,
            scheme=scheme,
            defaults={
                'member_number': p.get('member_number', '').strip(),
                'group_number': p.get('group_number', '').strip(),
                'card_expiry': p.get('card_expiry') or None,
                'copay_pct': p.get('copay_pct', 20),
                'is_primary': bool(p.get('is_primary', True)),
                'enrolled_date': p.get('enrolled_date') or date.today(),
                'notes': p.get('notes', '').strip(),
            },
        )
        if not created:
            messages.warning(request, f'{pat.full_name} is already enrolled in {scheme.name}.')
        else:
            messages.success(request, f'{pat.full_name} enrolled in {scheme.name}.')
        return redirect('hmo:member_list')

    schemes = InsuranceScheme.objects.filter(is_deleted=False, is_active=True)
    return render(request, 'hmo/member_form.html', {
        'schemes': schemes,
        'patient': patient,
        'today': date.today(),
    })


# ── Pre-Authorisation ─────────────────────────────────────────────────────────

@login_required
def preauth_list(request):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    status_filter = request.GET.get('status', '')
    qs = PreAuthorization.objects.filter(is_deleted=False).select_related(
        'member__patient', 'member__scheme', 'visit'
    )
    if status_filter:
        qs = qs.filter(status=status_filter)

    return render(request, 'hmo/preauth_list.html', {
        'preauths': qs[:100],
        'status_filter': status_filter,
        'status_choices': PreAuthStatus.choices,
    })


@login_required
def preauth_create(request, member_id=None):
    if not _can_submit_preauth(request.user):
        messages.error(request, 'Access denied.')
        return redirect('hmo:preauth_list')

    member = get_object_or_404(InsuredMember, pk=member_id, is_deleted=False) if member_id else None

    if request.method == 'POST':
        p = request.POST
        mid = p.get('member')
        m = get_object_or_404(InsuredMember, pk=mid, is_deleted=False)
        auth = PreAuthorization.objects.create(
            member=m,
            visit_id=p.get('visit') or None,
            service_description=p.get('service_description', '').strip(),
            estimated_cost=p.get('estimated_cost', 0),
            status=PreAuthStatus.PENDING,
            notes=p.get('notes', '').strip(),
            created_by=request.user,
        )
        messages.success(request, f'Pre-auth request submitted for {m.patient.full_name}.')
        return redirect('hmo:preauth_list')

    members = InsuredMember.objects.filter(is_deleted=False, is_active=True).select_related('patient', 'scheme')
    return render(request, 'hmo/preauth_form.html', {
        'member': member,
        'members': members,
    })


@login_required
def preauth_respond(request, preauth_id):
    """Scheme response: mark approved/rejected, enter auth code."""
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('hmo:preauth_list')

    auth = get_object_or_404(PreAuthorization, pk=preauth_id, is_deleted=False)

    if request.method == 'POST':
        p = request.POST
        auth.status = p.get('status', PreAuthStatus.PENDING)
        auth.auth_code = p.get('auth_code', '').strip()
        auth.valid_until = p.get('valid_until') or None
        auth.rejection_reason = p.get('rejection_reason', '').strip()
        auth.responded_at = timezone.now()
        auth.updated_by = request.user
        auth.save()
        messages.success(request, f'Pre-auth updated: {auth.get_status_display()}')
        return redirect('hmo:preauth_list')

    return render(request, 'hmo/preauth_respond.html', {
        'auth': auth,
        'status_choices': PreAuthStatus.choices,
    })


# ── Claim Batches ─────────────────────────────────────────────────────────────

@login_required
def batch_list(request):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    batches = ClaimBatch.objects.filter(is_deleted=False).select_related('scheme')
    return render(request, 'hmo/batch_list.html', {
        'batches': batches,
        'batch_statuses': ClaimBatchStatus.choices,
    })


@login_required
def batch_create(request):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('hmo:batch_list')

    if request.method == 'POST':
        p = request.POST
        scheme = get_object_or_404(InsuranceScheme, pk=p.get('scheme'), is_deleted=False)
        # Auto-generate batch number: SCH-YYYYMM-NNN (max-based to avoid duplicates)
        month_str = date.today().strftime('%Y%m')
        prefix = f'{scheme.code}-{month_str}-'
        last = ClaimBatch.objects.filter(batch_number__startswith=prefix).order_by('-batch_number').first()
        seq = int(last.batch_number.split('-')[-1]) + 1 if last else 1
        batch_number = f'{prefix}{seq:03d}'
        batch = ClaimBatch.objects.create(
            batch_number=batch_number,
            scheme=scheme,
            notes=p.get('notes', '').strip(),
            created_by=request.user,
        )
        messages.success(request, f'Batch {batch.batch_number} created.')
        return redirect('hmo:batch_detail', batch_id=batch.pk)

    schemes = InsuranceScheme.objects.filter(is_deleted=False, is_active=True)
    return render(request, 'hmo/batch_form.html', {'schemes': schemes})


@login_required
def batch_detail(request, batch_id):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    batch = get_object_or_404(ClaimBatch, pk=batch_id, is_deleted=False)
    claims = batch.claims.filter(is_deleted=False).select_related('member__patient')
    unbatched = Claim.objects.filter(
        is_deleted=False, batch__isnull=True,
        member__scheme=batch.scheme,
        status=ClaimStatus.DRAFT,
    ).select_related('member__patient')

    return render(request, 'hmo/batch_detail.html', {
        'batch': batch,
        'claims': claims,
        'unbatched': unbatched,
        'batch_statuses': ClaimBatchStatus.choices,
    })


@login_required
@require_POST
def batch_add_claim(request, batch_id):
    """Add an unbatched claim to this batch."""
    if not _can_manage(request.user):
        return JsonResponse({'error': 'Access denied'}, status=403)
    batch = get_object_or_404(ClaimBatch, pk=batch_id, is_deleted=False,
                               status=ClaimBatchStatus.DRAFT)
    claim = get_object_or_404(Claim, pk=request.POST.get('claim_id'),
                               is_deleted=False, batch__isnull=True)
    claim.batch = batch
    claim.save(update_fields=['batch'])
    batch.recalculate_totals()
    messages.success(request, f'Claim {claim.claim_number} added to batch.')
    return redirect('hmo:batch_detail', batch_id=batch_id)


@login_required
@require_POST
def batch_submit(request, batch_id):
    """Mark batch as SUBMITTED and set submission date."""
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('hmo:batch_list')

    batch = get_object_or_404(ClaimBatch, pk=batch_id, is_deleted=False)
    if batch.status != ClaimBatchStatus.DRAFT:
        messages.warning(request, 'Only DRAFT batches can be submitted.')
        return redirect('hmo:batch_detail', batch_id=batch_id)

    batch.status = ClaimBatchStatus.SUBMITTED
    batch.submission_date = date.today()
    batch.submitted_by = request.user
    batch.updated_by = request.user
    batch.save()
    # Also mark all claims in batch as SUBMITTED
    batch.claims.filter(is_deleted=False, status=ClaimStatus.DRAFT).update(
        status=ClaimStatus.SUBMITTED
    )
    batch.recalculate_totals()

    # GL: Post Insurance AR (412) for each claim in the batch
    from apps.billing.gl_service import post_insurance_invoice_split
    for claim in batch.claims.filter(is_deleted=False).select_related('invoice'):
        if claim.invoice and claim.invoice.insurance_amount and claim.invoice.insurance_amount > 0:
            post_insurance_invoice_split(claim.invoice, user=request.user)

    messages.success(request, f'Batch {batch.batch_number} submitted to {batch.scheme.name}.')
    return redirect('hmo:batch_detail', batch_id=batch_id)


@login_required
@require_POST
def batch_record_payment(request, batch_id):
    """Record scheme payment against a batch."""
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('hmo:batch_list')

    from decimal import Decimal
    batch = get_object_or_404(ClaimBatch, pk=batch_id, is_deleted=False)
    p = request.POST
    batch.total_approved = Decimal(p.get('total_approved', '0') or '0')
    batch.total_paid = Decimal(p.get('total_paid', '0') or '0')
    batch.payment_date = p.get('payment_date') or None
    batch.payment_ref = p.get('payment_ref', '').strip()
    batch.notes = p.get('notes', '').strip()
    # Determine paid vs partial
    if batch.total_paid >= batch.total_claimed:
        batch.status = ClaimBatchStatus.PAID
    elif batch.total_paid > 0:
        batch.status = ClaimBatchStatus.PARTIAL
    batch.updated_by = request.user
    batch.save()
    # GL: Post insurance payment — Dr Bank / Cr Insurance AR (412)
    from apps.billing.gl_service import post_insurance_batch_payment
    post_insurance_batch_payment(batch, user=request.user)

    messages.success(request, f'Payment of {batch.total_paid:,.0f} FCFA recorded for batch {batch.batch_number}.')
    return redirect('hmo:batch_detail', batch_id=batch_id)


# ── Individual Claims ─────────────────────────────────────────────────────────

@login_required
def claim_list(request):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')
    scheme_id = request.GET.get('scheme', '')

    qs = Claim.objects.filter(is_deleted=False).select_related(
        'member__patient', 'member__scheme', 'batch'
    )
    if q:
        qs = qs.filter(
            Q(claim_number__icontains=q) |
            Q(member__patient__first_name__icontains=q) |
            Q(member__patient__last_name__icontains=q)
        )
    if status_filter:
        qs = qs.filter(status=status_filter)
    if scheme_id:
        qs = qs.filter(member__scheme_id=scheme_id)

    schemes = InsuranceScheme.objects.filter(is_deleted=False, is_active=True)
    return render(request, 'hmo/claim_list.html', {
        'claims': qs[:100],
        'status_choices': ClaimStatus.choices,
        'status_filter': status_filter,
        'scheme_id': scheme_id,
        'schemes': schemes,
        'q': q,
    })


@login_required
def claim_create(request, member_id=None):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('hmo:claim_list')

    member = get_object_or_404(InsuredMember, pk=member_id, is_deleted=False) if member_id else None

    if request.method == 'POST':
        p = request.POST
        mid = p.get('member')
        m = get_object_or_404(InsuredMember, pk=mid, is_deleted=False)

        # Auto claim number: SCH-YYYYMMDD-NNNN (max-based to avoid duplicates)
        day_str = date.today().strftime('%Y%m%d')
        prefix = f'{m.scheme.code}-{day_str}-'
        last_claim = Claim.objects.filter(claim_number__startswith=prefix).order_by('-claim_number').first()
        seq = int(last_claim.claim_number.split('-')[-1]) + 1 if last_claim else 1
        claim_number = f'{prefix}{seq:04d}'

        claim = Claim.objects.create(
            claim_number=claim_number,
            member=m,
            visit_id=p.get('visit') or None,
            invoice_id=p.get('invoice') or None,
            pre_auth_id=p.get('pre_auth') or None,
            service_date=p.get('service_date') or date.today(),
            notes=p.get('notes', '').strip(),
            created_by=request.user,
        )

        # Create line items from posted services
        service_names = p.getlist('service_name')
        quantities = p.getlist('quantity')
        unit_prices = p.getlist('unit_price')
        for name, qty, price in zip(service_names, quantities, unit_prices):
            if name.strip():
                qty_int = int(qty) if qty else 1
                price_dec = float(price) if price else 0
                ClaimItem.objects.create(
                    claim=claim,
                    service_name=name.strip(),
                    quantity=qty_int,
                    unit_price=price_dec,
                    claimed_amount=qty_int * price_dec,
                )
        claim.recalculate_claimed()

        # Compute patient copay
        copay_pct = m.copay_pct
        claim.patient_copay = round(float(claim.claimed_amount) * float(copay_pct) / 100, 2)
        claim.save(update_fields=['patient_copay'])

        messages.success(request, f'Claim {claim.claim_number} created.')
        return redirect('hmo:claim_detail', claim_id=claim.pk)

    # Pre-populate from the member's visit list
    from apps.patients.models import Visit
    visits = []
    pre_auths = []
    if member:
        visits = Visit.objects.filter(
            patient=member.patient, is_deleted=False
        ).order_by('-visit_date')[:20]
        pre_auths = PreAuthorization.objects.filter(
            member=member, is_deleted=False,
            status=PreAuthStatus.APPROVED,
        )

    members = InsuredMember.objects.filter(
        is_deleted=False, is_active=True
    ).select_related('patient', 'scheme')

    return render(request, 'hmo/claim_form.html', {
        'member': member,
        'members': members,
        'visits': visits,
        'pre_auths': pre_auths,
        'today': date.today(),
    })


@login_required
def claim_detail(request, claim_id):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    claim = get_object_or_404(Claim, pk=claim_id, is_deleted=False)
    items = claim.items.all()
    return render(request, 'hmo/claim_detail.html', {
        'claim': claim,
        'items': items,
        'status_choices': ClaimStatus.choices,
    })


@login_required
@require_POST
def claim_reject(request, claim_id):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('hmo:claim_list')

    claim = get_object_or_404(Claim, pk=claim_id, is_deleted=False)
    claim.status = ClaimStatus.REJECTED
    claim.rejection_reason = request.POST.get('rejection_reason', '').strip()
    claim.rejection_date = date.today()
    claim.updated_by = request.user
    claim.save()
    # GL: Reverse Insurance AR → transfer to Patient AR (411)
    from apps.billing.gl_service import post_insurance_claim_rejection
    post_insurance_claim_rejection(claim, user=request.user)

    messages.warning(request, f'Claim {claim.claim_number} marked as rejected.')
    return redirect('hmo:claim_detail', claim_id=claim_id)


# ── Insurance Financial Ledger (OHADA Account 412) ───────────────────────────

@login_required
def insurance_ledger(request):
    """
    OHADA Grand Livre Auxiliaire — Account 412 (Insurance Receivables).

    Full subsidiary ledger per insurance scheme showing:
      Date | Description | Doc Ref | Debit | Credit | Balance

    OHADA Chart of Accounts:
      - Class 4 — Third-Party Accounts
      - Account 412000 — Insurance Receivables (Assurances)
      - Batch submitted = Dr 412 (insurer owes)
      - Payment received = Cr 412 (insurer paid)
      - Claim rejected = Cr 412 (AR reversed)
    """
    _allowed = (
        UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT,
        UserRole.ACCOUNTANT, UserRole.CEO, UserRole.ADMIN_DIRECTOR,
    )
    if not (request.user.is_superuser or request.user.role in _allowed):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    from decimal import Decimal
    from django.core.paginator import Paginator
    from apps.billing.models import JournalEntry, JournalLine

    scheme_id = request.GET.get('scheme', '')
    schemes = InsuranceScheme.objects.filter(is_deleted=False).order_by('name')
    scheme = None
    ledger = []
    summary = {}

    if scheme_id:
        scheme = InsuranceScheme.objects.filter(pk=scheme_id, is_deleted=False).first()

    if scheme:
        # Build ledger from JournalLines on account 412000
        from apps.billing.models import GLAccount
        ar_acct = GLAccount.objects.filter(code='412000', is_active=True).first()

        if ar_acct:
            # Get all journal lines for this account that reference this scheme
            jlines = JournalLine.objects.filter(
                account=ar_acct,
                entry__is_posted=True,
            ).select_related('entry').order_by('entry__entry_date', 'entry__created_at')

            # Also build from claims/batches directly for richer data
            pass

        # Build ledger from claim batches (more useful data)
        raw = []

        # Batches submitted = AR recognized (Debit 412)
        batches = ClaimBatch.objects.filter(
            scheme=scheme, is_deleted=False,
            status__in=[ClaimBatchStatus.SUBMITTED, ClaimBatchStatus.PROCESSING,
                        ClaimBatchStatus.PAID, ClaimBatchStatus.PARTIAL],
        ).order_by('submission_date')

        for b in batches:
            if b.total_claimed and b.total_claimed > 0:
                raw.append({
                    'date': b.submission_date or b.created_at.date(),
                    'ref_type': 'batch_submit',
                    'op': f'Claim Batch Submitted — {b.batch_number} ({b.claims.count()} claims)',
                    'piece': b.batch_number,
                    'debit': Decimal(str(b.total_claimed)),
                    'credit': Decimal('0'),
                    'by': str(b.submitted_by or 'System'),
                    'ref_id': str(b.pk),
                })

            # Payment received = AR settled (Credit 412)
            if b.total_paid and b.total_paid > 0:
                raw.append({
                    'date': b.payment_date or b.updated_at.date(),
                    'ref_type': 'batch_payment',
                    'op': f'Payment Received — {b.batch_number} — Ref: {b.payment_ref or "N/A"}',
                    'piece': b.payment_ref or b.batch_number,
                    'debit': Decimal('0'),
                    'credit': Decimal(str(b.total_paid)),
                    'by': str(b.updated_by or 'System'),
                    'ref_id': str(b.pk),
                })

        # Rejected claims = AR reversal (Credit 412)
        rejected_claims = Claim.objects.filter(
            member__scheme=scheme, is_deleted=False,
            status=ClaimStatus.REJECTED,
        ).select_related('member__patient')

        for c in rejected_claims:
            if c.claimed_amount and c.claimed_amount > 0:
                raw.append({
                    'date': c.rejection_date or c.updated_at.date(),
                    'ref_type': 'claim_reject',
                    'op': f'Claim Rejected — {c.claim_number} — {c.member.patient.full_name}',
                    'piece': c.claim_number,
                    'debit': Decimal('0'),
                    'credit': Decimal(str(c.claimed_amount)),
                    'by': str(c.updated_by or 'System'),
                    'ref_id': str(c.pk),
                })

        # Sort chronologically
        raw.sort(key=lambda x: x['date'])

        # Compute running balance
        balance = Decimal('0')
        for entry in raw:
            balance += entry['debit'] - entry['credit']
            entry['balance'] = balance

        ledger = raw

        total_debit = sum(e['debit'] for e in raw)
        total_credit = sum(e['credit'] for e in raw)

        summary = {
            'gl_account': '412000',
            'gl_label': 'Insurance Receivables',
            'gl_class': 'Class 4 — Third-Party Accounts',
            'scheme_name': scheme.name,
            'scheme_code': scheme.code,
            'scheme_type': scheme.get_scheme_type_display(),
            'coverage_pct': scheme.coverage_pct,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'balance': total_debit - total_credit,
            'batch_count': batches.count(),
            'rejected_count': rejected_claims.count(),
        }

    return render(request, 'hmo/insurance_ledger.html', {
        'scheme': scheme,
        'schemes': schemes,
        'ledger': ledger,
        'summary': summary,
        'scheme_id': scheme_id,
    })


@login_required
def insurance_aging(request):
    """Insurance AR Aging Report — Account 412."""
    _allowed = (
        UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT,
        UserRole.ACCOUNTANT, UserRole.CEO, UserRole.ADMIN_DIRECTOR,
    )
    if not (request.user.is_superuser or request.user.role in _allowed):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    from decimal import Decimal
    from datetime import timedelta
    today = date.today()

    schemes = InsuranceScheme.objects.filter(is_deleted=False, is_active=True).order_by('name')
    aging_data = []

    for scheme in schemes:
        # Get all submitted but unpaid batches
        batches = ClaimBatch.objects.filter(
            scheme=scheme, is_deleted=False,
            status__in=[ClaimBatchStatus.SUBMITTED, ClaimBatchStatus.PROCESSING, ClaimBatchStatus.PARTIAL],
        )

        current = Decimal('0')     # 0-30 days
        over_30 = Decimal('0')     # 31-60 days
        over_60 = Decimal('0')     # 61-90 days
        over_90 = Decimal('0')     # 90+ days

        for b in batches:
            outstanding = Decimal(str(b.total_claimed or 0)) - Decimal(str(b.total_paid or 0))
            if outstanding <= 0:
                continue
            sub_date = b.submission_date or b.created_at.date()
            days = (today - sub_date).days

            if days <= 30:
                current += outstanding
            elif days <= 60:
                over_30 += outstanding
            elif days <= 90:
                over_60 += outstanding
            else:
                over_90 += outstanding

        total = current + over_30 + over_60 + over_90
        if total > 0:
            aging_data.append({
                'scheme': scheme,
                'current': current,
                'over_30': over_30,
                'over_60': over_60,
                'over_90': over_90,
                'total': total,
            })

    grand_total = sum(d['total'] for d in aging_data)

    return render(request, 'hmo/insurance_aging.html', {
        'aging_data': aging_data,
        'grand_total': grand_total,
    })


# ── AJAX: patient search for member enrolment form ────────────────────────────

@login_required
def patient_search_ajax(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})
    from apps.patients.models import Patient
    patients = Patient.objects.filter(
        is_deleted=False
    ).filter(
        Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(patient_id__icontains=q)
    )[:10]
    results = [{'id': str(p.pk), 'name': p.full_name, 'pid': p.patient_id} for p in patients]
    return JsonResponse({'results': results})
