from django.urls import path
from . import views

app_name = 'outreach'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('activities/', views.activity_list, name='list'),
    path('activities/new/', views.activity_create, name='create'),
    path('activities/<uuid:pk>/', views.activity_detail, name='detail'),
    path('activities/<uuid:pk>/edit/', views.activity_edit, name='edit'),
    path('activities/<uuid:pk>/record/', views.record_add, name='record_add'),
    path('stats/', views.stats_view, name='stats'),
]
