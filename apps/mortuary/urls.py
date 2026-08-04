from django.urls import path
from . import views

app_name = 'mortuary'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('bodies/', views.admission_list, name='admission_list'),
    path('bodies/new/', views.admission_create, name='admission_create'),
    path('bodies/<int:pk>/', views.admission_detail, name='admission_detail'),
    path('bodies/<int:admission_id>/post-mortem/', views.postmortem_create, name='postmortem_create'),
    path('post-mortem/<int:pk>/update/', views.postmortem_update, name='postmortem_update'),
    path('bodies/<int:admission_id>/release/', views.release_create, name='release_create'),
    path('storage/', views.storage_list, name='storage_list'),
    path('storage/manage/', views.storage_manage, name='storage_manage'),
]
