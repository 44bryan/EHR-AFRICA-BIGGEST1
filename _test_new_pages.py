"""Test all billing/finance pages using Django test client with forced login."""
import sys, os, django
sys.path.insert(0, "/opt/ehr-africa")
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.base"
django.setup()

from django.test.client import Client
from apps.accounts.models import User

admin = User.objects.filter(is_superuser=True).first()

# Test as each finance role
roles_to_test = ['super_admin', 'finance_director', 'senior_accountant', 'accountant', 'chief_cashier']
users = {}
for role in roles_to_test:
    u = User.objects.filter(role=role, is_active=True).first()
    if u:
        users[role] = u
        print(f"Found user for {role}: {u.username}")
    else:
        print(f"No user for {role}, will use admin")
        users[role] = admin

# All billing URLs to test
urls_to_test = [
    # New cost center module
    ("Journal Types List", "/billing/gl/journal-types/"),
    ("Journal Types Create", "/billing/gl/journal-types/create/"),
    ("Stock Op Types List", "/billing/gl/stock-operation-types/"),
    ("Stock Op Types Create", "/billing/gl/stock-operation-types/create/"),
    ("Cost Center P&L", "/billing/gl/cost-center-pl/"),
    # GL pages
    ("Chart of Accounts", "/billing/gl/chart/"),
    ("Journal Entries", "/billing/gl/journal-entries/"),
    ("Journal Entry Create", "/billing/gl/journal-entries/create/"),
    ("Trial Balance", "/billing/gl/trial-balance/"),
    ("General Ledger", "/billing/gl/general-ledger/"),
    ("Cost Centers List", "/billing/gl/cost-centers/"),
    ("Cost Center Create", "/billing/gl/cost-centers/create/"),
    ("Revenue Analysis", "/billing/gl/revenue-analysis/"),
    ("Balance Sheet", "/billing/gl/balance-sheet/"),
    ("Income Statement", "/billing/gl/income-statement/"),
    ("Auxiliary Balance", "/billing/gl/auxiliary-balance/"),
    ("GL Mappings", "/billing/gl/mappings/"),
    # Billing pages
    ("Invoice List", "/billing/invoices/"),
    ("POS Cashier", "/billing/cashier/"),
    ("Billing Day", "/billing/day/"),
    ("Shifts", "/billing/shifts/"),
    ("AP Vendors", "/billing/ap/vendors/"),
    ("AP Bills", "/billing/ap/bills/"),
    ("AP Aging", "/billing/reports/ap-aging/"),
    ("Expenses", "/billing/expenses/"),
    ("Budget List", "/billing/budgets/"),
    ("Budget YTD", "/billing/reports/budget-ytd/"),
    ("Wallets", "/billing/wallets/"),
    ("Assets", "/billing/assets/"),
    ("Price Catalog", "/billing/price-catalog/"),
    # Bank operations
    ("Bank Accounts", "/billing/bank/accounts/"),
    ("Bank Reconciliation", "/billing/bank/reconciliation/"),
    ("Cash to Bank", "/billing/bank/deposits/"),
    # Cheques
    ("Cheque Books", "/billing/cheques/books/"),
    ("Cheque Register", "/billing/cheques/register/"),
    # Staff Advances
    ("Advances", "/billing/advances/"),
    # Cash management
    ("Cash Transfers", "/billing/cash/transfers/"),
    ("Safe Balance", "/billing/cash/safe/"),
    ("Variance Register", "/billing/variance/"),
    # Reports
    ("Surgery Revenue", "/billing/reports/surgery-revenue/"),
    ("Revenue by Dept", "/billing/reports/revenue-by-dept/"),
    ("Donor Report", "/billing/reports/donor/"),
    ("DSF Report", "/billing/reports/dsf/"),
    ("Daily Liquidity", "/billing/reports/daily-liquidity/"),
]

print(f"\n{'='*80}")
print(f"Testing as SUPER ADMIN ({admin.username})")
print(f"{'='*80}")

client = Client()
client.force_login(admin)

ok_count = 0
fail_urls = []

for name, url in urls_to_test:
    try:
        resp = client.get(url)
        status = resp.status_code
        if status == 200:
            print(f"  OK   200  {name}")
            ok_count += 1
        elif status == 302:
            location = resp.get("Location", "")
            print(f"  302  {name:30s} -> {location}")
            fail_urls.append((name, url, f"302 -> {location}"))
        elif status == 404:
            print(f"  404  {name}")
            fail_urls.append((name, url, "404"))
        elif status == 403:
            print(f"  403  {name}")
            fail_urls.append((name, url, "403"))
        else:
            print(f"  {status}  {name}")
            fail_urls.append((name, url, str(status)))
    except Exception as e:
        err = str(e)[:300]
        print(f"  ERR  {name}")
        print(f"       {err}")
        fail_urls.append((name, url, f"ERR: {err[:100]}"))

print(f"\n{'='*80}")
print(f"Results: {ok_count} OK, {len(fail_urls)} FAILED")
if fail_urls:
    print(f"\nFailed URLs:")
    for name, url, reason in fail_urls:
        print(f"  {name:30s} {url:45s} {reason}")
