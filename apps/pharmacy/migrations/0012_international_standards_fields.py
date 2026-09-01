"""
Add WHO GPP, FIP, JCI MMU compliance fields to pharmacy models.

PharmacyLocation: storage_conditions, license_number, has_controlled_access
StockTransfer: approved_by, transport_conditions
StockExit: waste_classification, destruction_certificate, financial_impact
DrugRecall: recall_type, regulatory_reference, patients_notified, corrective_action
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacy', '0011_fix_audit_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── PharmacyLocation ──
        migrations.AddField(
            model_name='pharmacylocation',
            name='storage_conditions',
            field=models.CharField(
                blank=True, max_length=20,
                choices=[
                    ('AMBIENT', 'Ambient (15-25 °C)'),
                    ('COOL', 'Cool Room (2-8 °C)'),
                    ('FROZEN', 'Frozen (< -15 °C)'),
                    ('CONTROLLED', 'Controlled Room (20-25 °C)'),
                ],
                help_text='Primary storage temperature range',
            ),
        ),
        migrations.AddField(
            model_name='pharmacylocation',
            name='license_number',
            field=models.CharField(blank=True, max_length=50, help_text='Regulatory license/permit for this location'),
        ),
        migrations.AddField(
            model_name='pharmacylocation',
            name='has_controlled_access',
            field=models.BooleanField(default=False, help_text='Restricted access for controlled substances'),
        ),

        # ── StockTransfer ──
        migrations.AddField(
            model_name='stocktransfer',
            name='approved_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='transfers_approved', to=settings.AUTH_USER_MODEL,
                help_text='Manager who authorized this transfer',
            ),
        ),
        migrations.AddField(
            model_name='stocktransfer',
            name='transport_conditions',
            field=models.CharField(
                blank=True, max_length=20,
                choices=[
                    ('AMBIENT', 'Ambient'),
                    ('COLD_CHAIN', 'Cold Chain (2-8 °C)'),
                    ('FROZEN', 'Frozen'),
                ],
                help_text='Temperature conditions during transit',
            ),
        ),

        # ── StockExit ──
        migrations.AddField(
            model_name='stockexit',
            name='waste_classification',
            field=models.CharField(
                blank=True, max_length=20,
                choices=[
                    ('HAZARDOUS', 'Hazardous Pharmaceutical Waste'),
                    ('NON_HAZARDOUS', 'Non-Hazardous Waste'),
                    ('CYTOTOXIC', 'Cytotoxic Waste'),
                    ('CONTROLLED', 'Controlled Substance Waste'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='stockexit',
            name='destruction_certificate',
            field=models.CharField(blank=True, max_length=100, help_text='Certificate of Destruction reference number'),
        ),
        migrations.AddField(
            model_name='stockexit',
            name='financial_impact',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, help_text='Value of destroyed stock (cost price × quantity)'),
        ),

        # ── DrugRecall ──
        migrations.AddField(
            model_name='drugrecall',
            name='recall_type',
            field=models.CharField(
                blank=True, max_length=20,
                choices=[
                    ('MANUFACTURER', 'Manufacturer Initiated'),
                    ('REGULATORY', 'Regulatory Authority (MINSANTE/WHO)'),
                    ('HOSPITAL', 'Hospital Initiated (Internal QC)'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='drugrecall',
            name='regulatory_reference',
            field=models.CharField(blank=True, max_length=100, help_text='FDA/MINSANTE/WHO reference number'),
        ),
        migrations.AddField(
            model_name='drugrecall',
            name='patients_notified',
            field=models.BooleanField(default=False, help_text='Have affected patients been contacted?'),
        ),
        migrations.AddField(
            model_name='drugrecall',
            name='corrective_action',
            field=models.TextField(blank=True, help_text='Corrective/preventive action taken or planned'),
        ),
    ]
