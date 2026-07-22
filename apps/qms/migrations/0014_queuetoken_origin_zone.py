"""
Migration 0014: Add origin_zone FK to QueueToken.

origin_zone is set at token creation and never changes, even when the token
moves to the SHARED zone for Lab/Pharmacy/Optical. Used for:
  - Return routing after shared services (back to patient's tier zone)
  - Per-tier revenue and volume reports on shared service stations
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qms', '0013_zones'),
    ]

    operations = [
        migrations.AddField(
            model_name='queuetoken',
            name='origin_zone',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='origin_tokens',
                to='qms.zone',
                help_text="Zone where the patient's visit originated. Never changes after issuance.",
            ),
        ),
    ]
