from django.urls import path
from . import views

app_name = 'investigations'

urlpatterns = [
    path('', views.investigation_list_view, name='list'),
    path('workstation/', views.investigation_workstation_view, name='workstation'),
    path('order/<uuid:consultation_pk>/', views.investigation_order_view, name='order'),
    path('<uuid:pk>/', views.investigation_detail_view, name='detail'),
    path('<uuid:pk>/result/', views.add_result_view, name='add_result'),
    path('<uuid:pk>/verify/', views.verify_result_view, name='verify'),
]
