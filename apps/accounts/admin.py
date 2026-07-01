from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserAuditLog


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['employee_id', 'email', 'full_name', 'role', 'department', 'is_active', 'totp_enabled']
    list_filter = ['role', 'department', 'is_active', 'totp_enabled', 'must_change_password']
    search_fields = ['email', 'first_name', 'last_name', 'employee_id']
    ordering = ['last_name']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('EHR Profile', {
            'fields': (
                'employee_id', 'role', 'department', 'phone_number', 'profile_photo',
            )
        }),
        ('Desk / Unit Assignment', {
            'description': (
                'cashier_station — for Cashier / Billing Officer accounts only.\n'
                'consultation_unit — for Ophthalmologist accounts only.'
            ),
            'fields': ('cashier_station', 'consultation_unit'),
        }),
        ('Security', {
            'fields': (
                'must_change_password', 'last_password_change',
                'totp_enabled', 'totp_secret',
            )
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
