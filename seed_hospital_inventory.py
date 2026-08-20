"""
FULL HOSPITAL INVENTORY SEED — EHR Africa Demo
Covers every department: Pharmacy, Theatre, Lab, ICU, Wards, Eye Clinic,
Emergency, Radiology, Maintenance, Kitchen, Admin, Linen, IT.
Run: python seed_hospital_inventory.py  (server venv active)
"""
import os, sys, django, uuid
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
sys.path.insert(0, '/opt/ehr-africa')
django.setup()

from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from apps.inventory.models import (
    InventoryItem, Vendor, PurchaseOrder, PurchaseOrderItem,
    BatchStock, StockMovement, DepartmentRequisition, RequisitionItem,
)
from apps.accounts.models import User

today = date.today()
Y = today.year
admin = User.objects.filter(is_superuser=True).first()

print("=" * 70)
print("FULL HOSPITAL INVENTORY SEED")
print("=" * 70)

# ── WIPE EXISTING ────────────────────────────────────────────────────────────
print("\nClearing existing inventory data...")
with transaction.atomic():
    RequisitionItem.objects.all().delete()
    DepartmentRequisition.objects.all().delete()
    StockMovement.objects.all().delete()
    BatchStock.objects.all().delete()
    PurchaseOrderItem.objects.all().delete()
    PurchaseOrder.objects.all().delete()
    InventoryItem.objects.all().delete()
    Vendor.objects.all().delete()
print("  Done.")

# ════════════════════════════════════════════════════════════════════════════
# VENDORS
# ════════════════════════════════════════════════════════════════════════════
print("\nCreating vendors...")

def V(name, contact, phone, email, address, total, on_time, late, incidents, notes):
    return Vendor.objects.create(
        name=name, contact_person=contact, phone=phone, email=email,
        address=address, total_orders=total, on_time_deliveries=on_time,
        late_deliveries=late, quality_incidents=incidents, notes=notes
    )

vendors = {}
vendors['medipharm']    = V("MEDIPHARM Cameroon SARL",        "Jean-Baptiste Fouda",    "+237 677 112 233", "orders@medipharm-cm.com",      "Rue 1.082, Akwa, Douala",              56, 55, 1, 0,  "Primary pharma & IV fluids. ISO-certified cold chain. Excellent track record.")
vendors['africamed']    = V("AfricaMed Supplies Ltd",          "Nkemdirim Chukwu",       "+237 699 445 566", "supply@africamed.com",          "Zone Industrielle, Bassa, Douala",      44, 41, 3, 1,  "Surgical consumables, PPE, disposables. Good pricing on bulk orders.")
vendors['ophtex']       = V("OPHTEX Vision Supplies",          "Sophie Abena",            "+237 655 778 899", "sales@ophtex.cm",               "Quartier Bastos, Yaoundé",             22, 21, 1, 0,  "Specialist ophthalmic lenses, implants, viscoelastics. Consignment available.")
vendors['labcore']      = V("LabCore Diagnostics SA",          "Dr. Paul Ngah",           "+237 688 334 455", "orders@labcore.cm",             "Rue de la Science, Yaoundé",           28, 23, 5, 2,  "Lab reagents and point-of-care test kits. Cold-chain incidents in 2025 — monitor.")
vendors['cleanpro']     = V("CleanPro Hospital Services",      "Mireille Tagne",          "+237 677 990 011", "info@cleanpro.cm",              "BP 1452, Bafoussam",                   22, 22, 0, 0,  "Cleaning, housekeeping, laundry supplies. 100% on-time. Preferred for consumables.")
vendors['techmed']      = V("TechMed Equipment Cameroon",      "Ibrahim Moussa",          "+237 699 123 456", "techmed@equip.cm",              "Avenue de Gaulle, Douala",             12, 8,  4, 1,  "Medical equipment and spare parts. Delivery inconsistent — escalate if delayed.")
vendors['pharmacentre'] = V("PharmaCentre Yaoundé",            "Dr. Chantal Biya",        "+237 655 221 133", "orders@pharmacentre.cm",        "Quartier Nlongkak, Yaoundé",           18, 17, 1, 0,  "Secondary pharma supplier. Good for urgent/emergency restocking.")
vendors['camidia']      = V("CAMIDIA Medical Imaging",         "Roger Atangana",          "+237 677 654 321", "camidia@imaging.cm",            "Rue Nachtigal, Yaoundé",               8,  7,  1, 0,  "Radiology films, contrast agents, X-ray consumables.")
vendors['nutricam']     = V("NutriCam Food Services",          "Evelyne Simo",            "+237 699 876 543", "orders@nutricam.cm",            "Marché Central, Bafoussam",            30, 30, 0, 0,  "Hospital kitchen: fresh produce, dry goods, cooking gas. 100% on-time.")
vendors['officepro']    = V("OfficePro Cameroon",              "Marc Essomba",            "+237 677 321 654", "info@officepro.cm",             "Carrefour Warda, Douala",              20, 19, 1, 0,  "Office supplies, printing, stationery, admin consumables.")
vendors['medigas']      = V("MediGas Cameroon SARL",           "Hassan Bello",            "+237 699 555 777", "medigas@gas.cm",                "Zone Industrielle, Douala",             10, 9,  1, 0,  "Medical oxygen, nitrogen, nitrous oxide cylinder supply and refill.")
vendors['camtextile']   = V("CamTextile Linen Solutions",      "Prudence Nkeng",          "+237 655 432 109", "linen@camtextile.cm",           "Rue de la Réunification, Douala",      14, 14, 0, 0,  "Hospital linen: bed sheets, gowns, theatre drapes. Perfect record.")

print(f"  Created {len(vendors)} vendors")

# ════════════════════════════════════════════════════════════════════════════
# ITEMS — grouped by department
# ════════════════════════════════════════════════════════════════════════════
print("\nCreating inventory items...")

items = {}

def I(key, name, code, cat, unit, cost, reorder, stock, loc, expiry=False, consign=False, udi='', storage='', vendor_key=None, desc=''):
    items[key] = InventoryItem.objects.create(
        name=name, item_code=code, category=cat, unit=unit,
        unit_cost=Decimal(str(cost)), reorder_level=reorder, current_stock=stock,
        location=loc, requires_expiry_tracking=expiry, is_consignment=consign,
        udi_code=udi, storage_conditions=storage or 'Room temperature 15–25 °C',
        preferred_vendor=vendors.get(vendor_key),
        description=desc,
    )

# ── PHARMACY / DRUGS ─────────────────────────────────────────────────────────
I('amox500',    "Amoxicillin 500mg Capsules",          "PHM-001", 'PHARMACEUTICAL', "box/100",   4500,  20, 110, "Pharmacy Main Store, Shelf A1",  expiry=True, vendor_key='medipharm',    desc="Broad-spectrum penicillin antibiotic. First-line for RTI, UTI.")
I('cipro500',   "Ciprofloxacin 500mg Tablets",         "PHM-002", 'PHARMACEUTICAL', "box/50",    6800,  15,  55, "Pharmacy Main Store, Shelf A1",  expiry=True, vendor_key='medipharm',    desc="Fluoroquinolone. Second-line for complicated UTI, typhoid.")
I('metro500iv', "Metronidazole 500mg IV Infusion",     "PHM-003", 'PHARMACEUTICAL', "bag",       2200,  30,  22, "Pharmacy ICU Shelf",             expiry=True, vendor_key='medipharm',    desc="Anaerobic antibiotic. Post-op and ICU standard.", storage="Room temp, protect from light")
I('paraciv',    "Paracetamol 1g IV Infusion",          "PHM-004", 'PHARMACEUTICAL', "bag",       2100,  50, 145, "Pharmacy Main Store, Shelf B2",  expiry=True, vendor_key='pharmacentre', desc="IV analgesia for post-operative pain.")
I('dexa4mg',    "Dexamethasone 4mg/2ml Injection",     "PHM-005", 'PHARMACEUTICAL', "ampoule",    850,  40,   8, "Pharmacy Main Store, Shelf A3",  expiry=True, vendor_key='medipharm',    desc="Corticosteroid. Ophthalmology + ICU + allergy.", storage="Room temp, protect from light")
I('ceftriax',   "Ceftriaxone 1g IV Powder",            "PHM-006", 'PHARMACEUTICAL', "vial",      3500,  40,  68, "Pharmacy ICU Shelf",             expiry=True, vendor_key='medipharm',    desc="3rd gen cephalosporin. ICU, meningitis, post-op sepsis.")
I('vancomycin', "Vancomycin 500mg IV",                 "PHM-007", 'PHARMACEUTICAL', "vial",      8500,  10,  18, "Pharmacy ICU Shelf",             expiry=True, vendor_key='pharmacentre', desc="Glycopeptide for MRSA and resistant gram+ve infections.")
I('amoxi_susp', "Amoxicillin 250mg/5ml Suspension",   "PHM-008", 'PHARMACEUTICAL', "bottle",    2800,  15,  32, "Pharmacy Paeds Shelf",           expiry=True, vendor_key='medipharm',    desc="Paediatric antibiotic suspension.")
I('paracetamol_tab', "Paracetamol 500mg Tablets",     "PHM-009", 'PHARMACEUTICAL', "box/1000",  1800,  10, 28,  "Pharmacy Main Store, Shelf B1",  expiry=True, vendor_key='medipharm',    desc="OTC analgesia/antipyretic. High-volume general ward use.")
I('ibuprofen',  "Ibuprofen 400mg Tablets",             "PHM-010", 'PHARMACEUTICAL', "box/500",   2200,   8,  19, "Pharmacy Main Store, Shelf B1",  expiry=True, vendor_key='medipharm',    desc="NSAID for pain and inflammation.")
I('amlodipine', "Amlodipine 5mg Tablets",              "PHM-011", 'PHARMACEUTICAL', "box/30",    3200,  10,  42, "Pharmacy Chronic Shelf",         expiry=True, vendor_key='medipharm',    desc="Calcium channel blocker. Hypertension management.")
I('lisinopril', "Lisinopril 10mg Tablets",             "PHM-012", 'PHARMACEUTICAL', "box/30",    3800,  10,  35, "Pharmacy Chronic Shelf",         expiry=True, vendor_key='medipharm',    desc="ACE inhibitor. Hypertension and heart failure.")
I('metformin',  "Metformin 500mg Tablets",             "PHM-013", 'PHARMACEUTICAL', "box/60",    2600,  10,  48, "Pharmacy Chronic Shelf",         expiry=True, vendor_key='medipharm',    desc="Biguanide for type 2 diabetes management.")
I('ringer',     "Ringer's Lactate 500ml IV",           "PHM-014", 'PHARMACEUTICAL', "bag",       1800, 100, 310, "Pharmacy IV Fluid Store",        expiry=True, vendor_key='pharmacentre', desc="IV crystalloid for rehydration and surgical use.")
I('ns09',       "Normal Saline 0.9% 500ml IV",         "PHM-015", 'PHARMACEUTICAL', "bag",       1600, 100, 285, "Pharmacy IV Fluid Store",        expiry=True, vendor_key='pharmacentre', desc="Isotonic saline IV fluid.")
I('dextrose5',  "Dextrose 5% 500ml IV",                "PHM-016", 'PHARMACEUTICAL', "bag",       1700,  60, 190, "Pharmacy IV Fluid Store",        expiry=True, vendor_key='pharmacentre', desc="Glucose IV fluid for hypoglycaemia and hydration.")
I('morphine',   "Morphine Sulphate 10mg/ml Injection", "PHM-017", 'PHARMACEUTICAL', "ampoule",   4500,  20,  35, "Pharmacy Controlled Drug Cabinet",expiry=True,vendor_key='pharmacentre', desc="Opioid analgesic. CONTROLLED DRUG — double-lock required.", storage="Secure controlled drug cabinet")
I('midazolam',  "Midazolam 5mg/ml Injection",          "PHM-018", 'PHARMACEUTICAL', "ampoule",   6200,  15,  22, "Pharmacy Controlled Drug Cabinet",expiry=True,vendor_key='pharmacentre', desc="Benzodiazepine sedation. CONTROLLED DRUG.", storage="Secure controlled drug cabinet")
I('ketamine',   "Ketamine 200mg/10ml Injection",       "PHM-019", 'PHARMACEUTICAL', "vial",      7500,  10,  16, "Pharmacy Controlled Drug Cabinet",expiry=True,vendor_key='pharmacentre', desc="Dissociative anaesthetic. CONTROLLED DRUG.", storage="Secure controlled drug cabinet")
I('heparin',    "Heparin Sodium 5000 IU/ml",           "PHM-020", 'PHARMACEUTICAL', "vial",      5800,  10,  14, "Pharmacy ICU Shelf",             expiry=True, vendor_key='medipharm',    desc="Anticoagulant for DVT, PE, post-op prophylaxis.")
I('insulin_r',  "Insulin Regular (Actrapid) 100IU/ml", "PHM-021", 'PHARMACEUTICAL', "vial",     12000,  10,  18, "Pharmacy Fridge",                expiry=True, vendor_key='medipharm',    desc="Short-acting insulin for DKA, peri-op glycaemic control.", storage="Refrigerate 2–8 °C")
I('ors',        "Oral Rehydration Salts (ORS) Sachets","PHM-022", 'PHARMACEUTICAL', "box/100",   3500,  10,  24, "Pharmacy Main Store",            expiry=True, vendor_key='medipharm',    desc="WHO-standard ORS for diarrhoea management.")
I('artesunate', "Artesunate 60mg IV",                  "PHM-023", 'PHARMACEUTICAL', "vial",      5500,  20,  28, "Pharmacy Malaria Shelf",         expiry=True, vendor_key='medipharm',    desc="Severe malaria treatment (WHO first-line).")
I('coartem',    "Artemether/Lumefantrine 20/120mg",    "PHM-024", 'PHARMACEUTICAL', "pack/24",   4800,  15,  36, "Pharmacy Malaria Shelf",         expiry=True, vendor_key='medipharm',    desc="ACT for uncomplicated malaria. NACP-approved.")
I('cotrimox',   "Cotrimoxazole 960mg Tablets",         "PHM-025", 'PHARMACEUTICAL', "box/100",   1900,  10,  30, "Pharmacy Chronic Shelf",         expiry=True, vendor_key='medipharm',    desc="PCP prophylaxis for HIV patients. ART clinic essential.")
I('folic_acid', "Folic Acid 5mg Tablets",              "PHM-026", 'PHARMACEUTICAL', "box/100",    800,  10,  40, "Pharmacy Maternity Shelf",       expiry=True, vendor_key='medipharm',    desc="Antenatal supplement. Essential for maternity ward.")
I('iron_folate',"Ferrous Sulphate + Folic Acid",       "PHM-027", 'PHARMACEUTICAL', "box/100",   1200,  10,  35, "Pharmacy Maternity Shelf",       expiry=True, vendor_key='medipharm',    desc="Iron supplement for anaemia in pregnancy.")
I('oxytocin',   "Oxytocin 10 IU/ml Injection",        "PHM-028", 'PHARMACEUTICAL', "ampoule",   2800,  20,  30, "Pharmacy Maternity Fridge",      expiry=True, vendor_key='pharmacentre', desc="Uterotonic for labour induction and PPH prevention.", storage="Refrigerate 2–8 °C")
I('magnesulph', "Magnesium Sulphate 50% 2ml",          "PHM-029", 'PHARMACEUTICAL', "ampoule",   1500,  20,  45, "Pharmacy Maternity Shelf",       expiry=True, vendor_key='medipharm',    desc="Eclampsia treatment and prevention.")
I('salbutamol_neb',"Salbutamol 2.5mg Nebuliser",      "PHM-030", 'PHARMACEUTICAL', "ampoule",   1800,  20,  38, "Pharmacy Paeds/Resp Shelf",      expiry=True, vendor_key='medipharm',    desc="Bronchodilator for asthma/wheeze attacks.")

