from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import StaffProfile, LeaveRequest, AttendanceRecord, LeaveRequestStatus, LeaveType


@login_required
def hrms_dashboard(request):
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
    profiles = StaffProfile.objects.filter(
        is_active=True, is_deleted=False
    ).select_related('user', 'user__department').order_by('user__last_name')
    return render(request, 'hrms/staff_list.html', {'profiles': profiles})


@login_required
def staff_detail(request, profile_id):
    profile = get_object_or_404(StaffProfile, id=profile_id, is_deleted=False)
    leaves = profile.user.leave_requests.filter(is_deleted=False).order_by('-applied_on')[:10]
    attendance = profile.user.attendance_records.order_by('-date')[:30]
    return render(request, 'hrms/staff_detail.html', {
        'profile': profile, 'leaves': leaves, 'attendance': attendance
    })


@login_required
def leave_requests(request):
    leaves = LeaveRequest.objects.filter(is_deleted=False).select_related(
        'staff', 'leave_type', 'approved_by'
    ).order_by('-applied_on')
    return render(request, 'hrms/leave_requests.html', {'leaves': leaves})


@login_required
def approve_leave(request, leave_id):
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
