from django.urls import path
from . import views

app_name = 'investigations'

urlpatterns = [
    path('', views.investigation_list_view, name='list'),
    path('workstation/', views.investigation_workstation_view, name='workstation'),
    path('order/<uuid:consultation_pk>/', views.investigation_order_view, name='order'),
    path('multi-order/<uuid:consultation_pk>/', views.multi_exam_order_view, name='multi_order'),
    path('<uuid:pk>/', views.investigation_detail_view, name='detail'),
    path('<uuid:pk>/print-slip/', views.print_request_slip_view, name='print_slip'),
    path('<uuid:pk>/result/', views.add_result_view, name='add_result'),
    path('<uuid:pk>/structured-result/', views.structured_result_view, name='structured_result'),
    path('combined-result/<str:patient_id>/', views.combined_structured_result_view, name='combined_result'),
    path('<uuid:pk>/verify/', views.verify_result_view, name='verify'),
    path('<uuid:pk>/cancel/', views.cancel_investigation_order, name='cancel'),
    path('<uuid:pk>/start/', views.start_investigation_view, name='start'),
    path('<uuid:pk>/check-in/', views.check_in_view, name='check_in'),
    path('<uuid:pk>/prepare/', views.prepare_patient_view, name='prepare'),
    path('bulk-check-in/', views.bulk_check_in_view, name='bulk_check_in'),
    path('bulk-start/', views.bulk_start_view, name='bulk_start'),

    # ── Acquisition Workflow ───────────────────────────────────────────────────
    path('<uuid:pk>/complete-acquisition/', views.complete_acquisition_view, name='complete_acquisition'),
    path('<uuid:pk>/repeat-acquisition/', views.repeat_acquisition_view, name='repeat_acquisition'),
    path('<uuid:pk>/override-quality/', views.override_quality_view, name='override_quality'),

    # ── Result Management ──────────────────────────────────────────────────────
    path('<uuid:pk>/acknowledge/', views.acknowledge_result_view, name='acknowledge'),
    path('<uuid:pk>/amend/', views.amend_result_view, name='amend'),
    path('unacknowledged/', views.unacknowledged_results_view, name='unacknowledged'),

    # ── Payment Authorization ──────────────────────────────────────────────────
    path('<uuid:pk>/authorize-payment/', views.authorize_payment_view, name='authorize_payment'),

    # ── Contrast Safety ────────────────────────────────────────────────────────
    path('<uuid:pk>/contrast-safety/', views.contrast_safety_view, name='contrast_safety'),
    path('<uuid:pk>/contrast-reaction/', views.contrast_reaction_view, name='contrast_reaction'),

    # ── Biometry Safety Workflow ───────────────────────────────────────────────
    path('<uuid:pk>/biometry/', views.biometry_record_view, name='biometry'),
    path('<uuid:pk>/biometry/surgeon-signoff/', views.biometry_surgeon_signoff_view, name='biometry_surgeon_signoff'),
    path('<uuid:pk>/biometry/second-verify/', views.biometry_second_verify_view, name='biometry_second_verify'),
    path('<uuid:pk>/biometry/lock/', views.biometry_lock_view, name='biometry_lock'),
    path('<uuid:pk>/biometry/postop/', views.biometry_postop_view, name='biometry_postop'),

    # ── Dilation Tracking ──────────────────────────────────────────────────────
    path('<uuid:pk>/dilation/', views.record_dilation_view, name='record_dilation'),

    # ── Dilation-Aware Visit Plan ──────────────────────────────────────────────
    path('visit-plan/<str:patient_id>/', views.visit_plan_view, name='visit_plan'),
    path('visit-plan/detail/<uuid:plan_pk>/', views.visit_plan_detail_view, name='visit_plan_detail'),
    path('visit-plan/step/<uuid:step_pk>/complete/', views.visit_plan_complete_step_view, name='visit_plan_complete_step'),

    # ── Device Management ──────────────────────────────────────────────────────
    path('devices/', views.device_list_view, name='device_list'),
    path('devices/create/', views.device_create_view, name='device_create'),
    path('devices/<uuid:pk>/', views.device_detail_view, name='device_detail'),
    path('devices/<uuid:pk>/edit/', views.device_edit_view, name='device_edit'),
    path('devices/<uuid:pk>/downtime/', views.device_downtime_view, name='device_downtime'),

    # ── DICOM Imaging Studies ──────────────────────────────────────────────────
    path('imaging/', views.imaging_study_list, name='imaging_list'),
    path('imaging/create/', views.imaging_study_create, name='imaging_create'),
    path('imaging/<uuid:study_id>/', views.imaging_study_detail, name='imaging_detail'),
    path('imaging/<uuid:study_id>/report/', views.imaging_study_report, name='imaging_report'),
    path('patient/<str:patient_id>/imaging/', views.patient_imaging_list, name='patient_imaging'),

    # ── Statistics & Reports ───────────────────────────────────────────────────
    path('stats/', views.investigation_stats_view, name='stats'),
    path('stats/export-csv/', views.stats_csv_export_view, name='stats_csv'),
    path('machine-revenue/', views.machine_revenue_view, name='machine_revenue'),
    path('machine-revenue/export-csv/', views.machine_revenue_csv_view, name='machine_revenue_csv'),
    path('staff-throughput/', views.staff_throughput_view, name='staff_throughput'),
    path('staff-throughput/export-csv/', views.staff_throughput_csv_view, name='staff_throughput_csv'),
    path('staff-throughput/pdf/', views.staff_throughput_pdf_view, name='staff_throughput_pdf'),
]
