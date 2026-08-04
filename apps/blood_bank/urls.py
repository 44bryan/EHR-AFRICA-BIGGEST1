from django.urls import path
from . import views

app_name = 'blood_bank'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    # Donors
    path('donors/', views.donor_list, name='donor_list'),
    path('donors/new/', views.donor_create, name='donor_create'),
    # Blood Units
    path('inventory/', views.unit_list, name='unit_list'),
    path('inventory/add/', views.unit_create, name='unit_create'),
    # Cross-Match
    path('cross-match/', views.crossmatch_list, name='crossmatch_list'),
    path('cross-match/new/', views.crossmatch_create, name='crossmatch_create'),
    path('cross-match/<uuid:xm_id>/result/', views.crossmatch_result, name='crossmatch_result'),
    # Issue / Transfusion
    path('issues/', views.issue_list, name='issue_list'),
    path('issues/new/', views.issue_create, name='issue_create'),
    path('issues/<uuid:issue_id>/status/', views.issue_update_status, name='issue_status'),
]
