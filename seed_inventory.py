"""
Inventory seed script — realistic demo data for finance director presentation.
Run on server: python seed_inventory.py  (from /opt/ehr-africa with venv active)
"""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
sys.path.insert(0, '/opt/ehr-africa')
django.setup()

from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone
from apps.inventory.models import (
    InventoryItem, Vendor, PurchaseOrder, PurchaseOrderItem,
    BatchStock, StockMovement, DepartmentRequisition, RequisitionItem,
    ItemCategory, PurchaseOrderStatus, RequisitionStatus,
)
from apps.accounts.models import User

today = date.today()
admin = User.objects.filter(is_superuser=True).first()

print("Clearing existing inventory data...")
RequisitionItem.objects.all().delete()
DepartmentRequisition.objects.all().delete()
StockMovement.objects.all().delete()
BatchStock.objects.all().delete()
PurchaseOrderItem.objects.all().delete()
PurchaseOrder.objects.all().delete()
InventoryItem.objects.all().delete()
Vendor.objects.all().delete()

# ── VENDORS ─────────────────────────────────────────────────────────────────
print("Creating vendors...")
vendors = {}

v_data = [
    dict(name="MEDIPHARM Cameroon SARL",        contact_person="Jean-Baptiste Fouda",    phone="+237 677 112 233", email="orders@medipharm-cm.com",    address="Rue 1.082, Akwa, Douala",            total_orders=48, on_time_deliveries=47, late_deliveries=1,  quality_incidents=0, notes="Primary pharma supplier. ISO-certified cold chain.", key='medipharm'),
    dict(name="AfricaMed Supplies Ltd",          contact_person="Nkemdirim Chukwu",       phone="+237 699 445 566", email="supply@africamed.com",        address="Zone Industrielle, Bassa, Douala",   total_orders=32, on_time_deliveries=30, late_deliveries=2,  quality_incidents=1, notes="Surgical consumables and PPE. Competitive pricing.", key='africamed'),
    dict(name="OPHTEX Vision Supplies",          contact_person="Sophie Abena",           phone="+237 655 778 899", email="sales@ophtex.cm",             address="Quartier Bastos, Yaoundé",           total_orders=20, on_time_deliveries=19, late_deliveries=1,  quality_incidents=0, notes="Specialist ophthalmic lenses and consumables. Consignment terms available.", key='ophtex'),
    dict(name="LabCore Diagnostics",             contact_person="Dr. Paul Ngah",          phone="+237 688 334 455", email="labcore@diagnostics.cm",      address="Rue de la Science, Yaoundé",         total_orders=25, on_time_deliveries=21, late_deliveries=4,  quality_incidents=2, notes="Lab reagents. Occasional cold-chain issues — monitor closely.", key='labcore'),
    dict(name="CleanPro Hospital Services",      contact_person="Mireille Tagne",         phone="+237 677 990 011", email="info@cleanpro.cm",            address="BP 1452, Bafoussam",                 total_orders=18, on_time_deliveries=18, late_deliveries=0,  quality_incidents=0, notes="Cleaning supplies and housekeeping materials. Always on time.", key='cleanpro'),
    dict(name="TechMed Equipment Cameroon",      contact_person="Ibrahim Moussa",         phone="+237 699 123 456", email="techmed@equip.cm",            address="Avenue de Gaulle, Douala",           total_orders=10, on_time_deliveries=7,  late_deliveries=3,  quality_incidents=1, notes="Medical equipment supplier. Delivery consistency needs improvement.", key='techmed'),
    dict(name="PharmaCentre Yaounde",            contact_person="Dr. Chantal Biya",       phone="+237 655 221 133", email="pharmacentre@yde.cm",         address="Quartier Nlongkak, Yaoundé",         total_orders=15, on_time_deliveries=14, late_deliveries=1,  quality_incidents=0, notes="Secondary pharma supplier for urgent orders.", key='pharmacentre'),
]

for vd in v_data:
    key = vd.pop('key')
    v = Vendor.objects.create(**vd)
    vendors[key] = v
    print(f"  Vendor: {v.name} — {v.performance_rating}")


# ── INVENTORY ITEMS ──────────────────────────────────────────────────────────
print("Creating inventory items...")
items = {}

