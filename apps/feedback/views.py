from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Avg, Count, Q
from django.utils import timezone
from datetime import timedelta
from .models import PatientFeedback, FeedbackType, FeedbackStatus


def _feedback_dashboard_stats(feedbacks):
    stats = feedbacks.aggregate(
        avg_overall=Avg('overall_rating'),
        avg_wait=Avg('wait_time_rating'),
        avg_staff=Avg('staff_courtesy_rating'),
        avg_doctor=Avg('doctor_rating'),
        avg_nps=Avg('nps_score'),
    )
    promoters  = feedbacks.filter(nps_score__gte=9).count()
    passives   = feedbacks.filter(nps_score__gte=7, nps_score__lte=8).count()
    detractors = feedbacks.filter(nps_score__lte=6, nps_score__isnull=False).count()
    total_nps  = promoters + passives + detractors
    nps = round(((promoters - detractors) / total_nps * 100)) if total_nps > 0 else 0
    return stats, nps, promoters, passives, detractors


@login_required
def feedback_dashboard(request):
    feedbacks = PatientFeedback.objects.filter(is_deleted=False)
    stats, nps, promoters, passives, detractors = _feedback_dashboard_stats(feedbacks)

    ratings_data = [
        ('Overall Experience', stats.get('avg_overall')),
        ('Wait Time', stats.get('avg_wait')),
        ('Staff Courtesy', stats.get('avg_staff')),
        ('Doctor', stats.get('avg_doctor')),
    ]

    # ── Departmental NPS breakdown ────────────────────────────────────────────
    dept_nps = []
    dept_qs = (
        feedbacks.filter(department__isnull=False, nps_score__isnull=False)
        .values('department__name')
        .annotate(
            total=Count('id'),
            promoters=Count('id', filter=Q(nps_score__gte=9)),
            detractors=Count('id', filter=Q(nps_score__lte=6)),
            avg_rating=Avg('overall_rating'),
        )
        .order_by('department__name')
    )
    for d in dept_qs:
        t = d['total']
        score = round(((d['promoters'] - d['detractors']) / t) * 100) if t else 0
        dept_nps.append({
            'name': d['department__name'],
            'nps': score,
            'total': t,
            'avg_rating': round(d['avg_rating'], 1) if d['avg_rating'] else None,
        })

    # ── Service recovery: open complaints >48 hrs ─────────────────────────────
    cutoff_48h = timezone.now() - timedelta(hours=48)
    open_statuses = [FeedbackStatus.NEW, FeedbackStatus.ACKNOWLEDGED, FeedbackStatus.INVESTIGATING]
    overdue_complaints = feedbacks.filter(
        feedback_type=FeedbackType.COMPLAINT,
        status__in=open_statuses,
        created_at__lte=cutoff_48h,
    ).select_related('patient', 'department', 'escalated_to').order_by('created_at')

    pending_complaints = feedbacks.filter(
        feedback_type=FeedbackType.COMPLAINT,
        status__in=open_statuses,
    ).select_related('patient', 'department').order_by('created_at')

    # ── Escalation matrix: already escalated ─────────────────────────────────
    escalated_qs = feedbacks.filter(
        escalated=True,
        status__in=open_statuses,
    ).select_related('patient', 'department', 'escalated_to').order_by('-escalated_at')

    # staff list for escalation dropdown
    from apps.accounts.models import User
    manager_users = User.objects.filter(
        is_active=True,
        role__in=['medical_director', 'admin_staff', 'department_head'],
    ).order_by('first_name')

    context = {
        'total_feedback': feedbacks.count(),
        'complaints': feedbacks.filter(feedback_type=FeedbackType.COMPLAINT).count(),
        'open_complaints': feedbacks.filter(
            feedback_type=FeedbackType.COMPLAINT,
            status__in=open_statuses,
        ).count(),
        'stats': stats,
        'nps_score': nps,
        'promoters': promoters,
        'passives': passives,
        'detractors': detractors,
        'ratings_data': ratings_data,
        'recent': feedbacks.order_by('-created_at')[:10],
        'dept_nps': dept_nps,
        'overdue_complaints': overdue_complaints,
        'pending_complaints': pending_complaints,
        'escalated_complaints': escalated_qs,
        'manager_users': manager_users,
    }
    return render(request, 'feedback/dashboard.html', context)


@login_required
def feedback_list(request):
    feedbacks = PatientFeedback.objects.filter(is_deleted=False).select_related(
        'patient', 'department'
    ).order_by('-created_at')
    return render(request, 'feedback/list.html', {'feedbacks': feedbacks})


@login_required
def feedback_detail(request, feedback_id):
    feedback = get_object_or_404(PatientFeedback, id=feedback_id, is_deleted=False)
    from apps.accounts.models import User
    manager_users = User.objects.filter(
        is_active=True,
        role__in=['medical_director', 'admin_staff', 'department_head'],
    ).order_by('first_name')
    return render(request, 'feedback/detail.html', {
        'feedback': feedback,
        'manager_users': manager_users,
    })


