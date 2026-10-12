"""
Migration 0050 — Add operation FK to JournalEntry

Links every auto-generated journal entry to the corresponding
BillingOperationCC row (TurboClinic operation code).
This lets Finance Directors filter the general ledger / reports
by operation type — exactly like TurboClinic.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0049_costcenter_codes_renumber'),
    ]

    operations = [
        migrations.AddField(
            model_name='journalentry',
            name='operation',
            field=models.ForeignKey(
                blank=True,
                help_text='TurboClinic operation code auto-tagged on every GL entry',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='journal_entries',
                to='billing.billingoperationcc',
            ),
        ),
    ]
