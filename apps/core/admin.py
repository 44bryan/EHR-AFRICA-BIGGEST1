from django.contrib import admin
from .models import BackupLog


@admin.register(BackupLog)
class BackupLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'filename', 'size_mb', 'status', 'trigger', 'duration_seconds', 'copied_to_external')
    list_filter = ('status', 'trigger', 'copied_to_external')
    readonly_fields = ('created_at', 'filename', 'output_path', 'size_mb', 'status',
                       'trigger', 'duration_seconds', 'error_message', 'copied_to_external', 'external_path')
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