item_data = [
    # PHARMACEUTICALS (expiry tracked)
    dict(name="Amoxicillin 500mg Capsules",    item_code="PHM-001", category='PHARMACEUTICAL', unit="box/100",   unit_cost=4500,  reorder_level=20,  current_stock=85,  location="Pharmacy Store A, Shelf 2",   requires_expiry_tracking=True,  storage_conditions="Room temperature 15–25 °C",          preferred_vendor='medipharm',    description="Broad-spectrum antibiotic. First-line for respiratory infections.", key='amox'),
    dict(name="Ciprofloxacin 500mg Tablets",   item_code="PHM-002", category='PHARMACEUTICAL', unit="box/50",    unit_cost=6800,  reorder_level=15,  current_stock=42,  location="Pharmacy Store A, Shelf 2",   requires_expiry_tracking=True,  storage_conditions="Room temperature 15–25 °C",          preferred_vendor='medipharm',    description="Fluoroquinolone antibiotic. Second-line treatment.", key='cipro'),
    dict(name="Metronidazole 500mg IV",        item_code="PHM-003", category='PHARMACEUTICAL', unit="vial",      unit_cost=1200,  reorder_level=30,  current_stock=18,  location="Pharmacy Store A, Shelf 4",   requires_expiry_tracking=True,  storage_conditions="Room temperature, protect from light", preferred_vendor='medipharm',    description="IV antibiotic for anaerobic infections. ICU essential.", key='metro'),
    dict(name="Paracetamol 1g IV Infusion",    item_code="PHM-004", category='PHARMACEUTICAL', unit="bag",       unit_cost=2100,  reorder_level=50,  current_stock=120, location="Pharmacy Store B, Shelf 1",   requires_expiry_tracking=True,  storage_conditions="Room temperature",                    preferred_vendor='pharmacentre', description="IV paracetamol for post-operative pain management.", key='paraciv'),
    dict(name="Dexamethasone 4mg/2ml Injection",item_code="PHM-005",category='PHARMACEUTICAL', unit="ampoule",   unit_cost=850,   reorder_level=40,  current_stock=6,   location="Pharmacy Store A, Shelf 5",   requires_expiry_tracking=True,  storage_conditions="Room temperature, protect from light", preferred_vendor='medipharm',    description="Corticosteroid. Used in ophthalmology and ICU.", key='dexa'),
    dict(name="Atropine 1% Eye Drops",         item_code="PHM-006", category='PHARMACEUTICAL', unit="bottle/5ml",unit_cost=3200,  reorder_level=10,  current_stock=28,  location="Pharmacy Eye Clinic Fridge",  requires_expiry_tracking=True,  storage_conditions="Refrigerate 2–8 °C",                  preferred_vendor='ophtex',       description="Mydriatic agent for ophthalmic procedures.", key='atrop'),
    dict(name="Fluorescein Sodium 2% Drops",   item_code="PHM-007", category='PHARMACEUTICAL', unit="strip/12",  unit_cost=4100,  reorder_level=8,   current_stock=22,  location="Pharmacy Eye Clinic",         requires_expiry_tracking=True,  storage_conditions="Room temperature, single-use",        preferred_vendor='ophtex',       description="Diagnostic dye for corneal staining (Goldman tonometry).", key='fluor'),
    dict(name="Ringer's Lactate 500ml",        item_code="PHM-008", category='PHARMACEUTICAL', unit="bag",       unit_cost=1800,  reorder_level=100, current_stock=240, location="Pharmacy Store B, Shelf 3",   requires_expiry_tracking=True,  storage_conditions="Room temperature",                    preferred_vendor='pharmacentre', description="IV fluid for rehydration and surgical use.", key='ringer'),

    # LAB REAGENTS (expiry tracked)
    dict(name="Blood Glucose Strips (ACCU-CHEK)",item_code="LAB-001",category='PHARMACEUTICAL', unit="box/50",   unit_cost=12000, reorder_level=10,  current_stock=35,  location="Lab Reagent Fridge",          requires_expiry_tracking=True,  storage_conditions="Refrigerate 2–8 °C",                  preferred_vendor='labcore',      description="Blood glucose test strips. ISO 15189 approved.", key='glucstrip'),
    dict(name="HbA1c Test Cartridges",          item_code="LAB-002", category='PHARMACEUTICAL', unit="cartridge", unit_cost=8500,  reorder_level=8,   current_stock=14,  location="Lab Reagent Fridge",          requires_expiry_tracking=True,  storage_conditions="Refrigerate 2–8 °C",                  preferred_vendor='labcore',      description="Point-of-care HbA1c for diabetes monitoring.", key='hba1c'),
    dict(name="Rapid Malaria RDT Kit",          item_code="LAB-003", category='PHARMACEUTICAL', unit="kit/25",    unit_cost=15000, reorder_level=5,   current_stock=12,  location="Lab Store, Shelf 1",          requires_expiry_tracking=True,  storage_conditions="Room temperature 4–30 °C",            preferred_vendor='labcore',      description="WHO pre-qualified rapid diagnostic test for malaria.", key='malariardt'),
    dict(name="HIV Rapid Test (Determine)",     item_code="LAB-004", category='PHARMACEUTICAL', unit="kit/20",    unit_cost=22000, reorder_level=4,   current_stock=9,   location="Lab Store, Shelf 1",          requires_expiry_tracking=True,  storage_conditions="Room temperature 2–30 °C",            preferred_vendor='labcore',      description="1st line HIV rapid test. NACP-approved.", key='hivtest'),

    # SURGICAL CONSUMABLES
    dict(name="Surgical Gloves — Medium (Sterile)", item_code="SUR-001", category='SURGICAL', unit="pair",     unit_cost=450,   reorder_level=200, current_stock=580, location="Theatre Store, Shelf A",      requires_expiry_tracking=False, storage_conditions="Room temperature, dry",               preferred_vendor='africamed',    description="Latex sterile surgical gloves size M.", key='gloves_m'),
    dict(name="Surgical Gloves — Large (Sterile)",  item_code="SUR-002", category='SURGICAL', unit="pair",     unit_cost=450,   reorder_level=150, current_stock=320, location="Theatre Store, Shelf A",      requires_expiry_tracking=False, storage_conditions="Room temperature, dry",               preferred_vendor='africamed',    description="Latex sterile surgical gloves size L.", key='gloves_l'),
    dict(name="Suture — Vicryl 2-0 (absorbable)",  item_code="SUR-003", category='SURGICAL', unit="box/12",   unit_cost=18000, reorder_level=5,   current_stock=22,  location="Theatre Store, Shelf B",      requires_expiry_tracking=True,  storage_conditions="Room temperature, intact packaging",  preferred_vendor='africamed',    description="Polyglactin 910 absorbable suture. JCI MMU.3.", key='vicryl'),
    dict(name="Suture — Prolene 6-0 (ophthalmic)", item_code="SUR-004", category='SURGICAL', unit="box/12",   unit_cost=24000, reorder_level=4,   current_stock=11,  location="Theatre Eye Store",           requires_expiry_tracking=True,  storage_conditions="Room temperature",                    preferred_vendor='ophtex',       description="Non-absorbable monofilament suture for eye surgery.", key='prolene'),
    dict(name="IV Cannula 20G",                item_code="SUR-005", category='MEDICAL_CONSUMABLE', unit="piece", unit_cost=350,  reorder_level=100, current_stock=420, location="Nursing Store, Shelf 2",      requires_expiry_tracking=False, storage_conditions="Room temperature",                    preferred_vendor='africamed',    description="IV access cannula, 20 gauge.", key='cannula20'),
    dict(name="IV Cannula 18G",                item_code="SUR-006", category='MEDICAL_CONSUMABLE', unit="piece", unit_cost=350,  reorder_level=80,  current_stock=290, location="Nursing Store, Shelf 2",      requires_expiry_tracking=False, storage_conditions="Room temperature",                    preferred_vendor='africamed',    description="IV access cannula, 18 gauge — large bore.", key='cannula18'),
    dict(name="Disposable Syringe 5ml",        item_code="SUR-007", category='MEDICAL_CONSUMABLE', unit="piece", unit_cost=120,  reorder_level=300, current_stock=1200,location="Nursing Store, Shelf 1",      requires_expiry_tracking=False, storage_conditions="Room temperature",                    preferred_vendor='africamed',    description="Luer-lock disposable syringe.", key='syringe5'),
    dict(name="Disposable Syringe 10ml",       item_code="SUR-008", category='MEDICAL_CONSUMABLE', unit="piece", unit_cost=150,  reorder_level=200, current_stock=750, location="Nursing Store, Shelf 1",      requires_expiry_tracking=False, storage_conditions="Room temperature",                    preferred_vendor='africamed',    description="Luer-lock disposable syringe 10ml.", key='syringe10'),
    dict(name="Urinary Catheter — Foley 16Fr", item_code="SUR-009", category='MEDICAL_CONSUMABLE', unit="piece", unit_cost=2800, reorder_level=20,  current_stock=65,  location="Theatre Store, Shelf C",      requires_expiry_tracking=True,  storage_conditions="Room temperature, sterile until opened",preferred_vendor='africamed',   description="Two-way silicone Foley catheter.", key='catheter'),

    # OPHTHALMIC LENSES (consignment)
    dict(name="IOL — Monofocal Hydrophilic (MICS)", item_code="LENS-001", category='LENS', unit="lens",  unit_cost=45000, reorder_level=2, current_stock=8,  location="Theatre Eye Cabinet — Locked",requires_expiry_tracking=True,  storage_conditions="Room temperature, sealed",            preferred_vendor='ophtex',       is_consignment=True, udi_code="(01)07612345678906(17)260831",  description="Monofocal hydrophilic acrylic IOL. Consignment — charged at implant.", key='iol_mono'),
    dict(name="IOL — Toric Premium (Astigmatism)",   item_code="LENS-002", category='LENS', unit="lens",  unit_cost=95000, reorder_level=2, current_stock=5,  location="Theatre Eye Cabinet — Locked",requires_expiry_tracking=True,  storage_conditions="Room temperature, sealed",            preferred_vendor='ophtex',       is_consignment=True, udi_code="(01)07612345678913(17)261130",  description="Premium toric IOL for astigmatism correction. Consignment.", key='iol_toric'),

    # IMPLANTS
    dict(name="Glaucoma Drainage Implant (Ahmed)",  item_code="IMP-001", category='IMPLANT', unit="implant", unit_cost=280000, reorder_level=1, current_stock=3, location="Theatre Eye Cabinet — Locked", requires_expiry_tracking=True, storage_conditions="Room temperature, sterile packaging",preferred_vendor='ophtex',      udi_code="(01)00843209000045(17)270630",  description="Ahmed Glaucoma Valve FP7. Sterile single-use implant.", key='ahmed'),

    # CLEANING
    dict(name="Chlorhexidine 4% Surgical Scrub",   item_code="CLN-001", category='CLEANING', unit="bottle/500ml", unit_cost=2800, reorder_level=15, current_stock=45, location="Theatre Scrub Area",        requires_expiry_tracking=False, storage_conditions="Room temperature",                    preferred_vendor='cleanpro',     description="Antiseptic skin cleanser for surgical hand scrub.", key='chlorhex'),
    dict(name="Alcohol 70% (Isopropyl) 1L",        item_code="CLN-002", category='CLEANING', unit="bottle",       unit_cost=3200, reorder_level=20, current_stock=60, location="Housekeeping Store",         requires_expiry_tracking=False, storage_conditions="Cool dry place, away from flame",     preferred_vendor='cleanpro',     description="Surface and skin disinfectant.", key='alcohol'),
    dict(name="Bleach Solution 10% (5L)",          item_code="CLN-003", category='CLEANING', unit="jerry can",    unit_cost=4500, reorder_level=10, current_stock=22, location="Housekeeping Store",         requires_expiry_tracking=False, storage_conditions="Cool place, avoid sunlight",           preferred_vendor='cleanpro',     description="High-level disinfectant for surfaces and spills.", key='bleach'),
    dict(name="N95 Respirator Masks",              item_code="CLN-004", category='MEDICAL_CONSUMABLE', unit="box/20", unit_cost=9500, reorder_level=10, current_stock=4, location="Nursing Store, Shelf 3",  requires_expiry_tracking=False, storage_conditions="Dry room temperature",                 preferred_vendor='africamed',    description="NIOSH-approved N95 respirator. Infection control standard.", key='n95'),

    # OFFICE / ADMIN
    dict(name="A4 Paper Ream",                     item_code="OFC-001", category='OFFICE', unit="ream",    unit_cost=3500, reorder_level=10, current_stock=45,  location="Admin Store",                 requires_expiry_tracking=False, storage_conditions="Dry room temperature",                 preferred_vendor='cleanpro',     description="80g/m² A4 printing paper.", key='paper'),
    dict(name="Prescription Pad (50 leaves)",      item_code="OFC-002", category='OFFICE', unit="pad",     unit_cost=1200, reorder_level=20, current_stock=38,  location="Admin Store",                 requires_expiry_tracking=False, storage_conditions="Dry room temperature",                 preferred_vendor='cleanpro',     description="NCR prescription pads — numbered.", key='rxpad'),
]

