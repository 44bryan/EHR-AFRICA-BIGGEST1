"""Generate _seed_real_data.py from the parsed JSON files."""
import json, os

with open('_seed_data_services.json') as f: services = json.load(f)
with open('_seed_data_pharmacy.json') as f: pharmacy = json.load(f)
with open('_seed_data_inventory.json') as f: inventory = json.load(f)

lines = []
lines.append('#!/usr/bin/env python')
lines.append('"""Real Data Seed — MICEI Hospital. Run from /opt/ehr-africa."""')
lines.append('import os, sys, django')
lines.append("os.chdir('/opt/ehr-africa')")
lines.append("sys.path.insert(0, '/opt/ehr-africa')")
lines.append("os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.production'")
lines.append('django.setup()')
lines.append('from decimal import Decimal')
lines.append('from apps.billing.models import ServicePrice, ServiceSubCategory, GLAccount')
lines.append('from apps.pharmacy.models import Drug')
lines.append('from apps.inventory.models import InventoryItem, StoreLocation')
lines.append('')
lines.append('print("="*60)')
lines.append('print("MICEI Real Data Import")')
lines.append('print("="*60)')
lines.append('')

# Clear existing
lines.append('print("\\n[1] Clearing fake data...")')
lines.append('sp_del = ServicePrice.objects.filter(is_deleted=False).count()')
lines.append('ServicePrice.objects.all().update(is_deleted=True)')
lines.append('print(f"  Soft-deleted {sp_del} service prices")')
lines.append('d_del = Drug.objects.filter(is_deleted=False).count()')
lines.append('Drug.objects.all().update(is_deleted=True)')
lines.append('print(f"  Soft-deleted {d_del} drugs")')
lines.append('InventoryItem.objects.all().update(is_active=False)')
lines.append('print("  Deactivated old inventory items")')
lines.append('')

# Sub-categories
lines.append('print("\\n[2] Creating sub-categories...")')
lines.append('SUB_DEF = {')
sub_defs = [
    ('ANE: Anesthesia','SURGICAL','Anesthesia'),
    ('CAT: Cataract Surgery','SURGICAL','Cataract Surgery'),
    ('CON: Consultation','CONSULT','Consultation'),
    ('COR: Cornea Surgery','SURGICAL','Cornea Surgery'),
    ('CSM: Consumables','OTHER','Consumables'),
    ('GLA: Glaucoma Surgery','SURGICAL','Glaucoma Surgery'),
    ('HOS: Hospitalization','ADMISSION','Hospitalization'),
    ('INT: Internist Consultation','CONSULT','Internist Consultation'),
    ('INV: Investigation','INVEST','Investigation'),
    ('LAB: Laboratory','LAB','Laboratory'),
    ('LAS: Laser Treatment','SURGICAL','Laser Treatment'),
    ('OCU: Oculoplastic Surgery','SURGICAL','Oculoplastic Surgery'),
    ('OMS: Other Medical Services','OTHER','Other Medical Services'),
    ('ORT: Orthoptics','CONSULT','Orthoptics'),
    ('OTH: Other Surgeries','SURGICAL','Other Surgeries'),
    ('PF001: Patient Folder','REG','Patient Folder'),
    ('VIT: Vitreoretinal Surgery','SURGICAL','Vitreoretinal Surgery'),
]
for key, cat, name in sub_defs:
    code = key.split(':')[0].strip()
    lines.append(f'    {repr(key)}: ({repr(cat)}, {repr(name)}, {repr(code)}),')
lines.append('}')
lines.append('sub_map = {}')
lines.append('for k,(cat,name,code) in SUB_DEF.items():')
lines.append('    sc,_ = ServiceSubCategory.objects.get_or_create(category=cat, name=name, defaults={"code":code})')
lines.append('    sub_map[k] = sc')
lines.append('')

