from django.contrib import admin
from .models import Appointment, DoctorSchedule


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['appointment_number', 'patient', 'department', 'doctor', 'appointment_date', 'status']
    list_filter = ['status', 'department', 'appointment_type']
    search_fields = ['appointment_number', 'patient__first_name', 'patient__patient_id']
    readonly_fields = ['appointment_number']


@admin.register(DoctorSchedule)
class DoctorScheduleAdmin(admin.ModelAdmin):
    list_display = ['doctor', 'department', 'get_day_of_week_display', 'start_time', 'end_time', 'is_active']
    list_filter = ['is_active', 'department']
