"""
Rename all 35 service families with professional ERP names
and a clean alphanumeric coding scheme (OPT-FRM, SRG-CAT, etc.)

Run: python manage.py shell < _rename_families.py
"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from apps.billing.models import ServiceSubCategory

print("=" * 60)
print("RENAMING SERVICE FAMILIES")
print("=" * 60)

# (old_name, new_code, new_name)
renames = [
    # ── OPTICAL ──
    ('CBP Lenses',             'OPT-CBP',  'Corrective Ophthalmic Lenses'),
    ('Lens Cases',             'OPT-CSE',  'Eyewear Cases & Pouches'),
    ('Accessories',            'OPT-ACC',  'Optical Accessories'),
    ('Reading Glasses',        'OPT-RDG',  'Prescription Reading Glasses'),
    ('Ready to Clip Frames',   'OPT-CLF',  'Clip-On Frames'),
    ('Sunglasses',             'OPT-SUN',  'Prescription & Fashion Sunglasses'),
    ('Ready to Clip Lenses',   'OPT-CLL',  'Clip-On Lenses'),
    ('Liquid Lens Cleaner',    'OPT-CLN',  'Lens Cleaning Solutions'),
    ('Lenses',                 'OPT-LNS',  'Ophthalmic Lenses'),
    ('Frames',                 'OPT-FRM',  'Eyeglass Frames'),
    ('Low Vision Devices',     'OPT-LVD',  'Low Vision Aids & Devices'),
    ('Contact Lens',           'OPT-CTL',  'Contact Lenses'),

    # ── SURGICAL ──
    ('Anesthesia',             'SRG-ANE',  'Surgical Anesthesia'),
    ('Cataract Surgery',       'SRG-CAT',  'Cataract Procedures'),
    ('Cornea Surgery',         'SRG-COR',  'Corneal Procedures'),
    ('Glaucoma Surgery',       'SRG-GLA',  'Glaucoma Procedures'),
    ('Laser Treatment',        'SRG-LAS',  'Laser Therapy & Photocoagulation'),
    ('Oculoplastic Surgery',   'SRG-OCU',  'Oculoplastic & Reconstructive'),
    ('Other Surgeries',        'SRG-OTH',  'General Ophthalmic Surgery'),
    ('Refractive Surgeries',   'SRG-REF',  'Refractive & Vision Correction'),
    ('Vitreoretinal Surgery',  'SRG-VIT',  'Vitreoretinal Procedures'),

    # ── CONSULTATION ──
    ('Consultation',           'CON-GEN',  'General Eye Consultation'),
    ('Internist Consultation', 'CON-INT',  'Internal Medicine Consultation'),

    # ── CLINICAL / INVESTIGATION ──
    ('Investigation',          'INV-DIA',  'Diagnostic Investigations'),
    ('Orthoptics',             'CLN-ORT',  'Orthoptic Assessment & Therapy'),
    ('Orthoptics Cards',       'CLN-ORC',  'Orthoptic Testing Cards'),

    # ── LABORATORY ──
    ('Laboratory',             'LAB-GEN',  'Laboratory Analysis'),

    # ── PHARMACY ──
    ('Medications',            'PHR-MED',  'Pharmaceutical Products'),
    ('Consumables',            'PHR-CSM',  'Medical Consumables & Disposables'),

    # ── ADMISSION ──
    ('Hospitalization',        'ADM-HOS',  'Inpatient Hospitalization'),

    # ── REGISTRATION ──
    ('Patient Folder',         'REG-FLD',  'Patient File & Registration'),

    # ── OTHER ──
    ('Non-Medical Stock',      'OTH-NMS',  'Non-Medical Supplies'),
    ('Other Medical Services', 'OTH-MED',  'Miscellaneous Clinical Services'),
    ('Sundry Income',          'OTH-SUN',  'Sundry & Miscellaneous Income'),
    ('Gift Bags',              'OTH-GFT',  'Promotional Items & Gift Packs'),
]

updated = 0
not_found = 0
for old_name, new_code, new_name in renames:
    try:
        sc = ServiceSubCategory.objects.get(name=old_name, is_deleted=False)
        sc.code = new_code
        sc.name = new_name
        sc.save(update_fields=['code', 'name', 'updated_at'])
        updated += 1
        print(f"  {old_name:30s} -> [{new_code}] {new_name}")
    except ServiceSubCategory.DoesNotExist:
        not_found += 1
        print(f"  SKIP: {old_name} (not found)")

print(f"\nRenamed: {updated}, Not found: {not_found}")
print(f"Total active families: {ServiceSubCategory.objects.filter(is_deleted=False).count()}")
print("Done!")