# ── EYE CLINIC DRUGS ─────────────────────────────────────────────────────────
I('atropine',   "Atropine 1% Eye Drops",               "PHM-031", 'PHARMACEUTICAL', "bottle/5ml",3200,  10,  25, "Pharmacy Eye Clinic Fridge",     expiry=True, vendor_key='ophtex',       desc="Mydriatic for refraction/uveitis.", storage="Refrigerate 2–8 °C")
I('fluorescein',"Fluorescein Sodium 2% Strips",        "PHM-032", 'PHARMACEUTICAL', "strip/12",  4100,   8,  20, "Pharmacy Eye Clinic",            expiry=True, vendor_key='ophtex',       desc="Corneal staining for tonometry and foreign bodies.")
I('timolol',    "Timolol 0.5% Eye Drops",              "PHM-033", 'PHARMACEUTICAL', "bottle/5ml",4800,   8,  18, "Pharmacy Eye Clinic",            expiry=True, vendor_key='ophtex',       desc="Beta-blocker for glaucoma IOP reduction.")
I('brinzolamide',"Brinzolamide 1% Eye Drops",          "PHM-034", 'PHARMACEUTICAL', "bottle/5ml",9500,   6,  12, "Pharmacy Eye Clinic",            expiry=True, vendor_key='ophtex',       desc="CAI for glaucoma — adjunct to timolol.")
I('lubricant',  "Artificial Tears Lubricating Drops",  "PHM-035", 'PHARMACEUTICAL', "bottle/10ml",2800, 10,  30, "Pharmacy Eye Clinic",            expiry=True, vendor_key='ophtex',       desc="Dry eye treatment. High volume use.")
I('predforte',  "Prednisolone 1% Eye Drops",           "PHM-036", 'PHARMACEUTICAL', "bottle/5ml",7200,   8,  14, "Pharmacy Eye Clinic Fridge",     expiry=True, vendor_key='ophtex',       desc="Post-op anti-inflammatory after cataract/glaucoma surgery.", storage="Refrigerate 2–8 °C")

# ── LAB REAGENTS ─────────────────────────────────────────────────────────────
I('glucstrip',  "Blood Glucose Strips (ACCU-CHEK)",    "LAB-001", 'PHARMACEUTICAL', "box/50",   12000,  10,  22, "Lab Reagent Fridge",             expiry=True, vendor_key='labcore',      desc="POCT glucose. ISO 15189 approved.", storage="Refrigerate 2–8 °C")
I('hba1c',      "HbA1c Test Cartridges",               "LAB-002", 'PHARMACEUTICAL', "cartridge", 8500,   8,  10, "Lab Reagent Fridge",             expiry=True, vendor_key='labcore',      desc="Diabetes monitoring. POC HbA1c.", storage="Refrigerate 2–8 °C")
I('malaria_rdt',"Malaria RDT Kit (WHO pre-qualified)", "LAB-003", 'PHARMACEUTICAL', "kit/25",   15000,   5,  14, "Lab Store, Shelf 1",             expiry=True, vendor_key='labcore',      desc="Rapid antigen detection — Plasmodium falciparum/pan.")
I('hiv_test',   "HIV Rapid Test (Determine HIV-1/2)",  "LAB-004", 'PHARMACEUTICAL', "kit/20",   22000,   4,  11, "Lab Store, Shelf 1",             expiry=True, vendor_key='labcore',      desc="WHO pre-qualified 1st line HIV test. NACP protocol.")
I('hbsag',      "HBsAg Rapid Test Strip",              "LAB-005", 'PHARMACEUTICAL', "kit/25",   14000,   4,   9, "Lab Store, Shelf 1",             expiry=True, vendor_key='labcore',      desc="Hepatitis B surface antigen rapid test.")
I('preg_test',  "Urine Pregnancy Test (hCG)",          "LAB-006", 'PHARMACEUTICAL', "kit/50",    6500,   5,  18, "Lab Store, Shelf 2",             expiry=True, vendor_key='labcore',      desc="Quantitative hCG strip for pregnancy confirmation.")
I('urine_strips',"Urine Dipstick 10-parameter",        "LAB-007", 'PHARMACEUTICAL', "bottle/100",8000,   5,  12, "Lab Store, Shelf 2",             expiry=True, vendor_key='labcore',      desc="Urinalysis 10-parameter dipstick.")
I('blood_bags', "Blood Collection Bags (CPDA-1 450ml)","LAB-008", 'PHARMACEUTICAL', "bag",       3500,  20,  55, "Lab Blood Bank Fridge",          expiry=True, vendor_key='labcore',      desc="Sterile blood collection bags with anticoagulant.", storage="Refrigerate 2–8 °C")
I('stain_gram', "Gram Stain Kit (4-bottle)",           "LAB-009", 'PHARMACEUTICAL', "kit",       9800,   4,   8, "Lab Microbiology Store",         expiry=True, vendor_key='labcore',      desc="Gram staining reagents for microbiology.", storage="Room temp, protect from light")
I('agar_blood', "Blood Agar Plates (ready-poured)",    "LAB-010", 'PHARMACEUTICAL', "pack/20",  18000,   4,   6, "Lab Microbiology Fridge",        expiry=True, vendor_key='labcore',      desc="Culture media for aerobic organisms.", storage="Refrigerate 2–8 °C")

