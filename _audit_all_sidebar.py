"""Full audit of every sidebar URL — test with force_login as super_admin."""
import sys, os, django
sys.path.insert(0, "/opt/ehr-africa")
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.base"
django.setup()

from django.test.client import Client
from django.urls import reverse, NoReverseMatch
from apps.accounts.models import User

admin = User.objects.filter(is_superuser=True).first()
client = Client()
client.force_login(admin)

# Every URL name found in sidebar.html
sidebar_urls = [
    # billing
    "billing:advance_list",
    "billing:ar_aging",
    "billing:asset_disposal_list",
    "billing:asset_list",
    "billing:balance_sheet",
    "billing:bank_account_list",
    "billing:bank_reconciliation_list",
    "billing:budget_annual_create",
    "billing:budget_list",
    "billing:budget_ytd_report",
    "billing:cash_count_list",
    "billing:cash_flow_forecast",
    "billing:cash_flow_statement",
    "billing:cash_to_bank_list",
    "billing:cash_transfer_list",
    "billing:cashdesks_overview",
    "billing:cashier_queue",
    "billing:chart_of_accounts",
    "billing:cheque_register",
    "billing:chequebook_list",
    "billing:corporate_list",
    "billing:cost_center_list",
    "billing:cost_center_pl_report",
    "billing:dashboard",
    "billing:depreciation_run_list",
    "billing:desk_list",
    "billing:discount_approval_list",
    "billing:expense_list",
    "billing:finance_director_dashboard",
    "billing:fiscal_period_list",
    "billing:general_ledger",
    "billing:gl_mapping_list",
    "billing:invoice_create",
    "billing:invoice_list",
    "billing:journal_entry_list",
    "billing:journal_type_list",
    "billing:maintenance_list",
    "billing:month_end_list",
    "billing:my_session",
    "billing:my_shift",
    "billing:patient_financial_history",
    "billing:petty_cash_list",
    "billing:pos_landing",
    "billing:proforma_list",
    "billing:reconciliation",
    "billing:report_ap_aging",
    "billing:report_audit_trail",
    "billing:report_daily_liquidity",
    "billing:report_daily_summary",
    "billing:report_donor",
    "billing:report_dsf",
    "billing:report_monthly_summary",
    "billing:report_pl",
    "billing:report_surgery_revenue",
    "billing:report_top_services",
    "billing:report_tva",
    "billing:revenue_analysis",
    "billing:revenue_by_desk",
    "billing:safe_balance_list",
    "billing:sales_journal",
    "billing:senior_accountant_dashboard",
    "billing:service_price_list",
    "billing:session_list",
    "billing:shift_day_open",
    "billing:shift_list",
    "billing:stock_operation_type_list",
    "billing:sub_category_list",
    "billing:surgical_cost_summary",
    "billing:syscohada_bilan",
    "billing:trial_balance",
    "billing:variance_register",
    "billing:void_register",
    "billing:wallet_list",
    "billing:withholding_tax_list",
    # Other apps
    "accounts:staff_hub",
    "dashboard:home",
    "dashboard:sysadmin",
    "dashboard:health_check",
    "dashboard:recycle_bin",
    "dashboard:sysadmin_settings",
    "patients:list",
    "patients:register",
    "patients:access_audit",
    "patients:amendment_list",
    "patients:chart_deficiency",
    "patients:consent_review",
    "patients:document_review",
    "patients:duplicate_detection",
    "patients:emergency_register",
    "patients:prereg_lookup",
    "patients:prereg_management",
    "patients:record_release_list",
    "patients:registration_stats",
    "consultations:workstation",
    "consultations:clinic_nurse",
    "consultations:list",
    "consultations:patient_tracker",
    "consultations:template_list",
    "consultations:triage_workstation",
    "consultations:unit_queue",
    "consultations:vip_dashboard",
    "consultations:education_library",
    "investigations:list",
    "investigations:workstation",
    "investigations:stats",
    "investigations:imaging_list",
    "investigations:device_list",
    "investigations:machine_revenue",
    "investigations:staff_throughput",
    "investigations:unacknowledged",
    "pharmacy:dashboard",
    "pharmacy:drug_list",
    "pharmacy:dispensing_list",
    "pharmacy:patient_search",
    "pharmacy:direct_sale",
    "pharmacy:stats",
    "pharmacy:adr_list",
    "pharmacy:controlled_register",
    "pharmacy:supplier_list",
    "pharmacy:stock_movement_log",
    "pharmacy:expiry_alerts",
    "pharmacy:quick_reorder",
    "pharmacy:stocktake_list",
    "pharmacy:transfer_list",
    "pharmacy:stock_adjustment_list",
    "pharmacy:stock_exit_list",
    "pharmacy:location_list",
    "pharmacy:chronic_rx_list",
    "pharmacy:recall_list",
    "pharmacy:ward_return_list",
    "pharmacy:unavailable_lines",
    "pharmacy:drug_bulk_import",
    "pharmacy:purchase_order_list",
    "pharmacy:receive_stock",
    "pharmacy:report_abc",
    "pharmacy:report_consumption",
    "pharmacy:report_dead_stock",
    "pharmacy:report_expiring",
    "pharmacy:report_productivity",
    "pharmacy:report_sales_journal",
    "pharmacy:report_stock_situation",
    "pharmacy:report_supplier_history",
    "pharmacy:report_turnover",
    "pharmacy:report_ven",
    "pharmacy:cross_store_stock",
    "inventory:dashboard",
    "inventory:item_list",
    "inventory:item_create",
    "inventory:grn_list",
    "inventory:stock_entry_list",
    "inventory:stock_exit_list",
    "inventory:stock_count_list",
    "inventory:transfer_list",
    "inventory:disposal_list",
    "inventory:movement_log",
    "inventory:alerts",
    "inventory:stock_ledger",
    "inventory:barcode_scan",
    "inventory:store_location_list",
    "inventory:vendor_list",
    "inventory:po_list",
    "inventory:po_create",
    "inventory:quotation_list",
    "inventory:quotation_compare",
    "inventory:requisition_list",
    "inventory:requisition_create",
    "inventory:supplier_invoice_list",
    "inventory:three_way_match_list",
    "inventory:return_list",
    "inventory:recycle_bin",
    "inventory:budget_list",
    "inventory:consignment_dashboard",
    "inventory:procurement_dashboard",
    "inventory:schedule_list",
    "inventory:stock_validation_list",
    "inventory:report_abc",
    "inventory:report_consumption",
    "inventory:report_expiry",
    "inventory:report_valuation",
    "inventory:report_vendors",
    "inventory:report_annual_stock_take",
    "inventory:stats",
    "ipd:dashboard",
    "ipd:admit",
    "ipd:bed_map",
    "ipd:ward_list",
    "ipd:theatre_board",
    "ipd:surgical_booking_queue",
    "ipd:pre_op_checkin",
    "ipd:procedure_room_queue",
    "ipd:theatre_session_list",
    "ipd:counseling_queue",
    "ipd:anaesthetic_record_list",
    "ipd:surgical_outcome_list",
    "ipd:admission_stats",
    "ipd:registration_stats",
    "ipd:nursing_stats",
    "ipd:procedure_room_stats",
    "ipd:theatre_utilization",
    "ipd:journal_of_registrations",
    "departments:dept_list",
    "departments:room_list_all",
    "leadership:dashboard",
    "leadership:analytics_dashboard",
    "leadership:department_stats",
    "leadership:finance_dashboard",
    "leadership:hospital_stats",
    "leadership:monthly_stats",
    "leadership:retina_dashboard",
    "hmo:dashboard",
    "hmo:scheme_list",
    "hmo:member_list",
    "hmo:preauth_list",
    "hmo:claim_list",
    "hmo:batch_list",
    "hmo:insurance_aging",
    "hmo:insurance_ledger",
    "blood_bank:dashboard",
    "blood_bank:donor_list",
    "blood_bank:unit_list",
    "blood_bank:crossmatch_list",
    "blood_bank:issue_list",
    "infection_control:dashboard",
    "infection_control:hai_list",
    "infection_control:antibiogram",
    "infection_control:outbreak_list",
    "dietary:dashboard",
    "dietary:order_list",
    "mortuary:dashboard",
    "mortuary:admission_list",
    "mortuary:storage_list",
    "notifications:sms_log",
    "notifications:sms_send",
    "notifications:template_list",
    "opd:dashboard",
    "reception:desk",
    "reception:walk_in",
]

