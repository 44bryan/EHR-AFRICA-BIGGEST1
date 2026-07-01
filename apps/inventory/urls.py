from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # Items
    path('items/', views.item_list, name='item_list'),
    path('items/create/', views.item_create, name='item_create'),
    path('items/<uuid:item_id>/', views.item_detail, name='item_detail'),
    path('items/<uuid:item_id>/edit/', views.item_edit, name='item_edit'),
    path('items/<uuid:item_id>/adjust/', views.stock_adjustment, name='stock_adjustment'),

    # Vendors
    path('vendors/', views.vendor_list, name='vendor_list'),
    path('vendors/create/', views.vendor_create, name='vendor_create'),
    path('vendors/<uuid:vendor_id>/edit/', views.vendor_edit, name='vendor_edit'),

    # Purchase Orders
    path('purchase-orders/', views.purchase_order_list, name='po_list'),
    path('purchase-orders/create/', views.po_create, name='po_create'),
    path('purchase-orders/<uuid:po_id>/', views.po_detail, name='po_detail'),
    path('purchase-orders/<uuid:po_id>/receive/', views.po_receive, name='po_receive'),
]
