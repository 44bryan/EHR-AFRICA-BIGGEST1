"""
Blood Bank views.

Access:
  - Lab technician / blood bank tech: full CRUD
  - Medical director, surgeon, anaesthetist: read + request cross-match
  - Finance/Admin: read-only stats
"""
import logging
from datetime import date
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import UserRole
from .models import (
    BloodDonor, BloodUnit, BloodUnitStatus, BloodProduct, BloodGroup,
    CrossMatch, CrossMatchResult, BloodIssue, BloodIssueStatus, DonorCategory,
)

logger = logging.getLogger('apps.blood_bank')


def _is_blood_bank_tech(user):
    return user.role in [
        UserRole.LAB_TECHNICIAN, UserRole.INVESTIGATION_TECHNICIAN,
        UserRole.SUPER_ADMIN,
    ]


def _can_request(user):
    """Can request cross-match and view blood bank data."""
    return user.role in [
        UserRole.SUPER_ADMIN, UserRole.LAB_TECHNICIAN, UserRole.INVESTIGATION_TECHNICIAN,
        UserRole.MEDICAL_DIRECTOR, UserRole.DOCTOR, UserRole.OPHTHALMOLOGIST,
        UserRole.NURSE, UserRole.WARD_NURSE, UserRole.THEATRE_NURSE,
        UserRole.CEO, UserRole.ADMIN_DIRECTOR,
    ] or getattr(user, 'role', '') == 'anaesthetist'


def _can_view(user):
    return _can_request(user) or user.role in [
        UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT, UserRole.ACCOUNTANT,
        UserRole.RECEPTIONIST,
    ]


@login_required
def dashboard(request):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    from datetime import timedelta
    today = timezone.localdate()
    inventory = BloodUnit.objects.filter(is_deleted=False, status=BloodUnitStatus.AVAILABLE)
    expiring_soon = inventory.filter(expiry_date__lte=today + timedelta(days=7))

    # Group available by blood group
    by_group = {}
    for bg in BloodGroup.values:
        by_group[bg] = inventory.filter(blood_group=bg).count()

    stats = {
        'total_available': inventory.count(),
        'reserved': BloodUnit.objects.filter(is_deleted=False, status=BloodUnitStatus.RESERVED).count(),
        'expiring_soon': inventory.filter(expiry_date__lte=today).count(),  # already expired
        'pending_xm': CrossMatch.objects.filter(is_deleted=False, result=CrossMatchResult.PENDING).count(),
        'issues_today': BloodIssue.objects.filter(is_deleted=False, issued_at__date=today).count(),
    }

    recent_issues = BloodIssue.objects.filter(
        is_deleted=False
    ).select_related('patient', 'blood_unit').order_by('-issued_at')[:8]

    pending_xm = CrossMatch.objects.filter(
        is_deleted=False, result=CrossMatchResult.PENDING
    ).select_related('patient', 'blood_unit').order_by('-requested_at')[:8]

    return render(request, 'blood_bank/dashboard.html', {
        'stats': stats,
        'by_group': by_group,
        'recent_issues': recent_issues,
        'pending_xm': pending_xm,
        'blood_groups': BloodGroup.choices,
    })


# ── Donor Register ────────────────────────────────────────────────────────────

@login_required
def donor_list(request):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    q = request.GET.get('q', '').strip()
    qs = BloodDonor.objects.filter(is_deleted=False)
    if q:
        qs = qs.filter(Q(donor_id__icontains=q) | Q(full_name__icontains=q))
    return render(request, 'blood_bank/donor_list.html', {'donors': qs[:100], 'q': q})


@login_required
def donor_create(request):
    if not _is_blood_bank_tech(request.user):
        messages.error(request, 'Access denied.')
        return redirect('blood_bank:donor_list')

    if request.method == 'POST':
        p = request.POST
        # Auto donor ID: DON-YYYYMMDD-NNN
        day_str = date.today().strftime('%Y%m%d')
        count = BloodDonor.objects.count() + 1
        donor = BloodDonor.objects.create(
            donor_id=f'DON-{day_str}-{count:03d}',
            full_name=p.get('full_name', '').strip(),
            blood_group=p.get('blood_group'),
            date_of_birth=p.get('date_of_birth') or None,
            gender=p.get('gender', ''),
            phone=p.get('phone', '').strip(),
            address=p.get('address', '').strip(),
            category=p.get('category', DonorCategory.VOLUNTARY),
            notes=p.get('notes', '').strip(),
        )
        messages.success(request, f'Donor {donor.donor_id} registered.')
        return redirect('blood_bank:donor_list')

    return render(request, 'blood_bank/donor_form.html', {
        'blood_groups': BloodGroup.choices,
        'categories': DonorCategory.choices,
    })


