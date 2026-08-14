import os, sys, django
os.chdir('/opt/ehr-africa')
sys.path.insert(0, '/opt/ehr-africa')
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.production'
django.setup()
from apps.accounts.models import User
usernames = ['gate01','recep01','medrec01','nurse01','cnurse01','wardnurse01',
             'doctor01','retina01','glauco01','cataract01','optom01','paedoph01',
             'lowvis01','anaes01','meddir01','cashier01','cashiervip','cashierexp',
             'chiefcash01','billing01','account01','tso01','pharma01','labtech01',
             'invest01','optics01','theatre01','admiss01','findir01','admindir01','ceo01']
deleted = User.objects.filter(username__in=usernames).delete()
print(f'Deleted: {deleted}')
