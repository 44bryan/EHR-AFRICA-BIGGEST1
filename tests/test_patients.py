"""
Tests: Patient registration, visit creation, and triage permissions.
Run: python manage.py test tests.test_patients
"""
from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import User, UserRole
from apps.patients.models import Patient, Visit


def make_user(role, username=None):
    count = User.objects.count()
    uname = username or f"u_{role}_{count}"
    return User.objects.create_user(
        username=uname,
        email=f"{uname}@ehr.test",
        employee_id=f"EMP{count:05d}",
        password="TestPass123!",
        role=role,
    )


def make_patient(suffix="001"):
    return Patient.objects.create(
        first_name="Test",
        last_name=f"Patient{suffix}",
        date_of_birth="1990-01-01",
        gender="M",
    )


class PatientModelTest(TestCase):

    def test_patient_id_auto_generated(self):
        p = make_patient()
        self.assertIsNotNone(p.patient_id)
        self.assertTrue(len(p.patient_id) > 0)

    def test_full_name_property(self):
        p = make_patient()
        self.assertIn("Test", p.full_name)
        self.assertIn("Patient", p.full_name)

    def test_patient_is_active_by_default(self):
        p = make_patient()
        self.assertTrue(p.is_active)

    def test_soft_delete(self):
        p = make_patient("002")
        p.is_deleted = True
        p.save()
        self.assertFalse(Patient.objects.filter(pk=p.pk, is_deleted=False).exists())


class TriagePermissionViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.patient = make_patient("003")
        self.nurse = make_user(UserRole.NURSE)
        self.admission = make_user(UserRole.ADMISSION_OFFICER)
        self.visit = Visit.objects.create(
            patient=self.patient,
            visit_type='NEW',
            chief_complaint='Eye pain',
            status='PARAMETERS',
            created_by=self.nurse,
        )

    def test_nurse_can_access_triage(self):
        self.client.force_login(self.nurse)
        url = reverse('patients:triage', kwargs={'visit_number': self.visit.visit_number})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_admission_officer_blocked_from_triage(self):
        self.client.force_login(self.admission)
        url = reverse('patients:triage', kwargs={'visit_number': self.visit.visit_number})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_patient_list_requires_login(self):
        response = self.client.get(reverse('patients:list'))
        # Should redirect to login
        self.assertIn(response.status_code, [302, 403])


class VisitModelTest(TestCase):

    def test_visit_number_auto_generated(self):
        patient = make_patient("004")
        nurse = make_user(UserRole.NURSE, "nurse_v")
        visit = Visit.objects.create(
            patient=patient,
            visit_type='NEW',
            chief_complaint='Blurry vision',
            status='REGISTERED',
            created_by=nurse,
        )
        self.assertIsNotNone(visit.visit_number)
        self.assertTrue(len(visit.visit_number) > 0)
