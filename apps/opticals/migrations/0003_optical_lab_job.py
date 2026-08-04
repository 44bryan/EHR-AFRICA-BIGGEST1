import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('opticals', '0002_contact_lens_low_vision'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OpticalLabJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('lab_name', models.CharField(default='In-House Glazing Lab', max_length=120)),
                ('job_number', models.CharField(blank=True, help_text='Lab reference / job ticket number', max_length=60)),
                ('status', models.CharField(
                    choices=[
                        ('PENDING', 'Pending Send'),
                        ('SENT', 'Sent to Lab'),
                        ('RETURNED', 'Returned — QC Check'),
                        ('READY', 'Ready for Collection'),
                        ('COLLECTED', 'Collected by Patient'),
                        ('CANCELLED', 'Cancelled'),
                    ],
                    default='PENDING',
                    max_length=20,
                )),
                ('sent_date', models.DateField(blank=True, null=True)),
                ('expected_return_date', models.DateField(blank=True, null=True)),
                ('actual_return_date', models.DateField(blank=True, null=True)),
                ('special_notes', models.TextField(blank=True)),
                ('order', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='lab_job',
                    to='opticals.opticalorder',
                )),
                ('received_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='lab_jobs_received',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('sent_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='lab_jobs_sent',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-created_at'], 'verbose_name': 'Optical Lab Job'},
        ),
    ]
