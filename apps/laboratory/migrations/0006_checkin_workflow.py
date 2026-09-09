"""Add check-in tracking fields to LabOrder."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('laboratory', '0005_iso15189_full_workflow'),
    ]

    operations = [
        migrations.AddField(
            model_name='laborder',
            name='checked_in_at',
            field=models.DateTimeField(
                blank=True, null=True,
                help_text='When patient physically arrived at lab for sample collection',
            ),
        ),
        migrations.AddField(
            model_name='laborder',
            name='checked_in_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='lab_checkins',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
