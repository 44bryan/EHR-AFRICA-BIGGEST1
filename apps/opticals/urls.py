from django.urls import path
from . import views

app_name = 'opticals'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('frames/', views.frame_list, name='frame_list'),
    path('frames/new/', views.frame_create, name='frame_create'),
    path('frames/<uuid:frame_id>/edit/', views.frame_edit, name='frame_edit'),
    path('frames/<uuid:frame_id>/receive/', views.frame_receive_stock, name='frame_receive_stock'),
    path('lenses/', views.lens_list, name='lens_list'),
    path('lenses/new/', views.lens_create, name='lens_create'),
    path('lenses/<uuid:lens_id>/edit/', views.lens_edit, name='lens_edit'),
    path('orders/', views.order_list, name='order_list'),
    path('orders/outstanding/', views.order_list_unpaid, name='order_list_unpaid'),
    path('orders/new/', views.create_order, name='create_order'),
    path('orders/<uuid:order_id>/', views.order_detail, name='order_detail'),
    path('orders/<uuid:order_id>/status/', views.update_order_status, name='update_status'),
    path('orders/<uuid:order_id>/pay/', views.collect_payment, name='collect_payment'),
    path('orders/<uuid:order_id>/receipt/', views.order_receipt, name='order_receipt'),
    path('orders/<uuid:order_id>/quotation/', views.order_quotation, name='order_quotation'),
    path('orders/<uuid:order_id>/quick-status/', views.quick_update_status, name='quick_status'),
    path('stats/', views.optical_stats_view, name='stats'),
    path('search/', views.patient_search, name='patient_search'),

    # Contact lens fittings
    path('contact-lens/', views.cl_fitting_list, name='cl_fitting_list'),
    path('contact-lens/new/', views.cl_fitting_create, name='cl_fitting_create'),
    path('contact-lens/new/<uuid:patient_id>/', views.cl_fitting_create, name='cl_fitting_create_patient'),

    # Low vision aid dispensings
    path('low-vision/', views.lva_dispensing_list, name='lva_dispensing_list'),
    path('low-vision/new/', views.lva_dispensing_create, name='lva_dispensing_create'),
    path('low-vision/new/<uuid:patient_id>/', views.lva_dispensing_create, name='lva_dispensing_create_patient'),
]
