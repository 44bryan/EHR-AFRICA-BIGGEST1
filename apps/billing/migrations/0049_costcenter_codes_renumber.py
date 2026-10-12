"""
Migration 0049 — Renumber Cost Center codes CC-001…CC-012 → 0001…0012

Makes codes continuous and numeric to match standard ERP conventions.
The FK links in BillingOperationCC and JournalEntry point to the PK (UUID),
not the code field, so those are unaffected.
"""

from django.db import migrations


RENAME_MAP = {
    'CC-001': '0001',
    'CC-002': '0002',
    'CC-003': '0003',
    'CC-004': '0004',
    'CC-005': '0005',
    'CC-006': '0006',
    'CC-007': '0007',
    'CC-008': '0008',
    'CC-009': '0009',
    'CC-010': '0010',
    'CC-011': '0011',
    'CC-012': '0012',
}


def rename_cc_codes(apps, schema_editor):
    CostCenter = apps.get_model('billing', 'CostCenter')
    for old_code, new_code in RENAME_MAP.items():
        CostCenter.objects.filter(code=old_code).update(code=new_code)


def reverse_rename(apps, schema_editor):
    CostCenter = apps.get_model('billing', 'CostCenter')
    for old_code, new_code in RENAME_MAP.items():
        CostCenter.objects.filter(code=new_code).update(code=old_code)


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0048_billingoperationcc_full_ops'),
    ]

    operations = [
        migrations.RunPython(rename_cc_codes, reverse_code=reverse_rename),
    ]
