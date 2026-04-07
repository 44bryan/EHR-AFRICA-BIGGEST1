from django.contrib import admin
from .models import QueueToken, ServiceCounter, DailyTokenSequence


@admin.register(ServiceCounter)
class ServiceCounterAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'service_type', 'serves_tiers', 'is_active', 'staff_assigned']
    list_filter = ['service_type', 'is_active']


@admin.register(QueueToken)
class QueueTokenAdmin(admin.ModelAdmin):
    list_display = ['token_number', 'service_type', 'service_tier', 'status',
                    'display_name', 'issuance_point', 'issued_at', 'wait_time_minutes']
    list_filter = ['service_type', 'service_tier', 'status', 'issuance_point']
    search_fields = ['token_number', 'patient_name']
    date_hierarchy = 'issued_at'


@admin.register(DailyTokenSequence)
class DailyTokenSequenceAdmin(admin.ModelAdmin):
    list_display = ['date', 'unique_key', 'last_number']
