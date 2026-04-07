from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Avg, Count, Q
from django.utils import timezone
from django.http import JsonResponse
from .models import OPDVisit, OPDVisitStatus


@login_required
def opd_dashboard(request):
    today = timezone.localdate()

    # Primary triage queue: patients.Visit (main hospital visit model)
    from apps.patients.models import Visit
    from apps.departments.models import Department
    from apps.dashboard.views import _compute_ai_triage

    visits_qs = Visit.objects.filter(
        visit_date__date=today, is_deleted=False
    ).select_related('patient', 'department', 'attending_doctor', 'triage_nurse')

    from apps.patients.models import VisitStatus
    total_today = visits_qs.count()
    # Waiting = registered at gate but not yet with doctor
    waiting = visits_qs.filter(status__in=[
        VisitStatus.REGISTERED, VisitStatus.AT_RECEPTIONIST,
        VisitStatus.AT_CASHIER,
    ]).count()
    # In triage = at parameters stage (includes legacy TRIAGE status)
    in_triage = visits_qs.filter(status__in=[
        VisitStatus.PARAMETERS, VisitStatus.TRIAGE,
    ]).count()
    in_consultation = visits_qs.filter(status=VisitStatus.IN_CONSULTATION).count()
    discharged = visits_qs.filter(status__in=[
        VisitStatus.DISCHARGED, VisitStatus.COMPLETED,
    ]).count()

    # Triage queue: active patients only — ordered by arrival time
    triage_queue = list(
        visits_qs.exclude(status__in=[
            VisitStatus.DISCHARGED, VisitStatus.COMPLETED,
        ]).order_by('visit_date')
    )
    for v in triage_queue:
        v.ai_priority, v.ai_priority_reason = _compute_ai_triage(v)
    _order = {'EMERGENCY': 0, 'URGENT': 1, 'ROUTINE': 2}
    triage_queue.sort(key=lambda v: (_order.get(v.ai_priority, 3), str(v.visit_date)))

    departments = Department.objects.filter(is_active=True).order_by('name')

    # OPDVisit stats for backward compat
    opd_visits_today = OPDVisit.objects.filter(visit_date=today)
    by_status = opd_visits_today.values('status').annotate(count=Count('id'))
    status_counts = {s['status']: s['count'] for s in by_status}

    context = {
        'today': today,
        'total_today': total_today,
        'waiting': waiting,
        'in_triage': in_triage,
        'in_consultation': in_consultation,
        'discharged': discharged,
        'triage_queue': triage_queue,
        'departments': departments,
        # OPD visit stats
        'opd_total': opd_visits_today.count(),
        'opd_registered': status_counts.get(OPDVisitStatus.REGISTERED, 0),
        'opd_with_doctor': status_counts.get(OPDVisitStatus.WITH_DOCTOR, 0),
        'opd_completed': status_counts.get(OPDVisitStatus.COMPLETED, 0),
    }
    return render(request, 'opd/dashboard.html', context)


@login_required
def visit_list(request):
    date_str = request.GET.get('date', '')
    dept = request.GET.get('department', '')
    visits = OPDVisit.objects.filter(is_deleted=False).select_related(
        'patient', 'department', 'attending_doctor'
    )
    if date_str:
        from datetime import date
        try:
            from datetime import datetime
            d = datetime.strptime(date_str, '%Y-%m-%d').date()
            visits = visits.filter(visit_date=d)
        except ValueError:
            pass
    else:
        visits = visits.filter(visit_date=timezone.localdate())
    if dept:
        visits = visits.filter(department__id=dept)

    from apps.departments.models import Department
    return render(request, 'opd/visit_list.html', {
        'visits': visits.order_by('registration_time'),
        'departments': Department.objects.filter(is_active=True, is_deleted=False),
        'selected_date': date_str,
    })


@login_required
def visit_detail(request, visit_id):
    visit = get_object_or_404(OPDVisit, id=visit_id, is_deleted=False)
    return render(request, 'opd/visit_detail.html', {'visit': visit})


@login_required
def update_visit_status(request, visit_id):
    visit = get_object_or_404(OPDVisit, id=visit_id, is_deleted=False)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status:
            visit.update_status(new_status)
            if request.headers.get('HX-Request'):
                return JsonResponse({'success': True, 'status': new_status})
            messages.success(request, 'Status updated.')
        return redirect('opd:visit_detail', visit_id=visit.id)
    return render(request, 'opd/update_status.html', {
        'visit': visit, 'statuses': OPDVisitStatus.choices
    })


@login_required
def register_visit(request):
    """Register a new OPD visit for a patient"""
    if request.method == 'POST':
        from apps.patients.models import Patient, Visit
        from apps.departments.models import Department
        patient = get_object_or_404(Patient, id=request.POST['patient_id'])
        department = None
        dept_id = request.POST.get('department_id')
        if dept_id:
            department = Department.objects.filter(id=dept_id).first()

        chief_complaint = request.POST.get('chief_complaint', '')

        # Create the main Visit object so the patient appears in the triage queue
        main_visit = Visit.objects.create(
            patient=patient,
            department=department,
            chief_complaint=chief_complaint,
            created_by=request.user,
        )

        visit = OPDVisit.objects.create(
            patient=patient,
            visit=main_visit,
            department=department,
            chief_complaint=chief_complaint,
            is_return_visit=request.POST.get('is_return', False),
            created_by=request.user,
        )
        messages.success(request, f'OPD visit {visit.visit_number} registered. Patient added to triage queue.')
        return redirect('patients:triage', visit_number=main_visit.visit_number)

    from apps.patients.models import Patient
    from apps.departments.models import Department
    return render(request, 'opd/register_visit.html', {
        'departments': Department.objects.filter(is_active=True, is_deleted=False),
    })
