from django.urls import path
from . import views

app_name = 'appointments'

urlpatterns = [
    path('', views.appointment_list_view, name='list'),
    path('board/', views.clinic_board_view, name='clinic_board'),
    path('book/', views.appointment_book_view, name='book'),
    path('<uuid:pk>/', views.appointment_detail_view, name='detail'),
    path('<uuid:pk>/check-in/', views.appointment_check_in_view, name='check_in'),
    path('<uuid:pk>/cancel/', views.appointment_cancel_view, name='cancel'),
    path('<uuid:pk>/no-show/', views.appointment_no_show_view, name='no_show'),
    path('<uuid:pk>/status/', views.update_status_view, name='update_status'),
    path('<uuid:pk>/reschedule/', views.reschedule_view, name='reschedule'),
    # Doctor schedule management
    path('schedules/', views.schedule_list_view, name='schedule_list'),
    path('schedules/add/', views.schedule_create_view, name='schedule_create'),
    path('schedules/<int:pk>/delete/', views.schedule_delete_view, name='schedule_delete'),
]
