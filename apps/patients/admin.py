from django.contrib import admin
from .models import Patient, NextOfKin, MedicalHistory, Visit, InsuranceInfo, PatientProblem


class NextOfKinInline(admin.TabularInline):
    model = NextOfKin
    extra = 1


class InsuranceInline(admin.TabularInline):
    model = InsuranceInfo
    extra = 0


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ['patient_id', 'full_name', 'gender', 'age', 'phone_number', 'registration_date', 'is_active']
    list_filter = ['gender', 'is_active', 'blood_group']
    search_fields = ['patient_id', 'first_name', 'last_name', 'phone_number']
    readonly_fields = ['patient_id', 'registration_date', 'age']
    inlines = [NextOfKinInline, InsuranceInline]
    ordering = ['-registration_date']


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ['visit_number', 'patient', 'department', 'visit_type', 'status', 'visit_date']
    list_filter = ['status', 'visit_type', 'department']
    search_fields = ['visit_number', 'patient__first_name', 'patient__last_name', 'patient__patient_id']
    readonly_fields = ['visit_number']


@admin.register(PatientProblem)
class PatientProblemAdmin(admin.ModelAdmin):
    list_display = ['patient', 'problem', 'icd10_code', 'status', 'onset_date', 'recorded_by']
    list_filter = ['status']
    search_fields = ['patient__first_name', 'patient__last_name', 'patient__patient_id', 'problem', 'icd10_code']
