from django.urls import path
from . import views

app_name = 'departments'

urlpatterns = [
    path('', views.dept_list, name='dept_list'),
    path('rooms/', views.room_list_all, name='room_list_all'),
    path('<uuid:dept_id>/edit/', views.dept_edit, name='dept_edit'),
    path('<uuid:dept_id>/rooms/', views.room_manage, name='room_manage'),
    path('<uuid:dept_id>/rooms-ajax/', views.room_ajax, name='room_ajax'),
]
