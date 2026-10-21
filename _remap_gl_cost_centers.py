"""
Remap existing JournalEntry cost_center FKs from old codes to new real AEF codes.

Old codes → New codes:
  0001 Pharmacy          → 008 Pharmacy
  0002 Theatre           → 001 Ophthalmology  (OT is ophthalmic surgery at AEF)
  0003 OPD               → 001 Ophthalmology  (OPD = ophthalmology consultations)
  0004 Laboratory        → 004 Laboratory
  0005 Optical           → 009 Optical Shop
  0006 IPD / Ward        → 006 Accommodation
  0007 Radiology         → 004 Laboratory     (imaging is part of diagnostics)
  0008 Administration    → 012 Finance & Administration
  0009 Finance           → 012 Finance & Administration
  0010 CSSD              → 013 Other Support Services
  0011 Nutrition         → 013 Other Support Services
  0012 Maintenance       → 013 Other Support Services
  ADM                    → 012 Finance & Administration
  FIN                    → 012 Finance & Administration
  HRM                    → 012 Finance & Administration
  IPD                    → 006 Accommodation
  LAB                    → 004 Laboratory
  LVS                    → 001 Ophthalmology
  MNT                    → 013 Other Support Services
  NUR                    → 001 Ophthalmology
  OPD                    → 001 Ophthalmology
  OPT                    → 009 Optical Shop
  ORT                    → 001 Ophthalmology
  OUT                    → 010 Outreach
  PHR                    → 008 Pharmacy
  RAD                    → 004 Laboratory
  SRG                    → 001 Ophthalmology
"""
import sys, os, django
sys.path.insert(0, '/opt/ehr-africa')
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.base'
django.setup()

from apps.billing.models import CostCenter, JournalEntry

# Build old_code → new_code mapping
OLD_TO_NEW = {
    '0001': '008', '0002': '001', '0003': '001', '0004': '004',
    '0005': '009', '0006': '006', '0007': '004', '0008': '012',
    '0009': '012', '0010': '013', '0011': '013', '0012': '013',
    'ADM':  '012', 'FIN':  '012', 'HRM':  '012', 'IPD':  '006',
    'LAB':  '004', 'LVS':  '001', 'MNT':  '013', 'NUR':  '001',
    'OPD':  '001', 'OPT':  '009', 'ORT':  '001', 'OUT':  '010',
    'PHR':  '008', 'RAD':  '004', 'SRG':  '001',
}

# Load all CostCenters by code (including soft-deleted old ones)
all_cc = {cc.code: cc for cc in CostCenter.objects.all()}
print(f"Loaded {len(all_cc)} cost centers")

# Verify all target codes exist and are active
missing = []
for new_code in set(OLD_TO_NEW.values()):
    if new_code not in all_cc or all_cc[new_code].is_deleted:
        missing.append(new_code)
if missing:
    print("ERROR — target codes not found or deleted:", missing)
    sys.exit(1)

total_updated = 0
for old_code, new_code in OLD_TO_NEW.items():
    if old_code not in all_cc:
        continue
    old_cc = all_cc[old_code]
    new_cc = all_cc[new_code]
    n = JournalEntry.objects.filter(cost_center=old_cc).update(cost_center=new_cc)
    if n:
        print(f"  {old_code} ({old_cc.name}) → {new_code} ({new_cc.name}): {n} entries remapped")
        total_updated += n

print()
print(f"Total remapped: {total_updated} GL entries")

# Final check
from django.db.models import Count
qs = (JournalEntry.objects
      .filter(is_deleted=False, cost_center__isnull=False)
      .values('cost_center__code', 'cost_center__name')
      .annotate(n=Count('id'))
      .order_by('cost_center__code'))
print()
print("New distribution:")
for r in qs:
    print(f"  {r['cost_center__code']} {r['cost_center__name']}: {r['n']} entries")
