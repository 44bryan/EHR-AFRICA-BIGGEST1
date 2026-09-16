from django.urls import path
from . import views

app_name = 'telemedicine'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('appointments/', views.appointment_list, name='appointment_list'),
    path('appointments/create/', views.appointment_create, name='appointment_create'),
    path('appointments/<uuid:pk>/', views.appointment_detail, name='appointment_detail'),
    path('appointments/<uuid:pk>/start/', views.session_start, name='session_start'),
    path('appointments/<uuid:pk>/end/', views.session_end, name='session_end'),
    path('appointments/<uuid:pk>/room/', views.session_room, name='session_room'),
    path('appointments/<uuid:pk>/notes/', views.session_notes, name='session_notes'),
    path('appointments/<uuid:pk>/cancel/', views.cancel_appointment, name='cancel_appointment'),
    # AI endpoints
    path('appointments/<uuid:pk>/ai-soap/', views.ai_soap_generate, name='ai_soap'),
    path('appointments/<uuid:pk>/ai-diagnose/', views.ai_diagnose, name='ai_diagnose'),
    # Prescriptions
    path('appointments/<uuid:pk>/prescriptions/add/', views.add_prescription, name='add_prescription'),
    path('appointments/<uuid:pk>/prescriptions/<uuid:rx_pk>/delete/', views.delete_prescription, name='delete_prescription'),
    path('appointments/<uuid:pk>/prescription-print/', views.print_prescription, name='print_prescription'),
    # Referral
    path('appointments/<uuid:pk>/referral/save/', views.save_referral, name='save_referral'),
    path('appointments/<uuid:pk>/referral/print/', views.print_referral, name='print_referral'),
    # Patient join (no auth)
    path('join/<uuid:room_id>/<str:token>/', views.patient_join, name='patient_join'),
    path('join/<uuid:room_id>/<str:token>/intake/', views.patient_intake_submit, name='patient_intake'),
]
