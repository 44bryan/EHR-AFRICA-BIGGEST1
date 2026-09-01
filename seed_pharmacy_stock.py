"""
Seed pharmacy drugs + stock from the Excel inventory report.
Source: rptEtatStock_SituationStock AOUT 31-2026.xls

Creates:
  - 2 PharmacyLocation records (FT Pharmacy, General Pharmacy)
  - Drug records for all 419 items
  - DrugStock batch for each item with qty > 0

Usage:
  python manage.py shell < seed_pharmacy_stock.py
  OR on server:
  cd /opt/ehr-africa && venv/bin/python manage.py shell < seed_pharmacy_stock.py
"""
import os, re, sys, datetime
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')

import django
django.setup()

from apps.pharmacy.models import (
    Drug, DrugStock, DrugCategory, DrugForm, PharmacyLocation,
)

# ── 1. Parse the Excel file ─────────────────────────────────────────────
import xlrd

XLS_PATH = '/opt/ehr-africa/rptEtatStock_SituationStock AOUT 31-2026.xls'
wb = xlrd.open_workbook(XLS_PATH)
sheet = wb.sheet_by_index(0)

raw_drugs = []
for r in range(12, sheet.nrows):
    code = str(sheet.cell_value(r, 1)).strip()
    if not code.startswith('PH0'):
        continue
    name = str(sheet.cell_value(r, 2)).strip()
    qty = sheet.cell_value(r, 5)
    cost_stock = sheet.cell_value(r, 6)
    avg_cost = sheet.cell_value(r, 7)
    qty = int(qty) if isinstance(qty, float) else 0
    avg_cost = Decimal(str(round(avg_cost, 2))) if isinstance(avg_cost, (int, float)) and avg_cost else Decimal('0')
    cost_stock = Decimal(str(round(cost_stock, 2))) if isinstance(cost_stock, (int, float)) and cost_stock else Decimal('0')
    raw_drugs.append({
        'code': code,
        'name': name,
        'qty': qty,
        'cost_stock': cost_stock,
        'avg_cost': avg_cost,
    })

print(f"Parsed {len(raw_drugs)} drugs from Excel")

# ── 2. Smart form/strength/unit/category detection ──────────────────────

# Form detection patterns (order matters — first match wins)
FORM_PATTERNS = [
    (r'\bEYE\s*OINT', DrugForm.EYE_OINTMENT, 'tube'),
    (r'\bOINT', DrugForm.CREAM, 'tube'),
    (r'\bPOMMADE', DrugForm.CREAM, 'tube'),
    (r'\bCREME?\b', DrugForm.CREAM, 'tube'),
    (r'\bGEL\b', DrugForm.CREAM, 'tube'),
    (r'\bEYE\s*DROP', DrugForm.EYE_DROP, 'bottle'),
    (r'\bCOLLYRE\b', DrugForm.EYE_DROP, 'bottle'),
    (r'\bCY\b', DrugForm.EYE_DROP, 'bottle'),       # CY = collyre
    (r'\bUNIDOSE\b', DrugForm.EYE_DROP, 'unit'),
    (r'\bNASAL', DrugForm.NASAL_DROP, 'bottle'),
    (r'\bINJ\b', DrugForm.INJECTION, 'ampoule'),
    (r'\bAMP\b', DrugForm.INJECTION, 'ampoule'),
    (r'\bVIAL\b', DrugForm.INJECTION, 'vial'),
    (r'\bSERINGUE\b', DrugForm.INJECTION, 'syringe'),
    (r'\bSIROP\b|\bSP\b|\bSOL\s*BUV', DrugForm.SYRUP, 'bottle'),
    (r'\bSUSP\b', DrugForm.SYRUP, 'bottle'),
    (r'\bSUPPO\b', DrugForm.OTHER, 'suppository'),
    (r'\bCP\b|\bTABLET\b|\bCOMP\b|\bSCHTS\b|\bBLISTER\b', DrugForm.TABLET, 'tablet'),
    (r'\bGELULE\b|\bCAPS?\b|\bCAPSULE\b', DrugForm.CAPSULE, 'capsule'),
    (r'\bFL/', DrugForm.SYRUP, 'bottle'),           # FL/ = flacon
]

