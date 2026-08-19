"""
Migration 0004 — ISO 15189 / JCI compliance additions:
  - SampleCollection.save() now uses sequential LAB-YYYYMMDD-NNNN IDs (code change only, no schema)
  - SampleRejection model (ISO 15189 §5.4.5)
  - LabResult.critical_acknowledged_by + critical_acknowledged_at (JCI IPSG.2)
  - LabResultAmendment model (ISO 15189 §5.8.3)
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('laboratory', '0003_alter_labtesttype_category'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── SampleRejection ──────────────────────────────────────────────────
        migrations.CreateModel(
            name='SampleRejection',
            fields=[
                ('id', models.UUIDField(primary_key=True, editable=False, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(db_index=True, default=False)),
                ('reason', models.CharField(
                    choices=[
                        ('HAEMOLYSED', 'Haemolysed sample'),
                        ('INSUFFICIENT', 'Insufficient volume'),
                        ('WRONG_CONTAINER', 'Wrong container / tube'),
                        ('UNLABELLED', 'Unlabelled / mislabelled'),
                        ('CLOTTED', 'Clotted sample'),
                        ('CONTAMINATED', 'Contaminated'),
                        ('DELAYED', 'Excessive transport delay'),
                        ('OTHER', 'Other — see notes'),
                    ],
                    max_length=20,
                )),
                ('notes', models.TextField(blank=True)),
                ('order', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='rejections',
                    to='laboratory.laborder',
                )),
                ('rejected_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'verbose_name': 'Sample Rejection', 'ordering': ['-created_at']},
        ),

        # ── LabResult — critical acknowledgement fields ───────────────────────
        migrations.AddField(
            model_name='labresult',
            name='critical_acknowledged_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='acknowledged_critical_results',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='labresult',
            name='critical_acknowledged_at',
            field=models.DateTimeField(blank=True, null=True),
        ),

        # ── LabResultAmendment ───────────────────────────────────────────────
        migrations.CreateModel(
            name='LabResultAmendment',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('original_value', models.CharField(max_length=200)),
                ('reason', models.TextField()),
                ('amended_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
                ('result', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='amendments',
                    to='laboratory.labresult',
                )),
            ],
            options={'verbose_name': 'Lab Result Amendment', 'ordering': ['-created_at']},
        ),
    ]
