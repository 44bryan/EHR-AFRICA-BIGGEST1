from django.contrib import admin
from .models import Department


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'head_of_department', 'location', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'code']
    actions = ['activate_departments', 'deactivate_departments']

    def activate_departments(self, request, queryset):
        queryset.update(is_active=True)
    activate_departments.short_description = 'Activate selected departments'

    def deactivate_departments(self, request, queryset):
        queryset.update(is_active=False)
    deactivate_departments.short_description = 'Deactivate selected departments'
