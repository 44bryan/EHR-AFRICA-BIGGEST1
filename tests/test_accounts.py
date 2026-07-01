"""
Tests: User model, roles, and permission methods.
Run: python manage.py test tests.test_accounts
"""
from django.test import TestCase
from apps.accounts.models import User, UserRole


def make_user(role, **kwargs):
    """Helper — create a user with the given role."""
    count = User.objects.count()
    return User.objects.create_user(
        username=f"test_{role}_{count}",
        email=f"test_{role}_{count}@ehr.test",
        employee_id=f"EMP{count:05d}",
        password="TestPass123!",
        role=role,
        **kwargs,
    )


class UserRolePropertiesTest(TestCase):

    def test_super_admin_is_flagged(self):
        u = make_user(UserRole.SUPER_ADMIN)
        self.assertTrue(u.is_super_admin)

    def test_doctor_roles_are_doctors(self):
        for role in [
            UserRole.OPHTHALMOLOGIST,
            UserRole.RETINA_SPECIALIST,
            UserRole.GLAUCOMA_SPECIALIST,
        ]:
            u = make_user(role)
            self.assertTrue(u.is_doctor, f"{role} should be a doctor")

    def test_nurse_roles_are_nurses(self):
        for role in [UserRole.NURSE, UserRole.WARD_NURSE, UserRole.THEATRE_NURSE]:
            u = make_user(role)
            self.assertTrue(u.is_nurse, f"{role} should be a nurse")

    def test_opd_nurse_can_do_triage(self):
        u = make_user(UserRole.NURSE)
        self.assertTrue(u.can_do_triage())

    def test_counseling_nurse_cannot_do_triage(self):
        u = make_user(UserRole.COUNSELING_NURSE)
        self.assertFalse(u.can_do_triage())

    def test_admission_officer_cannot_do_triage(self):
        u = make_user(UserRole.ADMISSION_OFFICER)
        self.assertFalse(u.can_do_triage())

    def test_doctor_can_create_consultation(self):
        u = make_user(UserRole.OPHTHALMOLOGIST)
        self.assertTrue(u.can_create_consultation())

    def test_nurse_cannot_create_consultation(self):
        u = make_user(UserRole.NURSE)
        self.assertFalse(u.can_create_consultation())

    def test_doctor_can_order_investigations(self):
        u = make_user(UserRole.RETINA_SPECIALIST)
        self.assertTrue(u.can_order_investigations())

    def test_cashier_role_properties(self):
        u = make_user(UserRole.CASHIER)
        self.assertFalse(u.is_doctor)
        self.assertFalse(u.is_nurse)
        self.assertFalse(u.can_do_triage())

    def test_role_department_code_for_retina(self):
        u = make_user(UserRole.RETINA_SPECIALIST)
        self.assertEqual(u.role_department_code, 'RETINA')

    def test_role_department_code_for_ophthalmologist(self):
        u = make_user(UserRole.OPHTHALMOLOGIST)
        self.assertEqual(u.role_department_code, 'GEN_OPH')

    def test_finance_director_properties(self):
        u = make_user(UserRole.FINANCE_DIRECTOR)
        self.assertTrue(u.is_finance_director)
        self.assertFalse(u.is_doctor)

    def test_chief_cashier_properties(self):
        u = make_user(UserRole.CHIEF_CASHIER)
        self.assertTrue(u.is_chief_cashier)

    def test_lab_tech_properties(self):
        u = make_user(UserRole.LAB_TECHNICIAN)
        self.assertTrue(u.is_lab_tech)
        self.assertFalse(u.can_create_consultation())
