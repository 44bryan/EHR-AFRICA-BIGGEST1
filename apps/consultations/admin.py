from django.contrib import admin
from .models import Consultation, Diagnosis, ConsultationDiagnosis, ConsultationNote


@admin.register(Diagnosis)
class DiagnosisAdmin(admin.ModelAdmin):
    list_display = ['icd10_code', 'description', 'is_ophthalmic', 'is_active']
    list_filter = ['is_ophthalmic', 'is_active']
    search_fields = ['icd10_code', 'description']


class ConsultationDiagnosisInline(admin.TabularInline):
    model = ConsultationDiagnosis
    extra = 1


class ConsultationNoteInline(admin.TabularInline):
    model = ConsultationNote
    extra = 0
    readonly_fields = ['created_by', 'created_at']


@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = ['patient', 'department', 'consulting_doctor', 'status', 'consultation_date']
    list_filter = ['status', 'department']
    search_fields = ['patient__first_name', 'patient__last_name', 'patient__patient_id']
    readonly_fields = ['consultation_date', 'created_by', 'updated_by']
    inlines = [ConsultationDiagnosisInline, ConsultationNoteInline]
