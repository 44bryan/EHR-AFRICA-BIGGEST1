from django.urls import path
from . import views

app_name = 'feedback'

urlpatterns = [
    path('', views.feedback_dashboard, name='dashboard'),
    path('list/', views.feedback_list, name='list'),
    path('service-recovery/', views.service_recovery, name='service_recovery'),
    path('<uuid:feedback_id>/', views.feedback_detail, name='detail'),
    path('<uuid:feedback_id>/resolve/', views.resolve_feedback, name='resolve'),
    path('<uuid:feedback_id>/escalate/', views.escalate_feedback, name='escalate'),
    path('<uuid:feedback_id>/acknowledge/', views.acknowledge_feedback, name='acknowledge'),
    path('submit/', views.submit_feedback, name='submit'),
]
