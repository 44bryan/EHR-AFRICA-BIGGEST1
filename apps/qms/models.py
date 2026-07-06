"""
QMS - Queue Management System
Multi-tier, multi-point patient flow management for GLUDD Specialist Eye Hospital.

Tiers:  STANDARD | EXPRESS | FAST_TRACK | VIP

Entry rules:
  STANDARD   — MUST take a ticket at the Main Gate before proceeding.
  EXPRESS    — NOT obliged to take a gate ticket. They enter through the
               Express/Fast Track desk (side entrance). Ticket optional.
  FAST_TRACK — Same as EXPRESS.
  VIP        — NOT obliged to take a gate ticket. They have their own
               dedicated VIP Reception at the back entrance. Ticket optional.

Issuance points:
  GATE          → Standard patients (mandatory)
  VIP_RECEPTION → VIP patients via back entrance
  EXPRESS_DESK  → Express / Fast Track patients via side entrance
  CASHIER       → Any tier can be issued here if they walk in without a ticket
  SYSTEM        → Auto-generated when a patient is routed between departments

Insurance Consultation Room:
  Patients insured by partnered insurance companies are routed to the
  INSURANCE_CONSULT service type. Billing is handled directly by the insurer.

Token prefix:  S-001  E-001  FT-001  V-001
"""
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel


# ── Service Tiers (patient class) ────────────────────────────────────────────
class ServiceTier(models.TextChoices):
    STANDARD   = 'STANDARD',    'Standard'
    EXPRESS    = 'EXPRESS',     'Express'
    FAST_TRACK = 'FAST_TRACK',  'Fast Track'
    VIP        = 'VIP',         'VIP'

TIER_PREFIX = {
    ServiceTier.STANDARD:   'S',
    ServiceTier.EXPRESS:    'E',
    ServiceTier.FAST_TRACK: 'FT',
    ServiceTier.VIP:        'V',
}

TIER_PRIORITY = {
    ServiceTier.STANDARD:   0,
    ServiceTier.EXPRESS:    10,
    ServiceTier.FAST_TRACK: 20,
    ServiceTier.VIP:        30,
}

# ── Where the entry ticket was issued ────────────────────────────────────────
class IssuancePoint(models.TextChoices):
    GATE          = 'GATE',          'Main Gate (Standard — mandatory)'
    VIP_RECEPTION = 'VIP_RECEPTION', 'VIP Reception (Back Entrance)'
    EXPRESS_DESK  = 'EXPRESS_DESK',  'Express / Fast Track Desk (Side Entrance)'
    CASHIER       = 'CASHIER',       'Cashier (walk-in without prior ticket)'
    SYSTEM        = 'SYSTEM',        'System (auto-routed)'


# ── Hospital departments / service stations ───────────────────────────────────
class ServiceType(models.TextChoices):
    # Entry / Admin
    RECEPTIONIST   = 'RECEPTIONIST', 'Receptionist (New Patient Registration)'
    CASHIER        = 'CASHIER',      'Cashier / Registration'
    PARAMETERS     = 'PARAMETERS',   'Parameters & Triage'
    # VIP / Express dedicated triage
    PARAMETERS_VIP = 'PARAMS_VIP',   'Parameters — VIP / Express / Fast Track'
    # Consultation units — tier-specific rooms
    VIP_CONSULT    = 'VIP_CONSULT',  'VIP Consultation Room'
    EXPRESS_CONSULT= 'EXP_CONSULT',  'Express / Fast Track Consultation'
    # Standard consultation units (shared queue, tier-priority ordered)
    GENERAL        = 'GENERAL',    'General Ophthalmology'
    RETINA         = 'RETINA',     'Retina Clinic'
    GLAUCOMA       = 'GLAUCOMA',   'Glaucoma Clinic'
    CATARACT       = 'CATARACT',   'Cataract / Surgical'
    PEDIATRIC      = 'PEDIATRIC',  'Pediatric Ophthalmology'
    NEURO          = 'NEURO',      'Neuro-ophthalmology'
    OCULOPLASTY    = 'OCULOPLASTY','Oculoplastics'
    CORNEA         = 'CORNEA',     'Cornea Clinic'
    UVEITIS        = 'UVEITIS',    'Uveitis Clinic'
    # Diagnostics
    REFRACTION     = 'REFRACTION', 'Refraction / Optometry'
    INVESTIGATION  = 'INVEST',     'Eye Investigations'
    LABORATORY     = 'LAB',        'Laboratory'
    # Dispensing
    PHARMACY       = 'PHARMACY',   'Pharmacy'
    OPTICAL        = 'OPTICAL',    'Optical Shop'
    # Insurance — insured patients (Express/FastTrack/VIP section)
    INSURANCE_CONSULT = 'INSUR_CONSULT', 'Insurance Consultation Room'
    # Pre-surgical
    COUNSELING     = 'COUNSEL',    'Surgical Counseling'
    ADMISSION      = 'ADMISSION',  'Admission'
    PRE_OP         = 'PRE_OP',     'Pre-operative Waiting'
    # Inpatient / surgical
    THEATRE        = 'THEATRE',    'Operating Theatre'
    BILLING        = 'BILLING',    'Billing / Accounts'
    # Specialized procedure clinics
    LASER_CLINIC   = 'LASER',      'Laser Clinic (YAG / SLT / Photocoagulation)'
    INJECTION_CLINIC = 'INJECTION', 'Intravitreal Injection Clinic (Anti-VEGF)'
    EMERGENCY      = 'EMERGENCY',  'Emergency / Casualty Eye'
    CONTACT_LENS   = 'CONTACT_LENS', 'Contact Lens Clinic'
    LOW_VISION     = 'LOW_VISION', 'Low Vision & Rehabilitation'
    GEN_PHYS       = 'GEN_PHYS',  'General Medicine / Internal Medicine'


