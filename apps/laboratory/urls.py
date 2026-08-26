from django.urls import path
from . import views

app_name = 'laboratory'

urlpatterns = [
    # ── Core workflow ────────────────────────────────────────────────────
    path('', views.lab_dashboard, name='dashboard'),
    path('list/', views.lab_list_view, name='list'),
    path('stats/', views.lab_stats_view, name='stats'),
    path('order/<uuid:consultation_pk>/', views.lab_order_view, name='order'),
    path('<uuid:pk>/', views.lab_detail_view, name='detail'),

    # ── Specimen collection & receipt ────────────────────────────────────
    path('bulk-collect/', views.bulk_collect_sample_view, name='bulk_collect'),
    path('<uuid:pk>/collect-sample/', views.collect_sample_view, name='collect_sample'),
    path('<uuid:pk>/receive-specimen/', views.specimen_receive_view, name='receive_specimen'),
    path('<uuid:pk>/reject-sample/', views.reject_sample_view, name='reject_sample'),

    # ── Results & validation ─────────────────────────────────────────────
    path('<uuid:pk>/results/', views.enter_results_view, name='enter_results'),
    path('result/<uuid:result_id>/verify/', views.verify_result, name='verify_result'),
    path('result/<uuid:result_id>/authorize/', views.authorize_result_view, name='authorize_result'),
    path('result/<uuid:result_id>/release/', views.release_result_view, name='release_result'),
    path('result/<uuid:result_id>/acknowledge/', views.acknowledge_result_view, name='acknowledge_result'),
    path('result/<uuid:result_id>/acknowledge-critical/', views.acknowledge_critical_view, name='acknowledge_critical'),
    path('unacknowledged/', views.unacknowledged_results_view, name='unacknowledged_results'),

    # ── Payment authorization ────────────────────────────────────────────
    path('<uuid:pk>/authorize-payment/', views.payment_authorize_view, name='authorize_payment'),

    # ── Cancel ───────────────────────────────────────────────────────────
    path('<uuid:pk>/cancel/', views.cancel_lab_order, name='cancel'),

    # ── Reports & exports ────────────────────────────────────────────────
    path('<uuid:pk>/result-pdf/', views.result_pdf_view, name='result_pdf'),
    path('stats/export-csv/', views.lab_stats_csv_view, name='stats_csv'),
    path('staff-throughput/', views.lab_staff_throughput_view, name='staff_throughput'),
    path('staff-throughput/export-csv/', views.lab_staff_throughput_csv_view, name='staff_throughput_csv'),
    path('staff-throughput/pdf/', views.lab_staff_throughput_pdf_view, name='staff_throughput_pdf'),
    path('tat-report/', views.tat_report_view, name='tat_report'),

    # ── Quality Control ──────────────────────────────────────────────────
    path('qc/', views.qc_dashboard_view, name='qc_dashboard'),
    path('qc/new/', views.qc_record_create_view, name='qc_record_create'),

    # ── Send-out / Referral tests ────────────────────────────────────────
    path('sendout/', views.sendout_list_view, name='sendout_list'),
    path('sendout/new/<uuid:item_pk>/', views.sendout_create_view, name='sendout_create'),
    path('sendout/<uuid:pk>/status/', views.sendout_update_status_view, name='sendout_update_status'),

    # ── Microbiology ─────────────────────────────────────────────────────
    path('culture/new/<uuid:item_pk>/', views.culture_create_view, name='culture_create'),
    path('culture/<uuid:pk>/', views.culture_detail_view, name='culture_detail'),
    path('culture/<uuid:pk>/reading/', views.culture_update_reading_view, name='culture_update_reading'),
    path('culture/<uuid:culture_pk>/organism/', views.organism_add_view, name='organism_add'),
    path('organism/<uuid:organism_pk>/sensitivity/', views.sensitivity_add_view, name='sensitivity_add'),
    path('antibiogram/', views.antibiogram_view, name='antibiogram'),
    path('antibiogram/generate/', views.generate_antibiogram_view, name='generate_antibiogram'),

    # ── Histopathology ───────────────────────────────────────────────────
    path('histopath/', views.histopath_list_view, name='histopath_list'),
    path('histopath/new/<uuid:item_pk>/', views.histopath_create_view, name='histopath_create'),
    path('histopath/<uuid:pk>/', views.histopath_detail_view, name='histopath_detail'),
    path('histopath/<uuid:pk>/update/', views.histopath_update_view, name='histopath_update'),

    # ── AJAX ─────────────────────────────────────────────────────────────
    path('check-duplicates/', views.check_duplicate_order_ajax, name='check_duplicates'),
]
