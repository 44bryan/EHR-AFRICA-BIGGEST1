import django, os
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.base'
django.setup()

from django.test import RequestFactory, Client
from apps.accounts.models import User

# Get a doctor user
doctor = User.objects.filter(is_active=True, role='ophthalmologist').first()
print("Testing as:", doctor.username, doctor.get_full_name())

client = Client()
client.force_login(doctor)

# Test the template search endpoint
response = client.get('/consultations/templates/search/', {'q': '', 'type': '', 'dept': 'GEN_OPH'},
                       HTTP_X_REQUESTED_WITH='XMLHttpRequest')
print("Status:", response.status_code)
import json
data = json.loads(response.content)
print("Results count:", len(data.get('results', [])))
for r in data.get('results', [])[:3]:
    print("  -", r['title'], "|", r['template_type'])
