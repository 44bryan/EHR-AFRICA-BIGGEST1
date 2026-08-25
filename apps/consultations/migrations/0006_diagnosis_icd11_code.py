from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('consultations', '0005_surgicalrequest'),
    ]

    operations = [
        migrations.AddField(
            model_name='diagnosis',
            name='icd11_code',
            field=models.CharField(blank=True, db_index=True, default='', help_text='ICD-11 code (e.g. 9B10.0). Added for future-proofing.', max_length=20),
        ),
    ]