# Category detection by drug name keywords
CATEGORY_KEYWORDS = {
    DrugCategory.ANTIBIOTIC: [
        'AMOXICILLIN', 'ACLAV', 'CEFTRIAXONE', 'CEFUROXIME', 'CIPROFLOX',
        'AZITHROMYCIN', 'DOXYCYCLINE', 'METRONIDAZOLE', 'GENTAMICIN',
        'OFLOXACIN', 'MOXIFLOX', 'TOBRAMYCIN', 'NEOMYCIN', 'CHLORAMPHENICOL',
        'ERYTHROMYCIN', 'CLINDAMYCIN', 'LEVOFLOX', 'CEFIXIME', 'RIFAMPICIN',
        'TETRACYCLINE', 'NORFLOX', 'VANCOMYCIN', 'AMPICILLIN', 'PENICILLIN',
        'FLUCLOX', 'CEFOTAXIME', 'SULFAMETH', 'COTRIMOX', 'NITROFURAN',
        'FUCIDIN', 'FUCITHALMIC', 'VIGAMOX', 'TOBREX', 'ZYMAR', 'CILOXAN',
    ],
    DrugCategory.ANTIFUNGAL: [
        'FLUCONAZOLE', 'NYSTATIN', 'KETOCONAZOLE', 'ITRACONAZOLE',
        'CLOTRIMAZOLE', 'MICONAZOLE', 'ECONAZOLE', 'FUNGIZONE',
        'MYCOSTER', 'NATAMYCIN',
    ],
    DrugCategory.ANTIVIRAL: [
        'ACYCLOVIR', 'VALACYCLOVIR', 'ZELITREX', 'GANCICLOVIR',
        'OSELTAMIVIR', 'TENOFOVIR', 'EFAVIRENZ', 'ZIDOVUDINE',
    ],
    DrugCategory.GLAUCOMA: [
        'TIMOLOL', 'LATANOPROST', 'TRAVOPROST', 'BIMATOPROST',
        'DORZOLAMIDE', 'BRIMONIDINE', 'PILOCARPINE', 'ACETAZOLAMIDE',
        'XALATAN', 'LUMIGAN', 'TRAVATAN', 'AZOPT', 'COSOPT', 'COMBIGAN',
        'ALPHAGAN', 'BETOPTIC', 'TRUSOPT', 'DIAMOX', 'MANNITOL',
    ],
    DrugCategory.STEROID: [
        'DEXAMETHASONE', 'PREDNISOLONE', 'PREDNISONE', 'BETAMETHASONE',
        'HYDROCORTISONE', 'TRIAMCINOLONE', 'FLUOCINOLONE', 'FLUOROMETHOLONE',
        'MAXIDEX', 'FLAREX', 'LOTEMAX', 'TOBRADEX', 'CELESTENE',
        'SOLUPRED', 'CORTISONE', 'DEPOMEDROL', 'KENACORT', 'SOLUMEDROL',
    ],
    DrugCategory.NSAID: [
        'DICLOFENAC', 'IBUPROFEN', 'KETOROLAC', 'NEPAFENAC', 'BROMFENAC',
        'FLURBIPROFEN', 'INDOMETACIN', 'PIROXICAM', 'KETOPROFEN',
        'NEVANAC', 'VOLTAREN', 'PROFENID', 'FELDENE',
    ],
    DrugCategory.MYDRIATIC: [
        'TROPICAMIDE', 'ATROPINE', 'CYCLOPENTOLATE', 'PHENYLEPHRINE',
        'MYDRIATICUM', 'NEOSYNEPHRINE', 'HOMATROPINE', 'MYDRIACYL',
    ],
    DrugCategory.LUBRICANT: [
        'ARTIFICIAL TEAR', 'HYPROMELLOSE', 'CARBOXYMETHYL', 'REFRESH',
        'SYSTANE', 'OPTIVE', 'CELLUVISC', 'LACRYVISC', 'LACRINORM',
        'HYABAK', 'THEALOZ', 'ARTELAC', 'SICCAFLUID', 'GENTEAL',
        'LUBRICANT', 'LARME', 'TEAR', 'LACRIGEL',
    ],
    DrugCategory.ANAESTHETIC: [
        'LIDOCAINE', 'TETRACAINE', 'PROPARACAINE', 'BUPIVACAINE',
        'OXYBUPROCAINE', 'XYLOCAINE', 'MARCAINE',
    ],
    DrugCategory.VITAMIN: [
        'VITAMIN', 'VITAMINE', 'FOLIC', 'IRON', 'ZINC', 'CALCIUM',
        'ASCORBIC', 'RETINOL', 'TOCOPHEROL', 'FERROUS',
    ],
    DrugCategory.ANALGESIC: [
        'PARACETAMOL', 'TRAMADOL', 'CODEINE', 'MORPHINE', 'DOLIPRANE',
        'EFFERALGAN', 'DAFALGAN', 'ACUMOL', 'NOVALGIN', 'PETHIDINE',
        'FENTANYL',
    ],
    DrugCategory.ANTIHYPERTENSIVE: [
        'AMLODIPINE', 'NIFEDIPINE', 'ENALAPRIL', 'LISINOPRIL', 'LOSARTAN',
        'VALSARTAN', 'ATENOLOL', 'PROPRANOLOL', 'BISOPROLOL', 'RAMIPRIL',
        'CAPTOPRIL', 'PERINDOPRIL', 'AFRIDIPINE',
    ],
    DrugCategory.ANTIDIABETIC: [
        'METFORMIN', 'GLIBENCLAMIDE', 'GLICLAZIDE', 'INSULIN', 'GLUCOPHAGE',
        'DAONIL', 'DIAMICRON', 'JANUVIA', 'SITAGLIPTIN',
    ],
}