for idata in item_data:
    key = idata.pop('key')
    vendor_key = idata.pop('preferred_vendor', None)
    idata['preferred_vendor'] = vendors.get(vendor_key)
    item = InventoryItem.objects.create(**idata)
    items[key] = item

print(f"  Created {len(items)} items")


# ── PURCHASE ORDERS ──────────────────────────────────────────────────────────
print("Creating purchase orders...")

def make_po(vendor_key, status, ordered_days_ago, expected_days_from_order=7, received_days_ago=None, notes='', is_auto=False):
    v = vendors[vendor_key]
    ordered_date = today - timedelta(days=ordered_days_ago)
    expected_date = ordered_date + timedelta(days=expected_days_from_order)
    received_date = today - timedelta(days=received_days_ago) if received_days_ago is not None else None
    po = PurchaseOrder(
        vendor=v, status=status,
        ordered_date=ordered_date, expected_date=expected_date,
        received_date=received_date, notes=notes,
        approved_by=admin if status not in ('DRAFT',) else None,
        is_auto_generated=is_auto,
    )
    po.po_number = None  # let save() generate
    # temporarily set to avoid collision
    import random
    po.po_number = f"TEMP-{random.randint(100000,999999)}"
    po.save()
    # Now regenerate proper number
    count = PurchaseOrder.objects.filter(ordered_date__year=ordered_date.year).count()
    po.po_number = f"{ordered_date.year}-{count:04d}"
    PurchaseOrder.objects.filter(pk=po.pk).update(po_number=po.po_number, total_amount=0)
    po.refresh_from_db()
    return po

