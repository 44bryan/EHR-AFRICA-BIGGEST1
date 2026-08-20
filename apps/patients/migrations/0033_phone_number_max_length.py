from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0032_patientamendmentrequest'),
    ]

    operations = [
        migrations.AlterField(
            model_name='patient',
            name='phone_number',
            field=models.CharField(max_length=30),
        ),
        migrations.AlterField(
            model_name='nextofkin',
            name='phone_number',
            field=models.CharField(max_length=30),
        ),
    ]
