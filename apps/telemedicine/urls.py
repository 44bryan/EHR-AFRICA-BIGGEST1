from django.urls import path
from . import views

app_name = 'telemedicine'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('appointments/', views.appointment_list, name='appointment_list'),
    path('appointments/create/', views.appointment_create, name='appointment_create'),
    path('appointments/<int:pk>/', views.appointment_detail, name='appointment_detail'),
    path('appointments/<int:pk>/start/', views.session_start, name='session_start'),
    path('appointments/<int:pk>/end/', views.session_end, name='session_end'),
    path('appointments/<int:pk>/room/', views.session_room, name='session_room'),
    path('appointments/<int:pk>/notes/', views.session_notes, name='session_notes'),
    path('appointments/<int:pk>/cancel/', views.cancel_appointment, name='cancel_appointment'),
    # AI endpoints
    path('appointments/<int:pk>/ai-soap/', views.ai_soap_generate, name='ai_soap'),
    path('appointments/<int:pk>/ai-diagnose/', views.ai_diagnose, name='ai_diagnose'),
    # Patient join (no auth)
    path('join/<uuid:room_id>/<str:token>/', views.patient_join, name='patient_join'),
    path('join/<uuid:room_id>/<str:token>/intake/', views.patient_intake_submit, name='patient_intake'),
]
