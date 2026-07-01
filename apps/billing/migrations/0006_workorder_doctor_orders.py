import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0005_service_work_order'),
        ('consultations', '0001_initial'),
    ]

    operations = [
        # Make invoice nullable (doctor orders don't have an invoice yet)
        migrations.AlterField(
            model_name='serviceworkorder',
            name='invoice',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='work_orders',
                to='billing.invoice',
                help_text='Set when cashier bills the order. Null = not yet billed.',
            ),
        ),
        # Add consultation FK
        migrations.AddField(
            model_name='serviceworkorder',
            name='consultation',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='work_orders',
                to='consultations.consultation',
                help_text='Set when doctor creates the order during a consultation.',
            ),
        ),
    ]
