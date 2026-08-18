from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('investigations', '0003_imagingstudy_updated_by_alter_imagingstudy_report_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='investigationtype',
            name='unit_price',
            field=models.DecimalField(
                max_digits=10, decimal_places=2, default=0,
                help_text='Price charged per investigation (FCFA)'
            ),
        ),
        migrations.AddField(
            model_name='investigationorder',
            name='location',
            field=models.CharField(
                max_length=10,
                choices=[('CLINIC', 'Clinic'), ('OUTREACH', 'Outreach / Field')],
                default='CLINIC',
                db_index=True,
                help_text='Where the investigation was performed',
            ),
        ),
    ]
