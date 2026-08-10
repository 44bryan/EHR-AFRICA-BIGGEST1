from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('telemedicine', '0004_preconsultationintake'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TelePrescription',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('drug_name', models.CharField(max_length=200)),
                ('dose', models.CharField(max_length=100)),
                ('frequency', models.CharField(blank=True, max_length=100)),
                ('duration', models.CharField(blank=True, max_length=100)),
                ('route', models.CharField(blank=True, help_text='e.g. Oral, Topical, IV', max_length=60)),
                ('instructions', models.TextField(blank=True)),
                ('appointment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='prescriptions', to='telemedicine.teleappointment')),
                ('prescribed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tele_prescriptions_given', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Tele-Prescription Item',
                'ordering': ['created_at'],
            },
        ),
        migrations.CreateModel(
            name='TeleReferral',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('referral_to', models.CharField(help_text='Specialist / department / hospital', max_length=200)),
                ('urgency', models.CharField(choices=[('ROUTINE', 'Routine'), ('SOON', 'Soon — within a week'), ('URGENT', 'Urgent — within 24 hours'), ('EMERGENCY', 'Emergency — same day')], default='ROUTINE', max_length=20)),
                ('reason', models.TextField()),
                ('clinical_summary', models.TextField(blank=True)),
                ('notes', models.TextField(blank=True)),
                ('appointment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='referrals', to='telemedicine.teleappointment')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Tele-Referral',
                'ordering': ['-created_at'],
            },
        ),
    ]
