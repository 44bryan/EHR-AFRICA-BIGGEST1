from django.urls import path
from . import views

app_name = 'reception'

urlpatterns = [
    path('', views.desk, name='desk'),
    path('walk-in/', views.walk_in, name='walk_in'),
    path('confirmation/<uuid:token_pk>/', views.confirmation, name='confirmation'),
    path('check-in/<uuid:pk>/', views.quick_checkin, name='quick_checkin'),
]