# PO 1 — RECEIVED — Medipharm (pharma bulk)
po1 = make_po('medipharm', 'RECEIVED', ordered_days_ago=45, expected_days_from_order=7, received_days_ago=37, notes="Quarterly pharma restocking — Q3 2026")
po1_items = [
    (items['amox'],    200, Decimal('4500')),
    (items['cipro'],   100, Decimal('6800')),
    (items['paraciv'], 300, Decimal('2100')),
    (items['ringer'],  500, Decimal('1800')),
]
total = Decimal('0')
for item, qty, price in po1_items:
    poi = PurchaseOrderItem.objects.create(
        purchase_order=po1, item=item, quantity_ordered=qty,
        quantity_received=qty, unit_price=price,
        lot_number=f"MPC-{today.year}-{item.item_code}-01",
        manufactured_date=today - timedelta(days=90),
        expiry_date=today + timedelta(days=730),
    )
    total += poi.subtotal
PurchaseOrder.objects.filter(pk=po1.pk).update(total_amount=total)

# PO 2 — RECEIVED — AfricaMed (surgical supplies)
po2 = make_po('africamed', 'RECEIVED', ordered_days_ago=30, expected_days_from_order=5, received_days_ago=24, notes="Surgical consumables top-up")
po2_items = [
    (items['gloves_m'], 500, Decimal('450')),
    (items['gloves_l'], 300, Decimal('450')),
    (items['cannula20'],400, Decimal('350')),
    (items['cannula18'],300, Decimal('350')),
    (items['syringe5'], 800, Decimal('120')),
    (items['syringe10'],500, Decimal('150')),
    (items['catheter'],  80, Decimal('2800')),
]
total = Decimal('0')
for item, qty, price in po2_items:
    poi = PurchaseOrderItem.objects.create(
        purchase_order=po2, item=item, quantity_ordered=qty,
        quantity_received=qty, unit_price=price,
    )
    total += poi.subtotal
PurchaseOrder.objects.filter(pk=po2.pk).update(total_amount=total)

