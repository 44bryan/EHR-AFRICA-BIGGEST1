import paramiko, re

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode(errors='replace').strip()

# Login
print("=== FULL SYSTEM AUDIT ===\n")
print("Logging in as admin...")
run('curl -s -c /tmp/ehr.jar http://127.0.0.1:8000/accounts/login/ -o /tmp/login.html')
csrf = run("""grep csrfmiddlewaretoken /tmp/login.html | head -1 | sed 's/.*value="//' | sed 's/".*//' """)
run(
    f'curl -s -c /tmp/ehr.jar -b /tmp/ehr.jar '
    f'-d "csrfmiddlewaretoken={csrf}&username=admin&password=Admin2026" '
    f'-H "Referer: http://127.0.0.1:8000/accounts/login/" '
    f'-o /dev/null http://127.0.0.1:8000/accounts/login/'
)
code = run('curl -s -b /tmp/ehr.jar -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/patients/')
if code != "200":
    print(f"AUTH FAILED (got {code}). Aborting.")
    ssh.close()
    exit(1)
print("Auth OK.\n")

pages = {
    # ═══════════════════════════════════════════════════════════════
    # CORE MODULES
    # ═══════════════════════════════════════════════════════════════
    "Dashboard Home":             "/dashboard/home/",
    "Patient List":               "/patients/",
    "Patient Registration":       "/patients/register/",
    "Appointments":               "/appointments/",
    "Consultations Workstation":  "/consultations/",
    "OPD Dashboard":              "/opd/",
    "IPD Dashboard":              "/ipd/",
    "IPD Ward Board":             "/ipd/ward-board/",
    "Pharmacy Dashboard":         "/pharmacy/",
    "Pharmacy Dispensing":        "/pharmacy/dispensing/",
    "Pharmacy Inventory":         "/pharmacy/inventory/",
    "Pharmacy Stats":             "/pharmacy/stats/",
    "Investigation Dashboard":    "/investigations/",
    "Investigation Stats":        "/investigations/stats/",
    "Laboratory Dashboard":       "/laboratory/",

    # ═══════════════════════════════════════════════════════════════
    # ACCOUNTS / AUTH
    # ═══════════════════════════════════════════════════════════════
    "Staff Hub":                  "/accounts/staff/",
    "Staff Create":               "/accounts/staff/create/",
    "Profile":                    "/accounts/profile/",

    # ═══════════════════════════════════════════════════════════════
    # BILLING — POS / INVOICES / SHIFTS
    # ═══════════════════════════════════════════════════════════════
    "Billing Dashboard":          "/billing/",
    "Invoice List":               "/billing/invoices/",
    "POS Landing":                "/billing/pos/",
    "POS Queue":                  "/billing/pos/queue/",
    "Shift List":                 "/billing/shifts/",
    "My Shift":                   "/billing/shifts/my/",
    "Session List":               "/billing/sessions/",
    "My Session":                 "/billing/sessions/mine/",
    "Work Queue":                 "/billing/work-queue/",
    "Cashdesks Overview":         "/billing/cashdesks/",
    "Desk List":                  "/billing/desks/",

    # ═══════════════════════════════════════════════════════════════
    # BILLING — CHARGE MASTER / EXPENSES / CORPORATE / PETTY CASH
    # ═══════════════════════════════════════════════════════════════
    "Service Prices":             "/billing/service-prices/",
    "Expense List":               "/billing/expenses/",
    "Corporate Accounts":         "/billing/corporate/",
    "Petty Cash":                 "/billing/petty-cash/",
    "Budget List":                "/billing/budget/",
    "Patient Wallets":            "/billing/wallets/",
    "Asset Register":             "/billing/assets/",
    "Proforma List":              "/billing/proforma/",
    "Patient Financial History":  "/billing/patient-accounts/",

    # ═══════════════════════════════════════════════════════════════
    # BILLING — GENERAL LEDGER / AP
    # ═══════════════════════════════════════════════════════════════
    "Chart of Accounts":          "/billing/gl/accounts/",
    "GL Account Create":          "/billing/gl/accounts/create/",
    "Journal Entry List":         "/billing/gl/journal/",
    "Journal Entry Create":       "/billing/gl/journal/create/",
    "General Ledger":             "/billing/gl/ledger/",
    "Trial Balance":              "/billing/gl/trial-balance/",
    "Balance Sheet":              "/billing/gl/balance-sheet/",
    "Cash Flow Statement":        "/billing/gl/cash-flow/",
    "AP Vendor List":             "/billing/ap/vendors/",
    "AP Vendor Create":           "/billing/ap/vendors/create/",
    "AP Bill List":               "/billing/ap/bills/",
    "AP Bill Create":             "/billing/ap/bills/create/",

    # ═══════════════════════════════════════════════════════════════
    # BILLING — BANK OPERATIONS
    # ═══════════════════════════════════════════════════════════════
    "Bank Account List":          "/billing/bank/accounts/",
    "Bank Account Create":        "/billing/bank/accounts/create/",
    "Bank Statement Import":      "/billing/bank/statements/import/",
    "Bank Reconciliation List":   "/billing/bank/reconciliation/",
    "Bank Reconciliation Create": "/billing/bank/reconciliation/create/",
    "Cash-to-Bank List":          "/billing/bank/deposits/",
    "Cash-to-Bank Create":        "/billing/bank/deposits/create/",

    # ═══════════════════════════════════════════════════════════════
    # BILLING — CHEQUE MANAGEMENT
    # ═══════════════════════════════════════════════════════════════
    "Chequebook List":            "/billing/cheques/books/",
    "Chequebook Create":          "/billing/cheques/books/create/",
    "Cheque Register":            "/billing/cheques/register/",
    "Cheque Issue":               "/billing/cheques/issue/",

    # ═══════════════════════════════════════════════════════════════
    # BILLING — STAFF ADVANCES
    # ═══════════════════════════════════════════════════════════════
    "Advance List":               "/billing/advances/",
    "Advance Request":            "/billing/advances/request/",

    # ═══════════════════════════════════════════════════════════════
    # BILLING — CASH / SAFE MANAGEMENT
    # ═══════════════════════════════════════════════════════════════
    "Cash Transfer List":         "/billing/cash/transfers/",
    "Cash Transfer Create":       "/billing/cash/transfers/create/",
    "Safe Balance List":          "/billing/cash/safe/",
    "Safe Balance Record":        "/billing/cash/safe/record/",

    # ═══════════════════════════════════════════════════════════════
    # BILLING — ASSET DISPOSAL / VARIANCE
    # ═══════════════════════════════════════════════════════════════
    "Asset Disposal List":        "/billing/assets/disposals/",
    "Variance Register":          "/billing/reports/variance-register/",

    # ═══════════════════════════════════════════════════════════════
    # BILLING — ALL REPORTS
    # ═══════════════════════════════════════════════════════════════
    "Daily Summary Report":       "/billing/reports/daily/",
    "P&L Report":                 "/billing/reports/pl/",
    "Top Services Report":        "/billing/reports/top-services/",
    "AR Aging Report":            "/billing/reports/ar-aging/",
    "Sales Journal":              "/billing/reports/sales-journal/",
    "Void Register":              "/billing/reports/void-register/",
    "Revenue by Desk":            "/billing/reports/revenue-by-desk/",
    "Reconciliation Report":      "/billing/reports/reconciliation/",
    "Daily Liquidity":            "/billing/reports/liquidity/",
    "Surgery Revenue":            "/billing/reports/surgery-revenue/",
    "Revenue by Dept":            "/billing/reports/revenue-by-department/",
    "Donor Report":               "/billing/reports/donor/",
    "DSF Report":                 "/billing/reports/dsf/",
    "Budget YTD":                 "/billing/reports/budget-ytd/",
    "AP Aging":                   "/billing/reports/ap-aging/",
    "Monthly Summary":            "/billing/reports/monthly-summary/",
    "TVA Return":                 "/billing/reports/tva/",
    "Audit Trail":                "/billing/reports/audit-trail/",

    # ═══════════════════════════════════════════════════════════════
    # BILLING — FISCAL PERIODS / DASHBOARDS / BUDGET
    # ═══════════════════════════════════════════════════════════════
    "Fiscal Period List":         "/billing/fiscal-periods/",
    "Finance Dir Dashboard":      "/billing/dashboard/finance-director/",
    "Sr Accountant Dashboard":    "/billing/dashboard/senior-accountant/",
    "Budget Annual Create":       "/billing/budget/annual-create/",

    # ═══════════════════════════════════════════════════════════════
    # BILLING — CSV EXPORTS
    # ═══════════════════════════════════════════════════════════════
    "Export Invoices CSV":        "/billing/export/invoices/",
    "Export AR Aging CSV":        "/billing/export/ar-aging/",
    "Export Expenses CSV":        "/billing/export/expenses/",
    "Export Shifts CSV":          "/billing/export/shifts/",
    "Export Service Prices CSV":  "/billing/export/service-prices/",
    "Export Sales Journal CSV":   "/billing/export/sales-journal/",
    "Export Void Register CSV":   "/billing/export/void-register/",
    "Export Corporate CSV":       "/billing/export/corporate/",
    "Export Patient Financial":   "/billing/export/patient-financial/",

    # ═══════════════════════════════════════════════════════════════
    # BILLING — DISCOUNT APPROVALS / ROUTING
    # ═══════════════════════════════════════════════════════════════
    "Discount Approval List":     "/billing/discounts/",

    # ═══════════════════════════════════════════════════════════════
    # ENTERPRISE — HMO / INSURANCE
    # ═══════════════════════════════════════════════════════════════
    "HMO Dashboard":              "/hmo/",
    "Insurance Schemes":          "/hmo/schemes/",
    "HMO Scheme Create":          "/hmo/schemes/create/",
    "Claims List":                "/hmo/claims/",
    "Claim Batches":              "/hmo/batches/",

    # ═══════════════════════════════════════════════════════════════
    # ENTERPRISE — BLOOD BANK
    # ═══════════════════════════════════════════════════════════════
    "Blood Bank Dashboard":       "/blood-bank/",
    "Blood Donors":               "/blood-bank/donors/",
    "Blood Donor Register":       "/blood-bank/donors/register/",

    # ═══════════════════════════════════════════════════════════════
    # ENTERPRISE — INFECTION CONTROL
    # ═══════════════════════════════════════════════════════════════
    "Infection Control Dash":     "/infection-control/",
    "HAI Reports":                "/infection-control/hai/",
    "HAI Create":                 "/infection-control/hai/create/",
    "Antibiogram":                "/infection-control/antibiogram/",
    "Outbreak Alerts":            "/infection-control/outbreaks/",

    # ═══════════════════════════════════════════════════════════════
    # ENTERPRISE — DIETARY
    # ═══════════════════════════════════════════════════════════════
    "Dietary Dashboard":          "/dietary/",
    "Diet Orders":                "/dietary/orders/",

    # ═══════════════════════════════════════════════════════════════
    # ENTERPRISE — MORTUARY
    # ═══════════════════════════════════════════════════════════════
    "Mortuary Dashboard":         "/mortuary/",

    # ═══════════════════════════════════════════════════════════════
    # NOTIFICATIONS
    # ═══════════════════════════════════════════════════════════════
    "Notifications":              "/notifications/",
    "SMS Log":                    "/notifications/sms/",

    # ═══════════════════════════════════════════════════════════════
    # QMS / TELEMEDICINE / OPTICALS / OTHER
    # ═══════════════════════════════════════════════════════════════
    "QMS Dashboard":              "/qms/",
    "Optical Shop":               "/opticals/",
    "Telemedicine":               "/telemedicine/",
    "Departments":                "/departments/",

    # ═══════════════════════════════════════════════════════════════
    # SYSADMIN
    # ═══════════════════════════════════════════════════════════════
    "Sysadmin Dashboard":         "/sysadmin/",
    "Health Check":               "/sysadmin/health/",
}

