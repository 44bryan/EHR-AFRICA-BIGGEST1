from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0026_merge_20260717_1604'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='VisitTierChange',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('old_tier', models.CharField(max_length=12)),
                ('new_tier', models.CharField(max_length=12)),
                ('reason', models.CharField(blank=True, max_length=255)),
                ('visit', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='tier_changes',
                    to='patients.visit',
                )),
                ('changed_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='tier_changes_made',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Visit Tier Change',
                'verbose_name_plural': 'Visit Tier Changes',
                'ordering': ['-created_at'],
            },
        ),
    ]
