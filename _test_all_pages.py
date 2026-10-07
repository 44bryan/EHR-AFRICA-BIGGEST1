import sys
sys.path.insert(0, '/opt/ehr-africa')
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
django.setup()
from django.test import Client

c = Client()
c.login(username='admin', password='Admin2026')

pages = [
    '/dashboard/',
    '/accounts/staff-hub/',
    '/patients/',
    '/patients/register/',
    '/pharmacy/',
    '/pharmacy/drugs/',
    '/pharmacy/stats/',
    '/pharmacy/suppliers/',
    '/pharmacy/purchase-orders/',
    '/pharmacy/controlled-drugs/',
    '/pharmacy/stock-adjustments/',
    '/pharmacy/returns/',
    '/billing/',
    '/billing/invoices/',
    '/billing/wallets/',
    '/consultations/',
    '/investigations/',
    '/ipd/',
    '/prescriptions/',
    '/reports/',
    '/hmo/',
    '/notifications/',
]

errors = []
for p in pages:
    try:
        r = c.get(p)
        status = r.status_code
        label = 'OK' if status in (200, 302) else 'FAIL-%d' % status
        if status >= 400:
            errors.append(p)
        print('%s %d %s' % (label.ljust(8), status, p))
    except Exception as e:
        errors.append(p)
        print('ERROR    --- %s: %s' % (p, str(e)[:80]))

print('')
print('=== %d errors out of %d pages ===' % (len(errors), len(pages)))
for e in errors:
    print('  FAILED: %s' % e)
