import os, sys, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ehr_project.settings.production")
sys.path.insert(0, "/opt/ehr-africa")
django.setup()

from datetime import date
from django.utils import timezone
from apps.patients.models import Patient, Visit, NextOfKin, MedicalHistory
from apps.accounts.models import User

today = timezone.localdate()
created_by = User.objects.filter(role="receptionist").first() or User.objects.first()

patients_data = [
    {
        "first_name": "Henriette",
        "last_name": "Tchoumba",
        "middle_name": "Alvine",
        "gender": "F",
        "dob": "1982-04-15",
        "phone": "+237677001101",
        "nationality": "Cameroonian",
        "occupation": "Director General",
        "quarter": "Bastos",
        "village_town": "Yaounde",
        "tier": "VIP",
        "nok_name": "Michel Tchoumba",
        "nok_rel": "Spouse",
        "nok_phone": "+237677002101",
        "complaint": "Blurred vision and eye strain",
    },
    {
        "first_name": "Christian",
        "last_name": "Mbida",
        "middle_name": "Patrick",
        "gender": "M",
        "dob": "1990-08-22",
        "phone": "+237678003102",
        "nationality": "Cameroonian",
        "occupation": "Engineer",
        "quarter": "Mvan",
        "village_town": "Yaounde",
        "tier": "EXPRESS",
        "nok_name": "Francoise Mbida",
        "nok_rel": "Mother",
        "nok_phone": "+237678004102",
        "complaint": "Eye redness and discharge for 3 days",
    },
    {
        "first_name": "Laure",
        "last_name": "Nguema",
        "middle_name": "Beatrice",
        "gender": "F",
        "dob": "1975-11-03",
        "phone": "+237699005103",
        "nationality": "Cameroonian",
        "occupation": "Teacher",
        "quarter": "Biyem-Assi",
        "village_town": "Yaounde",
        "tier": "FAST_TRACK",
        "nok_name": "Pierre Nguema",
        "nok_rel": "Husband",
        "nok_phone": "+237699006103",
        "complaint": "Difficulty reading, needs glasses check",
    },
    {
        "first_name": "Moussa",
        "last_name": "Hamidou",
        "middle_name": "Adamou",
        "gender": "M",
        "dob": "1988-02-17",
        "phone": "+237670007104",
        "nationality": "Cameroonian",
        "occupation": "Farmer",
        "quarter": "Mokolo",
        "village_town": "Yaounde",
        "tier": "STANDARD",
        "nok_name": "Fatima Hamidou",
        "nok_rel": "Wife",
        "nok_phone": "+237670008104",
        "complaint": "Painful eye and light sensitivity",
    },
]

for d in patients_data:
    dob = date.fromisoformat(d["dob"])
    p = Patient.objects.create(
        first_name=d["first_name"],
        last_name=d["last_name"],
        middle_name=d.get("middle_name", ""),
        gender=d["gender"],
        date_of_birth=dob,
        phone_number=d["phone"],
        nationality=d["nationality"],
        occupation=d["occupation"],
        quarter=d["quarter"],
        village_town=d["village_town"],
        created_by=created_by,
    )
    MedicalHistory.objects.create(patient=p)
    NextOfKin.objects.create(
        patient=p,
        full_name=d["nok_name"],
        relationship=d["nok_rel"],
        phone_number=d["nok_phone"],
    )
    v = Visit.objects.create(
        patient=p,
        visit_type="NEW",
        chief_complaint=d["complaint"],
        status="AT_CASHIER",
        service_tier=d["tier"],
        billing_type="SELF_PAY",
        visit_date=timezone.now(),
        created_by=created_by,
    )
    print(f"[{d['tier']:10s}] {p.full_name:35s}  ID={p.patient_id}  Visit={v.visit_number}")

print("\nDone — 4 patients waiting at their tier cashier counters.")
