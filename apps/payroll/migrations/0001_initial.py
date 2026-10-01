import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SalaryComponent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(max_length=150)),
                ('code', models.CharField(max_length=20, unique=True)),
                ('component_type', models.CharField(
                    choices=[('EARNING', 'Earning'), ('DEDUCTION', 'Deduction'), ('STATUTORY', 'Statutory (CNPS / Tax)')],
                    max_length=20)),
                ('is_percentage', models.BooleanField(default=False)),
                ('default_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('is_taxable', models.BooleanField(default=True)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={'ordering': ['component_type', 'name']},
        ),
        migrations.CreateModel(
            name='SalaryStructure',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(max_length=150)),
                ('description', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='StructureComponent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('override_amount', models.DecimalField(decimal_places=2, max_digits=12, null=True, blank=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('salary_structure', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='components', to='payroll.salarystructure')),
                ('component', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='structure_components', to='payroll.salarycomponent')),
            ],
            options={'ordering': ['sort_order']},
        ),
        migrations.AddConstraint(
            model_name='structurecomponent',
            constraint=models.UniqueConstraint(fields=['salary_structure', 'component'],
                                                name='unique_structure_component'),
        ),
        migrations.CreateModel(
            name='StaffSalaryAssignment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('basic_salary', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('effective_from', models.DateField()),
                ('notes', models.TextField(blank=True)),
                ('staff', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                    related_name='salary_assignment', to=settings.AUTH_USER_MODEL)),
                ('structure', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    to='payroll.salarystructure')),
            ],
            options={'ordering': ['-effective_from']},
        ),
        migrations.CreateModel(
            name='PayrollRun',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('year', models.PositiveIntegerField()),
                ('month', models.PositiveIntegerField()),
                ('description', models.CharField(blank=True, max_length=200)),
                ('status', models.CharField(
                    choices=[('DRAFT', 'Draft'), ('PENDING', 'Pending Approval'),
                             ('APPROVED', 'Approved'), ('PAID', 'Paid'), ('CANCELLED', 'Cancelled')],
                    default='DRAFT', max_length=20)),
                ('total_gross', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('total_deductions', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('total_net', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('notes', models.TextField(blank=True)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='payroll_runs_created', to=settings.AUTH_USER_MODEL)),
                ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='payroll_runs_approved', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-year', '-month']},
        ),
        migrations.AddConstraint(
            model_name='payrollrun',
            constraint=models.UniqueConstraint(fields=['year', 'month'], name='unique_payroll_month'),
        ),
        migrations.CreateModel(
            name='PaySlip',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('basic_salary', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('gross_pay', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('total_deductions', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('net_pay', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('cnps_employee', models.DecimalField(decimal_places=2, default=0, max_digits=10,
                    verbose_name='CNPS Employee (NSIF 2.8%)')),
                ('cnps_employer', models.DecimalField(decimal_places=2, default=0, max_digits=10,
                    verbose_name='CNPS Employer (NSIF 4.7%)')),
                ('withholding_tax', models.DecimalField(decimal_places=2, default=0, max_digits=10,
                    verbose_name='Withholding Tax (IRPP)')),
                ('status', models.CharField(
                    choices=[('DRAFT', 'Draft'), ('APPROVED', 'Approved'), ('PAID', 'Paid')],
                    default='DRAFT', max_length=20)),
                ('payment_date', models.DateField(blank=True, null=True)),
                ('payment_method', models.CharField(blank=True, max_length=20)),
                ('notes', models.TextField(blank=True)),
                ('payroll_run', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='payslips', to='payroll.payrollrun')),
                ('staff', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='payslips', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['payroll_run', 'staff__last_name']},
        ),
        migrations.AddConstraint(
            model_name='payslip',
            constraint=models.UniqueConstraint(fields=['payroll_run', 'staff'], name='unique_payslip'),
        ),
        migrations.CreateModel(
            name='PaySlipLine',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('description', models.CharField(max_length=200)),
                ('component_type', models.CharField(
                    choices=[('EARNING', 'Earning'), ('DEDUCTION', 'Deduction'), ('STATUTORY', 'Statutory (CNPS / Tax)')],
                    max_length=20)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('payslip', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='lines', to='payroll.payslip')),
                ('component', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT,
                    to='payroll.salarycomponent')),
            ],
            options={'ordering': ['component_type', 'description']},
        ),
    ]
