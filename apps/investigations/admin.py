from django.contrib import admin
from .models import InvestigationType, InvestigationOrder, InvestigationResult


@admin.register(InvestigationType)
class InvestigationTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'category', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['name', 'code']


@admin.register(InvestigationOrder)
class InvestigationOrderAdmin(admin.ModelAdmin):
    list_display = ['patient', 'investigation_type', 'urgency', 'status', 'created_at']
    list_filter = ['status', 'urgency', 'investigation_type']
    search_fields = ['patient__first_name', 'patient__last_name', 'patient__patient_id']
