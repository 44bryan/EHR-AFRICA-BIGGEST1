from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.notification_list, name='list'),
    path('<int:pk>/read/', views.mark_read, name='mark_read'),
    path('count/', views.unread_count, name='unread_count'),
    path('poll/', views.poll_notifications, name='poll'),
    # SMS / WhatsApp management
    path('sms/', views.sms_log, name='sms_log'),
    path('sms/send/', views.sms_send, name='sms_send'),
    path('sms/send/<uuid:patient_id>/', views.sms_send, name='sms_send_patient'),
    path('sms/templates/', views.template_list, name='template_list'),
    path('sms/templates/new/', views.template_create, name='template_create'),
]
