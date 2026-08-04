"""
HMO / Insurance Claim Management

Covers: CNPS, Mutual de Santé, corporate employer schemes, NHIS.
Workflow: Enrol patient → pre-auth (if required) → visit → create claim
          → batch with other claims → submit to payer → reconcile payment.
"""
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.core.models import AuditModel, TimeStampedModel


# ── Scheme / Payer ────────────────────────────────────────────────────────────

class SchemeType(models.TextChoices):
    CNPS      = 'CNPS',      'CNPS (National Social Insurance)'
    MUTUAL    = 'MUTUAL',    'Mutual de Santé'
    CORPORATE = 'CORPORATE', 'Corporate / Employer Scheme'
    NHIS      = 'NHIS',      'NHIS'
    OTHER     = 'OTHER',     'Other'


class InsuranceScheme(TimeStampedModel):
    """A payer / insurance scheme (CNPS, a mutual, a corporate employer, etc.)."""
    name               = models.CharField(max_length=200, unique=True)
    code               = models.CharField(max_length=20, unique=True, help_text='Short internal code e.g. CNPS01')
    scheme_type        = models.CharField(max_length=20, choices=SchemeType.choices, default=SchemeType.OTHER)
    coverage_pct       = models.DecimalField(
        max_digits=5, decimal_places=2, default=80,
        help_text='Percentage the scheme pays (e.g. 80 = scheme pays 80%, patient pays 20%)',
    )
    pre_auth_required  = models.BooleanField(default=False, help_text='Require pre-authorisation before rendering service')
    max_annual_claim   = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                              help_text='Annual claim ceiling per member in FCFA (blank = unlimited)')
    contact_phone      = models.CharField(max_length=30, blank=True)
    contact_email      = models.EmailField(blank=True)
    address            = models.TextField(blank=True)
    notes              = models.TextField(blank=True)
    is_active          = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Insurance Scheme'
        verbose_name_plural = 'Insurance Schemes'

    def __str__(self):
        return f'{self.name} ({self.code})'


# ── Enrolled Members ──────────────────────────────────────────────────────────

class InsuredMember(TimeStampedModel):
    """A patient enrolled in an insurance scheme."""
    patient        = models.ForeignKey('patients.Patient', on_delete=models.PROTECT,
                                       related_name='insurance_memberships')
    scheme         = models.ForeignKey(InsuranceScheme, on_delete=models.PROTECT,
                                       related_name='members')
    member_number  = models.CharField(max_length=60)
    group_number   = models.CharField(max_length=60, blank=True, help_text='Corporate group / policy number')
    card_expiry    = models.DateField(null=True, blank=True)
    copay_pct      = models.DecimalField(
        max_digits=5, decimal_places=2, default=20,
        help_text='Patient co-pay percentage (overrides scheme default if set)',
    )
    dependant_of   = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='dependants', help_text='If this is a dependant, link to primary member')
    is_primary     = models.BooleanField(default=True)
    is_active      = models.BooleanField(default=True)
    enrolled_date  = models.DateField(default=timezone.localdate)
    notes          = models.TextField(blank=True)

    class Meta:
        ordering = ['patient__last_name', 'patient__first_name']
        unique_together = [('patient', 'scheme')]
        verbose_name = 'Insured Member'
        verbose_name_plural = 'Insured Members'

    def __str__(self):
        return f'{self.patient.full_name} — {self.scheme.code} ({self.member_number})'

    @property
    def is_expired(self):
        if self.card_expiry:
            return self.card_expiry < timezone.localdate()
        return False


# ── Pre-Authorisation ─────────────────────────────────────────────────────────

class PreAuthStatus(models.TextChoices):
    PENDING  = 'PENDING',  'Pending Scheme Response'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected by Scheme'
    EXPIRED  = 'EXPIRED',  'Expired'
    WAIVED   = 'WAIVED',   'Pre-auth Waived (Emergency)'


class PreAuthorization(AuditModel):
    """Pre-authorisation request sent to a payer before rendering a service."""
    member              = models.ForeignKey(InsuredMember, on_delete=models.PROTECT,
                                             related_name='pre_auths')
    visit               = models.ForeignKey('patients.Visit', on_delete=models.PROTECT,
                                             related_name='pre_auths', null=True, blank=True)
    service_description = models.TextField(help_text='Describe procedure/service needing pre-auth')
    estimated_cost      = models.DecimalField(max_digits=12, decimal_places=2)
    status              = models.CharField(max_length=20, choices=PreAuthStatus.choices,
                                            default=PreAuthStatus.PENDING)
    auth_code           = models.CharField(max_length=60, blank=True,
                                            help_text='Approval code returned by scheme')
    requested_at        = models.DateTimeField(default=timezone.now)
    responded_at        = models.DateTimeField(null=True, blank=True)
    valid_until         = models.DateField(null=True, blank=True)
    rejection_reason    = models.TextField(blank=True)
    notes               = models.TextField(blank=True)

    class Meta:
        ordering = ['-requested_at']
        verbose_name = 'Pre-Authorisation'
        verbose_name_plural = 'Pre-Authorisations'

    def __str__(self):
        return f'PreAuth {self.pk} — {self.member} [{self.status}]'

    @property
    def is_valid(self):
        if self.status != PreAuthStatus.APPROVED:
            return False
        if self.valid_until and self.valid_until < timezone.localdate():
            return False
        return True