# ── Blood Unit Inventory ──────────────────────────────────────────────────────

@login_required
def unit_list(request):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    bg_filter = request.GET.get('bg', '')
    status_filter = request.GET.get('status', '')
    qs = BloodUnit.objects.filter(is_deleted=False).select_related('donor')

    if bg_filter:
        qs = qs.filter(blood_group=bg_filter)
    if status_filter:
        qs = qs.filter(status=status_filter)

    return render(request, 'blood_bank/unit_list.html', {
        'units': qs[:150],
        'blood_groups': BloodGroup.choices,
        'statuses': BloodUnitStatus.choices,
        'bg_filter': bg_filter,
        'status_filter': status_filter,
    })


@login_required
def unit_create(request):
    if not _is_blood_bank_tech(request.user):
        messages.error(request, 'Access denied.')
        return redirect('blood_bank:unit_list')

    if request.method == 'POST':
        p = request.POST
        day_str = date.today().strftime('%Y%m%d')
        count = BloodUnit.objects.count() + 1
        unit = BloodUnit.objects.create(
            unit_number=f'BU-{day_str}-{count:04d}',
            product=p.get('product', BloodProduct.WHOLE),
            blood_group=p.get('blood_group'),
            volume_ml=int(p.get('volume_ml', 450)),
            donor_id=p.get('donor') or None,
            collection_date=p.get('collection_date') or date.today(),
            expiry_date=p.get('expiry_date'),
            storage_location=p.get('storage_location', '').strip(),
            hiv_tested=bool(p.get('hiv_tested')),
            hbsag_tested=bool(p.get('hbsag_tested')),
            hcv_tested=bool(p.get('hcv_tested')),
            syphilis_tested=bool(p.get('syphilis_tested')),
            malaria_tested=bool(p.get('malaria_tested')),
            all_negative=bool(p.get('all_negative')),
            notes=p.get('notes', '').strip(),
            created_by=request.user,
        )
        # Update donor last_donation
        if unit.donor:
            donor = unit.donor
            donor.last_donation = unit.collection_date
            donor.total_donations += 1
            donor.save(update_fields=['last_donation', 'total_donations'])
        messages.success(request, f'Blood unit {unit.unit_number} added to inventory.')
        return redirect('blood_bank:unit_list')

    donors = BloodDonor.objects.filter(is_deleted=False).order_by('full_name')
    return render(request, 'blood_bank/unit_form.html', {
        'blood_groups': BloodGroup.choices,
        'products': BloodProduct.choices,
        'donors': donors,
        'today': date.today(),
    })


# ── Cross-Match ───────────────────────────────────────────────────────────────

@login_required
def crossmatch_list(request):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    qs = CrossMatch.objects.filter(is_deleted=False).select_related(
        'patient', 'blood_unit', 'requested_by'
    ).order_by('-requested_at')[:100]
    return render(request, 'blood_bank/crossmatch_list.html', {
        'crossmatches': qs,
        'result_choices': CrossMatchResult.choices,
    })


@login_required
def crossmatch_create(request):
    if not _can_request(request.user):
        messages.error(request, 'Access denied.')
        return redirect('blood_bank:crossmatch_list')

    if request.method == 'POST':
        p = request.POST
        from apps.patients.models import Patient
        patient = get_object_or_404(Patient, pk=p.get('patient'), is_deleted=False)
        unit = get_object_or_404(BloodUnit, pk=p.get('blood_unit'),
                                  is_deleted=False, status=BloodUnitStatus.AVAILABLE)
        xm = CrossMatch.objects.create(
            patient=patient,
            blood_unit=unit,
            visit_id=p.get('visit') or None,
            requested_by=request.user,
            notes=p.get('notes', '').strip(),
            created_by=request.user,
        )
        messages.success(request, f'Cross-match requested for {patient.full_name} × {unit.unit_number}.')
        return redirect('blood_bank:crossmatch_list')

    available_units = BloodUnit.objects.filter(
        is_deleted=False, status=BloodUnitStatus.AVAILABLE, all_negative=True
    ).order_by('expiry_date')
    from apps.patients.models import Patient
    patients = Patient.objects.filter(is_deleted=False).order_by('last_name')[:200]
    return render(request, 'blood_bank/crossmatch_form.html', {
        'available_units': available_units,
        'patients': patients,
        'blood_groups': BloodGroup.choices,
    })


