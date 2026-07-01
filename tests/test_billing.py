"""
Tests: Billing models and invoice workflow.
Run: python manage.py test tests.test_billing
"""
from decimal import Decimal
from django.test import TestCase
from apps.accounts.models import User, UserRole
from apps.patients.models import Patient
from apps.billing.models import (
    Invoice, InvoiceItem, Payment, InvoiceStatus,
    PaymentMethod, ServicePrice, ServiceCategory,
)


def make_cashier(username='cashier_01'):
    count = User.objects.count()
    return User.objects.create_user(
        username=username, email=f'{username}@ehr.test',
        employee_id=f'EMP{count:05d}', password='TestPass123!', role=UserRole.CASHIER
    )


def make_accountant(username='acct_01'):
    count = User.objects.count()
    return User.objects.create_user(
        username=username, email=f'{username}@ehr.test',
        employee_id=f'EMP{count:05d}', password='TestPass123!', role=UserRole.ACCOUNTANT
    )


def make_patient(suffix='B01'):
    return Patient.objects.create(
        first_name='Billing',
        last_name=f'Test{suffix}',
        date_of_birth='1985-06-15',
        gender='F',
    )


def make_service(name='Consultation', price=5000):
    return ServicePrice.objects.create(
        name=name,
        code='CONS-STD',
        category=ServiceCategory.CONSULTATION,
        price=Decimal(price),
    )


class InvoiceModelTest(TestCase):

    def setUp(self):
        self.cashier = make_cashier()
        self.patient = make_patient()
        self.service = make_service()

    def test_invoice_number_auto_generated(self):
        inv = Invoice.objects.create(patient=self.patient, created_by=self.cashier)
        self.assertIsNotNone(inv.invoice_number)
        self.assertTrue(inv.invoice_number.startswith('INV-'))

    def test_invoice_number_unique(self):
        inv1 = Invoice.objects.create(patient=self.patient, created_by=self.cashier)
        inv2 = Invoice.objects.create(patient=self.patient, created_by=self.cashier)
        self.assertNotEqual(inv1.invoice_number, inv2.invoice_number)

    def test_invoice_default_status_is_draft(self):
        inv = Invoice.objects.create(patient=self.patient, created_by=self.cashier)
        self.assertEqual(inv.status, InvoiceStatus.DRAFT)

    def test_subtotal_with_items(self):
        inv = Invoice.objects.create(patient=self.patient, created_by=self.cashier)
        InvoiceItem.objects.create(
            invoice=inv,
            description='Consultation',
            category=ServiceCategory.CONSULTATION,
            unit_price=Decimal('5000'),
            quantity=1,
        )
        InvoiceItem.objects.create(
            invoice=inv,
            description='Eye Drops',
            category=ServiceCategory.PHARMACY,
            unit_price=Decimal('2500'),
            quantity=2,
        )
        self.assertEqual(inv.subtotal, Decimal('10000'))

    def test_total_after_discount(self):
        inv = Invoice.objects.create(
            patient=self.patient,
            discount_amount=Decimal('1000'),
            created_by=self.cashier,
        )
        InvoiceItem.objects.create(
            invoice=inv,
            description='Consultation',
            category=ServiceCategory.CONSULTATION,
            unit_price=Decimal('5000'),
            quantity=1,
        )
        self.assertEqual(inv.total, Decimal('4000'))

    def test_balance_due_after_full_payment(self):
        inv = Invoice.objects.create(
            patient=self.patient,
            status=InvoiceStatus.ISSUED,
            created_by=self.cashier,
        )
        InvoiceItem.objects.create(
            invoice=inv,
            description='Consultation',
            category=ServiceCategory.CONSULTATION,
            unit_price=Decimal('5000'),
            quantity=1,
        )
        Payment.objects.create(
            invoice=inv,
            amount=Decimal('5000'),
            payment_method=PaymentMethod.CASH,
            received_by=self.cashier,
        )
        self.assertEqual(inv.balance_due, Decimal('0'))

    def test_update_status_marks_paid(self):
        inv = Invoice.objects.create(
            patient=self.patient,
            status=InvoiceStatus.ISSUED,
            created_by=self.cashier,
        )
        InvoiceItem.objects.create(
            invoice=inv,
            description='Consultation',
            category=ServiceCategory.CONSULTATION,
            unit_price=Decimal('3000'),
            quantity=1,
        )
        Payment.objects.create(
            invoice=inv,
            amount=Decimal('3000'),
            payment_method=PaymentMethod.CASH,
            received_by=self.cashier,
        )
        inv.update_status()
        inv.refresh_from_db()
        self.assertEqual(inv.status, InvoiceStatus.PAID)

    def test_update_status_marks_partially_paid(self):
        inv = Invoice.objects.create(
            patient=self.patient,
            status=InvoiceStatus.ISSUED,
            created_by=self.cashier,
        )
        InvoiceItem.objects.create(
            invoice=inv,
            description='Consultation',
            category=ServiceCategory.CONSULTATION,
            unit_price=Decimal('5000'),
            quantity=1,
        )
        Payment.objects.create(
            invoice=inv,
            amount=Decimal('2000'),
            payment_method=PaymentMethod.CASH,
            received_by=self.cashier,
        )
        inv.update_status()
        inv.refresh_from_db()
        self.assertEqual(inv.status, InvoiceStatus.PARTIALLY_PAID)

    def test_cancelled_invoice_status_not_changed_by_update(self):
        inv = Invoice.objects.create(
            patient=self.patient,
            status=InvoiceStatus.CANCELLED,
            created_by=self.cashier,
        )
        inv.update_status()
        inv.refresh_from_db()
        self.assertEqual(inv.status, InvoiceStatus.CANCELLED)


class ServicePriceTest(TestCase):

    def test_nhis_price_returned_for_nhis_method(self):
        svc = ServicePrice.objects.create(
            name='Consult NHIS',
            category=ServiceCategory.CONSULTATION,
            price=Decimal('5000'),
            nhis_price=Decimal('3500'),
        )
        self.assertEqual(svc.get_price_for_method(PaymentMethod.NHIS), Decimal('3500'))

    def test_standard_price_returned_for_cash(self):
        svc = ServicePrice.objects.create(
            name='Consult Cash',
            category=ServiceCategory.CONSULTATION,
            price=Decimal('5000'),
            nhis_price=Decimal('3500'),
        )
        self.assertEqual(svc.get_price_for_method(PaymentMethod.CASH), Decimal('5000'))

    def test_standard_price_when_nhis_price_not_set(self):
        svc = ServicePrice.objects.create(
            name='Consult No NHIS',
            category=ServiceCategory.CONSULTATION,
            price=Decimal('5000'),
        )
        self.assertEqual(svc.get_price_for_method(PaymentMethod.NHIS), Decimal('5000'))