# ── SURGICAL CONSUMABLES / THEATRE ───────────────────────────────────────────
I('glove_m',    "Surgical Gloves Sterile — Medium",    "SUR-001", 'SURGICAL',       "pair",       450, 200, 620, "Theatre Store, Shelf A1",        vendor_key='africamed',    desc="Latex sterile surgical gloves — size M.")
I('glove_l',    "Surgical Gloves Sterile — Large",     "SUR-002", 'SURGICAL',       "pair",       450, 150, 380, "Theatre Store, Shelf A1",        vendor_key='africamed',    desc="Latex sterile surgical gloves — size L.")
I('glove_s',    "Surgical Gloves Sterile — Small",     "SUR-003", 'SURGICAL',       "pair",       450,  80, 240, "Theatre Store, Shelf A1",        vendor_key='africamed',    desc="Latex sterile surgical gloves — size S.")
I('exam_glove', "Examination Gloves (non-sterile box)","SUR-004", 'MEDICAL_CONSUMABLE',"box/100",  2500, 50, 180, "Nursing Store, Shelf 1",         vendor_key='africamed',    desc="Non-sterile nitrile examination gloves — one size.")
I('vicryl20',   "Suture Vicryl 2-0 (absorbable)",     "SUR-005", 'SURGICAL',       "box/12",   18000,   5,  24, "Theatre Store, Shelf B1",        expiry=True, vendor_key='africamed',    desc="Polyglactin 910 absorbable suture — general closure.")
I('vicryl30',   "Suture Vicryl 3-0 (absorbable)",     "SUR-006", 'SURGICAL',       "box/12",   18000,   5,  18, "Theatre Store, Shelf B1",        expiry=True, vendor_key='africamed',    desc="Polyglactin 910 absorbable — subcutaneous closure.")
I('prolene60',  "Suture Prolene 6-0 (ophthalmic)",    "SUR-007", 'SURGICAL',       "box/12",   24000,   4,  15, "Theatre Eye Store",              expiry=True, vendor_key='ophtex',       desc="Non-absorbable monofilament — eye surgery.")
I('prolene100', "Suture Prolene 10-0 (microsurgical)", "SUR-008", 'SURGICAL',       "box/6",    38000,   3,   8, "Theatre Eye Store",              expiry=True, vendor_key='ophtex',       desc="Microsurgical suture for corneal and iris procedures.")
I('cannula20',  "IV Cannula 20G",                     "SUR-009", 'MEDICAL_CONSUMABLE',"piece",    350, 100, 550, "Nursing Store, Shelf 2",         vendor_key='africamed',    desc="IV access — standard adult.")
I('cannula18',  "IV Cannula 18G",                     "SUR-010", 'MEDICAL_CONSUMABLE',"piece",    350,  80, 380, "Nursing Store, Shelf 2",         vendor_key='africamed',    desc="IV access — large bore trauma/ICU.")
I('cannula24',  "IV Cannula 24G (paediatric)",        "SUR-011", 'MEDICAL_CONSUMABLE',"piece",    380,  50, 220, "Nursing Store, Shelf 2",         vendor_key='africamed',    desc="Paediatric IV access.")
I('syringe1',   "Disposable Syringe 1ml (TB/insulin)","SUR-012", 'MEDICAL_CONSUMABLE',"piece",    120, 200,1050, "Nursing Store, Shelf 1",         vendor_key='africamed',    desc="Insulin and tuberculin syringe.")
I('syringe5',   "Disposable Syringe 5ml",             "SUR-013", 'MEDICAL_CONSUMABLE',"piece",    120, 300,1400, "Nursing Store, Shelf 1",         vendor_key='africamed',    desc="General purpose injection syringe.")
I('syringe10',  "Disposable Syringe 10ml",            "SUR-014", 'MEDICAL_CONSUMABLE',"piece",    150, 200, 850, "Nursing Store, Shelf 1",         vendor_key='africamed',    desc="IV drug delivery.")
I('syringe20',  "Disposable Syringe 20ml",            "SUR-015", 'MEDICAL_CONSUMABLE',"piece",    200, 100, 420, "Nursing Store, Shelf 1",         vendor_key='africamed',    desc="Wound irrigation, nasogastric feeding.")
I('needle21',   "Needle 21G (green)",                 "SUR-016", 'MEDICAL_CONSUMABLE',"piece",     80, 300,1800, "Nursing Store, Shelf 3",         vendor_key='africamed',    desc="Standard injection needle.")
I('catheter16', "Foley Catheter Silicone 16Fr",       "SUR-017", 'MEDICAL_CONSUMABLE',"piece",   2800,  20,  68, "Theatre Store, Shelf C",         expiry=True, vendor_key='africamed',    desc="Two-way urinary catheter — standard male/female.")
I('catheter12', "Foley Catheter Silicone 12Fr (paeds)","SUR-018",'MEDICAL_CONSUMABLE',"piece",   2800,  10,  30, "Theatre Store, Shelf C",         expiry=True, vendor_key='africamed',    desc="Paediatric urinary catheter.")
I('ng_tube',    "Nasogastric Tube (CH16)",            "SUR-019", 'MEDICAL_CONSUMABLE',"piece",   1800,  15,  40, "Nursing Store, Shelf 4",         vendor_key='africamed',    desc="NG tube for feeding and decompression.")
I('iv_set',     "IV Infusion Set (drip set)",         "SUR-020", 'MEDICAL_CONSUMABLE',"piece",    650, 200, 750, "Nursing Store, Shelf 2",         vendor_key='africamed',    desc="Gravity IV administration set with 15µm filter.")
I('burette_set',"Burette Infusion Set (paediatric)",  "SUR-021", 'MEDICAL_CONSUMABLE',"piece",    950,  50, 180, "Nursing Store, Shelf 2",         vendor_key='africamed',    desc="Paediatric measured volume IV set.")
I('wound_drain',"Wound Drain — Jackson-Pratt (10mm)", "SUR-022", 'MEDICAL_CONSUMABLE',"piece",   5500,  10,  22, "Theatre Store, Shelf D",         expiry=True, vendor_key='africamed',    desc="Closed suction wound drain.")
I('scalpel10',  "Scalpel Blade Size 10 (x100)",       "SUR-023", 'SURGICAL',       "box",      14000,   5,  12, "Theatre Store, Shelf B2",        vendor_key='africamed',    desc="Carbon steel surgical blades — general surgery.")
I('scalpel15',  "Scalpel Blade Size 15 (x100)",       "SUR-024", 'SURGICAL',       "box",      14000,   4,   9, "Theatre Eye Store",              vendor_key='africamed',    desc="Fine blade for ophthalmic and plastic surgery.")
I('bone_wax',   "Bone Wax (2.5g)",                   "SUR-025", 'SURGICAL',       "piece",    18000,   5,  10, "Theatre Store, Shelf B3",        vendor_key='africamed',    desc="Haemostatic wax for bone bleeding.")
I('haemostat',  "Oxidised Cellulose (Surgicel 5x10cm)","SUR-026",'SURGICAL',      "piece",    42000,   5,   8, "Theatre Store, Shelf B3",        expiry=True, vendor_key='africamed',    desc="Absorbable haemostat for surgical bleeding control.")

# ── OPHTHALMIC LENSES / IMPLANTS ─────────────────────────────────────────────
I('iol_mono',   "IOL Monofocal Hydrophilic (MICS)",   "LENS-001",'LENS',           "lens",     45000,   2,   7, "Theatre Eye Cabinet — Locked",   expiry=True, consign=True, vendor_key='ophtex', udi="(01)07612345678906(17)280831", desc="Monofocal IOL. Consignment — charged at implant.")
I('iol_toric',  "IOL Toric Premium (Astigmatism)",    "LENS-002",'LENS',           "lens",     95000,   2,   4, "Theatre Eye Cabinet — Locked",   expiry=True, consign=True, vendor_key='ophtex', udi="(01)07612345678913(17)281130", desc="Toric IOL for astigmatism correction. Consignment.")
I('ahmed_valve',"Ahmed Glaucoma Valve FP7",           "IMP-001", 'IMPLANT',        "implant", 280000,   1,   3, "Theatre Eye Cabinet — Locked",   expiry=True, vendor_key='ophtex', udi="(01)00843209000045(17)290630", desc="Glaucoma drainage implant. Sterile single-use.")
I('viscoelastic',"Viscoelastic (Healon 0.4ml)",       "LENS-003",'LENS',           "syringe",  28000,   5,  10, "Theatre Eye Cabinet — Locked",   expiry=True, vendor_key='ophtex',       desc="OVD for cataract surgery. Consignment stock.", consign=True)

# ── RADIOLOGY / IMAGING ───────────────────────────────────────────────────────
I('xray_film',  "X-Ray Film 35x43cm (box/100)",       "RAD-001", 'DIAGNOSTIC',     "box",      85000,   3,   8, "Radiology Store, Shelf A",       vendor_key='camidia',      desc="CR X-ray film for digital cassette system.")
I('contrast',   "Iohexol Contrast Agent 350mg/ml",    "RAD-002", 'PHARMACEUTICAL', "bottle",   24000,  10,  22, "Radiology Drug Store",           expiry=True, vendor_key='camidia',      desc="Non-ionic iodinated contrast for CT/fluoroscopy.")
I('gel_ultrasound',"Ultrasound Transmission Gel 5L",  "RAD-003", 'MEDICAL_CONSUMABLE',"can",    8500,   5,  12, "Radiology Store, Shelf B",       vendor_key='camidia',      desc="Water-soluble gel for USS transducer coupling.")
I('lead_apron', "Lead Apron (0.5mm Pb equivalent)",   "RAD-004", 'DIAGNOSTIC',     "piece",  280000,   2,   6, "Radiology Equipment Store",      vendor_key='camidia',      desc="Radiation protection apron. Annual inspection required.", storage="Hang flat, no folding")

# ── ANAESTHESIA / ICU ─────────────────────────────────────────────────────────
I('o2_cylinder',"Medical Oxygen Cylinder (F-type)",   "GAS-001", 'DIAGNOSTIC',     "cylinder",18000,  10,  28, "Gas Store — Locked",             vendor_key='medigas',      desc="Medical grade O2. Refill by MediGas on-site.", storage="Upright, chained to wall")
I('nitrous',    "Nitrous Oxide Cylinder (E-type)",     "GAS-002", 'DIAGNOSTIC',     "cylinder",14000,   4,   8, "Gas Store — Locked",             vendor_key='medigas',      desc="Anaesthetic gas. Theatre use only.", storage="Upright, chained to wall")
I('sevoflurane',"Sevoflurane Inhalation Agent 250ml", "PHM-038", 'PHARMACEUTICAL', "bottle",  185000,  2,   4, "Pharmacy Controlled Drug Cabinet",expiry=True, vendor_key='pharmacentre', desc="Volatile anaesthetic for inhalation induction. CONTROLLED.", storage="Secure controlled drug cabinet")
I('etomidate',  "Etomidate 2mg/ml Injection",         "PHM-039", 'PHARMACEUTICAL', "ampoule",  9500,  10,  18, "Pharmacy ICU Shelf",             expiry=True, vendor_key='pharmacentre', desc="IV induction agent for haemodynamically unstable patients.")
I('atracurium', "Atracurium 25mg/2.5ml Injection",    "PHM-040", 'PHARMACEUTICAL', "ampoule",  7200,  10,  24, "Pharmacy ICU Shelf",             expiry=True, vendor_key='pharmacentre', desc="Non-depolarising muscle relaxant for intubation.", storage="Refrigerate 2–8 °C")
I('neostigmine',"Neostigmine 2.5mg/ml Injection",     "PHM-041", 'PHARMACEUTICAL', "ampoule",  4500,  10,  16, "Pharmacy ICU Shelf",             expiry=True, vendor_key='pharmacentre', desc="Reversal agent for non-depolarising NMBs.")
I('et_tube70',  "Endotracheal Tube Cuffed 7.0mm",     "SUR-027", 'MEDICAL_CONSUMABLE',"piece",  1800,  20,  65, "Theatre Anaes Store",            expiry=True, vendor_key='africamed',    desc="PVC cuffed ET tube for anaesthesia/ICU ventilation.")
I('et_tube65',  "Endotracheal Tube Cuffed 6.5mm",     "SUR-028", 'MEDICAL_CONSUMABLE',"piece",  1800,  20,  50, "Theatre Anaes Store",            expiry=True, vendor_key='africamed',    desc="Smaller adult cuffed ET tube.")
I('lma_3',      "LMA Classic Size 3",                 "SUR-029", 'MEDICAL_CONSUMABLE',"piece",  22000,   5,  12, "Theatre Anaes Store",            vendor_key='africamed',    desc="Laryngeal mask airway — standard adult female.")
I('lma_4',      "LMA Classic Size 4",                 "SUR-030", 'MEDICAL_CONSUMABLE',"piece",  22000,   5,  12, "Theatre Anaes Store",            vendor_key='africamed',    desc="Laryngeal mask airway — standard adult male.")
I('sp_needle',  "Spinal Needle 25G (Quincke)",        "SUR-031", 'MEDICAL_CONSUMABLE',"piece",  2200,  20,  55, "Theatre Anaes Store",            expiry=True, vendor_key='africamed',    desc="Pencil-point spinal needle for regional anaesthesia.")
I('epi_kit',    "Epidural Kit (18G Tuohy + catheter)","SUR-032", 'MEDICAL_CONSUMABLE',"kit",   18000,   5,  14, "Theatre Anaes Store",            expiry=True, vendor_key='africamed',    desc="Complete epidural kit for obstetric and chronic pain.")
I('bupivacaine',"Bupivacaine 0.5% Heavy 4ml",         "PHM-042", 'PHARMACEUTICAL', "ampoule",  2800,  20,  42, "Pharmacy Theatre Shelf",         expiry=True, vendor_key='pharmacentre', desc="Spinal anaesthetic agent for subarachnoid block.")

