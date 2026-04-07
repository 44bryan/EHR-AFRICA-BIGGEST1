from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0009_patient_country_patient_division_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='visit',
            name='referral_document',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='patients/referrals/',
                help_text='Scanned copy of the referral letter (uploaded by patient during pre-registration or by receptionist at desk)',
                verbose_name='Referral Document',
            ),
        ),
    ]
