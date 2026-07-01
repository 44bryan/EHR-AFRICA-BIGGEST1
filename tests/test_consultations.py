"""
Tests: Consultation workstation access and clinic nurse call endpoint.
Run: python manage.py test tests.test_consultations
"""
import json
import uuid
from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import User, UserRole
from apps.patients.models import Patient, Visit


def make_user(role, username=None):
    count = User.objects.count()
    uname = username or f'u_{role}_{count}'
    return User.objects.create_user(
        username=uname,
        email=f'{uname}@ehr.test',
        employee_id=f'EMP{count:05d}',
        password='TestPass123!',
        role=role,
    )


def make_patient_and_visit(nurse, visit_type='NEW', status='PARAMETERS'):
    patient = Patient.objects.create(
        first_name='Consult',
        last_name='Test',
        date_of_birth='1992-03-20',
        gender='M',
    )
    visit = Visit.objects.create(
        patient=patient,
        visit_type=visit_type,
        chief_complaint='Blurry vision',
        status=status,
        created_by=nurse,
    )
    return patient, visit


class WorkstationPermissionTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.doctor = make_user(UserRole.OPHTHALMOLOGIST, 'doctor_ws')
        self.nurse = make_user(UserRole.NURSE, 'nurse_ws')
        self.cashier = make_user(UserRole.CASHIER, 'cashier_ws')
        _, self.visit = make_patient_and_visit(self.nurse, status='AT_DOCTOR')

    def test_doctor_can_access_workstation(self):
        self.client.force_login(self.doctor)
        url = reverse('consultations:workstation')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_cashier_blocked_from_workstation(self):
        self.client.force_login(self.cashier)
        url = reverse('consultations:workstation')
        response = self.client.get(url)
        self.assertIn(response.status_code, [403, 302])

    def test_workstation_requires_login(self):
        url = reverse('consultations:workstation')
        response = self.client.get(url)
        self.assertIn(response.status_code, [302, 403])


class ClinicNurseWorkstationTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.nurse = make_user(UserRole.NURSE, 'nurse_cn')
        self.admission = make_user(UserRole.ADMISSION_OFFICER, 'adm_cn')
        _, self.visit = make_patient_and_visit(self.nurse, status='PARAMETERS')

    def test_nurse_can_access_clinic_nurse_view(self):
        self.client.force_login(self.nurse)
        url = reverse('consultations:clinic_nurse')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_admission_officer_blocked_from_clinic_nurse(self):
        self.client.force_login(self.admission)
        url = reverse('consultations:clinic_nurse')
        response = self.client.get(url)
        self.assertIn(response.status_code, [403, 302])

    def test_clinic_nurse_unauthenticated_redirects(self):
        url = reverse('consultations:clinic_nurse')
        response = self.client.get(url)
        self.assertIn(response.status_code, [302, 403])


class ClinicCallEndpointTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.nurse = make_user(UserRole.NURSE, 'nurse_call')
        _, self.visit = make_patient_and_visit(self.nurse, status='PARAMETERS')

    def test_call_endpoint_requires_post(self):
        self.client.force_login(self.nurse)
        url = reverse('consultations:clinic_call', kwargs={'visit_pk': self.visit.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_call_endpoint_returns_json(self):
        self.client.force_login(self.nurse)
        url = reverse('consultations:clinic_call', kwargs={'visit_pk': self.visit.pk})
        response = self.client.post(
            url,
            HTTP_X_CSRFTOKEN='test',
            content_type='application/json',
        )
        self.assertEqual(response.get('Content-Type', '').split(';')[0], 'application/json')

    def test_call_nonexistent_visit_returns_404(self):
        self.client.force_login(self.nurse)
        fake_pk = uuid.uuid4()
        url = reverse('consultations:clinic_call', kwargs={'visit_pk': fake_pk})
        response = self.client.post(url, content_type='application/json')
        self.assertEqual(response.status_code, 404)

    def test_call_endpoint_unauthenticated_redirects(self):
        url = reverse('consultations:clinic_call', kwargs={'visit_pk': self.visit.pk})
        response = self.client.post(url, content_type='application/json')
        self.assertIn(response.status_code, [302, 403])
