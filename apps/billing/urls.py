from django.urls import path
from . import views

app_name = 'billing'

urlpatterns = [
    path('', views.billing_dashboard, name='dashboard'),
    path('reports/', views.reports_index, name='reports_index'),
    path('pos/', views.pos_landing, name='pos_landing'),
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/new/', views.invoice_create, name='invoice_create'),
    path('invoices/<uuid:invoice_id>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<uuid:invoice_id>/pay/', views.add_payment, name='add_payment'),
    path('invoices/<uuid:invoice_id>/cancel/', views.cancel_invoice, name='cancel_invoice'),
    path('invoices/<uuid:invoice_id>/waive/', views.waive_invoice, name='waive_invoice'),
    path('invoices/<uuid:invoice_id>/void-draft/', views.void_draft_invoice, name='void_draft_invoice'),

    # POS (Point of Sale)
    path('pos/queue/', views.cashier_queue, name='cashier_queue'),
    path('pos/<uuid:token_id>/', views.cashier_pos, name='cashier_pos'),
    path('pos/<uuid:token_id>/finalize/', views.pos_finalize, name='pos_finalize'),
    # QMS-independent POS (works when QMS is off or patient has no token)
    path('pos/patient/<str:patient_id>/', views.patient_pos, name='patient_pos'),
    path('finalize/patient/<str:patient_id>/', views.patient_finalize, name='patient_finalize'),
    path('invoice/<uuid:invoice_id>/add-item/', views.pos_add_item, name='pos_add_item'),
    path('invoice/<uuid:invoice_id>/discount/', views.pos_apply_discount, name='pos_apply_discount'),
    path('item/<uuid:item_id>/remove/', views.pos_remove_item, name='pos_remove_item'),
    path('item/<uuid:item_id>/edit/', views.pos_edit_item, name='pos_edit_item'),
    path('invoice/<uuid:invoice_id>/record-payment/', views.pos_record_payment, name='pos_record_payment'),
    path('receipt/<uuid:invoice_id>/', views.receipt_view, name='receipt'),

    # Surgical deposit
    path('surgical-deposit/<uuid:booking_id>/', views.surgical_deposit, name='surgical_deposit'),
    path('surgical-deposit/<uuid:booking_id>/receipt/', views.surgical_deposit_receipt, name='surgical_deposit_receipt'),
    path('surgical-deposit/<uuid:booking_id>/return-checkin/', views.surgical_return_checkin, name='surgical_return_checkin'),

    # Refund
    path('invoices/<uuid:invoice_id>/refund/', views.process_refund, name='process_refund'),

    # Financial reports
    path('reports/ar-aging/', views.ar_aging_report, name='ar_aging'),
    path('reports/reconciliation/', views.cashier_reconciliation, name='reconciliation'),

    # Cashier Shift management
    path('shifts/', views.shift_list, name='shift_list'),
    path('shifts/my/', views.my_shift, name='my_shift'),
    path('shifts/open/', views.shift_open, name='shift_open'),
    path('shifts/open-day/', views.shift_day_open, name='shift_day_open'),
    path('shifts/<uuid:shift_id>/', views.shift_detail, name='shift_detail'),
    path('shifts/<uuid:shift_id>/close/', views.shift_close, name='shift_close'),
    path('shifts/<uuid:shift_id>/submit/', views.shift_submit, name='shift_submit'),
    path('shifts/<uuid:shift_id>/transfer/', views.shift_transfer, name='shift_transfer'),
    path('shifts/<uuid:shift_id>/verify/', views.shift_verify, name='shift_verify'),
    path('shifts/<uuid:shift_id>/reopen/', views.shift_reopen, name='shift_reopen'),
    path('shifts/<uuid:shift_id>/force-close/', views.shift_force_close, name='shift_force_close'),

    # SLA breach API
    path('api/waiting-sla/', views.waiting_sla_json, name='waiting_sla_json'),

    # Work Order system — department queues after payment
    path('work-queue/', views.work_queue, name='work_queue'),
    path('work-orders/<uuid:wo_id>/done/', views.work_order_done, name='work_order_done'),

    # Doctor orders — created during consultation, billed at cashier
    path('doctor-orders/create/', views.doctor_order_create, name='doctor_order_create'),
    path('doctor-orders/<uuid:wo_id>/cancel/', views.doctor_order_cancel, name='doctor_order_cancel'),

    # ── Service Price (Charge Master) Management ──────────────────────────────
    path('service-prices/', views.service_price_list, name='service_price_list'),
    path('service-prices/create/', views.service_price_create, name='service_price_create'),
    path('service-prices/<uuid:price_id>/edit/', views.service_price_edit, name='service_price_edit'),
    path('service-prices/<uuid:price_id>/form/', views.service_price_edit_form, name='service_price_edit_form'),
    path('service-prices/<uuid:price_id>/toggle/', views.service_price_toggle, name='service_price_toggle'),

    # ── Service Sub-Categories ───────────────────────────────────────────────
    path('sub-categories/', views.sub_category_list, name='sub_category_list'),
    path('sub-categories/create/', views.sub_category_create, name='sub_category_create'),
    path('sub-categories/<uuid:sub_id>/edit/', views.sub_category_edit, name='sub_category_edit'),
    path('sub-categories/<uuid:sub_id>/delete/', views.sub_category_delete, name='sub_category_delete'),

    # ── Revenue Analysis ─────────────────────────────────────────────────────
    path('reports/revenue-analysis/', views.revenue_analysis, name='revenue_analysis'),

    # ── Expense Management ────────────────────────────────────────────────────
    path('expenses/', views.expense_list, name='expense_list'),
    path('expenses/create/', views.expense_create, name='expense_create'),
    path('expenses/<uuid:expense_id>/delete/', views.expense_delete, name='expense_delete'),
    path('expenses/<uuid:expense_id>/approve/', views.expense_approve, name='expense_approve'),

    # ── Corporate Account Management ──────────────────────────────────────────
    path('corporate/', views.corporate_list, name='corporate_list'),
    path('corporate/create/', views.corporate_create, name='corporate_create'),
    path('corporate/<uuid:account_id>/', views.corporate_detail, name='corporate_detail'),
    path('corporate/<uuid:account_id>/add-member/', views.corporate_add_member, name='corporate_add_member'),
    path('corporate/member/<uuid:member_id>/remove/', views.corporate_remove_member, name='corporate_remove_member'),
    path('corporate/<uuid:account_id>/statement/', views.corporate_statement, name='corporate_statement'),

    # ── Petty Cash Management ─────────────────────────────────────────────────
    path('petty-cash/', views.petty_cash_list, name='petty_cash_list'),
    path('petty-cash/create/', views.petty_cash_create, name='petty_cash_create'),
    path('petty-cash/<uuid:fund_id>/', views.petty_cash_detail, name='petty_cash_detail'),
    path('petty-cash/<uuid:fund_id>/entry/', views.petty_cash_entry, name='petty_cash_entry'),

    # ── Financial Reports ─────────────────────────────────────────────────────
    path('reports/daily/', views.report_daily_summary, name='report_daily_summary'),
    path('reports/pl/', views.report_pl, name='report_pl'),
    path('reports/top-services/', views.report_top_services, name='report_top_services'),

    # ── Budget Module ─────────────────────────────────────────────────────────
    path('budget/', views.budget_list, name='budget_list'),
    path('budget/create/', views.budget_create, name='budget_create'),
    path('budget/<uuid:budget_id>/delete/', views.budget_delete, name='budget_delete'),
    path('budget/<uuid:budget_id>/amend/', views.budget_amend, name='budget_amend'),
    path('budget/<uuid:budget_id>/amendments/', views.budget_amendment_history, name='budget_amendment_history'),

    # ── Insurance split ───────────────────────────────────────────────────────
    path('invoice/<uuid:invoice_id>/insurance/', views.invoice_set_insurance, name='invoice_set_insurance'),

    # ── All-Cashdesks Overview ────────────────────────────────────────────────
    path('cashdesks/', views.cashdesks_overview, name='cashdesks_overview'),

    # ── Sales Journal ─────────────────────────────────────────────────────────
    path('reports/sales-journal/', views.sales_journal, name='sales_journal'),

    # ── Proforma Invoices ─────────────────────────────────────────────────────
    path('proforma/', views.proforma_list, name='proforma_list'),
    path('proforma/create/', views.proforma_create, name='proforma_create'),
    path('proforma/<uuid:proforma_id>/', views.proforma_detail, name='proforma_detail'),
    path('proforma/<uuid:proforma_id>/convert/', views.proforma_convert, name='proforma_convert'),
    path('proforma/<uuid:proforma_id>/cancel/', views.proforma_cancel, name='proforma_cancel'),
    path('proforma/<uuid:proforma_id>/pdf/', views.proforma_pdf, name='proforma_pdf'),

    # ── Audit Registers ───────────────────────────────────────────────────────
    path('reports/void-register/', views.void_register, name='void_register'),
    path('payments/<uuid:payment_id>/receipt/', views.payment_receipt, name='payment_receipt'),

    # ── Patient Financial History ─────────────────────────────────────────────
    path('patient-accounts/', views.patient_financial_history, name='patient_financial_history'),

    # ── Patient Wallet (Pre-payment Accounts) ────────────────────────────────
    path('wallets/', views.wallet_list, name='wallet_list'),
    path('wallets/search/', views.wallet_search_ajax, name='wallet_search_ajax'),
    path('wallets/<str:patient_id>/', views.wallet_detail, name='wallet_detail'),
    path('wallets/<str:patient_id>/deposit/', views.wallet_deposit, name='wallet_deposit'),
    path('wallets/<str:patient_id>/deduct/', views.wallet_deduct, name='wallet_deduct'),

    # ── Asset Register ────────────────────────────────────────────────────────
    path('assets/', views.asset_list, name='asset_list'),
    path('assets/depreciation/run/', views.trigger_depreciation_run, name='trigger_depreciation_run'),
    path('assets/create/', views.asset_create, name='asset_create'),
    path('assets/<uuid:asset_id>/edit/', views.asset_edit, name='asset_edit'),

    # General Ledger
    path('gl/accounts/', views.chart_of_accounts, name='chart_of_accounts'),
    path('gl/accounts/create/', views.gl_account_create, name='gl_account_create'),
    path('gl/accounts/<uuid:account_id>/edit/', views.gl_account_edit, name='gl_account_edit'),
    path('gl/accounts/<uuid:account_id>/delete/', views.gl_account_delete, name='gl_account_delete'),
    path('gl/journal/', views.journal_entry_list, name='journal_entry_list'),
    path('gl/journal/create/', views.journal_entry_create, name='journal_entry_create'),
    path('gl/journal/ai-suggest/', views.journal_ai_suggest, name='journal_ai_suggest'),
    path('gl/journal/<uuid:entry_id>/', views.journal_entry_detail, name='journal_entry_detail'),
    path('gl/journal/<uuid:entry_id>/review/', views.journal_entry_review, name='journal_entry_review'),
    path('gl/journal/<uuid:entry_id>/post/', views.journal_entry_post, name='journal_entry_post'),
    path('gl/journal/<uuid:entry_id>/reject/', views.journal_entry_reject, name='journal_entry_reject'),
    # Journal Types
    path('gl/journal-types/', views.journal_type_list, name='journal_type_list'),
    path('gl/journal-types/create/', views.journal_type_create, name='journal_type_create'),
    path('gl/journal-types/<uuid:jt_id>/edit/', views.journal_type_edit, name='journal_type_edit'),
    # GL Configuration Hub — consolidated single page (replaces 6 separate pages)
    path('gl/hub/', views.gl_config_hub, name='gl_config_hub'),
    # GL Setup Overview — single page showing full configuration chain
    path('gl/setup-overview/', views.gl_setup_overview, name='gl_setup_overview'),
    # Item Category GL Routing (automatic account resolution — Finance Director sets once)
    path('gl/item-category-gl/', views.item_category_gl_list, name='item_category_gl_list'),
    path('gl/item-category-gl/<str:category>/edit/', views.item_category_gl_edit, name='item_category_gl_edit'),
    path('gl/operation-cc-mapping/', views.operation_cc_mapping, name='operation_cc_mapping'),
    # BillingOperationCC full CRUD
    path('gl/operations/', views.billing_operation_list, name='billing_operation_list'),
    path('gl/operations/create/', views.billing_operation_create, name='billing_operation_create'),
    path('gl/operations/<uuid:op_id>/', views.billing_operation_detail, name='billing_operation_detail'),
    path('gl/operations/<uuid:op_id>/edit/', views.billing_operation_edit, name='billing_operation_edit'),
    # Stock Operation Types (exception/special operations only)
    path('gl/stock-operation-types/', views.stock_operation_type_list, name='stock_operation_type_list'),
    path('gl/stock-operation-types/create/', views.stock_operation_type_create, name='stock_operation_type_create'),
    path('gl/stock-operation-types/<uuid:sot_id>/edit/', views.stock_operation_type_edit, name='stock_operation_type_edit'),
    # Cost Centers
    path('gl/cost-centers/', views.cost_center_list, name='cost_center_list'),
    path('gl/cost-centers/create/', views.cost_center_create, name='cost_center_create'),
    path('gl/cost-centers/<uuid:center_id>/edit/', views.cost_center_edit, name='cost_center_edit'),
    path('gl/cost-center-pl/', views.cost_center_pl_report, name='cost_center_pl_report'),
    path('gl/ledger/', views.general_ledger, name='general_ledger'),
    path('gl/trial-balance/', views.trial_balance, name='trial_balance'),
    path('gl/auxiliary-balance/', views.auxiliary_balance, name='auxiliary_balance'),
    path('gl/balance-sheet/', views.balance_sheet, name='balance_sheet'),
    path('gl/cash-flow/', views.cash_flow_statement, name='cash_flow_statement'),
    path('gl/voucher-balance/', views.voucher_wise_balance, name='voucher_wise_balance'),
    path('reports/ap-aging/', views.ap_aging_report, name='ap_aging'),
    path('reports/customer-ledger/', views.customer_ledger_summary, name='customer_ledger_summary'),
    path('reports/gross-profit/', views.gross_profit_report, name='gross_profit'),
    path('reports/gross-net-profit/', views.gross_net_profit_report, name='gross_net_profit'),
    path('reports/profitability/', views.profitability_analysis, name='profitability_analysis'),
    path('reports/ar-summary/', views.ar_summary_report, name='ar_summary'),
    path('reports/supplier-ledger/', views.supplier_ledger_summary, name='supplier_ledger_summary'),

    # Accounts Payable
    path('ap/vendors/', views.ap_vendor_list, name='ap_vendor_list'),
    path('ap/vendors/create/', views.ap_vendor_create, name='ap_vendor_create'),
    path('ap/vendors/<uuid:vendor_id>/edit/', views.ap_vendor_edit, name='ap_vendor_edit'),
    path('ap/bills/', views.ap_bill_list, name='ap_bill_list'),
    path('ap/bills/create/', views.ap_bill_create, name='ap_bill_create'),
    path('ap/bills/<uuid:bill_id>/', views.ap_bill_detail, name='ap_bill_detail'),
    path('ap/bills/<uuid:bill_id>/pay/', views.ap_bill_pay, name='ap_bill_pay'),

    # ── Advanced Tier-Scoped Cashier Desk Module ──────────────────────────────
    path('desks/', views.desk_list, name='desk_list'),
    path('desks/create/', views.desk_create, name='desk_create'),
    path('desks/<uuid:desk_id>/edit/', views.desk_edit, name='desk_edit'),
    path('desks/<uuid:desk_id>/toggle/', views.desk_toggle, name='desk_toggle'),
    path('desks/<uuid:desk_id>/queue/', views.desk_cashier_queue, name='desk_queue'),

    # Cashier Sessions
    path('sessions/', views.session_list, name='session_list'),
    path('sessions/open/', views.session_open, name='session_open'),
    path('sessions/mine/', views.my_session, name='my_session'),
    path('sessions/<uuid:session_id>/', views.session_detail, name='session_detail'),
    path('sessions/<uuid:session_id>/close/', views.session_close, name='session_close'),
    path('sessions/<uuid:session_id>/verify/', views.session_verify, name='session_verify'),
    path('sessions/<uuid:session_id>/edit-float/', views.session_edit_float, name='session_edit_float'),
    path('sessions/<uuid:session_id>/void/', views.session_void, name='session_void'),

    # Discount Approvals
    path('invoice/<uuid:invoice_id>/discount-request/', views.discount_request, name='discount_request'),
    path('discounts/', views.discount_approval_list, name='discount_approval_list'),
    path('discounts/<uuid:approval_id>/decide/', views.discount_decide, name='discount_decide'),

    # Invoice Tier Rerouting
    path('invoice/<uuid:invoice_id>/reroute-tier/', views.invoice_reroute_tier, name='invoice_reroute_tier'),

    # Change Service Type (Changement Type Prestation)
    path('invoice/<uuid:invoice_id>/change-service-type/', views.invoice_change_service_type, name='invoice_change_service_type'),

    # Revenue by Desk Report
    path('reports/revenue-by-desk/', views.revenue_by_desk, name='revenue_by_desk'),

    # ── CSV Exports ───────────────────────────────────────────────────────────
    path('export/invoices/', views.export_invoice_list, name='export_invoice_list'),
    path('export/ar-aging/', views.export_ar_aging, name='export_ar_aging'),
    path('export/expenses/', views.export_expense_list, name='export_expense_list'),
    path('export/shifts/', views.export_shift_list, name='export_shift_list'),
    path('export/service-prices/', views.export_service_prices, name='export_service_prices'),
    path('export/sales-journal/', views.export_sales_journal, name='export_sales_journal'),
    path('export/void-register/', views.export_void_register, name='export_void_register'),
    path('export/corporate/', views.export_corporate_list, name='export_corporate_list'),
    path('export/patient-financial/', views.export_patient_financial, name='export_patient_financial'),

    # ═══════════════════════════════════════════════════════════════════════════
    # BANK OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════
    path('bank/accounts/', views.bank_account_list, name='bank_account_list'),
    path('bank/accounts/create/', views.bank_account_create, name='bank_account_create'),
    path('bank/accounts/<uuid:account_id>/edit/', views.bank_account_edit, name='bank_account_edit'),
    path('bank/statements/import/', views.bank_statement_import, name='bank_statement_import'),
    path('bank/reconciliation/', views.bank_reconciliation_list, name='bank_reconciliation_list'),
    path('bank/reconciliation/create/', views.bank_reconciliation_create, name='bank_reconciliation_create'),
    path('bank/reconciliation/<uuid:recon_id>/', views.bank_reconciliation_detail, name='bank_reconciliation_detail'),
    path('bank/reconciliation/<uuid:recon_id>/complete/', views.bank_reconciliation_complete, name='bank_reconciliation_complete'),
    path('bank/reconciliation/<uuid:recon_id>/review/', views.bank_reconciliation_review, name='bank_reconciliation_review'),
    path('bank/accounts/<uuid:account_id>/auto-match/', views.bank_statement_auto_match, name='bank_statement_auto_match'),

    # ── Cash-to-Bank Deposits ───────────────────────────────────────────────
    path('bank/deposits/', views.cash_to_bank_list, name='cash_to_bank_list'),
    path('bank/deposits/create/', views.cash_to_bank_create, name='cash_to_bank_create'),
    path('bank/deposits/<uuid:deposit_id>/confirm/', views.cash_to_bank_confirm, name='cash_to_bank_confirm'),

    # ═══════════════════════════════════════════════════════════════════════════
    # CHEQUE MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════
    path('cheques/books/', views.chequebook_list, name='chequebook_list'),
    path('cheques/books/create/', views.chequebook_create, name='chequebook_create'),
    path('cheques/register/', views.cheque_register, name='cheque_register'),
    path('cheques/issue/', views.cheque_issue, name='cheque_issue'),
    path('cheques/<uuid:cheque_id>/void/', views.cheque_void, name='cheque_void'),
    path('cheques/<uuid:cheque_id>/clear/', views.cheque_clear, name='cheque_clear'),

    # ═══════════════════════════════════════════════════════════════════════════
    # STAFF ADVANCES
    # ═══════════════════════════════════════════════════════════════════════════
    path('advances/', views.advance_list, name='advance_list'),
    path('advances/request/', views.advance_request, name='advance_request'),
    path('advances/<uuid:advance_id>/', views.advance_detail, name='advance_detail'),
    path('advances/<uuid:advance_id>/approve/', views.advance_approve, name='advance_approve'),
    path('advances/<uuid:advance_id>/reject/', views.advance_reject, name='advance_reject'),
    path('advances/<uuid:advance_id>/disburse/', views.advance_disburse, name='advance_disburse'),
    path('advances/<uuid:advance_id>/settle/', views.advance_settle, name='advance_settle'),

    # ═══════════════════════════════════════════════════════════════════════════
    # CASH TRANSFERS & SAFE
    # ═══════════════════════════════════════════════════════════════════════════
    path('cash/transfers/', views.cash_transfer_list, name='cash_transfer_list'),
    path('cash/transfers/create/', views.cash_transfer_create, name='cash_transfer_create'),
    path('cash/transfers/<uuid:transfer_id>/confirm/', views.cash_transfer_confirm, name='cash_transfer_confirm'),
    path('cash/safe/', views.safe_balance_list, name='safe_balance_list'),
    path('cash/safe/record/', views.safe_balance_record, name='safe_balance_record'),

    # ═══════════════════════════════════════════════════════════════════════════
    # CASH VARIANCE REGISTER
    # ═══════════════════════════════════════════════════════════════════════════
    path('reports/variance-register/', views.variance_register, name='variance_register'),
    path('reports/variance/<uuid:variance_id>/resolve/', views.variance_resolve, name='variance_resolve'),

    # ═══════════════════════════════════════════════════════════════════════════
    # ASSET DISPOSAL
    # ═══════════════════════════════════════════════════════════════════════════
    path('assets/<uuid:asset_id>/dispose/', views.asset_dispose, name='asset_dispose'),
    path('assets/disposals/', views.asset_disposal_list, name='asset_disposal_list'),
    path('assets/disposals/<uuid:disposal_id>/action/', views.asset_disposal_approve, name='asset_disposal_approve'),

    # ═══════════════════════════════════════════════════════════════════════════
    # ADVANCED FINANCIAL REPORTS
    # ═══════════════════════════════════════════════════════════════════════════
    path('reports/liquidity/', views.report_daily_liquidity, name='report_daily_liquidity'),
    path('reports/surgery-revenue/', views.report_surgery_revenue, name='report_surgery_revenue'),
    path('reports/surgical-cost-summary/', views.surgical_cost_summary, name='surgical_cost_summary'),
    path('reports/revenue-by-department/', views.report_revenue_by_department, name='report_revenue_by_department'),
    path('reports/donor/', views.report_donor, name='report_donor'),
    path('reports/dsf/', views.report_dsf, name='report_dsf'),

    # ═══════════════════════════════════════════════════════════════════════════
    # BUDGET ENHANCEMENT
    # ═══════════════════════════════════════════════════════════════════════════
    path('budget/annual-create/', views.budget_annual_create, name='budget_annual_create'),
    path('reports/budget-ytd/', views.budget_ytd_report, name='budget_ytd_report'),

    # ═══════════════════════════════════════════════════════════════════════════
    # ADDITIONAL FINANCIAL REPORTS (International Standards)
    # ═══════════════════════════════════════════════════════════════════════════
    path('reports/ap-aging/', views.report_ap_aging, name='report_ap_aging'),
    path('reports/monthly-summary/', views.report_monthly_summary, name='report_monthly_summary'),
    path('reports/tva/', views.report_tva, name='report_tva'),
    path('reports/audit-trail/', views.report_audit_trail, name='report_audit_trail'),

    # ═══════════════════════════════════════════════════════════════════════════
    # FISCAL PERIOD MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════
    path('fiscal-periods/', views.fiscal_period_list, name='fiscal_period_list'),
    path('fiscal-periods/<uuid:period_id>/action/', views.fiscal_period_action, name='fiscal_period_action'),

    # ═══════════════════════════════════════════════════════════════════════════
    # GL MAPPING SETTINGS (System Admin)
    # ═══════════════════════════════════════════════════════════════════════════
    path('gl/mappings/', views.gl_mapping_list, name='gl_mapping_list'),
    path('gl/mappings/seed/', views.gl_mapping_seed, name='gl_mapping_seed'),

    # ═══════════════════════════════════════════════════════════════════════════
    # ROLE DASHBOARDS
    # ═══════════════════════════════════════════════════════════════════════════
    path('dashboard/finance-director/', views.finance_director_dashboard, name='finance_director_dashboard'),
    path('dashboard/senior-accountant/', views.senior_accountant_dashboard, name='senior_accountant_dashboard'),

    # ═══════════════════════════════════════════════════════════════════════════
    # MONTH-END CLOSE
    # ═══════════════════════════════════════════════════════════════════════════
    path('month-end/', views.month_end_list, name='month_end_list'),
    path('month-end/create/', views.month_end_create, name='month_end_create'),
    path('month-end/<uuid:close_id>/', views.month_end_detail, name='month_end_detail'),

    # ═══════════════════════════════════════════════════════════════════════════
    # CASH COUNT SHEET
    # ═══════════════════════════════════════════════════════════════════════════
    path('cash-count/', views.cash_count_list, name='cash_count_list'),
    path('cash-count/create/', views.cash_count_create, name='cash_count_create'),

    # ═══════════════════════════════════════════════════════════════════════════
    # DEPRECIATION RUNS
    # ═══════════════════════════════════════════════════════════════════════════
    path('depreciation/', views.depreciation_run_list, name='depreciation_run_list'),
    path('depreciation/create/', views.depreciation_run_create, name='depreciation_run_create'),
    path('depreciation/<uuid:run_id>/', views.depreciation_run_detail, name='depreciation_run_detail'),

    # ═══════════════════════════════════════════════════════════════════════════
    # WITHHOLDING TAX (IRC / TSR)
    # ═══════════════════════════════════════════════════════════════════════════
    path('withholding-tax/', views.withholding_tax_list, name='withholding_tax_list'),
    path('withholding-tax/create/', views.withholding_tax_create, name='withholding_tax_create'),
    path('withholding-tax/<uuid:wht_id>/remit/', views.withholding_tax_remit, name='withholding_tax_remit'),

    # ═══════════════════════════════════════════════════════════════════════════
    # SYSCOHADA BILAN + CASH FLOW FORECAST
    # ═══════════════════════════════════════════════════════════════════════════
    path('reports/syscohada-bilan/', views.syscohada_bilan, name='syscohada_bilan'),
    path('reports/cash-flow-forecast/', views.cash_flow_forecast, name='cash_flow_forecast'),

    # ═══════════════════════════════════════════════════════════════════════════
    # ENHANCED CASH MANAGEMENT (Retraits, Approvisionnement, Extourne)
    # ═══════════════════════════════════════════════════════════════════════════
    path('cash/operation-types/', views.cash_operation_type_list, name='cash_operation_type_list'),
    path('cash/operation-types/create/', views.cash_operation_type_create, name='cash_operation_type_create'),
    path('cash/operation-types/<uuid:type_id>/edit/', views.cash_operation_type_edit, name='cash_operation_type_edit'),
    path('cash/withdrawals/', views.cash_withdrawal_list, name='cash_withdrawal_list'),
    path('cash/withdrawals/create/', views.cash_withdrawal_create, name='cash_withdrawal_create'),
    path('cash/withdrawals/multi/', views.cash_withdrawal_multi_create, name='cash_withdrawal_multi_create'),
    path('cash/withdrawals/patient/', views.cash_withdrawal_patient, name='cash_withdrawal_patient'),
    path('cash/withdrawals/reverse/', views.cash_withdrawal_reverse, name='cash_withdrawal_reverse'),
    path('cash/supply/', views.cash_desk_supply_list, name='cash_desk_supply_list'),
    path('cash/supply/create/', views.cash_desk_supply_create, name='cash_desk_supply_create'),
    path('api/cash-desk-balance/', views.cash_desk_balance_ajax, name='cash_desk_balance_ajax'),

    # ═══════════════════════════════════════════════════════════════════════════
    # ASSET MAINTENANCE
    # ═══════════════════════════════════════════════════════════════════════════
    path('maintenance/', views.maintenance_list, name='maintenance_list'),
    path('maintenance/schedules/', views.maintenance_schedule_list, name='maintenance_schedule_list'),
    path('assets/<uuid:asset_id>/maintenance/schedule/', views.maintenance_schedule_create, name='maintenance_schedule_create'),
    path('assets/<uuid:asset_id>/maintenance/create/', views.maintenance_wo_create, name='maintenance_wo_create'),
    path('maintenance/<uuid:wo_id>/complete/', views.maintenance_wo_complete, name='maintenance_wo_complete'),
]