# ── INFECTION CONTROL / PPE ───────────────────────────────────────────────────
I('n95_mask',   "N95 Respirator Masks (box/20)",       "PPE-001", 'MEDICAL_CONSUMABLE',"box",    9500,  10,   5, "Nursing Store, Shelf 3",         vendor_key='africamed',    desc="NIOSH-approved FFP2 respirator — isolation and AGMP.")
I('surgical_mask',"Surgical Face Masks (box/50)",      "PPE-002", 'MEDICAL_CONSUMABLE',"box",    3500,  20,  68, "Nursing Store, Shelf 3",         vendor_key='africamed',    desc="3-ply surgical mask — standard ward use.")
I('apron',      "Disposable Aprons (box/100)",         "PPE-003", 'MEDICAL_CONSUMABLE',"box",    4500,  10,  32, "Nursing Store, Shelf 3",         vendor_key='africamed',    desc="Non-sterile PE apron for body fluid protection.")
I('face_shield',"Face Shield (box/25)",                "PPE-004", 'MEDICAL_CONSUMABLE',"box",   12000,   5,  14, "Nursing Store, Shelf 3",         vendor_key='africamed',    desc="Full-face splash protection for high-risk procedures.")
I('sharps_bin', "Sharps Disposal Container 5L",        "PPE-005", 'MEDICAL_CONSUMABLE',"piece",   800,  50, 180, "Nursing Store, Shelf 4",         vendor_key='africamed',    desc="WHO-approved yellow sharps container.")
I('waste_red',  "Clinical Waste Bags — Red (50L, x50)","PPE-006",'MEDICAL_CONSUMABLE',"pack",   3800,  10,  28, "Housekeeping Store",             vendor_key='cleanpro',     desc="Red biohazard bags for infectious clinical waste.")
I('waste_yellow',"Clinical Waste Bags — Yellow (50L)", "PPE-007",'MEDICAL_CONSUMABLE',"pack",   3800,  10,  22, "Housekeeping Store",             vendor_key='cleanpro',     desc="Yellow cytotoxic waste bags.")

# ── CLEANING / HOUSEKEEPING ───────────────────────────────────────────────────
I('chlorhex',   "Chlorhexidine 4% Surgical Scrub 500ml","CLN-001",'CLEANING',      "bottle",   2800,  15,  48, "Theatre Scrub Area",             vendor_key='cleanpro',     desc="Antiseptic hand and surgical site scrub.")
I('alcohol70',  "Isopropyl Alcohol 70% 1L",            "CLN-002", 'CLEANING',       "bottle",   3200,  20,  65, "Housekeeping Store",             vendor_key='cleanpro',     desc="Surface and skin disinfectant.")
I('bleach10',   "Bleach 10% Solution 5L",              "CLN-003", 'CLEANING',       "jerry can", 4500, 10,  24, "Housekeeping Store",             vendor_key='cleanpro',     desc="High-level disinfectant for spills and surfaces.")
I('hand_rub',   "Alcohol Hand Rub Gel 500ml",          "CLN-004", 'CLEANING',       "bottle",   3500,  50, 120, "All Wards — Wall dispensers",    vendor_key='cleanpro',     desc="WHO-formulation ABHR. Dispensers at all entry points.")
I('detergent',  "Hospital Detergent Concentrate 5L",   "CLN-005", 'CLEANING',       "can",      8500,   8,  18, "Housekeeping Store",             vendor_key='cleanpro',     desc="Low-foaming enzymatic detergent for floors and surfaces.")
I('mop_heads',  "Cotton Mop Heads (replaceable)",      "CLN-006", 'CLEANING',       "piece",    4500,  20,  42, "Housekeeping Store",             vendor_key='cleanpro',     desc="Colour-coded mop heads (blue=general, red=toilet).")
I('bin_liners', "Domestic Bin Liners 60L (roll/50)",   "CLN-007", 'CLEANING',       "roll",     2800,  10,  25, "Housekeeping Store",             vendor_key='cleanpro',     desc="Black domestic waste bin liners.")

# ── LINEN / LAUNDRY ────────────────────────────────────────────────────────────
I('bed_sheet',  "Hospital Bed Sheet (white cotton)",   "LIN-001", 'LINEN',          "piece",    8500,  50, 180, "Linen Store, Shelf A",           vendor_key='camtextile',   desc="100% cotton white bed sheet 190x90cm. JCI standard.")
I('pillow_case',"Pillow Case (white cotton)",          "LIN-002", 'LINEN',          "piece",    3500,  50, 200, "Linen Store, Shelf A",           vendor_key='camtextile',   desc="Standard 50x70cm pillowcase.")
I('theatre_drape',"Theatre Drape (sterile, large)",   "LIN-003", 'LINEN',          "piece",   12000,  20,  45, "Theatre Linen Cabinet",          vendor_key='camtextile',   desc="Sterile surgical draping sheet — JCI theatre standard.")
I('patient_gown',"Patient Hospital Gown",             "LIN-004", 'LINEN',          "piece",    6500,  30, 110, "Linen Store, Shelf B",           vendor_key='camtextile',   desc="Tie-back patient gown. Easy IV access design.")
I('theatre_gown',"Surgeon Theatre Gown (sterile)",    "LIN-005", 'LINEN',          "piece",   14000,  20,  38, "Theatre Linen Cabinet",          vendor_key='camtextile',   desc="Sterile water-resistant surgical gown.")
I('nurse_scrubs',"Nursing Scrubs Set (medium)",       "LIN-006", 'LINEN',          "set",     18000,  15,  55, "Staff Room Store",               vendor_key='camtextile',   desc="V-neck scrub top + trousers. Green for nursing staff.")
I('blanket',    "Hospital Blanket (acrylic)",          "LIN-007", 'LINEN',          "piece",   12000,  30, 105, "Linen Store, Shelf C",           vendor_key='camtextile',   desc="Washable acrylic patient blanket.")

# ── KITCHEN / DIETARY ─────────────────────────────────────────────────────────
I('rice',       "Rice (long grain) 50kg sack",         "KIT-001", 'OTHER',          "sack",    22000,   5,  18, "Kitchen Dry Store",              vendor_key='nutricam',     desc="Staple carbohydrate — all diet types.")
I('beans',      "Black-eye Beans 25kg sack",           "KIT-002", 'OTHER',          "sack",    18000,   3,  10, "Kitchen Dry Store",              vendor_key='nutricam',     desc="High-protein legume for patient meals.")
I('cooking_oil',"Vegetable Cooking Oil 20L",           "KIT-003", 'OTHER',          "can",     16000,   4,  14, "Kitchen Dry Store",              vendor_key='nutricam',     desc="Refined vegetable oil for food preparation.")
I('lpg_gas',    "LPG Cooking Gas Cylinder 12.5kg",     "KIT-004", 'OTHER',          "cylinder",16500,   6,  16, "Kitchen Gas Store",              vendor_key='nutricam',     desc="LPG for hospital kitchen cooking.", storage="Upright, ventilated area")
I('sugar',      "Sugar (refined white) 50kg sack",     "KIT-005", 'OTHER',          "sack",    28000,   3,  12, "Kitchen Dry Store",              vendor_key='nutricam',     desc="Sugar for patient beverages and diet preparations.")
I('salt',       "Iodised Salt 25kg sack",              "KIT-006", 'OTHER',          "sack",     8500,   2,   8, "Kitchen Dry Store",              vendor_key='nutricam',     desc="Iodised table salt.")
I('milk_powder',"Full Cream Milk Powder 25kg",         "KIT-007", 'OTHER',          "bag",     48000,   2,   5, "Kitchen Dry Store",              expiry=True, vendor_key='nutricam',     desc="Full cream powdered milk for patient nutrition.")

# ── OFFICE / ADMIN ───────────────────────────────────────────────────────────
I('a4_paper',   "A4 Paper 80g Ream",                   "OFC-001", 'OFFICE',         "ream",     3500,  10,  42, "Admin Store",                    vendor_key='officepro',    desc="Standard printing paper.")
I('rx_pad',     "Prescription Pad (50 leaves NCR)",    "OFC-002", 'OFFICE',         "pad",      1200,  20,  38, "Admin Store",                    vendor_key='officepro',    desc="Numbered NCR prescription pads.")
I('folder',     "Manila Patient File Folder",          "OFC-003", 'OFFICE',         "piece",     450,  50, 280, "Admin Store",                    vendor_key='officepro',    desc="Patient medical record file folders.")
I('ballpen',    "Ballpoint Pens (box/50)",             "OFC-004", 'OFFICE',         "box",      5500,   5,  18, "Admin Store",                    vendor_key='officepro',    desc="Blue ballpoint pens for all departments.")
I('toner_hp',   "HP Laser Toner Cartridge (CF217A)",   "OFC-005", 'IT',             "cartridge",32000,  4,   7, "IT Store",                       vendor_key='officepro',    desc="Black toner for HP LaserJet Pro M130fw printers.")
I('ream_therm', "Thermal Paper Roll (80mm)",           "OFC-006", 'OFFICE',         "roll",      1800, 20,  55, "Admin Store",                    vendor_key='officepro',    desc="Thermal receipt rolls for cashier POS printers.")
I('wristband',  "Patient ID Wristbands (box/250)",     "OFC-007", 'OFFICE',         "box",      8500,   5,  18, "Admin Store",                    vendor_key='officepro',    desc="Pre-printed patient identification wristbands.")

# ── MAINTENANCE / FACILITIES ─────────────────────────────────────────────────
I('autoclave_tape',"Autoclave Indicator Tape (50m)",   "MNT-001",'OTHER',           "roll",     4500,  10,  22, "CSSD Store",                     vendor_key='africamed',    desc="Chemical indicator tape for steam sterilisation cycle.")
I('autoclave_bag', "Autoclave Pouches (18x35cm, x200)","MNT-002",'OTHER',           "box",     22000,   5,  12, "CSSD Store",                     vendor_key='africamed',    desc="Self-sealing sterilisation pouches for CSSD instruments.")
I('glut_28',    "Glutaraldehyde 2.8% Cidex (5L)",      "MNT-003",'CLEANING',        "can",     38000,   4,  10, "CSSD High-Level Disinfection Area",expiry=True,vendor_key='cleanpro', desc="High-level disinfectant for heat-sensitive endoscopes.")
I('battery_9v', "9V Alkaline Batteries (pack/10)",     "MNT-004",'OTHER',           "pack",     3500,  10,  28, "Maintenance Store",               vendor_key='officepro',    desc="For BP monitors, glucometers, otoscopes.")
I('bulb_led',   "LED Bulb 15W E27 (pack/5)",           "MNT-005",'OTHER',           "pack",     7500,   8,  20, "Maintenance Store",               vendor_key='officepro',    desc="Energy-saving LEDs for wards and corridors.")

print(f"  Created {InventoryItem.objects.count()} items across all departments")

# ════════════════════════════════════════════════════════════════════════════
# PURCHASE ORDERS
# ════════════════════════════════════════════════════════════════════════════
print("\nCreating purchase orders...")
po_list = []

