from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.utils import timezone
from .models import (
    StaffProfile, LeaveRequest, AttendanceRecord, LeaveRequestStatus, LeaveType,
    PayrollRun, PayrollEntry, PayrollStatus,
)
from apps.accounts.models import UserRole


def _can_manage_hrms(user):
    """Admin Director, Finance Director, CEO, Medical Director, ADMIN, Super Admin can manage HR."""
    return user.role in (
        UserRole.ADMIN_DIRECTOR, UserRole.FINANCE_DIRECTOR, UserRole.CEO,
        UserRole.MEDICAL_DIRECTOR, UserRole.ADMIN, UserRole.SUPER_ADMIN,
    ) or user.is_superuser


def _can_manage_payroll(user):
    """Payroll is Finance Director + Admin Director + CEO + ADMIN + Super Admin."""
    return user.role in (
        UserRole.ADMIN_DIRECTOR, UserRole.FINANCE_DIRECTOR, UserRole.CEO,
        UserRole.ADMIN, UserRole.SUPER_ADMIN,
    ) or user.is_superuser


@login_required
def hrms_dashboard(request):
    if not _can_manage_hrms(request.user):
        return HttpResponseForbidden()
    today = timezone.localdate()
    context = {
        'total_staff': StaffProfile.objects.filter(is_active=True, is_deleted=False).count(),
        'present_today': AttendanceRecord.objects.filter(
            date=today, status__in=['PRESENT', 'LATE']
        ).count(),
        'on_leave_today': AttendanceRecord.objects.filter(date=today, status='ON_LEAVE').count(),
        'pending_leaves': LeaveRequest.objects.filter(
            status=LeaveRequestStatus.PENDING, is_deleted=False
        ).count(),
        'recent_leaves': LeaveRequest.objects.filter(is_deleted=False).select_related(
            'staff', 'leave_type'
        ).order_by('-applied_on')[:10],
    }
    return render(request, 'hrms/dashboard.html', context)


@login_required
def staff_list(request):
    if not _can_manage_hrms(request.user):
        return HttpResponseForbidden()
    profiles = StaffProfile.objects.filter(
        is_active=True, is_deleted=False
    ).select_related('user', 'user__department').order_by('user__last_name')
    return render(request, 'hrms/staff_list.html', {'profiles': profiles})


@login_required
def staff_detail(request, profile_id):
    if not _can_manage_hrms(request.user):
        return HttpResponseForbidden()
    profile = get_object_or_404(StaffProfile, id=profile_id, is_deleted=False)
    leaves = profile.user.leave_requests.filter(is_deleted=False).order_by('-applied_on')[:10]
    attendance = profile.user.attendance_records.order_by('-date')[:30]
    return render(request, 'hrms/staff_detail.html', {
        'profile': profile, 'leaves': leaves, 'attendance': attendance
    })


@login_required
def leave_requests(request):
    if not _can_manage_hrms(request.user):
        return HttpResponseForbidden()
    leaves = LeaveRequest.objects.filter(is_deleted=False).select_related(
        'staff', 'leave_type', 'approved_by'
    ).order_by('-applied_on')
    return render(request, 'hrms/leave_requests.html', {'leaves': leaves})


@login_required
def approve_leave(request, leave_id):
    if not _can_manage_hrms(request.user):
        return HttpResponseForbidden()
    leave = get_object_or_404(LeaveRequest, id=leave_id, is_deleted=False)
    if request.method == 'POST':
        action = request.POST.get('action')
        leave.approval_notes = request.POST.get('notes', '')
        leave.approved_by = request.user
        if action == 'approve':
            leave.status = LeaveRequestStatus.APPROVED
            messages.success(request, 'Leave approved.')
        else:
            leave.status = LeaveRequestStatus.REJECTED
            messages.warning(request, 'Leave rejected.')
        leave.save()
        return redirect('hrms:leave_requests')
    return render(request, 'hrms/approve_leave.html', {'leave': leave})


@login_required
def attendance_register(request):
    if not _can_manage_hrms(request.user):
        return HttpResponseForbidden()
    today = timezone.localdate()
    records = AttendanceRecord.objects.filter(date=today).select_related('staff')
    return render(request, 'hrms/attendance.html', {'records': records, 'today': today})


@login_required
def apply_leave(request):
    """Staff self-service: apply for leave."""
    leave_types = LeaveType.objects.filter(is_deleted=False)
    if request.method == 'POST':
        leave_type_id = request.POST.get('leave_type')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        reason = request.POST.get('reason', '').strip()

        if not leave_type_id or not start_date or not end_date or not reason:
            messages.error(request, 'All fields are required.')
        else:
            try:
                leave_type = LeaveType.objects.get(pk=leave_type_id)
                LeaveRequest.objects.create(
                    staff=request.user,
                    leave_type=leave_type,
                    start_date=start_date,
                    end_date=end_date,
                    reason=reason,
                    created_by=request.user,
                )
                messages.success(request, 'Leave request submitted successfully.')
                return redirect('hrms:my_leaves')
            except LeaveType.DoesNotExist:
                messages.error(request, 'Invalid leave type selected.')

    return render(request, 'hrms/apply_leave.html', {'leave_types': leave_types})


