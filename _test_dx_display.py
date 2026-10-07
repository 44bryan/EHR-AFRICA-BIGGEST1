import os, django, re
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.base'
django.setup()
from django.test import Client
from apps.accounts.models import User

c = Client()
user = User.objects.get(username='admin')
c.force_login(user)

# Patient detail
resp = c.get('/patients/EHR-2026-041473/')
html = resp.content.decode()

print("=== PATIENT DETAIL ===")
idx = html.find('Latest Dx')
print("Quick View card:", "FOUND" if idx >= 0 else "NOT FOUND")
if idx >= 0:
    print(repr(html[idx-50:idx+200]))

count = html.count('Mature Cataract')
print("Mature Cataract occurrences:", count)

idx_banner = html.find('Last Dx:')
print("Banner Last Dx:", "FOUND" if idx_banner >= 0 else "NOT FOUND")
if idx_banner >= 0:
    print(repr(html[idx_banner:idx_banner+200]))

# Consultation create page
print("\n=== CONSULTATION CREATE ===")
resp2 = c.get('/consultations/new/EHR-2026-041473/')
html2 = resp2.content.decode()
idx2 = html2.find('Mature Cataract')
print("Mature Cataract in create:", "FOUND" if idx2 >= 0 else "NOT FOUND")
if idx2 >= 0:
    print(repr(html2[idx2-80:idx2+80]))

idx3 = html2.find('Dx:')
print("Dx label in create:", "FOUND" if idx3 >= 0 else "NOT FOUND")
if idx3 >= 0:
    print(repr(html2[idx3-50:idx3+100]))

# Check diagnosis_summary field pre-filled
idx4 = html2.find('diagnosis_summary')
print("diagnosis_summary field:", "FOUND" if idx4 >= 0 else "NOT FOUND")
