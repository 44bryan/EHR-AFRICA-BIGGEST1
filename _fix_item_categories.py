"""
Fix ServicePrice entries stuck on category='OTHER'.

Strategy (in order of priority):
  1. If the entry has a sub_category FK → use sub_category.category
  2. Keyword match on name → PHARMACY or OPTICAL
  3. Leave as OTHER (nothing matches)

Run: python _fix_item_categories.py
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from apps.billing.models import ServicePrice, ServiceCategory

PHARMACY_KEYWORDS = [
    'tablet', 'capsule', 'syrup', 'injection', 'ampoule', 'vial', 'solution',
    'suspension', 'cream', 'ointment', 'gel', 'drops', 'spray', 'inhaler',
    'patch', 'suppository', 'sachet', 'powder', 'drug', 'medicine', 'pharma',
    'mg', 'ml', 'mcg', 'antibiotic', 'analgesic', 'vitamin', 'vaccine',
    'amoxicillin', 'paracetamol', 'ibuprofen', 'metronidazole', 'ciprofloxacin',
    'dexamethasone', 'prednisolone', 'chloramphenicol', 'tetracycline',
    'atropine', 'tropicamide', 'timolol', 'latanoprost', 'dorzolamide',
    'pilocarpine', 'acetazolamide', 'betaxolol', 'brinzolamide',
    'artificial tear', 'lubricant', 'eye drop', 'ear drop',
]

OPTICAL_KEYWORDS = [
    'frame', 'frames', 'lens', 'lenses', 'glasses', 'spectacle', 'spectacles',
    'contact lens', 'contact lenses', 'sunglasses', 'reading glass',
    'progressive', 'bifocal', 'multifocal', 'single vision', 'tinted',
    'photochromic', 'anti-reflective', 'anti reflective', 'case', 'cord',
    'optical accessory', 'accessories',
]


def classify_by_name(name: str) -> str | None:
    low = name.lower()
    for kw in PHARMACY_KEYWORDS:
        if kw in low:
            return ServiceCategory.PHARMACY
    for kw in OPTICAL_KEYWORDS:
        if kw in low:
            return ServiceCategory.OPTICAL
    return None


qs = ServicePrice.objects.filter(category=ServiceCategory.OTHER, is_deleted=False)
total = qs.count()
print(f"ServicePrice entries with category=OTHER: {total}")

fixed_subcat = 0
fixed_keyword = 0
skipped = 0

for sp in qs.select_related('sub_category'):
    new_cat = None

    # Priority 1: inherit from sub_category
    if sp.sub_category and sp.sub_category.category != ServiceCategory.OTHER:
        new_cat = sp.sub_category.category

    # Priority 2: keyword match
    if not new_cat:
        new_cat = classify_by_name(sp.name)

    if new_cat:
        old = sp.category
        sp.category = new_cat
        sp.save(update_fields=['category'])
        if sp.sub_category:
            fixed_subcat += 1
        else:
            fixed_keyword += 1
        print(f"  [{old} -> {new_cat}] {sp.name}")
    else:
        skipped += 1

print(f"\nResults:")
print(f"  Fixed via sub_category: {fixed_subcat}")
print(f"  Fixed via keyword:      {fixed_keyword}")
print(f"  Still OTHER (no match): {skipped}")
print("Done.")
