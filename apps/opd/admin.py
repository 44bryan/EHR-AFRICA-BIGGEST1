from django.contrib import admin
from .models import OPDVisit


@admin.register(OPDVisit)
class OPDVisitAdmin(admin.ModelAdmin):
    list_display = ['visit_number', 'patient', 'department', 'status', 'visit_date', 'attending_doctor', 'total_wait_minutes']
    list_filter = ['status', 'visit_date', 'department', 'payment_status']
    search_fields = ['visit_number', 'patient__first_name', 'patient__last_name']
    date_hierarchy = 'visit_date'