# Services
lines.append('print("\\n[3] Importing service prices...")')
lines.append('SERVICES = ' + repr(services))
lines.append('')
lines.append('cnt = 0')
lines.append('for it in SERVICES:')
lines.append('    sub = sub_map.get(it["sub"])')
lines.append('    ServicePrice.objects.update_or_create(')
lines.append('        code=it["code"], tier=it["tier"], is_deleted=False,')
lines.append('        defaults={')
lines.append('            "name": it["name"], "category": it["category"],')
lines.append('            "sub_category": sub, "price": Decimal(str(it["price"])),')
lines.append('            "entry_type": "SERVICE", "is_active": True,')
lines.append('        })')
lines.append('    cnt += 1')
lines.append('    if cnt % 200 == 0: print(f"  {cnt} services...")')
lines.append('print(f"  Service prices: {cnt}")')
lines.append('')

# Drug category guesser
lines.append('def guess_cat(n):')
lines.append('    n=n.upper()')
lines.append('    if any(x in n for x in ["ANTIBIOTIC","AMOXICILLIN","CIPROFLOX","DOXYCYCLINE","PENICILLIN"]): return "ANTIBIOTIC"')
lines.append('    if any(x in n for x in ["ACYCLOVIR","ANTIVIRAL","GANCICLOVIR"]): return "ANTIVIRAL"')
lines.append('    if any(x in n for x in ["TIMOLOL","LATANOPROST","BIMATOPROST","DORZOLAMIDE","TAFLUPROST","TRAVOPROST","PILOCARPINE","BRINZOLAMIDE","BRIMONIDINE"]): return "GLAUCOMA"')
lines.append('    if any(x in n for x in ["PREDNISOLONE","DEXAMETHASONE","BETAMETHASONE","FLUOROMETHOL","FLUORO"]): return "STEROID"')
lines.append('    if any(x in n for x in ["DICLOFENAC","FLURBIPROFEN","KETOROLAC","IBUPROFEN"]): return "NSAID"')
lines.append('    if any(x in n for x in ["ATROPINE","CYCLOPENTOLATE","TROPICAMIDE","PHENYLEPHRINE"]): return "MYDRIATIC"')
lines.append('    if any(x in n for x in ["ARTIFICIAL TEAR","HYALURONATE","HYDROXYPROPYL","CARBOMER","POLYVINYL","LUBRICANT"]): return "LUBRICANT"')
lines.append('    if any(x in n for x in ["PROPARACAINE","TETRACAINE","LIDOCAINE","ANAESTHETIC"]): return "ANAESTHETIC"')
lines.append('    if any(x in n for x in ["VITAMIN","LUTEIN","ZEAXANTHIN","ZINC SUPPLEMENT"]): return "VITAMIN"')
lines.append('    if any(x in n for x in ["PARACETAMOL","TRAMADOL","ANALGESIC"]): return "ANALGESIC"')
lines.append('    if any(x in n for x in ["ANTIFUNGAL","FLUCONAZOLE","KETOCONAZOLE"]): return "ANTIFUNGAL"')
lines.append('    return "OTHER"')
lines.append('')
lines.append('def guess_form(n):')
lines.append('    n=n.upper()')
lines.append('    if any(x in n for x in ["EYE DROP","OPHTHALMIC SOL","COLLYRE","/5ML","/10ML"]): return "EYE_DROP"')
lines.append('    if any(x in n for x in ["EYE OINTMENT","OPHTHALMIC OINT","POMMADE"]): return "EYE_OINTMENT"')
lines.append('    if any(x in n for x in ["TABLET","TAB ","MG TAB","COMPRIM"]): return "TABLET"')
lines.append('    if any(x in n for x in ["CAPSULE","CAP ","GELULE"]): return "CAPSULE"')
lines.append('    if any(x in n for x in ["INJECTION","INJ ","VIAL","IV ","IM "]): return "INJECTION"')
lines.append('    if any(x in n for x in ["SYRUP","SUSPENSION","SYR "]): return "SYRUP"')
lines.append('    if any(x in n for x in ["CREAM","CREME","GEL "]): return "CREAM"')
lines.append('    return "OTHER"')
lines.append('')

