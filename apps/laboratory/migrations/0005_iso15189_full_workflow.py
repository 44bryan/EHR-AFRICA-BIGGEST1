"""
Full ISO 15189 laboratory workflow — four independent state machines.
New models: OrderSet, QCRecord, AutoverificationRule, SendOutTest,
CultureResult, OrganismIdentification, AntibioticSensitivity,
CumulativeAntibiogram, HistopathologySpecimen, ResultAcknowledgment, TATTimestamp.
Enhanced: LabTestType, LabOrder, SampleCollection, LabResult, LabResultAmendment.
"""
import uuid
import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('laboratory', '0004_iso15189_compliance'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('consultations', '0001_initial'),
        ('patients', '0001_initial'),
    ]

    operations = [
        # ═══════════════════════════════════════════════════════════════════
        # LabTestType enhancements
        # ═══════════════════════════════════════════════════════════════════
        migrations.AddField(
            model_name='labtesttype',
            name='loinc_code',
            field=models.CharField(blank=True, db_index=True, max_length=20,
                                   help_text='LOINC code for interoperability'),
        ),
        migrations.AddField(
            model_name='labtesttype',
            name='container_type',
            field=models.CharField(blank=True, max_length=20,
                                   choices=[('EDTA_PURPLE','EDTA (Purple top)'),('PLAIN_RED','Plain / SST (Red top)'),
                                            ('CITRATE_BLUE','Citrate (Blue top)'),('FLUORIDE_GREY','Fluoride Oxalate (Grey top)'),
                                            ('HEPARIN_GREEN','Heparin (Green top)'),('URINE_CUP','Urine Cup'),
                                            ('SWAB_TUBE','Swab / Transport tube'),('STERILE_CONT','Sterile Container'),
                                            ('SLIDE','Glass Slide'),('FORMALIN_POT','Formalin Pot (Histology)'),('OTHER','Other')]),
        ),
        migrations.AddField(
            model_name='labtesttype',
            name='min_volume_ml',
            field=models.DecimalField(blank=True, null=True, max_digits=6, decimal_places=2),
        ),
        migrations.AddField(
            model_name='labtesttype',
            name='patient_prep',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='labtesttype',
            name='method',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='labtesttype',
            name='work_area',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='labtesttype',
            name='is_send_out',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='labtesttype',
            name='default_referral_lab',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='labtesttype',
            name='critical_low',
            field=models.DecimalField(blank=True, null=True, max_digits=10, decimal_places=3),
        ),
        migrations.AddField(
            model_name='labtesttype',
            name='critical_high',
            field=models.DecimalField(blank=True, null=True, max_digits=10, decimal_places=3),
        ),
        migrations.AddField(
            model_name='labtesttype',
            name='delta_check_percent',
            field=models.DecimalField(blank=True, null=True, max_digits=5, decimal_places=1),
        ),
        migrations.AddField(
            model_name='labtesttype',
            name='delta_check_hours',
            field=models.PositiveIntegerField(default=168),
        ),

        # ═══════════════════════════════════════════════════════════════════
        # LabTestCategory expansion (handled by choices, no migration needed)
        # ═══════════════════════════════════════════════════════════════════

        # ═══════════════════════════════════════════════════════════════════
        # OrderSet (panels / workups)
        # ═══════════════════════════════════════════════════════════════════
        migrations.CreateModel(
            name='OrderSet',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100, unique=True)),
                ('code', models.CharField(max_length=20, unique=True)),
                ('description', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('tests', models.ManyToManyField(related_name='order_sets', to='laboratory.labtesttype')),
            ],
            options={'ordering': ['name'], 'verbose_name': 'Order Set / Panel'},
        ),

        # ═══════════════════════════════════════════════════════════════════
        # LabOrder enhancements — payment + specimen state machines
        # ═══════════════════════════════════════════════════════════════════
        migrations.AddField(
            model_name='laborder',
            name='payment_status',
            field=models.CharField(max_length=15, default='UNPAID',
                                   choices=[('UNPAID','Unpaid'),('PAID','Paid'),('INSURED','Insurance / Third-party'),
                                            ('WAIVED','Waived (Indigent)'),('STAT_OVERRIDE','STAT Override — Bill Later'),
                                            ('PREPAID','Pre-paid Package / Deposit'),('BILL_LATER','Bill Later (Authorised)')]),
        ),
        migrations.AddField(
            model_name='laborder',
            name='payment_authorized_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='authorized_lab_payments', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='laborder',
            name='payment_authorization_reason',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='laborder',
            name='payment_authorized_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='laborder',
            name='specimen_status',
            field=models.CharField(max_length=15, default='PENDING',
                                   choices=[('PENDING','Pending Collection'),('COLLECTED','Collected'),
                                            ('IN_TRANSIT','In Transit'),('RECEIVED','Received at Lab'),
                                            ('REJECTED','Rejected'),('RE_COLLECT','Re-collection Required')]),
        ),
        migrations.AddField(
            model_name='laborder',
            name='icd10_code',
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name='laborder',
            name='duplicate_warning_acknowledged',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='laborder',
            name='order_set',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    to='laboratory.orderset'),
        ),

        # ═══════════════════════════════════════════════════════════════════
        # SampleCollection enhancements
        # ═══════════════════════════════════════════════════════════════════
        migrations.AddField(
            model_name='samplecollection',
            name='identity_verified',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='samplecollection',
            name='identity_method',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='samplecollection',
            name='container_used',
            field=models.CharField(blank=True, max_length=20,
                                   choices=[('EDTA_PURPLE','EDTA (Purple top)'),('PLAIN_RED','Plain / SST (Red top)'),
                                            ('CITRATE_BLUE','Citrate (Blue top)'),('FLUORIDE_GREY','Fluoride Oxalate (Grey top)'),
                                            ('HEPARIN_GREEN','Heparin (Green top)'),('URINE_CUP','Urine Cup'),
                                            ('SWAB_TUBE','Swab / Transport tube'),('STERILE_CONT','Sterile Container'),
                                            ('SLIDE','Glass Slide'),('FORMALIN_POT','Formalin Pot (Histology)'),('OTHER','Other')]),
        ),
        migrations.AddField(
            model_name='samplecollection',
            name='volume_ml',
            field=models.DecimalField(blank=True, null=True, max_digits=6, decimal_places=2),
        ),
        migrations.AddField(
            model_name='samplecollection',
            name='collection_site',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='samplecollection',
            name='fasting_status',
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='samplecollection',
            name='received_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='received_samples', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='samplecollection',
            name='received_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='samplecollection',
            name='condition_on_arrival',
            field=models.CharField(default='GOOD', max_length=15,
                                   choices=[('GOOD','Good'),('HAEMOLYSED','Haemolysed'),('LIPEMIC','Lipemic'),
                                            ('ICTERIC','Icteric'),('CLOTTED','Clotted'),('DAMAGED','Damaged / Leaking')]),
        ),
        # Alter sample_type to include new choices
        migrations.AlterField(
            model_name='samplecollection',
            name='sample_type',
            field=models.CharField(max_length=20,
                                   choices=[('BLOOD_EDTA','Blood — EDTA'),('BLOOD_PLAIN','Blood — Plain'),
                                            ('BLOOD_FLUORIDE','Blood — Fluoride Oxalate'),('BLOOD_CITRATE','Blood — Citrate'),
                                            ('BLOOD_HEPARIN','Blood — Heparin'),('URINE','Urine'),('SWAB','Swab'),
                                            ('AQUEOUS','Aqueous Humour'),('VITREOUS','Vitreous'),
                                            ('CORNEAL_SCRAPE','Corneal Scraping'),('CONJUNCTIVAL','Conjunctival Swab'),
                                            ('CSF','Cerebrospinal Fluid'),('TISSUE','Tissue / Biopsy'),('OTHER','Other')]),
        ),
        # Fix related_name on collected_by
        migrations.AlterField(
            model_name='samplecollection',
            name='collected_by',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='collected_samples', to=settings.AUTH_USER_MODEL),
        ),

        # ═══════════════════════════════════════════════════════════════════
        # SampleRejection — new rejection reasons
        # ═══════════════════════════════════════════════════════════════════
        migrations.AlterField(
            model_name='samplerejection',
            name='reason',
            field=models.CharField(max_length=20,
                                   choices=[('HAEMOLYSED','Haemolysed sample'),('INSUFFICIENT','Insufficient volume'),
                                            ('WRONG_CONTAINER','Wrong container / tube'),('UNLABELLED','Unlabelled / mislabelled'),
                                            ('CLOTTED','Clotted sample'),('CONTAMINATED','Contaminated'),
                                            ('DELAYED','Excessive transport delay'),('WRONG_PATIENT','Wrong patient / mismatch'),
                                            ('WRONG_VOLUME','Wrong fill volume'),('OTHER','Other — see notes')]),
        ),

        # ═══════════════════════════════════════════════════════════════════
        # LabResult enhancements — result state machine
        # ═══════════════════════════════════════════════════════════════════
        migrations.AddField(
            model_name='labresult',
            name='result_status',
            field=models.CharField(max_length=15, default='PENDING',
                                   choices=[('PENDING','Pending'),('IN_PROGRESS','In Progress'),
                                            ('PRELIMINARY','Preliminary'),('TECH_VALID','Technically Validated'),
                                            ('AUTHORIZED','Authorised (Biologist)'),('RELEASED','Released to Clinician'),
                                            ('AMENDED','Amended (see version history)')]),
        ),
        migrations.AddField(
            model_name='labresult',
            name='authorized_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='authorized_lab_results', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='labresult',
            name='authorized_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='labresult',
            name='released_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='labresult',
            name='auto_verified',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='labresult',
            name='version_number',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='labresult',
            name='delta_check_value',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='labresult',
            name='delta_check_flagged',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='labresult',
            name='delta_check_percent',
            field=models.DecimalField(blank=True, null=True, max_digits=6, decimal_places=1),
        ),
        migrations.AddField(
            model_name='labresult',
            name='critical_notified_to',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='labresult',
            name='critical_read_back_confirmed',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='labresult',
            name='critical_read_back_at',
            field=models.DateTimeField(blank=True, null=True),
        ),

        # ═══════════════════════════════════════════════════════════════════
        # LabResultAmendment enhancements
        # ═══════════════════════════════════════════════════════════════════
        migrations.AddField(
            model_name='labresultamendment',
            name='new_value',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='labresultamendment',
            name='version_number',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='labresultamendment',
            name='doctor_re_notified',
            field=models.BooleanField(default=False),
        ),

        # ═══════════════════════════════════════════════════════════════════
        # ResultAcknowledgment — doctor seen/unseen tracking
        # ═══════════════════════════════════════════════════════════════════
        migrations.CreateModel(
            name='ResultAcknowledgment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('acknowledged_at', models.DateTimeField(auto_now_add=True)),
                ('notes', models.TextField(blank=True)),
                ('result', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                             related_name='acknowledgments', to='laboratory.labresult')),
                ('acknowledged_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                       related_name='acknowledged_results', to=settings.AUTH_USER_MODEL)),
            ],
            options={'unique_together': {('result', 'acknowledged_by')},
                     'ordering': ['-acknowledged_at'], 'verbose_name': 'Result Acknowledgment'},
        ),

        # ═══════════════════════════════════════════════════════════════════
        # QCRecord — Levey-Jennings / Westgard
        # ═══════════════════════════════════════════════════════════════════
        migrations.CreateModel(
            name='QCRecord',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('run_date', models.DateTimeField()),
                ('qc_material', models.CharField(max_length=100)),
                ('lot_number', models.CharField(max_length=50)),
                ('level', models.CharField(max_length=10, choices=[('LOW','Low'),('NORMAL','Normal'),('HIGH','High')])),
                ('target_value', models.DecimalField(max_digits=10, decimal_places=3)),
                ('observed_value', models.DecimalField(max_digits=10, decimal_places=3)),
                ('target_sd', models.DecimalField(max_digits=8, decimal_places=3)),
                ('calculated_z_score', models.DecimalField(blank=True, null=True, max_digits=6, decimal_places=2)),
                ('westgard_rule', models.CharField(default='NONE', max_length=10,
                    choices=[('NONE','No violation'),('1_2S','1-2s warning'),('1_3S','1-3s rejection'),
                             ('2_2S','2-2s rejection'),('R_4S','R-4s rejection'),
                             ('4_1S','4-1s rejection'),('10X','10x rejection')])),
                ('is_acceptable', models.BooleanField(default=True)),
                ('reagent_lot', models.CharField(blank=True, max_length=50)),
                ('reagent_expiry', models.DateField(blank=True, null=True)),
                ('calibration_date', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('corrective_action', models.TextField(blank=True)),
                ('test_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                                related_name='qc_records', to='laboratory.labtesttype')),
                ('performed_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                   to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                 related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                 related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-run_date'], 'verbose_name': 'QC Record'},
        ),

        # ═══════════════════════════════════════════════════════════════════
        # AutoverificationRule
        # ═══════════════════════════════════════════════════════════════════
        migrations.CreateModel(
            name='AutoverificationRule',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=False)),
                ('min_value', models.DecimalField(blank=True, null=True, max_digits=10, decimal_places=3)),
                ('max_value', models.DecimalField(blank=True, null=True, max_digits=10, decimal_places=3)),
                ('max_delta_percent', models.DecimalField(blank=True, null=True, max_digits=5, decimal_places=1)),
                ('require_qc_pass', models.BooleanField(default=True)),
                ('require_no_flags', models.BooleanField(default=True)),
                ('test_type', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                                    related_name='autoverification_rule', to='laboratory.labtesttype')),
            ],
            options={'verbose_name': 'Autoverification Rule'},
        ),

        # ═══════════════════════════════════════════════════════════════════
        # SendOutTest — referral lab tracking
        # ═══════════════════════════════════════════════════════════════════
        migrations.CreateModel(
            name='SendOutTest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('referral_lab_name', models.CharField(max_length=200)),
                ('referral_lab_address', models.TextField(blank=True)),
                ('referral_lab_phone', models.CharField(blank=True, max_length=20)),
                ('status', models.CharField(default='PENDING', max_length=15,
                    choices=[('PENDING','Pending Dispatch'),('DISPATCHED','Dispatched'),('IN_TRANSIT','In Transit'),
                             ('RECEIVED','Received by Ref Lab'),('RESULTED','Result Received'),('CANCELLED','Cancelled')])),
                ('dispatch_date', models.DateTimeField(blank=True, null=True)),
                ('courier', models.CharField(blank=True, max_length=100)),
                ('tracking_number', models.CharField(blank=True, max_length=100)),
                ('expected_return_date', models.DateField(blank=True, null=True)),
                ('actual_return_date', models.DateField(blank=True, null=True)),
                ('external_accession_number', models.CharField(blank=True, max_length=50)),
                ('external_report_file', models.FileField(blank=True, upload_to='lab/sendout_reports/%Y/%m/')),
                ('external_cost', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('markup_percentage', models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ('order_item', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                                     related_name='send_out', to='laboratory.laborderitem')),
                ('dispatched_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                    related_name='dispatched_sendouts', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                 related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                 related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at'], 'verbose_name': 'Send-Out Test'},
        ),

        # ═══════════════════════════════════════════════════════════════════
        # Microbiology — CultureResult
        # ═══════════════════════════════════════════════════════════════════
        migrations.CreateModel(
            name='CultureResult',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('specimen_source', models.CharField(max_length=50)),
                ('gram_stain_result', models.TextField(blank=True)),
                ('gram_stain_at', models.DateTimeField(blank=True, null=True)),
                ('koh_mount_result', models.TextField(blank=True)),
                ('koh_mount_at', models.DateTimeField(blank=True, null=True)),
                ('culture_media', models.TextField(blank=True)),
                ('incubation_temp', models.CharField(blank=True, max_length=20)),
                ('incubation_atmosphere', models.CharField(blank=True, max_length=30)),
                ('growth_status', models.CharField(default='PENDING', max_length=20,
                    choices=[('PENDING','Pending'),('NO_GROWTH_24H','No Growth at 24h'),
                             ('NO_GROWTH_48H','No Growth at 48h'),('NO_GROWTH_FINAL','No Growth (Final)'),
                             ('GROWTH_24H','Growth at 24h'),('GROWTH_48H','Growth at 48h'),
                             ('GROWTH_72H','Growth at 72h'),('GROWTH_EXTENDED','Growth (Extended Culture)')])),
                ('culture_read_24h', models.TextField(blank=True)),
                ('culture_read_24h_at', models.DateTimeField(blank=True, null=True)),
                ('culture_read_48h', models.TextField(blank=True)),
                ('culture_read_48h_at', models.DateTimeField(blank=True, null=True)),
                ('culture_read_72h', models.TextField(blank=True)),
                ('culture_read_72h_at', models.DateTimeField(blank=True, null=True)),
                ('final_report', models.TextField(blank=True)),
                ('final_report_at', models.DateTimeField(blank=True, null=True)),
                ('is_preliminary', models.BooleanField(default=True)),
                ('order_item', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                                     related_name='culture', to='laboratory.laborderitem')),
                ('gram_stain_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                    related_name='gram_stains', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                 related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                 related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at'], 'verbose_name': 'Culture Result'},
        ),

        # ═══════════════════════════════════════════════════════════════════
        # Microbiology — OrganismIdentification
        # ═══════════════════════════════════════════════════════════════════
        migrations.CreateModel(
            name='OrganismIdentification',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organism_name', models.CharField(max_length=200)),
                ('organism_code', models.CharField(blank=True, max_length=20)),
                ('colony_count', models.CharField(blank=True, max_length=30)),
                ('identification_method', models.CharField(blank=True, max_length=50)),
                ('is_significant', models.BooleanField(default=True)),
                ('notes', models.TextField(blank=True)),
                ('culture', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                              related_name='organisms', to='laboratory.cultureresult')),
            ],
            options={'ordering': ['organism_name'], 'verbose_name': 'Organism Identification'},
        ),

        # ═══════════════════════════════════════════════════════════════════
        # Microbiology — AntibioticSensitivity
        # ═══════════════════════════════════════════════════════════════════
        migrations.CreateModel(
            name='AntibioticSensitivity',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('antibiotic_name', models.CharField(max_length=100)),
                ('antibiotic_code', models.CharField(blank=True, max_length=10)),
                ('sensitivity', models.CharField(max_length=2,
                    choices=[('S','Sensitive'),('I','Intermediate'),('R','Resistant'),('NT','Not Tested')])),
                ('zone_diameter_mm', models.DecimalField(blank=True, null=True, max_digits=5, decimal_places=1)),
                ('mic_value', models.CharField(blank=True, max_length=20)),
                ('method', models.CharField(default='DISK', max_length=10,
                    choices=[('DISK','Disk Diffusion (Kirby-Bauer)'),('ETEST','E-test'),
                             ('VITEK','VITEK / Automated'),('BROTH','Broth Microdilution'),('MANUAL','Manual')])),
                ('organism', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                               related_name='sensitivities', to='laboratory.organismidentification')),
            ],
            options={'ordering': ['antibiotic_name'], 'verbose_name': 'Antibiotic Sensitivity',
                     'verbose_name_plural': 'Antibiotic Sensitivities'},
        ),

        # ═══════════════════════════════════════════════════════════════════
        # Microbiology — CumulativeAntibiogram
        # ═══════════════════════════════════════════════════════════════════
        migrations.CreateModel(
            name='CumulativeAntibiogram',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organism_name', models.CharField(max_length=200)),
                ('antibiotic_name', models.CharField(max_length=100)),
                ('period_start', models.DateField()),
                ('period_end', models.DateField()),
                ('total_isolates', models.PositiveIntegerField()),
                ('sensitive_count', models.PositiveIntegerField()),
                ('intermediate_count', models.PositiveIntegerField(default=0)),
                ('resistant_count', models.PositiveIntegerField(default=0)),
            ],
            options={'unique_together': {('organism_name', 'antibiotic_name', 'period_start', 'period_end')},
                     'ordering': ['organism_name', 'antibiotic_name'], 'verbose_name': 'Cumulative Antibiogram'},
        ),

        # ═══════════════════════════════════════════════════════════════════
        # Histopathology
        # ═══════════════════════════════════════════════════════════════════
        migrations.CreateModel(
            name='HistopathologySpecimen',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('accession_number', models.CharField(max_length=30, unique=True)),
                ('specimen_site', models.CharField(max_length=100)),
                ('specimen_type', models.CharField(blank=True, max_length=50)),
                ('laterality', models.CharField(blank=True, max_length=5)),
                ('clinical_history', models.TextField()),
                ('status', models.CharField(default='ACCESSIONED', max_length=15,
                    choices=[('ACCESSIONED','Accessioned'),('GROSSING','Grossing'),('PROCESSING','Tissue Processing'),
                             ('CUTTING','Microtomy / Cutting'),('STAINING','Staining'),('REPORTING','Reporting'),
                             ('FINALIZED','Finalized'),('ADDENDUM','Addendum Issued')])),
                ('gross_description', models.TextField(blank=True)),
                ('gross_at', models.DateTimeField(blank=True, null=True)),
                ('cassette_count', models.PositiveIntegerField(default=0)),
                ('block_count', models.PositiveIntegerField(default=0)),
                ('microscopic_description', models.TextField(blank=True)),
                ('diagnosis', models.TextField(blank=True)),
                ('snomed_code', models.CharField(blank=True, max_length=20)),
                ('icd_o_code', models.CharField(blank=True, max_length=20)),
                ('special_stains', models.JSONField(blank=True, default=list)),
                ('ihc_stains', models.JSONField(blank=True, default=list)),
                ('reported_at', models.DateTimeField(blank=True, null=True)),
                ('storage_location', models.CharField(blank=True, max_length=100)),
                ('addendum_text', models.TextField(blank=True)),
                ('addendum_at', models.DateTimeField(blank=True, null=True)),
                ('order_item', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                                     related_name='histopath', to='laboratory.laborderitem')),
                ('gross_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                               related_name='grossed_specimens', to=settings.AUTH_USER_MODEL)),
                ('pathologist', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                   related_name='pathology_reports', to=settings.AUTH_USER_MODEL)),
                ('addendum_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                   related_name='pathology_addenda', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                 related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                 related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at'], 'verbose_name': 'Histopathology Specimen'},
        ),

        # ═══════════════════════════════════════════════════════════════════
        # TAT Timestamp — transition audit trail
        # ═══════════════════════════════════════════════════════════════════
        migrations.CreateModel(
            name='TATTimestamp',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('event', models.CharField(max_length=20,
                    choices=[('ORDERED','Order Placed'),('PAYMENT_CLEARED','Payment Cleared'),
                             ('COLLECTED','Specimen Collected'),('RECEIVED_AT_LAB','Received at Lab'),
                             ('REJECTED','Specimen Rejected'),('ANALYSIS_STARTED','Analysis Started'),
                             ('RESULT_ENTERED','Result Entered'),('TECH_VALIDATED','Technically Validated'),
                             ('AUTHORIZED','Authorised'),('RELEASED','Released'),
                             ('DOCTOR_VIEWED','Doctor Viewed'),('AMENDED','Amended')])),
                ('timestamp', models.DateTimeField(default=django.utils.timezone.now)),
                ('notes', models.CharField(blank=True, max_length=200)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                            related_name='tat_timestamps', to='laboratory.laborder')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                           to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['timestamp'], 'verbose_name': 'TAT Timestamp'},
        ),

        # ═══════════════════════════════════════════════════════════════════
        # LabOrder — add STAT + DRAFT to urgency/status choices
        # ═══════════════════════════════════════════════════════════════════
        migrations.AlterField(
            model_name='laborder',
            name='urgency',
            field=models.CharField(default='ROUTINE', max_length=10,
                                   choices=[('ROUTINE','Routine'),('URGENT','Urgent'),
                                            ('STAT','STAT (Immediate)'),('EMERGENCY','Emergency')]),
        ),
        migrations.AlterField(
            model_name='laborder',
            name='status',
            field=models.CharField(default='ORDERED', max_length=20,
                                   choices=[('DRAFT','Draft'),('ORDERED','Ordered'),
                                            ('SAMPLE_COLLECTED','Sample Collected'),('PROCESSING','Processing'),
                                            ('COMPLETED','Completed'),('CANCELLED','Cancelled')]),
        ),
    ]
