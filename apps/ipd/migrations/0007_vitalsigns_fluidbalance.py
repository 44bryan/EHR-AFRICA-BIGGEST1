import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ipd', '0006_anaestheticrecord_nursingcareplan'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── VitalSigns ───────────────────────────────────────────────────────
        migrations.CreateModel(
            name='VitalSigns',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('recorded_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('temperature', models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True, help_text='°C')),
                ('pulse', models.PositiveSmallIntegerField(blank=True, null=True, help_text='bpm')),
                ('respiratory_rate', models.PositiveSmallIntegerField(blank=True, null=True, help_text='breaths/min')),
                ('spo2', models.PositiveSmallIntegerField(blank=True, null=True, help_text='%')),
                ('bp_systolic', models.PositiveSmallIntegerField(blank=True, null=True, help_text='mmHg')),
                ('bp_diastolic', models.PositiveSmallIntegerField(blank=True, null=True, help_text='mmHg')),
                ('blood_glucose', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True, help_text='mmol/L')),
                ('pain_score', models.PositiveSmallIntegerField(blank=True, null=True, help_text='0–10 VAS')),
                ('visual_acuity_re', models.CharField(blank=True, max_length=20)),
                ('visual_acuity_le', models.CharField(blank=True, max_length=20)),
                ('iop_re', models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True, help_text='mmHg')),
                ('iop_le', models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True, help_text='mmHg')),
                ('gcs', models.PositiveSmallIntegerField(blank=True, null=True, help_text='3–15')),
                ('notes', models.TextField(blank=True)),
                ('admission', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='vital_signs',
                    to='ipd.admission',
                )),
                ('recorded_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='vitals_recorded',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Vital Signs Entry',
                'verbose_name_plural': 'Vital Signs Flowsheet',
                'ordering': ['-recorded_at'],
            },
        ),

        # ── FluidBalance ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name='FluidBalance',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('recorded_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('entry_type', models.CharField(
                    choices=[
                        ('IV_FLUID', 'IV Fluid'),
                        ('ORAL', 'Oral Intake'),
                        ('NG_FEED', 'NG / Nasogastric Feed'),
                        ('BLOOD', 'Blood Transfusion'),
                        ('URINE', 'Urine Output'),
                        ('DRAIN', 'Drain / Wound Drainage'),
                        ('VOMIT', 'Vomit'),
                        ('STOOL', 'Stool'),
                        ('OTHER_OUT', 'Other Output'),
                    ],
                    max_length=20,
                )),
                ('description', models.CharField(blank=True, max_length=200)),
                ('volume_ml', models.PositiveIntegerField(help_text='Volume in millilitres')),
                ('is_intake', models.BooleanField(help_text='True = intake, False = output')),
                ('notes', models.TextField(blank=True)),
                ('admission', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='fluid_entries',
                    to='ipd.admission',
                )),
                ('recorded_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='fluid_entries_recorded',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Fluid Balance Entry',
                'verbose_name_plural': 'Fluid Balance Chart',
                'ordering': ['-recorded_at'],
            },
        ),
    ]
