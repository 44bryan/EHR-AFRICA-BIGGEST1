from django.urls import path
from . import views

app_name = 'opticals'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('frames/', views.frame_list, name='frame_list'),
    path('lenses/', views.lens_list, name='lens_list'),
    path('orders/', views.order_list, name='order_list'),
    path('orders/new/', views.create_order, name='create_order'),
    path('orders/<uuid:order_id>/', views.order_detail, name='order_detail'),
    path('orders/<uuid:order_id>/status/', views.update_order_status, name='update_status'),
]
