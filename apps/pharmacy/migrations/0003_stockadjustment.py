from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacy', '0002_drugstock_manufacture_date'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='StockAdjustment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('reason', models.CharField(
                    choices=[
                        ('DAMAGE', 'Damaged / Broken'),
                        ('EXPIRED', 'Expired — Disposal'),
                        ('COUNT_UP', 'Physical Count — Surplus'),
                        ('COUNT_DOWN', 'Physical Count — Shortage'),
                        ('RETURN', 'Patient Return'),
                        ('THEFT', 'Suspected Theft / Pilferage'),
                        ('OTHER', 'Other'),
                    ],
                    max_length=20,
                )),
                ('quantity_before', models.IntegerField(help_text='Stock level before adjustment')),
                ('quantity_change', models.IntegerField(
                    help_text='Positive = stock added, Negative = stock removed'
                )),
                ('quantity_after', models.IntegerField(help_text='Stock level after adjustment')),
                ('notes', models.TextField(blank=True)),
                ('adjusted_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('batch', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='adjustments',
                    to='pharmacy.drugstock',
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
            options={
                'ordering': ['-adjusted_at'],
            },
        ),
    ]