# Strength extraction pattern: looks for patterns like 250MG, 0.5%, 1G, 100/12.5MG
STRENGTH_RE = re.compile(
    r'(\d+[,.]?\d*\s*/\s*\d+[,.]?\d*\s*(?:MG|G|ML|MCG|%|UI|IU|MG/ML))'
    r'|(\d+[,.]?\d*\s*(?:MG|G|ML|MCG|%|UI|IU|MG/ML))',
    re.IGNORECASE
)


def detect_form(name):
    for pattern, form_val, unit in FORM_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return form_val, unit
    return DrugForm.OTHER, 'unit'


def detect_category(name):
    upper = name.upper()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in upper:
                return cat
    return DrugCategory.OTHER


def extract_strength(name):
    m = STRENGTH_RE.search(name)
    if m:
        return (m.group(1) or m.group(2)).strip().replace(',', '.')
    return ''


def extract_generic(name):
    """Try to get a clean generic name from the raw Excel name."""
    # Remove strength, form abbreviations, packaging info
    clean = name.upper()
    # Remove batch/packaging info like B/12, B/24, B/10, FL/5ML, etc.
    clean = re.sub(r'\bB/\d+\b', '', clean)
    clean = re.sub(r'\bFL/\d+\s*ML\b', '', clean)
    clean = re.sub(r'\bEN/\d+\s*ML\b', '', clean)
    clean = re.sub(r'\bF/\d+\s*ML\b', '', clean)
    clean = re.sub(r'\b\d+\s*X\s*\d+\b', '', clean)
    # Remove strength
    clean = STRENGTH_RE.sub('', clean)
    # Remove form abbreviations
    for abbr in ['CP', 'COMP', 'TABLET', 'SCHTS', 'BLISTER', 'AMP', 'INJ',
                 'VIAL', 'FL', 'CY', 'GEL', 'SUPPO', 'SP', 'GELULE',
                 'SOL BUV', 'SIROP', 'UNIDOSE', 'COLLYRE', 'POMMADE',
                 'CREME', 'EYE OINTMENT', 'EYE DROP', 'CAPS', 'ENFT',
                 'PUR', 'SERINGUE', 'UBI', 'NASAL']:
        clean = re.sub(r'\b' + abbr + r'\b', '', clean)
    # Clean up
    clean = re.sub(r'\s+', ' ', clean).strip(' /-')
    return clean.title() if clean else name


