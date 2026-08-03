"""
Standalone script: creates the default field_admin account if it doesn't exist.
Run via: python outreach_field/create_admin.py
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['DJANGO_SETTINGS_MODULE'] = 'outreach_field.settings_field'
django.setup()

from apps.accounts.models import User

if not User.objects.filter(username='field_admin').exists():
    u = User.objects.create_superuser('field_admin', '', 'field123')
    u.role = 'super_admin'
    u.save()
    print('Default login created: field_admin / field123')
else:
    print('field_admin already exists.')
