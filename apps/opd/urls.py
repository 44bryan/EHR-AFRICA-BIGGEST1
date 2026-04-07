from django.urls import path
from . import views

app_name = 'opd'

urlpatterns = [
    path('', views.opd_dashboard, name='dashboard'),
    path('visits/', views.visit_list, name='visit_list'),
    path('visits/register/', views.register_visit, name='register_visit'),
    path('visits/<uuid:visit_id>/', views.visit_detail, name='visit_detail'),
    path('visits/<uuid:visit_id>/status/', views.update_visit_status, name='update_status'),
]
