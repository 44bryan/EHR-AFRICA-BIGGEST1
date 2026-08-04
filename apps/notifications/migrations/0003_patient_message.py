import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_rename_notif_recip_read_idx_notificatio_recipie_4e3567_idx'),
        ('patients', '0029_patientdocument'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PatientMessage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('channel', models.CharField(
                    choices=[
                        ('SMS', 'SMS'),
                        ('WHATSAPP', 'WhatsApp'),
                    ],
                    default='SMS',
                    max_length=10,
                )),
                ('message_type', models.CharField(
                    choices=[
                        ('APPOINTMENT_REMINDER', 'Appointment Reminder'),
                        ('RESULTS_READY', 'Results Ready'),
                        ('DISCHARGE_INSTRUCTIONS', 'Discharge Instructions'),
                        ('PRESCRIPTION_READY', 'Prescription Ready'),
                        ('BALANCE_DUE', 'Balance / Payment Due'),
                        ('FOLLOW_UP', 'Follow-up Reminder'),
                        ('CUSTOM', 'Custom Message'),
                    ],
                    default='CUSTOM',
                    max_length=30,
                )),
                ('recipient_number', models.CharField(max_length=20, help_text='E.164 format e.g. +237612345678')),
                ('patient', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='sms_messages',
                    to='patients.patient',
                )),
                ('sent_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='patient_messages_sent',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('body', models.TextField()),
                ('status', models.CharField(
                    choices=[
                        ('PENDING', 'Pending'),
                        ('SENT', 'Sent'),
                        ('DELIVERED', 'Delivered'),
                        ('FAILED', 'Failed'),
                    ],
                    default='PENDING',
                    max_length=10,
                )),
                ('provider_ref', models.CharField(blank=True, max_length=100,
                                                   help_text='Message SID / reference from provider')),
                ('error_message', models.TextField(blank=True)),
                ('sent_at', models.DateTimeField(null=True, blank=True)),
            ],
            options={
                'ordering': ['-created_at'],
                'verbose_name': 'Patient Message',
                'verbose_name_plural': 'Patient Messages (SMS/WhatsApp)',
            },
        ),
        migrations.CreateModel(
            name='MessageTemplate',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('name', models.CharField(max_length=100, unique=True)),
                ('channel', models.CharField(
                    choices=[('SMS', 'SMS'), ('WHATSAPP', 'WhatsApp'), ('BOTH', 'Both')],
                    default='SMS', max_length=10,
                )),
                ('message_type', models.CharField(
                    choices=[
                        ('APPOINTMENT_REMINDER', 'Appointment Reminder'),
                        ('RESULTS_READY', 'Results Ready'),
                        ('DISCHARGE_INSTRUCTIONS', 'Discharge Instructions'),
                        ('PRESCRIPTION_READY', 'Prescription Ready'),
                        ('BALANCE_DUE', 'Balance / Payment Due'),
                        ('FOLLOW_UP', 'Follow-up Reminder'),
                        ('CUSTOM', 'Custom Message'),
                    ],
                    default='CUSTOM', max_length=30,
                )),
                ('body', models.TextField(
                    help_text='Use {{ patient_name }}, {{ appointment_date }}, {{ hospital_name }} as placeholders'
                )),
                ('is_active', models.BooleanField(default=True)),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['name'],
                'verbose_name': 'Message Template',
            },
        ),
    ]
