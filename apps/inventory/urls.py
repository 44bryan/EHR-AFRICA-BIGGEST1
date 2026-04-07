from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('items/', views.item_list, name='item_list'),
    path('items/<uuid:item_id>/', views.item_detail, name='item_detail'),
    path('items/<uuid:item_id>/adjust/', views.stock_adjustment, name='stock_adjustment'),
    path('purchase-orders/', views.purchase_order_list, name='po_list'),
    path('vendors/', views.vendor_list, name='vendor_list'),
]
