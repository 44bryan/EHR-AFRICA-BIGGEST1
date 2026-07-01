from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0021_alter_user_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='hospitalconfig',
            name='consultation_days',
            field=models.PositiveSmallIntegerField(
                default=15,
                verbose_name='Consultation Validity (days)',
                help_text='Consultation window. After this, patient must pay a new consultation fee.',
            ),
        ),
    ]
