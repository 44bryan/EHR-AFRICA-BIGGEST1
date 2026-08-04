import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacy', '0004_dispensingitem_custom_drug'),
        ('patients', '0018_patientconsent'),
        ('ipd', '0006_anaestheticrecord_nursingcareplan'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Drug: controlled drug classification fields ──────────────────────
        migrations.AddField(
            model_name='drug',
            name='is_controlled',
            field=models.BooleanField(
                default=False,
                help_text='Requires narcotics register entry and witness signature on every dispensing',
            ),
        ),
        migrations.AddField(
            model_name='drug',
            name='controlled_schedule',
            field=models.CharField(
                blank=True,
                max_length=5,
                choices=[
                    ('S2', 'Schedule II — Opioids / Strong Narcotics'),
                    ('S3', 'Schedule III — Moderate Controlled'),
                    ('S4', 'Schedule IV — Benzodiazepines / Controlled'),
                    ('S5', 'Schedule V — Cough Preparations / Mild Controlled'),
                ],
                help_text='WHO/national controlled drug schedule',
            ),
        ),

        # ── ControlledDrugEntry ──────────────────────────────────────────────
        migrations.CreateModel(
            name='ControlledDrugEntry',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('entry_type', models.CharField(
                    choices=[
                        ('STOCK_IN', 'Stock Received'),
                        ('DISPENSE', 'Dispensed to Patient'),
                        ('RETURN', 'Patient Return'),
                        ('WASTAGE', 'Wastage / Destroyed'),
                        ('ADJUSTMENT', 'Manual Adjustment'),
                    ],
                    max_length=20,
                )),
                ('quantity', models.DecimalField(decimal_places=2, max_digits=10)),
                ('balance_before', models.DecimalField(decimal_places=2, max_digits=10)),
                ('balance_after', models.DecimalField(decimal_places=2, max_digits=10)),
                ('witness_confirmed', models.BooleanField(
                    default=False,
                    help_text='Witness has counter-signed this entry',
                )),
                ('notes', models.TextField(blank=True)),
                ('entry_date', models.DateTimeField(default=django.utils.timezone.now)),
                ('drug', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='controlled_entries',
                    to='pharmacy.drug',
                )),
                ('batch', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='controlled_entries',
                    to='pharmacy.drugstock',
                )),
                ('patient', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='controlled_drug_entries',
                    to='patients.patient',
                )),
                ('dispensing', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='controlled_entries',
                    to='pharmacy.dispensing',
                )),
                ('performed_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='controlled_entries_made',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('witness', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='controlled_entries_witnessed',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Controlled Drug Entry',
                'verbose_name_plural': 'Controlled Drug Register',
                'ordering': ['-entry_date'],
            },
        ),

        # ── WardDrugReturn ───────────────────────────────────────────────────
        migrations.CreateModel(
            name='WardDrugReturn',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('return_number', models.CharField(max_length=30, unique=True)),
                ('quantity_returned', models.PositiveIntegerField()),
                ('reason', models.TextField(blank=True)),
                ('status', models.CharField(
                    choices=[
                        ('PENDING', 'Pending Pharmacy Acceptance'),
                        ('ACCEPTED', 'Accepted — Stock Restored'),
                        ('REJECTED', 'Rejected — Disposed'),
                    ],
                    default='PENDING',
                    max_length=20,
                )),
                ('returned_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('actioned_at', models.DateTimeField(blank=True, null=True)),
                ('rejection_reason', models.TextField(blank=True)),
                ('admission', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='drug_returns',
                    to='ipd.admission',
                )),
                ('drug', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='ward_returns',
                    to='pharmacy.drug',
                )),
                ('batch', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='ward_returns',
                    to='pharmacy.drugstock',
                )),
                ('returned_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='drug_returns_submitted',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('actioned_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='drug_returns_actioned',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-returned_at'],
            },
        ),

        # ── ChronicPrescription ──────────────────────────────────────────────
        migrations.CreateModel(
            name='ChronicPrescription',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('dose', models.CharField(max_length=100)),
                ('frequency', models.CharField(max_length=100)),
                ('quantity_per_refill', models.PositiveIntegerField()),
                ('refill_interval_days', models.PositiveIntegerField(default=30)),
                ('start_date', models.DateField(default=django.utils.timezone.now)),
                ('next_refill_date', models.DateField(blank=True, null=True)),
                ('last_refill_date', models.DateField(blank=True, null=True)),
                ('refill_count', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('notes', models.TextField(blank=True)),
                ('patient', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='chronic_prescriptions',
                    to='patients.patient',
                )),
                ('drug', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='chronic_prescriptions',
                    to='pharmacy.drug',
                )),
                ('prescribing_doctor', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='chronic_prescriptions_written',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['next_refill_date'],
                'unique_together': {('patient', 'drug')},
            },
        ),
    ]
