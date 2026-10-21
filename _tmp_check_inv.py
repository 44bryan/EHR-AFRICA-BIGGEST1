
import os, sys, django
sys.path.insert(0, "/opt/ehr-africa")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ehr_project.settings.base")
django.setup()
from apps.billing.models import StockOperationType

# Simulate op_types_by_store_ajax for PHARMACY store (ENTRY)
store_type = "PHARMACY"
category = "ENTRY"
qs = StockOperationType.objects.filter(category=category, is_active=True, is_deleted=False)
result = []
for op in qs:
    if not op.location_types or (store_type and op.applies_to_store_type(store_type)):
        result.append(f"{op.code} | {op.name} | loc_types={op.location_types\!r} | dr={op.debit_account_id} | cr={op.credit_account_id}")
print(f"PHARMACY ENTRY ops: {len(result)}")
for r in result: print(" ", r)

# Also check CENTRAL (Medical Consumables Main Store)
store_type2 = "CENTRAL"
result2 = []
for op in qs:
    if not op.location_types or (store_type2 and op.applies_to_store_type(store_type2)):
        result2.append(f"{op.code} | {op.name}")
print(f"CENTRAL ENTRY ops: {len(result2)}")
for r in result2: print(" ", r)

# Check THEATRE (OT Store)
store_type3 = "THEATRE"
result3 = []
for op in qs:
    if not op.location_types or (store_type3 and op.applies_to_store_type(store_type3)):
        result3.append(f"{op.code} | {op.name}")
print(f"THEATRE ENTRY ops: {len(result3)}")
for r in result3: print(" ", r)
