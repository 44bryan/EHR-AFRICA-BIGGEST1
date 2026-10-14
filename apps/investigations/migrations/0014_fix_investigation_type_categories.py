"""
Data migration: fix InvestigationType.category for all known billing service codes.

Before this migration, codes like INV-16/INV-17 (refractometry), ORT-xx (orthoptics),
etc. were stored with category='INVEST' or 'OTHER', causing post-payment routing to
send patients to the Investigation queue instead of the Refraction/Orthoptics queue.

This migration applies SERVICE_CODE_CATEGORY_MAP from investigations/models.py to all
existing InvestigationType records in the database.
"""
from django.db import migrations

# Inline copy of SERVICE_CODE_CATEGORY_MAP so the migration is self-contained
# (migrations must not import from app models directly).
_CODE_CATEGORY_MAP = {
    # Refraction
    'INV-16': 'REFRACTION',
    'INV-17': 'REFRACTION',
    'INV-18': 'REFRACTION',
    'INV-23': 'REFRACTION',
    'INV-24': 'REFRACTION',
    'INV-28': 'REFRACTION',
    # Orthoptics
    'INV-13': 'ORTHOPTICS',
    'ORT-01': 'ORTHOPTICS',
    'ORT-02': 'ORTHOPTICS',
    'ORT-04': 'ORTHOPTICS',
    'ORT-05': 'ORTHOPTICS',
    'ORT-06': 'ORTHOPTICS',
    'ORT-07': 'ORTHOPTICS',
    'ORT-08': 'ORTHOPTICS',
    'ORT-09': 'ORTHOPTICS',
    'ORT-10': 'ORTHOPTICS',
    'ORT-11': 'ORTHOPTICS',
    'ORT-12': 'ORTHOPTICS',
    'ORT-13': 'ORTHOPTICS',
    'ORT-14': 'ORTHOPTICS',
    'ORT-15': 'ORTHOPTICS',
    'ORT-16': 'ORTHOPTICS',
    'ORT-17': 'ORTHOPTICS',
    'ORT-18': 'ORTHOPTICS',
    'ORT-19': 'ORTHOPTICS',
    'ORT-20': 'ORTHOPTICS',
    'ORT-21': 'ORTHOPTICS',
    'ORT-22': 'ORTHOPTICS',
    'ORT-23': 'ORTHOPTICS',
    'ORT-24': 'ORTHOPTICS',
    'ORT-25': 'ORTHOPTICS',
    # Low Vision
    'ORT-03': 'LOW_VISION',
    # Visual Field
    'INV-26': 'VISUAL_FIELD',
    'INV-27': 'VISUAL_FIELD',
    'INV-29': 'VISUAL_FIELD',
    # Tonometry
    'INV-11': 'TONOMETRY',
    'INV-19': 'TONOMETRY',
    'INV-32': 'TONOMETRY',
    'INV-35': 'TONOMETRY',
    # Biometry
    'INV-04': 'BIOMETRY',
    # Topography / Keratometry
    'INV-05': 'TOPOGRAPHY',
    'INV-12': 'TOPOGRAPHY',
    # OCT
    'INV-14': 'OCT',
    # Angiography
    'INV-01': 'ANGIOGRAPHY',
    'INV-02': 'ANGIOGRAPHY',
    # Fundus Photography
    'INV-08': 'FUNDUS_PHOTO',
    'INV-09': 'FUNDUS_PHOTO',
    'INV-30': 'FUNDUS_PHOTO',
    'INV-33': 'FUNDUS_PHOTO',
    # Anterior Segment
    'INV-03': 'ANT_SEG',
    'INV-10': 'ANT_SEG',
    # Electrophysiology
    'INV-06': 'ELECTROPHYSIOLOGY',
    'INV-07': 'ELECTROPHYSIOLOGY',
    'INV-25': 'ELECTROPHYSIOLOGY',
    # Ultrasound / Imaging
    'INV-22': 'IMAGING',
    'INV-15': 'IMAGING',
    # External
    'INV-31': 'EXTERNAL',
}


def fix_categories(apps, schema_editor):
    InvestigationType = apps.get_model('investigations', 'InvestigationType')
    updated = 0
    for code, correct_cat in _CODE_CATEGORY_MAP.items():
        count = InvestigationType.objects.filter(
            code=code,
        ).exclude(
            category=correct_cat,
        ).update(category=correct_cat)
        updated += count
    if updated:
        print(f'\n  Fixed {updated} InvestigationType category records.')


def reverse_fix(apps, schema_editor):
    # Non-destructive reverse: reset affected codes to 'OTHER'
    InvestigationType = apps.get_model('investigations', 'InvestigationType')
    InvestigationType.objects.filter(code__in=_CODE_CATEGORY_MAP.keys()).update(category='OTHER')


class Migration(migrations.Migration):

    dependencies = [
        ('investigations', '0013_acquisitionrecord_deleted_by_and_more'),
    ]

    operations = [
        migrations.RunPython(fix_categories, reverse_code=reverse_fix),
    ]
