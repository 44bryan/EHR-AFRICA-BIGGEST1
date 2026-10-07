"""Test pagination server-side with Django test client."""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
import django
django.setup()

from django.test import Client

c = Client()
c.login(username='admin', password='Admin2026')

# Test patient list page 1
r1 = c.get('/patients/')
print(f'Patients page 1: {r1.status_code}')
if r1.status_code == 200:
    html = r1.content.decode()
    import re
    page = re.search(r'Page (\d+) of (\d+)', html)
    if page:
        print(f'  Shows: Page {page.group(1)} of {page.group(2)}')
    # Check wrapper div
    wrapper = re.search(r'id="wrapper"([^>]*)', html)
    print(f'  Wrapper attrs: {wrapper.group(1).strip() if wrapper else "NOT FOUND"}')
    # hx-boost
    boost_count = html.count('hx-boost')
    print(f'  hx-boost count: {boost_count}')
    # Pagination links
    links = re.findall(r'href="([^"]*page=[^"]*)"', html)
    print(f'  Pagination links: {links}')
elif r1.status_code == 302:
    print(f'  REDIRECTS TO: {r1.url}')

# Test patient list page 2
r2 = c.get('/patients/?page=2')
print(f'\nPatients page 2: {r2.status_code}')
if r2.status_code == 200:
    html2 = r2.content.decode()
    page2 = re.search(r'Page (\d+) of (\d+)', html2)
    if page2:
        print(f'  Shows: Page {page2.group(1)} of {page2.group(2)}')
elif r2.status_code == 302:
    print(f'  REDIRECTS TO: {r2.url}')

# Test pharmacy drugs page 2
r3 = c.get('/pharmacy/drugs/?page=2')
print(f'\nPharmacy drugs page 2: {r3.status_code}')
if r3.status_code == 200:
    html3 = r3.content.decode()
    page3 = re.search(r'Page (\d+) of (\d+)', html3)
    if page3:
        print(f'  Shows: Page {page3.group(1)} of {page3.group(2)}')
elif r3.status_code == 302:
    print(f'  REDIRECTS TO: {r3.url}')

# Test with pharma01 account
c2 = Client()
c2.login(username='pharma01', password='Admin2026')
r4 = c2.get('/pharmacy/drugs/?page=2')
print(f'\nPharmacy drugs page 2 (pharma01): {r4.status_code}')
if r4.status_code == 302:
    print(f'  REDIRECTS TO: {r4.url}')
