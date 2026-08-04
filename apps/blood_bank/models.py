"""
Blood Bank Module

Covers: donor register, blood unit inventory, cross-match,
        issue/transfusion log, expiry tracking, and wastage.
"""
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.core.models import AuditModel, TimeStampedModel


class BloodGroup(models.TextChoices):
    A_POS  = 'A+',  'A+'
    A_NEG  = 'A-',  'A-'
    B_POS  = 'B+',  'B+'
    B_NEG  = 'B-',  'B-'
    AB_POS = 'AB+', 'AB+'
    AB_NEG = 'AB-', 'AB-'
    O_POS  = 'O+',  'O+'
    O_NEG  = 'O-',  'O-'


class BloodProduct(models.TextChoices):
    WHOLE       = 'WHOLE',   'Whole Blood'
    PRBC        = 'PRBC',    'Packed Red Blood Cells (pRBC)'
    FFP         = 'FFP',     'Fresh Frozen Plasma (FFP)'
    PLATELETS   = 'PLT',     'Platelets'
    CRYO        = 'CRYO',    'Cryoprecipitate'
    ALBUMIN     = 'ALB',     'Albumin'


class DonorCategory(models.TextChoices):
    VOLUNTARY  = 'VOLUNTARY',  'Voluntary / Community'
    REPLACEMENT = 'REPLACEMENT', 'Replacement (Family / Friend)'
    AUTOLOGOUS = 'AUTOLOGOUS', 'Autologous (Patient Pre-deposit)'
    DIRECTED   = 'DIRECTED',   'Directed Donation'


# ── Donor Register ────────────────────────────────────────────────────────────

class BloodDonor(TimeStampedModel):
    """A blood donor — may or may not be a registered patient."""
    donor_id       = models.CharField(max_length=20, unique=True)
    full_name      = models.CharField(max_length=150)
    blood_group    = models.CharField(max_length=5, choices=BloodGroup.choices)
    date_of_birth  = models.DateField(null=True, blank=True)
    gender         = models.CharField(max_length=1, choices=[('M', 'Male'), ('F', 'Female')], blank=True)
    phone          = models.CharField(max_length=20, blank=True)
    address        = models.TextField(blank=True)
    category       = models.CharField(max_length=15, choices=DonorCategory.choices,
                                       default=DonorCategory.VOLUNTARY)
    patient        = models.ForeignKey('patients.Patient', on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='blood_donations',
                                        help_text='Link if this donor is also a registered patient')
    last_donation  = models.DateField(null=True, blank=True)
    total_donations = models.PositiveIntegerField(default=0)
    is_deferred    = models.BooleanField(default=False, help_text='Temporarily deferred from donating')
    deferral_reason = models.TextField(blank=True)
    deferral_until = models.DateField(null=True, blank=True)
    notes          = models.TextField(blank=True)

    class Meta:
        ordering = ['full_name']
        verbose_name = 'Blood Donor'
        verbose_name_plural = 'Blood Donors'

    def __str__(self):
        return f'{self.donor_id} — {self.full_name} ({self.blood_group})'

    @property
    def can_donate(self):
        if self.is_deferred:
            if self.deferral_until and self.deferral_until > timezone.localdate():
                return False
        if self.last_donation:
            # Minimum 56 days between whole-blood donations
            from datetime import timedelta
            if (timezone.localdate() - self.last_donation).days < 56:
                return False
        return True


# ── Blood Unit / Inventory ────────────────────────────────────────────────────

class BloodUnitStatus(models.TextChoices):
    AVAILABLE  = 'AVAILABLE',  'Available'
    RESERVED   = 'RESERVED',   'Reserved (Cross-matched)'
    ISSUED     = 'ISSUED',     'Issued to Patient'
    EXPIRED    = 'EXPIRED',    'Expired'
    DISCARDED  = 'DISCARDED',  'Discarded / Wastage'


class BloodUnit(AuditModel):
    """A single collected and processed blood unit in inventory."""
    unit_number    = models.CharField(max_length=30, unique=True)
    product        = models.CharField(max_length=10, choices=BloodProduct.choices,
                                       default=BloodProduct.WHOLE)
    blood_group    = models.CharField(max_length=5, choices=BloodGroup.choices)
    volume_ml      = models.PositiveIntegerField(default=450, help_text='Volume in mL')
    donor          = models.ForeignKey(BloodDonor, on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='donated_units')
    collection_date = models.DateField(default=timezone.localdate)
    expiry_date    = models.DateField()
    status         = models.CharField(max_length=15, choices=BloodUnitStatus.choices,
                                       default=BloodUnitStatus.AVAILABLE)
    storage_location = models.CharField(max_length=60, blank=True, help_text='e.g. Fridge A, Shelf 2')
    # Screening results
    hiv_tested     = models.BooleanField(default=False)
    hbsag_tested   = models.BooleanField(default=False)
    hcv_tested     = models.BooleanField(default=False)
    syphilis_tested = models.BooleanField(default=False)
    malaria_tested = models.BooleanField(default=False)
    all_negative   = models.BooleanField(default=False,
                                          help_text='True = all screening tests came back negative — unit is safe')
    discarded_reason = models.TextField(blank=True)
    notes          = models.TextField(blank=True)

    class Meta:
        ordering = ['expiry_date']
        verbose_name = 'Blood Unit'
        verbose_name_plural = 'Blood Units'

    def __str__(self):
        return f'{self.unit_number} — {self.blood_group} {self.get_product_display()} [{self.status}]'

    @property
    def is_expired(self):
        return self.expiry_date < timezone.localdate()