# ── 3. Create Pharmacy Locations ────────────────────────────────────────
ft_loc, _ = PharmacyLocation.objects.get_or_create(
    name='FT Pharmacy',
    defaults={
        'location_type': 'OUTPATIENT',
        'address': 'Front desk / outpatient dispensing point',
        'is_active': True,
    }
)
gen_loc, _ = PharmacyLocation.objects.get_or_create(
    name='General Pharmacy',
    defaults={
        'location_type': 'MAIN',
        'address': 'Main pharmacy store — PHARMACY STORE (PH02)',
        'is_active': True,
    }
)
print(f"Locations: FT Pharmacy (id={ft_loc.pk}), General Pharmacy (id={gen_loc.pk})")

# ── 4. Import Drugs + Stock ─────────────────────────────────────────────
created = 0
updated = 0
stock_created = 0
today = datetime.date.today()
# Default expiry: 2 years from now (placeholder since Excel doesn't have expiry)
default_expiry = today + datetime.timedelta(days=730)

for item in raw_drugs:
    name = item['name']
    form_val, unit = detect_form(name)
    category = detect_category(name)
    strength = extract_strength(name)
    generic = extract_generic(name)

    # Try to find existing drug by exact name match
    drug, was_created = Drug.objects.get_or_create(
        name=name,
        defaults={
            'generic_name': generic,
            'category': category,
            'form': form_val,
            'strength': strength,
            'unit': unit,
            'cost_price': item['avg_cost'],
            'selling_price': (item['avg_cost'] * Decimal('1.35')).quantize(Decimal('0.01')) if item['avg_cost'] else Decimal('0'),
            'reorder_level': 10,
            'requires_prescription': True,
            'location': gen_loc,  # Default to General Pharmacy
            'barcode': item['code'],  # PH01xxx as barcode
        }
    )

    if was_created:
        created += 1
    else:
        # Update cost if we have new data
        if item['avg_cost'] and drug.cost_price == 0:
            drug.cost_price = item['avg_cost']
            drug.selling_price = (item['avg_cost'] * Decimal('1.35')).quantize(Decimal('0.01'))
            drug.save(update_fields=['cost_price', 'selling_price'])
        updated += 1

    # Create stock batch if qty > 0
    if item['qty'] > 0:
        # Check if we already have a batch for this import
        batch_num = f"INIT-{item['code']}-{today.strftime('%Y%m')}"
        batch, batch_created = DrugStock.objects.get_or_create(
            drug=drug,
            batch_number=batch_num,
            defaults={
                'expiry_date': default_expiry,
                'quantity_received': item['qty'],
                'quantity_remaining': item['qty'],
                'purchase_price': item['avg_cost'],
                'received_date': today,
                'supplier': 'Initial Stock Import (Aug 2026)',
                'notes': f"Imported from inventory report. Total cost: {item['cost_stock']} FCFA",
            }
        )
        if batch_created:
            stock_created += 1

print(f"\nDone!")
print(f"  Drugs created: {created}")
print(f"  Drugs already existed: {updated}")
print(f"  Stock batches created: {stock_created}")
print(f"  Total drugs in formulary: {Drug.objects.filter(is_deleted=False).count()}")
print(f"  Total stock batches: {DrugStock.objects.filter(is_deleted=False).count()}")
print(f"  Default location: General Pharmacy")
print(f"  Selling price markup: 35% over cost price")
print(f"  Default expiry: {default_expiry} (placeholder — update with real batch expiry dates)")
