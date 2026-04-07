"""
Feedback Module
Patient satisfaction surveys, NPS scores, complaint management.
"""
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel, AuditModel


class FeedbackType(models.TextChoices):
    SATISFACTION = 'SATISFACTION', 'Satisfaction Survey'
    NPS = 'NPS', 'Net Promoter Score'
    COMPLAINT = 'COMPLAINT', 'Complaint'
    COMPLIMENT = 'COMPLIMENT', 'Compliment'
    SUGGESTION = 'SUGGESTION', 'Suggestion'


class FeedbackStatus(models.TextChoices):
    NEW = 'NEW', 'New'
    ACKNOWLEDGED = 'ACK', 'Acknowledged'
    INVESTIGATING = 'INVEST', 'Under Investigation'
    RESOLVED = 'RESOLVED', 'Resolved'
    CLOSED = 'CLOSED', 'Closed'


class PatientFeedback(AuditModel):
    patient = models.ForeignKey(
        'patients.Patient', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='feedbacks'
    )
    anonymous_name = models.CharField(max_length=200, blank=True)
    feedback_type = models.CharField(max_length=20, choices=FeedbackType.choices)
    department = models.ForeignKey(
        'departments.Department', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='feedbacks'
    )
    visit_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=FeedbackStatus.choices, default=FeedbackStatus.NEW)

    # Ratings (1-5 scale)
    overall_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    wait_time_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    staff_courtesy_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    cleanliness_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    doctor_rating = models.PositiveSmallIntegerField(null=True, blank=True)

    # NPS (0-10)
    nps_score = models.PositiveSmallIntegerField(null=True, blank=True)

    message = models.TextField()
    resolution = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='resolved_feedbacks'
    )
    resolved_date = models.DateField(null=True, blank=True)
    # ── Escalation matrix ─────────────────────────────────────────────────
    escalated      = models.BooleanField(default=False)
    escalated_to   = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='escalated_feedbacks'
    )
    escalated_at   = models.DateTimeField(null=True, blank=True)
    escalation_note = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        name = self.patient.full_name if self.patient else self.anonymous_name or 'Anonymous'
        return f"{self.get_feedback_type_display()} from {name}"

    @property
    def nps_category(self):
        if self.nps_score is None:
            return None
        if self.nps_score >= 9:
            return 'Promoter'
        elif self.nps_score >= 7:
            return 'Passive'
        return 'Detractor'

    @property
    def submitter_name(self):
        if self.patient:
            return self.patient.full_name
        return self.anonymous_name or 'Anonymous'
