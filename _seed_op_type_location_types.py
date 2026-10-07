"""
Seed location_types on StockOperationType records.

Rules:
  - EN-ACH  (Purchase entry)               → all stores (blank)
  - EN-DON  (Donation entry)               → all stores (blank)
  - EN-RET  (Return from dept)             → all stores (blank)
  - EN-TRF  (Transfer In)                  → all stores (blank)
  - EN-OUV  (Opening stock)                → all stores (blank)
  - EN-ADJ  (Adjustment +)                 → all stores (blank)
  - EN-PHA  (Pharmaceutical Purchase)      → PHARMACY
  - EN-MED  (Medical Supplies Entry)       → GENERAL,THEATRE,WARD,EMERGENCY
  - EN-OPT  (Optical Goods Entry)          → OPTICAL,SHOWROOM
  - EX-CON  (Dept Consumption)             → all stores (blank)
  - EX-PAT  (Patient Direct Use)           → PHARMACY,GENERAL,WARD
  - EX-EXP  (Expired Disposal)             → all stores (blank)
  - EX-DMG  (Damaged Write-off)            → all stores (blank)
  - EX-THF  (Theft / Loss)                 → all stores (blank)
  - EX-TRF  (Transfer Out)                 → all stores (blank)
  - EX-SAM  (Sample / Demonstration)       → OPTICAL,SHOWROOM
  - EX-RTV  (Return to Vendor)             → all stores (blank)
  - EX-ADJ  (Adjustment -)                 → all stores (blank)
  - EN-CNS  (Consignment Received)         → GENERAL,PHARMACY
  - EX-CNS  (Consignment Return)           → GENERAL,PHARMACY
  - EX-SCR  (Scrap/Obsolete)               → all stores (blank)
  All others → blank (all stores)

Run via: python manage.py shell < _seed_op_type_location_types.py
Or directly: python _seed_op_type_location_types.py
"""

import os, sys, django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from apps.billing.models import StockOperationType

LOCATION_MAP = {
    # Pharmacy-specific entry
    'EN-PHA': 'PHARMACY',
    'EN-PHAR': 'PHARMACY',
    # Optical-specific
    'EN-OPT':  'OPTICAL,SHOWROOM',
    'EX-SAM':  'OPTICAL,SHOWROOM',
    'EX-DEMO': 'OPTICAL,SHOWROOM',
    # Medical/theatre
    'EN-MED':  'GENERAL,THEATRE,WARD,EMERGENCY',
    'EN-SURG': 'THEATRE',
    'EX-SURG': 'THEATRE',
    # Consignment
    'EN-CNS':  'GENERAL,PHARMACY',
    'EX-CNS':  'GENERAL,PHARMACY',
    # Patient direct (pharmacy and ward)
    'EX-PAT':  'PHARMACY,GENERAL,WARD,EMERGENCY',
}

updated = 0
all_types = StockOperationType.objects.all()
print(f'Total op types: {all_types.count()}')
for op in all_types:
    loc = LOCATION_MAP.get(op.code, '')
    if op.location_types != loc:
        op.location_types = loc
        op.save(update_fields=['location_types'])
        updated += 1
        if loc:
            print(f'  {op.code} → "{loc}"')
        else:
            print(f'  {op.code} → all stores (blank)')

print(f'\nDone. {updated} operation types updated.')
