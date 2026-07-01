"""
API Token model for Power BI and external integrations.
"""
import secrets
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel


class APIToken(TimeStampedModel):
    """
    Bearer token for external API access (Power BI, mobile apps, etc.)
    Generate tokens in Django Admin or management command.
    """
    name = models.CharField(max_length=100, help_text="Descriptive name, e.g. 'Power BI Dashboard'")
    token = models.CharField(max_length=64, unique=True, editable=False)
    is_active = models.BooleanField(default=True)
    last_used = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Leave blank for no expiry")
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='api_tokens'
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'API Token'

    def __str__(self):
        return f"{self.name} ({'active' if self.is_active else 'inactive'})"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_hex(32)
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        if not self.is_active:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True

    def touch(self):
        APIToken.objects.filter(pk=self.pk).update(last_used=timezone.now())
