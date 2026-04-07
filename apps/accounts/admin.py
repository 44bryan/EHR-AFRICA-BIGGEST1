from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserAuditLog


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['employee_id', 'email', 'full_name', 'role', 'department', 'is_active']
    list_filter = ['role', 'department', 'is_active']
    search_fields = ['email', 'first_name', 'last_name', 'employee_id']
    ordering = ['last_name']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('EHR Profile', {
            'fields': ('role', 'department', 'phone_number', 'employee_id',
                       'profile_photo', 'must_change_password', 'last_password_change')
        }),
    )


@admin.register(UserAuditLog)
class UserAuditLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'target_model', 'ip_address', 'timestamp']
    list_filter = ['action']
    search_fields = ['user__email', 'target_model']
    readonly_fields = ['user', 'action', 'target_model', 'target_id', 'ip_address', 'user_agent', 'extra_data', 'timestamp']
    ordering = ['-timestamp']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
