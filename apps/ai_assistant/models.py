"""
AI Assistant — Claude-powered clinical decision support.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import AuditModel, TimeStampedModel


class ContextType(models.TextChoices):
    GENERAL = 'GENERAL', _('General Query')
    CLINICAL_DECISION = 'CLINICAL_DECISION', _('Clinical Decision Support')
    DIFFERENTIAL_DX = 'DIFFERENTIAL_DX', _('Differential Diagnosis')
    DRUG_CHECK = 'DRUG_CHECK', _('Drug Information / Interaction Check')
    GUIDELINE = 'GUIDELINE', _('Clinical Guidelines')
    REPORT_ASSIST = 'REPORT_ASSIST', _('Report Writing Assistance')
    # Clinical AI Support — answers based on system/hospital/guideline knowledge only.
    # Does NOT inject patient data — intended for management, CEO, and knowledge queries.
    SYSTEM_KNOWLEDGE = 'SYSTEM_KNOWLEDGE', _('Clinical AI Support — Hospital & System Knowledge')


class AIConversation(AuditModel):
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='ai_conversations')
    patient = models.ForeignKey(
        'patients.Patient',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_conversations',
    )
    consultation = models.ForeignKey(
        'consultations.Consultation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=200, blank=True)
    context_type = models.CharField(max_length=25, choices=ContextType.choices, default=ContextType.GENERAL)
    is_active = models.BooleanField(default=True)
    # Store the full message history for the Claude API
    system_prompt = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'AI Conversation'

    def __str__(self):
        return f"AI Chat — {self.user.full_name} [{self.created_at:%d/%m/%Y %H:%M}]"

    @property
    def message_count(self):
        return self.messages.count()


class AIMessage(TimeStampedModel):
    class Role(models.TextChoices):
        USER = 'user', _('User')
        ASSISTANT = 'assistant', _('Assistant')

    conversation = models.ForeignKey(AIConversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    tokens_used = models.PositiveIntegerField(null=True, blank=True)
    model_used = models.CharField(max_length=50, default='claude-sonnet-4-6')
    response_time_ms = models.PositiveIntegerField(null=True, blank=True)
    is_flagged = models.BooleanField(default=False)
    flag_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'AI Message'

    def __str__(self):
        return f"[{self.role}] {self.content[:80]}..."
