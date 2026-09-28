# Generated manually — 4-eyes stock validation + GRN finance fields
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0008_alter_departmentreturnitem_options_and_more'),
        ('billing', '0026_recategorize_clinical_exams'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── GRNStatus gets two new values (AWAITING_VALIDATION, VALIDATED) ────
        migrations.AlterField(
            model_name='goodsreceivednote',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending Inspection'),
                    ('INSPECTED', 'Inspected'),
                    ('ACCEPTED', 'Accepted — Stock Updated'),
                    ('AWAITING_VALIDATION', 'Awaiting Finance Validation'),
                    ('VALIDATED', 'Validated — GL Posted'),
                    ('REJECTED', 'Rejected'),
                ],
                default='PENDING',
                max_length=25,
            ),
        ),
        # ── 4-Eyes fields on GoodsReceivedNote ────────────────────────────────
        migrations.AddField(
            model_name='goodsreceivednote',
            name='validated_by',
            field=models.ForeignKey(
                blank=True, null=True,
                help_text='Finance Director who validated this receipt',
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='grns_validated',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='goodsreceivednote',
            name='validated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='goodsreceivednote',
            name='validation_notes',
            field=models.TextField(blank=True, default='',
                                   help_text='Finance Director notes on validation'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='goodsreceivednote',
            name='journal_entry',
            field=models.ForeignKey(
                blank=True, null=True,
                help_text='GL journal entry created on validation',
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='grn_source',
                to='billing.journalentry',
            ),
        ),
        migrations.AddField(
            model_name='goodsreceivednote',
            name='environmental_certificate',
            field=models.BooleanField(default=False,
                                      help_text='Environmental compliance certificate'),
        ),
        # ── StockValidation model ─────────────────────────────────────────────
        migrations.CreateModel(
            name='StockValidation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('validation_type', models.CharField(
                    choices=[
                        ('GRN', 'Goods Received Note'),
                        ('ENTRY', 'Direct Stock Entry'),
                        ('EXIT', 'Stock Exit'),
                        ('DISPOSAL', 'Disposal / Wastage'),
                        ('ADJUSTMENT', 'Stock Adjustment'),
                        ('COUNT', 'Stock Count Variance'),
                        ('RETURN', 'Department Return'),
                        ('ISSUE', 'Requisition Issue'),
                    ],
                    max_length=15,
                )),
                ('status', models.CharField(
                    choices=[
                        ('PENDING', 'Pending Finance Validation'),
                        ('VALIDATED', 'Validated — GL Posted'),
                        ('REJECTED', 'Rejected by Finance'),
                    ],
                    default='PENDING',
                    max_length=15,
                )),
                ('source_id', models.UUIDField(help_text='PK of the source transaction')),
                ('reference', models.CharField(max_length=50, help_text='Transaction reference number')),
                ('description', models.TextField(blank=True)),
                ('total_value', models.DecimalField(
                    decimal_places=2, default=0, max_digits=14,
                    help_text='Total financial value of this transaction (XAF)',
                )),
                ('submitted_at', models.DateTimeField(auto_now_add=True)),
                ('validated_at', models.DateTimeField(blank=True, null=True)),
                ('validation_notes', models.TextField(blank=True)),
                ('submitted_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='stock_validations_submitted',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('validated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='stock_validations_reviewed',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('journal_entry', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='stock_validation_source',
                    to='billing.journalentry',
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
                'ordering': ['-submitted_at'],
            },
        ),
    ]
