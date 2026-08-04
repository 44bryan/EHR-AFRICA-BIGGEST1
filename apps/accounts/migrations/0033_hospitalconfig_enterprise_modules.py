from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0032_user_can_do_reception'),
    ]

    operations = [
        migrations.AddField(
            model_name='hospitalconfig',
            name='module_hmo',
            field=models.BooleanField(default=True, verbose_name='HMO & Insurance Claims'),
        ),
        migrations.AddField(
            model_name='hospitalconfig',
            name='module_blood_bank',
            field=models.BooleanField(default=True, verbose_name='Blood Bank'),
        ),
        migrations.AddField(
            model_name='hospitalconfig',
            name='module_infection_control',
            field=models.BooleanField(default=True, verbose_name='Infection Control / Antibiogram'),
        ),
        migrations.AddField(
            model_name='hospitalconfig',
            name='module_dietary',
            field=models.BooleanField(default=True, verbose_name='Dietary & Nutrition'),
        ),
        migrations.AddField(
            model_name='hospitalconfig',
            name='module_mortuary',
            field=models.BooleanField(default=True, verbose_name='Mortuary'),
        ),
    ]
