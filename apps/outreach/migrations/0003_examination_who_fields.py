"""
Migration 0003 — WHO/ICD-11 international standard fields on OutreachExamination.

Adds:
  - principal_cause_vi  (WHO principal cause of visual impairment)
  - pupil_re / pupil_le  (pupil reactions, RAPD detection)
  - conf_vf_re / conf_vf_le  (confrontation visual fields)
  - color_vision_re / color_vision_le  (Ishihara / gross)
  - external_exam  (lids, adnexa, orbit)
  - informed_consent / consent_date  (JCI PFR.5)
  - low_vision_referral
  - examiner_designation
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('outreach', '0002_outreach_advanced'),
    ]

    operations = [
        # Principal cause of VI (WHO)
        migrations.AddField(
            model_name='outreachexamination',
            name='principal_cause_vi',
            field=models.CharField(
                blank=True, default='', max_length=30,
                verbose_name='Principal Cause of VI (WHO)',
                help_text='Primary cause driving visual impairment per WHO classification',
                choices=[
                    ('REFRACTIVE_ERROR', 'Uncorrected Refractive Error'),
                    ('CATARACT', 'Cataract (Unoperated)'),
                    ('GLAUCOMA', 'Glaucoma'),
                    ('AMD', 'Age-related Macular Degeneration'),
                    ('DIABETIC_RETINOPATHY', 'Diabetic Retinopathy'),
                    ('CORNEAL_OPACITY', 'Corneal Opacity'),
                    ('TRACHOMA', 'Trachoma'),
                    ('ONCHOCERCIASIS', 'Onchocerciasis'),
                    ('OTHER', 'Other / Undetermined'),
                    ('NORMAL', 'No Visual Impairment'),
                ],
            ),
        ),
        # Pupil reactions
        migrations.AddField(
            model_name='outreachexamination',
            name='pupil_re',
            field=models.CharField(
                blank=True, default='', max_length=10,
                verbose_name='Pupil RE',
                choices=[
                    ('NORMAL', 'Normal / Reactive'), ('SLUGGISH', 'Sluggish'),
                    ('RAPD', 'RAPD Present (Relative Afferent Pupillary Defect)'),
                    ('FIXED', 'Fixed / Non-reactive'), ('NT', 'Not Tested'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='outreachexamination',
            name='pupil_le',
            field=models.CharField(
                blank=True, default='', max_length=10,
                verbose_name='Pupil LE',
                choices=[
                    ('NORMAL', 'Normal / Reactive'), ('SLUGGISH', 'Sluggish'),
                    ('RAPD', 'RAPD Present (Relative Afferent Pupillary Defect)'),
                    ('FIXED', 'Fixed / Non-reactive'), ('NT', 'Not Tested'),
                ],
            ),
        ),
        # Confrontation visual fields
        migrations.AddField(
            model_name='outreachexamination',
            name='conf_vf_re',
            field=models.CharField(
                blank=True, default='', max_length=20,
                verbose_name='Confrontation VF RE',
                choices=[
                    ('FULL', 'Full to Confrontation'), ('CONSTRICTED', 'Constricted'),
                    ('NASAL', 'Nasal Field Defect'), ('TEMPORAL', 'Temporal Field Defect'),
                    ('HEMIANOPIA', 'Hemianopia'), ('SCOTOMA', 'Central Scotoma'),
                    ('NT', 'Not Tested'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='outreachexamination',
            name='conf_vf_le',
            field=models.CharField(
                blank=True, default='', max_length=20,
                verbose_name='Confrontation VF LE',
                choices=[
                    ('FULL', 'Full to Confrontation'), ('CONSTRICTED', 'Constricted'),
                    ('NASAL', 'Nasal Field Defect'), ('TEMPORAL', 'Temporal Field Defect'),
                    ('HEMIANOPIA', 'Hemianopia'), ('SCOTOMA', 'Central Scotoma'),
                    ('NT', 'Not Tested'),
                ],
            ),
        ),
        # Color vision
        migrations.AddField(
            model_name='outreachexamination',
            name='color_vision_re',
            field=models.CharField(
                blank=True, default='', max_length=10,
                verbose_name='Color Vision RE',
                choices=[
                    ('NORMAL', 'Normal'), ('DEFECTIVE', 'Color Vision Defect'),
                    ('NT', 'Not Tested'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='outreachexamination',
            name='color_vision_le',
            field=models.CharField(
                blank=True, default='', max_length=10,
                verbose_name='Color Vision LE',
                choices=[
                    ('NORMAL', 'Normal'), ('DEFECTIVE', 'Color Vision Defect'),
                    ('NT', 'Not Tested'),
                ],
            ),
        ),
        # External examination
        migrations.AddField(
            model_name='outreachexamination',
            name='external_exam',
            field=models.TextField(
                blank=True,
                verbose_name='External Examination (lids, adnexa, orbit)',
            ),
        ),
        # Informed consent (JCI PFR.5)
        migrations.AddField(
            model_name='outreachexamination',
            name='informed_consent',
            field=models.BooleanField(
                default=False,
                help_text='Patient/guardian has given verbal/written consent',
            ),
        ),
        migrations.AddField(
            model_name='outreachexamination',
            name='consent_date',
            field=models.DateField(null=True, blank=True),
        ),
        # Low vision referral pathway
        migrations.AddField(
            model_name='outreachexamination',
            name='low_vision_referral',
            field=models.BooleanField(
                default=False,
                help_text='Refer for formal low vision assessment/rehabilitation',
            ),
        ),
        # Examiner designation
        migrations.AddField(
            model_name='outreachexamination',
            name='examiner_designation',
            field=models.CharField(
                blank=True, max_length=100,
                help_text='e.g. Ophthalmologist, Optometrist, Ophthalmic Nurse',
            ),
        ),
    ]
