"""Add CHECKED_IN acquisition status + check-in tracking fields."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('investigations', '0007_acquisition_observations_critical_values'),
    ]

    operations = [
        migrations.AlterField(
            model_name='investigationorder',
            name='acquisition_status',
            field=models.CharField(
                choices=[
                    ('SCHEDULED', 'Scheduled'),
                    ('CHECKED_IN', 'Checked In'),
                    ('PATIENT_PREPARED', 'Patient Prepared'),
                    ('IN_PROGRESS', 'In Progress'),
                    ('ACQUIRED', 'Acquired'),
                    ('QUALITY_FAILED', 'Quality Failed'),
                    ('REPEAT', 'Repeat Acquisition'),
                ],
                db_index=True,
                default='SCHEDULED',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='investigationorder',
            name='checked_in_at',
            field=models.DateTimeField(
                blank=True, null=True,
                help_text='When patient physically arrived at investigation room',
            ),
        ),
        migrations.AddField(
            model_name='investigationorder',
            name='checked_in_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='investigation_checkins',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
