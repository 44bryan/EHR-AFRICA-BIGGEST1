from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('procurement/', views.procurement_dashboard, name='procurement_dashboard'),

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

    # Inter-Store Transfers
    path('transfers/', views.transfer_list, name='transfer_list'),
    path('transfers/create/', views.transfer_create, name='transfer_create'),
    path('transfers/<uuid:transfer_id>/', views.transfer_detail, name='transfer_detail'),
    path('transfers/<uuid:transfer_id>/approve/', views.transfer_approve, name='transfer_approve'),
    path('transfers/<uuid:transfer_id>/dispatch/', views.transfer_dispatch, name='transfer_dispatch'),
    path('transfers/<uuid:transfer_id>/receive/', views.transfer_receive, name='transfer_receive'),
    path('transfers/<uuid:transfer_id>/cancel/', views.transfer_cancel, name='transfer_cancel'),

    # Goods Received Notes (GRN)
    path('grn/', views.grn_list, name='grn_list'),
    path('grn/create/', views.grn_create, name='grn_create'),
    path('grn/<uuid:grn_id>/', views.grn_detail, name='grn_detail'),
    path('grn/<uuid:grn_id>/accept/', views.grn_accept, name='grn_accept'),
    path('grn/<uuid:grn_id>/reject/', views.grn_reject, name='grn_reject'),

    # Disposal Workflow
    path('disposal/', views.disposal_list, name='disposal_list'),
    path('disposal/create/', views.disposal_create, name='disposal_create'),
    path('disposal/<uuid:disposal_id>/', views.disposal_detail, name='disposal_detail'),
    path('disposal/<uuid:disposal_id>/authorize/', views.disposal_authorize, name='disposal_authorize'),
    path('disposal/<uuid:disposal_id>/dispose/', views.disposal_dispose, name='disposal_dispose'),
    path('disposal/<uuid:disposal_id>/reject/', views.disposal_reject, name='disposal_reject'),

    # Stock Take Schedule
    path('schedule/', views.schedule_list, name='schedule_list'),
    path('schedule/create/', views.schedule_create, name='schedule_create'),
    path('schedule/<uuid:schedule_id>/start/', views.schedule_start_count, name='schedule_start_count'),

    # Reports
    path('reports/valuation/', views.report_stock_valuation, name='report_valuation'),
    path('reports/movements/', views.report_movement_history, name='report_movements'),
    path('reports/consumption/', views.report_consumption_by_dept, name='report_consumption'),
    path('reports/expiry/', views.report_expiry_alert, name='report_expiry'),
    path('reports/vendors/', views.report_vendor_performance, name='report_vendors'),
    path('reports/abc/', views.report_abc_analysis, name='report_abc'),

    # ── NEW: Stats / Analytics ───────────────────────────────────────
    path('stats/', views.stats, name='stats'),

    # ── NEW: Movement Log ────────────────────────────────────────────
    path('movement-log/', views.movement_log, name='movement_log'),

    # ── NEW: Receive Stock (walk-in) ─────────────────────────────────
    path('receive-stock/', views.receive_stock, name='receive_stock'),

    # ── NEW: Alerts ──────────────────────────────────────────────────
    path('alerts/', views.alerts, name='alerts'),

    # ── NEW: Barcode Scan ────────────────────────────────────────────
    path('barcode/', views.barcode_scan, name='barcode_scan'),
    path('barcode/lookup/', views.barcode_lookup_ajax, name='barcode_lookup'),

    # ── NEW: Consignment Stock ───────────────────────────────────────
    path('consignment/', views.consignment_dashboard, name='consignment_dashboard'),

    # ── NEW: Supplier Quotations ─────────────────────────────────────
    path('quotations/', views.quotation_list, name='quotation_list'),
    path('quotations/create/', views.quotation_create, name='quotation_create'),
    path('quotations/compare/', views.quotation_compare, name='quotation_compare'),
    path('quotations/<uuid:rfq_id>/', views.quotation_detail, name='quotation_detail'),
    path('quotations/<uuid:rfq_id>/update/', views.quotation_update, name='quotation_update'),

    # ── NEW: Budget ──────────────────────────────────────────────────
    path('budget/', views.budget_list, name='budget_list'),
    path('budget/create/', views.budget_create, name='budget_create'),
    path('budget/<uuid:budget_id>/edit/', views.budget_edit, name='budget_edit'),

    # ── Stock Entry / Exit ─────────────────────────────────────────
    path('stock-exit/', views.stock_exit_list, name='stock_exit_list'),
    path('stock-exit/create/', views.stock_exit_create, name='stock_exit_create'),
    path('stock-entry/', views.stock_entry_list, name='stock_entry_list'),
    path('stock-entry/create/', views.stock_entry_create, name='stock_entry_create'),

    # ── 4-Eyes Stock Validation (Finance Director) ────────────────
    path('validations/', views.stock_validation_list, name='stock_validation_list'),
    path('validations/<uuid:validation_id>/', views.stock_validation_detail, name='stock_validation_detail'),
    path('validations/<uuid:validation_id>/approve/', views.stock_validation_approve, name='stock_validation_approve'),
    path('validations/<uuid:validation_id>/reject/', views.stock_validation_reject, name='stock_validation_reject'),

    # ── Stock Card / Bin Card / Stock Ledger ───────────────────
    path('items/<uuid:item_id>/stock-card/', views.stock_card, name='stock_card'),
    path('items/<uuid:item_id>/bin-card/', views.bin_card, name='bin_card'),
    path('stock-ledger/', views.stock_ledger, name='stock_ledger'),

    # ── Annual Stock Take Report ───────────────────────────────
    path('reports/annual-stock-take/', views.annual_stock_take_report, name='report_annual_stock_take'),

    # ── PO Finance Approval ────────────────────────────────────
    path('purchase-orders/<uuid:po_id>/finance-approve/', views.po_finance_approve, name='po_finance_approve'),
    path('purchase-orders/<uuid:po_id>/finance-reject/', views.po_finance_reject, name='po_finance_reject'),

    # ── Supplier Invoices ──────────────────────────────────────
    path('supplier-invoices/', views.supplier_invoice_list, name='supplier_invoice_list'),
    path('supplier-invoices/create/', views.supplier_invoice_create, name='supplier_invoice_create'),
    path('supplier-invoices/<uuid:invoice_id>/', views.supplier_invoice_detail, name='supplier_invoice_detail'),

    # ── 3-Way Match ────────────────────────────────────────────
    path('three-way-match/', views.three_way_match_list, name='three_way_match_list'),
    path('three-way-match/create/', views.three_way_match_create, name='three_way_match_create'),
    path('three-way-match/<uuid:match_id>/', views.three_way_match_detail, name='three_way_match_detail'),
    path('three-way-match/<uuid:match_id>/resolve/', views.three_way_match_resolve, name='three_way_match_resolve'),
]
