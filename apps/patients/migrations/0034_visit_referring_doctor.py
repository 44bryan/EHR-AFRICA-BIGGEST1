from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0033_phone_number_max_length'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='visit',
            name='referring_doctor',
            field=models.ForeignKey(
                blank=True,
                help_text='Doctor who sent this patient to Refraction — used for return routing.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='refraction_referrals',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