# ── Claim Batch ───────────────────────────────────────────────────────────────

class ClaimBatchStatus(models.TextChoices):
    DRAFT      = 'DRAFT',      'Draft — Building'
    SUBMITTED  = 'SUBMITTED',  'Submitted to Scheme'
    PROCESSING = 'PROCESSING', 'Scheme Processing'
    PAID       = 'PAID',       'Paid in Full'
    PARTIAL    = 'PARTIAL',    'Partially Paid'
    REJECTED   = 'REJECTED',   'Rejected by Scheme'


class ClaimBatch(AuditModel):
    """A submission batch sent to the insurer containing multiple claims."""
    batch_number     = models.CharField(max_length=30, unique=True)
    scheme           = models.ForeignKey(InsuranceScheme, on_delete=models.PROTECT,
                                          related_name='claim_batches')
    submitted_by     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                          related_name='claim_batches_submitted', null=True, blank=True)
    submission_date  = models.DateField(null=True, blank=True)
    status           = models.CharField(max_length=20, choices=ClaimBatchStatus.choices,
                                         default=ClaimBatchStatus.DRAFT)
    total_claimed    = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_approved   = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_paid       = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    payment_date     = models.DateField(null=True, blank=True)
    payment_ref      = models.CharField(max_length=100, blank=True,
                                         help_text='Scheme payment reference / cheque number')
    notes            = models.TextField(blank=True)

    class Meta:
        ordering = ['-submission_date', '-created_at']
        verbose_name = 'Claim Batch'
        verbose_name_plural = 'Claim Batches'

    def __str__(self):
        return f'Batch {self.batch_number} — {self.scheme.code} [{self.status}]'

    def recalculate_totals(self):
        """Recompute totals from constituent claims."""
        from django.db.models import Sum
        agg = self.claims.filter(is_deleted=False).aggregate(
            tc=Sum('claimed_amount'),
            ta=Sum('approved_amount'),
            tp=Sum('paid_amount'),
        )
        self.total_claimed  = agg['tc'] or 0
        self.total_approved = agg['ta'] or 0
        self.total_paid     = agg['tp'] or 0
        self.save(update_fields=['total_claimed', 'total_approved', 'total_paid'])


# ── Individual Claim ──────────────────────────────────────────────────────────

class ClaimStatus(models.TextChoices):
    DRAFT     = 'DRAFT',     'Draft'
    SUBMITTED = 'SUBMITTED', 'Submitted'
    APPROVED  = 'APPROVED',  'Approved'
    REJECTED  = 'REJECTED',  'Rejected'
    PARTIAL   = 'PARTIAL',   'Partially Approved'
    PAID      = 'PAID',      'Paid'


class Claim(AuditModel):
    """Individual insurance claim for one patient visit."""
    claim_number     = models.CharField(max_length=30, unique=True)
    batch            = models.ForeignKey(ClaimBatch, on_delete=models.SET_NULL,
                                          related_name='claims', null=True, blank=True)
    member           = models.ForeignKey(InsuredMember, on_delete=models.PROTECT,
                                          related_name='claims')
    visit            = models.ForeignKey('patients.Visit', on_delete=models.PROTECT,
                                          related_name='insurance_claims')
    invoice          = models.ForeignKey('billing.Invoice', on_delete=models.PROTECT,
                                          related_name='insurance_claims', null=True, blank=True)
    pre_auth         = models.ForeignKey(PreAuthorization, on_delete=models.SET_NULL,
                                          related_name='claims', null=True, blank=True)
    status           = models.CharField(max_length=20, choices=ClaimStatus.choices,
                                         default=ClaimStatus.DRAFT)
    service_date     = models.DateField(default=timezone.localdate)
    claimed_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    approved_amount  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    patient_copay    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    rejection_reason = models.TextField(blank=True)
    rejection_date   = models.DateField(null=True, blank=True)
    notes            = models.TextField(blank=True)

    class Meta:
        ordering = ['-service_date', '-created_at']
        verbose_name = 'Claim'
        verbose_name_plural = 'Claims'

    def __str__(self):
        return f'Claim {self.claim_number} — {self.member.patient.full_name} [{self.status}]'

    def recalculate_claimed(self):
        """Sum up ClaimItems → update claimed_amount."""
        from django.db.models import Sum
        total = self.items.aggregate(t=Sum('claimed_amount'))['t'] or 0
        self.claimed_amount = total
        self.save(update_fields=['claimed_amount'])


# ── Claim Line Items ──────────────────────────────────────────────────────────

class ClaimItem(models.Model):
    """A single service line within a claim."""
    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    claim            = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name='items')
    service_name     = models.CharField(max_length=200)
    quantity         = models.PositiveIntegerField(default=1)
    unit_price       = models.DecimalField(max_digits=10, decimal_places=2)
    claimed_amount   = models.DecimalField(max_digits=12, decimal_places=2)
    approved_amount  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    rejection_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['service_name']

    def __str__(self):
        return f'{self.service_name} × {self.quantity} = {self.claimed_amount}'

    def save(self, *args, **kwargs):
        if not self.claimed_amount:
            self.claimed_amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)
