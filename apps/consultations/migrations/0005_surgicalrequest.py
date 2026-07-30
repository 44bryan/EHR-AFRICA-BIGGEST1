import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('consultations', '0004_procedurerecord'),
        ('patients', '0028_visittierchange_is_deleted'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SurgicalRequest',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False, editable=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('surgery_type', models.CharField(
                    max_length=20,
                    choices=[
                        ('CATARACT',   'Cataract Extraction (PHACO/ECCE)'),
                        ('TRAB',       'Trabeculectomy'),
                        ('PTERYGIUM',  'Pterygium Excision'),
                        ('SQUINT',     'Squint Correction (Strabismus)'),
                        ('DCR',        'Dacryocystorhinostomy (DCR)'),
                        ('VITRECTOMY', 'Vitrectomy (PPV)'),
                        ('PKP',        'Penetrating Keratoplasty (Corneal Graft)'),
                        ('RRD',        'Retinal Detachment Repair'),
                        ('ENUCLEATION','Enucleation'),
                        ('EVISC',      'Evisceration'),
                        ('OCULOPLASTY','Oculoplastic Procedure'),
                        ('GLAUC_DRN',  'Glaucoma Drainage Device'),
                        ('OTHER',      'Other Surgery'),
                    ],
                )),
                ('eye', models.CharField(
                    max_length=2, default='NA',
                    choices=[('RE', 'Right Eye (OD)'), ('LE', 'Left Eye (OS)'), ('BE', 'Both Eyes (OU)'), ('NA', 'Not Eye-specific')],
                )),
                ('urgency', models.CharField(
                    max_length=10, default='ELECTIVE',
                    choices=[('ELECTIVE', 'Elective'), ('URGENT', 'Urgent (within 1 week)'), ('EMERGENCY', 'Emergency (same day)')],
                )),
                ('status', models.CharField(
                    max_length=12, default='REQUESTED',
                    choices=[('REQUESTED', 'Requested'), ('SCHEDULED', 'Scheduled'), ('COMPLETED', 'Completed'), ('CANCELLED', 'Cancelled')],
                )),
                ('pre_op_notes',   models.TextField(blank=True)),
                ('scheduled_date', models.DateField(blank=True, null=True)),
                ('theatre_notes',  models.TextField(blank=True)),
                ('consultation', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='surgical_requests',
                    to='consultations.consultation',
                )),
                ('patient', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='surgical_requests',
                    to='patients.patient',
                )),
                ('requested_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='surgical_requests_made',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-created_at'], 'verbose_name': 'Surgical Request'},
        ),
    ]
