"""
Rename families - handles unique constraint conflicts by deleting old soft-deleted entries first.
Run: python manage.py shell < _rename_families2.py
"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from apps.billing.models import ServiceSubCategory

print("=" * 60)
print("RENAMING SERVICE FAMILIES (v2)")
print("=" * 60)

# First hard-delete all soft-deleted entries to avoid unique conflicts
deleted = ServiceSubCategory.objects.filter(is_deleted=True).delete()
print(f"Cleaned up {deleted[0]} soft-deleted entries\n")

renames = [
    # ── OPTICAL ──
    ('Corrective Ophthalmic Lenses', 'OPT-CBP', 'OPT-CBP',  'Corrective Ophthalmic Lenses'),  # already renamed
    ('Eyewear Cases & Pouches',      'OPT-CSE', 'OPT-CSE',  'Eyewear Cases & Pouches'),
    ('Optical Accessories',          'OPT-ACC', 'OPT-ACC',  'Optical Accessories'),
    ('Prescription Reading Glasses', 'OPT-RDG', 'OPT-RDG',  'Prescription Reading Glasses'),
    ('Clip-On Frames',               'OPT-CLF', 'OPT-CLF',  'Clip-On Frames'),
    ('Prescription & Fashion Sunglasses', 'OPT-SUN', 'OPT-SUN', 'Prescription & Fashion Sunglasses'),
    ('Clip-On Lenses',               'OPT-CLL', 'OPT-CLL',  'Clip-On Lenses'),
    ('Lens Cleaning Solutions',      'OPT-CLN', 'OPT-CLN',  'Lens Cleaning Solutions'),
    ('Ophthalmic Lenses',            'OPT-LNS', 'OPT-LNS',  'Ophthalmic Lenses'),
    ('Eyeglass Frames',              'OPT-FRM', 'OPT-FRM',  'Eyeglass Frames'),
    ('Low Vision Aids & Devices',    'OPT-LVD', 'OPT-LVD',  'Low Vision Aids & Devices'),
    # These still need renaming (script crashed before reaching them)
    ('Contact Lens',                 'CTL',     'OPT-CTL',  'Contact Lenses & Solutions'),
    ('Anesthesia',                   'ANE',     'SRG-ANE',  'Surgical Anesthesia'),
    ('Cataract Surgery',             'CAT',     'SRG-CAT',  'Cataract Procedures'),
    ('Cornea Surgery',               'COR',     'SRG-COR',  'Corneal Procedures'),
    ('Glaucoma Surgery',             'GLA',     'SRG-GLA',  'Glaucoma Procedures'),
    ('Laser Treatment',              'LAS',     'SRG-LAS',  'Laser Therapy & Photocoagulation'),
    ('Oculoplastic Surgery',         'OCU',     'SRG-OCU',  'Oculoplastic & Reconstructive'),
    ('Other Surgeries',              'OTH',     'SRG-OTH',  'General Ophthalmic Surgery'),
    ('Refractive Surgeries',         'RES',     'SRG-REF',  'Refractive & Vision Correction'),
    ('Vitreoretinal Surgery',        'VIT',     'SRG-VIT',  'Vitreoretinal Procedures'),
    ('Consultation',                 'CON',     'CON-GEN',  'General Eye Consultation'),
    ('Internist Consultation',       'INT',     'CON-INT',  'Internal Medicine Consultation'),
    ('Investigation',                'INV',     'INV-DIA',  'Diagnostic Investigations'),
    ('Orthoptics',                   'ORT',     'CLN-ORT',  'Orthoptic Assessment & Therapy'),
    ('Orthoptics Cards',             'OTC',     'CLN-ORC',  'Orthoptic Testing Materials'),
    ('Laboratory',                   'LAB',     'LAB-GEN',  'Laboratory Analysis'),
    ('Medications',                  'MED',     'PHR-MED',  'Pharmaceutical Products'),
    ('Consumables',                  'CSM',     'PHR-CSM',  'Medical Consumables & Disposables'),
    ('Hospitalization',              'HOS',     'ADM-HOS',  'Inpatient Hospitalization'),
    ('Patient Folder',               'PF001',   'REG-FLD',  'Patient File & Registration'),
    ('Non-Medical Stock',            'NMS',     'OTH-NMS',  'Non-Medical Supplies'),
    ('Other Medical Services',       'OMS',     'OTH-MED',  'Miscellaneous Clinical Services'),
    ('Sundry Income',                'SUN',     'OTH-SUN',  'Sundry & Miscellaneous Income'),
    ('Gift Bags',                    'GB01',    'OTH-GFT',  'Promotional Items & Gift Packs'),
]

updated = 0
skipped = 0
for old_name, old_code, new_code, new_name in renames:
    # Try to find by old name first, then by old code
    sc = ServiceSubCategory.objects.filter(name=old_name, is_deleted=False).first()
    if not sc:
        sc = ServiceSubCategory.objects.filter(code=old_code, is_deleted=False).first()
    if sc:
        sc.code = new_code
        sc.name = new_name
        sc.save(update_fields=['code', 'name', 'updated_at'])
        updated += 1
        print(f"  [{new_code:8s}] {new_name}")
    else:
        skipped += 1
        print(f"  SKIP: {old_name} / {old_code}")

print(f"\nRenamed: {updated}, Skipped: {skipped}")
print(f"Total active families: {ServiceSubCategory.objects.filter(is_deleted=False).count()}")
print("\nDone!")
