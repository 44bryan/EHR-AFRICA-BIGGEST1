"""
OPD - Outpatient Department
Patient flow management, visit tracking, department statistics.
"""
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel, AuditModel


class OPDVisitStatus(models.TextChoices):
    REGISTERED = 'REGISTERED', 'Registered'
    TRIAGE = 'TRIAGE', 'At Triage/Nurse'
    WAITING_DOCTOR = 'WAITING', 'Waiting for Doctor'
    WITH_DOCTOR = 'WITH_DOCTOR', 'With Doctor'
    INVESTIGATION = 'INVESTIGATION', 'Investigation Ordered'
    PHARMACY = 'PHARMACY', 'At Pharmacy'
    BILLING = 'BILLING', 'At Billing'
    COMPLETED = 'COMPLETED', 'Completed'
    DID_NOT_ATTEND = 'DNA', 'Did Not Attend'


class OPDVisit(AuditModel):
    """Tracks a patient's outpatient flow for a given day"""
    visit_number = models.CharField(max_length=30, unique=True)
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.PROTECT, related_name='opd_visits'
    )
    visit = models.ForeignKey(
        'patients.Visit', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='opd_records'
    )
    department = models.ForeignKey(
        'departments.Department', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='opd_visits'
    )
    attending_doctor = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='opd_patients'
    )
    status = models.CharField(
        max_length=20, choices=OPDVisitStatus.choices, default=OPDVisitStatus.REGISTERED
    )
    visit_date = models.DateField(default=timezone.now)
    registration_time = models.DateTimeField(default=timezone.now)
    triage_time = models.DateTimeField(null=True, blank=True)
    doctor_seen_time = models.DateTimeField(null=True, blank=True)
    completed_time = models.DateTimeField(null=True, blank=True)
    chief_complaint = models.TextField(blank=True)
    triage_notes = models.TextField(blank=True)
    vital_signs = models.JSONField(default=dict, blank=True)
    is_return_visit = models.BooleanField(default=False)
    payment_status = models.CharField(max_length=20, choices=[
        ('UNPAID', 'Unpaid'), ('PARTIAL', 'Partially Paid'), ('PAID', 'Paid'), ('WAIVED', 'Waived')
    ], default='UNPAID')

    class Meta:
        ordering = ['-visit_date', 'registration_time']

    def __str__(self):
        return f"OPD {self.visit_number} - {self.patient.full_name}"

    def save(self, *args, **kwargs):
        if not self.visit_number:
            today = timezone.localdate()
            count = OPDVisit.objects.filter(visit_date=today).count() + 1
            self.visit_number = f"OPD-{today.strftime('%Y%m%d')}-{count:04d}"
        super().save(*args, **kwargs)

    @property
    def total_wait_minutes(self):
        if self.doctor_seen_time and self.registration_time:
            return int((self.doctor_seen_time - self.registration_time).total_seconds() / 60)
        return None

    def update_status(self, new_status):
        now = timezone.now()
        self.status = new_status
        if new_status == OPDVisitStatus.TRIAGE and not self.triage_time:
            self.triage_time = now
        elif new_status == OPDVisitStatus.WITH_DOCTOR and not self.doctor_seen_time:
            self.doctor_seen_time = now
        elif new_status == OPDVisitStatus.COMPLETED and not self.completed_time:
            self.completed_time = now
        self.save()


class TriageLevel(models.TextChoices):
    EMERGENCY = '1', 'Level 1 - Emergency'
    URGENT = '2', 'Level 2 - Urgent'
    LESS_URGENT = '3', 'Level 3 - Less Urgent'
    NON_URGENT = '4', 'Level 4 - Non-Urgent'
    ROUTINE = '5', 'Level 5 - Routine'