def make_po(vendor_key, status, ord_ago, exp_days=7, rec_ago=None, notes='', is_auto=False):
    v = vendors[vendor_key]
    ord_date = today - timedelta(days=ord_ago)
    exp_date = ord_date + timedelta(days=exp_days)
    rec_date = today - timedelta(days=rec_ago) if rec_ago is not None else None
    po = PurchaseOrder(
        vendor=v, status=status,
        ordered_date=ord_date, expected_date=exp_date,
        received_date=rec_date, notes=notes,
        approved_by=admin if status not in ('DRAFT',) else None,
        is_auto_generated=is_auto,
    )
    po.po_number = f"SEED-{uuid.uuid4().hex[:8].upper()}"
    po.save()
    return po

def add_lines(po, line_list, receive=False):
    total = Decimal('0')
    for item_key, qty, price, lot, mfg_dago, exp_dago in line_list:
        item = items[item_key]
        rec_qty = qty if receive else 0
        poi = PurchaseOrderItem.objects.create(
            purchase_order=po, item=item,
            quantity_ordered=qty, quantity_received=rec_qty,
            unit_price=Decimal(str(price)),
            lot_number=lot,
            manufactured_date=(today - timedelta(days=mfg_dago)) if mfg_dago else None,
            expiry_date=(today + timedelta(days=exp_dago)) if exp_dago else None,
        )
        total += poi.subtotal
    PurchaseOrder.objects.filter(pk=po.pk).update(total_amount=total)
    return po

# PO 1 — RECEIVED — MEDIPHARM — Quarterly pharma bulk (60 days ago)
po1 = make_po('medipharm','RECEIVED', ord_ago=60, exp_days=10, rec_ago=50, notes="Q3 2026 quarterly pharmaceutical restocking — bulk order")
add_lines(po1, [
    ('amox500',    300, 4500,  f"MPC-{Y}-AMX-Q3",   120, 730),
    ('cipro500',   150, 6800,  f"MPC-{Y}-CIP-Q3",    90, 730),
    ('metro500iv', 120, 2200,  f"MPC-{Y}-MET-Q3",    90, 640),
    ('paraciv',    400, 2100,  f"MPC-{Y}-PAR-Q3",    60, 730),
    ('ceftriax',   200, 3500,  f"MPC-{Y}-CEF-Q3",    90, 730),
    ('ringer',     800, 1800,  f"MPC-{Y}-RL-Q3",     45, 730),
    ('ns09',       700, 1600,  f"MPC-{Y}-NS-Q3",     45, 730),
    ('dextrose5',  400, 1700,  f"MPC-{Y}-D5-Q3",     45, 730),
    ('artesunate', 100, 5500,  f"MPC-{Y}-ART-Q3",    60, 548),
    ('coartem',    120, 4800,  f"MPC-{Y}-COA-Q3",    60, 548),
], receive=True)

# PO 2 — RECEIVED — AfricaMed — Surgical consumables (30 days ago)
po2 = make_po('africamed','RECEIVED', ord_ago=30, exp_days=5, rec_ago=24, notes="Monthly surgical consumables — all wards and theatre")
add_lines(po2, [
    ('glove_m',    800, 450,   "", None, None),
    ('glove_l',    500, 450,   "", None, None),
    ('glove_s',    300, 450,   "", None, None),
    ('exam_glove', 200, 2500,  "", None, None),
    ('cannula20',  600, 350,   "", None, None),
    ('cannula18',  400, 350,   "", None, None),
    ('cannula24',  250, 380,   "", None, None),
    ('syringe5',  1200, 120,   "", None, None),
    ('syringe10',  800, 150,   "", None, None),
    ('syringe20',  400, 200,   "", None, None),
    ('needle21',  2000,  80,   "", None, None),
    ('iv_set',     600, 650,   "", None, None),
    ('sharps_bin', 200, 800,   "", None, None),
    ('surgical_mask',100,3500, "", None, None),
    ('n95_mask',    50, 9500,  "", None, None),
], receive=True)

# PO 3 — RECEIVED — OPHTEX — Eye clinic full restocking (20 days ago)
po3 = make_po('ophtex','RECEIVED', ord_ago=20, exp_days=10, rec_ago=8, notes="Eye clinic and theatre ophthalmic supplies — Q3 restocking")
add_lines(po3, [
    ('atropine',   60, 3200,   f"OPX-{Y}-AT",  60, 365),
    ('fluorescein',80, 4100,   f"OPX-{Y}-FL",  30, 548),
    ('timolol',    48, 4800,   f"OPX-{Y}-TIM", 30, 548),
    ('brinzolamide',24,9500,   f"OPX-{Y}-BRZ", 30, 548),
    ('lubricant',  60, 2800,   f"OPX-{Y}-LUB", 30, 365),
    ('predforte',  36, 7200,   f"OPX-{Y}-PRD", 30, 548),
    ('prolene60',  24, 24000,  f"OPX-{Y}-P60", 30, 1095),
    ('prolene100', 12, 38000,  f"OPX-{Y}-P100",30, 1095),
    ('iol_mono',   12, 45000,  f"OPX-{Y}-IOL1",60, 548),
    ('iol_toric',   6, 95000,  f"OPX-{Y}-TOR1",60, 548),
    ('ahmed_valve', 4, 280000, f"OPX-{Y}-AHM1",90, 730),
    ('viscoelastic',20,28000,  f"OPX-{Y}-VIS", 60, 548),
    ('scalpel15',  10, 14000,  "", None, None),
], receive=True)

# PO 4 — RECEIVED — LabCore — Lab reagents (OLD BATCH — expiring soon for dashboard alerts)
po4 = make_po('labcore','RECEIVED', ord_ago=310, exp_days=7, rec_ago=302, notes="Lab reagents — Jan 2026 batch (approaching expiry — see dashboard alerts)")
add_lines(po4, [
    ('glucstrip',   40, 12000, f"LBC-{Y-1}-G1",  365,  55),
    ('hba1c',       25, 8500,  f"LBC-{Y-1}-H1",  365,  55),
    ('malaria_rdt', 20, 15000, f"LBC-{Y-1}-M1",  330,  45),
    ('hiv_test',    15, 22000, f"LBC-{Y-1}-HIV1", 330, 45),
    ('hbsag',       15, 14000, f"LBC-{Y-1}-HBS1", 310, 40),
    ('preg_test',   20, 6500,  f"LBC-{Y-1}-PRG1", 300, 60),
    ('urine_strips',18, 8000,  f"LBC-{Y-1}-UR1",  290, 60),
    ('stain_gram',   8, 9800,  f"LBC-{Y-1}-GRM1", 300, 90),
    ('agar_blood',  10, 18000, f"LBC-{Y-1}-AGA1", 300, 90),
], receive=True)

# PO 5 — RECEIVED — PharmaCentre — Surgical sutures + controlled drugs (15 days ago)
po5 = make_po('pharmacentre','RECEIVED', ord_ago=15, exp_days=5, rec_ago=9, notes="Theatre sutures and controlled drug replenishment")
add_lines(po5, [
    ('vicryl20',   48, 18000,  f"PHA-{Y}-V20",  30, 1095),
    ('vicryl30',   36, 18000,  f"PHA-{Y}-V30",  30, 1095),
    ('morphine',   60, 4500,   f"PHA-{Y}-MOR",  60, 730),
    ('midazolam',  40, 6200,   f"PHA-{Y}-MDZ",  60, 730),
    ('ketamine',   30, 7500,   f"PHA-{Y}-KET",  60, 730),
    ('bupivacaine',80, 2800,   f"PHA-{Y}-BUP",  30, 730),
    ('etomidate',  40, 9500,   f"PHA-{Y}-ETO",  60, 730),
    ('atracurium', 40, 7200,   f"PHA-{Y}-ATR",  60, 548),
    ('neostigmine',30, 4500,   f"PHA-{Y}-NEO",  60, 730),
    ('sevoflurane', 8, 185000, f"PHA-{Y}-SEV",  60, 730),
], receive=True)

# PO 6 — RECEIVED — CleanPro — Monthly housekeeping (7 days ago)
po6 = make_po('cleanpro','RECEIVED', ord_ago=7, exp_days=3, rec_ago=2, notes="Monthly housekeeping and PPE supplies")
add_lines(po6, [
    ('chlorhex',   60, 2800,   "", None, None),
    ('alcohol70',  80, 3200,   "", None, None),
    ('bleach10',   50, 4500,   "", None, None),
    ('hand_rub',  150, 3500,   "", None, None),
    ('detergent',  20, 8500,   "", None, None),
    ('mop_heads',  50, 4500,   "", None, None),
    ('bin_liners', 30, 2800,   "", None, None),
    ('waste_red',  30, 3800,   "", None, None),
    ('waste_yellow',20,3800,   "", None, None),
    ('apron',      50, 4500,   "", None, None),
    ('face_shield', 20,12000,  "", None, None),
    ('surgical_mask',100,3500, "", None, None),
], receive=True)

# PO 7 — RECEIVED — CamTextile — Linen restocking (14 days ago)
po7 = make_po('camtextile','RECEIVED', ord_ago=14, exp_days=7, rec_ago=6, notes="Hospital linen annual restocking — all wards")
add_lines(po7, [
    ('bed_sheet',   100, 8500,  "", None, None),
    ('pillow_case', 120, 3500,  "", None, None),
    ('patient_gown', 60, 6500,  "", None, None),
    ('blanket',      60,12000,  "", None, None),
    ('theatre_drape',30,12000,  "", None, None),
    ('theatre_gown', 25,14000,  "", None, None),
    ('nurse_scrubs', 20,18000,  "", None, None),
], receive=True)

# PO 8 — RECEIVED — NutriCam — Kitchen monthly food supplies (5 days ago)
po8 = make_po('nutricam','RECEIVED', ord_ago=5, exp_days=2, rec_ago=1, notes="Monthly kitchen dry goods — August 2026")
add_lines(po8, [
    ('rice',         20, 22000, "", None, None),
    ('beans',        10, 18000, "", None, None),
    ('cooking_oil',  10, 16000, "", None, None),
    ('lpg_gas',       8, 16500, "", None, None),
    ('sugar',         8, 28000, "", None, None),
    ('salt',          5,  8500, "", None, None),
    ('milk_powder',   4, 48000, "", None, None),
], receive=True)

# PO 9 — RECEIVED — MediGas — Oxygen cylinders (10 days ago)
po9 = make_po('medigas','RECEIVED', ord_ago=10, exp_days=3, rec_ago=6, notes="Medical gas cylinder top-up — ICU + Theatre")
add_lines(po9, [
    ('o2_cylinder', 15, 18000, "", None, None),
    ('nitrous',      4, 14000, "", None, None),
], receive=True)

# PO 10 — RECEIVED — OfficePro — Admin stationery (20 days ago)
po10 = make_po('officepro','RECEIVED', ord_ago=20, exp_days=5, rec_ago=14, notes="Admin and IT consumables — monthly order")
add_lines(po10, [
    ('a4_paper',    50, 3500,  "", None, None),
    ('rx_pad',      50, 1200,  "", None, None),
    ('folder',     300, 450,   "", None, None),
    ('ballpen',     20, 5500,  "", None, None),
    ('ream_therm',  60, 1800,  "", None, None),
    ('wristband',   20, 8500,  "", None, None),
    ('toner_hp',     6, 32000, "", None, None),
    ('battery_9v',  20, 3500,  "", None, None),
    ('bulb_led',    15, 7500,  "", None, None),
], receive=True)

