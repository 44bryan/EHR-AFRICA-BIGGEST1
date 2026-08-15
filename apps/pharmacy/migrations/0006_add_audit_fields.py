from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacy', '0005_enterprise_additions'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ChronicPrescription
        migrations.AddField(
            model_name='chronicprescription',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='chronicprescription',
            name='updated_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
        # ControlledDrugEntry
        migrations.AddField(
            model_name='controlleddrugentry',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='controlleddrugentry',
            name='updated_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
        # WardDrugReturn
        migrations.AddField(
            model_name='warddrugreturn',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='warddrugreturn',
            name='updated_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