class TokenStatus(models.TextChoices):
    WAITING   = 'WAITING',   'Waiting'
    CALLED    = 'CALLED',    'Called'
    SERVING   = 'SERVING',   'Serving'
    COMPLETED = 'COMPLETED', 'Completed'
    SKIPPED   = 'SKIPPED',   'Skipped / Re-queued'
    CANCELLED = 'CANCELLED', 'Cancelled'
    NO_SHOW   = 'NO_SHOW',   'No Show'


# ── Physical / virtual service counters ─────────────────────────────────────
class ServiceCounter(TimeStampedModel):
    name         = models.CharField(max_length=100)
    code         = models.CharField(max_length=20, unique=True)
    service_type = models.CharField(max_length=20, choices=ServiceType.choices)
    # Which tiers this counter serves (comma-sep or all if blank)
    serves_tiers = models.CharField(
        max_length=100, blank=True,
        help_text='Comma-separated tiers this counter handles. Empty = all tiers.'
    )
    is_active        = models.BooleanField(default=True)
    current_serving  = models.ForeignKey(
        'QueueToken', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='serving_at_counter'
    )
    staff_assigned = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='qms_counters'
    )

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.name} ({self.code})"

    def get_serves_tiers(self):
        """Return list of tiers this counter serves, or all if unset."""
        if self.serves_tiers:
            return [t.strip() for t in self.serves_tiers.split(',')]
        return [t for t, _ in ServiceTier.choices]

    def get_tier_label(self):
        """Human-readable tier label for this counter."""
        _map = {
            'STANDARD':   'Standard',
            'EXPRESS':    'Express',
            'FAST_TRACK': 'Fast Track',
            'VIP':        'VIP',
        }
        if not self.serves_tiers:
            return 'All Tiers'
        tiers = [t.strip() for t in self.serves_tiers.split(',')]
        return ' / '.join(_map.get(t, t) for t in tiers)


