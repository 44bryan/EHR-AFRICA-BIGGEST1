"""
Migration 0051 — Seed CashOperationType with TurboClinic CASH group operations

Populates the empty CashOperationType table so that the Approvisionnement Caisse
and Retrait Espèces forms have operation choices matching TurboClinic operation codes.
"""

import uuid
import django.utils.timezone
from django.db import migrations


# (code, name, category)
CASH_TYPES = [
    ('100', 'Ouverture / Fermeture Caisse',           'SUPPLY'),
    ('102', 'Approvisionnement Caisse (Float)',        'SUPPLY'),
    ('104', 'Versement Espèces (Dépôt)',               'SUPPLY'),
    ('106', 'Retrait Espèces',                         'WITHDRAWAL'),
    ('108', 'Transfert Inter-caisse',                  'INTER_DESK'),
    ('112', 'Encaissements Patient',                   'WITHDRAWAL'),
    ('114', 'Décaissements / Remboursements Patient',  'PATIENT_WD'),
    ('116', 'Transfert Inter-caisse: Envoi',           'INTER_DESK'),
    ('118', 'Transfert Inter-caisse: Réception',       'INTER_DESK'),
    ('119', 'Frais d\'Enregistrement',                 'WITHDRAWAL'),
    ('170', 'Versement Avance Proforma',               'WITHDRAWAL'),
    ('200', 'Saisie Opérations Diverses',              'WITHDRAWAL'),
]


def seed(apps, schema_editor):
    CashOperationType = apps.get_model('billing', 'CashOperationType')
    now = django.utils.timezone.now()
    for code, name, category in CASH_TYPES:
        CashOperationType.objects.get_or_create(
            code=code,
            defaults={
                'id': uuid.uuid4(),
                'name': name,
                'category': category,
                'is_active': True,
                'is_deleted': False,
                'deletion_reason': '',
                'created_at': now,
                'updated_at': now,
            }
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0050_journalentry_operation_fk'),
    ]

    operations = [
        migrations.RunPython(seed, reverse_code=noop),
    ]
