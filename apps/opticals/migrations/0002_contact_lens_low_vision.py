import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('opticals', '0001_initial'),
        ('patients', '0018_patientconsent'),
        ('prescriptions', '0002_druginteraction'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── ContactLensFitting ───────────────────────────────────────────────
        migrations.CreateModel(
            name='ContactLensFitting',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('fitting_number', models.CharField(max_length=30, unique=True)),
                ('lens_type', models.CharField(
                    choices=[
                        ('DAILY', 'Daily Disposable'),
                        ('FORT', 'Fortnightly Disposable'),
                        ('MONTHLY', 'Monthly Disposable'),
                        ('ANNUAL', 'Annual / Extended Wear'),
                        ('RIGID', 'Rigid Gas-Permeable (RGP)'),
                        ('SCLERAL', 'Scleral Lens'),
                        ('ORTHOK', 'Orthokeratology'),
                        ('THERAPEUTIC', 'Therapeutic / Bandage Lens'),
                    ],
                    max_length=20,
                )),
                ('brand', models.CharField(blank=True, max_length=100)),
                ('fitting_date', models.DateField(default=django.utils.timezone.now)),
                # Right eye
                ('re_sphere', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('re_cylinder', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('re_axis', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('re_add', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('re_base_curve', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('re_diameter', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                # Left eye
                ('le_sphere', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('le_cylinder', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('le_axis', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('le_add', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('le_base_curve', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('le_diameter', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                # Dispensing
                ('quantity_dispensed', models.PositiveIntegerField(default=1)),
                ('price_per_unit', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('total_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('care_solution_included', models.BooleanField(default=False)),
                ('care_solution_price', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                # Follow-up & assessment
                ('next_follow_up', models.DateField(blank=True, null=True)),
                ('follow_up_notes', models.TextField(blank=True)),
                ('patient_education_given', models.BooleanField(default=False)),
                ('fitting_assessment', models.TextField(blank=True)),
                ('over_refraction_va', models.CharField(blank=True, max_length=20)),
                ('is_successful', models.BooleanField(default=True)),
                # Relations
                ('patient', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='cl_fittings',
                    to='patients.patient',
                )),
                ('fitted_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='cl_fittings_done',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('optical_prescription', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='cl_fittings',
                    to='prescriptions.opticalprescription',
                )),
            ],
            options={
                'verbose_name': 'Contact Lens Fitting',
                'ordering': ['-fitting_date'],
            },
        ),

        # ── LowVisionAidDispensing ───────────────────────────────────────────
        migrations.CreateModel(
            name='LowVisionAidDispensing',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('dispensing_number', models.CharField(max_length=30, unique=True)),
                ('dispensing_date', models.DateField(default=django.utils.timezone.now)),
                # Assessment
                ('distance_va_re', models.CharField(blank=True, max_length=20)),
                ('distance_va_le', models.CharField(blank=True, max_length=20)),
                ('near_va_re', models.CharField(blank=True, max_length=20)),
                ('near_va_le', models.CharField(blank=True, max_length=20)),
                ('vision_goal', models.TextField(blank=True)),
                # Aid dispensed
                ('aid_type', models.CharField(
                    choices=[
                        ('OPT_MAG', 'Optical Magnifier (Hand-held / Stand)'),
                        ('TELESC', 'Telescopic Aid / Monocular'),
                        ('BIOPTIC', 'Bioptic Telescope'),
                        ('CCTV', 'CCTV / Electronic Magnifier'),
                        ('RD_SPEC', 'High Add Reading Spectacle'),
                        ('PRISM', 'Prism Spectacle'),
                        ('TINTED', 'Tinted Filter / Light Management'),
                        ('TALKING', 'Talking / Audio Device'),
                        ('CANE', 'Mobility Cane'),
                        ('OTHER', 'Other Aid'),
                    ],
                    max_length=20,
                )),
                ('aid_brand_model', models.CharField(blank=True, max_length=200)),
                ('magnification', models.CharField(blank=True, max_length=50)),
                ('va_achieved_with_aid', models.CharField(blank=True, max_length=20)),
                # Pricing
                ('unit_price', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('total_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                # Training
                ('training_given', models.TextField(blank=True)),
                ('follow_up_date', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('patient_satisfied', models.BooleanField(default=True)),
                # Relations
                ('patient', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='lva_dispensings',
                    to='patients.patient',
                )),
                ('dispensed_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='lva_dispensings_done',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Low Vision Aid Dispensing',
                'ordering': ['-dispensing_date'],
            },
        ),
    ]
