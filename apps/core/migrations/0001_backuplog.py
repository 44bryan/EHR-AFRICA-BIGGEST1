from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='BackupLog',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('filename', models.CharField(blank=True, max_length=255)),
                ('output_path', models.CharField(blank=True, max_length=500)),
                ('size_mb', models.FloatField(blank=True, null=True)),
                ('status', models.CharField(
                    choices=[('SUCCESS', 'Success'), ('FAILED', 'Failed'), ('RUNNING', 'Running')],
                    default='RUNNING', max_length=10)),
                ('trigger', models.CharField(
                    choices=[('CELERY', 'Automated (Celery)'), ('MANUAL', 'Manual (Admin)'), ('CLI', 'CLI (manage.py)')],
                    default='CELERY', max_length=10)),
                ('duration_seconds', models.FloatField(blank=True, null=True)),
                ('error_message', models.TextField(blank=True)),
                ('copied_to_external', models.BooleanField(default=False)),
                ('external_path', models.CharField(blank=True, max_length=500)),
            ],
            options={
                'verbose_name': 'Backup Log',
                'verbose_name_plural': 'Backup Logs',
                'ordering': ['-created_at'],
            },
        ),
    ]
