import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0004_cashier_shift'),
        ('patients', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ServiceWorkOrder',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('category', models.CharField(
                    choices=[
                        ('CONSULT', 'Consultation'),
                        ('INVEST', 'Investigation / Diagnostics'),
                        ('LAB', 'Laboratory'),
                        ('PHARMACY', 'Pharmacy'),
                        ('OPTICAL', 'Opticals'),
                        ('SURGICAL', 'Surgical Procedure'),
                        ('ADMISSION', 'Inpatient Admission'),
                        ('REG', 'Registration'),
                        ('OTHER', 'Other'),
                    ],
                    max_length=20,
                )),
                ('description', models.CharField(max_length=255)),
                ('status', models.CharField(
                    choices=[
                        ('PENDING', 'Pending'),
                        ('DONE', 'Done'),
                        ('CANCELLED', 'Cancelled'),
                    ],
                    default='PENDING',
                    max_length=20,
                )),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.CharField(blank=True, max_length=300)),
                ('completed_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='completed_work_orders',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('invoice', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='work_orders',
                    to='billing.invoice',
                )),
                ('invoice_item', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='work_orders',
                    to='billing.invoiceitem',
                )),
                ('patient', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='work_orders',
                    to='patients.patient',
                )),
            ],
            options={
                'verbose_name': 'Service Work Order',
                'verbose_name_plural': 'Service Work Orders',
                'ordering': ['created_at'],
            },
        ),
    ]
