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
]
