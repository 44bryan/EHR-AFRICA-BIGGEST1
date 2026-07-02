from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacy', '0003_stockadjustment'),
    ]

    operations = [
        migrations.AddField(
            model_name='dispensingitem',
            name='custom_drug_name',
            field=models.CharField(
                blank=True, max_length=200,
                help_text='Used when drug is not in the formulary (Others)'
            ),
        ),
        migrations.AlterField(
            model_name='dispensingitem',
            name='drug',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='pharmacy.drug',
            ),
        ),
    ]
