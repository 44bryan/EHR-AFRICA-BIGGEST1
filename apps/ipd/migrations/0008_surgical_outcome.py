import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('ipd', '0007_vitalsigns_fluidbalance'),
        ('patients', '0029_alter_patient_options'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SurgicalOutcome',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('surgery_date', models.DateField(blank=True, null=True)),
                ('pre_va_right', models.CharField(blank=True, max_length=20, verbose_name='Pre-op VA (Right Eye)')),
                ('pre_va_left', models.CharField(blank=True, max_length=20, verbose_name='Pre-op VA (Left Eye)')),
                ('pre_iop_right', models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True, verbose_name='Pre-op IOP Right (mmHg)')),
                ('pre_iop_left', models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True, verbose_name='Pre-op IOP Left (mmHg)')),
                ('post_va_right', models.CharField(blank=True, max_length=20, verbose_name='Post-op VA (Right Eye)')),
                ('post_va_left', models.CharField(blank=True, max_length=20, verbose_name='Post-op VA (Left Eye)')),
                ('post_iop_right', models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True, verbose_name='Post-op IOP Right (mmHg)')),
                ('post_iop_left', models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True, verbose_name='Post-op IOP Left (mmHg)')),
                ('outcome_grade', models.CharField(
                    blank=True,
                    choices=[
                        ('EXCELLENT', 'Excellent — VA ≥ 6/18'),
                        ('GOOD', 'Good — VA 6/36 to 6/60'),
                        ('FAIR', 'Fair — VA < 6/60'),
                        ('POOR', 'Poor — No visual gain'),
                        ('COMPLICATED', 'Complicated — Adverse outcome'),
                    ],
                    max_length=20,
                )),
                ('intraoperative_complications', models.TextField(blank=True)),
                ('postoperative_complications', models.TextField(blank=True)),
                ('follow_up_date', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('booking', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='outcome',
                    to='ipd.surgicalbooking',
                )),
                ('patient', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='surgical_outcomes',
                    to='patients.patient',
                )),
                ('recorded_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='outcomes_entered',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('surgeon', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='surgical_outcomes_recorded',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-surgery_date', '-created_at'], 'verbose_name': 'Surgical Outcome'},
        ),
    ]
