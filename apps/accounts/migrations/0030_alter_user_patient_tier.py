from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0029_patient_tier'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='patient_tier',
            field=models.CharField(
                blank=True,
                choices=[
                    ('ALL', 'All Tiers'),
                    ('STANDARD', 'Standard Only'),
                    ('EXPRESS', 'Express / Fast Track Only'),
                    ('VIP', 'VIP Only'),
                ],
                default='ALL',
                help_text='For pharmacists, lab techs, refractionists, cashiers, triage nurses — which patient tier this account serves. VIP staff see only VIP patients; EXPRESS staff see only Express/Fast Track; Standard staff see only standard patients; ALL sees everyone.',
                max_length=10,
            ),
        ),
    ]
