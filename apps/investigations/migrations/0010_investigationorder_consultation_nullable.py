"""Make InvestigationOrder.consultation nullable for nurse-initiated exams."""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('investigations', '0009_acquisitionrecord_deleted_at_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='investigationorder',
            name='consultation',
            field=models.ForeignKey(
                blank=True,
                help_text='Null when exam is ordered at triage (nurse-initiated, before consultation).',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='investigation_orders',
                to='consultations.consultation',
            ),
        ),
    ]
