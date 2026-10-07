#!/usr/bin/env python
"""Fix 2 ERP gaps: link all ServicePrices to sub-categories + seed 12-month budget."""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from apps.billing.models import ServiceSubCategory, ServicePrice, Budget
from apps.accounts.models import User
from decimal import Decimal

admin = User.objects.filter(is_superuser=True).first()

# ────────────────────────────────────────────────────────
# 1. LINK SERVICE PRICES → SUB-CATEGORIES
# ────────────────────────────────────────────────────────
print("=" * 60)
print("  1. LINKING SERVICE PRICES TO SUB-CATEGORIES")
print("=" * 60)

# Build lookup: category → sub-category mappings (by keyword matching)
subs = {sc.id: sc for sc in ServiceSubCategory.objects.filter(is_deleted=False)}

# Map: (price_category, name_keyword_pattern) → sub_category code
# More specific rules first, fallback to category default
RULES = [
    # CONSULT
    ('CONSULT', lambda n: True, 'CON-GEN'),

    # CLINICAL — orthoptic vs general
    ('CLINICAL', lambda n: any(k in n.lower() for k in ['orthop', 'hess', 'muscle', 'cover test', 'binocular', 'strabismus']), 'CLN-ORT'),
    ('CLINICAL', lambda n: True, 'CLN-ORC'),  # default clinical → Orthoptic Cards (clinical tests)

    # INVEST
    ('INVEST', lambda n: True, 'INV-DIA'),

    # LAB
    ('LAB', lambda n: True, 'LAB-GEN'),

    # OPTICAL
    ('OPTICAL', lambda n: any(k in n.lower() for k in ['frame', 'spectacle frame']), 'OPT-FRM'),
    ('OPTICAL', lambda n: any(k in n.lower() for k in ['progressive', 'bifocal', 'single vision', 'photochromic', 'prescription']), 'OPT-LNS'),
    ('OPTICAL', lambda n: any(k in n.lower() for k in ['contact lens']), 'OPT-CTL'),
    ('OPTICAL', lambda n: any(k in n.lower() for k in ['anti-reflect', 'uv400', 'tint', 'coating']), 'OPT-ACC'),
    ('OPTICAL', lambda n: any(k in n.lower() for k in ['sunglasses']), 'OPT-SUN'),
    ('OPTICAL', lambda n: any(k in n.lower() for k in ['reading']), 'OPT-RDG'),
    ('OPTICAL', lambda n: any(k in n.lower() for k in ['clip-on frame']), 'OPT-CLF'),
    ('OPTICAL', lambda n: any(k in n.lower() for k in ['clip-on lens']), 'OPT-CLL'),
    ('OPTICAL', lambda n: any(k in n.lower() for k in ['cleaning', 'solution']), 'OPT-CLN'),
    ('OPTICAL', lambda n: any(k in n.lower() for k in ['case', 'pouch']), 'OPT-CSE'),
    ('OPTICAL', lambda n: any(k in n.lower() for k in ['low vision']), 'OPT-LVD'),
    ('OPTICAL', lambda n: any(k in n.lower() for k in ['repair', 'fitting']), 'OPT-ACC'),
    ('OPTICAL', lambda n: True, 'OPT-LNS'),  # default optical → lenses

    # PHARMACY
    ('PHARMACY', lambda n: any(k in n.lower() for k in ['consumable', 'gauze', 'syringe', 'glove']), 'PHR-CSM'),
    ('PHARMACY', lambda n: True, 'PHR-MED'),

    # SURGICAL
    ('SURGICAL', lambda n: 'cataract' in n.lower(), 'SRG-CAT'),
    ('SURGICAL', lambda n: 'glaucoma' in n.lower() or 'trabeculect' in n.lower(), 'SRG-GLA'),
    ('SURGICAL', lambda n: any(k in n.lower() for k in ['vitreo', 'retinal', 'intravitreal']), 'SRG-VIT'),
    ('SURGICAL', lambda n: any(k in n.lower() for k in ['laser', 'yag']), 'SRG-LAS'),
    ('SURGICAL', lambda n: any(k in n.lower() for k in ['lid', 'oculoplastic', 'chalazion', 'pterygium']), 'SRG-OCU'),
    ('SURGICAL', lambda n: any(k in n.lower() for k in ['cornea']), 'SRG-COR'),
    ('SURGICAL', lambda n: any(k in n.lower() for k in ['strabismus']), 'SRG-OTH'),
    ('SURGICAL', lambda n: any(k in n.lower() for k in ['refract']), 'SRG-REF'),
    ('SURGICAL', lambda n: any(k in n.lower() for k in ['anesth']), 'SRG-ANE'),
    ('SURGICAL', lambda n: True, 'SRG-OTH'),  # default surgical

    # ADMISSION
    ('ADMISSION', lambda n: True, 'ADM-HOS'),

    # REG
    ('REG', lambda n: True, 'REG-FLD'),

    # OTHER
    ('OTHER', lambda n: 'gift' in n.lower(), 'OTH-GFT'),
    ('OTHER', lambda n: True, 'OTH-MED'),
]

# Build code → sub_category lookup
code_to_sub = {}
for sc in subs.values():
    if sc.code:
        code_to_sub[sc.code] = sc

