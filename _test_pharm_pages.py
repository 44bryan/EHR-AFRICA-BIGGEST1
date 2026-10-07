import os, sys, django
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.base"
sys.path.insert(0, "/opt/ehr-africa")
django.setup()
from django.test import Client
from apps.accounts.models import User

user = User.objects.filter(role="head_pharmacist").first()
if not user:
    user = User.objects.get(username="admin")
    print("Using admin (no head_pharmacist found)")
else:
    print("Using {} ({})".format(user.username, user.role))

c = Client()
c.force_login(user)

pages = [
    ("/pharmacy/", "Dashboard"),
    ("/pharmacy/dispense/", "Dispense Queue"),
    ("/pharmacy/drugs/", "Drug List"),
    ("/pharmacy/drugs/new/", "Drug Create"),
    ("/pharmacy/dispensing/", "Dispensing List"),
    ("/pharmacy/search/", "Patient Search"),
    ("/pharmacy/direct-sale/", "Direct Sale"),
    ("/pharmacy/controlled/", "Controlled Register"),
    ("/pharmacy/controlled/new/", "Controlled Entry Create"),
    ("/pharmacy/controlled/pdf/", "Controlled PDF"),
    ("/pharmacy/ward-returns/", "Ward Returns"),
    ("/pharmacy/ward-returns/new/", "Ward Return Create"),
    ("/pharmacy/chronic-rx/", "Chronic Rx List"),
    ("/pharmacy/chronic-rx/new/", "Chronic Rx Create"),
    ("/pharmacy/suppliers/", "Suppliers"),
    ("/pharmacy/suppliers/new/", "Supplier Create"),
    ("/pharmacy/purchase-orders/", "PO List"),
    ("/pharmacy/purchase-orders/new/", "PO Create"),
    ("/pharmacy/adjustments/", "Adjustments"),
    ("/pharmacy/locations/", "Locations"),
    ("/pharmacy/locations/new/", "Location Create"),
    ("/pharmacy/cross-store/", "Cross-Store"),
    ("/pharmacy/transfers/", "Transfers"),
    ("/pharmacy/transfers/new/", "Transfer Create"),
    ("/pharmacy/stock-exits/", "Stock Exits"),
    ("/pharmacy/stock-exits/new/", "Stock Exit Create"),
    ("/pharmacy/recalls/", "Recalls"),
    ("/pharmacy/recalls/new/", "Recall Create"),
    ("/pharmacy/pilferage/", "Pilferage"),
    ("/pharmacy/stats/", "Statistics"),
    ("/pharmacy/barcode-labels/", "Barcode Labels"),
    ("/pharmacy/unavailable-lines/", "Unavailable Lines"),
    ("/pharmacy/drugs/import/", "Drug Import"),
    ("/pharmacy/alerts/", "Expiry Alerts"),
    ("/pharmacy/reports/abc/", "ABC Report"),
    ("/pharmacy/reports/ven/", "VEN Report"),
    ("/pharmacy/reports/dead-stock/", "Dead Stock"),
    ("/pharmacy/reports/consumption/", "Consumption"),
    ("/pharmacy/reports/turnover/", "Turnover"),
    ("/pharmacy/reports/productivity/", "Productivity"),
    ("/pharmacy/reports/stock-situation/", "Stock Situation"),
    ("/pharmacy/reports/sales-journal/", "Sales Journal"),
    ("/pharmacy/reports/expiring/", "Expiring Stock"),
    ("/pharmacy/reports/supplier-history/", "Supplier History"),
]

errors = []
ok = 0
for url, name in pages:
    try:
        r = c.get(url)
        if r.status_code in (200, 302):
            ok += 1
        else:
            errors.append((url, name, r.status_code, ""))
    except Exception as e:
        errors.append((url, name, "CRASH", str(e)[:120]))

print("Passed: {}/{}".format(ok, len(pages)))
if errors:
    print("ERRORS ({}):".format(len(errors)))
    for url, name, code, msg in errors:
        print("  {} {} ({})".format(code, name, url))
        if msg:
            print("       {}".format(msg))
else:
    print("ALL PAGES PASS")
