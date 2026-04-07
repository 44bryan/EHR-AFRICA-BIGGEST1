from django.contrib import admin
from .models import DrugPrescription, DrugPrescriptionItem, OpticalPrescription


class DrugItemInline(admin.TabularInline):
    model = DrugPrescriptionItem
    extra = 1


@admin.register(DrugPrescription)
class DrugPrescriptionAdmin(admin.ModelAdmin):
    list_display = ['patient', 'prescribed_by', 'prescription_date', 'is_dispensed']
    list_filter = ['is_dispensed']
    search_fields = ['patient__first_name', 'patient__patient_id']
    inlines = [DrugItemInline]


@admin.register(OpticalPrescription)
class OpticalPrescriptionAdmin(admin.ModelAdmin):
    list_display = ['patient', 'prescribed_by', 'prescription_type', 'prescription_date', 'is_dispensed']
    list_filter = ['prescription_type', 'is_dispensed']
    search_fields = ['patient__first_name', 'patient__patient_id']
