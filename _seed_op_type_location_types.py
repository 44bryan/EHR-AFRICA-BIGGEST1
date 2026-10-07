"""
Seed location_types on ALL StockOperationType records.

StoreLocation.location_type choices:
  GENERAL, PHARMACY, OPTICAL, SHOWROOM, THEATRE, CENTRAL, SUB,
  WARD, EMERGENCY, FRONT_DESK, NON_MEDICAL, OUTREACH, OTN

Rules:
  blank = applies to ALL stores (generic operations)
  otherwise = comma-separated list of store types that see this op

Run via: python manage.py shell < _seed_op_type_location_types.py
Or directly: python _seed_op_type_location_types.py
"""

import os, sys, django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from apps.billing.models import StockOperationType

# code -> location_types string (blank = all stores)
LOCATION_MAP = {

    # ── ENTRY TYPES ────────────────────────────────────────────────────────────

    # Generic / all stores
    'EN-ACH': '',                           # Purchase Entry          → ALL
    'EN-DON': '',                           # Donation Received       → ALL
    'EN-RET': '',                           # Return to Stock         → ALL
    'EN-TRF': '',                           # Transfer In             → ALL
    'EN-AJP': '',                           # Adjustment Surplus (+)  → ALL

    # Pharmacy only
    'EN-PHR': 'PHARMACY',                   # Pharmacy Purchase
    'EN-PRT': 'PHARMACY',                   # Pharmacy Return

    # Optical / Showroom only
    'EN-FRM': 'OPTICAL,SHOWROOM',           # Frame Purchase
    'EN-LNS': 'OPTICAL,SHOWROOM',           # Lens Purchase
    'EN-LVD': 'OPTICAL,SHOWROOM',           # Low Vision Devices
    'EN-ACC': 'OPTICAL,SHOWROOM',           # Accessories Purchase
    'EN-WIP': 'OPTICAL,SHOWROOM',           # Work in Progress Entry

    # Theatre / Surgery
    'EN-SRG': 'THEATRE',                    # Surgical Supplies
    'EN-ANS': 'THEATRE',                    # Anaesthesia Supplies
    'EN-CSD': 'THEATRE',                    # CSSD Supplies

    # General / non-medical / multi-store consumables
    'EN-CON': 'GENERAL,CENTRAL,SUB,WARD,EMERGENCY',   # Consumables Purchase
    'EN-CLN': 'GENERAL,NON_MEDICAL',        # Cleaning Supplies
    'EN-OFC': 'GENERAL,NON_MEDICAL,FRONT_DESK',        # Office Supplies
    'EN-MNT': 'GENERAL,NON_MEDICAL',        # Maintenance Parts

    # Lab (no dedicated LAB store type yet, use GENERAL)
    'EN-LAB': 'GENERAL,CENTRAL',            # Lab Reagents & Supplies

    # ── EXIT TYPES ─────────────────────────────────────────────────────────────

    # Generic / all stores
    'EX-CON': '',                           # Consumption             → ALL
    'EX-DIS': '',                           # Disposal                → ALL
    'EX-EXP': '',                           # Expired Write-off       → ALL
    'EX-PER': '',                           # Loss / Pilferage        → ALL
    'EX-TRF': '',                           # Transfer Out            → ALL
    'EX-AJU': '',                           # Adjustment Shortage (-) → ALL
    'EX-DON': '',                           # Donation Given          → ALL

    # Pharmacy only
    'EX-DSP': 'PHARMACY',                   # Pharmacy Dispensing
    'EX-PRE': 'PHARMACY',                   # Prescription Fill

    # Optical / Showroom only
    'EX-OPT': 'OPTICAL,SHOWROOM',           # Optical Sale Exit
    'EX-LNS': 'OPTICAL,SHOWROOM',           # Lens Sale Exit
    'EX-OPR': 'OPTICAL,SHOWROOM',           # Optical Repair Consumption
    'EX-SAM': 'OPTICAL,SHOWROOM',           # Sample / Demo
    'EX-VTE': 'OPTICAL,SHOWROOM,FRONT_DESK',# Sale Exit (general sales)

    # Theatre / Surgery
    'EX-THR': 'THEATRE',                    # Theatre Consumption
    'EX-ANS': 'THEATRE',                    # Anaesthesia Consumption
    'EX-CSD': 'THEATRE',                    # CSSD Consumption
    'EX-IMP': 'THEATRE',                    # Implant Used

    # Ward / Emergency
    'EX-WRD': 'WARD,EMERGENCY',             # Ward Issue
    'EX-EMG': 'EMERGENCY,WARD',             # Emergency Issue

    # General / non-medical
    'EX-CLN': 'GENERAL,NON_MEDICAL',        # Cleaning Consumption
    'EX-OFC': 'GENERAL,NON_MEDICAL',        # Office Consumption
    'EX-MNT': 'GENERAL,NON_MEDICAL',        # Maintenance Consumption

    # Lab
    'EX-LAB': 'GENERAL,CENTRAL',            # Lab Reagent Usage

    # Outreach / screening
    'EX-OUT': 'OUTREACH,PHARMACY,GENERAL',  # Outreach Issue
    'EX-SCR': 'OUTREACH,GENERAL',           # Screening Camp Issue
}

updated = 0
not_found = []
all_types = {op.code: op for op in StockOperationType.objects.all()}

print(f'Total op types in DB: {len(all_types)}')
print()

for code, loc in LOCATION_MAP.items():
    op = all_types.get(code)
    if not op:
        not_found.append(code)
        continue
    if op.location_types != loc:
        op.location_types = loc
        op.save(update_fields=['location_types'])
        updated += 1
        scope = loc if loc else 'ALL STORES'
        print(f'  [{op.category}] {code:<12} {op.name:<40} -> {scope}')

# Any remaining types not in our map stay blank (all stores)
for code, op in all_types.items():
    if code not in LOCATION_MAP and op.location_types != '':
        op.location_types = ''
        op.save(update_fields=['location_types'])
        updated += 1
        print(f'  [{op.category}] {code:<12} {op.name:<40} -> ALL STORES (reset)')

print()
print(f'Updated: {updated} operation types')
if not_found:
    print(f'Codes in map but not in DB (skipped): {not_found}')

print()
print('Summary by store type:')
from collections import defaultdict
store_map = defaultdict(list)
for code, loc in LOCATION_MAP.items():
    op = all_types.get(code)
    if not op:
        continue
    if loc:
        for s in loc.split(','):
            store_map[s.strip()].append(f"{code}({op.category})")
    else:
        store_map['ALL'].append(f"{code}({op.category})")

for store, codes in sorted(store_map.items()):
    print(f'  {store:<15}: {", ".join(codes)}')
