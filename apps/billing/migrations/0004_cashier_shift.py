# Generated migration for CashierShift model

import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0003_seed_service_prices'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CashierShift',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('shift_date', models.DateField(default=django.utils.timezone.localdate)),
                ('opened_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('opening_cash', models.DecimalField(
                    decimal_places=2, default=0, max_digits=12,
                    help_text='Cash float handed to cashier at shift start (FCFA)'
                )),
                ('closing_cash_declared', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=12, null=True,
                    help_text='Physical cash in drawer as counted and declared by cashier'
                )),
                ('status', models.CharField(
                    choices=[
                        ('OPEN', 'Open'),
                        ('CLOSED', 'Closed'),
                        ('SUBMITTED', 'Submitted to Chief Cashier'),
                        ('VERIFIED', 'Verified'),
                    ],
                    default='OPEN', max_length=20
                )),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
                ('verified_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('cashier', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='cashier_shifts',
                    to=settings.AUTH_USER_MODEL
                )),
                ('verified_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='verified_shifts',
                    to=settings.AUTH_USER_MODEL
                )),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL
                )),
            ],
            options={
                'verbose_name': 'Cashier Shift',
                'verbose_name_plural': 'Cashier Shifts',
                'ordering': ['-shift_date', '-opened_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='cashiershift',
            constraint=models.UniqueConstraint(
                fields=['cashier', 'shift_date'],
                name='unique_cashier_shift_per_day'
            ),
        ),
    ]
