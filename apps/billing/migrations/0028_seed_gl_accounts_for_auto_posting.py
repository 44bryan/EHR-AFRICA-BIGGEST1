"""
Seed GL accounts required for auto-posting:
573000 Petty Cash, 658100 Cash Variance Expense, 758000 Other Income (Overage)
Also ensure 499000, 658000, 654000, 754000, 281000, 241000 exist.
"""
from django.db import migrations


GL_ACCOUNTS = [
    # (code, name, account_type, parent_code_prefix)
    ('499000', 'Patient Deposits / Prepayments',     'LIABILITY',  '4'),
    ('573000', 'Petty Cash',                         'ASSET',      '5'),
    ('658000', 'Bad Debt / Write-off Expense',       'EXPENSE',    '6'),
    ('658100', 'Cash Shortage / Variance Expense',   'EXPENSE',    '6'),
    ('758000', 'Other Income (Cash Overage)',         'REVENUE',    '7'),
    ('654000', 'Loss on Asset Disposal',             'EXPENSE',    '6'),
    ('754000', 'Gain on Asset Disposal',             'REVENUE',    '7'),
    ('281000', 'Accumulated Depreciation',           'CONTRA_ASSET', '2'),
    ('241000', 'Equipment & Fixed Assets',           'ASSET',      '2'),
    ('421000', 'Staff Advances Receivable',          'ASSET',      '4'),
    ('521100', 'Mobile Money Account',               'ASSET',      '5'),
]


def seed_gl(apps, schema_editor):
    GLAccount = apps.get_model('billing', 'GLAccount')
    for code, name, acct_type, _ in GL_ACCOUNTS:
        GLAccount.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'account_type': acct_type,
                'is_active': True,
            },
        )


def unseed_gl(apps, schema_editor):
    GLAccount = apps.get_model('billing', 'GLAccount')
    codes = [code for code, *_ in GL_ACCOUNTS]
    GLAccount.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0027_cost_center_journal_workflow'),
    ]

    operations = [
        migrations.RunPython(seed_gl, unseed_gl),
    ]
