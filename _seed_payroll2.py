import os, sys, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ehr_project.settings.base")
sys.path.insert(0, "/opt/ehr-africa")
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

print("Cleaning...")
PayrollRun.objects.filter(year=2026, month=10).delete()
StaffSalaryAssignment.objects.all().delete()
StructureComponent.objects.all().delete()
SalaryStructure.objects.all().delete()
SalaryComponent.objects.all().delete()

EARN = ComponentType.EARNING

def mkcomp(name, code, default=0):
    return SalaryComponent.objects.create(
        name=name, code=code, component_type=EARN,
        is_percentage=False, default_amount=Decimal(str(default)),
        is_taxable=True, is_active=True
    )

housing   = mkcomp("Indemnite de Logement",  "IND_LOG",    50000)
transport = mkcomp("Indemnite de Transport",  "IND_TRANS",  25000)
resp      = mkcomp("Prime de Responsabilite", "PRIME_RESP", 75000)
risk      = mkcomp("Prime de Risque",         "PRIME_RISK", 30000)
night     = mkcomp("Prime de Nuit",           "PRIME_NUIT", 20000)
print(f"  {SalaryComponent.objects.count()} components.")

admin_user = User.objects.filter(is_superuser=True).first()

def mkstruct(name, comp_list):
    s = SalaryStructure.objects.create(name=name, is_active=True)
    for i, (comp, ov) in enumerate(comp_list):
        StructureComponent.objects.create(
            salary_structure=s, component=comp,
            override_amount=Decimal(str(ov)), sort_order=i
        )
    return s

med = mkstruct("Structure Medecin Specialiste",    [(housing,80000),(transport,35000),(resp,150000),(risk,50000)])
inf = mkstruct("Structure Infirmier",              [(housing,50000),(transport,25000),(risk,20000),(night,20000)])
adm = mkstruct("Structure Administratif",          [(housing,40000),(transport,25000)])
pha = mkstruct("Structure Pharmacien",             [(housing,70000),(transport,30000),(resp,100000)])
lab = mkstruct("Structure Technicien",             [(housing,45000),(transport,25000),(risk,25000)])
print(f"  {SalaryStructure.objects.count()} structures.")

ROLE_MAP = {
    "ophthalmologist":           (med,  350000),
    "glaucoma_specialist":       (med,  380000),
    "retina_specialist":         (med,  380000),
    "pediatric_ophthalmologist": (med,  360000),
    "general_physician":         (med,  320000),
    "optometrist":               (med,  280000),
    "pediatric_refractionist":   (med,  260000),
    "low_vision_specialist":     (med,  270000),
    "anaesthetist":              (med,  400000),
    "medical_director":          (med,  600000),
    "admin_director":            (med,  450000),
    "finance_director":          (med,  500000),
    "optician":                  (inf,  180000),
    "optical_dispenser":         (inf,  160000),
    "nurse":                     (inf,  150000),
    "ward_nurse":                (inf,  155000),
    "theatre_nurse":             (inf,  165000),
    "consultation_nurse":        (inf,  155000),
    "counseling_nurse":          (inf,  150000),
    "lab_technician":            (lab,  180000),
    "investigation_technician":  (lab,  180000),
    "pharmacist":                (pha,  300000),
    "head_pharmacist":           (pha,  380000),
    "cashier":                   (adm,  120000),
    "chief_cashier":             (adm,  160000),
    "accountant":                (adm,  200000),
    "senior_accountant":         (adm,  280000),
    "billing_officer":           (adm,  130000),
    "receptionist":              (adm,  100000),
    "medical_records":           (adm,  110000),
    "store_keeper":              (adm,  110000),
    "procurement_officer":       (adm,  140000),
    "admission_officer":         (adm,  110000),
    "gatekeeper":                (adm,   80000),
}

today = timezone.localdate().replace(day=1)
assigned = 0
for staff in User.objects.filter(is_active=True).exclude(is_superuser=True).order_by("role", "first_name"):
    r = getattr(staff, "role", None)
    if r and r in ROLE_MAP:
        structure, basic = ROLE_MAP[r]
        StaffSalaryAssignment.objects.create(
            staff=staff, structure=structure,
            basic_salary=Decimal(str(basic)), effective_from=today
        )
        assigned += 1
print(f"  Assigned: {assigned} staff.")

_CNPS_CAP = Decimal("750000")

def _cnps(gross):
    b = min(gross, _CNPS_CAP)
    return (b*Decimal("0.042")).quantize(Decimal("1")), (b*Decimal("0.1495")).quantize(Decimal("1"))

def _irpp(gross, ce):
    pd = min(gross*Decimal("0.30"), Decimal("33333"))
    ta = max(Decimal("0"), gross - ce - pd) * 12
    brackets = [
        (Decimal("2000000"), Decimal("0.11")),
        (Decimal("1000000"), Decimal("0.165")),
        (Decimal("2000000"), Decimal("0.275")),
        (None,               Decimal("0.385")),
    ]
    irpp = Decimal("0"); rem = ta
    for lim, rate in brackets:
        if rem <= 0: break
        chunk = min(rem, lim) if lim else rem
        irpp += chunk * rate
        rem  -= chunk
    return (irpp * Decimal("1.10") / 12).quantize(Decimal("1"))

