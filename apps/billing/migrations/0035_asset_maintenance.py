import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0034_erp_gl_accounts_entry_type'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MaintenanceSchedule',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('frequency', models.CharField(
                    choices=[('MONTHLY', 'Monthly'), ('QUARTERLY', 'Quarterly'),
                             ('BIANNUAL', 'Every 6 Months'), ('ANNUAL', 'Annual'),
                             ('AS_NEEDED', 'As Needed')],
                    default='ANNUAL', max_length=20)),
                ('next_due', models.DateField()),
                ('last_done', models.DateField(blank=True, null=True)),
                ('description', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('asset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='maintenance_schedules', to='billing.assetregister')),
                ('assigned_to', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='maintenance_assignments', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['next_due']},
        ),
        migrations.CreateModel(
            name='MaintenanceWorkOrder',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('wo_number', models.CharField(blank=True, max_length=20, unique=True)),
                ('maintenance_type', models.CharField(
                    choices=[('PREVENTIVE', 'Preventive'), ('CORRECTIVE', 'Corrective'),
                             ('INSPECTION', 'Inspection'), ('CALIBRATION', 'Calibration')],
                    default='PREVENTIVE', max_length=20)),
                ('status', models.CharField(
                    choices=[('PENDING', 'Pending'), ('IN_PROGRESS', 'In Progress'),
                             ('DONE', 'Completed'), ('DEFERRED', 'Deferred')],
                    default='PENDING', max_length=20)),
                ('description', models.TextField()),
                ('estimated_cost', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('actual_cost', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('findings', models.TextField(blank=True)),
                ('parts_used', models.TextField(blank=True)),
                ('asset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='work_orders', to='billing.assetregister')),
                ('schedule', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='work_orders', to='billing.maintenanceschedule')),
                ('created_by', models.ForeignKey(null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='maintenance_wos_created', to=settings.AUTH_USER_MODEL)),
                ('performed_by', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='maintenance_wos_performed', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