linked = 0
skipped = 0
for sp in ServicePrice.objects.filter(is_deleted=False, sub_category__isnull=True):
    matched = False
    for cat, matcher, sub_code in RULES:
        if sp.category == cat and matcher(sp.name):
            sc = code_to_sub.get(sub_code)
            if sc:
                sp.sub_category = sc
                sp.save(update_fields=['sub_category'])
                linked += 1
                matched = True
                break
    if not matched:
        print(f"  [!] No rule for: {sp.category}|{sp.name}")
        skipped += 1

print(f"  Linked: {linked} prices to sub-categories")
if skipped:
    print(f"  Skipped: {skipped} (no matching rule)")

# Verify
total = ServicePrice.objects.filter(is_deleted=False).count()
with_sub = ServicePrice.objects.filter(is_deleted=False).exclude(sub_category__isnull=True).count()
print(f"  Result: {with_sub}/{total} prices now have sub-categories")

# ────────────────────────────────────────────────────────
# 2. SEED 12-MONTH BUDGET (FY 2026)
# ────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  2. SEEDING 12-MONTH BUDGET (FY 2026)")
print("=" * 60)

YEAR = 2026

# Revenue targets by department (monthly amounts in FCFA)
REVENUE_BUDGETS = [
    ('Consultation', 'Ophthalmology', 3_500_000),
    ('Consultation', 'Internal Medicine', 1_200_000),
    ('Registration', 'Front Desk', 800_000),
    ('Investigation', 'Diagnostics', 4_000_000),
    ('Laboratory', 'Lab', 3_200_000),
    ('Optical Sales', 'Optical Shop', 6_500_000),
    ('Pharmacy Sales', 'Pharmacy', 5_000_000),
    ('Surgery', 'Theatre', 8_000_000),
    ('Admission', 'IPD', 2_500_000),
    ('Other Income', 'Administration', 500_000),
]

# Expense budgets by department (monthly amounts in FCFA)
EXPENSE_BUDGETS = [
    ('Staff Salaries', 'Human Resources', 12_000_000),
    ('Medical Supplies', 'Pharmacy', 3_500_000),
    ('Optical Stock', 'Optical Shop', 4_000_000),
    ('Lab Reagents', 'Lab', 1_800_000),
    ('Surgical Consumables', 'Theatre', 2_000_000),
    ('Utilities', 'Administration', 800_000),
    ('Equipment Maintenance', 'Biomedical', 600_000),
    ('Rent & Lease', 'Administration', 1_500_000),
    ('Insurance', 'Administration', 300_000),
    ('IT & Communications', 'IT', 400_000),
    ('Transport & Fuel', 'Logistics', 350_000),
    ('Cleaning & Hygiene', 'Housekeeping', 250_000),
    ('Marketing & Outreach', 'Administration', 200_000),
    ('Training & CPD', 'Human Resources', 150_000),
    ('Depreciation', 'Finance', 500_000),
]

created = 0
existed = 0

for month in range(1, 13):
    # Revenue
    for category, department, amount in REVENUE_BUDGETS:
        # Seasonal adjustments: Jan/Feb slightly lower, Oct-Dec higher
        factor = Decimal('1.0')
        if month in (1, 2):
            factor = Decimal('0.85')
        elif month in (10, 11, 12):
            factor = Decimal('1.15')
        elif month in (7, 8):  # rainy season dip
            factor = Decimal('0.90')

        adj_amount = (Decimal(str(amount)) * factor).quantize(Decimal('1'))

        obj, is_new = Budget.objects.update_or_create(
            year=YEAR, month=month, budget_type='REVENUE',
            category=category, department=department,
            defaults={
                'budgeted_amount': adj_amount,
                'notes': f'FY{YEAR} monthly revenue target',
                'created_by': admin,
                'updated_by': admin,
            }
        )
        if is_new:
            created += 1
        else:
            existed += 1

    # Expenses
    for category, department, amount in EXPENSE_BUDGETS:
        obj, is_new = Budget.objects.update_or_create(
            year=YEAR, month=month, budget_type='EXPENSE',
            category=category, department=department,
            defaults={
                'budgeted_amount': Decimal(str(amount)),
                'notes': f'FY{YEAR} monthly expense budget',
                'created_by': admin,
                'updated_by': admin,
            }
        )
        if is_new:
            created += 1
        else:
            existed += 1

from django.db.models import Sum
total_budget = Budget.objects.filter(year=YEAR).count()
rev_total = Budget.objects.filter(year=YEAR, budget_type='REVENUE').aggregate(
    s=Sum('budgeted_amount'))['s'] or 0
exp_total = Budget.objects.filter(year=YEAR, budget_type='EXPENSE').aggregate(
    s=Sum('budgeted_amount'))['s'] or 0

print(f"  Created: {created} budget lines")
print(f"  Updated: {existed} existing lines")
print(f"  Total: {total_budget} budget lines for FY{YEAR}")
print(f"  Revenue target: {rev_total:,.0f} FCFA")
print(f"  Expense budget: {exp_total:,.0f} FCFA")
print(f"  Projected surplus: {rev_total - exp_total:,.0f} FCFA")

print("\n" + "=" * 60)
print("  GAPS FIXED!")
print("=" * 60)
