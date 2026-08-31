"""
Stage 1: Pharmacy OTC flag on Dispensing + RxLineUnavailable tracking model.
"""
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacy', '0007_pharmacy_enterprise'),
        ('prescriptions', '0002_druginteraction'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Add is_otc flag to Dispensing
        migrations.AddField(
            model_name='dispensing',
            name='is_otc',
            field=models.BooleanField(
                default=False,
                help_text='True for over-the-counter / walk-in sales without a prescription',
            ),
        ),
        # RxLineUnavailable model
        migrations.CreateModel(
            name='RxLineUnavailable',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('reason', models.CharField(
                    choices=[
                        ('OUT_OF_STOCK', 'Out of Stock'),
                        ('EXPIRED', 'All Batches Expired'),
                        ('DISCONTINUED', 'Drug Discontinued'),
                        ('NOT_FORMULARY', 'Not in Formulary'),
                        ('DECLINED', 'Patient Declined'),
                        ('OTHER', 'Other'),
                    ],
                    max_length=20,
                )),
                ('notes', models.TextField(blank=True)),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('marked_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='rx_lines_marked_unavailable',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('prescription', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='unavailable_lines',
                    to='prescriptions.drugprescription',
                )),
                ('rx_item', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='unavailable',
                    to='prescriptions.drugprescriptionitem',
                )),
            ],
            options={
                'verbose_name': 'Unavailable Rx Line',
                'ordering': ['-created_at'],
            },
        ),
    ]
