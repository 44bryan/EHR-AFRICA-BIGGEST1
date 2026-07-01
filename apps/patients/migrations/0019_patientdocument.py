import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0018_preregistration_arrival_tracking'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PatientDocument',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('document_type', models.CharField(
                    choices=[
                        ('CONSULT', 'Consultation Note'), ('LAB', 'Lab Report'),
                        ('IMG', 'Imaging / Radiology'), ('RX', 'Prescription'),
                        ('REF', 'Referral Letter'), ('SURG', 'Surgical Report'),
                        ('DC', 'Discharge Summary'), ('CONSENT', 'Consent Form'),
                        ('ID', 'ID / Insurance Card'), ('OTHER', 'Other Document'),
                    ],
                    default='OTHER', max_length=20,
                )),
                ('source', models.CharField(
                    choices=[
                        ('SCAN', 'Scanned Paper Record'),
                        ('DIGITAL', 'Digital Document'),
                        ('EXT', 'External / Referred'),
                    ],
                    default='SCAN', max_length=10,
                )),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True, default='')),
                ('file', models.FileField(upload_to='patient_documents/%Y/%m/')),
                ('document_date', models.DateField(blank=True, null=True)),
                ('patient', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='documents', to='patients.patient',
                )),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL,
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
