from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0024_perf_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='patientconsent',
            name='patient_signature',
            field=models.TextField(
                blank=True,
                help_text='Base64-encoded digital signature drawn by patient or representative'
            ),
        ),
    ]
