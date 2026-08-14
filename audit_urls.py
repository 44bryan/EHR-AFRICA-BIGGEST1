"""
Audit: resolve all named URL patterns and flag any that crash on reverse().
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from django.urls import reverse, NoReverseMatch
from django.urls import get_resolver
import uuid

SAMPLE_UUID = str(uuid.uuid4())
SAMPLE_INT  = 1
SAMPLE_STR  = 'VIS-0001'

# Known URL names that need args - map name - kwargs to try
KNOWN_ARGS = {
    'patients:detail':            {'patient_id': 'P00001'},
    'patients:visit_detail':      {'visit_number': 'VIS-0001'},
    'patients:triage':            {'visit_number': 'VIS-0001'},
    'patients:triage_start':      {'patient_id': 'P00001'},
    'patients:discharge':         {'visit_number': 'VIS-0001'},
    'patients:edit':              {'patient_id': 'P00001'},
    'consultations:detail':       {'pk': SAMPLE_UUID},
    'consultations:edit':         {'pk': SAMPLE_UUID},
    'consultations:create':       {'patient_id': 'P00001'},
    'billing:invoice_detail':     {'invoice_id': SAMPLE_UUID},
    'billing:receipt':            {'invoice_id': SAMPLE_UUID},
    'billing:shift_detail':       {'shift_id': SAMPLE_UUID},
    'billing:add_payment':        {'invoice_id': SAMPLE_UUID},
    'billing:cashier_pos':        {'token_id': SAMPLE_UUID},
    'billing:patient_pos':        {'patient_id': 'P00001'},
    'billing:corporate_detail':   {'account_id': SAMPLE_UUID},
    'billing:petty_cash_detail':  {'fund_id': SAMPLE_UUID},
    'qms:counter':                {'counter_id': SAMPLE_UUID},
    'qms:call_next':              {'counter_id': SAMPLE_UUID},
    'accounts:user_edit':         {'pk': SAMPLE_UUID},
    'accounts:reset_password':    {'pk': SAMPLE_UUID},
    'reports:consultation_pdf':   {'pk': SAMPLE_UUID},
    'reports:drug_prescription_pdf': {'pk': SAMPLE_UUID},
    'reports:optical_prescription_pdf': {'pk': SAMPLE_UUID},
    'reports:investigation_pdf':  {'pk': SAMPLE_UUID},
    'reports:lab_pdf':            {'pk': SAMPLE_UUID},
    'reports:visit_summary_pdf':  {'pk': SAMPLE_UUID},
    'reports:patient_summary_pdf':{'patient_id': 'P00001'},
    'reports:medical_certificate':{'consultation_pk': SAMPLE_UUID},
    'reports:referral_letter':    {'consultation_pk': SAMPLE_UUID},
    'investigations:detail':      {'pk': SAMPLE_UUID},
    'investigations:add_result':  {'pk': SAMPLE_UUID},
    'laboratory:detail':          {'pk': SAMPLE_UUID},
    'laboratory:enter_results':   {'pk': SAMPLE_UUID},
    'laboratory:collect_sample':  {'pk': SAMPLE_UUID},
    # pharmacy:dispense takes no kwargs - just pharmacy/dispense/
    'pharmacy:dispensing_detail': {'dispensing_id': SAMPLE_UUID},
    # 'ipd:ward_detail' - no detail view, ward_list used instead
    'ipd:admission_detail':       {'admission_id': SAMPLE_UUID},
    'opticals:order_detail':      {'order_id': SAMPLE_UUID},
    'hrms:payroll_detail':        {'run_id': SAMPLE_UUID},
    'hrms:payslip':               {'entry_id': SAMPLE_UUID},
}

# No-args URLs to test
NO_ARG_URLS = [
    'dashboard:home', 'dashboard:sysadmin', 'dashboard:health_check',
    'patients:list', 'patients:register', 'patients:emergency_register',
    'consultations:list', 'consultations:workstation', 'consultations:triage_workstation',
    'billing:pos_landing', 'billing:invoice_list', 'billing:dashboard',
    'billing:shift_list', 'billing:shift_open', 'billing:shift_day_open',
    'billing:reconciliation', 'billing:my_shift',
    'billing:service_price_list', 'billing:work_queue',
    'billing:corporate_list', 'billing:ar_aging', 'billing:expense_list',
    'billing:petty_cash_list', 'billing:budget_list',
    'qms:dashboard', 'qms:receptionist', 'qms:gate_issue',
    'qms:express_desk', 'qms:vip_reception', 'qms:doctor_queue',
    'qms:my_counter',
    'accounts:login', 'accounts:staff_hub', 'accounts:user_create',
    'accounts:system_modules', 'accounts:profile',
    'investigations:list', 'investigations:workstation',
    'laboratory:list', 'laboratory:dashboard',
    'pharmacy:dashboard',
    # prescriptions:drug_list - no list view, accessed via consultation
    'appointments:list',
    'opticals:dashboard', 'opticals:order_list',
    'ipd:dashboard', 'ipd:ward_list', 'ipd:theatre_board',
    'cssd:cycles',
    'hrms:dashboard', 'hrms:payroll_list',
    'leadership:dashboard', 'leadership:finance_dashboard',
    'leadership:monthly_stats', 'leadership:retina_dashboard',
    'reports:disease_burden', 'reports:revenue_report', 'reports:staff_performance',
    'departments:dept_list',
]

errors = []
ok_count = 0

for name in NO_ARG_URLS:
    try:
        reverse(name)
        ok_count += 1
    except NoReverseMatch as e:
        errors.append(f'NoReverseMatch: {name} - {e}')
    except Exception as e:
        errors.append(f'ERROR: {name} - {e}')

for name, kwargs in KNOWN_ARGS.items():
    try:
        reverse(name, kwargs=kwargs)
        ok_count += 1
    except NoReverseMatch as e:
        errors.append(f'NoReverseMatch: {name} kwargs={kwargs} - {e}')
    except Exception as e:
        errors.append(f'ERROR: {name} - {e}')

total = len(NO_ARG_URLS) + len(KNOWN_ARGS)
print(f'\nURL Reverse Audit: {ok_count}/{total} OK, {len(errors)} errors\n')
for e in errors:
    print(f'  !! {e}')
if not errors:
    print('  All named URLs resolve correctly.')
