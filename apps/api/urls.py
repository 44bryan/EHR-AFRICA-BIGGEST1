from django.urls import path
from . import views
from . import powerbi_views as pbi
from . import fhir_views as fhir

app_name = 'api'

urlpatterns = [
    # Internal HTMX / JS endpoints
    path('dashboard/stats/', views.dashboard_stats_view, name='dashboard_stats'),
    path('patients/search/', views.patient_search_view, name='patient_search'),

    # Power BI REST API
    path('powerbi/', pbi.powerbi_index, name='powerbi_index'),
    path('powerbi/kpi/overview/', pbi.kpi_overview, name='powerbi_kpi_overview'),
    path('powerbi/patients/demographics/', pbi.patient_demographics, name='powerbi_patient_demographics'),
    path('powerbi/patients/visits/daily/', pbi.visits_daily, name='powerbi_visits_daily'),
    path('powerbi/patients/visits/monthly/', pbi.visits_monthly, name='powerbi_visits_monthly'),
    path('powerbi/billing/revenue/monthly/', pbi.revenue_monthly, name='powerbi_revenue_monthly'),
    path('powerbi/billing/financial-summary/', pbi.financial_summary, name='powerbi_financial_summary'),
    path('powerbi/appointments/analytics/', pbi.appointments_analytics, name='powerbi_appointments'),
    path('powerbi/clinical/diagnoses/', pbi.diagnoses_frequency, name='powerbi_diagnoses'),
    path('powerbi/laboratory/analytics/', pbi.lab_analytics, name='powerbi_lab'),
    path('powerbi/pharmacy/analytics/', pbi.pharmacy_analytics, name='powerbi_pharmacy'),
    path('powerbi/staff/performance/', pbi.staff_performance, name='powerbi_staff'),
    path('powerbi/outreach/analytics/', pbi.outreach_analytics, name='powerbi_outreach'),

    # ── FHIR R4 ───────────────────────────────────────────────────────────────
    path('fhir/metadata', fhir.fhir_metadata, name='fhir_metadata'),
    path('fhir/Patient/', fhir.fhir_patient_search, name='fhir_patient_search'),
    path('fhir/Patient/<str:patient_id>/', fhir.fhir_patient_read, name='fhir_patient_read'),
    path('fhir/Encounter/<uuid:consultation_id>/', fhir.fhir_encounter_read, name='fhir_encounter_read'),
    path('fhir/Invoice/<uuid:invoice_id>/', fhir.fhir_invoice_read, name='fhir_invoice_read'),
    path('fhir/Observation/<uuid:visit_id>/', fhir.fhir_observation_list, name='fhir_observation_list'),
]
