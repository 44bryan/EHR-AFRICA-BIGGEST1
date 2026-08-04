from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.core.models import TimeStampedModel, AuditModel


class BodyStatus(models.TextChoices):
    RECEIVED = 'RECEIVED', 'Received'
    IN_STORAGE = 'IN_STORAGE', 'In Storage'
    POST_MORTEM = 'POST_MORTEM', 'Post-Mortem Pending'
    RELEASED = 'RELEASED', 'Released'
    TRANSFERRED = 'TRANSFERRED', 'Transferred'


class StorageStatus(models.TextChoices):
    AVAILABLE = 'AVAILABLE', 'Available'
    OCCUPIED = 'OCCUPIED', 'Occupied'
    MAINTENANCE = 'MAINTENANCE', 'Under Maintenance'


class PostMortemType(models.TextChoices):
    CLINICAL = 'CLINICAL', 'Clinical / Hospital'
    MEDICOLEGAL = 'MEDICOLEGAL', 'Medico-Legal'
    CORONER = 'CORONER', 'Coroner's Request'


class PostMortemStatus(models.TextChoices):
    REQUESTED = 'REQUESTED', 'Requested'
    APPROVED = 'APPROVED', 'Approved'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class CauseOfDeath(models.TextChoices):
    NATURAL = 'NATURAL', 'Natural'
    ACCIDENT = 'ACCIDENT', 'Accident'
    HOMICIDE = 'HOMICIDE', 'Homicide'
    SUICIDE = 'SUICIDE', 'Suicide'
    UNDETERMINED = 'UNDETERMINED', 'Undetermined'
    PENDING = 'PENDING', 'Pending Investigation'


class MortuaryAdmission(AuditModel):
    """Body receipt record."""
    # Body identification
    body_number = models.CharField(max_length=30, unique=True)
    full_name = models.CharField(max_length=200)
    age_years = models.PositiveSmallIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=[('M', 'Male'), ('F', 'Female'), ('U', 'Unknown')])
    # Link to patient if death occurred in hospital
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='mortuary_admissions'
    )
    # Death details
    date_of_death = models.DateTimeField()
    place_of_death = models.CharField(max_length=200, blank=True)
    cause_of_death = models.CharField(
        max_length=20, choices=CauseOfDeath.choices, default=CauseOfDeath.PENDING
    )
    provisional_cause_text = models.TextField(blank=True)
    # Body condition
    body_condition = models.CharField(max_length=20, choices=[
        ('GOOD', 'Good'), ('DECOMPOSED', 'Decomposed'), ('BURNED', 'Burned'),
        ('TRAUMATIC', 'Traumatic Injuries'), ('OTHER', 'Other')
    ], default='GOOD')
    identifying_marks = models.TextField(blank=True)
    # Administrative
    status = models.CharField(max_length=20, choices=BodyStatus.choices, default=BodyStatus.RECEIVED)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='bodies_received'
    )
    received_at = models.DateTimeField(default=timezone.now)
    # Next of kin
    next_of_kin_name = models.CharField(max_length=200, blank=True)
    next_of_kin_phone = models.CharField(max_length=20, blank=True)
    next_of_kin_relationship = models.CharField(max_length=100, blank=True)
    # Police / legal
    police_case_number = models.CharField(max_length=50, blank=True)
    doctor_who_certified = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-received_at']

    def __str__(self):
        return f"{self.body_number} — {self.full_name}"

    def save(self, *args, **kwargs):
        if not self.body_number:
            from django.utils import timezone as tz
            count = MortuaryAdmission.objects.count() + 1
            self.body_number = f"MORT-{tz.now().year}-{count:04d}"
        super().save(*args, **kwargs)


class MortuaryStorage(TimeStampedModel):
    """Cold storage compartment register."""
    compartment_number = models.CharField(max_length=20, unique=True)
    section = models.CharField(max_length=50, blank=True, help_text='e.g. Block A, Freezer 1')
    status = models.CharField(
        max_length=20, choices=StorageStatus.choices, default=StorageStatus.AVAILABLE
    )
    current_body = models.OneToOneField(
        MortuaryAdmission, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='storage_compartment'
    )
    temperature_celsius = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['compartment_number']

    def __str__(self):
        return f"Compartment {self.compartment_number} ({self.get_status_display()})"


class PostMortemRequest(AuditModel):
    """Post-mortem examination request."""
    admission = models.OneToOneField(
        MortuaryAdmission, on_delete=models.PROTECT, related_name='post_mortem'
    )
    pm_type = models.CharField(max_length=20, choices=PostMortemType.choices)
    status = models.CharField(
        max_length=20, choices=PostMortemStatus.choices, default=PostMortemStatus.REQUESTED
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='pm_requests_made'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pm_requests_approved'
    )
    pathologist = models.CharField(max_length=200, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    reason = models.TextField()
    findings = models.TextField(blank=True)
    final_cause_of_death = models.CharField(max_length=300, blank=True)
    report_reference = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"PM — {self.admission.full_name} ({self.get_status_display()})"


class BodyRelease(AuditModel):
    """Body release to family / funeral home."""
    admission = models.OneToOneField(
        MortuaryAdmission, on_delete=models.PROTECT, related_name='release'
    )
    released_to_name = models.CharField(max_length=200)
    released_to_id_type = models.CharField(max_length=50, blank=True, help_text='e.g. NIC, Passport')
    released_to_id_number = models.CharField(max_length=50, blank=True)
    released_to_phone = models.CharField(max_length=20, blank=True)
    relationship = models.CharField(max_length=100, blank=True)
    funeral_home = models.CharField(max_length=200, blank=True)
    transport_provider = models.CharField(max_length=200, blank=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='bodies_released'
    )
    released_at = models.DateTimeField(default=timezone.now)
    death_certificate_issued = models.BooleanField(default=False)
    certificate_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-released_at']

    def __str__(self):
        return f"Release — {self.admission.full_name} to {self.released_to_name}"
