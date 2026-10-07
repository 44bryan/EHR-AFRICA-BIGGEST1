"""
Seed sample payroll data for October 2026.
Creates salary components, structures, assigns salaries to existing staff,
generates a payroll run with full CNPS+IRPP calculations.
Run via: cd /opt/ehr-africa && source venv/bin/activate && python _seed_payroll_sample.py
"""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
sys.path.insert(0, '/opt/ehr-africa')
django.setup()

from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from apps.accounts.models import User
from apps.payroll.models import (
    SalaryComponent, SalaryStructure, StructureComponent,
    StaffSalaryAssignment, PayrollRun, PaySlip, PaySlipLine,
    ComponentType, PayrollRunStatus
)

# ── 1. Clear existing sample data ────────────────────────────────────────────
print("Cleaning existing sample payroll data...")
PayrollRun.objects.filter(year=2026, month=10).delete()
StaffSalaryAssignment.objects.all().delete()
StructureComponent.objects.all().delete()
SalaryStructure.objects.all().delete()
SalaryComponent.objects.all().delete()
print("  Done.")

# ── 2. Salary Components ──────────────────────────────────────────────────────
print("Creating salary components...")

def mkcomp(name, code, ctype, default=0):
    return SalaryComponent.objects.create(
        name=name, code=code, component_type=ctype,
        is_percentage=False, default_amount=Decimal(str(default)),
        is_taxable=True, is_active=True
    )

EARN = ComponentType.EARNING

housing   = mkcomp("Indemnite de Logement",  "IND_LOG",    EARN, 50000)
transport = mkcomp("Indemnite de Transport",  "IND_TRANS",  EARN, 25000)
resp      = mkcomp("Prime de Responsabilite", "PRIME_RESP", EARN, 75000)
risk      = mkcomp("Prime de Risque",         "PRIME_RISK", EARN, 30000)
night     = mkcomp("Prime de Nuit",           "PRIME_NUIT", EARN, 20000)
print(f"  Created {SalaryComponent.objects.count()} components.")

# ── 3. Salary Structures ──────────────────────────────────────────────────────
print("Creating salary structures...")
admin_user = User.objects.filter(is_superuser=True).first()

def mkstruct(name, comp_overrides):
    """comp_overrides: list of (component, override_amount)"""
    s = SalaryStructure.objects.create(name=name, is_active=True)
    for i, (comp, override) in enumerate(comp_overrides):
        StructureComponent.objects.create(
            salary_structure=s, component=comp,
            override_amount=Decimal(str(override)),
            sort_order=i
        )
    return s

struct_medecin   = mkstruct("Structure Medecin Specialiste",    [(housing, 80000), (transport, 35000), (resp, 150000), (risk, 50000)])
struct_infirmier = mkstruct("Structure Infirmier Diplome",      [(housing, 50000), (transport, 25000), (risk, 20000),  (night, 20000)])
struct_admin     = mkstruct("Structure Personnel Administratif",[(housing, 40000), (transport, 25000)])
struct_pharm     = mkstruct("Structure Pharmacien",             [(housing, 70000), (transport, 30000), (resp, 100000)])
struct_lab       = mkstruct("Structure Technicien",             [(housing, 45000), (transport, 25000), (risk, 25000)])

print(f"  Created {SalaryStructure.objects.count()} structures.")

# ── 4. Assign salaries ────────────────────────────────────────────────────────
print("Assigning salaries to staff...")