with transaction.atomic():
    run = PayrollRun.objects.create(
        year=2026, month=10, status=PayrollRunStatus.DRAFT,
        created_by=admin_user, description="Payroll Octobre 2026 - Donnees de test"
    )
    created = 0
    for asgn in StaffSalaryAssignment.objects.filter(is_deleted=False).select_related("staff","structure"):
        basic = asgn.basic_salary
        elines = []
        for sc in asgn.structure.components.select_related("component").order_by("sort_order"):
            if sc.component.component_type == ComponentType.EARNING:
                amt = sc.override_amount if sc.override_amount is not None else sc.component.default_amount
                elines.append((sc.component, amt))
        gross = basic + sum(a for _, a in elines)
        ce, co = _cnps(gross)
        irpp   = _irpp(gross, ce)
        td     = ce + irpp
        net    = max(Decimal("0"), gross - td)
        slip = PaySlip.objects.create(
            payroll_run=run, staff=asgn.staff,
            basic_salary=basic, gross_pay=gross,
            total_deductions=td, net_pay=net,
            cnps_employee=ce, cnps_employer=co,
            withholding_tax=irpp, status="DRAFT"
        )
        PaySlipLine.objects.create(payslip=slip, component=None, description="Salaire de Base",
                                   component_type=ComponentType.EARNING, amount=basic)
        for comp, amt in elines:
            PaySlipLine.objects.create(payslip=slip, component=comp, description=comp.name,
                                       component_type=ComponentType.EARNING, amount=amt)
        PaySlipLine.objects.create(payslip=slip, component=None, description="CNPS Employe 4.2%",
                                   component_type=ComponentType.STATUTORY, amount=ce)
        PaySlipLine.objects.create(payslip=slip, component=None, description="IRPP+CAC Bareme",
                                   component_type=ComponentType.STATUTORY, amount=irpp)
        created += 1
    from django.db.models import Sum
    t = run.payslips.aggregate(g=Sum("gross_pay"), d=Sum("total_deductions"), n=Sum("net_pay"))
    run.total_gross=t["g"] or 0; run.total_deductions=t["d"] or 0; run.total_net=t["n"] or 0
    run.save()
    print(f"  Generated {created} payslips.")

# Print table
print()
W = 120
print(f"{'NAME':<30} {'ROLE':<25} {'BASIC':>10} {'ALLOC':>9} {'BRUT':>10} {'CNPS':>9} {'IRPP':>9} {'NET':>12}")
print("-"*W)
for s in PaySlip.objects.filter(payroll_run=run).select_related("staff").order_by("-gross_pay"):
    n = (s.staff.get_full_name() or s.staff.username)[:29]
    r = str(getattr(s.staff, "role", "-"))[:24]
    alloc = s.gross_pay - s.basic_salary
    print(f"{n:<30} {r:<25} {int(s.basic_salary):>10,} {int(alloc):>9,} {int(s.gross_pay):>10,} "
          f"{int(s.cnps_employee):>9,} {int(s.withholding_tax):>9,} {int(s.net_pay):>12,}")
print("-"*W)
print(f"{'TOTAUX':<67} {int(run.total_gross):>10,} {'':>9} {'':>9} {int(run.total_net):>12,}")

# Detailed example
sam = PaySlip.objects.filter(payroll_run=run).order_by("-gross_pay").first()
if sam:
    g  = sam.gross_pay
    pd = min(g * Decimal("0.30"), Decimal("33333"))
    ti = max(Decimal("0"), g - sam.cnps_employee - pd)
    print()
    print(f"--- EXEMPLE CALCUL: {sam.staff.get_full_name()} ({getattr(sam.staff,'role','-')}) ---")
    print(f"  Salaire de base              : {int(sam.basic_salary):>12,} FCFA")
    print(f"  + Indemnites / Primes        : {int(g - sam.basic_salary):>12,} FCFA")
    print(f"  = SALAIRE BRUT               : {int(g):>12,} FCFA")
    print(f"  Assiette CNPS (plaf. 750 000): {int(min(g,_CNPS_CAP)):>12,} FCFA")
    print(f"  CNPS Employe  (4,20 %)       : {int(sam.cnps_employee):>12,} FCFA")
    print(f"  CNPS Patronal (14,95%)       : {int(sam.cnps_employer):>12,} FCFA  [charge patronale]")
    print(f"  Ded. professionelle (30%, max 33 333): {int(pd):>7,} FCFA")
    print(f"  Revenu imposable / mois      : {int(ti):>12,} FCFA")
    print(f"  Revenu imposable / an        : {int(ti*12):>12,} FCFA")
    print(f"  IRPP + CAC (10 %)            : {int(sam.withholding_tax):>12,} FCFA")
    print(f"  TOTAL RETENUES               : {int(sam.total_deductions):>12,} FCFA")
    print(f"  = NET A PAYER                : {int(sam.net_pay):>12,} FCFA")

print(f"\nRun ID: {run.pk}")
print("=> Allez sur /payroll/runs/ pour voir et telecharger les bulletins.")
