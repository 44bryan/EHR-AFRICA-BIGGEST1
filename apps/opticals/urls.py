from django.urls import path
from . import views

app_name = 'opticals'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('frames/', views.frame_list, name='frame_list'),
    path('frames/new/', views.frame_create, name='frame_create'),
    path('frames/<uuid:frame_id>/edit/', views.frame_edit, name='frame_edit'),
    path('frames/<uuid:frame_id>/delete/', views.frame_delete, name='frame_delete'),
    path('frames/<uuid:frame_id>/receive/', views.frame_receive_stock, name='frame_receive_stock'),
    path('lenses/', views.lens_list, name='lens_list'),
    path('lenses/new/', views.lens_create, name='lens_create'),
    path('lenses/<uuid:lens_id>/edit/', views.lens_edit, name='lens_edit'),
    path('lenses/<uuid:lens_id>/delete/', views.lens_delete, name='lens_delete'),
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

    # Lab Job Card
    path('lab/', views.lab_job_queue, name='lab_job_queue'),
    path('orders/<uuid:order_id>/send-to-lab/', views.send_to_lab, name='send_to_lab'),
    path('lab/<uuid:job_id>/action/', views.lab_job_action, name='lab_job_action'),

    # QC verification
    path('orders/<uuid:order_id>/qc-verify/', views.qc_verify, name='qc_verify'),
    path('orders/<uuid:order_id>/qc-fail/', views.qc_fail, name='qc_fail'),

    # Reports
    path('uncollected/', views.uncollected_orders, name='uncollected_orders'),

    # Lens price matrix
    path('price-matrix/', views.lens_price_matrix, name='lens_price_matrix'),
    path('price-matrix/save/', views.lens_price_matrix_save, name='lens_price_matrix_save'),
    path('price-matrix/<uuid:entry_id>/delete/', views.lens_price_matrix_delete, name='lens_price_matrix_delete'),
    path('price-matrix/lookup/', views.lens_price_lookup_ajax, name='lens_price_lookup'),

    # Warranty & after-sales
    path('warranties/', views.warranty_list, name='warranty_list'),
    path('repairs/', views.repair_list, name='repair_list'),
    path('repairs/new/', views.repair_create, name='repair_create'),
    path('repairs/<uuid:repair_id>/action/', views.repair_action, name='repair_action'),

    # Frame suppliers
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/new/', views.supplier_create, name='supplier_create'),
    path('suppliers/<uuid:supplier_id>/edit/', views.supplier_edit, name='supplier_edit'),
    path('suppliers/<uuid:supplier_id>/delete/', views.supplier_delete, name='supplier_delete'),

    # Goods Received Notes
    path('grn/', views.grn_list, name='grn_list'),
    path('grn/new/', views.grn_create, name='grn_create'),
    path('grn/<uuid:grn_id>/', views.grn_detail, name='grn_detail'),
    path('grn/<uuid:grn_id>/confirm/', views.grn_confirm, name='grn_confirm'),

    # Frame stocktake
    path('stocktake/', views.frame_stocktake_list, name='frame_stocktake_list'),
    path('stocktake/new/', views.frame_stocktake_create, name='frame_stocktake_create'),
    path('stocktake/<uuid:stocktake_id>/', views.frame_stocktake_detail, name='frame_stocktake_detail'),
    path('stocktake/<uuid:stocktake_id>/finalize/', views.frame_stocktake_finalize, name='frame_stocktake_finalize'),

    # Min stock alerts
    path('min-stock-alerts/', views.min_stock_alerts, name='min_stock_alerts'),

    # Sales report & analytics
    path('sales-report/', views.sales_report, name='sales_report'),

    # Patient optical history
    path('patient/<uuid:patient_id>/history/', views.patient_optical_history, name='patient_optical_history'),
]
