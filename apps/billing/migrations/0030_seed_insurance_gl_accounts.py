"""
Seed OHADA GL accounts for insurance accounting integration:
  411000 — Patient Accounts Receivable (Clients)
  412000 — Insurance Receivables (Assurances)
  413000 — Corporate Receivables (Comptes Clients Entreprises)
  658200 — Insurance Bad Debt / Write-off
"""
from django.db import migrations


INSURANCE_GL_ACCOUNTS = [
    ('411000', 'Patient Accounts Receivable (Clients)',     'ASSET', '4'),
    ('412000', 'Insurance Receivables (Assurances)',        'ASSET', '4'),
    ('413000', 'Corporate Receivables (Entreprises)',       'ASSET', '4'),
    ('658200', 'Insurance Bad Debt / Write-off',            'EXPENSE', '6'),
]


def seed(apps, schema_editor):
    GLAccount = apps.get_model('billing', 'GLAccount')
    for code, name, acct_type, _ in INSURANCE_GL_ACCOUNTS:
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
    codes = [code for code, *_ in INSURANCE_GL_ACCOUNTS]
    GLAccount.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0029_seed_store_gl_accounts'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