ROLE_MAP = {
    'OPHTHALMOLOGIST':          (struct_medecin,    350000),
    'OPTOMETRIST':              (struct_medecin,    280000),
    'OPTICIAN':                 (struct_infirmier,  180000),
    'ORTHOPTIST':               (struct_infirmier,  200000),
    'NURSE':                    (struct_infirmier,  150000),
    'NURSE_DIRECTOR':           (struct_infirmier,  220000),
    'PHARMACIST':               (struct_pharm,      300000),
    'HEAD_PHARMACIST':          (struct_pharm,      380000),
    'LAB_TECHNICIAN':           (struct_lab,        180000),
    'INVESTIGATION_TECHNICIAN': (struct_lab,        180000),
    'CASHIER':                  (struct_admin,      120000),
    'CHIEF_CASHIER':            (struct_admin,      160000),
    'ACCOUNTANT':               (struct_admin,      200000),
    'SENIOR_ACCOUNTANT':        (struct_admin,      280000),
    'FINANCE_DIRECTOR':         (struct_medecin,    500000),
    'ADMIN_DIRECTOR':           (struct_medecin,    450000),
    'MEDICAL_DIRECTOR':         (struct_medecin,    600000),
    'RECEPTIONIST':             (struct_admin,      100000),
    'MEDICAL_RECORDS':          (struct_admin,      110000),
    'STORE_KEEPER':             (struct_admin,      110000),
    'DOCTOR':                   (struct_medecin,    320000),
    'CEO':                      (struct_medecin,    700000),
    'QUALITY_OFFICER':          (struct_admin,      180000),
    'ANAESTHETIST':             (struct_medecin,    400000),
    'CSSD_TECHNICIAN':          (struct_lab,        130000),
    'PHYSIOTHERAPIST':          (struct_infirmier,  200000),
    'INTERN':                   (struct_admin,       80000),
}

assigned = 0
today = timezone.localdate().replace(day=1)
for staff in User.objects.filter(is_active=True).exclude(is_superuser=True).order_by('role', 'first_name'):
    role = getattr(staff, 'role', None)
    if role and role in ROLE_MAP:
        structure, basic = ROLE_MAP[role]
        StaffSalaryAssignment.objects.create(
            staff=staff, structure=structure,
            basic_salary=Decimal(str(basic)),
            effective_from=today
        )
        assigned += 1

print(f"  Assigned: {assigned} staff.")

# ── 5. Create PayrollRun & generate payslips ──────────────────────────────────
print("Creating PayrollRun Oct 2026 and generating payslips...")

_CNPS_CAP = Decimal('750000')

def _compute_cnps(gross):
    base = min(gross, _CNPS_CAP)
    return (
        (base * Decimal('0.042')).quantize(Decimal('1')),
        (base * Decimal('0.1495')).quantize(Decimal('1')),
    )

def _compute_irpp(gross, cnps_emp):
    prof_ded        = min(gross * Decimal('0.30'), Decimal('33333'))
    taxable_monthly = max(Decimal('0'), gross - cnps_emp - prof_ded)
    taxable_annual  = taxable_monthly * 12
    brackets = [
        (Decimal('2000000'), Decimal('0.11')),
        (Decimal('1000000'), Decimal('0.165')),
        (Decimal('2000000'), Decimal('0.275')),
        (None,               Decimal('0.385')),
    ]
    irpp_annual = Decimal('0')
    remaining   = taxable_annual
    for limit, rate in brackets:
        if remaining <= 0:
            break
        chunk = min(remaining, limit) if limit else remaining
        irpp_annual += chunk * rate
        remaining   -= chunk
    return ((irpp_annual * Decimal('1.10')) / 12).quantize(Decimal('1'))

