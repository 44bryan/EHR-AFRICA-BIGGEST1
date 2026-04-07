"""
Outreach Department — community eye camps, school screenings, mobile clinics.
"""
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimeStampedModel


class OutreachType(models.TextChoices):
    EYE_CAMP         = 'EYE_CAMP',         _('Eye Camp (Community)')
    SCHOOL_SCREENING = 'SCHOOL_SCREENING',  _('School Screening')
    MOBILE_CLINIC    = 'MOBILE_CLINIC',     _('Mobile Eye Clinic')
    CORPORATE        = 'CORPORATE',         _('Corporate Health Screening')
    VILLAGE_VISIT    = 'VILLAGE_VISIT',     _('Village / Rural Visit')
    CHURCH_CAMP      = 'CHURCH_CAMP',       _('Church / Faith Community Camp')
    OTHER            = 'OTHER',             _('Other')


class OutreachStatus(models.TextChoices):
    PLANNED      = 'PLANNED',     _('Planned')
    IN_PROGRESS  = 'IN_PROGRESS', _('In Progress')
    COMPLETED    = 'COMPLETED',   _('Completed')
    CANCELLED    = 'CANCELLED',   _('Cancelled')
    POSTPONED    = 'POSTPONED',   _('Postponed')


class OutreachActivity(TimeStampedModel):
    """A single outreach event (camp, school visit, mobile clinic etc.)."""
    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title         = models.CharField(max_length=200)
    activity_type = models.CharField(max_length=30, choices=OutreachType.choices,
                                     default=OutreachType.EYE_CAMP)
    status        = models.CharField(max_length=20, choices=OutreachStatus.choices,
                                     default=OutreachStatus.PLANNED)

    # Location
    location_name   = models.CharField(max_length=200, help_text='School, village, company name')
    region          = models.CharField(max_length=100, blank=True, help_text='e.g. Centre Region')
    town            = models.CharField(max_length=100, blank=True)
    gps_coordinates = models.CharField(max_length=60, blank=True)

    # Schedule
    activity_date = models.DateField()
    end_date      = models.DateField(null=True, blank=True, help_text='For multi-day activities')
    start_time    = models.TimeField(null=True, blank=True)
    end_time      = models.TimeField(null=True, blank=True)

    # Team
    team_leader = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='led_outreach', limit_choices_to={'is_active': True},
    )
    team_members = models.ManyToManyField(
        'accounts.User', blank=True, related_name='outreach_activities',
    )
    vehicle_details = models.CharField(max_length=200, blank=True)
    equipment_notes = models.TextField(blank=True)

    # Partner / Sponsor
    partner_org    = models.CharField(max_length=200, blank=True)
    sponsor        = models.CharField(max_length=200, blank=True)
    sponsor_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Notes
    objectives      = models.TextField(blank=True)
    notes           = models.TextField(blank=True)
    challenges      = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)

    class Meta:
        ordering = ['-activity_date']
        verbose_name = 'Outreach Activity'
        verbose_name_plural = 'Outreach Activities'

    def __str__(self):
        return f'{self.title} — {self.activity_date}'

    @property
    def total_screened(self):
        return sum(r.total_screened for r in self.records.all())

    @property
    def total_treated(self):
        return sum(r.total_treated for r in self.records.all())

    @property
    def total_referred(self):
        return sum(r.total_referred for r in self.records.all())

    @property
    def total_surgeries_performed(self):
        return sum(r.surgeries_performed for r in self.records.all())


class OutreachRecord(TimeStampedModel):
    """Daily/session statistics record for an outreach activity."""
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity    = models.ForeignKey(OutreachActivity, on_delete=models.CASCADE,
                                    related_name='records')
    record_date = models.DateField()
    recorded_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='outreach_records',
    )

    # Head counts
    total_screened    = models.PositiveIntegerField(default=0)
    male_screened     = models.PositiveIntegerField(default=0)
    female_screened   = models.PositiveIntegerField(default=0)
    children_screened = models.PositiveIntegerField(default=0, help_text='Under 18')
    elderly_screened  = models.PositiveIntegerField(default=0, help_text='60+')

    # Clinical findings
    normal_vision        = models.PositiveIntegerField(default=0)
    refractive_errors    = models.PositiveIntegerField(default=0)
    cataract             = models.PositiveIntegerField(default=0)
    glaucoma_suspects    = models.PositiveIntegerField(default=0)
    diabetic_retinopathy = models.PositiveIntegerField(default=0)
    pterygium            = models.PositiveIntegerField(default=0)
    trachoma             = models.PositiveIntegerField(default=0)
    corneal_opacity      = models.PositiveIntegerField(default=0)
    other_pathology      = models.PositiveIntegerField(default=0)

    # Interventions
    glasses_dispensed   = models.PositiveIntegerField(default=0)
    medications_given   = models.PositiveIntegerField(default=0)
    surgeries_performed = models.PositiveIntegerField(default=0)
    total_treated       = models.PositiveIntegerField(default=0)
    total_referred      = models.PositiveIntegerField(default=0,
                          help_text='Referred to hospital for further care')

    # Referral breakdown
    referred_cataract = models.PositiveIntegerField(default=0)
    referred_glaucoma = models.PositiveIntegerField(default=0)
    referred_retina   = models.PositiveIntegerField(default=0)
    referred_other    = models.PositiveIntegerField(default=0)

    # Costs (FCFA)
    drugs_cost     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    transport_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_cost     = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['record_date']
        unique_together = [['activity', 'record_date']]

    def __str__(self):
        return f'{self.activity.title} — {self.record_date} ({self.total_screened} screened)'

    @property
    def total_cost(self):
        return self.drugs_cost + self.transport_cost + self.other_cost
