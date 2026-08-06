"""
Fix: override id field from UUIDField (inherited from TimeStampedModel) to
BigAutoField so it matches the bigint column already in the database.
Uses SeparateDatabaseAndState — no DDL is executed, only the migration state
is updated.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('telemedicine', '0002_add_deleted_at'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='teleappointment',
                    name='id',
                    field=models.BigAutoField(
                        auto_created=True, primary_key=True,
                        serialize=False, verbose_name='ID',
                    ),
                ),
                migrations.AlterField(
                    model_name='telesessionnote',
                    name='id',
                    field=models.BigAutoField(
                        auto_created=True, primary_key=True,
                        serialize=False, verbose_name='ID',
                    ),
                ),
            ],
            database_operations=[],  # DB already has bigint — nothing to change
        ),
    ]
