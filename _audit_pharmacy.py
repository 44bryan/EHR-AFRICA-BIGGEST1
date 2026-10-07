"""
Full pharmacy module audit — hit every URL, check for 500 errors.
Run via: manage.py shell < _audit_pharmacy.py
"""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
import django; django.setup()

from django.test import Client

c = Client()
c.login(username='admin', password='Admin2026')

# Also test as pharmacist
c2 = Client()
c2.login(username='pharma01', password='Admin2026')

results = []

def test_url(client, url, label, method='GET', data=None, expect_redirect=False):
    try:
        if method == 'GET':
            r = client.get(url)
        else:
            r = client.post(url, data or {})
        ok = r.status_code in (200, 302, 301, 403)
        if expect_redirect:
            ok = r.status_code in (302, 301)
        status = 'PASS' if ok else 'FAIL'
        detail = f'HTTP {r.status_code}'
        if r.status_code == 302:
            detail += f' -> {r.url}'
        results.append((label, ok, detail))
        print(f'  [{status}] {label} -- {detail}')
    except Exception as e:
        results.append((label, False, str(e)[:100]))
        print(f'  [FAIL] {label} -- EXCEPTION: {str(e)[:100]}')

print('=' * 70)
print('PHARMACY MODULE — FULL URL AUDIT (admin)')
print('=' * 70)

# Core pages
test_url(c, '/pharmacy/', 'Dashboard')
test_url(c, '/pharmacy/stats/', 'Stats')
test_url(c, '/pharmacy/alerts/', 'Expiry Alerts')
test_url(c, '/pharmacy/drugs/', 'Drug List')
test_url(c, '/pharmacy/drugs/new/', 'Drug Create Form')
test_url(c, '/pharmacy/drugs/?page=2', 'Drug List Page 2')
test_url(c, '/pharmacy/drugs/search/?q=para', 'Drug Search AJAX')
test_url(c, '/pharmacy/drugs/barcode/?code=TEST', 'Barcode Lookup (miss)')
test_url(c, '/pharmacy/drugs/barcode/', 'Barcode Lookup (empty)')

# Find a real drug for detail pages
from apps.pharmacy.models import Drug, DrugStock, Dispensing, Supplier, PurchaseOrder
drug = Drug.objects.filter(is_deleted=False, is_active=True).first()
if drug:
    test_url(c, f'/pharmacy/drugs/{drug.pk}/', 'Drug Detail')
    test_url(c, f'/pharmacy/drugs/{drug.pk}/edit/', 'Drug Edit Form')
    test_url(c, f'/pharmacy/drugs/{drug.pk}/add-stock/', 'Add Stock Form')
    batch = DrugStock.objects.filter(drug=drug, is_deleted=False).first()
    if batch:
        test_url(c, f'/pharmacy/stock/{batch.pk}/adjust/', 'Stock Adjust Form')

# Dispensing
test_url(c, '/pharmacy/dispensing/', 'Dispensing List')
test_url(c, '/pharmacy/dispensing/?page=1', 'Dispensing List Page 1')
test_url(c, '/pharmacy/search/', 'Patient Search (pharmacy)')
test_url(c, '/pharmacy/direct-sale/', 'Direct Sale / OTC Form')

disp = Dispensing.objects.filter(is_deleted=False).order_by('-created_at').first()
if disp:
    test_url(c, f'/pharmacy/dispensing/{disp.pk}/', 'Dispensing Detail')
    if disp.status == 'DISPENSED':
        test_url(c, f'/pharmacy/dispensing/{disp.pk}/receipt/', 'Dispensing Receipt')
        test_url(c, f'/pharmacy/dispensing/{disp.pk}/label/', 'Dispensing Label PDF')
        test_url(c, f'/pharmacy/dispensing/{disp.pk}/return/', 'Dispensing Return Form')