# PO 3 — RECEIVED — OPHTEX (lenses + ophthalmic)
po3 = make_po('ophtex', 'RECEIVED', ordered_days_ago=20, expected_days_from_order=10, received_days_ago=8, notes="Ophthalmic items — eye clinic restocking")
po3_items = [
    (items['atrop'],    50, Decimal('3200')),
    (items['fluor'],    60, Decimal('4100')),
    (items['prolene'],  24, Decimal('24000')),
    (items['iol_mono'], 10, Decimal('45000')),
    (items['iol_toric'], 5, Decimal('95000')),
    (items['ahmed'],     3, Decimal('280000')),
]
total = Decimal('0')
for item, qty, price in po3_items:
    poi = PurchaseOrderItem.objects.create(
        purchase_order=po3, item=item, quantity_ordered=qty,
        quantity_received=qty, unit_price=price,
        lot_number=f"OPX-{today.year}-{item.item_code}",
        manufactured_date=today - timedelta(days=60),
        expiry_date=today + timedelta(days=548),
    )
    total += poi.subtotal
PurchaseOrder.objects.filter(pk=po3.pk).update(total_amount=total)

# PO 4 — RECEIVED — LabCore (reagents — some near expiry for demo)
po4 = make_po('labcore', 'RECEIVED', ordered_days_ago=180, expected_days_from_order=7, received_days_ago=172, notes="Lab reagents — older batch, monitor expiry")
po4_items = [
    (items['glucstrip'], 30, Decimal('12000')),
    (items['hba1c'],     20, Decimal('8500')),
    (items['malariardt'],15, Decimal('15000')),
    (items['hivtest'],   10, Decimal('22000')),
]
total = Decimal('0')
for item, qty, price in po4_items:
    poi = PurchaseOrderItem.objects.create(
        purchase_order=po4, item=item, quantity_ordered=qty,
        quantity_received=qty, unit_price=price,
        lot_number=f"LBC-{today.year - 1}-{item.item_code}",
        manufactured_date=today - timedelta(days=365),
        expiry_date=today + timedelta(days=45),  # expiring soon — for dashboard alerts!
    )
    total += poi.subtotal
PurchaseOrder.objects.filter(pk=po4.pk).update(total_amount=total)

# PO 5 — APPROVED — CleanPro (pending delivery)
po5 = make_po('cleanpro', 'APPROVED', ordered_days_ago=5, expected_days_from_order=3, notes="Cleaning supplies — routine monthly order")
po5_items = [
    (items['chlorhex'], 50, Decimal('2800')),
    (items['alcohol'],  80, Decimal('3200')),
    (items['bleach'],   40, Decimal('4500')),
    (items['paper'],    30, Decimal('3500')),
]
total = Decimal('0')
for item, qty, price in po5_items:
    poi = PurchaseOrderItem.objects.create(
        purchase_order=po5, item=item, quantity_ordered=qty,
        quantity_received=0, unit_price=price,
    )
    total += poi.subtotal
PurchaseOrder.objects.filter(pk=po5.pk).update(total_amount=total)

# PO 6 — SUBMITTED — Medipharm (critical restock — dexamethasone low)
po6 = make_po('medipharm', 'SUBMITTED', ordered_days_ago=2, expected_days_from_order=5, notes="URGENT: Dexamethasone and Metronidazole critically low")
po6_items = [
    (items['dexa'],  150, Decimal('850')),
    (items['metro'],  100, Decimal('1200')),
    (items['amox'],   100, Decimal('4500')),
]
total = Decimal('0')
for item, qty, price in po6_items:
    poi = PurchaseOrderItem.objects.create(
        purchase_order=po6, item=item, quantity_ordered=qty,
        quantity_received=0, unit_price=price,
    )
    total += poi.subtotal
PurchaseOrder.objects.filter(pk=po6.pk).update(total_amount=total)

# PO 7 — DRAFT — Auto-generated (N95 reorder trigger)
po7 = make_po('africamed', 'DRAFT', ordered_days_ago=1, expected_days_from_order=4, notes="Auto-generated: N95 masks hit reorder level", is_auto=True)
poi7 = PurchaseOrderItem.objects.create(
    purchase_order=po7, item=items['n95'], quantity_ordered=50, quantity_received=0, unit_price=Decimal('9500'),
)
PurchaseOrder.objects.filter(pk=po7.pk).update(total_amount=poi7.subtotal)

# PO 8 — RECEIVED — PharmaCentre (sutures for theatre)
po8 = make_po('pharmacentre', 'RECEIVED', ordered_days_ago=15, expected_days_from_order=5, received_days_ago=9, notes="Theatre sutures replenishment")
po8_items = [
    (items['vicryl'],  36, Decimal('18000')),
    (items['prolene'], 12, Decimal('24000')),
]
total = Decimal('0')
for item, qty, price in po8_items:
    poi = PurchaseOrderItem.objects.create(
        purchase_order=po8, item=item, quantity_ordered=qty,
        quantity_received=qty, unit_price=price,
        lot_number=f"PHA-{today.year}-SUTURES",
        manufactured_date=today - timedelta(days=30),
        expiry_date=today + timedelta(days=1095),
    )
    total += poi.subtotal
PurchaseOrder.objects.filter(pk=po8.pk).update(total_amount=total)

print("  Created 8 purchase orders")


# ── BATCH STOCK (FEFO demo data) ─────────────────────────────────────────────
print("Creating batch stocks (FEFO demo)...")

