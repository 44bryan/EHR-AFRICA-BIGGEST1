import uuid
import hashlib
from django.db import models
from django.conf import settings
from django.utils import timezone

from apps.core.models import AuditModel


class AppointmentStatus(models.TextChoices):
    SCHEDULED = 'SCHEDULED', 'Scheduled'
    WAITING = 'WAITING', 'Patient Waiting'
    IN_SESSION = 'IN_SESSION', 'In Session'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'
    NO_SHOW = 'NO_SHOW', 'No Show'


class AppointmentType(models.TextChoices):
    NEW = 'NEW', 'New Consultation'
    FOLLOW_UP = 'FOLLOW_UP', 'Follow-Up'
    PRESCRIPTION = 'PRESCRIPTION', 'Prescription Review'
    REFERRAL = 'REFERRAL', 'Specialist Referral'
    URGENT = 'URGENT', 'Urgent / Triage'


class TeleAppointment(AuditModel):
    """A scheduled telemedicine (video) consultation."""

    patient = models.ForeignKey(
        'patients.Patient',
        on_delete=models.CASCADE,
        related_name='tele_appointments',
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tele_appointments_as_doctor',
    )
    appointment_type = models.CharField(
        max_length=20,
        choices=AppointmentType.choices,
        default=AppointmentType.FOLLOW_UP,
    )
    status = models.CharField(
        max_length=20,
        choices=AppointmentStatus.choices,
        default=AppointmentStatus.SCHEDULED,
    )
    scheduled_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=20)
    chief_complaint = models.TextField(blank=True)
    # Unique room identifier — used to generate the video room URL
    session_room_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    # Tracking
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    actual_duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    patient_joined = models.BooleanField(default=False)
    cancellation_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-scheduled_at']
        verbose_name = 'Tele-Appointment'
        verbose_name_plural = 'Tele-Appointments'

    def __str__(self):
        return f"Tele-{self.pk}: {self.patient} with {self.doctor.get_full_name()} @ {self.scheduled_at:%d %b %Y %H:%M}"

    @property
    def session_url(self):
        """Public Jitsi Meet room URL for this appointment."""
        jitsi = getattr(settings, 'JITSI_SERVER', 'https://meet.jit.si')
        room = f"EHR-{self.session_room_id.hex[:16].upper()}"
        return f"{jitsi}/{room}"

    @property
    def patient_join_token(self):
        """Short token to authenticate patient join link (not a full security system)."""
        raw = f"{self.session_room_id}{self.patient_id}{settings.SECRET_KEY}"
        return hashlib.sha256(raw.encode()).hexdigest()[:20]

    @property
    def is_active(self):
        return self.status in (AppointmentStatus.WAITING, AppointmentStatus.IN_SESSION)

    @property
    def can_start(self):
        return self.status in (AppointmentStatus.SCHEDULED, AppointmentStatus.WAITING)

    @property
    def duration_display(self):
        if self.started_at and self.ended_at:
            delta = self.ended_at - self.started_at
            mins = int(delta.total_seconds() // 60)
            return f"{mins} min"
        return f"{self.duration_minutes} min (planned)"


class TeleSessionNote(AuditModel):
    """SOAP note recorded during or after a telemedicine session."""

    appointment = models.OneToOneField(
        TeleAppointment,
        on_delete=models.CASCADE,
        related_name='session_note',
    )
    subjective = models.TextField(help_text="Patient's complaint in their own words")
    objective = models.TextField(blank=True, help_text="Observations, vitals reported by patient")
    assessment = models.TextField(blank=True, help_text="Diagnosis or clinical impression")
    plan = models.TextField(blank=True, help_text="Treatment plan, medications ordered")
    follow_up_days = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Recommend follow-up after this many days (leave blank if none)",
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Tele-Session Note'

    def __str__(self):
        return f"Note for Tele-{self.appointment_id}"