# PO 11 — RECEIVED — AfricaMed — CSSD and anaesthesia (25 days ago)
po11 = make_po('africamed','RECEIVED', ord_ago=25, exp_days=7, rec_ago=16, notes="CSSD sterilisation supplies + anaesthesia consumables")
add_lines(po11, [
    ('et_tube70',   60, 1800,  "", None, None),
    ('et_tube65',   50, 1800,  "", None, None),
    ('lma_3',       15, 22000, "", None, None),
    ('lma_4',       15, 22000, "", None, None),
    ('sp_needle',   80, 2200,  f"AFM-{Y}-SPN", 30, 1095),
    ('epi_kit',     20, 18000, f"AFM-{Y}-EPI", 30, 1095),
    ('catheter16',  80, 2800,  f"AFM-{Y}-C16", 30, 1095),
    ('catheter12',  40, 2800,  f"AFM-{Y}-C12", 30, 1095),
    ('ng_tube',     50, 1800,  "", None, None),
    ('burette_set', 80, 950,   "", None, None),
    ('wound_drain', 30, 5500,  f"AFM-{Y}-WDR", 30, 1095),
    ('scalpel10',   10, 14000, "", None, None),
    ('autoclave_tape',20,4500, "", None, None),
    ('autoclave_bag', 15,22000,"", None, None),
], receive=True)

# PO 12 — RECEIVED — CAMIDIA — Radiology (45 days ago)
po12 = make_po('camidia','RECEIVED', ord_ago=45, exp_days=10, rec_ago=35, notes="Radiology consumables — quarterly")
add_lines(po12, [
    ('xray_film',   10, 85000, "", None, None),
    ('contrast',    30, 24000, f"CAM-{Y}-CNTR", 90, 548),
    ('gel_ultrasound',12,8500, "", None, None),
], receive=True)

# PO 13 — APPROVED — LabCore — NEW batch reagents (pending delivery)
po13 = make_po('labcore','APPROVED', ord_ago=3, exp_days=7, notes="New lab reagents batch — replacing expiring stock (current batch expiring ≤60 days)")
add_lines(po13, [
    ('glucstrip',   50, 12000, "", None, None),
    ('hba1c',       30, 8500,  "", None, None),
    ('malaria_rdt', 25, 15000, "", None, None),
    ('hiv_test',    20, 22000, "", None, None),
    ('hbsag',       20, 14000, "", None, None),
    ('agar_blood',  15, 18000, "", None, None),
    ('blood_bags',  60, 3500,  "", None, None),
], receive=False)

# PO 14 — SUBMITTED — MEDIPHARM — Critical drug restock (Dexamethasone + Vancomycin)
po14 = make_po('medipharm','SUBMITTED', ord_ago=2, exp_days=5, notes="URGENT: Dexamethasone critically low (6 units). Vancomycin + Heparin below reorder.")
add_lines(po14, [
    ('dexa4mg',    200, 850,   "", None, None),
    ('vancomycin',  50, 8500,  "", None, None),
    ('heparin',     50, 5800,  "", None, None),
    ('insulin_r',   30, 12000, "", None, None),
    ('midazolam',   40, 6200,  "", None, None),
], receive=False)

# PO 15 — DRAFT — Auto-generated — N95 masks reorder trigger
po15 = make_po('africamed','DRAFT', ord_ago=1, exp_days=4, notes="AUTO-GENERATED: N95 masks fell to 5 boxes (reorder level = 10). Pending approval.", is_auto=True)
add_lines(po15, [
    ('n95_mask',    60, 9500,  "", None, None),
    ('face_shield', 30, 12000, "", None, None),
    ('waste_red',   40, 3800,  "", None, None),
], receive=False)

# PO 16 — DRAFT — Auto-generated — Bone wax + haemostat theatre supplies
po16 = make_po('africamed','DRAFT', ord_ago=0, exp_days=5, notes="AUTO-GENERATED: Haemostat Surgicel and bone wax hit reorder level.", is_auto=True)
add_lines(po16, [
    ('haemostat',   15, 42000, "", None, None),
    ('bone_wax',    15, 18000, "", None, None),
], receive=False)

print(f"  Created {PurchaseOrder.objects.count()} purchase orders")

# ════════════════════════════════════════════════════════════════════════════
# BATCH STOCKS — the key FEFO demo data
# ════════════════════════════════════════════════════════════════════════════
print("\nCreating batch stocks (FEFO tracking)...")

def B(item_key, lot, mfg_ago, exp_days, qty_recv, qty_rem, cost, po=None, quarantine=False, qreason=''):
    BatchStock.objects.create(
        item=items[item_key],
        lot_number=lot,
        manufactured_date=today - timedelta(days=mfg_ago) if mfg_ago else None,
        expiry_date=today + timedelta(days=exp_days),
        quantity_received=qty_recv,
        quantity_remaining=qty_rem,
        unit_cost=Decimal(str(cost)),
        purchase_order=po,
        is_quarantined=quarantine,
        quarantine_reason=qreason,
    )

# PHARMACEUTICALS — multiple batches showing FEFO ordering
B('amox500',    f"MPC-{Y-1}-AMX-Q4",  400,  180, 200, 45, 4500, po1)   # older batch — goes first
B('amox500',    f"MPC-{Y}-AMX-Q3",    120,  730, 300, 65, 4500, po1)   # newer batch — second
B('cipro500',   f"MPC-{Y}-CIP-Q3",     90,  730, 150, 55, 6800, po1)
B('metro500iv', f"MPC-{Y}-MET-Q3",     90,  640, 120, 22, 2200, po1)
B('paraciv',    f"MPC-{Y}-PAR-Q3",     60,  730, 400,145, 2100, po1)
B('dexa4mg',    f"MPC-{Y-1}-DEX-Q2",  300,   90, 100,  8,  850, po1)   # nearly expired — CRITICAL ALERT
B('ceftriax',   f"MPC-{Y}-CEF-Q3",     90,  730, 200, 68, 3500, po1)
B('vancomycin', f"PHA-{Y}-VAN",         60,  730,  30, 18, 8500, po5)
B('amoxi_susp', f"MPC-{Y}-AMXS",       90,  548, 60,  32, 2800, po1)
B('paracetamol_tab',f"MPC-{Y}-PCT",    120,  730, 40,  28, 1800, po1)
B('ibuprofen',  f"MPC-{Y}-IBU",        120,  730, 30,  19, 2200, po1)
B('amlodipine', f"MPC-{Y}-AML",        180, 1095, 60,  42, 3200, po1)
B('lisinopril', f"MPC-{Y}-LIS",        180, 1095, 50,  35, 3800, po1)
B('metformin',  f"MPC-{Y}-MET2",       180, 1095, 80,  48, 2600, po1)
B('ringer',     f"MPC-{Y}-RL-Q3",       45,  730, 800,310, 1800, po1)
B('ns09',       f"MPC-{Y}-NS-Q3",       45,  730, 700,285, 1600, po1)
B('dextrose5',  f"MPC-{Y}-D5-Q3",       45,  730, 400,190, 1700, po1)
B('morphine',   f"PHA-{Y}-MOR",          60,  730,  60, 35, 4500, po5)
B('midazolam',  f"PHA-{Y}-MDZ",          60,  730,  40, 22, 6200, po5)
B('ketamine',   f"PHA-{Y}-KET",          60,  730,  30, 16, 7500, po5)
B('heparin',    f"MPC-{Y}-HEP",          90,  730,  20, 14, 5800, po1)
B('insulin_r',  f"MPC-{Y}-INS",          60,  548,  25, 18,12000, po1)
B('ors',        f"MPC-{Y}-ORS",         120,  730,  40, 24, 3500, po1)
B('artesunate', f"MPC-{Y}-ART-Q3",      60,  548, 100, 28, 5500, po1)
B('coartem',    f"MPC-{Y}-COA-Q3",      60,  548, 120, 36, 4800, po1)
B('cotrimox',   f"MPC-{Y}-CTX",        120,  730,  50, 30, 1900, po1)
B('folic_acid', f"MPC-{Y}-FOL",        120,  730,  60, 40,  800, po1)
B('iron_folate',f"MPC-{Y}-IRF",        120,  730,  50, 35, 1200, po1)
B('oxytocin',   f"PHA-{Y}-OXY",         60,  548,  50, 30, 2800, po5)
B('magnesulph', f"MPC-{Y}-MGA",         90,  730,  70, 45, 1500, po1)
B('salbutamol_neb',f"MPC-{Y}-SAL",     90,  730,  60, 38, 1800, po1)

# EYE CLINIC BATCHES
B('atropine',   f"OPX-{Y}-AT",          60,  365,  60, 25, 3200, po3)
B('fluorescein',f"OPX-{Y}-FL",          30,  548,  80, 20, 4100, po3)
B('timolol',    f"OPX-{Y}-TIM",         30,  548,  48, 18, 4800, po3)
B('brinzolamide',f"OPX-{Y}-BRZ",        30,  548,  24, 12, 9500, po3)
B('lubricant',  f"OPX-{Y}-LUB",         30,  365,  60, 30, 2800, po3)
B('predforte',  f"OPX-{Y}-PRD",         30,  548,  36, 14, 7200, po3)

# LAB REAGENTS — OLD BATCH EXPIRING SOON (these show up in dashboard expiry alerts)
B('glucstrip',  f"LBC-{Y-1}-G1",       365,   55,  40, 14,12000, po4)  # WARNING — 55 days
B('hba1c',      f"LBC-{Y-1}-H1",       365,   55,  25, 10, 8500, po4)  # WARNING
B('malaria_rdt',f"LBC-{Y-1}-M1",       330,   45,  20, 12,15000, po4)  # CRITICAL — 45 days
B('hiv_test',   f"LBC-{Y-1}-HIV1",     330,   45,  15,  9,22000, po4)  # CRITICAL
B('hbsag',      f"LBC-{Y-1}-HBS1",     310,   40,  15,  7,14000, po4)  # CRITICAL
B('preg_test',  f"LBC-{Y-1}-PRG1",     300,   60,  20, 12, 6500, po4)  # WARNING
B('urine_strips',f"LBC-{Y-1}-UR1",     290,   60,  18, 10, 8000, po4)  # WARNING
B('stain_gram', f"LBC-{Y-1}-GRM1",     300,   90,   8,  8, 9800, po4)  # OK
B('agar_blood', f"LBC-{Y-1}-AGA1",     300,   90,  10,  6,18000, po4)  # OK

# BLOOD BAGS
B('blood_bags', f"LBC-{Y}-BLB",         60,  548,  80, 55, 3500, po4)

# SUTURES & SURGICAL (long expiry — shows stability)
B('vicryl20',   f"PHA-{Y}-V20",         30, 1095,  48, 24,18000, po5)
B('vicryl30',   f"PHA-{Y}-V30",         30, 1095,  36, 18,18000, po5)
B('prolene60',  f"OPX-{Y}-P60",         30, 1095,  24, 15,24000, po3)
B('prolene100', f"OPX-{Y}-P100",        30, 1095,  12,  8,38000, po3)
B('sp_needle',  f"AFM-{Y}-SPN",         30, 1095,  80, 55, 2200, po11)
B('epi_kit',    f"AFM-{Y}-EPI",         30, 1095,  20, 14,18000, po11)
B('catheter16', f"AFM-{Y}-C16",         30, 1095,  80, 68, 2800, po11)
B('catheter12', f"AFM-{Y}-C12",         30, 1095,  40, 30, 2800, po11)
B('wound_drain',f"AFM-{Y}-WDR",         30, 1095,  30, 22, 5500, po11)

# OPHTHALMIC LENSES & IMPLANTS (consignment — shows value on dashboard)
B('iol_mono',   f"OPX-{Y}-IOL1",        60,  548,  12,  7,45000, po3)
B('iol_toric',  f"OPX-{Y}-TOR1",        60,  548,   6,  4,95000, po3)
B('ahmed_valve',f"OPX-{Y}-AHM1",        90,  730,   4,  3,280000,po3)
B('viscoelastic',f"OPX-{Y}-VIS",        60,  548,  20, 10,28000, po3)

