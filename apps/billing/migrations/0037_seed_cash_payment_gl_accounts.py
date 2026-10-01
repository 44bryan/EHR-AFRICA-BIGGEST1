"""
Seed critical GL accounts required for payment auto-posting.
Ensures CASH (572000), Bank (521000), Petty Cash (571000) exist.
Without these, CASH payment GL entries are silently skipped.
"""
from django.db import migrations


CRITICAL_GL_ACCOUNTS = [
    # (code, name, account_type)
    ('572000', 'Cash in Hand — Cashier',        'ASSET'),
    ('571000', 'Petty Cash — Main',             'ASSET'),
    ('521000', 'Bank Account — Main',           'ASSET'),
    ('573100', 'Cash Float — Desk',             'ASSET'),
]


def seed(apps, schema_editor):
    GLAccount = apps.get_model('billing', 'GLAccount')
    for code, name, acct_type in CRITICAL_GL_ACCOUNTS:
        GLAccount.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'account_type': acct_type,
                'is_active': True,
            },
        )


def unseed(apps, schema_editor):
    # Only remove if we created them (no other data depends on these in tests)
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0036_maintenance_audit_fields'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
