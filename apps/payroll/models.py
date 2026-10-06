"""
Payroll Module
Salary structures, payroll runs, and payslip generation for AEF/MICEI.
Cameroon-specific: CNPS (NSIF) social security, withholding tax (IRPP).
"""
from decimal import Decimal
from django.db import models
from django.utils import timezone
from apps.core.models import AuditModel


class ComponentType(models.TextChoices):
    EARNING = 'EARNING', 'Earning'
    DEDUCTION = 'DEDUCTION', 'Deduction'
    STATUTORY = 'STATUTORY', 'Statutory (CNPS / Tax)'


class SalaryComponent(AuditModel):
    """Reusable pay component: base salary, housing allowance, CNPS, etc."""
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20, unique=True)
    component_type = models.CharField(max_length=20, choices=ComponentType.choices)
    is_percentage = models.BooleanField(default=False, help_text='If True, amount is % of basic salary')
    default_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_taxable = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['component_type', 'name']

    def __str__(self):
        return f"{self.code} — {self.name}"


class SalaryStructure(AuditModel):
    """Named salary structure assigned to a staff member."""
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class StructureComponent(AuditModel):
    """Assigns a SalaryComponent to a SalaryStructure with overridden amount."""
    salary_structure = models.ForeignKey(SalaryStructure, on_delete=models.CASCADE,
                                          related_name='components')
    component = models.ForeignKey(SalaryComponent, on_delete=models.CASCADE,
                                   related_name='structure_components')
    override_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                           help_text='Leave blank to use component default')
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order']
        unique_together = [('salary_structure', 'component')]

    def effective_amount(self, basic_salary=Decimal('0')):
        amount = self.override_amount if self.override_amount is not None else self.component.default_amount
        if self.component.is_percentage:
            return (basic_salary * amount / Decimal('100')).quantize(Decimal('1'))
        return amount


class StaffSalaryAssignment(AuditModel):
    """Links a User to a SalaryStructure + basic salary override."""
    staff = models.OneToOneField('accounts.User', on_delete=models.CASCADE,
                                  related_name='salary_assignment')
    structure = models.ForeignKey(SalaryStructure, on_delete=models.PROTECT)
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    effective_from = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-effective_from']

    def __str__(self):
        return f"{self.staff.full_name} — {self.structure}"


class PayrollRunStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    PENDING_APPROVAL = 'PENDING', 'Pending Approval'
    APPROVED = 'APPROVED', 'Approved'
    PAID = 'PAID', 'Paid'
    CANCELLED = 'CANCELLED', 'Cancelled'


class PayrollRun(AuditModel):
    """A monthly payroll processing batch."""
    year = models.PositiveIntegerField()
    month = models.PositiveIntegerField()  # 1-12
    description = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=PayrollRunStatus.choices,
                               default=PayrollRunStatus.DRAFT)
    total_gross = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                    null=True, related_name='payroll_runs_created')
    approved_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='payroll_runs_approved')
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-year', '-month']
        unique_together = [('year', 'month')]

    def __str__(self):
        import calendar
        return f"Payroll {calendar.month_name[self.month]} {self.year}"

    @property
    def period_label(self):
        import calendar
        return f"{calendar.month_name[self.month]} {self.year}"


class PaySlipStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    APPROVED = 'APPROVED', 'Approved'
    PAID = 'PAID', 'Paid'


class PaySlip(AuditModel):
    """Individual payslip generated per staff per PayrollRun."""
    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name='payslips')
    staff = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='payslips')
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gross_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cnps_employee = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                         verbose_name='CNPS Employee (NSIF 2.8%)')
    cnps_employer = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                         verbose_name='CNPS Employer (NSIF 4.7%)')
    withholding_tax = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                           verbose_name='Withholding Tax (IRPP)')
    status = models.CharField(max_length=20, choices=PaySlipStatus.choices, default=PaySlipStatus.DRAFT)
    payment_date = models.DateField(null=True, blank=True)
    payment_method = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['payroll_run', 'staff__last_name']
        unique_together = [('payroll_run', 'staff')]

    def __str__(self):
        return f"Payslip {self.staff.full_name} — {self.payroll_run}"


class PaySlipLine(AuditModel):
    """Individual line on a payslip (one per component)."""
    payslip = models.ForeignKey(PaySlip, on_delete=models.CASCADE, related_name='lines')
    component = models.ForeignKey(SalaryComponent, on_delete=models.PROTECT, null=True, blank=True)
    description = models.CharField(max_length=200)
    component_type = models.CharField(max_length=20, choices=ComponentType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ['component_type', 'description']

    def __str__(self):
        return f"{self.description}: {self.amount}"
