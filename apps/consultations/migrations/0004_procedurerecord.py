import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('consultations', '0003_allow_blank_presenting_complaint'),
        ('patients', '0018_patientconsent'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ProcedureRecord',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False, editable=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('procedure_date', models.DateField(auto_now_add=True)),
                ('procedure_type', models.CharField(
                    max_length=15,
                    choices=[
                        ('SLT', 'Selective Laser Trabeculoplasty (SLT)'),
                        ('ALT', 'Argon Laser Trabeculoplasty (ALT)'),
                        ('YAG_PI', 'YAG Peripheral Iridotomy'),
                        ('YAG_CAP', 'YAG Posterior Capsulotomy'),
                        ('YAG_VIT', 'YAG Vitreolysis'),
                        ('PRP', 'Panretinal Photocoagulation (PRP)'),
                        ('FOCAL', 'Focal / Grid Laser (Retina)'),
                        ('PHOTOCOAG', 'Laser Photocoagulation'),
                        ('CYCLO', 'Cyclophotcoagulation (CPC)'),
                        ('ANTI_VEGF', 'Intravitreal Anti-VEGF'),
                        ('IVT_STER', 'Intravitreal Steroid'),
                        ('SUBCONJ', 'Subconjunctival Injection'),
                        ('AC_PARA', 'Anterior Chamber Paracentesis'),
                        ('FB_REM', 'Foreign Body Removal'),
                        ('EPIL', 'Epilation'),
                        ('CHALAZION', 'Chalazion I&C'),
                        ('CONJ_BX', 'Conjunctival Biopsy'),
                        ('CORN_SC', 'Corneal Scraping / Swab'),
                        ('SUT_REM', 'Suture Removal'),
                        ('PTERYG', 'Pterygium Excision'),
                        ('OTHER', 'Other Procedure'),
                    ],
                )),
                ('eye', models.CharField(
                    max_length=2, default='NA',
                    choices=[('RE', 'Right Eye (OD)'), ('LE', 'Left Eye (OS)'),
                             ('BE', 'Both Eyes (OU)'), ('NA', 'Not Eye-specific')],
                )),
                ('urgency', models.CharField(
                    max_length=10, default='ROUTINE',
                    choices=[('ROUTINE', 'Routine'), ('URGENT', 'Urgent'), ('EMERGENCY', 'Emergency')],
                )),
                ('pre_iop_re',  models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True)),
                ('pre_iop_le',  models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True)),
                ('post_iop_re', models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True)),
                ('post_iop_le', models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True)),
                ('laser_energy', models.CharField(blank=True, max_length=80)),
                ('drug_used',    models.CharField(blank=True, max_length=200)),
                ('notes',        models.TextField(blank=True)),
                ('complications',models.TextField(blank=True)),
                ('consultation', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='procedures',
                    to='consultations.consultation',
                )),
                ('patient', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='procedures',
                    to='patients.patient',
                )),
                ('performed_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='procedures_performed',
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
            options={'ordering': ['-procedure_date', '-created_at'], 'verbose_name': 'Procedure Record'},
        ),
    ]
