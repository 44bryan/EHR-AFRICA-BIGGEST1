from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0021_dob_approximate_phone_whatsapp_postal'),
    ]

    operations = [
        migrations.AddField(
            model_name='visit',
            name='referral_hospital',
            field=models.CharField(blank=True, help_text='Name of hospital or doctor that referred this patient', max_length=150),
        ),
        migrations.AddField(
            model_name='visit',
            name='intake_disability',
            field=models.CharField(blank=True, help_text='Disability status declared at intake (comma-separated)', max_length=200),
        ),
        migrations.AddField(
            model_name='visit',
            name='intake_eye_complaints',
            field=models.TextField(blank=True, help_text='Eye complaints ticked by receptionist at intake'),
        ),
    ]
