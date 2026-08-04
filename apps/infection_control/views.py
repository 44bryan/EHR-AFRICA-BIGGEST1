"""
Infection Control views.

Access:
  - Quality officer, medical director, super admin: full CRUD
  - Lab tech: can enter antibiogram results
  - Ward nurse, theatre nurse: read + report HAI
"""
import logging
from datetime import date
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone

from apps.accounts.models import UserRole
from .models import HAIReport, HAIType, HAIStatus, AntibioticSensitivity, OutbreakAlert, AlertLevel

logger = logging.getLogger('apps.infection_control')


def _can_manage(user):
    return user.role in [
        UserRole.SUPER_ADMIN, UserRole.MEDICAL_DIRECTOR,
        UserRole.QUALITY_OFFICER, UserRole.ADMIN_DIRECTOR,
    ]


def _can_report(user):
    return user.role in [
        UserRole.SUPER_ADMIN, UserRole.MEDICAL_DIRECTOR, UserRole.QUALITY_OFFICER,
        UserRole.NURSE, UserRole.WARD_NURSE, UserRole.THEATRE_NURSE,
        UserRole.LAB_TECHNICIAN, UserRole.ADMIN_DIRECTOR, UserRole.CEO,
    ]


def _can_view(user):
    return _can_report(user) or user.role in [UserRole.FINANCE_DIRECTOR, UserRole.SENIOR_ACCOUNTANT]


@login_required
def dashboard(request):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    today = timezone.localdate()
    hai_by_type = HAIReport.objects.filter(
        is_deleted=False
    ).values('hai_type').annotate(count=Count('id')).order_by('-count')

    stats = {
        'total_hai': HAIReport.objects.filter(is_deleted=False).count(),
        'open_hai': HAIReport.objects.filter(is_deleted=False,
            status__in=[HAIStatus.REPORTED, HAIStatus.INVESTIGATING]).count(),
        'active_outbreaks': OutbreakAlert.objects.filter(is_deleted=False, is_active=True).count(),
        'antibiogram_records': AntibioticSensitivity.objects.filter(is_deleted=False).count(),
    }

    recent_hai = HAIReport.objects.filter(is_deleted=False).select_related(
        'patient', 'ward', 'reported_by'
    ).order_by('-onset_date')[:8]

    active_outbreaks = OutbreakAlert.objects.filter(
        is_deleted=False, is_active=True
    ).order_by('-onset_date')

    return render(request, 'infection_control/dashboard.html', {
        'stats': stats,
        'recent_hai': recent_hai,
        'active_outbreaks': active_outbreaks,
        'hai_by_type': hai_by_type,
    })


# ── HAI Reports ───────────────────────────────────────────────────────────────

@login_required
def hai_list(request):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')
    qs = HAIReport.objects.filter(is_deleted=False).select_related('patient', 'ward', 'reported_by')
    if status_filter:
        qs = qs.filter(status=status_filter)
    if type_filter:
        qs = qs.filter(hai_type=type_filter)
    return render(request, 'infection_control/hai_list.html', {
        'reports': qs[:100],
        'status_choices': HAIStatus.choices,
        'type_choices': HAIType.choices,
        'status_filter': status_filter,
        'type_filter': type_filter,
    })


@login_required
def hai_create(request):
    if not _can_report(request.user):
        messages.error(request, 'Access denied.')
        return redirect('infection_control:hai_list')

    if request.method == 'POST':
        p = request.POST
        from apps.patients.models import Patient
        patient = get_object_or_404(Patient, pk=p.get('patient'), is_deleted=False)
        day_str = date.today().strftime('%Y%m%d')
        count = HAIReport.objects.count() + 1
        report = HAIReport.objects.create(
            report_number=f'HAI-{day_str}-{count:04d}',
            patient=patient,
            visit_id=p.get('visit') or None,
            hai_type=p.get('hai_type'),
            organism=p.get('organism', '').strip(),
            onset_date=p.get('onset_date') or date.today(),
            ward_id=p.get('ward') or None,
            clinical_details=p.get('clinical_details', '').strip(),
            notes=p.get('notes', '').strip(),
            reported_by=request.user,
            created_by=request.user,
        )
        messages.success(request, f'HAI report {report.report_number} filed.')
        return redirect('infection_control:hai_list')

    from apps.ipd.models import Ward
    from apps.patients.models import Patient
    wards = Ward.objects.filter(is_deleted=False).order_by('name')
    patients = Patient.objects.filter(is_deleted=False).order_by('last_name')[:200]
    return render(request, 'infection_control/hai_form.html', {
        'hai_types': HAIType.choices,
        'wards': wards,
        'patients': patients,
        'today': date.today(),
    })


