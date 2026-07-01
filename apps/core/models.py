"""
Abstract base models shared across all apps.
All models in this EHR system inherit from these.
"""
import uuid
from django.db import models
from django.utils import timezone


class BackupLog(models.Model):
    """Tracks every automated and manual database backup."""

    class Status(models.TextChoices):
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'
        RUNNING = 'RUNNING', 'Running'

    class TriggerSource(models.TextChoices):
        CELERY = 'CELERY', 'Automated (Celery)'
        MANUAL = 'MANUAL', 'Manual (Admin)'
        CLI = 'CLI', 'CLI (manage.py)'

    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    filename = models.CharField(max_length=255, blank=True)
    output_path = models.CharField(max_length=500, blank=True)
    size_mb = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    trigger = models.CharField(max_length=10, choices=TriggerSource.choices, default=TriggerSource.CELERY)
    duration_seconds = models.FloatField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    # Checksums / verification
    copied_to_external = models.BooleanField(default=False)
    external_path = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Backup Log'
        verbose_name_plural = 'Backup Logs'

    def __str__(self):
        return f"{self.filename} — {self.status} ({self.created_at:%Y-%m-%d %H:%M})"


class TimeStampedModel(models.Model):
    """
    Abstract base model providing self-managed created_at/updated_at
    timestamps and soft-delete support.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at'])


class ActiveManager(models.Manager):
    """Returns only non-deleted records."""
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class AuditModel(TimeStampedModel):
    """
    Extends TimeStampedModel with created_by/updated_by tracking.
    Use this for all clinical records.
    """
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    updated_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )

    class Meta:
        abstract = True
