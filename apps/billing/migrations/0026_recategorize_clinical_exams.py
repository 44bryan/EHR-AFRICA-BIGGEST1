# Data migration: recategorize optometry exams → CLINICAL, deactivate duplicates
from django.db import migrations


def recategorize(apps, schema_editor):
    ServicePrice = apps.get_model('billing', 'ServicePrice')

    # 1. Move optometry exams from INVEST/CONSULT → CLINICAL
    CLINICAL_NAMES = [
        'Subjective Refraction',
        'Auto-Refraction',
        'Visual Acuity',
        'Cycloplegic Refraction',
        'Binocular Vision Evaluation',
        'Colour Vision Test',
        'Hess Chart / Diplopia',
        'Muscle Balance & Strabismus',
        'Cover Test / Orthoptic Assessment',
        'Orthoptic Assessment',
        'Low Vision Assessment',
        'Applanation Tonometry (Goldmann)',
        'IOP Non-Contact Tonometry',
        'Fundoscopy',
        'Slit Lamp Examination',
        'Gonioscopy',
    ]
    ServicePrice.objects.filter(
        name__in=CLINICAL_NAMES, is_active=True
    ).exclude(category='CLINICAL').update(category='CLINICAL')

    # Also move CONS-REFRAC code to CLINICAL
    ServicePrice.objects.filter(
        code='CONS-REFRAC', is_active=True
    ).update(category='CLINICAL')

    # 2. Deactivate duplicates
    DEACTIVATE = [
        ('IOP Goldman Applanation Tonometry', 'INV-TONO'),
        ('Non-Contact Tonometry', 'INV-TONO'),
        ('Tonometry (IOP)', 'INV-IOP'),
        ('Biometry', 'INV-BIOM'),
        ('Biometry (A-scan)', 'INV-BIOM'),
        ('Electroretinography (ERG)', 'INV-ELEC'),
        ('Pachymetry (Corneal Thickness)', 'INV-PACH'),
        ('OCT', 'INV-IMAG'),
        ('OCT Scan', 'INV-OCT'),
        ('OCT Anterior Segment', 'INV-OCT'),
        ('Visual Field', 'INV-VISU'),
        ('Visual Field Test', 'INV-VF'),
        ('Retinal Angiography (FFA)', 'INV-IMAG'),
        ('Ultrasound B-Scan', 'INV-IMAG'),
        ('Subjective Refraction', 'SVC-REFRACTION'),
    ]
    for name, code in DEACTIVATE:
        ServicePrice.objects.filter(name=name, code=code, is_active=True).update(is_active=False)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0025_add_clinical_exam_category'),
    ]

    operations = [
        migrations.RunPython(recategorize, noop),
    ]
