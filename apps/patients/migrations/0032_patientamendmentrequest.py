from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0031_recordrelease_auditmodel_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PatientAmendmentRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False, db_index=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='amendment_requests', to='patients.patient')),
                ('requestor_name', models.CharField(max_length=200)),
                ('requestor_type', models.CharField(
                    max_length=20,
                    choices=[
                        ('PATIENT', 'Patient'),
                        ('NOK', 'Next of Kin'),
                        ('LEGAL', 'Legal Representative'),
                    ],
                    default='PATIENT',
                )),
                ('requestor_contact', models.CharField(max_length=100, blank=True)),
                ('field_to_amend', models.CharField(max_length=200, help_text='Which field/section needs correction')),
                ('current_value', models.TextField(blank=True, help_text='What the record currently says')),
                ('requested_value', models.TextField(help_text='What the correct information should be')),
                ('reason', models.TextField(help_text='Why the correction is needed')),
                ('supporting_evidence', models.TextField(blank=True, help_text='Documents or proof provided')),
                ('status', models.CharField(
                    max_length=20,
                    choices=[
                        ('PENDING', 'Pending Review'),
                        ('UNDER_REVIEW', 'Under Review'),
                        ('APPROVED', 'Approved & Applied'),
                        ('REJECTED', 'Rejected'),
                    ],
                    default='PENDING',
                    db_index=True,
                )),
                ('reviewed_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='reviewed_amendments',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('decision_notes', models.TextField(blank=True)),
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
            options={'ordering': ['-created_at']},
        ),
    ]
