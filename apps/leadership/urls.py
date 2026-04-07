from django.urls import path
from . import views

app_name = 'leadership'

urlpatterns = [
    path('', views.leadership_dashboard, name='dashboard'),
    path('kpi/', views.kpi_json, name='kpi_json'),
    path('monthly-stats/', views.monthly_stats, name='monthly_stats'),
    path('retina/', views.retina_dashboard, name='retina_dashboard'),
    path('finance/', views.finance_dashboard, name='finance_dashboard'),
]
