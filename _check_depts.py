import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
sys.path.insert(0, '/opt/ehr-africa')
django.setup()

from apps.accounts.models import User

# Check general physician users — are they flagged as is_doctor?
print("=== General Physician Users ===")
gp_users = User.objects.filter(role='general_physician')
for u in gp_users:
    dept = u.department
    dept_code = u.role_department_code
    print(f"  {u.username}: is_doctor={u.is_doctor}, dept_FK={dept}, role_dept_code={dept_code}, consult_unit={getattr(u,'consultation_unit','')}")

# Check who the current triage/refraction user is
print()
print("=== Doctor roles (who is routing patients) ===")
for u in User.objects.filter(role__in=['ophthalmologist','optometrist','opd_nurse']):
    print(f"  {u.username}: role={u.role}, dept={u.department}, dept_code={u.role_department_code}")
