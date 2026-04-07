"""
Lightweight JSON API endpoints used by HTMX/JS on the frontend.
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone


@login_required
def dashboard_stats_view(request):
    from apps.patients.models import Patient, Visit
    from apps.appointments.models import Appointment
    from apps.investigations.models import InvestigationOrder
    from apps.laboratory.models import LabOrder

    today = timezone.localdate()
    return JsonResponse({
        'total_patients': Patient.objects.filter(is_active=True).count(),
        'today_visits': Visit.objects.filter(visit_date__date=today).count(),
        'today_appointments': Appointment.objects.filter(
            appointment_date=today, status__in=['SCHEDULED', 'CONFIRMED', 'CHECKED_IN']
        ).count(),
        'pending_investigations': InvestigationOrder.objects.filter(
            status__in=['ORDERED', 'IN_PROGRESS']
        ).count(),
        'pending_labs': LabOrder.objects.filter(
            status__in=['ORDERED', 'SAMPLE_COLLECTED', 'PROCESSING']
        ).count(),
    })


@login_required
def patient_search_view(request):
    from apps.patients.views import patient_search_api
    return patient_search_api(request)
