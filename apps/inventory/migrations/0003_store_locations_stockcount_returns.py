"""
Add StoreLocation, StockCount, StockCountItem, DepartmentReturn, DepartmentReturnItem.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inventory', '0002_international_standard'),
    ]

    operations = [
        # ── StoreLocation ──
        migrations.CreateModel(
            name='StoreLocation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('name', models.CharField(max_length=100, unique=True)),
                ('location_type', models.CharField(choices=[
                    ('CENTRAL', 'Central Store'), ('SUB', 'Sub-Store'),
                    ('WARD', 'Ward Store'), ('THEATRE', 'Theatre Store'),
                    ('EMERGENCY', 'Emergency Store'),
                ], max_length=20)),
                ('address', models.TextField(blank=True, help_text='Physical location within facility')),
                ('is_active', models.BooleanField(default=True)),
                ('manager', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='managed_store_locations', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['name']},
        ),
        # ── StockCount ──
        migrations.CreateModel(
            name='StockCount',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('count_number', models.CharField(blank=True, max_length=30, unique=True)),
                ('count_date', models.DateField(default=django.utils.timezone.localdate)),
                ('status', models.CharField(choices=[
                    ('IN_PROGRESS', 'In Progress'), ('COMPLETED', 'Completed'),
                    ('APPROVED', 'Approved — Adjustments Applied'),
                ], default='IN_PROGRESS', max_length=15)),
                ('notes', models.TextField(blank=True)),
                ('counted_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name='stock_counts', to=settings.AUTH_USER_MODEL)),
                ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='approved_stock_counts', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-count_date']},
        ),
        # ── StockCountItem ──
        migrations.CreateModel(
            name='StockCountItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('system_quantity', models.PositiveIntegerField(help_text='Quantity per system at time of count')),
                ('physical_quantity', models.PositiveIntegerField(help_text='Actual count found')),
                ('variance', models.IntegerField(default=0, help_text='physical - system')),
                ('notes', models.CharField(blank=True, max_length=200)),
                ('stock_count', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='items', to='inventory.stockcount')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    to='inventory.inventoryitem')),
            ],
        ),
        # ── DepartmentReturn ──
        migrations.CreateModel(
            name='DepartmentReturn',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('return_number', models.CharField(blank=True, max_length=30, unique=True)),
                ('department', models.CharField(max_length=100)),
                ('status', models.CharField(choices=[
                    ('PENDING', 'Pending Acceptance'), ('ACCEPTED', 'Accepted — Stock Restored'),
                    ('REJECTED', 'Rejected'),
                ], default='PENDING', max_length=15)),
                ('notes', models.TextField(blank=True)),
                ('rejection_reason', models.TextField(blank=True)),
                ('returned_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name='store_returns', to=settings.AUTH_USER_MODEL)),
                ('received_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='received_store_returns', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        # ── DepartmentReturnItem ──
        migrations.CreateModel(
            name='DepartmentReturnItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('quantity', models.PositiveIntegerField()),
                ('condition', models.CharField(choices=[
                    ('GOOD', 'Good — Restock'), ('DAMAGED', 'Damaged — Write Off'),
                    ('EXPIRED', 'Expired'),
                ], default='GOOD', max_length=20)),
                ('notes', models.CharField(blank=True, max_length=200)),
                ('department_return', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='items', to='inventory.departmentreturn')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    to='inventory.inventoryitem')),
            ],
        ),
    ]