print(f"Testing {len(pages)} pages across ALL modules...\n")

ok_pages = []
redirect_pages = []
error_pages = []

for name, url in pages.items():
    code = run(f'curl -s -b /tmp/ehr.jar -o /dev/null -w "%{{http_code}}" http://127.0.0.1:8000{url}')
    if code == "200":
        ok_pages.append((name, url))
        print(f"  [OK]  {name}")
    elif code == "302":
        redirect_pages.append((name, url))
        print(f"  [->]  {name}")
    elif code == "500":
        error_pages.append((name, url, "500"))
        print(f"  [500] {name}  *** SERVER ERROR ***")
    elif code == "404":
        error_pages.append((name, url, "404"))
        print(f"  [404] {name}  *** NOT FOUND ***")
    elif code == "403":
        error_pages.append((name, url, "403"))
        print(f"  [403] {name}  (forbidden)")
    else:
        error_pages.append((name, url, code))
        print(f"  [{code}] {name}")

print(f"\n{'='*70}")
print(f"  TOTAL TESTED:  {len(pages)}")
print(f"  OK (200):      {len(ok_pages)}")
print(f"  Redirect (302):{len(redirect_pages)}")
print(f"  ERRORS:        {len(error_pages)}")
print(f"{'='*70}")

if error_pages:
    print(f"\n--- ERROR DETAILS ({len(error_pages)}) ---\n")
    for name, url, code in error_pages:
        print(f"  [{code}] {name}: {url}")
        if code == "500":
            # Get error from gunicorn log
            run(f'curl -s -b /tmp/ehr.jar -o /dev/null http://127.0.0.1:8000{url}')

    # Get error traces from journalctl
    import time
    time.sleep(2)
    stdin, stdout, stderr = ssh.exec_command(
        'sudo -S journalctl -u ehr-gunicorn --since "30 seconds ago" --no-pager 2>&1 '
        '| grep -E "(FieldError|TemplateDoesNotExist|AttributeError|NoReverseMatch|'
        'Internal Server Error|ImportError|OperationalError|TypeError|ValueError|'
        'KeyError|TemplateSyntax)" | sort -u',
        timeout=15
    )
    stdin.write('123456\n')
    stdin.flush()
    trace = stdout.read().decode(errors='replace').strip()
    if trace:
        print(f"\n--- SERVER LOG ERRORS ---\n")
        for line in trace.split('\n'):
            # Clean up systemd prefix
            clean = re.sub(r'^.*gunicorn\[\d+\]: ', '', line).strip()
            if clean:
                print(f"  {clean[:200]}")
else:
    print("\n*** ALL PAGES PASSING — ZERO ERRORS ***")

# Summary of redirects (some are expected, e.g. role-based)
if redirect_pages:
    print(f"\n--- REDIRECTS ({len(redirect_pages)}) ---")
    print("  (Redirects are normal for role-gated or form-only pages)")
    for name, url in redirect_pages:
        print(f"  [->] {name}: {url}")

ssh.close()
