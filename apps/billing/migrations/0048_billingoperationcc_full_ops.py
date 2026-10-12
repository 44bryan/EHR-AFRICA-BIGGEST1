"""
Migration 0048 — Full TurboClinic-style operations list for BillingOperationCC

Replaces the 20 generic placeholder rows from 0047 with the complete ~55-operation
list that mirrors AEF's current TurboClinic system, making staff familiar with
the same operation codes they already know.

Groups:
  CASH      — Cash desk operations (100-series)
  REVENUE   — Revenue / sales per store (119-130)
  EXPENSE   — Expense / purchase operations (201-210)
  STOCK     — Stock entries, exits, transfers (133-156)
  INVENTORY — Physical inventory counts (150-154)
  ASSET     — Depreciation and asset disposals (160-166)
  BANK      — Per-bank-account operations (T001-T007)
  YEAR_END  — Proforma advance, misc, year-end closing (170-999)
"""

import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


# ─────────────────────────────────────────────────────────────────────────────
# Full seed data  (code, name, category_key, group, cc_code, sort_order)
# cc_code=None means "unassigned until Finance Director configures"
# ─────────────────────────────────────────────────────────────────────────────

OPERATIONS = [

    # ── Cash Desk Operations (100-series) ────────────────────────────────────
    ('100', 'Ouverture / Fermeture Caisse',          'CASH_OPEN',        'CASH',      'CC-008', 1),
    ('102', 'Approvisionnement Caisse (Float)',       'CASH_FLOAT',       'CASH',      'CC-008', 2),
    ('104', 'Versement Espèces (Dépôt)',              'CASH_DEPOSIT',     'CASH',      'CC-008', 3),
    ('106', 'Retrait Espèces',                       'CASH_WITHDRAW',    'CASH',      'CC-008', 4),
    ('108', 'Transfert Inter-caisse',                'CASH_TRANSFER',    'CASH',      'CC-008', 5),
    ('112', 'Encaissements Patient',                 'PATIENT_RECEIPT',  'CASH',      'CC-008', 6),
    ('114', 'Décaissements / Remboursements Patient','PATIENT_REFUND',   'CASH',      'CC-008', 7),
    ('116', 'Transfert Inter-caisse: Envoi',         'CASH_SEND',        'CASH',      'CC-008', 8),
    ('118', 'Transfert Inter-caisse: Réception',     'CASH_RECEIVE',     'CASH',      'CC-008', 9),

    # ── Revenue Sales (119-130) ───────────────────────────────────────────────
    ('119', 'Frais d\'Enregistrement',               'REG',              'REVENUE',   'CC-008', 1),
    ('120', 'Ventes Prestations — OPD',              'CONSULT',          'REVENUE',   'CC-003', 2),
    ('121', 'Ventes Prestations — Clinical',         'CLINICAL',         'REVENUE',   'CC-003', 3),
    ('122', 'Ventes Pharmacie',                      'PHARMACY',         'REVENUE',   'CC-001', 4),
    ('124', 'Ventes Optique',                        'OPTICAL',          'REVENUE',   'CC-005', 5),
    ('126', 'Ventes OT / Chirurgie',                 'SURGICAL',         'REVENUE',   'CC-002', 6),
    ('127', 'Ventes Laboratory',                     'LAB',              'REVENUE',   'CC-004', 7),
    ('128', 'Ventes Investigation / Diagnostics',    'INVEST',           'REVENUE',   'CC-004', 8),
    ('129', 'Ventes IPD / Admission',                'ADMISSION',        'REVENUE',   'CC-006', 9),
    ('130', 'Autres Revenus',                        'OTHER',            'REVENUE',   'CC-008', 10),

    # ── Expense / Purchases (201-210) ────────────────────────────────────────
    ('201', 'Achats Médicaments — Pharmacie',        'DRUGS',            'EXPENSE',   'CC-001', 1),
    ('202', 'Achats Fournitures Médicales',          'SUPPLIES',         'EXPENSE',   'CC-008', 2),
    ('203', 'Charges Utilities (Élect. / Eau)',      'UTILITIES',        'EXPENSE',   'CC-008', 3),
    ('204', 'Charges Salariales',                    'SALARY',           'EXPENSE',   'CC-008', 4),
    ('205', 'Charges Loyer & Installations',         'RENT',             'EXPENSE',   'CC-008', 5),
    ('206', 'Matériels & Maintenance',               'EQUIPMENT',        'EXPENSE',   'CC-012', 6),
    ('207', 'Transport & Logistique',                'TRANSPORT',        'EXPENSE',   'CC-008', 7),
    ('208', 'Charges Administratives',               'ADMIN',            'EXPENSE',   'CC-008', 8),
    ('209', 'Marketing & Communication',             'MARKETING',        'EXPENSE',   'CC-008', 9),
    ('210', 'Autres Dépenses',                       'EXP_OTHER',        'EXPENSE',   'CC-008', 10),

    # ── Stock Movements — Entrées (133-141) ──────────────────────────────────
    ('133', 'Entrées stock — Magasin Principal',     'STOCK_IN_MAIN',    'STOCK',     'CC-008', 1),
    ('134', 'Entrées stock — Pharmacie',             'STOCK_IN_PHARMACY','STOCK',     'CC-001', 2),
    ('135', 'Entrées stock — Optique',               'STOCK_IN_OPTICAL', 'STOCK',     'CC-005', 3),
    ('136', 'Entrées stock — OT / Théâtre',          'STOCK_IN_OT',      'STOCK',     'CC-002', 4),
    ('137', 'Entrées stock — Laboratory',            'STOCK_IN_LAB',     'STOCK',     'CC-004', 5),
    ('141', 'Entrée stock — Réception GRN',          'STOCK_IN_GRN',     'STOCK',     'CC-008', 6),

    # ── Stock Movements — Sorties (142-149) ──────────────────────────────────
    ('142', 'Sortie stock — Réception',              'STOCK_OUT_RCV',    'STOCK',     'CC-008', 7),
    ('144', 'Sorties Produits Périmés',              'EXPIRED_STOCK',    'STOCK',     'CC-008', 8),
    ('145', 'Sorties Pharmacie',                     'STOCK_OUT_PHARMA', 'STOCK',     'CC-001', 9),
    ('146', 'Sorties OT / Théâtre',                  'STOCK_OUT_OT',     'STOCK',     'CC-002', 10),
    ('147', 'Sorties Optique',                       'STOCK_OUT_OPTICAL','STOCK',     'CC-005', 11),
    ('148', 'Sorties OPD / Investigation',           'STOCK_OUT_OPD',    'STOCK',     'CC-003', 12),
    ('149', 'Sorties Laboratory',                    'STOCK_OUT_LAB',    'STOCK',     'CC-004', 13),
    ('156', 'Transfert Inter-magasin',               'STOCK_TRANSFER',   'STOCK',     'CC-008', 14),
    ('180', 'Sorties Non-Medical Stock',             'STOCK_OUT_NONMED', 'STOCK',     'CC-008', 15),
    ('300', 'Entrées stock — Non-Medical',           'STOCK_IN_NONMED',  'STOCK',     'CC-008', 16),

    # ── Inventory Counts (150-155) ───────────────────────────────────────────
    ('150', 'Inventaire Pharmacie',                  'INV_PHARMACY',     'INVENTORY', 'CC-001', 1),
    ('151', 'Inventaire OT / Théâtre',               'INV_OT',           'INVENTORY', 'CC-002', 2),
    ('152', 'Inventaire Optique',                    'INV_OPTICAL',      'INVENTORY', 'CC-005', 3),
    ('153', 'Inventaire Réception / Principale',     'INV_MAIN',         'INVENTORY', 'CC-008', 4),
    ('154', 'Inventaire Consommables Médicaux',      'INV_CONSUMABLES',  'INVENTORY', 'CC-008', 5),
    ('155', 'Ecriture Périodique',                   'PERIODIC_ENTRY',   'INVENTORY', 'CC-008', 6),

    # ── Asset Operations (160-166) ───────────────────────────────────────────
    ('160', 'Amortissement',                         'DEPRECIATION',     'ASSET',     'CC-012', 1),
    ('162', 'Amortissement Complémentaire',          'DEPRECIATION_ADD', 'ASSET',     'CC-012', 2),
    ('164', 'Sortie Immobilisations',                'ASSET_DISPOSAL',   'ASSET',     'CC-012', 3),
    ('166', 'Cession Immobilisation',                'ASSET_TRANSFER',   'ASSET',     'CC-012', 4),

    # ── Bank Operations (T-series — AEF bank accounts) ───────────────────────
    # AC = Approvisionnement Caisse (float from bank)
    # V  = Versement Espèces (deposit to bank)
    # R  = Retrait Espèces (withdrawal from bank)
    ('T001-AC', 'Approvisionnement Caisse — SIB',   'BANK_SIB_AC',      'BANK',      'CC-008', 1),
    ('T001-V',  'Versement Espèces — SIB',          'BANK_SIB_V',       'BANK',      'CC-008', 2),
    ('T001-R',  'Retrait Espèces — SIB',            'BANK_SIB_R',       'BANK',      'CC-008', 3),
    ('T002-AC', 'Approvisionnement Caisse — CBM',   'BANK_CBM_AC',      'BANK',      'CC-008', 4),
    ('T002-V',  'Versement Espèces — CBM',          'BANK_CBM_V',       'BANK',      'CC-008', 5),
    ('T002-R',  'Retrait Espèces — CBM',            'BANK_CBM_R',       'BANK',      'CC-008', 6),
    ('T003-AC', 'Approvisionnement Caisse — LCIF',  'BANK_LCIF_AC',     'BANK',      'CC-008', 7),
    ('T003-V',  'Versement Espèces — LCIF',         'BANK_LCIF_V',      'BANK',      'CC-008', 8),
    ('T003-R',  'Retrait Espèces — LCIF',           'BANK_LCIF_R',      'BANK',      'CC-008', 9),
    ('T004-AC', 'Approvisionnement Caisse — OPIC',  'BANK_OPIC_AC',     'BANK',      'CC-008', 10),
    ('T004-V',  'Versement Espèces — OPIC',         'BANK_OPIC_V',      'BANK',      'CC-008', 11),
    ('T004-R',  'Retrait Espèces — OPIC',           'BANK_OPIC_R',      'BANK',      'CC-008', 12),
    ('T005-AC', 'Approvisionnement Caisse — ORBIS', 'BANK_ORBIS_AC',    'BANK',      'CC-008', 13),
    ('T005-V',  'Versement Espèces — ORBIS',        'BANK_ORBIS_V',     'BANK',      'CC-008', 14),
    ('T005-R',  'Retrait Espèces — ORBIS',          'BANK_ORBIS_R',     'BANK',      'CC-008', 15),
    ('T006-AC', 'Approvisionnement Caisse — LCIF-DR','BANK_LCIFDR_AC',  'BANK',      'CC-008', 16),
    ('T006-V',  'Versement Espèces — LCIF-DR',      'BANK_LCIFDR_V',    'BANK',      'CC-008', 17),
    ('T006-R',  'Retrait Espèces — LCIF-DR',        'BANK_LCIFDR_R',    'BANK',      'CC-008', 18),
    ('T007-AC', 'Approvisionnement Caisse — GIZ Solar','BANK_GIZ_AC',   'BANK',      'CC-008', 19),
    ('T007-V',  'Versement Espèces — GIZ Solar',    'BANK_GIZ_V',       'BANK',      'CC-008', 20),
    ('T007-R',  'Retrait Espèces — GIZ Solar',      'BANK_GIZ_R',       'BANK',      'CC-008', 21),

    # ── Year-End & Special Operations ────────────────────────────────────────
    ('170', 'Versement Avance Proforma',             'PROFORMA_ADVANCE', 'YEAR_END',  'CC-008', 1),
    ('200', 'Saisie Opérations Diverses',            'MISC_OP',          'YEAR_END',  'CC-008', 2),
    ('901', 'Clôture Comptes de Gestion',            'YEAR_END_PL',      'YEAR_END',  'CC-008', 3),
    ('902', 'Clôture Comptes de Bilan',              'YEAR_END_BS',      'YEAR_END',  'CC-008', 4),
    ('903', 'Report à Nouveau',                      'CARRY_FORWARD',    'YEAR_END',  'CC-008', 5),
    ('999', 'Régularisations',                       'ADJUSTMENT',       'YEAR_END',  'CC-008', 6),
]