batch_data = [
    # Amoxicillin — 3 batches, different expiry for FEFO demo
    dict(item=items['amox'],    lot_number="MPC-2026-A1", manufactured_date=today-timedelta(days=365), expiry_date=today+timedelta(days=180), quantity_received=100, quantity_remaining=35,  unit_cost=Decimal('4500'), purchase_order=po1),
    dict(item=items['amox'],    lot_number="MPC-2026-A2", manufactured_date=today-timedelta(days=90),  expiry_date=today+timedelta(days=540), quantity_received=100, quantity_remaining=50,  unit_cost=Decimal('4500'), purchase_order=po1),

    # Ciprofloxacin
    dict(item=items['cipro'],   lot_number="MPC-2026-C1", manufactured_date=today-timedelta(days=90),  expiry_date=today+timedelta(days=730), quantity_received=100, quantity_remaining=42,  unit_cost=Decimal('6800'), purchase_order=po1),

    # Metronidazole — LOW STOCK (triggers reorder)
    dict(item=items['metro'],   lot_number="PHA-2026-M1", manufactured_date=today-timedelta(days=60),  expiry_date=today+timedelta(days=640), quantity_received=50,  quantity_remaining=18,  unit_cost=Decimal('1200'), purchase_order=po1),

    # Paracetamol IV
    dict(item=items['paraciv'], lot_number="PHA-2026-P1", manufactured_date=today-timedelta(days=45),  expiry_date=today+timedelta(days=730), quantity_received=300, quantity_remaining=120, unit_cost=Decimal('2100'), purchase_order=po1),

    # Dexamethasone — CRITICALLY LOW
    dict(item=items['dexa'],    lot_number="MPC-2026-D1", manufactured_date=today-timedelta(days=120), expiry_date=today+timedelta(days=365), quantity_received=80,  quantity_remaining=6,   unit_cost=Decimal('850'),  purchase_order=po1),

    # Atropine eye drops
    dict(item=items['atrop'],   lot_number="OPX-2026-AT", manufactured_date=today-timedelta(days=60),  expiry_date=today+timedelta(days=365), quantity_received=50,  quantity_remaining=28,  unit_cost=Decimal('3200'), purchase_order=po3),

    # Fluorescein
    dict(item=items['fluor'],   lot_number="OPX-2026-FL", manufactured_date=today-timedelta(days=30),  expiry_date=today+timedelta(days=548), quantity_received=60,  quantity_remaining=22,  unit_cost=Decimal('4100'), purchase_order=po3),

    # Lab reagents — EXPIRING SOON (≤45 days)
    dict(item=items['glucstrip'],lot_number="LBC-2025-G1", manufactured_date=today-timedelta(days=320), expiry_date=today+timedelta(days=45),  quantity_received=30,  quantity_remaining=14,  unit_cost=Decimal('12000'),purchase_order=po4),
    dict(item=items['hba1c'],   lot_number="LBC-2025-H1", manufactured_date=today-timedelta(days=350), expiry_date=today+timedelta(days=45),  quantity_received=20,  quantity_remaining=8,   unit_cost=Decimal('8500'), purchase_order=po4),
    dict(item=items['malariardt'],lot_number="LBC-2025-M1",manufactured_date=today-timedelta(days=300),expiry_date=today+timedelta(days=45),  quantity_received=15,  quantity_remaining=10,  unit_cost=Decimal('15000'),purchase_order=po4),
    dict(item=items['hivtest'], lot_number="LBC-2025-HIV1",manufactured_date=today-timedelta(days=330),expiry_date=today+timedelta(days=45),  quantity_received=10,  quantity_remaining=7,   unit_cost=Decimal('22000'),purchase_order=po4),

    # Sutures
    dict(item=items['vicryl'],  lot_number="PHA-2026-VIC", manufactured_date=today-timedelta(days=30),  expiry_date=today+timedelta(days=1095),quantity_received=36,  quantity_remaining=22,  unit_cost=Decimal('18000'),purchase_order=po8),
    dict(item=items['prolene'], lot_number="PHA-2026-PRO", manufactured_date=today-timedelta(days=30),  expiry_date=today+timedelta(days=1095),quantity_received=12,  quantity_remaining=11,  unit_cost=Decimal('24000'),purchase_order=po8),
    dict(item=items['prolene'], lot_number="OPX-2026-PRO2",manufactured_date=today-timedelta(days=20),  expiry_date=today+timedelta(days=1200),quantity_received=12,  quantity_remaining=6,   unit_cost=Decimal('24000'),purchase_order=po3),

    # IOLs (consignment)
    dict(item=items['iol_mono'],lot_number="OPX-2026-IOL1",manufactured_date=today-timedelta(days=60), expiry_date=today+timedelta(days=548), quantity_received=10,  quantity_remaining=8,   unit_cost=Decimal('45000'),purchase_order=po3),
    dict(item=items['iol_toric'],lot_number="OPX-2026-TOR1",manufactured_date=today-timedelta(days=60),expiry_date=today+timedelta(days=548), quantity_received=5,   quantity_remaining=5,   unit_cost=Decimal('95000'),purchase_order=po3),

    # Glaucoma implant
    dict(item=items['ahmed'],   lot_number="OPX-2026-AHM1",manufactured_date=today-timedelta(days=90), expiry_date=today+timedelta(days=730), quantity_received=3,   quantity_remaining=3,   unit_cost=Decimal('280000'),purchase_order=po3),

    # Catheter
    dict(item=items['catheter'],lot_number="AFM-2026-CAT",manufactured_date=today-timedelta(days=30),  expiry_date=today+timedelta(days=1095),quantity_received=80,  quantity_remaining=65,  unit_cost=Decimal('2800'), purchase_order=po2),

    # Ringer's
    dict(item=items['ringer'],  lot_number="PHA-2026-RL1", manufactured_date=today-timedelta(days=45),  expiry_date=today+timedelta(days=730), quantity_received=500, quantity_remaining=240, unit_cost=Decimal('1800'), purchase_order=po1),
]

