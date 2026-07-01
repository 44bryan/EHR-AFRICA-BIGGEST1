from django.urls import path
from . import views
from . import analytics_views

app_name = 'leadership'

urlpatterns = [
    path('', views.leadership_dashboard, name='dashboard'),
    path('kpi/', views.kpi_json, name='kpi_json'),
    path('monthly-stats/', views.monthly_stats, name='monthly_stats'),
    path('retina/', views.retina_dashboard, name='retina_dashboard'),
    path('finance/', views.finance_dashboard, name='finance_dashboard'),
    path('analytics/', analytics_views.analytics_dashboard, name='analytics_dashboard'),
    path('analytics/data/', analytics_views.analytics_data_json, name='analytics_data'),
    path('hospital-stats/', views.hospital_stats_view, name='hospital_stats'),
]
