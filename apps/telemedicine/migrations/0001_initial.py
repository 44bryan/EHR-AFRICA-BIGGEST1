import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('patients', '0029_patientdocument'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TeleAppointment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('appointment_type', models.CharField(
                    choices=[
                        ('NEW', 'New Consultation'),
                        ('FOLLOW_UP', 'Follow-Up'),
                        ('PRESCRIPTION', 'Prescription Review'),
                        ('REFERRAL', 'Specialist Referral'),
                        ('URGENT', 'Urgent / Triage'),
                    ],
                    default='FOLLOW_UP', max_length=20,
                )),
                ('status', models.CharField(
                    choices=[
                        ('SCHEDULED', 'Scheduled'),
                        ('WAITING', 'Patient Waiting'),
                        ('IN_SESSION', 'In Session'),
                        ('COMPLETED', 'Completed'),
                        ('CANCELLED', 'Cancelled'),
                        ('NO_SHOW', 'No Show'),
                    ],
                    default='SCHEDULED', max_length=20,
                )),
                ('scheduled_at', models.DateTimeField()),
                ('duration_minutes', models.PositiveSmallIntegerField(default=20)),
                ('chief_complaint', models.TextField(blank=True)),
                ('session_room_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('ended_at', models.DateTimeField(blank=True, null=True)),
                ('actual_duration_minutes', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('patient_joined', models.BooleanField(default=False)),
                ('cancellation_reason', models.TextField(blank=True)),
                ('patient', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='tele_appointments',
                    to='patients.patient',
                )),
                ('doctor', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='tele_appointments_as_doctor',
                    to=settings.AUTH_USER_MODEL,
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
            options={'ordering': ['-scheduled_at'], 'verbose_name': 'Tele-Appointment'},
        ),
        migrations.CreateModel(
            name='TeleSessionNote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('subjective', models.TextField()),
                ('objective', models.TextField(blank=True)),
                ('assessment', models.TextField(blank=True)),
                ('plan', models.TextField(blank=True)),
                ('follow_up_days', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('appointment', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='session_note',
                    to='telemedicine.teleappointment',
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
            options={'ordering': ['-created_at'], 'verbose_name': 'Tele-Session Note'},
        ),
    ]
