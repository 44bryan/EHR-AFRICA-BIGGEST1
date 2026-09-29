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
    timestamps and soft-delete support with mandatory deletion reason.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    deletion_reason = models.TextField(blank=True, default='')

    class Meta:
        abstract = True
        ordering = ['-created_at']

    def soft_delete(self, user=None, reason=''):
        """Soft-delete with mandatory audit trail: who deleted and why."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.deletion_reason = reason or ''
        fields = ['is_deleted', 'deleted_at', 'deleted_by', 'deletion_reason']
        self.save(update_fields=fields)
        # Log to DeletionLog for central audit
        DeletionLog.objects.create(
            content_type=f'{self._meta.app_label}.{self._meta.model_name}',
            object_id=str(self.pk),
            object_repr=str(self)[:200],
            deleted_by=user,
            reason=reason or '',
        )

    def restore(self, user=None):
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.deletion_reason = ''
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'deletion_reason'])


class DeletionLog(models.Model):
    """
    Central audit log for ALL soft-deletes system-wide.
    Immutable — no edits or deletes allowed by any role.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content_type = models.CharField(max_length=100)  # e.g. 'patients.patient'
    object_id = models.CharField(max_length=50)
    object_repr = models.CharField(max_length=200, blank=True)
    deleted_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    reason = models.TextField()
    deleted_at = models.DateTimeField(auto_now_add=True)
    is_restored = models.BooleanField(default=False)
    restored_at = models.DateTimeField(null=True, blank=True)
    restored_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )

    class Meta:
        ordering = ['-deleted_at']
        verbose_name = 'Deletion Log'
        verbose_name_plural = 'Deletion Logs'

    def __str__(self):
        return f'{self.content_type} #{self.object_id} — {self.reason[:60]}'


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
