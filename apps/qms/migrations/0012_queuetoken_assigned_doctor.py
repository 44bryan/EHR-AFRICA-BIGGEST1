from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('qms', '0011_perf_indexes'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='queuetoken',
            name='assigned_doctor',
            field=models.ForeignKey(
                blank=True,
                help_text='VIP/Express only: specific doctor this patient is assigned to see.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='assigned_consultation_tokens',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
