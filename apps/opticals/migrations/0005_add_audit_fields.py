from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('opticals', '0004_optical_lab_job_audit_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ContactLensFitting
        migrations.AddField(
            model_name='contactlensfitting',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='contactlensfitting',
            name='updated_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
        # LowVisionAidDispensing
        migrations.AddField(
            model_name='lowvisionaiddispensing',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='lowvisionaiddispensing',
            name='updated_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
