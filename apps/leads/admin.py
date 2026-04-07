from django.contrib import admin
from .models import Lead, LeadActivity


class LeadActivityInline(admin.TabularInline):
    model = LeadActivity
    extra = 0
    readonly_fields = ['created_at']


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'phone', 'source', 'status', 'assigned_to', 'next_follow_up', 'created_at']
    list_filter = ['status', 'source', 'priority']
    search_fields = ['first_name', 'last_name', 'phone', 'email']
    inlines = [LeadActivityInline]
