from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('investigations', '0001_initial'),
        ('consultations', '0001_initial'),
        ('patients', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ImagingStudy',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('modality', models.CharField(choices=[
                    ('OCT', 'OCT (Optical Coherence Tomography)'),
                    ('FFA', 'Fundus Fluorescein Angiography'),
                    ('FUNDUS', 'Fundus Photography'),
                    ('PENTACAM', 'Pentacam / Corneal Topography'),
                    ('BIOMETRY', 'Biometry (IOL Master / A-Scan)'),
                    ('BSCAN', 'B-Scan Ultrasound'),
                    ('PERIMETRY', 'Visual Field / Perimetry'),
                    ('XRAY', 'X-Ray'),
                    ('CT', 'CT Scan'),
                    ('MRI', 'MRI'),
                    ('OTHER', 'Other'),
                ], max_length=20)),
                ('study_date', models.DateField(blank=True, null=True)),
                ('description', models.CharField(max_length=255)),
                ('study_uid', models.CharField(blank=True, max_length=200)),
                ('accession_number', models.CharField(blank=True, max_length=50)),
                ('series_count', models.PositiveSmallIntegerField(default=1)),
                ('viewer_url', models.URLField(blank=True, max_length=500)),
                ('report', models.TextField(blank=True)),
                ('is_reported', models.BooleanField(default=False)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='imaging_studies', to='patients.patient')),
                ('consultation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='imaging_studies', to='consultations.consultation')),
                ('order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='imaging_studies', to='investigations.investigationorder')),
                ('ordered_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ordered_imaging', to=settings.AUTH_USER_MODEL)),
                ('reported_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='imaging_reports', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Imaging Study',
                'verbose_name_plural': 'Imaging Studies',
                'ordering': ['-study_date', '-created_at'],
            },
        ),
    ]
