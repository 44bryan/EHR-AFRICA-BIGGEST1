from django.contrib import admin
from .models import SalaryComponent, SalaryStructure, StructureComponent, StaffSalaryAssignment, PayrollRun, PaySlip

admin.site.register(SalaryComponent)
admin.site.register(SalaryStructure)
admin.site.register(StructureComponent)
admin.site.register(StaffSalaryAssignment)
admin.site.register(PayrollRun)
admin.site.register(PaySlip)