with transaction.atomic():
    run = PayrollRun.objects.create(
        year=2026, month=10,
        status=PayrollRunStatus.DRAFT,
        created_by=admin_user,
        description='Payroll Octobre 2026 — Données de test'
    )

    created = 0
    for asgn in StaffSalaryAssignment.objects.filter(
            is_deleted=False).select_related('staff', 'structure'):
        basic = asgn.basic_salary
        earnings_lines = []
        for sc in asgn.structure.components.select_related('component').order_by('sort_order'):
            if sc.component.component_type == ComponentType.EARNING:
                amt = sc.override_amount if sc.override_amount is not None else sc.component.default_amount
                earnings_lines.append((sc.component, amt))

        gross    = basic + sum(a for _, a in earnings_lines)
        cnps_emp, cnps_empl = _compute_cnps(gross)
        irpp     = _compute_irpp(gross, cnps_emp)
        total_d  = cnps_emp + irpp
        net_pay  = max(Decimal('0'), gross - total_d)

        slip = PaySlip.objects.create(
            payroll_run=run, staff=asgn.staff,
            basic_salary=basic, gross_pay=gross,
            total_deductions=total_d, net_pay=net_pay,
            cnps_employee=cnps_emp, cnps_employer=cnps_empl,
            withholding_tax=irpp, status='DRAFT',
        )
        # Basic salary line (no SalaryComponent — statutory)
        PaySlipLine.objects.create(
            payslip=slip, component=None,
            description='Salaire de Base',
            component_type=ComponentType.EARNING, amount=basic,
        )
        for comp, amt in earnings_lines:
            PaySlipLine.objects.create(
                payslip=slip, component=comp,
                description=comp.name,
                component_type=ComponentType.EARNING, amount=amt,
            )
        PaySlipLine.objects.create(
            payslip=slip, component=None,
            description='CNPS Employe (4.2% plafonne 750 000)',
            component_type=ComponentType.STATUTORY, amount=cnps_emp,
        )
        PaySlipLine.objects.create(
            payslip=slip, component=None,
            description='IRPP + CAC (Bareme progressif)',
            component_type=ComponentType.STATUTORY, amount=irpp,
        )
        created += 1

    from django.db.models import Sum
    totals = run.payslips.aggregate(
        gross=Sum('gross_pay'), ded=Sum('total_deductions'), net=Sum('net_pay')
    )
    run.total_gross      = totals['gross'] or 0
    run.total_deductions = totals['ded']   or 0
    run.total_net        = totals['net']   or 0
    run.save()

print(f"  Generated {created} payslips.")

# ── 6. Verification table ─────────────────────────────────────────────────────
print("\n" + "="*115)
print(f"{'NAME':<28} {'ROLE':<22} {'BASIC':>10} {'INDEMNITES':>12} {'BRUT':>10} {'CNPS 4.2%':>10} {'IRPP':>10} {'NET':>12}")
print("="*115)

for slip in PaySlip.objects.filter(payroll_run=run).select_related('staff').order_by('-gross_pay'):
    name = (slip.staff.get_full_name() or slip.staff.username)[:27]
    role = str(getattr(slip.staff, 'role', '—'))[:21]
    allowances = slip.gross_pay - slip.basic_salary
    print(
        f"{name:<28} {role:<22} {int(slip.basic_salary):>10,} {int(allowances):>12,} "
        f"{int(slip.gross_pay):>10,} {int(slip.cnps_employee):>10,} "
        f"{int(slip.withholding_tax):>10,} {int(slip.net_pay):>12,}"
    )

print("="*115)
print(f"{'TOTAUX':<63} {int(run.total_gross):>10,} {'':>10} {'':>10} {int(run.total_net):>12,}")

# Show one detailed example
sample = PaySlip.objects.filter(payroll_run=run).order_by('-gross_pay').first()
if sample:
    gross = sample.gross_pay
    cnps_base = min(gross, _CNPS_CAP)
    prof_ded  = min(gross * Decimal('0.30'), Decimal('33333'))
    taxable   = max(0, gross - sample.cnps_employee - prof_ded)
    print(f"\n--- DETAIL CALCUL: {sample.staff.get_full_name()} ---")
    print(f"  Salaire de base         : {int(sample.basic_salary):>12,} FCFA")
    print(f"  + Indemnites/Primes     : {int(gross - sample.basic_salary):>12,} FCFA")
    print(f"  = SALAIRE BRUT          : {int(gross):>12,} FCFA")
    print(f"  Assiette CNPS           : min(brut, 750 000) = {int(cnps_base):>12,} FCFA")
    print(f"  CNPS Employe (4,2%)     : {int(sample.cnps_employee):>12,} FCFA")
    print(f"  CNPS Patron  (14,95%)   : {int(sample.cnps_employer):>12,} FCFA (charge patronale)")
    print(f"  Deduction prof. (30%brut, max 33 333): {int(prof_ded):>5,} FCFA")
    print(f"  Revenu imposable/mois   : {int(taxable):>12,} FCFA")
    print(f"  Revenu imposable/an     : {int(taxable*12):>12,} FCFA")
    print(f"  IRPP + CAC (10%)        : {int(sample.withholding_tax):>12,} FCFA")
    print(f"  = NET A PAYER           : {int(sample.net_pay):>12,} FCFA")

print(f"\nRun ID : {run.pk}")
print("Naviguez vers /payroll/runs/ pour voir le bulletin.")
