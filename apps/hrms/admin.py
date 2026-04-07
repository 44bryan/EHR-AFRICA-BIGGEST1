from django.contrib import admin
from .models import StaffProfile, ShiftType, StaffSchedule, AttendanceRecord, LeaveType, LeaveRequest


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'employment_type', 'date_of_joining', 'specialization', 'is_active']
    list_filter = ['employment_type', 'is_active']
    search_fields = ['user__first_name', 'user__last_name', 'user__email']


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'days_allowed_per_year', 'is_paid']


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ['staff', 'leave_type', 'start_date', 'end_date', 'status', 'days_requested']
    list_filter = ['status', 'leave_type']
    search_fields = ['staff__first_name', 'staff__last_name']


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ['staff', 'date', 'clock_in', 'clock_out', 'status']
    list_filter = ['status', 'date']
    date_hierarchy = 'date'
