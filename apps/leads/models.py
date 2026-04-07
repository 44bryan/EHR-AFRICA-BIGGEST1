"""
Lead Management System
Patient leads, follow-up pipeline, conversion tracking.
"""
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel, AuditModel


class LeadSource(models.TextChoices):
    WALK_IN = 'WALK_IN', 'Walk-In'
    REFERRAL = 'REFERRAL', 'Doctor Referral'
    SOCIAL_MEDIA = 'SOCIAL', 'Social Media'
    WEBSITE = 'WEBSITE', 'Website'
    PHONE = 'PHONE', 'Phone Inquiry'
    WHATSAPP = 'WHATSAPP', 'WhatsApp'
    EMAIL = 'EMAIL', 'Email'
    COMMUNITY = 'COMMUNITY', 'Community Outreach'
    OTHER = 'OTHER', 'Other'


class LeadStatus(models.TextChoices):
    NEW = 'NEW', 'New'
    CONTACTED = 'CONTACTED', 'Contacted'
    INTERESTED = 'INTERESTED', 'Interested'
    APPOINTMENT_BOOKED = 'APPT', 'Appointment Booked'
    CONVERTED = 'CONVERTED', 'Converted to Patient'
    NOT_INTERESTED = 'NOT_INT', 'Not Interested'
    LOST = 'LOST', 'Lost'


class Lead(AuditModel):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    age = models.PositiveSmallIntegerField(null=True, blank=True)
    source = models.CharField(max_length=20, choices=LeadSource.choices)
    status = models.CharField(max_length=20, choices=LeadStatus.choices, default=LeadStatus.NEW)
    inquiry = models.TextField(help_text='What is the patient inquiring about?')
    assigned_to = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='assigned_leads'
    )
    converted_patient = models.ForeignKey(
        'patients.Patient', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='lead_source'
    )
    converted_date = models.DateField(null=True, blank=True)
    next_follow_up = models.DateField(null=True, blank=True)
    priority = models.PositiveSmallIntegerField(default=0, choices=[
        (0, 'Normal'), (1, 'High'), (2, 'Urgent')
    ])

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.get_status_display()})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def convert(self, patient):
        self.status = LeadStatus.CONVERTED
        self.converted_patient = patient
        self.converted_date = timezone.localdate()
        self.save()


class LeadActivity(TimeStampedModel):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=30, choices=[
        ('CALL', 'Phone Call'),
        ('SMS', 'SMS'),
        ('WHATSAPP', 'WhatsApp'),
        ('EMAIL', 'Email'),
        ('MEETING', 'Meeting'),
        ('NOTE', 'Note'),
    ])
    summary = models.TextField()
    outcome = models.TextField(blank=True)
    next_action = models.TextField(blank=True)
    performed_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='lead_activities'
    )

    class Meta:
        ordering = ['-created_at']