# ── Cross-Match ───────────────────────────────────────────────────────────────

class CrossMatchResult(models.TextChoices):
    COMPATIBLE   = 'COMPATIBLE',   'Compatible'
    INCOMPATIBLE = 'INCOMPATIBLE', 'Incompatible'
    PENDING      = 'PENDING',      'Pending'


class CrossMatch(AuditModel):
    """Cross-match test between a blood unit and a patient."""
    patient        = models.ForeignKey('patients.Patient', on_delete=models.PROTECT,
                                        related_name='cross_matches')
    blood_unit     = models.ForeignKey(BloodUnit, on_delete=models.PROTECT,
                                        related_name='cross_matches')
    visit          = models.ForeignKey('patients.Visit', on_delete=models.PROTECT,
                                        related_name='cross_matches', null=True, blank=True)
    requested_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                        related_name='cross_match_requests')
    performed_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                        related_name='cross_match_results', null=True, blank=True)
    requested_at   = models.DateTimeField(default=timezone.now)
    result         = models.CharField(max_length=15, choices=CrossMatchResult.choices,
                                       default=CrossMatchResult.PENDING)
    completed_at   = models.DateTimeField(null=True, blank=True)
    notes          = models.TextField(blank=True)

    class Meta:
        ordering = ['-requested_at']
        verbose_name = 'Cross-Match'
        verbose_name_plural = 'Cross-Matches'

    def __str__(self):
        return f'XM {self.patient.full_name} × {self.blood_unit.unit_number} [{self.result}]'

    def save(self, *args, **kwargs):
        # When compatible → reserve the blood unit
        if self.result == CrossMatchResult.COMPATIBLE:
            self.blood_unit.status = BloodUnitStatus.RESERVED
            self.blood_unit.save(update_fields=['status'])
        super().save(*args, **kwargs)


# ── Blood Issue / Transfusion ─────────────────────────────────────────────────

class BloodIssueStatus(models.TextChoices):
    ISSUED      = 'ISSUED',     'Issued — In Progress'
    TRANSFUSED  = 'TRANSFUSED', 'Transfused'
    RETURNED    = 'RETURNED',   'Returned Unused'
    REACTION    = 'REACTION',   'Transfusion Reaction'


class BloodIssue(AuditModel):
    """Record of blood issued from the blood bank to a patient."""
    issue_number   = models.CharField(max_length=30, unique=True)
    blood_unit     = models.ForeignKey(BloodUnit, on_delete=models.PROTECT,
                                        related_name='issues')
    patient        = models.ForeignKey('patients.Patient', on_delete=models.PROTECT,
                                        related_name='blood_issues')
    visit          = models.ForeignKey('patients.Visit', on_delete=models.PROTECT,
                                        related_name='blood_issues', null=True, blank=True)
    cross_match    = models.ForeignKey(CrossMatch, on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='issues')
    issued_by      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                        related_name='blood_issued')
    received_by    = models.CharField(max_length=100, blank=True,
                                       help_text='Name of nurse/doctor who collected the unit')
    issued_at      = models.DateTimeField(default=timezone.now)
    status         = models.CharField(max_length=15, choices=BloodIssueStatus.choices,
                                       default=BloodIssueStatus.ISSUED)
    transfused_at  = models.DateTimeField(null=True, blank=True)
    volume_transfused_ml = models.PositiveIntegerField(null=True, blank=True)
    reaction_description = models.TextField(blank=True)
    notes          = models.TextField(blank=True)

    class Meta:
        ordering = ['-issued_at']
        verbose_name = 'Blood Issue'
        verbose_name_plural = 'Blood Issues'

    def __str__(self):
        return f'{self.issue_number} — {self.patient.full_name} [{self.status}]'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update blood unit status
        if self.status == BloodIssueStatus.ISSUED:
            self.blood_unit.status = BloodUnitStatus.ISSUED
            self.blood_unit.save(update_fields=['status'])
        elif self.status == BloodIssueStatus.RETURNED:
            self.blood_unit.status = BloodUnitStatus.AVAILABLE
            self.blood_unit.save(update_fields=['status'])
