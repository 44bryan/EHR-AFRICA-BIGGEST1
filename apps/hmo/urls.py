from django.urls import path
from . import views

app_name = 'hmo'

urlpatterns = [
    # Dashboard
    path('', views.hmo_dashboard, name='dashboard'),

    # Insurance Schemes
    path('schemes/', views.scheme_list, name='scheme_list'),
    path('schemes/new/', views.scheme_create, name='scheme_create'),
    path('schemes/<uuid:scheme_id>/edit/', views.scheme_edit, name='scheme_edit'),

    # Insured Members
    path('members/', views.member_list, name='member_list'),
    path('members/enrol/', views.member_enrol, name='member_enrol'),
    path('members/enrol/<uuid:patient_id>/', views.member_enrol, name='member_enrol_patient'),

    # Pre-Authorisation
    path('pre-auth/', views.preauth_list, name='preauth_list'),
    path('pre-auth/new/', views.preauth_create, name='preauth_create'),
    path('pre-auth/new/<uuid:member_id>/', views.preauth_create, name='preauth_create_member'),
    path('pre-auth/<uuid:preauth_id>/respond/', views.preauth_respond, name='preauth_respond'),

    # Claim Batches
    path('batches/', views.batch_list, name='batch_list'),
    path('batches/new/', views.batch_create, name='batch_create'),
    path('batches/<uuid:batch_id>/', views.batch_detail, name='batch_detail'),
    path('batches/<uuid:batch_id>/add-claim/', views.batch_add_claim, name='batch_add_claim'),
    path('batches/<uuid:batch_id>/submit/', views.batch_submit, name='batch_submit'),
    path('batches/<uuid:batch_id>/payment/', views.batch_record_payment, name='batch_payment'),

    # Individual Claims
    path('claims/', views.claim_list, name='claim_list'),
    path('claims/new/', views.claim_create, name='claim_create'),
    path('claims/new/<uuid:member_id>/', views.claim_create, name='claim_create_member'),
    path('claims/<uuid:claim_id>/', views.claim_detail, name='claim_detail'),
    path('claims/<uuid:claim_id>/reject/', views.claim_reject, name='claim_reject'),

    # AJAX
    path('ajax/patient-search/', views.patient_search_ajax, name='patient_search_ajax'),
]
