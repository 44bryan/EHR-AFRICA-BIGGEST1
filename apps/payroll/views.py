"""
Payroll Module Views
Salary structures, payroll runs, and payslip management.
Cameroon-specific: CNPS 4.2% employee / 14.95% employer, IRPP progressive rates.
"""
from decimal import Decimal, ROUND_HALF_UP
import calendar as _cal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from apps.accounts.models import UserRole
from .models import (
    SalaryComponent, SalaryStructure, StructureComponent,
    StaffSalaryAssignment, PayrollRun, PayrollRunStatus, PaySlip, PaySlipLine,
    ComponentType,
)

# ── Cameroon IRPP (Income Tax) calculation ─────────────────────────────────────
# Source: DGI Cameroon — progressive annual brackets + 10% CAC
_IRPP_BRACKETS = [
    (Decimal('2000000'),  Decimal('0.11')),   # 0 – 2,000,000 FCFA/year → 11%
    (Decimal('3000000'),  Decimal('0.165')),  # 2,000,001 – 3,000,000 → 16.5%
    (Decimal('5000000'),  Decimal('0.275')),  # 3,000,001 – 5,000,000 → 27.5%
    (None,                Decimal('0.385')),  # > 5,000,000 → 38.5%
]
_IRPP_CAC = Decimal('0.10')           # 10% Centimes Additionnels Communaux
_CNPS_EMP_RATE  = Decimal('0.042')    # Employee pension contribution: 4.2%
_CNPS_EMPL_RATE = Decimal('0.1495')   # Employer total: pension 4.2% + family 7% + AT 2.5% + PNVV 0.75%
_CNPS_CAP       = Decimal('750000')   # Monthly CNPS base ceiling

def _compute_cnps(gross: Decimal):
    """Compute employee and employer CNPS contributions (capped at 750,000 base)."""
    base = min(gross, _CNPS_CAP)
    emp  = (base * _CNPS_EMP_RATE).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    empl = (base * _CNPS_EMPL_RATE).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return emp, empl

