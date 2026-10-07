"""Test all Senior Accountant + Store Keeper sidebar URLs on production — runs ON server."""
import sys, os, django
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.base'
django.setup()

from django.test import RequestFactory, Client
from apps.accounts.models import User

def test_role_urls(username, url_list):
    c = Client()
    user = User.objects.filter(username=username, is_active=True).first()
    if not user:
        print(f'  User "{username}" not found!')
        return
    c.force_login(user)
    failures = []
    ok = 0
    for label, url in url_list:
        try:
            r = c.get(url, follow=False)
            code = r.status_code
            if code == 200:
                ok += 1
            elif code in (301, 302):
                loc = r.get('Location', '')
                if 'login' in loc:
                    failures.append(f'  REDIRECT->login: {label} -> {url}')
                else:
                    ok += 1
            elif code == 403:
                failures.append(f'  403 FORBIDDEN: {label} -> {url}')
            elif code == 500:
                failures.append(f'  500 SERVER ERROR: {label} -> {url}')
            else:
                failures.append(f'  {code}: {label} -> {url}')
        except Exception as e:
            failures.append(f'  EXCEPTION: {label} -> {url} ({e})')

    print(f'  {ok}/{len(url_list)} OK')
    if failures:
        for f in failures:
            print(f)
    else:
        print('  All pages accessible!')
    return failures

from django.urls import reverse

# ── Senior Accountant URLs ──
sa_urls = [
    ('P&L', reverse('billing:report_pl')),
    ('Balance Sheet', reverse('billing:balance_sheet')),
    ('Cash Flow', reverse('billing:cash_flow_statement')),
    ('Trial Balance', reverse('billing:trial_balance')),
    ('Revenue Analysis', reverse('billing:revenue_analysis')),
    ('Chart of Accounts', reverse('billing:chart_of_accounts')),
    ('Journal Entries', reverse('billing:journal_entry_list')),
    ('General Ledger', reverse('billing:general_ledger')),
    ('Cost Centers', reverse('billing:cost_center_list')),
    ('Budget List', reverse('billing:budget_list')),
    ('Budget YTD', reverse('billing:budget_ytd_report')),
    ('Annual Budget', reverse('billing:budget_annual_create')),
    ('Invoice List', reverse('billing:invoice_list')),
    ('Sales Journal', reverse('billing:sales_journal')),
    ('AR Aging', reverse('billing:ar_aging')),
    ('Corporate List', reverse('billing:corporate_list')),
    ('Service Prices', reverse('billing:service_price_list')),
    ('Sub Categories', reverse('billing:sub_category_list')),
    ('Discount Approvals', reverse('billing:discount_approval_list')),
    ('Wallets', reverse('billing:wallet_list')),
    ('Patient Financial', reverse('billing:patient_financial_history')),
    ('Proforma List', reverse('billing:proforma_list')),
    ('AP Vendors', reverse('billing:ap_vendor_list')),
    ('AP Bills', reverse('billing:ap_bill_list')),
    ('AP Aging', reverse('billing:report_ap_aging')),
    ('Expenses', reverse('billing:expense_list')),
    ('Petty Cash', reverse('billing:petty_cash_list')),
    ('Advances', reverse('billing:advance_list')),
    ('Bank Accounts', reverse('billing:bank_account_list')),
    ('Bank Recon', reverse('billing:bank_reconciliation_list')),
    ('Cash to Bank', reverse('billing:cash_to_bank_list')),
    ('Cheque Books', reverse('billing:chequebook_list')),
    ('Cheque Register', reverse('billing:cheque_register')),
    ('Asset List', reverse('billing:asset_list')),
    ('Asset Disposals', reverse('billing:asset_disposal_list')),
    ('TVA Return', reverse('billing:report_tva')),
    ('Fiscal Periods', reverse('billing:fiscal_period_list')),
    ('Audit Trail', reverse('billing:report_audit_trail')),
    ('Void Register', reverse('billing:void_register')),
    ('Top Services', reverse('billing:report_top_services')),
    ('Revenue by Desk', reverse('billing:revenue_by_desk')),
    ('Surgery Revenue', reverse('billing:report_surgery_revenue')),
    ('Revenue by Dept', reverse('billing:report_revenue_by_department')),
    ('Daily Summary', reverse('billing:report_daily_summary')),
    ('Daily Liquidity', reverse('billing:report_daily_liquidity')),
    ('Monthly Summary', reverse('billing:report_monthly_summary')),
    ('Shifts', reverse('billing:shift_list')),
    ('Sessions', reverse('billing:session_list')),
    ('Reconciliation', reverse('billing:reconciliation')),
    ('Cash Transfers', reverse('billing:cash_transfer_list')),
    ('Safe Balance', reverse('billing:safe_balance_list')),
    ('Variance Register', reverse('billing:variance_register')),
    ('Stock Validations', reverse('inventory:stock_validation_list')),
    ('Stock Valuation', reverse('inventory:report_valuation')),
    ('Stock Ledger', reverse('inventory:stock_ledger')),
    ('ABC/VEN', reverse('inventory:report_abc')),
    ('Dept Consumption', reverse('inventory:report_consumption')),
    ('HMO Dashboard', reverse('hmo:dashboard')),
    ('Insurance Ledger', reverse('hmo:insurance_ledger')),
    ('Insurance Aging', reverse('hmo:insurance_aging')),
]

