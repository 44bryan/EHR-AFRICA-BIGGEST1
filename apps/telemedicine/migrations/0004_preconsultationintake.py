from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('telemedicine', '0003_fix_pk_type'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PreConsultationIntake',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('symptoms', models.TextField()),
                ('duration', models.CharField(blank=True, max_length=100)),
                ('severity_score', models.PositiveSmallIntegerField(default=5)),
                ('worsening', models.BooleanField(default=False)),
                ('current_medications', models.TextField(blank=True)),
                ('known_allergies', models.TextField(blank=True)),
                ('other_symptoms', models.TextField(blank=True)),
                ('blood_pressure', models.CharField(blank=True, max_length=20)),
                ('temperature', models.CharField(blank=True, max_length=10)),
                ('ai_triage_summary', models.TextField(blank=True)),
                ('ai_urgency', models.CharField(
                    blank=True, max_length=20,
                    choices=[
                        ('low', 'Low — Routine'),
                        ('moderate', 'Moderate — Soon'),
                        ('high', 'High — Urgent'),
                        ('emergency', 'Emergency — Immediate'),
                    ],
                )),
                ('ai_key_concerns', models.JSONField(blank=True, default=list)),
                ('ai_doctor_notes', models.TextField(blank=True)),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
                ('appointment', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='intake',
                    to='telemedicine.teleappointment',
                )),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='telemedicine_intakes_created',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='telemedicine_intakes_updated',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'verbose_name': 'Pre-Consultation Intake'},
        ),
    ]
