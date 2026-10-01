"""
Appointment scheduling and doctor schedules.
"""
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import AuditModel, TimeStampedModel
from apps.core.utils import generate_appointment_number


class Appointment(AuditModel):
    class Status(models.TextChoices):
        SCHEDULED = 'SCHEDULED', _('Scheduled')
        CONFIRMED = 'CONFIRMED', _('Confirmed')
        CHECKED_IN = 'CHECKED_IN', _('Checked In')
        COMPLETED = 'COMPLETED', _('Completed')
        CANCELLED = 'CANCELLED', _('Cancelled')
        NO_SHOW = 'NO_SHOW', _('No Show')

    class AppointmentType(models.TextChoices):
        NEW = 'NEW', _('New Patient')
        FOLLOW_UP = 'FOLLOW_UP', _('Follow-up')
        PROCEDURE = 'PROCEDURE', _('Procedure')
        REVIEW = 'REVIEW', _('Review')
        EMERGENCY = 'EMERGENCY', _('Emergency')

    class ServiceTier(models.TextChoices):
        STANDARD = 'STANDARD', _('Standard')
        EXPRESS = 'EXPRESS', _('Express')
        VIP = 'VIP', _('VIP')
        EVIP = 'EVIP', _('Executive VIP')

    appointment_number = models.CharField(max_length=20, unique=True, editable=False)
    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE, related_name='appointments')
    department = models.ForeignKey('departments.Department', on_delete=models.SET_NULL, null=True, related_name='appointments')
    doctor = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointments',
    )
    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=30)
    appointment_type = models.CharField(max_length=15, choices=AppointmentType.choices, default=AppointmentType.FOLLOW_UP)
    service_tier = models.CharField(max_length=15, choices=ServiceTier.choices, default=ServiceTier.STANDARD)
    reason = models.TextField()
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.SCHEDULED)
    booked_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='booked_appointments',
    )
    cancellation_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    reminder_sent = models.BooleanField(default=False)

    class Meta:
        ordering = ['appointment_date', 'appointment_time']
        verbose_name = 'Appointment'

    def __str__(self):
        return f"{self.appointment_number} — {self.patient.full_name} [{self.appointment_date}]"

    def save(self, *args, **kwargs):
        if not self.appointment_number:
            self.appointment_number = generate_appointment_number()
        super().save(*args, **kwargs)


class DoctorSchedule(TimeStampedModel):
    WEEKDAY_CHOICES = [
        (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'),
        (3, 'Thursday'), (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday'),
    ]

    doctor = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='schedules')
    department = models.ForeignKey('departments.Department', on_delete=models.CASCADE)
    day_of_week = models.PositiveSmallIntegerField(choices=WEEKDAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_duration_minutes = models.PositiveSmallIntegerField(default=30)
    max_patients = models.PositiveSmallIntegerField(default=20)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [('doctor', 'day_of_week', 'department')]
        verbose_name = 'Doctor Schedule'

    def __str__(self):
        return f"{self.doctor.full_name} — {self.get_day_of_week_display()} ({self.start_time}–{self.end_time})"
