from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0033_hospitalconfig_enterprise_modules'),
    ]

    operations = [
        migrations.AddField(
            model_name='hospitalconfig',
            name='module_telemedicine',
            field=models.BooleanField(default=True, verbose_name='Telemedicine (Video Consultations)'),
        ),
    ]
