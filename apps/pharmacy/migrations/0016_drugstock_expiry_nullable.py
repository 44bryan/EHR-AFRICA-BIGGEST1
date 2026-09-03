from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacy', '0015_add_missing_audit_columns'),
    ]

    operations = [
        migrations.AlterField(
            model_name='drugstock',
            name='expiry_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
