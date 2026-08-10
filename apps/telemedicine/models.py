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

    # Override the UUID pk inherited from TimeStampedModel — DB column is bigint
    id = models.BigAutoField(primary_key=True)

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
        """Public Jitsi Meet room URL for this appointment.
        Config fragment skips the pre-join lobby and goes straight into the room.
        """
        jitsi = getattr(settings, 'JITSI_SERVER', 'https://meet.jit.si')
        room = f"EHRAfrica{self.session_room_id.hex[:12].upper()}"
        config = (
            "#config.prejoinPageEnabled=false"
            "&config.startWithAudioMuted=false"
            "&config.startWithVideoMuted=false"
            "&config.disableDeepLinking=true"
            "&config.enableLobby=false"
            "&config.disableModeratorIndicator=true"
            "&config.requireDisplayName=false"
        )
        return f"{jitsi}/{room}{config}"

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


class IntakeUrgency(models.TextChoices):
    LOW = 'low', 'Low — Routine'
    MODERATE = 'moderate', 'Moderate — Soon'
    HIGH = 'high', 'High — Urgent'
    EMERGENCY = 'emergency', 'Emergency — Immediate'


class PreConsultationIntake(AuditModel):
    """Patient-submitted symptom intake — auto-triaged by AI before the session."""

    id = models.BigAutoField(primary_key=True)

    appointment = models.OneToOneField(
        TeleAppointment,
        on_delete=models.CASCADE,
        related_name='intake',
    )
    symptoms = models.TextField(help_text='Main symptoms / reason for this call')
    duration = models.CharField(max_length=100, blank=True)
    severity_score = models.PositiveSmallIntegerField(
        default=5, help_text='Self-rated severity 1 (mild) to 10 (severe)'
    )
    worsening = models.BooleanField(default=False)
    current_medications = models.TextField(blank=True)
    known_allergies = models.TextField(blank=True)
    other_symptoms = models.TextField(blank=True)
    blood_pressure = models.CharField(max_length=20, blank=True)
    temperature = models.CharField(max_length=10, blank=True)
    # AI-generated
    ai_triage_summary = models.TextField(blank=True)
    ai_urgency = models.CharField(max_length=20, blank=True, choices=IntakeUrgency.choices)
    ai_key_concerns = models.JSONField(default=list, blank=True)
    ai_doctor_notes = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Pre-Consultation Intake'

    def __str__(self):
        return f'Intake for Tele-{self.appointment_id}'

    @property
    def urgency_color(self):
        return {'low': 'success', 'moderate': 'warning', 'high': 'danger', 'emergency': 'danger'}.get(self.ai_urgency, 'secondary')

    @property
    def urgency_label(self):
        return {'low': 'Routine', 'moderate': 'See Soon', 'high': 'Urgent', 'emergency': 'EMERGENCY'}.get(self.ai_urgency, '—')


class TelePrescription(AuditModel):
    """Drug prescribed during or after a telemedicine session."""

    id = models.BigAutoField(primary_key=True)
    appointment = models.ForeignKey(
        'TeleAppointment', on_delete=models.CASCADE, related_name='prescriptions'
    )
    drug_name = models.CharField(max_length=200)
    dose = models.CharField(max_length=100)
    frequency = models.CharField(max_length=100, blank=True)
    duration = models.CharField(max_length=100, blank=True)
    route = models.CharField(max_length=60, blank=True, help_text='e.g. Oral, Topical, IV')
    instructions = models.TextField(blank=True)
    prescribed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='tele_prescriptions_given',
    )

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Tele-Prescription Item'

    def __str__(self):
        return f"{self.drug_name} {self.dose} — Tele-{self.appointment_id}"


class TeleReferral(AuditModel):
    """Referral generated from a telemedicine session."""

    class Urgency(models.TextChoices):
        ROUTINE   = 'ROUTINE',   'Routine'
        SOON      = 'SOON',      'Soon — within a week'
        URGENT    = 'URGENT',    'Urgent — within 24 hours'
        EMERGENCY = 'EMERGENCY', 'Emergency — same day'

    id = models.BigAutoField(primary_key=True)
    appointment = models.ForeignKey(
        'TeleAppointment', on_delete=models.CASCADE, related_name='referrals'
    )
    referral_to = models.CharField(max_length=200, help_text='Specialist / department / hospital')
    urgency = models.CharField(max_length=20, choices=Urgency.choices, default=Urgency.ROUTINE)
    reason = models.TextField()
    clinical_summary = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Tele-Referral'

    def __str__(self):
        return f"Referral to {self.referral_to} — Tele-{self.appointment_id}"


class TeleSessionNote(AuditModel):
    """SOAP note recorded during or after a telemedicine session."""

    # Override the UUID pk inherited from TimeStampedModel — DB column is bigint
    id = models.BigAutoField(primary_key=True)

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
