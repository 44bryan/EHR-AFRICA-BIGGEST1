from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('prescriptions', '0003_optical_near_vision'),
    ]

    operations = [
        migrations.AlterField(
            model_name='opticalprescription',
            name='lens_type',
            field=models.CharField(blank=True, help_text='Comma-separated list of lens types', max_length=500),
        ),
    ]
