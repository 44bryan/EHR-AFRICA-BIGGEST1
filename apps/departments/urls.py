from django.urls import path
from . import views

app_name = 'departments'

urlpatterns = [
    path('', views.dept_list, name='dept_list'),
    path('<uuid:dept_id>/edit/', views.dept_edit, name='dept_edit'),
]