@login_required
@require_POST
def crossmatch_result(request, xm_id):
    """Lab tech enters cross-match result."""
    if not _is_blood_bank_tech(request.user):
        messages.error(request, 'Access denied.')
        return redirect('blood_bank:crossmatch_list')

    xm = get_object_or_404(CrossMatch, pk=xm_id, is_deleted=False)
    xm.result = request.POST.get('result', CrossMatchResult.PENDING)
    xm.performed_by = request.user
    xm.completed_at = timezone.now()
    xm.notes = request.POST.get('notes', '').strip()
    xm.updated_by = request.user
    xm.save()
    messages.success(request, f'Cross-match result recorded: {xm.get_result_display()}')
    return redirect('blood_bank:crossmatch_list')


# ── Issue / Transfusion ───────────────────────────────────────────────────────

@login_required
def issue_list(request):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    qs = BloodIssue.objects.filter(is_deleted=False).select_related(
        'patient', 'blood_unit', 'issued_by'
    ).order_by('-issued_at')[:100]
    return render(request, 'blood_bank/issue_list.html', {
        'issues': qs,
        'status_choices': BloodIssueStatus.choices,
    })


@login_required
def issue_create(request):
    if not _is_blood_bank_tech(request.user):
        messages.error(request, 'Access denied.')
        return redirect('blood_bank:issue_list')

    if request.method == 'POST':
        p = request.POST
        from apps.patients.models import Patient
        patient = get_object_or_404(Patient, pk=p.get('patient'), is_deleted=False)
        unit = get_object_or_404(BloodUnit, pk=p.get('blood_unit'), is_deleted=False)

        day_str = date.today().strftime('%Y%m%d')
        count = BloodIssue.objects.count() + 1
        issue = BloodIssue.objects.create(
            issue_number=f'ISS-{day_str}-{count:04d}',
            blood_unit=unit,
            patient=patient,
            visit_id=p.get('visit') or None,
            cross_match_id=p.get('cross_match') or None,
            issued_by=request.user,
            received_by=p.get('received_by', '').strip(),
            notes=p.get('notes', '').strip(),
            created_by=request.user,
        )
        messages.success(request, f'Unit {unit.unit_number} issued to {patient.full_name}.')
        return redirect('blood_bank:issue_list')

    # Pre-load reserved (cross-matched compatible) units
    units = BloodUnit.objects.filter(
        is_deleted=False, status__in=[BloodUnitStatus.AVAILABLE, BloodUnitStatus.RESERVED],
        all_negative=True,
    ).order_by('expiry_date')
    compatible_xm = CrossMatch.objects.filter(
        is_deleted=False, result=CrossMatchResult.COMPATIBLE
    ).select_related('patient', 'blood_unit')

    from apps.patients.models import Patient
    patients = Patient.objects.filter(is_deleted=False).order_by('last_name')[:200]
    return render(request, 'blood_bank/issue_form.html', {
        'units': units,
        'patients': patients,
        'compatible_xm': compatible_xm,
    })


@login_required
@require_POST
def issue_update_status(request, issue_id):
    """Update transfusion outcome: Transfused / Returned / Reaction."""
    if not _is_blood_bank_tech(request.user):
        messages.error(request, 'Access denied.')
        return redirect('blood_bank:issue_list')

    issue = get_object_or_404(BloodIssue, pk=issue_id, is_deleted=False)
    p = request.POST
    issue.status = p.get('status', issue.status)
    if issue.status == BloodIssueStatus.TRANSFUSED:
        issue.transfused_at = timezone.now()
        issue.volume_transfused_ml = p.get('volume_transfused_ml') or None
    issue.reaction_description = p.get('reaction_description', '').strip()
    issue.notes = p.get('notes', '').strip()
    issue.updated_by = request.user
    issue.save()
    messages.success(request, 'Transfusion record updated.')
    return redirect('blood_bank:issue_list')
