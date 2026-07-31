from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0028_visittierchange_is_deleted'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PatientDocument',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False, db_index=True)),
                ('title', models.CharField(max_length=200)),
                ('document_type', models.CharField(
                    choices=[
                        ('REFERRAL', 'Referral Letter'),
                        ('LAB_RESULT', 'External Lab Result'),
                        ('IMAGING', 'Imaging / Radiology'),
                        ('PRESCRIPTION', 'External Prescription'),
                        ('DISCHARGE', 'Discharge Summary'),
                        ('ID_DOCUMENT', 'ID / Insurance Card'),
                        ('CONSENT', 'Signed Consent'),
                        ('OTHER', 'Other'),
                    ],
                    default='OTHER',
                    max_length=20,
                )),
                ('source', models.CharField(
                    choices=[
                        ('SCAN', 'Physical Scan'),
                        ('UPLOAD', 'Digital Upload'),
                        ('EMAIL', 'Received by Email'),
                        ('WHATSAPP', 'WhatsApp / Messaging'),
                        ('OTHER', 'Other'),
                    ],
                    default='SCAN',
                    max_length=20,
                )),
                ('description', models.TextField(blank=True)),
                ('document_date', models.DateField(
                    blank=True, null=True,
                    help_text='Date on the original document (if known)'
                )),
                ('file', models.FileField(upload_to='patient_documents/%Y/%m/')),
                ('patient', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='documents',
                    to='patients.patient',
                )),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Patient Document',
                'verbose_name_plural': 'Patient Documents',
                'ordering': ['-created_at'],
            },
        ),
    ]
