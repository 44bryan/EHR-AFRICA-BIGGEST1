from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0016_gl_ap_models'),
        ('laboratory', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='serviceworkorder',
            name='lab_order_item',
            field=models.ForeignKey(
                blank=True,
                help_text='Links this work order to a specific lab test item for per-test payment tracking.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='work_orders',
                to='laboratory.laborderitem',
            ),
        ),
    ]
