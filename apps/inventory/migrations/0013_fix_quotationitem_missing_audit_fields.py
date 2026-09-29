"""
Fix QuotationItem table missing is_deleted / deleted_at columns.
Migration 0007 created the table without these AuditModel fields.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0012_alter_supplierinvoiceitem_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='quotationitem',
            name='is_deleted',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='quotationitem',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
