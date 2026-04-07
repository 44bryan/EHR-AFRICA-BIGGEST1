from django.urls import path
from . import views

app_name = 'leads'

urlpatterns = [
    path('', views.leads_dashboard, name='dashboard'),
    path('list/', views.lead_list, name='lead_list'),
    path('new/', views.lead_create, name='lead_create'),
    path('<uuid:lead_id>/', views.lead_detail, name='lead_detail'),
    path('<uuid:lead_id>/edit/', views.lead_edit, name='lead_edit'),
    path('<uuid:lead_id>/activity/', views.add_activity, name='add_activity'),
]
