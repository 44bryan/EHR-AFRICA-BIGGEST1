import sys, os, django
sys.path.insert(0, '/opt/ehr-africa')
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.base'
django.setup()

from apps.billing.models import CostCenter
from apps.inventory.models import StoreLocation

admin_pk = None
try:
    from apps.accounts.models import User
    u = User.objects.filter(is_superuser=True).first()
    admin_pk = u.pk if u else None
except Exception:
    pass

# ── Real cost centers from TurboClinic screenshots ──────────────────────────
REAL_CC = [
    ('001', 'Ophthalmology'),
    ('004', 'Laboratory'),
    ('005', 'Anesthesia'),
    ('006', 'Accommodation'),
    ('007', 'Patient Affairs'),
    ('008', 'Pharmacy'),
    ('009', 'Optical Shop'),
    ('010', 'Outreach'),
    ('011', 'Training Center'),
    ('012', 'Finance & Administration'),
    ('013', 'Other Support Services'),
    ('014', 'Partnership, Marketing & Dev\'t'),
    ('015', 'New Projects'),
    ('016', 'General Admin Expenses'),
    ('018', 'Donation, Grant & Sundry Income'),
]

# Soft-delete all old cost centers that are NOT in the real list
real_codes = {c[0] for c in REAL_CC}
old_deleted = CostCenter.objects.exclude(code__in=real_codes).update(
    is_deleted=True, is_active=False
)
print(f"Soft-deleted {old_deleted} old cost centers")

# Create / update real cost centers
cc_map = {}
for code, name in REAL_CC:
    obj, created = CostCenter.objects.update_or_create(
        code=code,
        defaults={
            'name': name,
            'is_active': True,
            'is_deleted': False,
        }
    )
    cc_map[code] = obj
    tag = 'CREATED' if created else 'UPDATED'
    print(f"  {tag}: {code} - {name}")

print()

# ── Update StoreLocation cost_center FKs ────────────────────────────────────
STORE_CC = {
    'FD01':  '007',  # Front Desk Store       → Patient Affairs
    'NM01':  '013',  # Non-Medical Stock       → Other Support Services
    'OP01':  '009',  # Optical Showroom        → Optical Shop
    'OP02':  '009',  # Optical Store           → Optical Shop
    'PH02':  '008',  # Pharmacy Store          → Pharmacy
    'PH-CU': '001',  # Emergency Chariots      → Ophthalmology
    'PH-OR': '001',  # Medical Consumables     → Ophthalmology
    'PH-OT': '001',  # OT Store                → Ophthalmology
    'PH-TOR':'010',  # Outreach Store          → Outreach
    'PH-TOT':'001',  # OT Transfer Store       → Ophthalmology
}

for store_code, cc_code in STORE_CC.items():
    updated = StoreLocation.objects.filter(store_code=store_code).update(
        cost_center=cc_map[cc_code]
    )
    status = 'OK' if updated else 'NOT FOUND'
    print(f"  StoreLocation {store_code} → CC {cc_code} ({cc_map[cc_code].name}): {status}")

print()
print("Cost center seed complete.")