# ── Patient queue token ───────────────────────────────────────────────────────
class QueueToken(TimeStampedModel):
    """
    One row = one patient at one service station.
    Entry tickets (GATE/CASHIER) track daily census.
    Department tokens (SYSTEM) are auto-created when staff route the patient.
    """
    token_number    = models.CharField(max_length=30, db_index=True)
    token_date      = models.DateField(default=timezone.localdate)
    patient         = models.ForeignKey(
        'patients.Patient', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='queue_tokens'
    )
    visit           = models.ForeignKey(
        'patients.Visit', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='queue_tokens'
    )
    patient_name    = models.CharField(max_length=200, blank=True)   # walk-ins
    service_type    = models.CharField(max_length=20, choices=ServiceType.choices)
    service_tier    = models.CharField(
        max_length=20, choices=ServiceTier.choices, default=ServiceTier.STANDARD
    )
    issuance_point  = models.CharField(
        max_length=20, choices=IssuancePoint.choices, default=IssuancePoint.GATE
    )
    status          = models.CharField(
        max_length=20, choices=TokenStatus.choices, default=TokenStatus.WAITING
    )
    # Higher = served sooner (Standard=0, Express=10, FastTrack=20, VIP=30)
    priority        = models.PositiveSmallIntegerField(default=0)
    counter         = models.ForeignKey(
        ServiceCounter, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='tokens'
    )
    issued_at       = models.DateTimeField(default=timezone.now)
    called_at       = models.DateTimeField(null=True, blank=True)
    served_at       = models.DateTimeField(null=True, blank=True)
    completed_at    = models.DateTimeField(null=True, blank=True)
    wait_time_minutes    = models.PositiveIntegerField(null=True, blank=True)
    service_time_minutes = models.PositiveIntegerField(null=True, blank=True)
    notes           = models.TextField(blank=True)
    is_insured      = models.BooleanField(default=False)
    insurance_company = models.CharField(max_length=100, blank=True)
    issued_by       = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='issued_tokens'
    )
    # Link to parent entry token (for department tokens)
    entry_token     = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='dept_tokens'
    )

    class Meta:
        ordering = ['-priority', 'issued_at']
        unique_together = [('token_number', 'token_date')]

    def __str__(self):
        return f"Token {self.token_number}"

    @property
    def display_name(self):
        if self.patient:
            return self.patient.full_name
        return self.patient_name or 'Walk-in'

    @property
    def tier_label(self):
        tier_map = {
            ServiceTier.STANDARD:   ('Standard', 'secondary'),
            ServiceTier.EXPRESS:    ('Express',  'info'),
            ServiceTier.FAST_TRACK: ('Fast Track','warning'),
            ServiceTier.VIP:        ('VIP',      'danger'),
        }
        return tier_map.get(self.service_tier, ('Standard', 'secondary'))

    def call(self, counter):
        self.status    = TokenStatus.CALLED
        self.called_at = timezone.now()
        self.counter   = counter
        if self.issued_at:
            delta = self.called_at - self.issued_at
            self.wait_time_minutes = int(delta.total_seconds() / 60)
        self.save()

    def start_serving(self):
        self.status   = TokenStatus.SERVING
        self.served_at = timezone.now()
        self.save()

    def complete(self):
        self.status       = TokenStatus.COMPLETED
        self.completed_at = timezone.now()
        if self.served_at:
            delta = self.completed_at - self.served_at
            self.service_time_minutes = int(delta.total_seconds() / 60)
        self.save()

    @property
    def visit_type_label(self):
        """Return the visit type ('NEW', 'FOLLOW_UP', etc.) from the linked Visit."""
        if self.visit:
            return self.visit.visit_type
        return ''

    @property
    def active_visit(self):
        """Return the linked Visit if it is still active (not completed/discharged)."""
        if self.visit and self.visit.status not in ('COMPLETED', 'DISCHARGED', 'CANCELLED'):
            return self.visit
        return None

    @property
    def display_token_number(self):
        """
        Always show the ENTRY ticket number to the patient.
        This is the number they received at the gate/reception desk.
        Department tokens are internal routing — patient only knows S-001, E-002, etc.
        """
        if self.entry_token:
            return self.entry_token.token_number
        if self.issuance_point in [
            IssuancePoint.GATE, IssuancePoint.VIP_RECEPTION,
            IssuancePoint.EXPRESS_DESK, IssuancePoint.CASHIER
        ]:
            return self.token_number
        # Fallback — show own number
        return self.token_number


# ── Sequence counters ─────────────────────────────────────────────────────────
class DailyTokenSequence(models.Model):
    """
    Two uses:
    1. Entry ticket sequence — unique_key = tier code  (S, E, FT, V)
    2. Dept token sequence   — unique_key = service_type code
    Shared across gate + cashier for entry tickets (preventing duplicate numbers).
    """
    date       = models.DateField(default=timezone.now)
    unique_key = models.CharField(max_length=30, default='S')   # tier prefix OR service_type code
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('date', 'unique_key')

    @classmethod
    def next_entry_token(cls, tier: str) -> str:
        """Issue the next entry ticket number for a tier (S-001, FT-001, V-001)."""
        prefix = TIER_PREFIX.get(tier, tier[:2].upper())
        today  = timezone.localdate()
        seq, _ = cls.objects.select_for_update().get_or_create(
            date=today, unique_key=prefix
        )
        seq.last_number += 1
        seq.save()
        return f"{prefix}-{seq.last_number:03d}"

    @classmethod
    def next_dept_token(cls, service_type: str) -> str:
        """Issue the next department queue token (RETINA-001, LAB-001, etc.)."""
        # Use the ServiceType value (up to 8 chars) as prefix
        prefix_map = {
            'RECEPTIONIST': 'REG',
            'CASHIER':   'CASH',
            'PARAMETERS':'PARAM',
            'PARAMS_VIP':'PVIP',
            'GENERAL':   'GEN',
            'RETINA':    'RET',
            'GLAUCOMA':  'GLAUC',
            'CATARACT':  'CAT',
            'PEDIATRIC': 'PEDS',
            'NEURO':     'NEURO',
            'OCULOPLASTY':'OCUP',
            'CORNEA':    'CORN',
            'REFRACTION':'REF',
            'INVEST':    'INV',
            'LAB':       'LAB',
            'PHARMACY':  'RX',
            'OPTICAL':   'OPT',
            'INSUR_CONSULT': 'INS',
            'COUNSEL':   'COUNS',
            'ADMISSION': 'ADM',
            'THEATRE':   'THTR',
            'BILLING':   'BILL',
        }
        prefix = prefix_map.get(service_type, service_type[:5].upper())
        key    = f"DEPT_{service_type}"
        today  = timezone.localdate()
        seq, _ = cls.objects.select_for_update().get_or_create(
            date=today, unique_key=key
        )
        seq.last_number += 1
        seq.save()
        return f"{prefix}-{seq.last_number:03d}"
