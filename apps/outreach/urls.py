from django.urls import path
from . import views

app_name = 'outreach'

urlpatterns = [
    # ── Dashboard & activity management ─────────────────────────────────────
    path('', views.dashboard, name='dashboard'),
    path('activities/', views.activity_list, name='list'),
    path('activities/new/', views.activity_create, name='create'),
    path('activities/<uuid:pk>/', views.activity_detail, name='detail'),
    path('activities/<uuid:pk>/edit/', views.activity_edit, name='edit'),
    path('activities/<uuid:pk>/record/', views.record_add, name='record_add'),

    # ── Individual patients ──────────────────────────────────────────────────
    path('activities/<uuid:pk>/patients/', views.patient_list, name='patient_list'),
    path('activities/<uuid:pk>/patients/new/', views.patient_register, name='patient_register'),
    path('patients/<uuid:patient_pk>/', views.patient_detail, name='patient_detail'),

    # ── Clinical examinations ────────────────────────────────────────────────
    path('patients/<uuid:patient_pk>/exam/', views.exam_create, name='exam_create'),
    path('patients/<uuid:patient_pk>/exam/edit/', views.exam_edit, name='exam_edit'),

    # ── Referrals ────────────────────────────────────────────────────────────
    path('patients/<uuid:patient_pk>/referral/', views.referral_create, name='referral_create'),
    path('patients/<uuid:patient_pk>/referral/letter/', views.referral_letter, name='referral_letter'),
    path('referrals/<uuid:referral_pk>/status/', views.referral_status_update, name='referral_status'),
    path('referral-lookup/', views.referral_lookup, name='referral_lookup'),

    # ── Stats ────────────────────────────────────────────────────────────────
    path('stats/', views.stats_view, name='stats'),

    # ── Field sync ───────────────────────────────────────────────────────────
    path('sync/', views.sync_dashboard, name='sync_dashboard'),
    path('sync/now/', views.sync_now, name='sync_now'),
    path('api/sync/', views.sync_api, name='sync_api'),
]
