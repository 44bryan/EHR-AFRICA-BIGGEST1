import os, django, glob
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

existing = set()
for f in glob.glob('templates/**/*.html', recursive=True):
    key = f.replace('templates' + os.sep, '').replace(os.sep, '/')
    existing.add(key)

print(f'Total templates on disk: {len(existing)}')

KEY_TEMPLATES = [
    # Layouts
    'layouts/base_authenticated.html',
    # Dashboard — all roles
    'dashboard/nurse.html', 'dashboard/consultation_nurse.html',
    'dashboard/doctor.html', 'dashboard/cashier.html', 'dashboard/chief_cashier.html',
    'dashboard/accountant.html', 'dashboard/billing.html', 'dashboard/admin_director.html',
    'dashboard/ceo.html', 'dashboard/medical_director.html',
    'dashboard/super_admin.html', 'dashboard/ward_nurse.html', 'dashboard/theatre_nurse.html',
    'dashboard/investigation_tech.html', 'dashboard/lab_tech.html',
    'dashboard/pharmacist.html', 'dashboard/optician.html',
    'dashboard/receptionist.html', 'dashboard/gatekeeper.html',
    'dashboard/health_check.html',
    # Patients
    'patients/list.html', 'patients/detail.html', 'patients/register.html',
    'patients/triage.html', 'patients/visit_detail.html', 'patients/emergency_register.html',
    # Consultations
    'consultations/workstation.html', 'consultations/triage_workstation.html',
    'consultations/detail.html', 'consultations/create.html',
    'consultations/list.html', 'consultations/edit.html', 'consultations/walkin_confirm.html',
    # Billing
    'billing/cashier_pos.html', 'billing/invoice_detail.html', 'billing/invoice_list.html',
    'billing/receipt.html', 'billing/shift_list.html', 'billing/shift_detail.html',
    'billing/shift_open.html', 'billing/shift_day_open.html',
    'billing/cashier_reconciliation.html', 'billing/dashboard.html',
    'billing/work_queue.html', 'billing/service_prices.html',
    'billing/corporate_list.html', 'billing/corporate_detail.html',
    'billing/expenses.html', 'billing/budget.html', 'billing/ar_aging.html',
    'billing/petty_cash_list.html', 'billing/petty_cash_detail.html',
    # QMS
    'qms/counter.html', 'qms/dashboard.html', 'qms/doctor_queue.html',
    'qms/receptionist.html', 'qms/gate_issue.html', 'qms/ticket_slip.html',
    'qms/express_desk.html', 'qms/vip_reception.html', 'qms/no_counter.html',
    # IPD
    'ipd/dashboard.html', 'ipd/ward_list.html', 'ipd/theatre_board.html',
    'ipd/ward_manage.html', 'ipd/surgical_booking_create.html',
    # Laboratory
    'laboratory/dashboard.html', 'laboratory/detail.html', 'laboratory/list.html',
    # Investigations
    'investigations/workstation.html', 'investigations/detail.html',
    # Pharmacy
    'pharmacy/dashboard.html', 'pharmacy/dispensing_detail.html',
    'pharmacy/dispensing_receipt.html',
    # Reports PDF
    'reports/pdf/consultation_report.html', 'reports/pdf/drug_prescription.html',
    'reports/pdf/optical_prescription.html', 'reports/pdf/investigation_report.html',
    'reports/pdf/lab_report.html', 'reports/pdf/visit_summary.html',
    'reports/pdf/patient_summary.html', 'reports/pdf/medical_certificate.html',
    'reports/pdf/referral_letter.html', 'reports/pdf/discharge_summary.html',
    # Accounts
    'accounts/user_form.html', 'accounts/staff_hub.html', 'accounts/system_modules.html',
    'accounts/login.html', 'accounts/profile.html',
    # HRMS
    'hrms/dashboard.html', 'hrms/payroll_list.html', 'hrms/payroll_detail.html',
    'hrms/payslip.html',
    # Leadership
    'leadership/dashboard.html', 'leadership/finance_dashboard.html',
    'leadership/monthly_stats.html', 'leadership/retina_dashboard.html',
    'leadership/analytics_dashboard.html',
    # Opticals
    'opticals/dashboard.html', 'opticals/order_detail.html', 'opticals/order_list.html',
    # CSSD
    'cssd/cycles.html', 'cssd/dispatch_instrument.html',
    # Appointments
    'appointments/list.html',
    # Prescriptions
    'prescriptions/drug_form.html',
    # Components
    'components/sidebar.html',
]

missing = [t for t in KEY_TEMPLATES if t not in existing]
ok = len(KEY_TEMPLATES) - len(missing)
print(f'Checked {len(KEY_TEMPLATES)} key templates: {ok} OK, {len(missing)} MISSING')
if missing:
    for t in missing:
        print(f'  MISSING: {t}')
