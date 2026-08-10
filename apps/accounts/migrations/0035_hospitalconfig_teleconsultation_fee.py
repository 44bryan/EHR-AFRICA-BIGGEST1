from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0034_hospitalconfig_telemedicine'),
    ]

    operations = [
        migrations.AddField(
            model_name='hospitalconfig',
            name='teleconsultation_fee',
            field=models.DecimalField(
                decimal_places=2, default=5000, max_digits=10,
                verbose_name='Teleconsultation Fee (FCFA)',
                help_text='Default fee charged when a tele-session ends. Set 0 to disable auto-billing.',
            ),
        ),
    ]
