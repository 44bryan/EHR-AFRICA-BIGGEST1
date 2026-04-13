from django.urls import path
from . import views

app_name = 'patients'

urlpatterns = [
    path('', views.patient_list_view, name='list'),
    path('register/', views.patient_register_view, name='register'),
    path('register/ajax/', views.patient_register_ajax, name='register_ajax'),
    path('search/', views.patient_search_api, name='search'),

    # ── Public QR / pre-registration (must come BEFORE <str:patient_id>/) ──
    path('checkin/', views.qr_checkin_view, name='qr_checkin'),
    path('prereg/', views.preregistration_view, name='prereg'),
    path('prereg/<str:code>/slip/', views.preregistration_slip_view, name='prereg_slip'),
    path('prereg/lookup/', views.preregistration_lookup_view, name='prereg_lookup'),

    # ── Patient-specific routes ─────────────────────────────────────────────
    path('visit/<str:visit_number>/', views.visit_detail_view, name='visit_detail'),
    path('visit/<str:visit_number>/triage/', views.triage_view, name='triage'),
    path('<str:patient_id>/triage-start/', views.triage_start_view, name='triage_start'),
    path('visit/<str:visit_number>/discharge/', views.discharge_view, name='discharge'),
    path('<str:patient_id>/', views.patient_detail_view, name='detail'),
    path('<str:patient_id>/edit/', views.patient_edit_view, name='edit'),
    path('<str:patient_id>/history/', views.medical_history_view, name='history'),
    path('<str:patient_id>/qr/', views.qr_generate_view, name='qr_generate'),
]