def submit_feedback(request):
    """Public-facing feedback form (no login required)"""
    if request.method == 'POST':
        from apps.patients.models import Patient
        patient_id = request.POST.get('patient_id')
        patient = None
        if patient_id:
            patient = Patient.objects.filter(id=patient_id, is_deleted=False).first()

        PatientFeedback.objects.create(
            patient=patient,
            anonymous_name=request.POST.get('name', ''),
            feedback_type=request.POST.get('feedback_type', FeedbackType.SATISFACTION),
            overall_rating=request.POST.get('overall_rating') or None,
            wait_time_rating=request.POST.get('wait_time_rating') or None,
            staff_courtesy_rating=request.POST.get('staff_courtesy_rating') or None,
            doctor_rating=request.POST.get('doctor_rating') or None,
            nps_score=request.POST.get('nps_score') or None,
            message=request.POST['message'],
        )
        return render(request, 'feedback/thank_you.html')
    return render(request, 'feedback/submit.html', {'feedback_types': FeedbackType.choices})


def _can_manage_feedback(user):
    return user.role in (
        'quality_officer', 'medical_director', 'admin_staff',
        'department_head', 'ceo', 'super_admin',
    )


@login_required
def resolve_feedback(request, feedback_id):
    if not _can_manage_feedback(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    feedback = get_object_or_404(PatientFeedback, id=feedback_id, is_deleted=False)
    if request.method == 'POST':
        feedback.status = FeedbackStatus.RESOLVED
        feedback.resolution = request.POST['resolution']
        feedback.resolved_by = request.user
        feedback.resolved_date = timezone.localdate()
        feedback.save()
        messages.success(request, 'Feedback resolved.')
        return redirect('feedback:detail', feedback_id=feedback.id)
    return render(request, 'feedback/resolve.html', {'feedback': feedback})


@login_required
def escalate_feedback(request, feedback_id):
    """Escalate a complaint to a department head / manager."""
    if not _can_manage_feedback(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    feedback = get_object_or_404(PatientFeedback, id=feedback_id, is_deleted=False)

    from apps.accounts.models import User
    escalate_to_id = request.POST.get('escalate_to')
    note = request.POST.get('note', '').strip()

    escalate_to = None
    if escalate_to_id:
        escalate_to = User.objects.filter(pk=escalate_to_id, is_active=True).first()

    feedback.escalated      = True
    feedback.escalated_to   = escalate_to
    feedback.escalated_at   = timezone.now()
    feedback.escalation_note = note
    if feedback.status == FeedbackStatus.NEW:
        feedback.status = FeedbackStatus.ACKNOWLEDGED
    feedback.save()

    # Notify the escalation target
    if escalate_to:
        try:
            from apps.notifications.models import Notification
            Notification.objects.create(
                recipient=escalate_to,
                title='Complaint Escalated to You',
                message=(
                    f'A patient complaint (#{str(feedback.id)[:8]}) has been escalated to you '
                    f'by {request.user.get_full_name()}. '
                    f'Note: {note or "No additional note."}'
                ),
                category='ALERT',
            )
        except Exception:
            pass

    messages.success(request, 'Complaint escalated successfully.')
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'feedback:dashboard'
    if next_url.startswith('/'):
        return redirect(next_url)
    return redirect(next_url)


@login_required
def acknowledge_feedback(request, feedback_id):
    """Quick-acknowledge a complaint (AJAX or form POST)."""
    if not _can_manage_feedback(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    feedback = get_object_or_404(PatientFeedback, id=feedback_id, is_deleted=False)
    if feedback.status == FeedbackStatus.NEW:
        feedback.status = FeedbackStatus.ACKNOWLEDGED
        feedback.save(update_fields=['status', 'updated_at'])
    messages.success(request, 'Complaint acknowledged.')
    return redirect(request.META.get('HTTP_REFERER', 'feedback:dashboard'))


@login_required
def service_recovery(request):
    """
    Service Recovery Dashboard — all open complaints with SLA traffic-light:
      Green  < 24 h
      Amber  24–48 h
      Red    > 48 h
    """
    now = timezone.now()
    open_statuses = [FeedbackStatus.NEW, FeedbackStatus.ACKNOWLEDGED, FeedbackStatus.INVESTIGATING]

    complaints = (
        PatientFeedback.objects.filter(
            feedback_type=FeedbackType.COMPLAINT,
            status__in=open_statuses,
            is_deleted=False,
        )
        .select_related('patient', 'department', 'escalated_to')
        .order_by('created_at')
    )

    # Annotate SLA status in Python (avoids DB-specific duration math)
    rows = []
    for fb in complaints:
        age_h = (now - fb.created_at).total_seconds() / 3600
        if age_h < 24:
            sla = 'green'
        elif age_h < 48:
            sla = 'amber'
        else:
            sla = 'red'
        rows.append({'fb': fb, 'age_h': round(age_h, 1), 'sla': sla})

    from apps.accounts.models import User
    manager_users = User.objects.filter(
        is_active=True,
        role__in=['medical_director', 'admin_staff', 'department_head'],
    ).order_by('first_name')

    context = {
        'rows': rows,
        'red_count':   sum(1 for r in rows if r['sla'] == 'red'),
        'amber_count': sum(1 for r in rows if r['sla'] == 'amber'),
        'green_count': sum(1 for r in rows if r['sla'] == 'green'),
        'manager_users': manager_users,
    }
    return render(request, 'feedback/service_recovery.html', context)
