from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('prescriptions', '0002_druginteraction'),
    ]

    operations = [
        migrations.AddField(
            model_name='opticalprescription',
            name='re_sphere_near',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name='opticalprescription',
            name='re_cylinder_near',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name='opticalprescription',
            name='re_axis_near',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='opticalprescription',
            name='re_va_near',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='opticalprescription',
            name='le_sphere_near',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name='opticalprescription',
            name='le_cylinder_near',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name='opticalprescription',
            name='le_axis_near',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='opticalprescription',
            name='le_va_near',
            field=models.CharField(blank=True, max_length=20),
        ),
    ]