for bd in batch_data:
    BatchStock.objects.create(**bd)

print(f"  Created {len(batch_data)} batch records")


# ── STOCK MOVEMENTS ──────────────────────────────────────────────────────────
print("Creating stock movement history...")

movements = [
    dict(item=items['amox'],     movement_type='IN',     quantity=200, balance_after=200, reference=f"PO-{po1.po_number}", notes="Received from MEDIPHARM — quarterly restocking"),
    dict(item=items['amox'],     movement_type='ISSUE',  quantity=-45, balance_after=155, reference="REQ-2026-0001", notes="Issued to General Ward"),
    dict(item=items['amox'],     movement_type='ISSUE',  quantity=-30, balance_after=125, reference="REQ-2026-0003", notes="Issued to Paediatrics"),
    dict(item=items['amox'],     movement_type='ISSUE',  quantity=-40, balance_after=85,  reference="REQ-2026-0005", notes="Issued to Eye Clinic"),
    dict(item=items['cipro'],    movement_type='IN',     quantity=100, balance_after=100, reference=f"PO-{po1.po_number}", notes="Received from MEDIPHARM"),
    dict(item=items['cipro'],    movement_type='ISSUE',  quantity=-58, balance_after=42,  reference="REQ-2026-0002", notes="Issued to ICU & General Ward"),
    dict(item=items['dexa'],     movement_type='IN',     quantity=80,  balance_after=80,  reference=f"PO-{po1.po_number}", notes="Received from MEDIPHARM"),
    dict(item=items['dexa'],     movement_type='ISSUE',  quantity=-74, balance_after=6,   reference="Multiple requisitions", notes="High usage — ophthalmology procedures + ICU"),
    dict(item=items['metro'],    movement_type='IN',     quantity=50,  balance_after=50,  reference=f"PO-{po1.po_number}", notes="Received"),
    dict(item=items['metro'],    movement_type='ISSUE',  quantity=-32, balance_after=18,  reference="REQ-2026-0004", notes="Issued to ICU"),
    dict(item=items['ringer'],   movement_type='IN',     quantity=500, balance_after=500, reference=f"PO-{po1.po_number}", notes="Bulk order received"),
    dict(item=items['ringer'],   movement_type='ISSUE',  quantity=-260,balance_after=240, reference="Various wards", notes="Daily IV fluid consumption"),
    dict(item=items['gloves_m'], movement_type='IN',     quantity=500, balance_after=500, reference=f"PO-{po2.po_number}", notes="Received from AfricaMed"),
    dict(item=items['gloves_m'], movement_type='ISSUE',  quantity=-180,balance_after=320, reference="Theatre", notes="Theatre daily use"),
    dict(item=items['gloves_m'], movement_type='ISSUE',  quantity=-100,balance_after=220, reference="General ward", notes="Ward use"),
    dict(item=items['gloves_m'], movement_type='ISSUE',  quantity=-80, balance_after=140, reference="Various", notes="Various depts"),
    dict(item=items['gloves_m'], movement_type='ADJUST', quantity=440, balance_after=580, reference="STOCK-ADJ-001", notes="Physical count reconciliation — variance +440"),
    dict(item=items['syringe5'], movement_type='IN',     quantity=800, balance_after=800, reference=f"PO-{po2.po_number}", notes="Received from AfricaMed"),
    dict(item=items['syringe5'], movement_type='ISSUE',  quantity=-600,balance_after=200, reference="All wards", notes="Daily clinical use"),
    dict(item=items['syringe5'], movement_type='ADJUST', quantity=1000,balance_after=1200,reference="STOCK-ADJ-002", notes="New stock integrated"),
    dict(item=items['glucstrip'],movement_type='IN',     quantity=30,  balance_after=30,  reference=f"PO-{po4.po_number}", notes="Received from LabCore"),
    dict(item=items['glucstrip'],movement_type='ISSUE',  quantity=-16, balance_after=14,  reference="Lab", notes="Diabetic screening use"),
    dict(item=items['iol_mono'], movement_type='IN',     quantity=10,  balance_after=10,  reference=f"PO-{po3.po_number}", notes="Consignment received from OPHTEX"),
    dict(item=items['iol_mono'], movement_type='ISSUE',  quantity=-2,  balance_after=8,   reference="SURG-OPH-2026-0047", notes="Implanted — Patient cataract surgery"),
    dict(item=items['ahmed'],    movement_type='IN',     quantity=3,   balance_after=3,   reference=f"PO-{po3.po_number}", notes="Consignment received from OPHTEX"),
    dict(item=items['n95'],      movement_type='IN',     quantity=10,  balance_after=10,  reference="Emergency purchase", notes="Emergency procurement — outbreak protocol"),
    dict(item=items['n95'],      movement_type='ISSUE',  quantity=-6,  balance_after=4,   reference="Infection control", notes="Issued to isolation ward"),
    dict(item=items['vicryl'],   movement_type='IN',     quantity=36,  balance_after=36,  reference=f"PO-{po8.po_number}", notes="Received from PharmaCentre"),
    dict(item=items['vicryl'],   movement_type='ISSUE',  quantity=-14, balance_after=22,  reference="Theatre", notes="General surgery use"),
    dict(item=items['malariardt'],movement_type='EXPIRE',quantity=-2,  balance_after=10,  reference="EXPIRE-2026-001", notes="2 kits expired — written off per JCI MMU.3"),
]

