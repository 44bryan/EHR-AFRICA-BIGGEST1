"""
Migration: Consolidate EXPRESS_OPHTHALMOLOGIST and INSURANCE_OPHTHALMOLOGIST
into the single OPHTHALMOLOGIST role with a new consultation_unit field.

Before: separate roles for Express / Insurance / General ophthalmologist
After:  one OPHTHALMOLOGIST role + consultation_unit field (GENERAL / EXP_CONSULT / VIP_CONSULT / INSUR_CONSULT)
"""
from django.db import migrations, models


def migrate_express_insurance_to_ophthalmologist(apps, schema_editor):
    """Convert existing express/insurance doctor accounts to OPHTHALMOLOGIST + consultation_unit."""
    User = apps.get_model('accounts', 'User')
    # Express ophthalmologists → OPHTHALMOLOGIST + consultation_unit = EXP_CONSULT
    User.objects.filter(role='express_ophthalmologist').update(
        role='ophthalmologist',
        consultation_unit='EXP_CONSULT',
    )
    # Insurance ophthalmologists → OPHTHALMOLOGIST + consultation_unit = INSUR_CONSULT
    User.objects.filter(role='insurance_ophthalmologist').update(
        role='ophthalmologist',
        consultation_unit='INSUR_CONSULT',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0015_add_theme_and_board_type'),
    ]

    operations = [
        # Step 1: Add the new consultation_unit field
        migrations.AddField(
            model_name='user',
            name='consultation_unit',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('GENERAL', 'General Consultation'),
                    ('EXP_CONSULT', 'Express / Fast Track'),
                    ('VIP_CONSULT', 'VIP Consultation'),
                    ('INSUR_CONSULT', 'Insurance Consultation'),
                ],
                default='GENERAL',
                blank=True,
                help_text='For Ophthalmologist accounts only — which consultation desk this doctor is assigned to.',
            ),
        ),
        # Step 2: Migrate data — remap old roles to new role + unit
        migrations.RunPython(
            migrate_express_insurance_to_ophthalmologist,
            migrations.RunPython.noop,
        ),
        # Step 3: Update the role field choices (remove EXPRESS and INSURANCE variants)
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('super_admin', 'Super Administrator'),
                    ('ceo', 'Chief Executive Officer'),
                    ('finance_director', 'Finance Director'),
                    ('admin_director', 'Administrative Director'),
                    ('medical_director', 'Medical Director'),
                    ('ophthalmologist', 'Ophthalmologist'),
                    ('retina_specialist', 'Retina Specialist'),
                    ('glaucoma_specialist', 'Glaucoma Specialist'),
                    ('pediatric_ophthalmologist', 'Pediatric Ophthalmologist'),
                    ('pediatric_refractionist', 'Pediatric Refractionist / Orthoptist'),
                    ('cataract_surgeon', 'Cataract Surgeon'),
                    ('cornea_specialist', 'Cornea Specialist'),
                    ('oculoplastics_surgeon', 'Oculoplastics Surgeon'),
                    ('neuro_ophthalmologist', 'Neuro-ophthalmologist'),
                    ('uveitis_specialist', 'Uveitis Specialist'),
                    ('optometrist', 'Optometrist / Refractionist'),
                    ('intern', 'Intern / House Officer'),
                    ('nurse', 'OPD Nurse (Triage)'),
                    ('theatre_nurse', 'Theatre Nurse'),
                    ('ward_nurse', 'Ward Nurse (IPD)'),
                    ('counseling_nurse', 'Surgical Counseling Nurse'),
                    ('investigation_technician', 'Investigation Technician'),
                    ('lab_technician', 'Lab Technician'),
                    ('pharmacist', 'Pharmacist'),
                    ('optical_dispenser', 'Optical Dispenser'),
                    ('receptionist', 'Receptionist'),
                    ('admission_officer', 'Admission Officer'),
                    ('billing_officer', 'Billing Officer'),
                    ('cashier', 'Cashier'),
                    ('gatekeeper', 'Gate Security / Ticket Issuer'),
                    ('medical_records', 'Medical Records Officer'),
                    ('admin', 'System Administrator'),
                ],
                default='receptionist',
                max_length=30,
            ),
        ),
    ]
