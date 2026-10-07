#!/usr/bin/env python
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from apps.hmo.models import InsuranceScheme
print('HMO models OK')
print('Schemes:', InsuranceScheme.objects.count())

from apps.accounts.models import HospitalConfig
cfg = HospitalConfig.get()
print('module_hmo:', cfg.module_hmo)

# Check URL resolution
from django.urls import reverse
try:
    print('hmo:dashboard ->', reverse('hmo:dashboard'))
    print('hmo:scheme_list ->', reverse('hmo:scheme_list'))
    print('hmo:scheme_create ->', reverse('hmo:scheme_create'))
except Exception as e:
    print('URL error:', e)