for md in movements:
    StockMovement.objects.create(performed_by=admin, **md)

print(f"  Created {len(movements)} stock movements")


# ── DEPARTMENT REQUISITIONS ──────────────────────────────────────────────────
print("Creating department requisitions...")

def make_req(department, priority, status, days_ago, items_list, notes='', needed_days=3):
    req = DepartmentRequisition(
        department=department, requested_by=admin, priority=priority,
        status=status, notes=notes,
        needed_by=today + timedelta(days=needed_days),
        approved_by=admin if status not in ('PENDING', 'REJECTED') else None,
        issued_by=admin if status in ('ISSUED', 'PARTIAL') else None,
        issued_at=timezone.now() - timedelta(days=days_ago-1) if status in ('ISSUED', 'PARTIAL') else None,
    )
    req.req_number = f"TEMP-{id(req)}"
    req.save()
    for item_key, qty_req, qty_issued in items_list:
        RequisitionItem.objects.create(
            requisition=req, item=items[item_key],
            quantity_requested=qty_req, quantity_issued=qty_issued,
        )
    return req

# Issued requisitions
r1 = make_req("General Ward",       "ROUTINE",   "ISSUED",  5, [("amox",45,""), ("syringe5",100,""), ("cannula20",50,""), ("ringer",60,"")],  notes="Weekly ward restocking")
r2 = make_req("ICU / Intensive Care","URGENT",   "ISSUED",  3, [("metro",20,""), ("dexa",15,""),    ("paraciv",40,""),  ("cannula18",30,"")], notes="ICU critical care supplies")
r3 = make_req("Eye Clinic / Theatre","ROUTINE",  "ISSUED",  7, [("atrop",10,""), ("fluor",15,""),   ("prolene",6,""),   ("amox",20,"")],      notes="Eye clinic weekly supplies")
r4 = make_req("Paediatrics Ward",    "ROUTINE",  "ISSUED",  4, [("amox",30,""), ("syringe5",80,""), ("paraciv",30,""), ("gloves_m",40,"")],   notes="Paediatrics weekly restocking")

# Fix qty_issued strings
for r in [r1, r2, r3, r4]:
    for ri in r.items.all():
        ri.quantity_issued = ri.quantity_requested
        ri.save()

# Approved — awaiting issue
r5 = make_req("Surgical Theatre",   "URGENT",   "APPROVED", 1, [("gloves_m",80,""), ("gloves_l",60,""), ("vicryl",6,""), ("syringe10",50,"")],notes="Pre-op theatre prep — urgent")
r5.items.all().update(quantity_issued=0)

# Partial issue
r6 = make_req("Laboratory",         "ROUTINE",  "PARTIAL",  2, [("glucstrip",5,""), ("hba1c",3,""),    ("malariardt",2,""), ("hivtest",2,"")],  notes="Lab reagent monthly top-up")
for ri in r6.items.all():
    ri.quantity_issued = ri.quantity_requested // 2
    ri.save()

# Pending (new requests)
r7 = make_req("Maternity Ward",     "ROUTINE",  "PENDING",  0, [("cannula20",30,""), ("syringe5",60,""), ("ringer",40,""), ("gloves_m",30,"")], notes="Maternity weekly supply request")
r8 = make_req("Ophthalmology Clinic","URGENT",  "PENDING",  0, [("atrop",15,""), ("dexa",20,""), ("fluor",10,"")],  notes="Eye clinic URGENT — pre-cataract week")
r9 = make_req("Emergency Dept.",    "EMERGENCY","PENDING",  0, [("dexa",10,""), ("metro",20,""), ("cannula18",20,""), ("catheter",5,"")], notes="EMERGENCY: resupply after trauma case surge")

# Set issued quantities to 0 for non-issued
for r in [r5, r7, r8, r9]:
    r.items.all().update(quantity_issued=0)

print(f"  Created 9 requisitions ({DepartmentRequisition.objects.count()} total)")


# ── FINAL SUMMARY ────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("INVENTORY SEED COMPLETE")
print("="*60)
print(f"  Vendors:       {Vendor.objects.count()}")
print(f"  Items:         {InventoryItem.objects.count()}")
print(f"  Purchase Orders:{PurchaseOrder.objects.count()}")
print(f"  Batch Records: {BatchStock.objects.count()}")
print(f"  Movements:     {StockMovement.objects.count()}")
print(f"  Requisitions:  {DepartmentRequisition.objects.count()}")
low_stock = InventoryItem.objects.filter(current_stock__lte=models.F('reorder_level')) if False else \
    [i for i in InventoryItem.objects.all() if i.current_stock <= i.reorder_level]
print(f"  Low Stock:     {len(low_stock)} items")
expiring = BatchStock.objects.filter(expiry_date__lte=today+timedelta(days=90), expiry_date__gt=today, quantity_remaining__gt=0)
print(f"  Expiring ≤90d: {expiring.count()} batches")
print("="*60)
print("Ready for finance director demo!")
