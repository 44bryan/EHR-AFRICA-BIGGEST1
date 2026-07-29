"""
Manual migration: add is_deleted + deleted_at to VisitTierChange
without altering the id column (it remains bigint as originally created).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0027_visittierchange'),
    ]

    operations = [
        # Add is_deleted (BooleanField)
        migrations.AddField(
            model_name='visittierchange',
            name='is_deleted',
            field=models.BooleanField(default=False),
        ),
        # Add deleted_at (nullable DateTimeField)
        migrations.AddField(
            model_name='visittierchange',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
