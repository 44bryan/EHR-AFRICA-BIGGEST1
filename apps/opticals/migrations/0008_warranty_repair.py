"""Add OpticalWarranty and OpticalRepair models."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('opticals', '0007_lenspricematrix'),
        ('patients', '0035_visit_routing_note'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OpticalWarranty',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('order', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='warranty', to='opticals.opticalorder')),
                ('warranty_months', models.PositiveSmallIntegerField(default=12, help_text='Duration in months')),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('status', models.CharField(choices=[('ACTIVE', 'Active'), ('CLAIMED', 'Claimed'), ('EXPIRED', 'Expired'), ('VOIDED', 'Voided')], default='ACTIVE', max_length=10)),
                ('terms', models.TextField(blank=True, help_text='Warranty terms / coverage details')),
            ],
            options={
                'ordering': ['-start_date'],
                'verbose_name': 'Optical Warranty',
                'verbose_name_plural': 'Optical Warranties',
            },
        ),
        migrations.CreateModel(
            name='OpticalRepair',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('repair_number', models.CharField(max_length=30, unique=True)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='optical_repairs', to='patients.patient')),
                ('order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='repairs', to='opticals.opticalorder')),
                ('repair_type', models.CharField(choices=[
                    ('WARRANTY', 'Warranty Claim'), ('FRAME', 'Frame Repair / Adjustment'),
                    ('REMAKE', 'Lens Remake'), ('RELENS', 'Re-lens (New Prescription)'),
                    ('NOSEPAD', 'Nose Pad Replacement'), ('TEMPLE', 'Temple Arm Replacement'),
                    ('SCREW', 'Screw / Hinge Fix'), ('TINT', 'Re-tint'), ('OTHER', 'Other'),
                ], max_length=20)),
                ('status', models.CharField(choices=[
                    ('RECEIVED', 'Received'), ('IN_PROG', 'In Progress'),
                    ('COMPLETED', 'Completed'), ('RETURNED', 'Returned to Patient'),
                    ('CANCELLED', 'Cancelled'),
                ], default='RECEIVED', max_length=20)),
                ('description', models.TextField(help_text='What is broken / what the patient wants')),
                ('is_warranty_claim', models.BooleanField(default=False)),
                ('cost', models.DecimalField(decimal_places=2, default=0, help_text='Cost to patient (0 if warranty)', max_digits=10)),
                ('received_date', models.DateField(default=django.utils.timezone.now)),
                ('completed_date', models.DateField(blank=True, null=True)),
                ('returned_date', models.DateField(blank=True, null=True)),
                ('technician_notes', models.TextField(blank=True)),
                ('received_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='optical_repairs_received', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-received_date'],
            },
        ),
    ]