# Add QMS URLs
qms_urls = [
    "qms:dashboard", "qms:gate_issue", "qms:cashier_issue", "qms:receptionist",
    "qms:doctor_queue", "qms:express_desk", "qms:vip_reception",
    "qms:display_board", "qms:consult_room_display", "qms:my_counter",
    "qms:counter_manage", "qms:roster", "qms:room_checkin",
    "qms:daily_census", "qms:zone_manage",
]
sidebar_urls.extend(qms_urls)

# Test each URL
ok = []
fail_resolve = []
fail_500 = []
fail_403 = []
fail_302 = []
fail_other = []

for url_name in sidebar_urls:
    try:
        url = reverse(url_name)
    except NoReverseMatch:
        fail_resolve.append(url_name)
        continue

    try:
        resp = client.get(url)
        if resp.status_code == 200:
            ok.append(url_name)
        elif resp.status_code == 500:
            fail_500.append((url_name, url))
        elif resp.status_code == 403:
            fail_403.append((url_name, url))
        elif resp.status_code == 302:
            fail_302.append((url_name, url, resp.get("Location", "")))
        else:
            fail_other.append((url_name, url, resp.status_code))
    except Exception as e:
        err = str(e)[:150]
        fail_500.append((url_name, f"ERR: {err}"))

print(f"\n{'='*70}")
print(f"SIDEBAR AUDIT RESULTS")
print(f"{'='*70}")
print(f"  OK (200):          {len(ok)}")
print(f"  URL not found:     {len(fail_resolve)}")
print(f"  500 Server Error:  {len(fail_500)}")
print(f"  403 Forbidden:     {len(fail_403)}")
print(f"  302 Redirect:      {len(fail_302)}")
print(f"  Other:             {len(fail_other)}")
print(f"  TOTAL tested:      {len(sidebar_urls)}")

if fail_resolve:
    print(f"\n--- URL NAMES THAT DON'T RESOLVE (NoReverseMatch) ---")
    for name in fail_resolve:
        print(f"  {name}")

if fail_500:
    print(f"\n--- 500 SERVER ERRORS ---")
    for item in fail_500:
        print(f"  {item[0]:50s} {item[1]}")

if fail_403:
    print(f"\n--- 403 FORBIDDEN ---")
    for name, url in fail_403:
        print(f"  {name:50s} {url}")

if fail_302:
    print(f"\n--- 302 REDIRECTS ---")
    for name, url, loc in fail_302:
        print(f"  {name:50s} {url} -> {loc}")

if fail_other:
    print(f"\n--- OTHER ERRORS ---")
    for name, url, code in fail_other:
        print(f"  {name:50s} {url} -> {code}")
