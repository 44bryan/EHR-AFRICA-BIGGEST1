"""Add missing deleted_at field to LensPriceMatrix (was omitted in 0011)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('opticals', '0013_add_updated_by_audit_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='lenspricematrix',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
