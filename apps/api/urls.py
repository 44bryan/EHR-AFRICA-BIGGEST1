from django.urls import path
from . import views

app_name = 'api'

urlpatterns = [
    path('dashboard/stats/', views.dashboard_stats_view, name='dashboard_stats'),
    path('patients/search/', views.patient_search_view, name='patient_search'),
]
