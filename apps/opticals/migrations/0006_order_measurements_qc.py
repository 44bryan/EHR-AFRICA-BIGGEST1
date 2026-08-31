"""
Stage 3: Add dispensing measurements and QC verification fields to OpticalOrder.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('opticals', '0005_add_audit_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(model_name='opticalorder', name='mono_pd_re',
            field=models.DecimalField(blank=True, decimal_places=1, help_text='Monocular PD Right (mm)', max_digits=4, null=True)),
        migrations.AddField(model_name='opticalorder', name='mono_pd_le',
            field=models.DecimalField(blank=True, decimal_places=1, help_text='Monocular PD Left (mm)', max_digits=4, null=True)),
        migrations.AddField(model_name='opticalorder', name='fitting_height_re',
            field=models.DecimalField(blank=True, decimal_places=1, help_text='Fitting Height RE (mm)', max_digits=4, null=True)),
        migrations.AddField(model_name='opticalorder', name='fitting_height_le',
            field=models.DecimalField(blank=True, decimal_places=1, help_text='Fitting Height LE (mm)', max_digits=4, null=True)),
        migrations.AddField(model_name='opticalorder', name='vertex_distance',
            field=models.DecimalField(blank=True, decimal_places=1, help_text='Vertex Distance (mm)', max_digits=4, null=True)),
        migrations.AddField(model_name='opticalorder', name='pantoscopic_tilt',
            field=models.DecimalField(blank=True, decimal_places=1, help_text='Pantoscopic Tilt (degrees)', max_digits=4, null=True)),
        migrations.AddField(model_name='opticalorder', name='wrap_angle',
            field=models.DecimalField(blank=True, decimal_places=1, help_text='Frame Wrap / Face-form Angle (degrees)', max_digits=4, null=True)),
        migrations.AddField(model_name='opticalorder', name='qc_verified',
            field=models.BooleanField(default=False, help_text='Quality check passed by dispenser')),
        migrations.AddField(model_name='opticalorder', name='qc_verified_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='optical_qc_verified', to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name='opticalorder', name='qc_verified_at',
            field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='opticalorder', name='qc_notes',
            field=models.TextField(blank=True, help_text='QC remarks — power verification, alignment, cosmetic check')),
    ]
