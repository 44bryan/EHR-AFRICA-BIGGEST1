from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0020_visit_consultation_room'),
    ]

    operations = [
        migrations.AddField(
            model_name='patient',
            name='dob_is_approximate',
            field=models.BooleanField(default=False, help_text='True when DOB was estimated from year, year+month, or age only'),
        ),
        migrations.AddField(
            model_name='patient',
            name='postal_code',
            field=models.CharField(blank=True, help_text='Zip / Postal code (optional)', max_length=10),
        ),
        migrations.AddField(
            model_name='patient',
            name='phone_is_whatsapp',
            field=models.BooleanField(default=False, help_text='Phone number is also a WhatsApp number'),
        ),
    ]
