import os, sys, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ehr_project.settings.production")
sys.path.insert(0, "/opt/ehr-africa")
django.setup()

from apps.departments.models import Department, ConsultationRoom

# General Ophthalmology rooms (VIP + Express + Standard)
gen = Department.objects.get(code="GEN_OPH")
for room_number, tier in [("1", "VIP"), ("2", "EXPRESS"), ("3", "STANDARD"), ("4", "STANDARD")]:
    obj, created = ConsultationRoom.objects.get_or_create(
        department=gen, room_number=room_number,
        defaults={"room_tier": tier, "label": f"Room {room_number}"},
    )
    print(f"{'Created' if created else 'Exists '}: {gen.name} Room {room_number} [{tier}]")

# Refraction rooms
refrac = Department.objects.filter(code="REFRAC").first()
if refrac:
    for room_number in ["1", "2"]:
        obj, created = ConsultationRoom.objects.get_or_create(
            department=refrac, room_number=room_number,
            defaults={"room_tier": "STANDARD", "label": f"Room {room_number}"},
        )
        print(f"{'Created' if created else 'Exists '}: {refrac.name} Room {room_number} [STANDARD]")

print("\nDone.")
