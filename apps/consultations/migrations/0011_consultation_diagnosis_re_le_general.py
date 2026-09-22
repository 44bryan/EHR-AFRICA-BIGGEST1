from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('consultations', '0010_consultation_diagnosis_summary'),
    ]

    operations = [
        migrations.AddField(
            model_name='consultation',
            name='diagnosis_re',
            field=models.CharField(
                blank=True,
                help_text='Right eye diagnosis (free text)',
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name='consultation',
            name='diagnosis_le',
            field=models.CharField(
                blank=True,
                help_text='Left eye diagnosis (free text)',
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name='consultation',
            name='diagnosis_general',
            field=models.CharField(
                blank=True,
                help_text='General / systemic diagnosis (free text)',
                max_length=255,
            ),
        ),
    ]
