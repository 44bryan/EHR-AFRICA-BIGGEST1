from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0029_patientdocument'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RecordReleaseRequest',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('is_deleted', models.BooleanField(default=False, db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('requestor_name', models.CharField(max_length=200)),
                ('requestor_type', models.CharField(
                    choices=[
                        ('PATIENT', 'Patient / Next of Kin'),
                        ('INSURANCE', 'Insurance Company'),
                        ('LEGAL', 'Legal / Attorney'),
                        ('HOSPITAL', 'Another Hospital / Referral'),
                        ('EMPLOYER', 'Employer'),
                        ('OTHER', 'Other'),
                    ],
                    max_length=20,
                )),
                ('requestor_contact', models.CharField(blank=True, max_length=200)),
                ('purpose', models.TextField()),
                ('records_requested', models.TextField()),
                ('authorization_reference', models.CharField(blank=True, max_length=200)),
                ('status', models.CharField(
                    choices=[
                        ('PENDING', 'Pending Review'),
                        ('APPROVED', 'Approved — Preparing'),
                        ('DISPATCHED', 'Dispatched / Released'),
                        ('REJECTED', 'Rejected'),
                    ],
                    db_index=True,
                    default='PENDING',
                    max_length=15,
                )),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('processing_notes', models.TextField(blank=True)),
                ('patient', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='release_requests',
                    to='patients.patient',
                )),
                ('processed_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='processed_releases',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Record Release Request',
                'ordering': ['-created_at'],
            },
        ),
    ]
