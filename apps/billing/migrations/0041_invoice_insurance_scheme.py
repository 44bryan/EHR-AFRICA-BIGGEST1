import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0040_glaccount_is_summary'),
        ('hmo', '0004_seed_insurance_schemes'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='insurance_scheme',
            field=models.ForeignKey(
                blank=True,
                help_text='Insurance company / payer scheme for this invoice',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='invoices',
                to='hmo.insurancescheme',
            ),
        ),
    ]
