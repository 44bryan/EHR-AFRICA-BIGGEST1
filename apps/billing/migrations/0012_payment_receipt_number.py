from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0011_alter_proformaitem_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='receipt_number',
            field=models.CharField(
                blank=True,
                help_text='Auto-generated unique receipt number (RCT-YYYY-NNNNN)',
                max_length=30,
                default='',
            ),
            preserve_default=False,
        ),
    ]
