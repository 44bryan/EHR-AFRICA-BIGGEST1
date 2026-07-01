"""
Tests: Patient self-service portal — session auth (Patient ID + DOB), dashboard, logout.
Run: python manage.py test tests.test_portal
"""
from django.test import TestCase, Client
from django.urls import reverse
from apps.patients.models import Patient


SESSION_KEY = 'portal_patient_id'


def make_portal_patient(suffix='P01'):
    return Patient.objects.create(
        first_name='Portal',
        last_name=f'User{suffix}',
        date_of_birth='1990-05-10',
        gender='F',
    )


class PortalLoginTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.patient = make_portal_patient()
        self.login_url = reverse('portal:login')

    def test_login_page_loads(self):
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)

    def test_valid_credentials_set_session_and_redirect(self):
        response = self.client.post(self.login_url, {
            'patient_id': self.patient.patient_id,
            'date_of_birth': '1990-05-10',
        })
        self.assertRedirects(response, reverse('portal:dashboard'), fetch_redirect_response=False)
        self.assertEqual(self.client.session.get(SESSION_KEY), self.patient.patient_id)

    def test_wrong_dob_rejected(self):
        response = self.client.post(self.login_url, {
            'patient_id': self.patient.patient_id,
            'date_of_birth': '1991-01-01',
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_wrong_patient_id_rejected(self):
        response = self.client.post(self.login_url, {
            'patient_id': 'EHR-DOESNOTEXIST',
            'date_of_birth': '1990-05-10',
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_invalid_dob_format_rejected(self):
        response = self.client.post(self.login_url, {
            'patient_id': self.patient.patient_id,
            'date_of_birth': 'not-a-date',
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_already_logged_in_redirects_to_dashboard(self):
        session = self.client.session
        session[SESSION_KEY] = self.patient.patient_id
        session.save()
        response = self.client.get(self.login_url)
        self.assertRedirects(response, reverse('portal:dashboard'), fetch_redirect_response=False)


class PortalDashboardTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.patient = make_portal_patient('P02')
        self.dashboard_url = reverse('portal:dashboard')

    def _login(self):
        session = self.client.session
        session[SESSION_KEY] = self.patient.patient_id
        session.save()

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(self.dashboard_url)
        self.assertRedirects(response, reverse('portal:login'), fetch_redirect_response=False)

    def test_authenticated_patient_can_view_dashboard(self):
        self._login()
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)

    def test_dashboard_context_has_patient(self):
        self._login()
        response = self.client.get(self.dashboard_url)
        self.assertIn('patient', response.context)
        self.assertEqual(response.context['patient'].pk, self.patient.pk)


class PortalLogoutTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.patient = make_portal_patient('P03')
        self.logout_url = reverse('portal:logout')

    def test_logout_clears_session_and_redirects(self):
        session = self.client.session
        session[SESSION_KEY] = self.patient.patient_id
        session.save()

        response = self.client.get(self.logout_url)
        self.assertRedirects(response, reverse('portal:login'), fetch_redirect_response=False)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_logout_when_not_logged_in_still_redirects(self):
        response = self.client.get(self.logout_url)
        self.assertRedirects(response, reverse('portal:login'), fetch_redirect_response=False)


class PortalProtectedViewsTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.patient = make_portal_patient('P04')

    def test_appointments_view_requires_portal_auth(self):
        url = reverse('portal:appointments')
        response = self.client.get(url)
        self.assertRedirects(response, reverse('portal:login'), fetch_redirect_response=False)

    def test_invoices_view_requires_portal_auth(self):
        url = reverse('portal:invoices')
        response = self.client.get(url)
        self.assertRedirects(response, reverse('portal:login'), fetch_redirect_response=False)

    def test_prescriptions_view_requires_portal_auth(self):
        url = reverse('portal:prescriptions')
        response = self.client.get(url)
        self.assertRedirects(response, reverse('portal:login'), fetch_redirect_response=False)
