from django.urls import path
from . import views

app_name = 'pharmacy'

urlpatterns = [
    path('', views.pharmacy_dashboard, name='dashboard'),
    path('stats/', views.pharmacy_stats_view, name='stats'),
    path('alerts/', views.drug_expiry_alerts, name='expiry_alerts'),
    path('drugs/', views.drug_list, name='drug_list'),
    path('drugs/new/', views.drug_create, name='drug_create'),
    path('drugs/<uuid:drug_id>/', views.drug_detail, name='drug_detail'),
    path('drugs/<uuid:drug_id>/edit/', views.drug_edit, name='drug_edit'),
    path('drugs/<uuid:drug_id>/add-stock/', views.add_stock, name='add_stock'),
    path('drugs/stock-ajax/', views.drug_stock_ajax, name='drug_stock_ajax'),
    path('drugs/search/', views.drug_search_ajax, name='drug_search_ajax'),
    path('dispensing/<uuid:dispensing_id>/add-item-ajax/', views.add_dispensing_item_ajax, name='add_dispensing_item_ajax'),
    path('dispensing/<uuid:dispensing_id>/add-manual-ajax/', views.add_manual_item_ajax, name='add_manual_item_ajax'),
    path('dispensing/<uuid:dispensing_id>/remove-item/<uuid:item_id>/', views.remove_dispensing_item_ajax, name='remove_dispensing_item_ajax'),
    path('dispense/', views.dispense, name='dispense'),
    path('dispensing/', views.dispensing_list, name='dispensing_list'),
    path('dispensing/<uuid:dispensing_id>/', views.dispensing_detail, name='dispensing_detail'),
    path('dispensing/<uuid:dispensing_id>/add-item/', views.add_dispensing_item, name='add_dispensing_item'),
    path('dispensing/<uuid:dispensing_id>/complete/', views.complete_dispensing, name='complete_dispensing'),
    path('dispensing/<uuid:dispensing_id>/cancel/', views.cancel_dispensing, name='cancel_dispensing'),
    path('pilferage/', views.pilferage_dashboard, name='pilferage'),
    path('dispensing/<uuid:dispensing_id>/receipt/', views.dispensing_receipt, name='dispensing_receipt'),
    path('search/', views.patient_search, name='patient_search'),
    path('rx/<uuid:rx_id>/start-dispensing/', views.start_rx_dispensing, name='start_rx_dispensing'),
    path('rx/<uuid:rx_id>/declined/', views.rx_declined, name='rx_declined'),
    path('adjustments/', views.stock_adjustment_list, name='stock_adjustment_list'),
    path('stock/<uuid:batch_id>/adjust/', views.stock_adjustment_create, name='stock_adjustment_create'),

    # Controlled drugs register
    path('controlled/', views.controlled_register, name='controlled_register'),
    path('controlled/new/', views.controlled_entry_create, name='controlled_entry_create'),
    path('controlled/<uuid:entry_id>/witness/', views.controlled_entry_witness_confirm, name='controlled_witness'),

    # Ward drug returns
    path('ward-returns/', views.ward_return_list, name='ward_return_list'),
    path('ward-returns/new/', views.ward_return_create, name='ward_return_create'),
    path('ward-returns/<uuid:return_id>/action/', views.ward_return_action, name='ward_return_action'),

    # Chronic Rx refill tracking
    path('chronic-rx/', views.chronic_rx_list, name='chronic_rx_list'),
    path('chronic-rx/new/', views.chronic_rx_create, name='chronic_rx_create'),
    path('chronic-rx/<uuid:rx_id>/refill/', views.chronic_rx_refill, name='chronic_rx_refill'),

    # Supplier management
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/new/', views.supplier_create, name='supplier_create'),
    path('suppliers/<uuid:supplier_id>/edit/', views.supplier_edit, name='supplier_edit'),

    # Purchase orders
    path('purchase-orders/', views.purchase_order_list, name='purchase_order_list'),
    path('purchase-orders/new/', views.purchase_order_create, name='purchase_order_create'),
    path('purchase-orders/<uuid:po_id>/', views.purchase_order_detail, name='purchase_order_detail'),
    path('purchase-orders/<uuid:po_id>/approve/', views.purchase_order_approve, name='purchase_order_approve'),
    path('purchase-orders/<uuid:po_id>/receive/', views.receive_purchase_order, name='receive_purchase_order'),

    # Dispensing return
    path('dispensing/<uuid:dispensing_id>/return/', views.dispensing_return_create, name='dispensing_return_create'),

    # Dispensing verification (pharmacist sign-off)
    path('dispensing/<uuid:dispensing_id>/verify/', views.dispensing_verify, name='dispensing_verify'),

    # Dispensing label PDF
    path('dispensing/<uuid:dispensing_id>/label/', views.dispensing_label_pdf, name='dispensing_label_pdf'),

    # Controlled drug register PDF
    path('controlled/pdf/', views.controlled_register_pdf, name='controlled_register_pdf'),

    # Bulk drug/stock import
    path('drugs/import/', views.drug_bulk_import, name='drug_bulk_import'),
    path('drugs/import/template/', views.drug_import_template, name='drug_import_template'),
]
