"""
In-app notification system.
Notifications are created by clinical events (billing, lab results, pharmacy, etc.)
and displayed in the topbar bell for the targeted user.
"""
from django.db import models
from django.utils import timezone


class MessageChannel(models.TextChoices):
    SMS       = 'SMS',       'SMS'
    WHATSAPP  = 'WHATSAPP',  'WhatsApp'
    BOTH      = 'BOTH',      'Both'


class MessageType(models.TextChoices):
    APPOINTMENT_REMINDER   = 'APPOINTMENT_REMINDER',   'Appointment Reminder'
    RESULTS_READY          = 'RESULTS_READY',          'Results Ready'
    DISCHARGE_INSTRUCTIONS = 'DISCHARGE_INSTRUCTIONS', 'Discharge Instructions'
    PRESCRIPTION_READY     = 'PRESCRIPTION_READY',     'Prescription Ready'
    BALANCE_DUE            = 'BALANCE_DUE',            'Balance / Payment Due'
    FOLLOW_UP              = 'FOLLOW_UP',              'Follow-up Reminder'
    CUSTOM                 = 'CUSTOM',                 'Custom Message'


class MessageStatus(models.TextChoices):
    PENDING   = 'PENDING',   'Pending'
    SENT      = 'SENT',      'Sent'
    DELIVERED = 'DELIVERED', 'Delivered'
    FAILED    = 'FAILED',    'Failed'


class PatientMessage(models.Model):
    """SMS or WhatsApp message sent to a patient."""
    import uuid as _uuid
    id               = models.UUIDField(primary_key=True, default=_uuid.uuid4, editable=False)
    created_at       = models.DateTimeField(auto_now_add=True)
    channel          = models.CharField(max_length=10, choices=MessageChannel.choices[:2],
                                         default=MessageChannel.SMS)
    message_type     = models.CharField(max_length=30, choices=MessageType.choices,
                                         default=MessageType.CUSTOM)
    recipient_number = models.CharField(max_length=20)
    patient          = models.ForeignKey('patients.Patient', on_delete=models.SET_NULL,
                                          null=True, blank=True, related_name='sms_messages')
    sent_by          = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                          null=True, blank=True, related_name='patient_messages_sent')
    body             = models.TextField()
    status           = models.CharField(max_length=10, choices=MessageStatus.choices,
                                         default=MessageStatus.PENDING)
    provider_ref     = models.CharField(max_length=100, blank=True)
    error_message    = models.TextField(blank=True)
    sent_at          = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Patient Message'
        verbose_name_plural = 'Patient Messages (SMS/WhatsApp)'

    def __str__(self):
        name = self.patient.full_name if self.patient else self.recipient_number
        return f'[{self.channel}] {name} — {self.get_status_display()}'


class MessageTemplate(models.Model):
    """Reusable SMS/WhatsApp message templates."""
    import uuid as _uuid
    id           = models.UUIDField(primary_key=True, default=_uuid.uuid4, editable=False)
    created_at   = models.DateTimeField(auto_now_add=True)
    name         = models.CharField(max_length=100, unique=True)
    channel      = models.CharField(max_length=10, choices=MessageChannel.choices,
                                     default=MessageChannel.SMS)
    message_type = models.CharField(max_length=30, choices=MessageType.choices,
                                     default=MessageType.CUSTOM)
    body         = models.TextField(
        help_text='Use {{ patient_name }}, {{ appointment_date }}, {{ hospital_name }} as placeholders'
    )
    is_active    = models.BooleanField(default=True)
    created_by   = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name='+')

    class Meta:
        ordering = ['name']
        verbose_name = 'Message Template'

    def __str__(self):
        return f'{self.name} [{self.channel}]'

    def render(self, context: dict) -> str:
        """Simple template rendering with {{ key }} substitution."""
        body = self.body
        for key, value in context.items():
            body = body.replace('{{ ' + key + ' }}', str(value))
            body = body.replace('{{' + key + '}}', str(value))
        return body


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
