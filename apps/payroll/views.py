"""
Payroll Module Views
Salary structures, payroll runs, and payslip management.
"""
from decimal import Decimal
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
            gross = Decimal('0')
            deductions = Decimal('0')
            cnps_emp = Decimal('0')
            cnps_empl = Decimal('0')
            wh_tax = Decimal('0')

            for sc in assignment.structure.components.select_related('component').order_by('sort_order'):
                comp = sc.component
                amount = sc.effective_amount(basic)
                lines_data.append((comp, comp.component_type, amount))
                if comp.component_type == ComponentType.EARNING:
                    gross += amount
                elif comp.component_type in (ComponentType.DEDUCTION, ComponentType.STATUTORY):
                    deductions += amount
                if comp.code == 'CNPS_EMP':
                    cnps_emp = amount
                elif comp.code == 'CNPS_EMPL':
                    cnps_empl = amount
                elif comp.code == 'IRPP':
                    wh_tax = amount

            # Add basic salary as an earning line
            gross += basic

            slip = PaySlip.objects.create(
                payroll_run=run,
                staff=assignment.staff,
                basic_salary=basic,
                gross_pay=gross,
                total_deductions=deductions,
                net_pay=gross - deductions,
                cnps_employee=cnps_emp,
                cnps_employer=cnps_empl,
                withholding_tax=wh_tax,
            )
            PaySlipLine.objects.create(
                payslip=slip, component_id=None if not lines_data else lines_data[0][0].pk,
                description='Basic Salary',
                component_type=ComponentType.EARNING,
                amount=basic,
            ) if not lines_data else None
            for comp, ctype, amount in lines_data:
                PaySlipLine.objects.create(
                    payslip=slip, component=comp, description=comp.name,
                    component_type=ctype, amount=amount,
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

    messages.success(request, f'Generated {created} payslips. {skipped} already existed.')
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
        run.status = PayrollRunStatus.PAID
        run.paid_at = timezone.now()
        run.payslips.all().update(status='PAID')
        run.save()
        messages.success(request, f'Payroll marked as PAID — {run}.')
    return redirect('payroll:run_detail', run_id=run_id)


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
