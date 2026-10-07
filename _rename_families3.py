"""
Rename families - keep simple, clear, same meaning as TurboClinic but reworded.
Run: python manage.py shell < _rename_families3.py
"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from apps.billing.models import ServiceSubCategory

print("=" * 60)
print("RENAMING FAMILIES (Simple & Clear)")
print("=" * 60)

# (current_name, new_code, new_name)
# Keep same meaning, just rephrase to avoid exact copy
renames = [
    # ── OPTICAL ──
    # TurboClinic: CBP Lenses → ours: Branded Lenses
    ('Corrective Ophthalmic Lenses', 'OPT-CBP',  'Branded Lenses'),
    # TurboClinic: Lens Cases → ours: Lens Cases & Pouches
    ('Eyewear Cases & Pouches',      'OPT-CSE',  'Lens Cases & Pouches'),
    # TurboClinic: Accessories → ours: Optical Accessories
    ('Optical Accessories',          'OPT-ACC',  'Optical Accessories'),
    # TurboClinic: Reading Glasses → ours: Reading Glasses
    ('Prescription Reading Glasses', 'OPT-RDG',  'Reading Glasses'),
    # TurboClinic: Ready to clip Frames → ours: Clip-On Frames
    ('Clip-On Frames',               'OPT-CLF',  'Clip-On Frames'),
    # TurboClinic: Sunglasses → ours: Sunglasses
    ('Prescription & Fashion Sunglasses', 'OPT-SUN', 'Sunglasses'),
    # TurboClinic: Ready to clip Lenses → ours: Clip-On Lenses
    ('Clip-On Lenses',               'OPT-CLL',  'Clip-On Lenses'),
    # TurboClinic: Liquid Lens Cleaner → ours: Lens Cleaning Products
    ('Lens Cleaning Solutions',      'OPT-CLN',  'Lens Cleaning Products'),
    # TurboClinic: Lenses → ours: Prescription Lenses
    ('Ophthalmic Lenses',            'OPT-LNS',  'Prescription Lenses'),
    # TurboClinic: Frames → ours: Eyeglass Frames
    ('Eyeglass Frames',              'OPT-FRM',  'Eyeglass Frames'),
    # TurboClinic: Low Vision Devices → ours: Low Vision Aids
    ('Low Vision Aids & Devices',    'OPT-LVD',  'Low Vision Aids'),
    # TurboClinic: Contact Lens → ours: Contact Lenses
    ('Contact Lenses & Solutions',   'OPT-CTL',  'Contact Lenses'),

    # ── SURGICAL ──
    # TurboClinic: Anesthesia → ours: Anesthesia Services
    ('Surgical Anesthesia',          'SRG-ANE',  'Anesthesia Services'),
    # TurboClinic: Cataract Surgery → ours: Cataract Surgery
    ('Cataract Procedures',          'SRG-CAT',  'Cataract Surgery'),
    # TurboClinic: Cornea Surgery → ours: Corneal Surgery
    ('Corneal Procedures',           'SRG-COR',  'Corneal Surgery'),
    # TurboClinic: Glaucoma Surgery → ours: Glaucoma Surgery
    ('Glaucoma Procedures',          'SRG-GLA',  'Glaucoma Surgery'),
    # TurboClinic: Laser Treatment → ours: Laser Treatment
    ('Laser Therapy & Photocoagulation', 'SRG-LAS', 'Laser Treatment'),
    # TurboClinic: Oculoplastic Surgery → ours: Oculoplastic Surgery
    ('Oculoplastic & Reconstructive', 'SRG-OCU', 'Oculoplastic Surgery'),
    # TurboClinic: Other Surgeries → ours: Other Surgeries
    ('General Ophthalmic Surgery',   'SRG-OTH',  'Other Surgeries'),
    # TurboClinic: Refractive Surgeries → ours: Refractive Surgery
    ('Refractive & Vision Correction', 'SRG-REF', 'Refractive Surgery'),
    # TurboClinic: Vitreoretinal Surgery → ours: Vitreoretinal Surgery
    ('Vitreoretinal Procedures',     'SRG-VIT',  'Vitreoretinal Surgery'),

    # ── CONSULTATION ──
    # TurboClinic: Consultation → ours: Eye Consultation
    ('General Eye Consultation',     'CON-GEN',  'Eye Consultation'),
    # TurboClinic: Internist Consultation → ours: Internal Medicine
    ('Internal Medicine Consultation', 'CON-INT', 'Internal Medicine'),

    # ── CLINICAL / INVESTIGATIONS ──
    # TurboClinic: Investigation → ours: Diagnostic Tests
    ('Diagnostic Investigations',    'INV-DIA',  'Diagnostic Tests'),
    # TurboClinic: Orthoptics → ours: Orthoptic Services
    ('Orthoptic Assessment & Therapy', 'CLN-ORT', 'Orthoptic Services'),
    # TurboClinic: Orthoptics Cards → ours: Orthoptic Cards
    ('Orthoptic Testing Materials',  'CLN-ORC',  'Orthoptic Cards'),

    # ── LAB ──
    # TurboClinic: Laboratory → ours: Lab Tests
    ('Laboratory Analysis',          'LAB-GEN',  'Lab Tests'),

    # ── PHARMACY ──
    # TurboClinic: Medications → ours: Medications
    ('Pharmaceutical Products',      'PHR-MED',  'Medications'),
    # TurboClinic: Consumables → ours: Medical Consumables
    ('Medical Consumables & Disposables', 'PHR-CSM', 'Medical Consumables'),

    # ── ADMISSION ──
    # TurboClinic: Hospitalization → ours: Hospitalization
    ('Inpatient Hospitalization',    'ADM-HOS',  'Hospitalization'),

    # ── REGISTRATION ──
    # TurboClinic: Patient Folder → ours: Patient Registration
    ('Patient File & Registration',  'REG-FLD',  'Patient Registration'),

    # ── OTHER ──
    # TurboClinic: Non-Medical Stock → ours: Non-Medical Items
    ('Non-Medical Supplies',         'OTH-NMS',  'Non-Medical Items'),
    # TurboClinic: Other Medical Services → ours: Other Services
    ('Miscellaneous Clinical Services', 'OTH-MED', 'Other Services'),
    # TurboClinic: Sundry Income → ours: Miscellaneous Income
    ('Sundry & Miscellaneous Income', 'OTH-SUN', 'Miscellaneous Income'),
    # TurboClinic: Gift Bags → ours: Gift Items
    ('Promotional Items & Gift Packs', 'OTH-GFT', 'Gift Items'),
]

updated = 0
for old_name, code, new_name in renames:
    sc = ServiceSubCategory.objects.filter(name=old_name, is_deleted=False).first()
    if not sc:
        sc = ServiceSubCategory.objects.filter(code=code, is_deleted=False).first()
    if sc:
        old = sc.name
        sc.name = new_name
        sc.save(update_fields=['name', 'updated_at'])
        updated += 1
        print(f"  [{code:8s}] {old:35s} -> {new_name}")
    else:
        print(f"  SKIP: {old_name}")

print(f"\nRenamed: {updated}/35")
print("Done!")
