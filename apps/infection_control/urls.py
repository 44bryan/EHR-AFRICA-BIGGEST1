from django.urls import path
from . import views

app_name = 'infection_control'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    # HAI Reports
    path('hai/', views.hai_list, name='hai_list'),
    path('hai/new/', views.hai_create, name='hai_create'),
    path('hai/<uuid:report_id>/', views.hai_detail, name='hai_detail'),
    # Antibiogram
    path('antibiogram/', views.antibiogram, name='antibiogram'),
    path('antibiogram/new/', views.sensitivity_create, name='sensitivity_create'),
    # Outbreak Alerts
    path('outbreaks/', views.outbreak_list, name='outbreak_list'),
    path('outbreaks/new/', views.outbreak_create, name='outbreak_create'),
]
