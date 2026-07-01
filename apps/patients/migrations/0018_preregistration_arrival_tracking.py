from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0017_patientconsent'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='preregistration',
            name='visit_date',
            field=models.DateField(blank=True, db_index=True, null=True,
                                   help_text='Date the patient intends to visit'),
        ),
        migrations.AddField(
            model_name='preregistration',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING',    'Pending Arrival'),
                    ('ARRIVED',    'Arrived — Awaiting Registration'),
                    ('REGISTERED', 'Registered'),
                    ('NO_SHOW',    'Did Not Show'),
                    ('EXPIRED',    'Expired'),
                ],
                default='PENDING', db_index=True, max_length=15,
            ),
        ),
        migrations.AddField(
            model_name='preregistration',
            name='arrived_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='preregistration',
            name='confirmed_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='confirmed_arrivals',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
