import sys, os
sys.path.insert(0, "/opt/ehr-africa")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ehr_project.settings.base")
import django; django.setup()

from django.template.loader import render_to_string
from apps.consultations.models import Consultation, ConsultationDiagnosis, ProcedureRecord
from apps.investigations.models import InvestigationOrder
from apps.reports.views import _sig_b64

c = Consultation.objects.select_related(
    'patient', 'department', 'consulting_doctor', 'co_signed_by', 'visit'
).prefetch_related(
    'consultation_diagnoses__diagnosis',
    'drug_prescriptions__items',
    'optical_prescriptions',
).first()

if not c:
    print("No consultations found")
    sys.exit(1)

print("Consultation:", c.pk)
print("Doctor:", c.consulting_doctor.username)

sig = _sig_b64(c.consulting_doctor)
print("Signature length:", len(sig))

# Build context same as the view
dept_data = []
raw = c.department_specific_data or {}
for key, val in raw.items():
    if val and str(val).strip():
        label = key.replace('_', ' ').replace(' od', ' OD').replace(' os', ' OS').title()
        dept_data.append((label, val))

context = {
    'consultation': c,
    'patient': c.patient,
    'diagnoses': c.consultation_diagnoses.select_related('diagnosis').all(),
    'drug_rxs': c.drug_prescriptions.prefetch_related('items').filter(is_deleted=False),
    'optical_rxs': c.optical_prescriptions.filter(is_deleted=False),
    'investigation_orders': InvestigationOrder.objects.filter(
        consultation=c, is_deleted=False
    ).select_related('investigation_type').order_by('created_at'),
    'procedures': ProcedureRecord.objects.filter(
        consultation=c, is_deleted=False
    ).order_by('procedure_date'),
    'dept_data': dept_data,
    'doctor_signature': sig,
}

html = render_to_string('reports/pdf/consultation_report.html', context)

# Check if signature data is in HTML
if 'data:image/png;base64' in html:
    print("SIGNATURE IS IN HTML - working!")
    idx = html.index('data:image/png;base64')
    print("Found at position:", idx)
    print("Context:", html[idx-50:idx+50])
else:
    print("SIGNATURE NOT IN HTML!")
    # Check if doctor_signature variable was empty
    if 'signature-block' in html:
        idx = html.index('signature-block')
        print("Signature block HTML:", html[idx:idx+300])
