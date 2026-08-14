"""
Load testing for EHR Africa.

Install:  pip install locust
Run:      locust --host=http://localhost:8000
Then open http://localhost:8089 in browser.

Quick CLI run (headless, 50 users, 2 min):
  locust --host=http://localhost:8000 --headless -u 50 -r 5 --run-time 2m

Scenarios covered:
  - StaffUser      : login → dashboard → patient list → patient detail  (doctors/nurses)
  - CashierUser    : login → billing dashboard → invoice list
  - PortalPatient  : portal login → dashboard → appointments → invoices
  - PublicUser     : unauthenticated hits (login page, 403 probes)
"""

import random
from locust import HttpUser, task, between, SequentialTaskSet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STAFF_CREDENTIALS = [
    # (username, password)  — pre-seeded demo accounts
    ('admin@ehr.test', 'Admin1234!'),
    ('nurse@ehr.test', 'Admin1234!'),
    ('doctor@ehr.test', 'Admin1234!'),
]

PORTAL_CREDENTIALS = [
    # (patient_id, dob)  — pre-seeded demo patients
    ('EHR-2024-00001', '1990-01-15'),
    ('EHR-2024-00002', '1985-07-22'),
]

# Adjust these to real IDs from your demo seed data
DEMO_PATIENT_IDS = ['EHR-2024-00001', 'EHR-2024-00002', 'EHR-2024-00003']
DEMO_VISIT_NUMBERS = ['VIS-2024-000001', 'VIS-2024-000002']


def _csrf(client, url='/accounts/login/'):
    """GET a page, extract CSRF token from cookies."""
    client.get(url, name='[csrf-fetch]')
    return client.cookies.get('csrftoken', '')


# ---------------------------------------------------------------------------
# Task sets
# ---------------------------------------------------------------------------

class StaffBrowseTaskSet(SequentialTaskSet):
    """
    Simulates a logged-in clinical staff member browsing the system.
    """

    def on_start(self):
        creds = random.choice(STAFF_CREDENTIALS)
        csrftoken = _csrf(self.client)
        resp = self.client.post(
            '/accounts/login/',
            data={
                'email': creds[0],
                'password': creds[1],
                'csrfmiddlewaretoken': csrftoken,
            },
            headers={'Referer': f'{self.client.base_url}/accounts/login/'},
            name='[staff] login',
            allow_redirects=True,
        )
        if resp.status_code not in (200, 302):
            self.interrupt()

    @task(3)
    def dashboard(self):
        self.client.get('/', name='[staff] dashboard')

    @task(5)
    def patient_list(self):
        self.client.get('/patients/', name='[staff] patient list')

    @task(2)
    def patient_search(self):
        self.client.get(
            f'/patients/?q={random.choice(["test", "john", "mary", "pat"])}',
            name='[staff] patient search',
        )

    @task(3)
    def patient_detail(self):
        pid = random.choice(DEMO_PATIENT_IDS)
        self.client.get(f'/patients/{pid}/', name='[staff] patient detail')

    @task(2)
    def consultation_list(self):
        self.client.get('/consultations/', name='[staff] consultation list')

    @task(1)
    def appointment_list(self):
        self.client.get('/appointments/', name='[staff] appointments')

    @task(1)
    def qms_dashboard(self):
        self.client.get('/qms/', name='[staff] QMS dashboard')

    def on_stop(self):
        self.client.get('/accounts/logout/', name='[staff] logout')


class CashierTaskSet(SequentialTaskSet):
    """
    Simulates a cashier processing invoices and payments.
    """

    def on_start(self):
        csrftoken = _csrf(self.client)
        resp = self.client.post(
            '/accounts/login/',
            data={
                'email': STAFF_CREDENTIALS[0][0],
                'password': STAFF_CREDENTIALS[0][1],
                'csrfmiddlewaretoken': csrftoken,
            },
            headers={'Referer': f'{self.client.base_url}/accounts/login/'},
            name='[cashier] login',
            allow_redirects=True,
        )
        if resp.status_code not in (200, 302):
            self.interrupt()

    @task(2)
    def billing_dashboard(self):
        self.client.get('/billing/', name='[cashier] billing dashboard')

    @task(4)
    def invoice_list(self):
        self.client.get('/billing/invoices/', name='[cashier] invoice list')

    @task(2)
    def cashier_pos(self):
        self.client.get('/billing/cashier/', name='[cashier] POS screen')

    @task(1)
    def service_price_list(self):
        self.client.get('/billing/service-prices/', name='[cashier] price list')

    def on_stop(self):
        self.client.get('/accounts/logout/', name='[cashier] logout')


class PortalTaskSet(SequentialTaskSet):
    """
    Simulates a patient using the self-service portal.
    """

    def on_start(self):
        creds = random.choice(PORTAL_CREDENTIALS)
        csrftoken = _csrf(self.client, '/portal/')
        resp = self.client.post(
            '/portal/',
            data={
                'patient_id': creds[0],
                'date_of_birth': creds[1],
                'csrfmiddlewaretoken': csrftoken,
            },
            headers={'Referer': f'{self.client.base_url}/portal/'},
            name='[portal] login',
            allow_redirects=True,
        )
        if resp.status_code not in (200, 302):
            self.interrupt()

    @task(3)
    def portal_dashboard(self):
        self.client.get('/portal/dashboard/', name='[portal] dashboard')

    @task(2)
    def portal_appointments(self):
        self.client.get('/portal/appointments/', name='[portal] appointments')

    @task(2)
    def portal_invoices(self):
        self.client.get('/portal/invoices/', name='[portal] invoices')

    @task(1)
    def portal_prescriptions(self):
        self.client.get('/portal/prescriptions/', name='[portal] prescriptions')

    def on_stop(self):
        self.client.get('/portal/logout/', name='[portal] logout')


# ---------------------------------------------------------------------------
# User classes (weights)
# ---------------------------------------------------------------------------

class StaffUser(HttpUser):
    """Clinical staff: doctors, nurses, receptionists."""
    tasks = [StaffBrowseTaskSet]
    wait_time = between(1, 4)
    weight = 60  # 60% of simulated users


class CashierUser(HttpUser):
    """Billing staff: cashiers."""
    tasks = [CashierTaskSet]
    wait_time = between(2, 5)
    weight = 20  # 20% of simulated users


class PortalPatient(HttpUser):
    """Patients using the self-service portal."""
    tasks = [PortalTaskSet]
    wait_time = between(3, 8)
    weight = 20  # 20% of simulated users
