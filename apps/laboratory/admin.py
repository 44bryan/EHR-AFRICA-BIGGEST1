from django.contrib import admin
from .models import LabTestType, LabOrder, LabOrderItem, LabResult


@admin.register(LabTestType)
class LabTestTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'category', 'turnaround_hours', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['name', 'code']


@admin.register(LabOrder)
class LabOrderAdmin(admin.ModelAdmin):
    list_display = ['patient', 'ordered_by', 'urgency', 'status', 'created_at']
    list_filter = ['status', 'urgency']
    search_fields = ['patient__first_name', 'patient__patient_id']
