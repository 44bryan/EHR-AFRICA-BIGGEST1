"""
Update service sub-categories to match the hospital's existing family codes
from TurboClinic (WhatsApp images from Finance Director).

These are the FAMILY codes — Level 2 grouping between ServiceCategory and ServicePrice.
Each family maps to a specific GL revenue sub-account.

Run: python manage.py shell < _seed_family_codes.py
"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from apps.billing.models import GLAccount, ServiceSubCategory, ServiceCategory

print("=" * 60)
print("SYNCING SERVICE FAMILIES FROM TURBOCLINIC")
print("=" * 60)

# First ensure all needed GL sub-accounts exist
extra_gl = [
    ('705500', 'Cornea Surgery Revenue', 'REVENUE'),
    ('705600', 'Laser Treatment Revenue', 'REVENUE'),
    ('705700', 'Other Surgeries Revenue', 'REVENUE'),
    ('705800', 'Refractive Surgery Revenue', 'REVENUE'),
    ('705900', 'Vitreoretinal Surgery Revenue', 'REVENUE'),
    ('706500', 'CBP Lenses Revenue', 'REVENUE'),
    ('706600', 'Lens Cases Revenue', 'REVENUE'),
    ('706700', 'Reading Glasses Revenue', 'REVENUE'),
    ('706800', 'Sunglasses Revenue', 'REVENUE'),
    ('706900', 'Lens Cleaner Revenue', 'REVENUE'),
    ('706010', 'Low Vision Devices Revenue', 'REVENUE'),
    ('701500', 'Internist Consultation Revenue', 'REVENUE'),
    ('701600', 'Orthoptics Revenue', 'REVENUE'),
    ('709400', 'Anesthesia Revenue', 'REVENUE'),
    ('709500', 'Consumables Revenue', 'REVENUE'),
    ('709600', 'Non-Medical Stock Revenue', 'REVENUE'),
    ('709700', 'Other Medical Services Revenue', 'REVENUE'),
    ('709800', 'Sundry Income', 'REVENUE'),
    ('709900', 'Gift Bags Revenue', 'REVENUE'),
    ('708300', 'Patient Folder Revenue', 'REVENUE'),
    ('701700', 'Orthoptics Cards Revenue', 'REVENUE'),
]

for code, name, atype in extra_gl:
    _, c = GLAccount.objects.get_or_create(
        code=code, defaults={'name': name, 'account_type': atype, 'is_active': True}
    )
    if c:
        print(f"  + GL {code}: {name}")

# Map from TurboClinic family codes to our system
# (turbo_code, name, parent_category, gl_code, sort_order)
families = [
    # ── Optical Products (numeric codes) ──
    ('001', 'CBP Lenses', 'OPTICAL', '706500', 1),
    ('002', 'Lens Cases', 'OPTICAL', '706600', 2),
    ('003', 'Accessories', 'OPTICAL', '706400', 3),
    ('004', 'Reading Glasses', 'OPTICAL', '706700', 4),
    ('005', 'Ready to Clip Frames', 'OPTICAL', '706100', 5),
    ('006', 'Sunglasses', 'OPTICAL', '706800', 6),
    ('007', 'Ready to Clip Lenses', 'OPTICAL', '706200', 7),
    ('008', 'Liquid Lens Cleaner', 'OPTICAL', '706900', 8),
    ('009', 'Lenses', 'OPTICAL', '706200', 9),
    ('010', 'Frames', 'OPTICAL', '706100', 10),

    # ── Surgical ──
    ('ANE', 'Anesthesia', 'SURGICAL', '709400', 1),
    ('CAT', 'Cataract Surgery', 'SURGICAL', '705100', 2),
    ('COR', 'Cornea Surgery', 'SURGICAL', '705500', 3),
    ('GLA', 'Glaucoma Surgery', 'SURGICAL', '705200', 4),
    ('LAS', 'Laser Treatment', 'SURGICAL', '705600', 5),
    ('OCU', 'Oculoplastic Surgery', 'SURGICAL', '705400', 6),
    ('OTH', 'Other Surgeries', 'SURGICAL', '705700', 7),
    ('RES', 'Refractive Surgeries', 'SURGICAL', '705800', 8),
    ('VIT', 'Vitreoretinal Surgery', 'SURGICAL', '705900', 9),

    # ── Consultation ──
    ('CON', 'Consultation', 'CONSULT', '701100', 1),
    ('INT', 'Internist Consultation', 'CONSULT', '701500', 2),

    # ── Clinical / Investigations ──
    ('INV', 'Investigation', 'INVEST', '702100', 1),
    ('ORT', 'Orthoptics', 'CLINICAL', '701600', 1),
    ('OTC', 'Orthoptics Cards', 'CLINICAL', '701700', 2),
    ('LAB', 'Laboratory', 'LAB', '703100', 1),

    # ── Pharmacy / Supplies ──
    ('MED', 'Medications', 'PHARMACY', '704100', 1),
    ('CSM', 'Consumables', 'PHARMACY', '709500', 2),
    ('NMS', 'Non-Medical Stock', 'OTHER', '709600', 1),

    # ── Hospitalization ──
    ('HOS', 'Hospitalization', 'ADMISSION', '707100', 1),

    # ── Low Vision ──
    ('LVD', 'Low Vision Devices', 'OPTICAL', '706010', 11),

    # ── Optical extras ──
    ('CTL', 'Contact Lens', 'OPTICAL', '706300', 12),

    # ── Registration / Admin ──
    ('PF001', 'Patient Folder', 'REG', '708300', 1),

    # ── Other ──
    ('OMS', 'Other Medical Services', 'OTHER', '709700', 2),
    ('SUN', 'Sundry Income', 'OTHER', '709800', 3),
    ('GB01', 'Gift Bags', 'OTHER', '709900', 4),
]

updated = 0
created = 0
for fcode, fname, cat, gl_code, sort in families:
    gl = GLAccount.objects.filter(code=gl_code).first()
    obj, was_created = ServiceSubCategory.objects.update_or_create(
        category=cat, name=fname,
        defaults={
            'code': fcode,
            'gl_account': gl,
            'sort_order': sort,
        }
    )
    if was_created:
        created += 1
        print(f"  NEW  [{fcode:5s}] {cat:10s} > {fname:30s} -> GL {gl_code}")
    else:
        updated += 1
        print(f"  UPD  [{fcode:5s}] {cat:10s} > {fname:30s} -> GL {gl_code}")

# Remove old sub-categories that don't match the new scheme
old_names = [f[1] for f in families]
removed = ServiceSubCategory.objects.filter(is_deleted=False).exclude(name__in=old_names)
if removed.exists():
    print(f"\n  Removing {removed.count()} old sub-categories that don't match new scheme:")
    for r in removed:
        print(f"    - [{r.code}] {r.category} > {r.name}")
    removed.update(is_deleted=True)

print(f"\nCreated: {created}, Updated: {updated}")
print(f"Total active families: {ServiceSubCategory.objects.filter(is_deleted=False).count()}")
print("Done!")
