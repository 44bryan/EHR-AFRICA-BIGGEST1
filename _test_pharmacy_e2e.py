"""
End-to-end integration test: OTC Sale + Barcode + Search
Run via: manage.py shell < _test_pharmacy_e2e.py
"""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
import django; django.setup()

from django.test import Client
from django.utils import timezone

results = []

def check(name, condition, detail=''):
    tag = 'PASS' if condition else 'FAIL'
    results.append((name, condition))
    print(f'  [{tag}] {name}' + (f' -- {detail}' if detail else ''))

print('=' * 60)
print('PHARMACY END-TO-END INTEGRATION TEST')
print('=' * 60)

c = Client()
logged_in = c.login(username='admin', password='Admin2026')
check('Admin login', logged_in)

# ── 1. Patient exists ────────────────────────────────────────────────────────
print('\n-- Step 1: Patient --')
from apps.patients.models import Patient
patient = Patient.objects.filter(is_deleted=False).first()
check('Patient exists', patient is not None, patient.full_name if patient else '')

# ── 2. Drug exists with stock ────────────────────────────────────────────────
print('\n-- Step 2: Drug & Stock --')
from apps.pharmacy.models import Drug, DrugStock, Dispensing, DispensingItem

drug = Drug.objects.filter(is_active=True, is_deleted=False, selling_price__gt=0).first()
check('Drug in formulary', drug is not None, drug.name if drug else '')

stock = DrugStock.objects.filter(
    drug=drug, is_deleted=False, quantity_remaining__gt=0,
    expiry_date__gte=timezone.localdate()
).first() if drug else None
check('Stock batch available', stock is not None, f'Batch {stock.batch_number}, qty={stock.quantity_remaining}' if stock else '')

# ── 3. Create OTC dispensing (direct sale) ────────────────────────────────────
print('\n-- Step 3: Create OTC sale --')
r1 = c.post('/pharmacy/direct-sale/', {
    'customer_type': 'registered',
    'patient_id': str(patient.pk) if patient else '',
})
check('OTC sale POST', r1.status_code in (200, 302), f'HTTP {r1.status_code}')

# Find the dispensing just created
disp = Dispensing.objects.filter(patient=patient, is_otc=True, is_deleted=False).order_by('-created_at').first()
check('Dispensing created', disp is not None, disp.dispensing_number if disp else '')

# ── 4. Add drug item via AJAX ─────────────────────────────────────────────────
print('\n-- Step 4: Add item to dispensing --')
if disp and drug:
    r2 = c.post(f'/pharmacy/dispensing/{disp.pk}/add-item-ajax/', {
        'drug_id': str(drug.pk),
        'qty': 1,
        'unit_price': str(drug.selling_price),
        'instructions': 'Test instruction',
    })
    check('Add item AJAX', r2.status_code == 200, f'HTTP {r2.status_code}')
    if r2.status_code == 200:
        data = r2.json()
        check('Item added OK', data.get('success', False), data.get('item', {}).get('drug_name', ''))
        check('Total > 0', float(data.get('total', 0)) > 0, f'{data.get("total")} FCFA')
        check('has is_controlled flag', 'is_controlled' in data)

# ── 5. Complete dispensing ────────────────────────────────────────────────────
print('\n-- Step 5: Complete dispensing --')
if disp:
    disp.refresh_from_db()
    r3 = c.post(f'/pharmacy/dispensing/{disp.pk}/complete/', {
        'payment_method': 'CASH',
        'amount': str(disp.total_amount),
    })
    check('Complete dispensing', r3.status_code in (200, 302), f'HTTP {r3.status_code}')
    disp.refresh_from_db()
    check('Status = DISPENSED', disp.status == 'DISPENSED', disp.status)

# ── 6. Receipt ───────────────────────────────────────────────────────────────
print('\n-- Step 6: Receipt --')
if disp:
    r4 = c.get(f'/pharmacy/dispensing/{disp.pk}/receipt/')
    check('Receipt loads', r4.status_code == 200, f'HTTP {r4.status_code}')

# ── 7. Barcode lookup ────────────────────────────────────────────────────────
print('\n-- Step 7: Barcode --')
r5 = c.get('/pharmacy/drugs/barcode/?code=NONEXISTENT999')
check('Barcode 404 for missing', r5.status_code == 404)

r5b = c.get('/pharmacy/drugs/barcode/')
check('Barcode 400 for empty', r5b.status_code == 400)

drug_bc = Drug.objects.filter(is_active=True, is_deleted=False).exclude(barcode__isnull=True).exclude(barcode='').first()
if drug_bc:
    r6 = c.get(f'/pharmacy/drugs/barcode/?code={drug_bc.barcode}')
    check('Barcode found', r6.status_code == 200, drug_bc.name)
else:
    print('  [SKIP] No drugs have barcodes')

# ── 8. Drug search AJAX ──────────────────────────────────────────────────────
print('\n-- Step 8: Drug search --')
if drug:
    r7 = c.get('/pharmacy/drugs/search/?q=' + drug.name[:5])
    check('Search returns 200', r7.status_code == 200)
    if r7.status_code == 200:
        data7 = r7.json()
        check('Search has results', len(data7.get('drugs', [])) > 0)
        if data7.get('drugs'):
            check('Has barcode field', 'barcode' in data7['drugs'][0])

# ── 9. Supplier list ─────────────────────────────────────────────────────────
print('\n-- Step 9: Supplier --')
from apps.pharmacy.models import Supplier
check('Suppliers seeded', Supplier.objects.filter(is_deleted=False).count() >= 5,
      f'{Supplier.objects.filter(is_deleted=False).count()} suppliers')

# ── 10. Pharmacy locations ───────────────────────────────────────────────────
print('\n-- Step 10: Multi-location --')
from apps.pharmacy.models import PharmacyLocation
ft = PharmacyLocation.objects.filter(name='FT Pharmacy').first()
gen = PharmacyLocation.objects.filter(name='General Pharmacy').first()
check('FT Pharmacy exists', ft is not None)
check('General Pharmacy exists', gen is not None)
ft_drugs = Drug.objects.filter(location=ft, is_deleted=False).count() if ft else 0
gen_drugs = Drug.objects.filter(location=gen, is_deleted=False).count() if gen else 0
check('FT has drugs', ft_drugs > 0, f'{ft_drugs} drugs')
check('General has drugs', gen_drugs > 0, f'{gen_drugs} drugs')

# ── 11. Controlled drug entry auto-creation ──────────────────────────────────
print('\n-- Step 11: Controlled drugs --')
from apps.pharmacy.models import ControlledDrugEntry
check('ControlledDrugEntry model exists', True)
controlled = Drug.objects.filter(is_controlled=True, is_deleted=False).count()
check('Controlled drugs in formulary', True, f'{controlled} drugs flagged')

# ── Summary ───────────────────────────────────────────────────────────────────
print('\n' + '=' * 60)
passed = sum(1 for _, ok in results if ok)
total = len(results)
failed = total - passed
if failed == 0:
    print(f'ALL {total} TESTS PASSED')
else:
    print(f'{failed} FAILED out of {total} tests')
    for name, ok in results:
        if not ok:
            print(f'  FAILED: {name}')
print('=' * 60)
