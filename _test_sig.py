import sys, os
sys.path.insert(0, "/opt/ehr-africa")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ehr_project.settings.base")
import django; django.setup()

from apps.accounts.models import User
from apps.reports.views import _sig_b64

# Test with admin user
admin = User.objects.get(username="admin")
print("Admin signature field:", admin.signature.name)
print("Admin signature path:", admin.signature.path)
print("File exists:", os.path.exists(admin.signature.path))

sig = _sig_b64(admin)
print("_sig_b64 result length:", len(sig))
if sig:
    print("Starts with:", sig[:40])
else:
    print("EMPTY - no signature returned!")

# Test with a doctor who has consultations
from apps.consultations.models import Consultation
c = Consultation.objects.select_related('consulting_doctor').first()
if c:
    doc = c.consulting_doctor
    print("\nDoctor:", doc.username, doc.get_full_name())
    if doc.signature:
        print("Doctor sig field:", doc.signature.name)
        try:
            print("Doctor sig path:", doc.signature.path)
            print("File exists:", os.path.exists(doc.signature.path))
        except Exception as e:
            print("Path error:", e)
    else:
        print("Doctor has NO signature field value")
    sig2 = _sig_b64(doc)
    print("_sig_b64 length:", len(sig2))
    if sig2:
        print("Starts with:", sig2[:40])
    else:
        print("EMPTY - no signature for doctor!")
