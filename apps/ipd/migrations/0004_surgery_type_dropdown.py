from django.db import migrations, models


SURGERY_TYPE_CHOICES = [
    ('PHACO', 'Phacoemulsification (Phaco) + IOL'),
    ('ECCE', 'ECCE (Extracapsular Cataract Extraction)'),
    ('ICCE', 'ICCE (Intracapsular Cataract Extraction)'),
    ('SICS', 'SICS (Small-Incision Cataract Surgery)'),
    ('IOL_EXCHANGE', 'IOL Exchange / Repositioning'),
    ('TRABECULECTOMY', 'Trabeculectomy'),
    ('TUBE_SHUNT', 'Tube Shunt / Drainage Implant'),
    ('CYCLOPHOTOCOAG', 'Cyclo-photocoagulation (CPC)'),
    ('LASER_TRABECULO', 'Selective Laser Trabeculoplasty (SLT)'),
    ('PI', 'Peripheral Iridotomy (PI)'),
    ('VITRECTOMY', 'Pars Plana Vitrectomy (PPV)'),
    ('BUCKLE', 'Scleral Buckle / Encirclement'),
    ('ANTI_VEGF', 'Intravitreal Anti-VEGF Injection'),
    ('LASER_RETINA', 'Laser Photocoagulation (Retina)'),
    ('PKP', 'Penetrating Keratoplasty (PKP)'),
    ('DSAEK', 'DSAEK / DMEK (Endothelial Keratoplasty)'),
    ('PTERYGIUM_EXC', 'Pterygium Excision + Graft'),
    ('KERATOCONUS', 'Corneal Collagen Cross-Linking (CXL)'),
    ('ENTROPION_REPAIR', 'Entropion Repair'),
    ('ECTROPION_REPAIR', 'Ectropion Repair'),
    ('PTOSIS_REPAIR', 'Ptosis Repair'),
    ('DCR', 'Dacryocystorhinostomy (DCR)'),
    ('ENUCLEATION', 'Enucleation / Evisceration'),
    ('EXENTERATION', 'Orbital Exenteration'),
    ('CHALAZION_EXC', 'Chalazion Excision'),
    ('LID_TUMOUR', 'Eyelid Tumour Excision'),
    ('STRABISMUS', 'Strabismus Surgery (Squint Correction)'),
    ('PROBING', 'Nasolacrimal Duct Probing'),
    ('FB_REMOVAL', 'Intraocular Foreign Body Removal'),
    ('EUA', 'Examination Under Anaesthesia (EUA)'),
    ('OTHER', 'Other (specify in notes)'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('ipd', '0003_admission_surgical_booking_bed_price_override_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='surgicalbooking',
            name='procedure',
            field=models.CharField(
                choices=SURGERY_TYPE_CHOICES,
                default='OTHER',
                help_text='Select procedure type from the list',
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name='surgicalbooking',
            name='procedure_notes',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Additional details or specify if "Other" selected',
                max_length=200,
            ),
            preserve_default=False,
        ),
    ]