def seed(apps, schema_editor):
    BillingOperationCC = apps.get_model('billing', 'BillingOperationCC')
    CostCenter         = apps.get_model('billing', 'CostCenter')

    # Clear old generic rows
    BillingOperationCC.objects.all().delete()

    cc_map = {cc.code: cc for cc in CostCenter.objects.filter(is_active=True, is_deleted=False)}
    now = django.utils.timezone.now()

    for code, name, cat_key, group, cc_code, order in OPERATIONS:
        BillingOperationCC.objects.create(
            id=uuid.uuid4(),
            operation_code=code,
            operation_name=name,
            category_key=cat_key,
            group=group,
            cost_center=cc_map.get(cc_code),
            sort_order=order,
            created_at=now,
            updated_at=now,
            is_deleted=False,
            deletion_reason='',
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0047_fix_billingoperationcc'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Widen the group column from max_length=10 to max_length=12 (for 'INVENTORY')
        migrations.AlterField(
            model_name='billingoperationcc',
            name='group',
            field=models.CharField(
                max_length=12,
                choices=[
                    ('CASH',      'Cash Desk Operations'),
                    ('REVENUE',   'Revenue Sales'),
                    ('EXPENSE',   'Expense / Purchases'),
                    ('STOCK',     'Stock Movements'),
                    ('INVENTORY', 'Inventory Count'),
                    ('ASSET',     'Asset Operations'),
                    ('BANK',      'Bank Operations'),
                    ('YEAR_END',  'Year-End & Special'),
                ],
                default='REVENUE',
            ),
        ),
        migrations.RunPython(seed, reverse_code=noop),
    ]
