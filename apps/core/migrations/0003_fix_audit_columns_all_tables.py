"""
Bulk-fix: add missing created_by_id / updated_by_id to all AuditModel tables.

These columns exist in the ORM model state (Django thinks migrations ran them)
but were never physically created on the production PostgreSQL table.
Using ADD COLUMN IF NOT EXISTS makes every statement idempotent.
"""
from django.db import migrations

# All tables confirmed missing created_by_id on the production server
_TABLES = [
    'ai_assistant_aimessage',
    'appointments_doctorschedule',
    'billing_bankreconciliationitem',
    'billing_budgetamendment',
    'blood_bank_blooddonor',
    'consultations_consultationdiagnosis',
    'consultations_patienteducationgiven',
    'dietary_dietaryrestriction',
    'dietary_mealitem',
    'hmo_insurancescheme',
    'hmo_insuredmember',
    'hrms_attendancerecord',
    'infection_control_antibioticsensitivity',
    'inventory_batchstock',
    'inventory_departmentreturnitem',
    'inventory_disposalitem',
    'inventory_grnitem',
    'inventory_purchaseorderitem',
    'inventory_quotationitem',
    'inventory_requisitionitem',
    'inventory_stockcountitem',
    'inventory_stockmovement',
    'inventory_storetransferitem',
    'inventory_supplierinvoiceitem',
    'investigations_investigationfile',
    'investigations_investigationtype',
    'ipd_fluidbalance',
    'ipd_marentry',
    'ipd_medrecitem',
    'ipd_vitalsigns',
    'laboratory_antibioticsensitivity',
    'laboratory_autoverificationrule',
    'laboratory_orderset',
    'laboratory_organismidentification',
    'laboratory_resultacknowledgment',
    'laboratory_samplerejection',
    'laboratory_tattimestamp',
    'leads_leadactivity',
    'mortuary_mortuarystorage',
    'opticals_framegrnitem',
    'opticals_framestocktakeitem',
    'outreach_outreachactivity',
    'outreach_outreachpatient',
    'outreach_outreachrecord',
    'outreach_outreachreferral',
    'outreach_outreachsynclog',
    'patients_insuranceinfo',
    'patients_nextofkin',
    'patients_patientallergy',
    'patients_patientmedication',
    'patients_patientproblem',
    'patients_routedestination',
    'patients_tierchangerequest',
    'patients_visitstop',
    'patients_visittierchange',
    'pharmacy_dispensingitem',
    'pharmacy_purchaseorderitem',
    'pharmacy_stocktakeitem',
    'pharmacy_stocktransferitem',
    'prescriptions_drugprescriptionitem',
    'qms_queuetoken',
    'qms_servicecounter',
    'qms_zone',
]

_REF = 'accounts_user'


def _build_sql():
    parts = []
    for tbl in _TABLES:
        parts.append(
            f'ALTER TABLE {tbl} '
            f'ADD COLUMN IF NOT EXISTS created_by_id uuid '
            f'REFERENCES {_REF}(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;'
        )
        parts.append(
            f'ALTER TABLE {tbl} '
            f'ADD COLUMN IF NOT EXISTS updated_by_id uuid '
            f'REFERENCES {_REF}(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;'
        )
    return '\n'.join(parts)


def _build_reverse_sql():
    parts = []
    for tbl in _TABLES:
        parts.append(f'ALTER TABLE {tbl} DROP COLUMN IF EXISTS created_by_id;')
        parts.append(f'ALTER TABLE {tbl} DROP COLUMN IF EXISTS updated_by_id;')
    return '\n'.join(parts)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_deletion_log_and_audit_fields'),
        ('accounts', '0033_hospitalconfig_enterprise_modules'),
    ]

    operations = [
        migrations.RunSQL(
            sql=_build_sql(),
            reverse_sql=_build_reverse_sql(),
        ),
    ]