# ── Store Keeper URLs ──
sk_urls = [
    ('Dashboard', reverse('inventory:dashboard')),
    ('Stats', reverse('inventory:stats')),
    ('Alerts', reverse('inventory:alerts')),
    ('All Items', reverse('inventory:item_list')),
    ('Add Item', reverse('inventory:item_create')),
    ('Barcode Scan', reverse('inventory:barcode_scan')),
    ('Locations', reverse('inventory:store_location_list')),
    ('Stock Entry', reverse('inventory:stock_entry_list')),
    ('Stock Exit', reverse('inventory:stock_exit_list')),
    ('GRN', reverse('inventory:grn_list')),
    ('Transfers', reverse('inventory:transfer_list')),
    ('Movement Log', reverse('inventory:movement_log')),
    ('Requisitions', reverse('inventory:requisition_list')),
    ('New Requisition', reverse('inventory:requisition_create')),
    ('Returns', reverse('inventory:return_list')),
    ('Stock Count', reverse('inventory:stock_count_list')),
    ('Count Schedule', reverse('inventory:schedule_list')),
    ('Disposal', reverse('inventory:disposal_list')),
    ('Consignment', reverse('inventory:consignment_dashboard')),
    ('Stock Ledger', reverse('inventory:stock_ledger')),
    ('Stock Valuation', reverse('inventory:report_valuation')),
    ('Dept Consumption', reverse('inventory:report_consumption')),
    ('Expiry Report', reverse('inventory:report_expiry')),
    ('Vendor Performance', reverse('inventory:report_vendors')),
    ('ABC/VEN', reverse('inventory:report_abc')),
    ('Annual Stock Take', reverse('inventory:report_annual_stock_take')),
]

# Find users
sa_user = User.objects.filter(role='senior_accountant', is_active=True).first()
sk_user = User.objects.filter(role='store_keeper', is_active=True).first()

print(f'Senior Accountant: {sa_user.username if sa_user else "NONE"}')
print(f'Store Keeper: {sk_user.username if sk_user else "NONE"}')

if sa_user:
    print(f'\n=== SENIOR ACCOUNTANT ({sa_user.username}) ===')
    test_role_urls(sa_user.username, sa_urls)

if sk_user:
    print(f'\n=== STORE KEEPER ({sk_user.username}) ===')
    test_role_urls(sk_user.username, sk_urls)

if not sa_user:
    print('\nNo senior_accountant user found. Testing as admin instead.')
    print('\n=== ADMIN -> SA URLs ===')
    test_role_urls('admin', sa_urls)

if not sk_user:
    print('\nNo store_keeper user found. Testing as admin instead.')
    print('\n=== ADMIN -> SK URLs ===')
    test_role_urls('admin', sk_urls)