def _compute_irpp(gross: Decimal, cnps_emp: Decimal):
    """
    Compute monthly IRPP (Cameroon income tax) using annual brackets.
    Steps:
    1. Professional expense deduction: 30% of gross, capped at 33,333 FCFA/month
    2. Taxable = gross - cnps_emp - professional_deduction
    3. Annualise, apply progressive brackets, add 10% CAC, monthly-ise.
    """
    prof_deduction = min(gross * Decimal('0.30'), Decimal('33333'))
    taxable_monthly = max(Decimal('0'), gross - cnps_emp - prof_deduction)
    taxable_annual  = taxable_monthly * 12

    irpp_annual = Decimal('0')
    prev_limit  = Decimal('0')
    for limit, rate in _IRPP_BRACKETS:
        if taxable_annual <= prev_limit:
            break
        band_top = limit if limit else taxable_annual
        taxable_in_band = min(taxable_annual, band_top) - prev_limit
        if taxable_in_band > 0:
            irpp_annual += taxable_in_band * rate
        if limit is None or taxable_annual <= limit:
            break
        prev_limit = limit

    irpp_annual_with_cac = (irpp_annual * (1 + _IRPP_CAC)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    monthly_irpp = (irpp_annual_with_cac / 12).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return monthly_irpp


def _can_manage(user):
    return user.is_superuser or user.role in (
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR, UserRole.FINANCE_DIRECTOR,
        UserRole.SENIOR_ACCOUNTANT,
    )


def _can_approve(user):
    return user.is_superuser or user.role in (
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR, UserRole.FINANCE_DIRECTOR,
    )


# ── Dashboard ──────────────────────────────────────────────────────────────────
@login_required
def dashboard(request):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    now = timezone.localtime(timezone.now())
    runs = PayrollRun.objects.order_by('-year', '-month')[:12]
    latest = runs.first()
    pending_count = PayrollRun.objects.filter(status=PayrollRunStatus.PENDING_APPROVAL).count()
    staff_count = StaffSalaryAssignment.objects.filter(is_deleted=False).count()
    return render(request, 'payroll/dashboard.html', {
        'runs': runs,
        'latest': latest,
        'pending_count': pending_count,
        'staff_count': staff_count,
        'current_year': now.year,
        'current_month': now.month,
    })


# ── Salary Structures ──────────────────────────────────────────────────────────
@login_required
def structure_list(request):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    structures = SalaryStructure.objects.filter(is_deleted=False)
    return render(request, 'payroll/structure_list.html', {'structures': structures})


@login_required
def structure_create(request):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        desc = request.POST.get('description', '').strip()
        if not name:
            messages.error(request, 'Name is required.')
        else:
            SalaryStructure.objects.create(name=name, description=desc)
            messages.success(request, f'Salary structure "{name}" created.')
            return redirect('payroll:structure_list')
    return render(request, 'payroll/structure_form.html', {'action': 'Create'})


@login_required
def structure_edit(request, structure_id):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    structure = get_object_or_404(SalaryStructure, pk=structure_id, is_deleted=False)
    components = SalaryComponent.objects.filter(is_active=True, is_deleted=False)
    assigned = structure.components.select_related('component').all()
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'save_structure':
            structure.name = request.POST.get('name', structure.name).strip()
            structure.description = request.POST.get('description', '').strip()
            structure.save()
            messages.success(request, 'Structure updated.')
            return redirect('payroll:structure_edit', structure_id=structure_id)
        elif action == 'add_component':
            comp_id = request.POST.get('component_id')
            override = request.POST.get('override_amount') or None
            if override:
                override = Decimal(override)
            sort_order = assigned.count()
            comp = get_object_or_404(SalaryComponent, pk=comp_id)
            StructureComponent.objects.get_or_create(
                salary_structure=structure, component=comp,
                defaults={'override_amount': override, 'sort_order': sort_order}
            )
            messages.success(request, f'{comp.name} added.')
            return redirect('payroll:structure_edit', structure_id=structure_id)
        elif action == 'remove_component':
            sc_id = request.POST.get('sc_id')
            StructureComponent.objects.filter(pk=sc_id, salary_structure=structure).delete()
            messages.success(request, 'Component removed.')
            return redirect('payroll:structure_edit', structure_id=structure_id)
    return render(request, 'payroll/structure_edit.html', {
        'structure': structure,
        'assigned': assigned,
        'components': components,
    })


# ── Salary Components ──────────────────────────────────────────────────────────
@login_required
def component_list(request):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    components = SalaryComponent.objects.filter(is_deleted=False)
    return render(request, 'payroll/component_list.html', {'components': components})


@login_required
def component_create(request):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        ctype = request.POST.get('component_type')
        is_pct = request.POST.get('is_percentage') == 'on'
        amount = Decimal(request.POST.get('default_amount', '0') or '0')
        is_taxable = request.POST.get('is_taxable') == 'on'
        if not name or not code:
            messages.error(request, 'Name and Code are required.')
        elif SalaryComponent.objects.filter(code=code).exists():
            messages.error(request, f'Code {code} already exists.')
        else:
            SalaryComponent.objects.create(
                name=name, code=code, component_type=ctype,
                is_percentage=is_pct, default_amount=amount, is_taxable=is_taxable
            )
            messages.success(request, f'Component "{name}" created.')
            return redirect('payroll:component_list')
    return render(request, 'payroll/component_form.html', {
        'action': 'Create',
        'component_types': ComponentType.choices,
    })


# ── Staff Salary Assignments ───────────────────────────────────────────────────
@login_required
def assignment_list(request):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from apps.accounts.models import User
    # All active staff
    staff = User.objects.filter(is_active=True, is_deleted=False).order_by('last_name', 'first_name')
    assignments = {a.staff_id: a for a in StaffSalaryAssignment.objects.filter(is_deleted=False).select_related('structure')}
    structures = SalaryStructure.objects.filter(is_active=True, is_deleted=False)
    return render(request, 'payroll/assignment_list.html', {
        'staff': staff,
        'assignments': assignments,
        'structures': structures,
    })


@login_required
def assignment_save(request, user_id):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    from apps.accounts.models import User
    user = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        structure_id = request.POST.get('structure_id')
        basic = Decimal(request.POST.get('basic_salary', '0') or '0')
        eff_from = request.POST.get('effective_from') or timezone.now().date()
        notes = request.POST.get('notes', '').strip()
        structure = get_object_or_404(SalaryStructure, pk=structure_id)
        StaffSalaryAssignment.objects.update_or_create(
            staff=user,
            defaults={
                'structure': structure,
                'basic_salary': basic,
                'effective_from': eff_from,
                'notes': notes,
                'is_deleted': False,
            }
        )
        messages.success(request, f'Salary assignment saved for {user.full_name}.')
    return redirect('payroll:assignment_list')


# ── Payroll Runs ───────────────────────────────────────────────────────────────
@login_required
def run_list(request):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    runs = PayrollRun.objects.order_by('-year', '-month')
    return render(request, 'payroll/run_list.html', {'runs': runs})


@login_required
def run_create(request):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    now = timezone.localtime(timezone.now())
    if request.method == 'POST':
        year = int(request.POST.get('year', now.year))
        month = int(request.POST.get('month', now.month))
        desc = request.POST.get('description', '').strip()
        if PayrollRun.objects.filter(year=year, month=month).exists():
            messages.error(request, f'Payroll for {_cal.month_name[month]} {year} already exists.')
        else:
            run = PayrollRun.objects.create(year=year, month=month, description=desc, created_by=request.user)
            messages.success(request, f'Payroll run created: {run}')
            return redirect('payroll:run_detail', run_id=run.pk)
    months = [(i, _cal.month_name[i]) for i in range(1, 13)]
    return render(request, 'payroll/run_create.html', {
        'months': months,
        'current_year': now.year,
        'current_month': now.month,
    })


@login_required
def run_detail(request, run_id):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    run = get_object_or_404(PayrollRun, pk=run_id)
    payslips = run.payslips.select_related('staff').order_by('staff__last_name')
    return render(request, 'payroll/run_detail.html', {
        'run': run,
        'payslips': payslips,
        'can_approve': _can_approve(request.user),
    })


@login_required
def run_generate(request, run_id):
    """Generate payslips for all staff with salary assignments."""
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    run = get_object_or_404(PayrollRun, pk=run_id)
    if run.status != PayrollRunStatus.DRAFT:
        messages.error(request, 'Can only generate for DRAFT payroll runs.')
        return redirect('payroll:run_detail', run_id=run_id)

    assignments = StaffSalaryAssignment.objects.filter(is_deleted=False).select_related('structure', 'staff')
    created, skipped = 0, 0

    with transaction.atomic():
        for assignment in assignments:
            if PaySlip.objects.filter(payroll_run=run, staff=assignment.staff).exists():
                skipped += 1
                continue

            basic = assignment.basic_salary
            lines_data = []
            earnings = Decimal('0')
            manual_deductions = Decimal('0')

            # 1. Collect earnings and manual deductions from salary structure
            for sc in assignment.structure.components.select_related('component').order_by('sort_order'):
                comp = sc.component
                amount = sc.effective_amount(basic)
                if comp.component_type == ComponentType.EARNING:
                    lines_data.append((comp, ComponentType.EARNING, amount))
                    earnings += amount
                elif comp.component_type == ComponentType.DEDUCTION:
                    lines_data.append((comp, ComponentType.DEDUCTION, amount))
                    manual_deductions += amount
                # Skip STATUTORY from components — we auto-calculate below

            gross = basic + earnings  # total gross

            # 2. Auto-compute CNPS (Cameroon statutory contributions)
            cnps_emp, cnps_empl = _compute_cnps(gross)

            # 3. Auto-compute IRPP (Cameroon income tax)
            irpp = _compute_irpp(gross, cnps_emp)

            # 4. Total deductions = CNPS employee + IRPP + manual deductions
            total_deductions = cnps_emp + irpp + manual_deductions
            net_pay = max(Decimal('0'), gross - total_deductions)

            slip = PaySlip.objects.create(
                payroll_run=run,
                staff=assignment.staff,
                basic_salary=basic,
                gross_pay=gross,
                total_deductions=total_deductions,
                net_pay=net_pay,
                cnps_employee=cnps_emp,
                cnps_employer=cnps_empl,
                withholding_tax=irpp,
                status='DRAFT',
            )

            # Basic salary line
            PaySlipLine.objects.create(
                payslip=slip,
                component=None,
                description='Salaire de Base',
                component_type=ComponentType.EARNING,
                amount=basic,
            )
            # Allowance / deduction lines from structure
            for comp, ctype, amount in lines_data:
                PaySlipLine.objects.create(
                    payslip=slip, component=comp, description=comp.name,
                    component_type=ctype, amount=amount,
                )
            # Statutory lines (auto-calculated)
            PaySlipLine.objects.create(
                payslip=slip, component=None,
                description=f'CNPS Employé (4.2% plafonné 750 000)',
                component_type=ComponentType.STATUTORY, amount=cnps_emp,
            )
            PaySlipLine.objects.create(
                payslip=slip, component=None,
                description=f'IRPP + CAC (Impôt sur Revenu)',
                component_type=ComponentType.STATUTORY, amount=irpp,
            )
            created += 1

        # Update run totals
        from django.db.models import Sum
        totals = run.payslips.aggregate(
            gross=Sum('gross_pay'), deductions=Sum('total_deductions'), net=Sum('net_pay')
        )
        run.total_gross = totals['gross'] or 0
        run.total_deductions = totals['deductions'] or 0
        run.total_net = totals['net'] or 0
        run.save()

    messages.success(request, f'Generated {created} payslips (CNPS + IRPP auto-calculated). {skipped} already existed.')
    return redirect('payroll:run_detail', run_id=run_id)


@login_required
def run_approve(request, run_id):
    if not _can_approve(request.user):
        messages.error(request, 'Only Finance Director or Admin can approve payroll.')
        return redirect('payroll:run_detail', run_id=run_id)
    run = get_object_or_404(PayrollRun, pk=run_id)
    if request.method == 'POST':
        if run.status == PayrollRunStatus.DRAFT:
            run.status = PayrollRunStatus.PENDING_APPROVAL
            run.save()
            messages.info(request, 'Payroll submitted for approval.')
        elif run.status == PayrollRunStatus.PENDING_APPROVAL:
            run.status = PayrollRunStatus.APPROVED
            run.approved_by = request.user
            run.approved_at = timezone.now()
            run.payslips.filter(status='DRAFT').update(status='APPROVED')
            run.save()
            messages.success(request, 'Payroll approved.')
    return redirect('payroll:run_detail', run_id=run_id)


@login_required
def run_mark_paid(request, run_id):
    if not _can_approve(request.user):
        messages.error(request, 'Access denied.')
        return redirect('payroll:run_detail', run_id=run_id)
    run = get_object_or_404(PayrollRun, pk=run_id)
    if request.method == 'POST' and run.status == PayrollRunStatus.APPROVED:
        with transaction.atomic():
            run.status = PayrollRunStatus.PAID
            run.paid_at = timezone.now()
            run.payslips.all().update(status='PAID')
            run.save()
            # GL posting: Dr 661000 Rémunérations / Cr 421000 Rémunérations dues
            _post_payroll_gl(run, request.user)
        messages.success(request, f'Payroll marked as PAID — {run}. GL entries posted.')
    return redirect('payroll:run_detail', run_id=run_id)


def _post_payroll_gl(run, user):
    """Post GL entries when payroll is marked paid."""
    try:
        from apps.billing.models import JournalEntry, JournalLine, GLAccount, JournalEntryStatus
        from django.db.models import Sum as _Sum
        totals = run.payslips.aggregate(
            gross=_Sum('gross_pay'),
            net=_Sum('net_pay'),
            cnps_emp=_Sum('cnps_employee'),
            cnps_empl=_Sum('cnps_employer'),
            irpp=_Sum('withholding_tax'),
        )
        gross  = totals['gross']  or Decimal('0')
        net    = totals['net']    or Decimal('0')
        cnps_e = totals['cnps_emp']  or Decimal('0')
        cnps_r = totals['cnps_empl'] or Decimal('0')
        irpp   = totals['irpp']   or Decimal('0')

        # Find or use fallback GL accounts
        def _acct(code):
            return GLAccount.objects.filter(code__startswith=code, is_deleted=False).first()

        sal_exp   = _acct('661')   # 661000 Salaires et traitements
        cnps_exp  = _acct('664')   # 664000 Charges sociales patronales
        sal_payab = _acct('421')   # 421000 Rémunérations dues
        cnps_payab= _acct('431')   # 431000 CNPS à payer
        tax_payab = _acct('447')   # 447000 IRPP à reverser

        if not sal_exp or not sal_payab:
            return  # GL accounts not configured — skip silently

        entry = JournalEntry.objects.create(
            entry_date=timezone.localdate(),
            reference=f'PAY-{run.year}-{run.month:02d}',
            description=f'Payroll {run.period_label} — {run.payslips.count()} staff',
            status=JournalEntryStatus.POSTED,
            created_by=user,
        )
        lines = [
            # Dr Salary expense (gross)
            JournalLine(entry=entry, account=sal_exp,   debit_amount=gross,  credit_amount=0,    description='Salaires bruts'),
        ]
        # Dr Employer CNPS charge
        if cnps_exp and cnps_r:
            lines.append(JournalLine(entry=entry, account=cnps_exp, debit_amount=cnps_r, credit_amount=0, description='Charges patronales CNPS'))
        # Cr Net salary payable
        lines.append(JournalLine(entry=entry, account=sal_payab,  debit_amount=0, credit_amount=net,    description='Salaires nets à payer'))
        # Cr CNPS to remit (employee + employer)
        if cnps_payab and (cnps_e + cnps_r):
            lines.append(JournalLine(entry=entry, account=cnps_payab, debit_amount=0, credit_amount=cnps_e+cnps_r, description='CNPS à reverser'))
        # Cr IRPP to remit
        if tax_payab and irpp:
            lines.append(JournalLine(entry=entry, account=tax_payab, debit_amount=0, credit_amount=irpp, description='IRPP à reverser DGI'))
        JournalLine.objects.bulk_create(lines)
    except Exception:
        pass  # Never block payroll marking


# ── CNPS Declaration ────────────────────────────────────────────────────────────
@login_required
def cnps_declaration(request, run_id):
    """Generate the monthly CNPS declaration summary."""
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    run = get_object_or_404(PayrollRun, pk=run_id)
    slips = run.payslips.select_related('staff').order_by('staff__last_name')
    from django.db.models import Sum as _S
    totals = slips.aggregate(
        gross=_S('gross_pay'), emp=_S('cnps_employee'), empl=_S('cnps_employer'),
    )
    return render(request, 'payroll/cnps_declaration.html', {
        'run': run,
        'slips': slips,
        'totals': totals,
        'cnps_emp_rate': _CNPS_EMP_RATE * 100,
        'cnps_empl_rate': _CNPS_EMPL_RATE * 100,
        'cnps_cap': _CNPS_CAP,
    })


# ── Payslip PDF (WeasyPrint — Cameroon-compliant bulletin de paie) ───────────────
@login_required
def payslip_pdf(request, slip_id):
    """Generate a Cameroon-compliant payslip as a downloadable/inline PDF."""
    slip = get_object_or_404(PaySlip, pk=slip_id)
    if not _can_manage(request.user) and slip.staff != request.user:
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    lines = slip.lines.order_by('component_type', 'description')
    earnings   = [l for l in lines if l.component_type == ComponentType.EARNING]
    # Only non-statutory deduction lines (CNPS + IRPP already shown separately in template)
    deductions = [l for l in lines if l.component_type == ComponentType.DEDUCTION]
    other_ded_total = sum(l.amount for l in deductions)

    from apps.reports.views import _sig_b64, render_pdf
    from django.conf import settings

    # Use Finance Director / HR authorizer signature — fall back to request.user sig
    authorizer_sig = ''
    try:
        from apps.accounts.models import UserRole
        hr = slip.payroll_run.created_by
        if hr:
            authorizer_sig = _sig_b64(hr)
    except Exception:
        pass

    cnps_base = min(slip.gross_pay, _CNPS_CAP)
    prof_deduction = min(slip.gross_pay * Decimal('0.30'), Decimal('33333'))
    taxable_income = max(Decimal('0'), slip.gross_pay - slip.cnps_employee - prof_deduction)

    context = {
        'slip': slip,
        'earnings': earnings,
        'deductions': deductions,
        'other_deductions_total': other_ded_total if other_ded_total else None,
        'cnps_base': cnps_base,
        'taxable_income': taxable_income,
        'authorizer_signature': authorizer_sig,
        'today': timezone.localdate(),
        'hospital_name': getattr(settings, 'HOSPITAL_NAME', ''),
        'hospital_address': getattr(settings, 'HOSPITAL_ADDRESS', ''),
        'hospital_phone': getattr(settings, 'HOSPITAL_PHONE', ''),
        'pdf_filename': (
            f"bulletin_paie_{slip.staff.employee_id or slip.staff.username}"
            f"_{slip.payroll_run.year}_{slip.payroll_run.month:02d}.pdf"
        ),
        'pdf_seal_label': 'BULLETIN DE PAIE',
    }
    return render_pdf('payroll/payslip_pdf.html', context)


# ── Payslip Print (printable A4) ────────────────────────────────────────────────
@login_required
def payslip_print(request, slip_id):
    """Printable A4 payslip view — links to PDF download."""
    slip = get_object_or_404(PaySlip, pk=slip_id)
    if not _can_manage(request.user) and slip.staff != request.user:
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    lines = slip.lines.order_by('component_type', 'description')
    earnings   = [l for l in lines if l.component_type == ComponentType.EARNING]
    # Non-statutory deductions only — CNPS + IRPP shown separately in template
    deductions = [l for l in lines if l.component_type == ComponentType.DEDUCTION]

    # Compute display helpers: CNPS base (capped) and taxable income
    cnps_base = min(slip.gross_pay, _CNPS_CAP)
    prof_deduction = min(slip.gross_pay * Decimal('0.30'), Decimal('33333'))
    taxable_income = max(Decimal('0'), slip.gross_pay - slip.cnps_employee - prof_deduction)

    from apps.reports.views import _sig_b64
    return render(request, 'payroll/payslip_print.html', {
        'slip': slip,
        'earnings': earnings,
        'deductions': deductions,
        'cnps_base': cnps_base,
        'taxable_income': taxable_income,
        'sig': _sig_b64(request.user),
    })


# ── Individual Payslip ─────────────────────────────────────────────────────────
@login_required
def payslip_detail(request, slip_id):
    if not _can_manage(request.user):
        # Staff can view their own payslip
        slip = get_object_or_404(PaySlip, pk=slip_id)
        if slip.staff != request.user:
            messages.error(request, 'Access denied.')
            return redirect('dashboard:home')
    else:
        slip = get_object_or_404(PaySlip, pk=slip_id)
    lines = slip.lines.order_by('component_type', 'description')
    return render(request, 'payroll/payslip_detail.html', {'slip': slip, 'lines': lines})


@login_required
def my_payslips(request):
    """Staff view their own payslips."""
    slips = PaySlip.objects.filter(staff=request.user).select_related('payroll_run').order_by(
        '-payroll_run__year', '-payroll_run__month'
    )
    return render(request, 'payroll/my_payslips.html', {'slips': slips})
