"""
Seed complete Stock Operation Types for a full hospital ERP.
Covers: Pharmacy, Optical, Surgery, Lab, Radiology, Outreach, IPD, CSSD, Admin.
Each type linked to correct OHADA SYSCEBNL GL accounts.
"""
import sys, os, django
sys.path.insert(0, "/opt/ehr-africa")
os.environ["DJANGO_SETTINGS_MODULE"] = "ehr_project.settings.base"
django.setup()

from apps.billing.models import StockOperationType, GLAccount
from apps.accounts.models import User

admin = User.objects.filter(is_superuser=True).first()

# Cache all GL accounts
acct_map = {}
for a in GLAccount.objects.filter(is_deleted=False):
    acct_map[a.code] = a

def get(code):
    """Get GL account, try exact then prefix match."""
    if code in acct_map:
        return acct_map[code]
    for k, v in acct_map.items():
        if k.startswith(code):
            return v
    print(f"  WARNING: No account for {code}")
    return None

# ══════════════════════════════════════════════════════════════════════
# STOCK ENTRIES (ENTREES)
# ══════════════════════════════════════════════════════════════════════

entries = [
    # General
    ("EN-ACH", "Purchase Entry (Achat)", "311000", "603100",
     "Goods received from supplier purchase order - Dr Stock / Cr Variation"),
    ("EN-TRF", "Transfer In (Transfert Recu)", "311000", "311000",
     "Inter-store or inter-department transfer received"),
    ("EN-RET", "Return to Stock (Retour)", "311000", "603100",
     "Items returned to stock from ward, patient, or dispensary"),
    ("EN-DON", "Donation Received (Don Recu)", "311000", "758200",
     "Goods donated by NGO, partner, or benefactor - Dr Stock / Cr Exceptional Income"),
    ("EN-AJP", "Adjustment Surplus (Ajustement +)", "311000", "603100",
     "Stocktake found more than expected - positive adjustment"),

    # Pharmacy specific
    ("EN-PHR", "Pharmacy Purchase", "321000", "603109",
     "Medication and pharmaceutical supplies received - Dr Pharmacy Stock / Cr CoS Medication"),
    ("EN-CON", "Consumables Purchase", "321000", "603110",
     "Medical consumables received (gloves, syringes, etc.) - Dr Stock / Cr CoS Consumables"),
    ("EN-PRT", "Pharmacy Return", "321000", "603109",
     "Medication returned from ward or patient back to pharmacy"),

    # Optical specific
    ("EN-FRM", "Frame Purchase", "311001", "603100",
     "Optical frames received from supplier - Dr Frame Stock / Cr CoS Frames"),
    ("EN-LNS", "Lens Purchase", "311002", "603101",
     "Optical lenses received from supplier - Dr Lens Stock / Cr CoS Lenses"),
    ("EN-ACC", "Accessories Purchase", "311000", "603106",
     "Optical accessories received (cases, cleaners, etc.)"),
    ("EN-LVD", "Low Vision Devices", "311000", "603108",
     "Low vision devices received from supplier"),

    # Surgery / Theatre
    ("EN-SRG", "Surgical Supplies", "321000", "603110",
     "Surgical consumables received (sutures, IOLs, drapes, etc.)"),
    ("EN-ANS", "Anaesthesia Supplies", "321000", "603110",
     "Anaesthesia drugs and consumables received"),

    # Lab
    ("EN-LAB", "Lab Reagents & Supplies", "321000", "603110",
     "Laboratory reagents, kits, and consumables received"),

    # CSSD
    ("EN-CSD", "CSSD Supplies", "321000", "603110",
     "Sterilization supplies, packaging, indicators received"),

    # Admin / Office
    ("EN-OFC", "Office Supplies", "321000", "603401",
     "Office stationery, printing supplies received - Dr Stock / Cr CoS Office"),
    ("EN-CLN", "Cleaning Supplies", "321000", "604300",
     "Cleaning and hygiene products received"),

    # Maintenance
    ("EN-MNT", "Maintenance Parts", "321000", "603402",
     "Spare parts, maintenance materials received"),

    # Production (for optical lab)
    ("EN-WIP", "Work in Progress Entry", "311000", "603100",
     "Semi-finished lenses or frames entering production pipeline"),
]

# ══════════════════════════════════════════════════════════════════════
# STOCK EXITS (SORTIES)
# ══════════════════════════════════════════════════════════════════════

