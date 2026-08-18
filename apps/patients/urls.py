from django.urls import path
from . import views

app_name = 'patients'

urlpatterns = [
    path('', views.patient_list_view, name='list'),
    path('register/', views.patient_register_view, name='register'),
    path('register/checkin-existing/', views.checkin_existing_patient, name='checkin_existing'),
    path('register/ajax/', views.patient_register_ajax, name='register_ajax'),
    path('register/emergency/', views.emergency_register_view, name='emergency_register'),
    path('search/', views.patient_search_api, name='search'),
    path('duplicate-check/', views.duplicate_check_api, name='duplicate_check'),

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
    path('visit/<str:visit_number>/change-tier/', views.change_visit_tier_view, name='change_visit_tier'),
    path('visit/<str:visit_number>/vip-slip/', views.vip_slip_view, name='vip_slip'),
    path('visit/<str:visit_number>/tier-log/', views.tier_change_log_view, name='tier_change_log'),
    path('<str:patient_id>/', views.patient_detail_view, name='detail'),
    path('<str:patient_id>/edit/', views.patient_edit_view, name='edit'),
    path('<str:patient_id>/history/', views.medical_history_view, name='history'),
    path('<str:patient_id>/qr/', views.qr_generate_view, name='qr_generate'),
    path('<str:patient_id>/card/', views.registration_card_view, name='registration_card'),

    # ── Chronic medications ─────────────────────────────────────────────────
    path('<str:patient_id>/medications/add/', views.medication_add_view, name='medication_add'),
    path('<str:patient_id>/medications/<int:med_id>/toggle/', views.medication_toggle_view, name='medication_toggle'),

    # ── Allergies ───────────────────────────────────────────────────────────
    path('<str:patient_id>/allergies/add/', views.allergy_add_view, name='allergy_add'),
    path('<str:patient_id>/allergies/<int:allergy_id>/delete/', views.allergy_delete_view, name='allergy_delete'),

    # ── Insurance ───────────────────────────────────────────────────────────
    path('<str:patient_id>/insurance/add/', views.insurance_add_view, name='insurance_add'),
    path('<str:patient_id>/insurance/<uuid:ins_id>/deactivate/', views.insurance_deactivate_view, name='insurance_deactivate'),

    # ── Problem List ─────────────────────────────────────────────────────────
    path('<str:patient_id>/problems/add/', views.problem_add_view, name='problem_add'),
    path('<str:patient_id>/problems/<int:problem_id>/update-status/', views.problem_update_status_view, name='problem_update_status'),
    path('<str:patient_id>/problems/<int:problem_id>/delete/', views.problem_delete_view, name='problem_delete'),

    # ── Informed Consent (JCI PFR.5) ────────────────────────────────────────
    path('<str:patient_id>/consents/', views.consent_list_view, name='consent_list'),
    path('<str:patient_id>/consents/new/', views.consent_create_view, name='consent_create'),
    path('<str:patient_id>/consents/<uuid:consent_id>/', views.consent_detail_view, name='consent_detail'),
    path('<str:patient_id>/consents/<uuid:consent_id>/print/', views.consent_print_view, name='consent_print'),

    # ── Documents / Scanned Records ─────────────────────────────────────────
    path('<str:patient_id>/documents/upload/', views.document_upload_view, name='document_upload'),
    path('<str:patient_id>/documents/<uuid:doc_id>/delete/', views.document_delete_view, name='document_delete'),

    # ── Medical Records Officer tools ────────────────────────────────────────
    path('records/releases/', views.record_release_list_view, name='record_release_list'),
    path('records/releases/new/', views.record_release_create_view, name='record_release_create'),
    path('records/releases/<int:pk>/update/', views.record_release_update_view, name='record_release_update'),
    path('records/deficiency/', views.chart_deficiency_view, name='chart_deficiency'),
    path('records/access-log/', views.access_audit_view, name='access_audit'),
    path('records/duplicates/', views.duplicate_detection_view, name='duplicate_detection'),
    path('prereg/manage/', views.prereg_management_view, name='prereg_management'),
]
