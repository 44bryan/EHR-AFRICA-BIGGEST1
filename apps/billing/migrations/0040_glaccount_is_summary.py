from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0039_finance_module_additions'),
    ]

    operations = [
        migrations.AddField(
            model_name='glaccount',
            name='is_summary',
            field=models.BooleanField(
                default=False,
                help_text='Summary/parent account — aggregates children, never receives journal lines directly',
            ),
        ),
    ]
