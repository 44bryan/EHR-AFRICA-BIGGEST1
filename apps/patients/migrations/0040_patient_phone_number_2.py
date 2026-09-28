from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0039_alter_patientamendmentrequest_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='patient',
            name='phone_number_2',
            field=models.CharField(blank=True, help_text='Secondary phone number', max_length=30),
        ),
    ]
