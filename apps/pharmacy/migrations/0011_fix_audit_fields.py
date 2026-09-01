"""
Fix missing AuditModel fields (created_by, updated_by) on Head Pharmacist models.
Migration 0010 was written manually and missed these inherited FK columns.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('pharmacy', '0010_head_pharmacist_module'),
    ]

    operations = [
        # ── PharmacyLocation ──
        migrations.AddField(
            model_name='pharmacylocation',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='pharmacylocation',
            name='updated_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
        # ── StockTransfer ──
        migrations.AddField(
            model_name='stocktransfer',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='stocktransfer',
            name='updated_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
        # ── StockExit ──
        migrations.AddField(
            model_name='stockexit',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='stockexit',
            name='updated_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
        # ── DrugRecall ──
        migrations.AddField(
            model_name='drugrecall',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='drugrecall',
            name='updated_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
        # ── Dispensing: make patient nullable + add walk_in_name for OTC ──
        migrations.AlterField(
            model_name='dispensing',
            name='patient',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='dispensings', to='patients.patient',
            ),
        ),
        migrations.AddField(
            model_name='dispensing',
            name='walk_in_name',
            field=models.CharField(blank=True, max_length=150,
                                   help_text='Customer name for walk-in OTC sales (no patient record needed)'),
        ),
    ]
