import paramiko, re

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode(errors='replace').strip()

# Login
print("Logging in...")
run('curl -s -c /tmp/ehr.jar http://127.0.0.1:8000/accounts/login/ -o /tmp/login.html')
csrf = run("""grep csrfmiddlewaretoken /tmp/login.html | head -1 | sed 's/.*value="//' | sed 's/".*//' """)
run(
    f'curl -s -c /tmp/ehr.jar -b /tmp/ehr.jar '
    f'-d "csrfmiddlewaretoken={csrf}&username=admin&password=Admin2026" '
    f'-H "Referer: http://127.0.0.1:8000/accounts/login/" '
    f'-o /dev/null http://127.0.0.1:8000/accounts/login/'
)
# Verify
code = run('curl -s -b /tmp/ehr.jar -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/patients/')
print(f"Auth: {'OK' if code == '200' else 'FAILED'}")
if code != "200":
    ssh.close()
    exit(1)

pages = {
    # NEW FINANCE PAGES
    "Bank Accounts":      "/billing/bank/accounts/",
    "Bank Reconciliation": "/billing/bank/reconciliation/",
    "Cash-to-Bank":       "/billing/bank/deposits/",
    "Chequebooks":        "/billing/cheques/books/",
    "Cheque Register":    "/billing/cheques/register/",
    "Advances":           "/billing/advances/",
    "Cash Transfers":     "/billing/cash/transfers/",
    "Safe Balance":       "/billing/cash/safe/",
    "Variance Register":  "/billing/reports/variance-register/",
    "Asset Disposals":    "/billing/assets/disposals/",
    "Daily Liquidity":    "/billing/reports/liquidity/",
    "Surgery Revenue":    "/billing/reports/surgery-revenue/",
    "Revenue by Dept":    "/billing/reports/revenue-by-department/",
    "Donor Report":       "/billing/reports/donor/",
    "DSF Report":         "/billing/reports/dsf/",
    "Budget YTD":         "/billing/reports/budget-ytd/",
    "AP Aging":           "/billing/reports/ap-aging/",
    "Monthly Summary":    "/billing/reports/monthly-summary/",
    "TVA Return":         "/billing/reports/tva/",
    "Audit Trail":        "/billing/reports/audit-trail/",
    "Fiscal Periods":     "/billing/fiscal-periods/",
    "Finance Dir Dash":   "/billing/dashboard/finance-director/",
    "Sr Accountant Dash": "/billing/dashboard/senior-accountant/",
    "Budget Annual":      "/billing/budget/annual-create/",
    # Existing billing
    "Billing Dash":       "/billing/",
    "Chart of Accounts":  "/billing/gl/accounts/",
    "Trial Balance":      "/billing/gl/trial-balance/",
    "Balance Sheet":      "/billing/gl/balance-sheet/",
    "Cash Flow":          "/billing/gl/cash-flow/",
    "General Ledger":     "/billing/gl/ledger/",
    "Journal Entries":    "/billing/gl/journal/",
    "AP Vendors":         "/billing/ap/vendors/",
    "AP Bills":           "/billing/ap/bills/",
    "Wallets":            "/billing/wallets/",
    "Assets":             "/billing/assets/",
    "Proformas":          "/billing/proforma/",
    "Daily Report":       "/billing/reports/daily/",
    "P&L":                "/billing/reports/pl/",
    "Sales Journal":      "/billing/reports/sales-journal/",
    "Void Register":      "/billing/reports/void-register/",
    "Expenses":           "/billing/expenses/",
    "Petty Cash":         "/billing/petty-cash/",
    "Budget List":        "/billing/budget/",
    "Service Prices":     "/billing/service-prices/",
    "Corporate":          "/billing/corporate/",
    # Investigations
    "Invest Dash":        "/investigations/",
    "Invest Stats":       "/investigations/stats/",
    # Enterprise
    "HMO":                "/hmo/",
    "HMO Schemes":        "/hmo/schemes/",
    "HMO Claims":         "/hmo/claims/",
    "Blood Bank":         "/blood-bank/",
    "Blood Donors":       "/blood-bank/donors/",
    "Infection Ctrl":     "/infection-control/",
    "HAI Reports":        "/infection-control/hai/",
    "Dietary":            "/dietary/",
    "Diet Orders":        "/dietary/orders/",
    "Mortuary":           "/mortuary/",
    # Core
    "Pharmacy":           "/pharmacy/",
    "Patients":           "/patients/",
    "Appointments":       "/appointments/",
    "IPD":                "/ipd/",
    "Consultations":      "/consultations/",
}

print(f"\nTesting {len(pages)} pages...\n")
failures = []
ok = 0

for name, url in pages.items():
    code = run(f'curl -s -b /tmp/ehr.jar -o /dev/null -w "%{{http_code}}" http://127.0.0.1:8000{url}')
    if code == "200":
        ok += 1
        print(f"  [OK]  {name:25s} {url}")
    elif code == "500":
        failures.append((name, url))
        print(f"  [!!]  {name:25s} {url} -> 500 ERROR")
    elif code == "302":
        print(f"  [->]  {name:25s} {url} -> redirect")
    else:
        print(f"  [??]  {name:25s} {url} -> {code}")

print(f"\n{'='*80}")
print(f"OK: {ok}  |  500 ERRORS: {len(failures)}  |  Total: {len(pages)}")

if failures:
    print(f"\n--- 500 ERROR DETAILS ---\n")
    for name, url in failures:
        print(f"  {name}: {url}")
        body = run(f'curl -s -b /tmp/ehr.jar http://127.0.0.1:8000{url} 2>/dev/null', timeout=20)
        # Extract error from Django debug page
        for pattern in ['Exception Type:', 'Exception Value:', 'TemplateSyntaxError', 'FieldError',
                        'AttributeError', 'NoReverseMatch', 'OperationalError', 'ProgrammingError',
                        'TemplateDoesNotExist', 'does not exist']:
            for line in body.split('\n'):
                if pattern in line:
                    clean = re.sub('<[^>]+>', '', line).strip()
                    if clean and len(clean) > 5:
                        print(f"    -> {clean[:200]}")
                        break
        print()

ssh.close()