# ANAESTHESIA BATCHES
B('bupivacaine',f"PHA-{Y}-BUP",         30,  730,  80, 42, 2800, po5)
B('etomidate',  f"PHA-{Y}-ETO",         60,  730,  40, 18, 9500, po5)
B('atracurium', f"PHA-{Y}-ATR",         60,  548,  40, 24, 7200, po5)
B('neostigmine', f"PHA-{Y}-NEO",         60,  730,  30, 16, 4500, po5)
B('sevoflurane',f"PHA-{Y}-SEV",         60,  730,   8,  4,185000,po5)
B('et_tube70',  f"AFM-{Y}-ET70",        30, 1095,  60, 65, 1800, po11)
B('et_tube65',  f"AFM-{Y}-ET65",        30, 1095,  50, 50, 1800, po11)

# CONTRAST AGENT (radiology — expiry tracked)
B('contrast',   f"CAM-{Y}-CNTR",        90,  548,  30, 22,24000, po12)

# QUARANTINED BATCH — shows quality control
B('glucstrip',  f"LBC-{Y}-G2-QUAR",    120,  365,  10,  10,12000, po4,
  quarantine=True, qreason="Cold chain break reported during transport — batch under QC hold pending vendor investigation")

print(f"  Created {BatchStock.objects.count()} batch records")

# ════════════════════════════════════════════════════════════════════════════
# STOCK MOVEMENTS — rich history across all departments
# ════════════════════════════════════════════════════════════════════════════
print("\nCreating stock movement history...")

mvs = [
    # PHARMA MOVEMENTS
    dict(item=items['amox500'],    movement_type='IN',     quantity=300,  balance_after=300,  reference=f"PO-{po1.po_number}", notes="Received from MEDIPHARM — Q3 quarterly order"),
    dict(item=items['amox500'],    movement_type='ISSUE',  quantity=-50,  balance_after=250,  reference="REQ-0001",             notes="General Ward weekly supply"),
    dict(item=items['amox500'],    movement_type='ISSUE',  quantity=-40,  balance_after=210,  reference="REQ-0005",             notes="Paediatrics ward supply"),
    dict(item=items['amox500'],    movement_type='ISSUE',  quantity=-60,  balance_after=150,  reference="REQ-0008",             notes="Eye clinic pre-op supply"),
    dict(item=items['amox500'],    movement_type='IN',     quantity=200,  balance_after=350,  reference=f"PO-{po1.po_number}", notes="Second lot received"),
    dict(item=items['amox500'],    movement_type='ISSUE',  quantity=-120, balance_after=230,  reference="Multiple REQs",        notes="Weekly ward issues — 6 departments"),
    dict(item=items['amox500'],    movement_type='ISSUE',  quantity=-120, balance_after=110,  reference="Monthly issue run",    notes="All wards combined"),

    dict(item=items['ringer'],     movement_type='IN',     quantity=800,  balance_after=800,  reference=f"PO-{po1.po_number}", notes="Q3 IV fluid bulk received"),
    dict(item=items['ringer'],     movement_type='ISSUE',  quantity=-200, balance_after=600,  reference="All wards",            notes="ICU + General Ward daily IV fluids"),
    dict(item=items['ringer'],     movement_type='ISSUE',  quantity=-180, balance_after=420,  reference="Theatre + ICU",        notes="Theatre surgical use + ICU patients"),
    dict(item=items['ringer'],     movement_type='ISSUE',  quantity=-110, balance_after=310,  reference="Various wards",        notes="Maternity + Emergency combined"),

    dict(item=items['dexa4mg'],    movement_type='IN',     quantity=100,  balance_after=100,  reference=f"PO-{po1.po_number}", notes="Received — ophthalmology and ICU stock"),
    dict(item=items['dexa4mg'],    movement_type='ISSUE',  quantity=-30,  balance_after=70,   reference="Eye Clinic Theatre",   notes="Post-op cataract patients — 30 ampoules"),
    dict(item=items['dexa4mg'],    movement_type='ISSUE',  quantity=-35,  balance_after=35,   reference="ICU",                  notes="Severe asthma and anaphylaxis cases"),
    dict(item=items['dexa4mg'],    movement_type='ISSUE',  quantity=-27,  balance_after=8,    reference="Multiple depts",       notes="Emergency use + Maternity (eclampsia prophylaxis)"),

    dict(item=items['morphine'],   movement_type='IN',     quantity=60,   balance_after=60,   reference=f"PO-{po5.po_number}", notes="Controlled drug received — pharmacist signature"),
    dict(item=items['morphine'],   movement_type='ISSUE',  quantity=-15,  balance_after=45,   reference="ICU",                  notes="Post-op analgesia — ICU patients"),
    dict(item=items['morphine'],   movement_type='ISSUE',  quantity=-10,  balance_after=35,   reference="Surgical Ward",        notes="Post-surgical pain management"),

    dict(item=items['artesunate'], movement_type='IN',     quantity=100,  balance_after=100,  reference=f"PO-{po1.po_number}", notes="Severe malaria treatment supply"),
    dict(item=items['artesunate'], movement_type='ISSUE',  quantity=-42,  balance_after=58,   reference="Emergency + Gen Ward", notes="Severe malaria cases — NACP protocol"),
    dict(item=items['artesunate'], movement_type='ISSUE',  quantity=-30,  balance_after=28,   reference="Paediatrics",          notes="Paediatric severe malaria cases"),

    # LAB MOVEMENTS
    dict(item=items['malaria_rdt'],movement_type='IN',     quantity=20,   balance_after=20,   reference=f"PO-{po4.po_number}", notes="Lab reagents received — Jan 2026 batch"),
    dict(item=items['malaria_rdt'],movement_type='ISSUE',  quantity=-8,   balance_after=12,   reference="Lab daily use",        notes="Daily RDT screening — outpatient and ward"),
    dict(item=items['malaria_rdt'],movement_type='EXPIRE', quantity=-2,   balance_after=10,   reference="EXPIRY-WO-001",        notes="2 kits written off — found expired on shelf audit"),

    dict(item=items['glucstrip'],  movement_type='IN',     quantity=40,   balance_after=40,   reference=f"PO-{po4.po_number}", notes="Blood glucose strips — Jan batch"),
    dict(item=items['glucstrip'],  movement_type='ISSUE',  quantity=-16,  balance_after=24,   reference="Lab + Ward rounds",    notes="Diabetic patient monitoring — daily rounds"),
    dict(item=items['glucstrip'],  movement_type='ISSUE',  quantity=-10,  balance_after=14,   reference="Diabetic clinic",      notes="Monthly diabetic clinic screening"),

    # SURGICAL / THEATRE
    dict(item=items['glove_m'],    movement_type='IN',     quantity=800,  balance_after=800,  reference=f"PO-{po2.po_number}", notes="AfricaMed monthly delivery — sterile gloves"),
    dict(item=items['glove_m'],    movement_type='ISSUE',  quantity=-80,  balance_after=720,  reference="Theatre",              notes="Daily theatre sessions — Mon to Fri"),
    dict(item=items['glove_m'],    movement_type='ISSUE',  quantity=-100, balance_after=620,  reference="All wards",            notes="Ward procedure gloves — weekly issue"),

    dict(item=items['syringe5'],   movement_type='IN',     quantity=1200, balance_after=1200, reference=f"PO-{po2.po_number}", notes="Bulk syringe stock received"),
    dict(item=items['syringe5'],   movement_type='ISSUE',  quantity=-800, balance_after=400,  reference="All departments",      notes="Bi-weekly comprehensive ward issue"),

    dict(item=items['vicryl20'],   movement_type='IN',     quantity=48,   balance_after=48,   reference=f"PO-{po5.po_number}", notes="Theatre sutures received"),
    dict(item=items['vicryl20'],   movement_type='ISSUE',  quantity=-14,  balance_after=34,   reference="Theatre",              notes="General surgery — abdominal closures"),
    dict(item=items['vicryl20'],   movement_type='ISSUE',  quantity=-10,  balance_after=24,   reference="Theatre",              notes="Obstetric surgery — caesarean sections"),

    # EYE CLINIC
    dict(item=items['iol_mono'],   movement_type='IN',     quantity=12,   balance_after=12,   reference=f"PO-{po3.po_number}", notes="IOL consignment received — OPHTEX"),
    dict(item=items['iol_mono'],   movement_type='ISSUE',  quantity=-3,   balance_after=9,    reference="SURG-OPH-2026-0043",  notes="Cataract surgery — 3 IOLs implanted (consignment charged)"),
    dict(item=items['iol_mono'],   movement_type='ISSUE',  quantity=-2,   balance_after=7,    reference="SURG-OPH-2026-0051",  notes="2 cataract procedures — bilateral"),
    dict(item=items['ahmed_valve'],movement_type='IN',     quantity=4,    balance_after=4,    reference=f"PO-{po3.po_number}", notes="Ahmed glaucoma implants received — consignment"),
    dict(item=items['ahmed_valve'],movement_type='ISSUE',  quantity=-1,   balance_after=3,    reference="SURG-OPH-2026-0055",  notes="Trabeculectomy + Ahmed valve implant — glaucoma case"),

    # ANAESTHESIA
    dict(item=items['o2_cylinder'],movement_type='IN',     quantity=15,   balance_after=15,   reference=f"PO-{po9.po_number}", notes="Medical oxygen cylinders — MediGas refill"),
    dict(item=items['o2_cylinder'],movement_type='ISSUE',  quantity=-3,   balance_after=12,   reference="ICU",                  notes="ICU ventilated patients — daily consumption"),
    dict(item=items['o2_cylinder'],movement_type='ISSUE',  quantity=-4,   balance_after=8,    reference="Theatre",              notes="Theatre GA sessions — weekly"),
    dict(item=items['et_tube70'],  movement_type='IN',     quantity=60,   balance_after=60,   reference=f"PO-{po11.po_number}",notes="Anaesthesia consumables received"),
    dict(item=items['et_tube70'],  movement_type='ISSUE',  quantity=-5,   balance_after=55,   reference="Theatre",              notes="GA intubations — cataract and general surgery list"),

    # CLEANING / PPE
    dict(item=items['hand_rub'],   movement_type='IN',     quantity=150,  balance_after=150,  reference=f"PO-{po6.po_number}", notes="ABHR dispensers restocked — CleanPro delivery"),
    dict(item=items['hand_rub'],   movement_type='ISSUE',  quantity=-30,  balance_after=120,  reference="All wards",            notes="Daily dispenser top-up — 12 ward stations"),
    dict(item=items['n95_mask'],   movement_type='IN',     quantity=50,   balance_after=50,   reference=f"PO-{po2.po_number}", notes="PPE received — AfricaMed"),
    dict(item=items['n95_mask'],   movement_type='ISSUE',  quantity=-25,  balance_after=25,   reference="ICU + Isolation",      notes="ICU staff and isolation ward"),
    dict(item=items['n95_mask'],   movement_type='ISSUE',  quantity=-20,  balance_after=5,    reference="Theatre + Emergency",  notes="Theatre team + emergency procedures"),

    # LINEN
    dict(item=items['bed_sheet'],  movement_type='IN',     quantity=100,  balance_after=100,  reference=f"PO-{po7.po_number}", notes="Linen received — CamTextile annual restock"),
    dict(item=items['bed_sheet'],  movement_type='ISSUE',  quantity=-60,  balance_after=40,   reference="All wards",            notes="Ward distribution — General, Paeds, Maternity, Eye"),
    dict(item=items['bed_sheet'],  movement_type='ADJUST', quantity=140,  balance_after=180,  reference="STOCK-ADJ-LIN-001",    notes="Laundry returned to store — post-wash count"),

    # KITCHEN
    dict(item=items['rice'],       movement_type='IN',     quantity=20,   balance_after=20,   reference=f"PO-{po8.po_number}", notes="Kitchen dry goods received — NutriCam August delivery"),
    dict(item=items['rice'],       movement_type='ISSUE',  quantity=-2,   balance_after=18,   reference="Kitchen daily",        notes="Daily kitchen use — average 70kg/day"),

    # ADJUSTMENTS
    dict(item=items['syringe1'],   movement_type='ADJUST', quantity=200,  balance_after=1050, reference="STOCK-ADJ-002",        notes="Annual physical count — found additional stock in paeds clinic store"),
    dict(item=items['a4_paper'],   movement_type='IN',     quantity=50,   balance_after=50,   reference=f"PO-{po10.po_number}", notes="Admin stationery received"),
    dict(item=items['a4_paper'],   movement_type='ISSUE',  quantity=-8,   balance_after=42,   reference="All admin depts",      notes="Admin departments weekly paper issue"),
]

