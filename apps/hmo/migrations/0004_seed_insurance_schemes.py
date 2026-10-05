"""
Data migration: seed the 16 insurance / payer companies used at AEF/MICEI.
Sourced from TurboClinic cashier insurance selector (Oct 2026 dry-run data).
"""
from django.db import migrations


SCHEMES = [
    # (name, code, scheme_type, coverage_pct, pre_auth_required)
    ('CNPS',                    'CNPS',     'CNPS',      80, False),
    ('CNPS - Needy',            'CNPS-NE',  'CNPS',      100, False),
    ('ASCOMA',                  'ASCOMA',   'CORPORATE', 80, True),
    ('ACTIVA Assurances',       'ACTIVA',   'CORPORATE', 80, True),
    ('AXA Assurances',          'AXA',      'CORPORATE', 80, True),
    ('SNH (Société Nat. Hydrocarbures)', 'SNH', 'CORPORATE', 80, True),
    ('BEAC',                    'BEAC',     'CORPORATE', 100, False),
    ('Magrabi ICO',             'MAGRABI',  'CORPORATE', 80, False),
    ('ZENITH Assurances',       'ZENITH',   'CORPORATE', 80, True),
    ('Willis Towers Watson',    'WTW',      'CORPORATE', 80, True),
    ('Swiss Embassy',           'SWISS-EM', 'CORPORATE', 100, False),
    ('European Union',          'EU',       'CORPORATE', 100, False),
    ('AAC (Afrique Assurance)', 'AAC',      'CORPORATE', 80, True),
    ('Partners Courtier',       'PART-CT',  'OTHER',     80, False),
    ('PASS 24',                 'PASS24',   'OTHER',     80, False),
    ('CSPH',                    'CSPH',     'CORPORATE', 100, False),
]


def seed_schemes(apps, schema_editor):
    InsuranceScheme = apps.get_model('hmo', 'InsuranceScheme')
    for name, code, scheme_type, coverage_pct, pre_auth in SCHEMES:
        InsuranceScheme.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'scheme_type': scheme_type,
                'coverage_pct': coverage_pct,
                'pre_auth_required': pre_auth,
                'is_active': True,
            }
        )


def unseed_schemes(apps, schema_editor):
    InsuranceScheme = apps.get_model('hmo', 'InsuranceScheme')
    codes = [s[1] for s in SCHEMES]
    InsuranceScheme.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('hmo', '0003_claim_deleted_by_claim_deletion_reason_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_schemes, unseed_schemes),
    ]