# Pharmacy
lines.append('print("\\n[4] Importing pharmacy drugs...")')
lines.append('PHARMACY = ' + repr(pharmacy))
lines.append('')
lines.append('dcnt, spcnt = 0, 0')
lines.append('for it in PHARMACY:')
lines.append('    if it["cat"] == "MED":')
lines.append('        dcat = guess_cat(it["name"])')
lines.append('        dform = guess_form(it["name"])')
lines.append('        _, created = Drug.objects.update_or_create(')
lines.append('            generic_name=it["name"],')
lines.append('            defaults={')
lines.append('                "name": it["name"], "category": dcat, "form": dform,')
lines.append('                "unit": "unit", "is_active": True, "is_deleted": False,')
lines.append('                "selling_price": Decimal(str(it["price"])),')
lines.append('                "price_express": Decimal(str(it["prices"].get("EXPRESS", it["price"]))),')
lines.append('                "price_vip": Decimal(str(it["prices"].get("VIP", it["price"]))),')
lines.append('                "price_executive_vip": Decimal(str(it["prices"].get("EVIP", it["price"]))),')
lines.append('                "reorder_level": 10,')
lines.append('            })')
lines.append('        if created: dcnt += 1')
lines.append('    sp_cat = "PHARMACY" if it["cat"]=="MED" else "OTHER"')
lines.append('    for tier,price in it["prices"].items():')
lines.append('        ServicePrice.objects.update_or_create(')
lines.append('            code=it["code"], tier=tier, is_deleted=False,')
lines.append('            defaults={')
lines.append('                "name": it["name"], "category": sp_cat,')
lines.append('                "price": Decimal(str(price)),')
lines.append('                "entry_type": "ITEM", "is_stockable": True, "is_active": True,')
lines.append('            })')
lines.append('        spcnt += 1')
lines.append('print(f"  Drugs: {dcnt}, Price entries: {spcnt}")')
lines.append('')

# Inventory — split into batches
lines.append('print("\\n[5] Importing inventory items...")')
lines.append('store_map = {s.store_code: s for s in StoreLocation.objects.filter(is_deleted=False)}')
lines.append('print(f"  Stores: {list(store_map.keys())}")')
lines.append('icnt, iskip = 0, 0')

batch_size = 300
for batch_num, start in enumerate(range(0, len(inventory), batch_size)):
    batch = inventory[start:start+batch_size]
    lines.append(f'INV{batch_num} = ' + repr(batch))

lines.append(f'ALL_INV = INV0')
for i in range(1, (len(inventory) // batch_size) + 1):
    lines.append(f'ALL_INV = ALL_INV + INV{i}')

lines.append('for it in ALL_INV:')
lines.append('    code = it["code"].strip()')
lines.append('    if not code or len(code) < 2: iskip+=1; continue')
lines.append('    store = store_map.get(it["store"])')
lines.append('    try:')
lines.append('        _, created = InventoryItem.objects.update_or_create(')
lines.append('            item_code=code,')
lines.append('            defaults={')
lines.append('                "name": it["name"], "category": it["item_cat"],')
lines.append('                "unit": "unit", "store_location": store,')
lines.append('                "is_active": True, "current_stock": 0, "reorder_level": 5,')
lines.append('            })')
lines.append('        if created: icnt += 1')
lines.append('    except Exception as e: iskip += 1')
lines.append('print(f"  Inventory: {icnt} created, {iskip} skipped")')
lines.append('')
lines.append('print("\\n" + "="*60)')
lines.append('print("IMPORT COMPLETE")')
lines.append('print("="*60)')

with open('_seed_real_data.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines) + '\n')

size = os.path.getsize('_seed_real_data.py')
print(f'Generated _seed_real_data.py — {size:,} bytes ({len(lines)} lines)')