for md in mvs:
    extra = {}
    if 'notes' not in md and '"notes"' in str(md):
        pass
    StockMovement.objects.create(performed_by=admin, **md)

print(f"  Created {StockMovement.objects.count()} stock movements")

# ════════════════════════════════════════════════════════════════════════════
# DEPARTMENT REQUISITIONS — from every ward
# ════════════════════════════════════════════════════════════════════════════
print("\nCreating department requisitions...")

def req(dept, priority, status, days_ago, item_list, notes="", needed=3):
    r = DepartmentRequisition(
        department=dept, requested_by=admin,
        priority=priority, status=status, notes=notes,
        needed_by=today + timedelta(days=needed),
        approved_by=admin if status not in ("PENDING","REJECTED") else None,
        issued_by=admin if status in ("ISSUED","PARTIAL") else None,
        issued_at=timezone.now()-timedelta(days=days_ago-1) if status in ("ISSUED","PARTIAL") else None,
    )
    r.req_number = ""
    r.save()
    for item_key, qty_r, qty_i in item_list:
        RequisitionItem.objects.create(
            requisition=r, item=items[item_key],
            quantity_requested=qty_r, quantity_issued=qty_i,
        )
    return r

# ISSUED — completed requisitions (historical)
req("General Ward (Male)","ROUTINE","ISSUED",7,
    [("amox500",40,40),("syringe5",100,100),("cannula20",50,50),("ringer",60,60),("iv_set",40,40),("paracetamol_tab",5,5)],
    notes="Monday weekly restocking — General Male Ward")

req("General Ward (Female)","ROUTINE","ISSUED",7,
    [("amox500",35,35),("syringe5",80,80),("cannula18",30,30),("ringer",50,50),("iv_set",35,35)],
    notes="Monday weekly restocking — General Female Ward")

req("ICU / Critical Care","URGENT","ISSUED",5,
    [("metro500iv",20,20),("dexa4mg",15,15),("paraciv",40,40),("cannula18",30,30),("ceftriax",20,20),("heparin",5,5),("syringe20",20,20)],
    notes="ICU critical drug replenishment — mid-week urgent")

req("Surgical Theatre","ROUTINE","ISSUED",6,
    [("glove_m",100,100),("glove_l",80,80),("vicryl20",8,8),("vicryl30",6,6),("syringe10",60,60),("scalpel10",2,2),("bupivacaine",30,30)],
    notes="Theatre weekly consumables before cataract list")

req("Paediatrics Ward","ROUTINE","ISSUED",4,
    [("amox500",30,30),("syringe5",80,80),("amoxi_susp",10,10),("paraciv",30,30),("cannula24",30,30),("burette_set",20,20)],
    notes="Paediatrics weekly restocking — Wednesday")

req("Maternity Ward","ROUTINE","ISSUED",3,
    [("oxytocin",20,20),("magnesulph",20,20),("ringer",40,40),("folic_acid",10,10),("iron_folate",10,10),("cannula18",20,20),("glove_m",30,30)],
    notes="Maternity ward weekly supplies — obstetric essentials")

req("Eye Clinic / Theatre","ROUTINE","ISSUED",8,
    [("atropine",10,10),("fluorescein",15,15),("prolene60",4,4),("lubricant",10,10),("predforte",6,6),("timolol",6,6)],
    notes="Eye clinic weekly supply run — pre-cataract list")

req("Emergency Department","URGENT","ISSUED",2,
    [("ceftriax",20,20),("ringer",30,30),("ns09",20,20),("cannula18",20,20),("morphine",5,5),("glove_m",30,30),("syringe10",30,30)],
    notes="Emergency dept bi-weekly urgent replenishment")

req("Laboratory","ROUTINE","ISSUED",5,
    [("malaria_rdt",3,3),("hiv_test",2,2),("preg_test",5,5),("urine_strips",3,3),("glove_m",20,20)],
    notes="Lab weekly reagent issue from pharmacy store")

req("Radiology","ROUTINE","ISSUED",10,
    [("gel_ultrasound",2,2),("contrast",5,5),("glove_m",10,10),("syringe20",10,10)],
    notes="Radiology monthly consumables")

req("Isolation Ward","URGENT","ISSUED",4,
    [("n95_mask",5,5),("glove_m",20,20),("apron",10,10),("face_shield",5,5),("hand_rub",3,3),("waste_red",2,2)],
    notes="Isolation ward infection control supplies — TB patient cohort")

req("Nursing Station (Ground)","ROUTINE","ISSUED",6,
    [("syringe1",100,100),("syringe5",100,100),("needle21",200,200),("sharps_bin",5,5),("surgical_mask",2,2)],
    notes="Ground floor nursing station restocking")

# APPROVED — issued soon
req("Anaesthesia / Theatre","URGENT","APPROVED",1,
    [("sevoflurane",2,0),("et_tube70",5,0),("sp_needle",10,0),("lma_4",2,0),("atracurium",8,0),("neostigmine",5,0)],
    notes="Pre-GA list supply — tomorrow's elective theatre list (4 cataract, 2 general)")

req("Paediatrics Ward","ROUTINE","APPROVED",1,
    [("cannula24",30,0),("burette_set",20,0),("syringe1",50,0),("malaria_rdt",3,0),("salbutamol_neb",10,0)],
    notes="Paediatrics weekly top-up — approved pending issue")

req("CSSD / Sterilisation","ROUTINE","APPROVED",2,
    [("autoclave_tape",5,0),("autoclave_bag",4,0),("glut_28",2,0),("glove_m",20,0)],
    notes="CSSD monthly sterilisation supplies")

# PARTIAL — partially fulfilled
req("Laboratory","ROUTINE","PARTIAL",2,
    [("glucstrip",5,2),("hba1c",3,1),("malaria_rdt",3,2),("hiv_test",2,1),("hbsag",2,1)],
    notes="Lab reagents — partial issue due to low stock; remainder on order (PO-13 approved)")

req("Pharmacy (Ward Stock)","ROUTINE","PARTIAL",3,
    [("artesunate",20,12),("coartem",15,10),("cotrimox",10,5)],
    notes="Pharmacy ward stock top-up — malaria season demand high")

# PENDING — awaiting approval
req("Maternity Ward","ROUTINE","PENDING",0,
    [("oxytocin",20,0),("cannula18",20,0),("ringer",30,0),("glove_m",30,0),("folic_acid",10,0)],
    notes="Maternity weekly supply request — Friday submission")

req("Ophthalmology Clinic","URGENT","PENDING",0,
    [("atropine",15,0),("dexa4mg",20,0),("fluorescein",10,0),("iol_mono",2,0),("viscoelastic",5,0)],
    notes="URGENT — pre-cataract surgery week: 12 cases listed Monday. Dexamethasone critically low.",
    needed=2)

req("Emergency Department","EMERGENCY","PENDING",0,
    [("dexa4mg",10,0),("metro500iv",20,0),("cannula18",20,0),("catheter16",5,0),("morphine",5,0),("ceftriax",15,0)],
    notes="EMERGENCY: multi-vehicle RTA — 6 critical patients. Immediate resupply needed.",
    needed=0)

req("ICU / Critical Care","URGENT","PENDING",0,
    [("vancomycin",10,0),("heparin",8,0),("insulin_r",4,0),("midazolam",8,0),("et_tube70",5,0)],
    notes="ICU critical drugs — MRSA case requires vancomycin IV. Stock dangerously low.")

req("Infectious Disease / HIV Clinic","ROUTINE","PENDING",0,
    [("cotrimox",20,0),("coartem",10,0),("hiv_test",5,0),("hbsag",3,0),("glove_m",20,0)],
    notes="HIV clinic monthly supplies — ART programme patient visit week")

req("Kitchen / Dietary","ROUTINE","PENDING",0,
    [("rice",4,0),("beans",2,0),("cooking_oil",2,0),("lpg_gas",3,0),("sugar",2,0)],
    notes="Kitchen weekly food supplies requisition — 186 patient meals/day")

print(f"  Created {DepartmentRequisition.objects.count()} requisitions")

# ════════════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ════════════════════════════════════════════════════════════════════════════
print()
print("=" * 70)
print("FULL HOSPITAL INVENTORY SEED COMPLETE")
print("=" * 70)

from apps.inventory.models import BatchStock
expiring_soon  = BatchStock.objects.filter(expiry_date__lte=today+timedelta(days=90), expiry_date__gt=today, quantity_remaining__gt=0, is_quarantined=False)
expired        = BatchStock.objects.filter(expiry_date__lt=today, quantity_remaining__gt=0)
quarantined    = BatchStock.objects.filter(is_quarantined=True)
all_items      = list(InventoryItem.objects.all())
low_stock      = [i for i in all_items if i.current_stock <= i.reorder_level]
consignment    = [i for i in all_items if i.is_consignment]

print(f"  Vendors:           {Vendor.objects.count()}")
print(f"  Inventory Items:   {InventoryItem.objects.count()} items across all departments")
print(f"  Purchase Orders:   {PurchaseOrder.objects.count()} (RECEIVED: {PurchaseOrder.objects.filter(status='RECEIVED').count()}, APPROVED: {PurchaseOrder.objects.filter(status='APPROVED').count()}, SUBMITTED: {PurchaseOrder.objects.filter(status='SUBMITTED').count()}, DRAFT/AUTO: {PurchaseOrder.objects.filter(status='DRAFT').count()})")
print(f"  Batch Records:     {BatchStock.objects.count()} lots tracked")
print(f"  Stock Movements:   {StockMovement.objects.count()} audit entries")
print(f"  Requisitions:      {DepartmentRequisition.objects.count()} (across all wards)")
print()
print(f"  [!] Low Stock Items: {len(low_stock)}")
for i in low_stock: print(f"      - {i.item_code}: {i.name} ({i.current_stock}/{i.reorder_level})")
print(f"  [EXPIRY] Expiring <=90d:  {expiring_soon.count()} batches")
print(f"  [QC] Quarantined:    {quarantined.count()} batch(es)")
print(f"  [CONSIGN] Consignment: {len(consignment)} items (lenses/implants)")
print()
print("  Vendor Performance Rankings:")
for v in sorted(Vendor.objects.all(), key=lambda x: x.on_time_rate or 0, reverse=True):
    rate = f"{v.on_time_rate}%" if v.on_time_rate is not None else "N/A"
    print(f"      {v.performance_rating:10s} — {v.name} ({rate})")
print()
print("  READY FOR FINANCE DIRECTOR DEMO!")
print("=" * 70)
