"""
In-app notification system.
Notifications are created by clinical events (billing, lab results, pharmacy, etc.)
and displayed in the topbar bell for the targeted user.
"""
from django.db import models
from django.utils import timezone


class NotificationType(models.TextChoices):
    LAB_RESULT = 'LAB_RESULT', 'Lab Result Ready'
    INVESTIGATION = 'INVESTIGATION', 'Investigation Result'
    PRESCRIPTION = 'PRESCRIPTION', 'Prescription Waiting'
    BILLING = 'BILLING', 'Billing / Payment'
    APPOINTMENT = 'APPOINTMENT', 'Appointment Reminder'
    DISCHARGE = 'DISCHARGE', 'Patient Discharged'
    LOW_STOCK = 'LOW_STOCK', 'Low Drug Stock'
    SYSTEM = 'SYSTEM', 'System Alert'
    GENERAL = 'GENERAL', 'General'


class NotificationPriority(models.TextChoices):
    LOW = 'LOW', 'Low'
    NORMAL = 'NORMAL', 'Normal'
    HIGH = 'HIGH', 'High'
    URGENT = 'URGENT', 'Urgent'


class Notification(models.Model):
    """Single in-app notification for a user."""
    recipient = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='notifications'
    )
    notification_type = models.CharField(
        max_length=30, choices=NotificationType.choices, default=NotificationType.GENERAL
    )
    priority = models.CharField(
        max_length=10, choices=NotificationPriority.choices, default=NotificationPriority.NORMAL
    )
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    link = models.CharField(max_length=500, blank=True, help_text='Optional URL to navigate to on click')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
        ]

    def __str__(self):
        return f"[{self.notification_type}] {self.title} → {self.recipient.full_name}"

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])