exits = [
    # General
    ("EX-CON", "Consumption (Consommation)", "603100", "311000",
     "Internal consumption by department - Dr Variation / Cr Stock"),
    ("EX-VTE", "Sale Exit (Sortie Vente)", "603100", "311000",
     "Stock exit linked to patient sale - Dr Variation / Cr Stock"),
    ("EX-DIS", "Disposal (Mise au Rebut)", "659000", "311000",
     "Expired, damaged, or unfit stock destroyed - Dr Exceptional Loss / Cr Stock"),
    ("EX-DON", "Donation Given (Don Donne)", "658000", "311000",
     "Stock donated to outreach, charity, or partner - Dr Exceptional Charge / Cr Stock"),
    ("EX-PER", "Loss / Pilferage (Perte)", "659000", "311000",
     "Stolen, missing, or unaccounted stock - Dr Exceptional Loss / Cr Stock"),
    ("EX-AJU", "Adjustment Shortage (Ajustement -)", "658000", "311000",
     "Stocktake found less than expected - negative adjustment"),
    ("EX-TRF", "Transfer Out (Transfert Envoye)", "311000", "311000",
     "Inter-store or inter-department transfer sent out"),
    ("EX-SAM", "Sample / Demo", "658000", "311000",
     "Free samples given to doctors or for demonstration"),
    ("EX-EXP", "Expired Write-off", "659000", "311000",
     "Stock written off due to expiry date passed"),

    # Pharmacy specific
    ("EX-DSP", "Pharmacy Dispensing", "603109", "321000",
     "Medication dispensed to patient - Dr CoS Medication / Cr Pharmacy Stock"),
    ("EX-WRD", "Ward Issue", "603110", "321000",
     "Consumables issued to ward/IPD for patient care"),
    ("EX-EMG", "Emergency Issue", "603110", "321000",
     "Emergency stock issue without prior requisition"),
    ("EX-PRE", "Prescription Fill", "603109", "321000",
     "Outpatient prescription filled and dispensed"),

    # Optical specific
    ("EX-OPT", "Optical Sale Exit", "603100", "311001",
     "Frames sold to patient - Dr CoS Frames / Cr Frame Stock"),
    ("EX-LNS", "Lens Sale Exit", "603101", "311002",
     "Lenses sold/fitted for patient - Dr CoS Lenses / Cr Lens Stock"),
    ("EX-OPR", "Optical Repair Consumption", "603106", "311000",
     "Parts used for optical repairs"),

    # Surgery / Theatre
    ("EX-THR", "Theatre Consumption", "603110", "321000",
     "Surgical consumables used during operation (IOLs, sutures, drapes)"),
    ("EX-ANS", "Anaesthesia Consumption", "603110", "321000",
     "Anaesthesia drugs used during procedure"),
    ("EX-IMP", "Implant Used", "603110", "321000",
     "Surgical implant (IOL, stent, etc.) used in patient"),

    # Lab
    ("EX-LAB", "Lab Reagent Usage", "603110", "321000",
     "Reagents and test kits consumed for investigations"),

    # CSSD
    ("EX-CSD", "CSSD Consumption", "603110", "321000",
     "Sterilization supplies consumed in CSSD processing"),

    # Outreach
    ("EX-OUT", "Outreach Issue", "603109", "321000",
     "Stock issued for community outreach / mobile clinic"),
    ("EX-SCR", "Screening Camp Issue", "603110", "321000",
     "Consumables used at screening camp"),

    # Admin / Office
    ("EX-OFC", "Office Consumption", "603401", "321000",
     "Office supplies consumed (paper, toner, stationery)"),
    ("EX-CLN", "Cleaning Consumption", "604300", "321000",
     "Cleaning products consumed"),

    # Maintenance
    ("EX-MNT", "Maintenance Consumption", "603402", "321000",
     "Spare parts and materials used for repairs"),
]

# ══════════════════════════════════════════════════════════════════════
# CREATE ALL
# ══════════════════════════════════════════════════════════════════════

created = 0
updated = 0
skipped = 0

for code, name, dr_code, cr_code, desc in entries:
    dr_acct = get(dr_code)
    cr_acct = get(cr_code)
    if not dr_acct or not cr_acct:
        print(f"  SKIP {code}: missing account(s)")
        skipped += 1
        continue
    obj, was_created = StockOperationType.objects.get_or_create(
        code=code,
        defaults={
            "name": name, "category": "ENTRY",
            "debit_account": dr_acct, "credit_account": cr_acct,
            "description": desc, "created_by": admin,
        }
    )
    if was_created:
        created += 1
        print(f"  + ENTRY {code:8s} {name:35s} Dr {dr_code} / Cr {cr_code}")
    else:
        # Update existing with better description if needed
        if obj.description != desc:
            obj.description = desc
            obj.save(update_fields=["description", "updated_at"])
            updated += 1
        print(f"  = EXISTS {code}")

for code, name, dr_code, cr_code, desc in exits:
    dr_acct = get(dr_code)
    cr_acct = get(cr_code)
    if not dr_acct or not cr_acct:
        print(f"  SKIP {code}: missing account(s)")
        skipped += 1
        continue
    obj, was_created = StockOperationType.objects.get_or_create(
        code=code,
        defaults={
            "name": name, "category": "EXIT",
            "debit_account": dr_acct, "credit_account": cr_acct,
            "description": desc, "created_by": admin,
        }
    )
    if was_created:
        created += 1
        print(f"  + EXIT  {code:8s} {name:35s} Dr {dr_code} / Cr {cr_code}")
    else:
        if obj.description != desc:
            obj.description = desc
            obj.save(update_fields=["description", "updated_at"])
            updated += 1
        print(f"  = EXISTS {code}")

total = StockOperationType.objects.filter(is_deleted=False).count()
print(f"\nCreated: {created}, Updated: {updated}, Skipped: {skipped}")
print(f"Total stock operation types in system: {total}")
print("Done!")