@login_required
def hai_detail(request, report_id):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    report = get_object_or_404(HAIReport, pk=report_id, is_deleted=False)
    if request.method == 'POST' and _can_manage(request.user):
        p = request.POST
        report.status = p.get('status', report.status)
        report.root_cause = p.get('root_cause', '').strip()
        report.corrective_action = p.get('corrective_action', '').strip()
        report.resolved_date = p.get('resolved_date') or None
        report.reviewed_by = request.user
        report.updated_by = request.user
        report.save()
        messages.success(request, 'Report updated.')
        return redirect('infection_control:hai_detail', report_id=report_id)
    return render(request, 'infection_control/hai_detail.html', {
        'report': report,
        'status_choices': HAIStatus.choices,
        'can_manage': _can_manage(request.user),
    })


# ── Antibiogram ───────────────────────────────────────────────────────────────

@login_required
def antibiogram(request):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    organism_q = request.GET.get('organism', '').strip()
    qs = AntibioticSensitivity.objects.filter(is_deleted=False)
    if organism_q:
        qs = qs.filter(organism__icontains=organism_q)
    return render(request, 'infection_control/antibiogram.html', {
        'records': qs[:100],
        'organism_q': organism_q,
        'antibiotic_fields': AntibioticSensitivity.ANTIBIOTIC_FIELDS,
    })


@login_required
def sensitivity_create(request):
    if not _can_report(request.user):
        messages.error(request, 'Access denied.')
        return redirect('infection_control:antibiogram')

    if request.method == 'POST':
        p = request.POST
        from apps.patients.models import Patient
        kwargs = {
            'organism': p.get('organism', '').strip(),
            'sample_type': p.get('sample_type', '').strip(),
            'collection_date': p.get('collection_date') or date.today(),
            'ward_id': p.get('ward') or None,
            'notes': p.get('notes', '').strip(),
            'recorded_by': request.user,
        }
        pid = p.get('patient')
        if pid:
            kwargs['patient_id'] = pid
        for abx in AntibioticSensitivity.ANTIBIOTIC_FIELDS:
            kwargs[abx] = p.get(abx, 'NT')
        rec = AntibioticSensitivity.objects.create(**kwargs)
        messages.success(request, f'Antibiogram record saved for {rec.organism}.')
        return redirect('infection_control:antibiogram')

    from apps.ipd.models import Ward
    from apps.patients.models import Patient
    wards = Ward.objects.filter(is_deleted=False)
    patients = Patient.objects.filter(is_deleted=False).order_by('last_name')[:200]
    return render(request, 'infection_control/sensitivity_form.html', {
        'wards': wards,
        'patients': patients,
        'antibiotic_fields': AntibioticSensitivity.ANTIBIOTIC_FIELDS,
        'sus_choices': [('S', 'S'), ('I', 'I'), ('R', 'R'), ('NT', 'NT')],
        'today': date.today(),
    })


# ── Outbreak Alerts ───────────────────────────────────────────────────────────

@login_required
def outbreak_list(request):
    if not _can_view(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    alerts = OutbreakAlert.objects.filter(is_deleted=False).order_by('-onset_date')
    return render(request, 'infection_control/outbreak_list.html', {
        'alerts': alerts,
        'alert_levels': AlertLevel.choices,
    })


@login_required
def outbreak_create(request):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('infection_control:outbreak_list')

    if request.method == 'POST':
        p = request.POST
        alert = OutbreakAlert.objects.create(
            title=p.get('title', '').strip(),
            pathogen=p.get('pathogen', '').strip(),
            alert_level=p.get('alert_level', AlertLevel.WATCH),
            affected_areas=p.get('affected_areas', '').strip(),
            onset_date=p.get('onset_date') or date.today(),
            case_count=int(p.get('case_count', 1)),
            description=p.get('description', '').strip(),
            actions_taken=p.get('actions_taken', '').strip(),
            issued_by=request.user,
            created_by=request.user,
        )
        # Also send in-app notification to all medical directors
        try:
            from apps.notifications.utils import notify_role
            from apps.notifications.models import NotificationType, NotificationPriority
            notify_role(
                role=UserRole.MEDICAL_DIRECTOR,
                title=f'[{alert.alert_level}] Outbreak Alert: {alert.title}',
                message=f'{alert.case_count} case(s). Affected: {alert.affected_areas}',
                link='/infection-control/outbreaks/',
                notification_type='WARNING',
                priority=NotificationPriority.URGENT,
            )
        except Exception as e:
            logger.warning(f'Could not notify medical directors: {e}')

        messages.success(request, f'Outbreak alert "{alert.title}" issued.')
        return redirect('infection_control:outbreak_list')

    return render(request, 'infection_control/outbreak_form.html', {
        'alert_levels': AlertLevel.choices,
        'today': date.today(),
    })
