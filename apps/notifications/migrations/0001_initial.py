from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notification_type', models.CharField(
                    choices=[
                        ('LAB_RESULT', 'Lab Result Ready'),
                        ('INVESTIGATION', 'Investigation Result'),
                        ('PRESCRIPTION', 'Prescription Waiting'),
                        ('BILLING', 'Billing / Payment'),
                        ('APPOINTMENT', 'Appointment Reminder'),
                        ('DISCHARGE', 'Patient Discharged'),
                        ('LOW_STOCK', 'Low Drug Stock'),
                        ('SYSTEM', 'System Alert'),
                        ('GENERAL', 'General'),
                    ],
                    default='GENERAL', max_length=30,
                )),
                ('priority', models.CharField(
                    choices=[
                        ('LOW', 'Low'), ('NORMAL', 'Normal'), ('HIGH', 'High'), ('URGENT', 'Urgent'),
                    ],
                    default='NORMAL', max_length=10,
                )),
                ('title', models.CharField(max_length=200)),
                ('message', models.TextField(blank=True)),
                ('link', models.CharField(blank=True, help_text='Optional URL to navigate to on click', max_length=500)),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('recipient', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='notifications',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['recipient', 'is_read'], name='notif_recip_read_idx'),
        ),
    ]
