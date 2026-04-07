"""
HRMS - Human Resources Management System
Staff profiles, attendance, leave management, shifts, appraisals.
"""
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel, AuditModel


class EmploymentType(models.TextChoices):
    FULL_TIME = 'FULL', 'Full Time'
    PART_TIME = 'PART', 'Part Time'
    CONTRACT = 'CONTRACT', 'Contract'
    LOCUM = 'LOCUM', 'Locum'
    INTERN = 'INTERN', 'Intern/NYSC'


class StaffProfile(AuditModel):
    """Extended staff profile beyond User model"""
    user = models.OneToOneField(
        'accounts.User', on_delete=models.CASCADE, related_name='staff_profile'
    )
    employment_type = models.CharField(max_length=20, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME)
    date_of_joining = models.DateField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    national_id = models.CharField(max_length=50, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account_number = models.CharField(max_length=50, blank=True)
    emergency_contact_name = models.CharField(max_length=200, blank=True)
    emergency_contact_phone = models.CharField(max_length=30, blank=True)
    qualifications = models.TextField(blank=True)
    specialization = models.CharField(max_length=200, blank=True)
    medical_council_number = models.CharField(max_length=100, blank=True)
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Staff Profile: {self.user.full_name}"


class ShiftType(AuditModel):
    name = models.CharField(max_length=100)
    start_time = models.TimeField()
    end_time = models.TimeField()
    department = models.ForeignKey(
        'departments.Department', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='shifts'
    )

    def __str__(self):
        return f"{self.name} ({self.start_time} - {self.end_time})"


class StaffSchedule(AuditModel):
    staff = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='hrms_schedules'
    )
    shift = models.ForeignKey(ShiftType, on_delete=models.PROTECT)
    date = models.DateField()
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('staff', 'date')
        ordering = ['date']


class AttendanceRecord(TimeStampedModel):
    staff = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='attendance_records'
    )
    date = models.DateField(default=timezone.now)
    clock_in = models.TimeField(null=True, blank=True)
    clock_out = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=[
        ('PRESENT', 'Present'),
        ('ABSENT', 'Absent'),
        ('LATE', 'Late'),
        ('HALF_DAY', 'Half Day'),
        ('ON_LEAVE', 'On Leave'),
        ('PUBLIC_HOLIDAY', 'Public Holiday'),
    ], default='PRESENT')
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('staff', 'date')
        ordering = ['-date']


class LeaveType(AuditModel):
    name = models.CharField(max_length=100)
    days_allowed_per_year = models.PositiveIntegerField(default=14)
    is_paid = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class LeaveRequestStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'
    CANCELLED = 'CANCELLED', 'Cancelled'


class LeaveRequest(AuditModel):
    staff = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='leave_requests'
    )
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=LeaveRequestStatus.choices, default=LeaveRequestStatus.PENDING)
    approved_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='approved_leaves'
    )
    approval_notes = models.TextField(blank=True)
    applied_on = models.DateField(default=timezone.now)

    class Meta:
        ordering = ['-applied_on']

    @property
    def days_requested(self):
        return (self.end_date - self.start_date).days + 1
