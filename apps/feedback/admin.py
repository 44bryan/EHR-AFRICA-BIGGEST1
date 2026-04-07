from django.contrib import admin
from .models import PatientFeedback


@admin.register(PatientFeedback)
class PatientFeedbackAdmin(admin.ModelAdmin):
    list_display = ['submitter_name', 'feedback_type', 'overall_rating', 'nps_score', 'status', 'created_at']
    list_filter = ['feedback_type', 'status', 'created_at']
    search_fields = ['patient__first_name', 'patient__last_name', 'anonymous_name', 'message']
    date_hierarchy = 'created_at'
