from django.urls import path
from . import views

app_name = 'laboratory'

urlpatterns = [
    path('', views.lab_dashboard, name='dashboard'),
    path('list/', views.lab_list_view, name='list'),
    path('stats/', views.lab_stats_view, name='stats'),
    path('order/<uuid:consultation_pk>/', views.lab_order_view, name='order'),
    path('<uuid:pk>/', views.lab_detail_view, name='detail'),
    path('bulk-collect/', views.bulk_collect_sample_view, name='bulk_collect'),
    path('<uuid:pk>/collect-sample/', views.collect_sample_view, name='collect_sample'),
    path('<uuid:pk>/results/', views.enter_results_view, name='enter_results'),
    path('result/<uuid:result_id>/verify/', views.verify_result, name='verify_result'),
    path('<uuid:pk>/cancel/', views.cancel_lab_order, name='cancel'),
    path('stats/export-csv/', views.lab_stats_csv_view, name='stats_csv'),
    path('staff-throughput/', views.lab_staff_throughput_view, name='staff_throughput'),
    path('staff-throughput/export-csv/', views.lab_staff_throughput_csv_view, name='staff_throughput_csv'),
    path('<uuid:pk>/reject-sample/', views.reject_sample_view, name='reject_sample'),
    path('<uuid:pk>/result-pdf/', views.result_pdf_view, name='result_pdf'),
    path('result/<uuid:result_id>/acknowledge-critical/', views.acknowledge_critical_view, name='acknowledge_critical'),
    path('staff-throughput/pdf/', views.lab_staff_throughput_pdf_view, name='staff_throughput_pdf'),
]
