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
    path('items/<uuid:item_id>/batches/', views.item_batches, name='item_batches'),

    # Vendors
    path('vendors/', views.vendor_list, name='vendor_list'),
    path('vendors/create/', views.vendor_create, name='vendor_create'),
    path('vendors/<uuid:vendor_id>/edit/', views.vendor_edit, name='vendor_edit'),

    # Purchase Orders
    path('purchase-orders/', views.purchase_order_list, name='po_list'),
    path('purchase-orders/create/', views.po_create, name='po_create'),
    path('purchase-orders/<uuid:po_id>/', views.po_detail, name='po_detail'),
    path('purchase-orders/<uuid:po_id>/receive/', views.po_receive, name='po_receive'),

    # Department Requisitions
    path('requisitions/', views.requisition_list, name='requisition_list'),
    path('requisitions/create/', views.requisition_create, name='requisition_create'),
    path('requisitions/<uuid:req_id>/', views.requisition_detail, name='requisition_detail'),
    path('requisitions/<uuid:req_id>/approve/', views.requisition_approve, name='requisition_approve'),
    path('requisitions/<uuid:req_id>/issue/', views.requisition_issue, name='requisition_issue'),

    # Store Locations
    path('locations/', views.store_location_list, name='store_location_list'),
    path('locations/create/', views.store_location_create, name='store_location_create'),
    path('locations/<uuid:loc_id>/edit/', views.store_location_edit, name='store_location_edit'),

    # Physical Stock Count
    path('stock-count/', views.stock_count_list, name='stock_count_list'),
    path('stock-count/new/', views.stock_count_create, name='stock_count_create'),
    path('stock-count/<uuid:count_id>/', views.stock_count_detail, name='stock_count_detail'),
    path('stock-count/<uuid:count_id>/update/', views.stock_count_update, name='stock_count_update'),
    path('stock-count/<uuid:count_id>/complete/', views.stock_count_complete, name='stock_count_complete'),
    path('stock-count/<uuid:count_id>/approve/', views.stock_count_approve, name='stock_count_approve'),

    # Department Returns
    path('returns/', views.return_list, name='return_list'),
    path('returns/create/', views.return_create, name='return_create'),
    path('returns/<uuid:return_id>/action/', views.return_action, name='return_action'),

    # Reports
    path('reports/valuation/', views.report_stock_valuation, name='report_valuation'),
    path('reports/movements/', views.report_movement_history, name='report_movements'),
    path('reports/consumption/', views.report_consumption_by_dept, name='report_consumption'),
    path('reports/expiry/', views.report_expiry_alert, name='report_expiry'),
    path('reports/vendors/', views.report_vendor_performance, name='report_vendors'),
]
