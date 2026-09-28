"""
Seed OHADA Class 3 GL accounts for each store type:
  311000 — General Store (Marchandises)
  321000 — Pharmacy Store (Matieres premieres pharmaceutiques)
  322000 — Optical Store (Marchandises optique)
  323000 — Theatre Store (Fournitures chirurgicales)
  331000 — Ward / Emergency Supplies
  603000 — Variation des Stocks de biens achetes (ensure exists)
"""
from django.db import migrations


STORE_GL_ACCOUNTS = [
    ('311000', 'General Store Stock (Marchandises)',           'ASSET', '3'),
    ('321000', 'Pharmacy Store Stock (Matieres pharmaceutiques)', 'ASSET', '3'),
    ('322000', 'Optical Store Stock (Marchandises optique)',   'ASSET', '3'),
    ('323000', 'Theatre Store Stock (Fournitures chirurgicales)', 'ASSET', '3'),
    ('331000', 'Ward / Emergency Supplies',                    'ASSET', '3'),
    ('603000', 'Variation des Stocks de Biens Achetes',        'EXPENSE', '6'),
]


def seed(apps, schema_editor):
    GLAccount = apps.get_model('billing', 'GLAccount')
    for code, name, acct_type, _ in STORE_GL_ACCOUNTS:
        GLAccount.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'account_type': acct_type,
                'is_active': True,
            },
        )


def unseed(apps, schema_editor):
    GLAccount = apps.get_model('billing', 'GLAccount')
    codes = [code for code, *_ in STORE_GL_ACCOUNTS]
    GLAccount.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0028_seed_gl_accounts_for_auto_posting'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
