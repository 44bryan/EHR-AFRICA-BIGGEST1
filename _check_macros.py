import django, os
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.base'
django.setup()
from apps.consultations.models import ClinicalTemplate
from django.db.models import Q

total = ClinicalTemplate.objects.filter(is_deleted=False, is_active=True).count()
print("Total active templates:", total)

# Show first 5
for t in ClinicalTemplate.objects.filter(is_deleted=False, is_active=True)[:5]:
    dept_name = str(t.department) if t.department else "None"
    by_name = str(t.created_by) if t.created_by else "None"
    print("  " + t.title + " | type=" + t.template_type + " | dept=" + dept_name + " | shared=" + str(t.is_shared) + " | by=" + by_name)

# Simulate the search endpoint with dept=GEN_OPH
qs = ClinicalTemplate.objects.filter(is_deleted=False, is_active=True)
qs_dept = qs.filter(Q(department__code='GEN_OPH') | Q(department__isnull=True))
print("\nWith dept=GEN_OPH filter:", qs_dept.count(), "results")

# Simulate with no dept
qs_nodept = qs.filter(Q(department__isnull=True) | Q(is_shared=True))
print("With no dept filter:", qs_nodept.count(), "results")