# Controlled drugs
test_url(c, '/pharmacy/controlled/', 'Controlled Register')
test_url(c, '/pharmacy/controlled/new/', 'Controlled Entry Create')
test_url(c, '/pharmacy/controlled/pdf/', 'Controlled Register PDF')

# Ward returns
test_url(c, '/pharmacy/ward-returns/', 'Ward Return List')
test_url(c, '/pharmacy/ward-returns/new/', 'Ward Return Create')

# Chronic Rx
test_url(c, '/pharmacy/chronic-rx/', 'Chronic Rx List')
test_url(c, '/pharmacy/chronic-rx/new/', 'Chronic Rx Create')

# Suppliers
test_url(c, '/pharmacy/suppliers/', 'Supplier List')
test_url(c, '/pharmacy/suppliers/new/', 'Supplier Create')
supplier = Supplier.objects.filter(is_deleted=False).first()
if supplier:
    test_url(c, f'/pharmacy/suppliers/{supplier.pk}/edit/', 'Supplier Edit')

# Purchase Orders
test_url(c, '/pharmacy/purchase-orders/', 'Purchase Order List')
test_url(c, '/pharmacy/purchase-orders/new/', 'Purchase Order Create')
po = PurchaseOrder.objects.filter(is_deleted=False).first()
if po:
    test_url(c, f'/pharmacy/purchase-orders/{po.pk}/', 'Purchase Order Detail')

# Adjustments
test_url(c, '/pharmacy/adjustments/', 'Stock Adjustment List')

# Unavailable lines
test_url(c, '/pharmacy/unavailable-lines/', 'Unavailable Lines')

# Bulk import
test_url(c, '/pharmacy/drugs/import/', 'Drug Bulk Import')

# Pilferage
test_url(c, '/pharmacy/pilferage/', 'Pilferage Dashboard')

# Head Pharmacist module
test_url(c, '/pharmacy/locations/', 'Location List')
test_url(c, '/pharmacy/locations/new/', 'Location Create')
test_url(c, '/pharmacy/transfers/', 'Transfer List')
test_url(c, '/pharmacy/transfers/new/', 'Transfer Create')
test_url(c, '/pharmacy/stock-exits/', 'Stock Exit List')
test_url(c, '/pharmacy/stock-exits/new/', 'Stock Exit Create')
test_url(c, '/pharmacy/recalls/', 'Recall List')
test_url(c, '/pharmacy/recalls/new/', 'Recall Create')

# Reports
test_url(c, '/pharmacy/reports/abc/', 'ABC Analysis')
test_url(c, '/pharmacy/reports/ven/', 'VEN Analysis')
test_url(c, '/pharmacy/reports/dead-stock/', 'Dead Stock Report')
test_url(c, '/pharmacy/reports/consumption/', 'Consumption Report')
test_url(c, '/pharmacy/reports/turnover/', 'Turnover Report')
test_url(c, '/pharmacy/reports/productivity/', 'Productivity Report')

# Stock AJAX
test_url(c, f'/pharmacy/drugs/stock-ajax/?drug_id={drug.pk}' if drug else '/pharmacy/drugs/stock-ajax/', 'Stock AJAX')

print('\n' + '=' * 70)
print('PHARMACIST ROLE ACCESS (pharma01)')
print('=' * 70)
test_url(c2, '/pharmacy/', 'Dashboard (pharma01)')
test_url(c2, '/pharmacy/drugs/', 'Drug List (pharma01)')
test_url(c2, '/pharmacy/dispensing/', 'Dispensing List (pharma01)')
test_url(c2, '/pharmacy/controlled/', 'Controlled Register (pharma01)')
test_url(c2, '/pharmacy/search/', 'Patient Search (pharma01)')

# Summary
print('\n' + '=' * 70)
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
failed = total - passed
if failed == 0:
    print(f'ALL {total} URLs PASSED — no errors')
else:
    print(f'{failed} FAILED out of {total} URLs:')
    for name, ok, detail in results:
        if not ok:
            print(f'  FAIL: {name} -- {detail}')
print('=' * 70)