@login_required
def my_leaves(request):
    """Staff self-service: view own leave requests."""
    leaves = LeaveRequest.objects.filter(
        staff=request.user, is_deleted=False
    ).select_related('leave_type', 'approved_by').order_by('-applied_on')
    return render(request, 'hrms/my_leaves.html', {'leaves': leaves})


@login_required
def clock_in_out(request):
    """Staff clock-in and clock-out."""
    today = timezone.localdate()
    now_time = timezone.localtime().time()

    record, created = AttendanceRecord.objects.get_or_create(
        staff=request.user,
        date=today,
        defaults={'clock_in': now_time, 'status': 'PRESENT'}
    )

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'clock_in' and not record.clock_in:
            record.clock_in = now_time
            record.status = 'PRESENT'
            record.save()
            messages.success(request, f'Clocked in at {now_time.strftime("%H:%M")}.')
        elif action == 'clock_out' and record.clock_in and not record.clock_out:
            record.clock_out = now_time
            record.save()
            messages.success(request, f'Clocked out at {now_time.strftime("%H:%M")}.')
        else:
            messages.info(request, 'No action taken.')
        return redirect('hrms:clock_in_out')

    return render(request, 'hrms/clock_in_out.html', {
        'record': record,
        'today': today,
        'now_time': now_time,
        'already_in': bool(record.clock_in),
        'already_out': bool(record.clock_out),
    })


# ── Payroll ───────────────────────────────────────────────────────────────────

@login_required
def payroll_list(request):
    if not _can_manage_payroll(request.user):
        return HttpResponseForbidden()
    runs = PayrollRun.objects.filter(is_deleted=False).order_by('-year', '-month')
    return render(request, 'hrms/payroll_list.html', {'runs': runs})


@login_required
def payroll_create(request):
    if not _can_manage_payroll(request.user):
        return HttpResponseForbidden()
    import calendar
    today = timezone.localdate()
    if request.method == 'POST':
        month = int(request.POST.get('month', today.month))
        year  = int(request.POST.get('year', today.year))

        if PayrollRun.objects.filter(month=month, year=year, is_deleted=False).exists():
            messages.error(request, f'Payroll for {calendar.month_name[month]} {year} already exists.')
            return redirect('hrms:payroll_list')

        run = PayrollRun.objects.create(
            month=month, year=year,
            created_by=request.user,
        )
        # Auto-populate entries from StaffProfile.basic_salary
        profiles = StaffProfile.objects.filter(is_active=True, is_deleted=False).select_related('user')
        for profile in profiles:
            PayrollEntry.objects.create(
                run=run,
                staff=profile.user,
                basic_salary=profile.basic_salary,
                created_by=request.user,
            )
        messages.success(request, f'Payroll created for {run.period_label} with {profiles.count()} staff entries.')
        return redirect('hrms:payroll_detail', run_id=run.pk)

    months = [(i, calendar.month_name[i]) for i in range(1, 13)]
    years  = list(range(today.year - 1, today.year + 2))
    return render(request, 'hrms/payroll_create.html', {
        'months': months, 'years': years,
        'current_month': today.month, 'current_year': today.year,
    })


@login_required
def payroll_detail(request, run_id):
    if not _can_manage_payroll(request.user):
        return HttpResponseForbidden()
    run = get_object_or_404(PayrollRun, pk=run_id, is_deleted=False)
    entries = run.entries.filter(is_deleted=False).select_related('staff')

    if request.method == 'POST' and run.status == PayrollStatus.DRAFT:
        action = request.POST.get('action')

        if action == 'save_entries':
            for entry in entries:
                key = str(entry.pk)
                entry.basic_salary        = request.POST.get(f'basic_{key}', entry.basic_salary) or 0
                entry.housing_allowance   = request.POST.get(f'housing_{key}', 0) or 0
                entry.transport_allowance = request.POST.get(f'transport_{key}', 0) or 0
                entry.other_allowances    = request.POST.get(f'other_allow_{key}', 0) or 0
                entry.tax_deduction       = request.POST.get(f'tax_{key}', 0) or 0
                entry.pension_deduction   = request.POST.get(f'pension_{key}', 0) or 0
                entry.other_deductions    = request.POST.get(f'other_ded_{key}', 0) or 0
                entry.days_absent         = int(request.POST.get(f'absent_{key}', 0) or 0)
                entry.notes               = request.POST.get(f'notes_{key}', '')
                entry.save()
            messages.success(request, 'Payroll entries saved.')

        elif action == 'process':
            run.status = PayrollStatus.PROCESSED
            run.processed_by = request.user
            run.save()
            messages.success(request, f'Payroll for {run.period_label} processed.')

        elif action == 'mark_paid':
            run.status = PayrollStatus.PAID
            run.save()
            messages.success(request, f'Payroll for {run.period_label} marked as paid.')

        return redirect('hrms:payroll_detail', run_id=run.pk)

    return render(request, 'hrms/payroll_detail.html', {
        'run': run, 'entries': entries,
    })


@login_required
def payslip(request, entry_id):
    entry = get_object_or_404(PayrollEntry, pk=entry_id, is_deleted=False)
    if not (_can_manage_payroll(request.user) or request.user == entry.staff):
        return HttpResponseForbidden()
    return render(request, 'hrms/payslip.html', {'entry': entry})
