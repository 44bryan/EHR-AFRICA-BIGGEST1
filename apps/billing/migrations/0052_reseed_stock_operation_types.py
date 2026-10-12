"""
Migration 0052 — Replace EN-ACH style StockOperationType records with
TurboClinic STOCK group operation codes (133-149, 156).

Drops the old generic English codes and inserts the exact operation
numbers that AEF staff already know from TurboClinic.

ENTRY operations (Stock In):
  133  Magasin Principal      DR 311000 / CR 401100
  134  Pharmacie              DR 321000 / CR 401100
  135  Optique                DR 322000 / CR 401100
  136  OT / Théâtre           DR 323000 / CR 401100
  137  Laboratory             DR 331000 / CR 401100
  141  Réception GRN          DR 311000 / CR 401100  (all stores)

EXIT operations (Stock Out):
  142  Sortie Générale        DR 603000 / CR 311000
  144  Produits Périmés       DR 603000 / CR 311000  (all stores)
  145  Sorties Pharmacie      DR 603000 / CR 321000
  146  Sorties OT / Théâtre   DR 603000 / CR 323000
  147  Sorties Optique        DR 603000 / CR 322000
  148  Sorties OPD            DR 603000 / CR 311000
  149  Sorties Lab            DR 603000 / CR 331000
  156  Transfert Interne      DR 321000 / CR 311000  (all stores)
"""

import uuid
import django.utils.timezone
from django.db import migrations


# ── GL accounts we depend on (ensure they exist) ─────────────────────────────
_ENSURE_GL = [
    ('311000', 'General Store Stock (Marchandises)',            'ASSET'),
    ('321000', 'Pharmacy Store Stock (Mat. pharmaceutiques)',   'ASSET'),
    ('322000', 'Optical Store Stock (Marchandises optique)',    'ASSET'),
    ('323000', 'Theatre Store Stock (Fournitures chir.)',       'ASSET'),
    ('331000', 'Ward / Laboratory Supplies',                    'ASSET'),
    ('603000', 'Variation des Stocks de Biens Achetes',         'EXPENSE'),
    ('401100', 'Fournisseurs — Achats Locaux',                  'LIABILITY'),
]

# ── New records: (code, name, category, debit_code, credit_code, location_types) ─
_NEW_STOCK_OPS = [
    # ── ENTRY (Stock In) ────────────────────────────────────────────────────
    ('133', 'Entrées stock — Magasin Principal',    'ENTRY', '311000', '401100', 'GENERAL'),
    ('134', 'Entrées stock — Pharmacie',            'ENTRY', '321000', '401100', 'PHARMACY'),
    ('135', 'Entrées stock — Optique',              'ENTRY', '322000', '401100', 'OPTICAL,SHOWROOM'),
    ('136', 'Entrées stock — OT / Théâtre',         'ENTRY', '323000', '401100', 'THEATRE,OT'),
    ('137', 'Entrées stock — Laboratory',           'ENTRY', '331000', '401100', 'LAB'),
    ('141', 'Entrée stock — Réception GRN',         'ENTRY', '311000', '401100', ''),
    # ── EXIT (Stock Out) ────────────────────────────────────────────────────
    ('142', 'Sortie stock — Générale',              'EXIT',  '603000', '311000', 'GENERAL'),
    ('144', 'Sorties Produits Périmés',             'EXIT',  '603000', '311000', ''),
    ('145', 'Sorties Pharmacie',                    'EXIT',  '603000', '321000', 'PHARMACY'),
    ('146', 'Sorties OT / Théâtre',                 'EXIT',  '603000', '323000', 'THEATRE,OT'),
    ('147', 'Sorties Optique',                      'EXIT',  '603000', '322000', 'OPTICAL,SHOWROOM'),
    ('148', 'Sorties OPD / Consommables',           'EXIT',  '603000', '311000', 'GENERAL'),
    ('149', 'Sorties Laboratory',                   'EXIT',  '603000', '331000', 'LAB'),
    ('156', 'Transfert Interne — Réception',        'EXIT',  '321000', '311000', ''),
]


def seed(apps, schema_editor):
    GLAccount = apps.get_model('billing', 'GLAccount')
    StockOperationType = apps.get_model('billing', 'StockOperationType')
    now = django.utils.timezone.now()

    # 1. Ensure all GL accounts exist
    for code, name, acct_type in _ENSURE_GL:
        GLAccount.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'account_type': acct_type,
                'is_active': True,
            }
        )

    # 2. Delete all old EN-ACH style records (any record whose code
    #    does NOT match the new TurboClinic numeric codes)
    new_codes = {row[0] for row in _NEW_STOCK_OPS}
    StockOperationType.objects.exclude(code__in=new_codes).delete()

    # 3. Insert / update new records
    for code, name, category, dr_code, cr_code, loc_types in _NEW_STOCK_OPS:
        dr_acct = GLAccount.objects.get(code=dr_code)
        cr_acct = GLAccount.objects.get(code=cr_code)
        StockOperationType.objects.update_or_create(
            code=code,
            defaults={
                'name': name,
                'category': category,
                'debit_account': dr_acct,
                'credit_account': cr_acct,
                'location_types': loc_types,
                'is_active': True,
                'is_deleted': False,
                'deletion_reason': '',
                'updated_at': now,
            }
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0051_seed_cash_operation_types'),
    ]

    operations = [
        migrations.RunPython(seed, reverse_code=noop),
    ]
