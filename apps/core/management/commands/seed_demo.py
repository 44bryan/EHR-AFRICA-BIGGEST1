"""
Management command: python manage.py seed_demo
Loads realistic demo data for CEO / Medical Director presentation.
Run this ONCE after setup_ehr to populate the system.

Data created:
  - Outreach activities (past eye camps + school screenings)
  - Appointments for today and next 7 days
  - Additional billing payments (so revenue shows on leadership dashboard)
  - Inventory items (surgical supplies, equipment)
  - Staff roles for missing accounts
"""
import random
from datetime import date, timedelta, time as dtime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


class Command(BaseCommand):
    help = 'Seed demo/presentation data for CEO and Medical Director demo'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear-outreach', action='store_true',
            help='Delete existing outreach data before seeding'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n=== GLUDD Demo Data Seeder ===\n'))

        if options['clear_outreach']:
            from apps.outreach.models import OutreachActivity
            OutreachActivity.objects.all().delete()
            self.stdout.write('  Cleared existing outreach data.')

        self._seed_outreach()
        self._seed_appointments()
        self._seed_inventory()
        self._seed_extra_billing()

        self.stdout.write(self.style.SUCCESS('\nDemo data seeded successfully!\n'))

    # ── Outreach Activities ───────────────────────────────────────────────────

    def _seed_outreach(self):
        from apps.outreach.models import (
            OutreachActivity, OutreachRecord,
            OutreachType, OutreachStatus,
        )
        from apps.accounts.models import User

        self.stdout.write('Seeding outreach activities...')
        today = date.today()

        # Try to find a doctor to use as team leader
        leader = User.objects.filter(role__in=['ophthalmologist', 'retina_specialist', 'medical_director']).first()
        superadmin = User.objects.filter(role='super_admin').first()

        activities = [
            {
                'title': 'Mfoundi Arrondissement Eye Camp',
                'activity_type': OutreachType.EYE_CAMP,
                'status': OutreachStatus.COMPLETED,
                'location_name': 'Mfoundi Community Hall',
                'region': 'Centre Region',
                'town': 'Yaoundé',
                'activity_date': today - timedelta(days=62),
                'objectives': 'Free eye screening for Mfoundi community, provision of reading glasses.',
                'partner_org': 'Yaoundé Community Health Initiative',
                'sponsor': 'Lion\'s Club Yaoundé',
                'sponsor_amount': Decimal('350000'),
                'records': [
                    {
                        'record_date': today - timedelta(days=62),
                        'total_screened': 284,
                        'male_screened': 119,
                        'female_screened': 165,
                        'children_screened': 41,
                        'elderly_screened': 67,
                        'normal_vision': 108,
                        'refractive_errors': 89,
                        'cataract': 34,
                        'glaucoma_suspects': 18,
                        'diabetic_retinopathy': 12,
                        'pterygium': 11,
                        'other_pathology': 12,
                        'glasses_dispensed': 72,
                        'medications_given': 45,
                        'surgeries_performed': 0,
                        'total_treated': 117,
                        'total_referred': 64,
                        'referred_cataract': 34,
                        'referred_glaucoma': 18,
                        'referred_retina': 12,
                        'drugs_cost': Decimal('85000'),
                        'transport_cost': Decimal('45000'),
                        'other_cost': Decimal('12000'),
                    }
                ],
            },
            {
                'title': 'Lycée Bilingue de Yaoundé School Screening',
                'activity_type': OutreachType.SCHOOL_SCREENING,
                'status': OutreachStatus.COMPLETED,
                'location_name': 'Lycée Bilingue de Yaoundé',
                'region': 'Centre Region',
                'town': 'Yaoundé',
                'activity_date': today - timedelta(days=45),
                'objectives': 'Vision screening for secondary school students. Identify and refer cases of refractive error.',
                'partner_org': 'Ministry of Secondary Education',
                'records': [
                    {
                        'record_date': today - timedelta(days=45),
                        'total_screened': 412,
                        'male_screened': 196,
                        'female_screened': 216,
                        'children_screened': 412,
                        'elderly_screened': 0,
                        'normal_vision': 289,
                        'refractive_errors': 98,
                        'cataract': 0,
                        'glaucoma_suspects': 2,
                        'diabetic_retinopathy': 0,
                        'pterygium': 3,
                        'other_pathology': 20,
                        'glasses_dispensed': 0,
                        'medications_given': 3,
                        'surgeries_performed': 0,
                        'total_treated': 3,
                        'total_referred': 100,
                        'referred_cataract': 0,
                        'referred_glaucoma': 2,
                        'referred_retina': 0,
                        'referred_other': 98,
                        'drugs_cost': Decimal('15000'),
                        'transport_cost': Decimal('30000'),
                        'other_cost': Decimal('8000'),
                    }
                ],
            },
            {
                'title': 'Obala Rural Mobile Eye Clinic',
                'activity_type': OutreachType.MOBILE_CLINIC,
                'status': OutreachStatus.COMPLETED,
                'location_name': 'Obala General Hospital Compound',
                'region': 'Centre Region',
                'town': 'Obala',
                'activity_date': today - timedelta(days=28),
                'objectives': 'Two-day mobile clinic in underserved rural Obala area. Free cataract screening and surgery for eligible patients.',
                'partner_org': 'SCNLS Cameroon',
                'sponsor': 'ORBIS International',
                'sponsor_amount': Decimal('1200000'),
                'records': [
                    {
                        'record_date': today - timedelta(days=28),
                        'total_screened': 178,
                        'male_screened': 72,
                        'female_screened': 106,
                        'children_screened': 28,
                        'elderly_screened': 89,
                        'normal_vision': 34,
                        'refractive_errors': 47,
                        'cataract': 68,
                        'glaucoma_suspects': 9,
                        'diabetic_retinopathy': 5,
                        'corneal_opacity': 8,
                        'other_pathology': 7,
                        'glasses_dispensed': 39,
                        'medications_given': 62,
                        'surgeries_performed': 12,
                        'total_treated': 101,
                        'total_referred': 29,
                        'referred_cataract': 17,
                        'referred_glaucoma': 9,
                        'referred_retina': 3,
                        'drugs_cost': Decimal('145000'),
                        'transport_cost': Decimal('180000'),
                        'other_cost': Decimal('55000'),
                    },
                    {
                        'record_date': today - timedelta(days=27),
                        'total_screened': 194,
                        'male_screened': 81,
                        'female_screened': 113,
                        'children_screened': 19,
                        'elderly_screened': 97,
                        'normal_vision': 41,
                        'refractive_errors': 52,
                        'cataract': 71,
                        'glaucoma_suspects': 11,
                        'diabetic_retinopathy': 4,
                        'corneal_opacity': 6,
                        'other_pathology': 9,
                        'glasses_dispensed': 43,
                        'medications_given': 67,
                        'surgeries_performed': 18,
                        'total_treated': 110,
                        'total_referred': 22,
                        'referred_cataract': 14,
                        'referred_glaucoma': 8,
                        'referred_retina': 0,
                        'drugs_cost': Decimal('158000'),
                        'transport_cost': Decimal('0'),
                        'other_cost': Decimal('32000'),
                    }
                ],
            },
            {
                'title': 'Cameroon Telecommunications Corporate Screening',
                'activity_type': OutreachType.CORPORATE,
                'status': OutreachStatus.COMPLETED,
                'location_name': 'Camtel Head Office',
                'region': 'Centre Region',
                'town': 'Yaoundé',
                'activity_date': today - timedelta(days=14),
                'objectives': 'Annual workplace eye health screening for corporate staff.',
                'partner_org': 'Camtel HR Department',
                'records': [
                    {
                        'record_date': today - timedelta(days=14),
                        'total_screened': 143,
                        'male_screened': 87,
                        'female_screened': 56,
                        'children_screened': 0,
                        'elderly_screened': 18,
                        'normal_vision': 61,
                        'refractive_errors': 68,
                        'cataract': 4,
                        'glaucoma_suspects': 6,
                        'diabetic_retinopathy': 4,
                        'glasses_dispensed': 0,
                        'medications_given': 10,
                        'total_treated': 10,
                        'total_referred': 82,
                        'referred_cataract': 4,
                        'referred_glaucoma': 6,
                        'referred_other': 72,
                        'drugs_cost': Decimal('22000'),
                        'transport_cost': Decimal('25000'),
                        'other_cost': Decimal('15000'),
                    }
                ],
            },
            {
                'title': 'Ekoumdoum Quartier Eye Camp — Q2',
                'activity_type': OutreachType.EYE_CAMP,
                'status': OutreachStatus.PLANNED,
                'location_name': 'Ekoumdoum Presbyterian Church',
                'region': 'Centre Region',
                'town': 'Yaoundé',
                'activity_date': today + timedelta(days=18),
                'objectives': 'Community eye screening, free glasses for elderly, referral for surgical cases.',
                'partner_org': 'Presbyterian Church of Cameroon',
            },
        ]

        for act_data in activities:
            records = act_data.pop('records', [])
            activity, created = OutreachActivity.objects.get_or_create(
                title=act_data['title'],
                defaults={**act_data, 'team_leader': leader}
            )
            if created:
                recorded_by = superadmin or leader
                for rec_data in records:
                    OutreachRecord.objects.get_or_create(
                        activity=activity,
                        record_date=rec_data.pop('record_date'),
                        defaults={**rec_data, 'recorded_by': recorded_by}
                    )
                self.stdout.write(f'  Created: {activity.title}')
            else:
                self.stdout.write(f'  Exists:  {activity.title}')

        self.stdout.write(self.style.SUCCESS('  OK Outreach data seeded'))

    # ── Appointments ──────────────────────────────────────────────────────────

    def _seed_appointments(self):
        from apps.appointments.models import Appointment
        from apps.patients.models import Patient
        from apps.departments.models import Department
        from apps.accounts.models import User

        self.stdout.write('Seeding appointments...')
        today = date.today()

        patients = list(Patient.objects.filter(is_deleted=False)[:15])
        if not patients:
            self.stdout.write('  No patients found — skip appointments')
            return

        doctors = list(User.objects.filter(
            role__in=['ophthalmologist', 'retina_specialist', 'glaucoma_specialist',
                      'optometrist', 'cataract_surgeon', 'medical_director', 'ceo']
        ))
        gen_oph = Department.objects.filter(code='GEN_OPH').first()
        retina  = Department.objects.filter(code='RETINA').first()
        refrac  = Department.objects.filter(code='REFRAC').first()
        glauc   = Department.objects.filter(code='GLAUC').first()

        slots = [
            (today,          dtime(8, 30),  'Follow-up glaucoma monitoring — IOP check',          gen_oph, 'FOLLOW_UP'),
            (today,          dtime(9, 0),   'Post-op day 30 review — phaco RE',                   gen_oph, 'REVIEW'),
            (today,          dtime(9, 30),  'New patient — gradual vision loss both eyes',         gen_oph, 'NEW'),
            (today,          dtime(10, 0),  'Retina check — diabetic retinopathy monitoring',      retina,  'FOLLOW_UP'),
            (today,          dtime(10, 30), 'Refraction — spectacle prescription renewal',         refrac,  'FOLLOW_UP'),
            (today,          dtime(11, 0),  'Glaucoma review — medication adjustment',             glauc,   'FOLLOW_UP'),
            (today,          dtime(14, 0),  'New patient — red eye with discharge',                gen_oph, 'NEW'),
            (today,          dtime(14, 30), 'Post-op check — trabeculectomy week 2',               glauc,   'REVIEW'),
            (today + timedelta(days=1), dtime(9, 0),  'Annual diabetic eye check',                retina,  'FOLLOW_UP'),
            (today + timedelta(days=1), dtime(9, 30), 'Paediatric amblyopia follow-up',           gen_oph, 'FOLLOW_UP'),
            (today + timedelta(days=2), dtime(10, 0), 'VIP consult — executive comprehensive eye exam', gen_oph, 'NEW'),
            (today + timedelta(days=3), dtime(8, 30), 'Glaucoma new case — referred from Bafoussam', glauc, 'NEW'),
            (today + timedelta(days=5), dtime(9, 0),  'Cataract surgery pre-op assessment',        gen_oph, 'PROCEDURE'),
            (today + timedelta(days=7), dtime(11, 0), 'Retina follow-up — AMD treatment monitoring', retina, 'FOLLOW_UP'),
        ]

        booked_by = User.objects.filter(role='receptionist').first() or User.objects.first()
        created_count = 0

        for i, (appt_date, appt_time, reason, dept, appt_type) in enumerate(slots):
            if not dept:
                continue
            patient = patients[i % len(patients)]
            doctor  = doctors[i % len(doctors)] if doctors else None

            exists = Appointment.objects.filter(
                patient=patient, appointment_date=appt_date, appointment_time=appt_time
            ).exists()
            if not exists:
                status = 'CONFIRMED' if appt_date == today else 'SCHEDULED'
                Appointment.objects.create(
                    patient=patient,
                    department=dept,
                    doctor=doctor,
                    appointment_date=appt_date,
                    appointment_time=appt_time,
                    duration_minutes=30,
                    appointment_type=appt_type,
                    reason=reason,
                    status=status,
                    booked_by=booked_by,
                )
                created_count += 1

        self.stdout.write(f'  Created {created_count} appointments')
        self.stdout.write(self.style.SUCCESS('  OK Appointments seeded'))

    # ── Inventory Items ───────────────────────────────────────────────────────

    def _seed_inventory(self):
        from apps.inventory.models import InventoryItem, ItemCategory

        self.stdout.write('Seeding inventory items...')

        items = [
            ('INV-001', 'Slit Lamp Bulb (Haag-Streit)',   ItemCategory.DIAGNOSTIC, 'unit',  5, 12, 18500),
            ('INV-002', 'Surgical Gloves (Box 100)',       ItemCategory.SURGICAL,   'box',   10, 45, 8500),
            ('INV-003', 'Disposable Syringes 2ml (x100)', ItemCategory.SURGICAL,   'box',   20, 80, 4200),
            ('INV-004', 'BSS Irrigation Solution 500ml',  ItemCategory.SURGICAL,   'bottle', 15, 30, 12000),
            ('INV-005', 'IOL — Monofocal 22.5D',          ItemCategory.SURGICAL,   'unit',   5, 18, 145000),
            ('INV-006', 'IOL — Monofocal 23.0D',          ItemCategory.SURGICAL,   'unit',   5, 14, 145000),
            ('INV-007', 'Surgical Drapes (Sterile)',       ItemCategory.SURGICAL,   'pack',  10, 25, 22000),
            ('INV-008', 'Ophthalmoscope Battery AA',       ItemCategory.DIAGNOSTIC, 'unit',   5, 24, 500),
            ('INV-009', 'Fluorescein Eye Strips (100)',    ItemCategory.DIAGNOSTIC, 'box',    5, 12, 15000),
            ('INV-010', 'Tonometer Tips (Disposable)',     ItemCategory.DIAGNOSTIC, 'box',    5, 8,  28000),
            ('INV-011', 'N95 Masks (Box 20)',              ItemCategory.OTHER,       'box',   10, 22, 7500),
            ('INV-012', 'Hand Sanitizer 500ml',            ItemCategory.CLEANING,   'bottle', 10, 35, 3500),
            ('INV-013', 'Surgical Marker Pen',             ItemCategory.SURGICAL,   'unit',   5, 18, 2500),
            ('INV-014', 'Viscoelastic OVD 0.5ml',         ItemCategory.SURGICAL,   'unit',   5, 20, 85000),
            ('INV-015', 'Phaco Cassette (Disposable)',     ItemCategory.SURGICAL,   'unit',  10, 15, 62000),
            ('INV-016', 'A4 Paper (Ream)',                 ItemCategory.OFFICE,     'ream',  10, 8,  3000),
            ('INV-017', 'Toner Cartridge HP LaserJet',    ItemCategory.OFFICE,     'unit',   2, 3,  35000),
            ('INV-018', 'Hydrogen Peroxide 3%',            ItemCategory.CLEANING,   'litre',  5, 12, 2800),
            ('INV-019', 'Sutures — Vicryl 8-0',            ItemCategory.SURGICAL,   'pack',   5, 15, 48000),
            ('INV-020', 'Trial Lens Set (Full)',            ItemCategory.DIAGNOSTIC, 'set',    1, 2,  580000),
        ]

        created = 0
        for code, name, cat, unit, reorder, stock, cost in items:
            _, made = InventoryItem.objects.get_or_create(
                item_code=code,
                defaults={
                    'name': name,
                    'category': cat,
                    'unit': unit,
                    'reorder_level': reorder,
                    'current_stock': stock,
                    'unit_cost': Decimal(str(cost)),
                }
            )
            if made:
                created += 1

        self.stdout.write(f'  Created {created} inventory items')
        self.stdout.write(self.style.SUCCESS('  OK Inventory seeded'))

    # ── Extra Billing Payments ─────────────────────────────────────────────────

    def _seed_extra_billing(self):
        """
        Create additional paid invoices so the leadership dashboard shows
        meaningful revenue numbers.
        """
        from apps.billing.models import Invoice, InvoiceItem, Payment, InvoiceStatus, ServiceCategory, PaymentMethod
        from apps.patients.models import Patient
        from apps.accounts.models import User

        self.stdout.write('Seeding billing/revenue data...')

        patients = list(Patient.objects.filter(is_deleted=False)[:20])
        if not patients:
            self.stdout.write('  No patients — skip billing')
            return

        cashier = User.objects.filter(role__in=['cashier', 'billing_officer']).first()
        if not cashier:
            cashier = User.objects.first()

        today = date.today()

        services = [
            # (category, description, unit_price, qty)
            (ServiceCategory.CONSULTATION, 'General Ophthalmology Consultation',  15000, 1),
            (ServiceCategory.CONSULTATION, 'Specialist Consultation (Retina)',    25000, 1),
            (ServiceCategory.CONSULTATION, 'Glaucoma Specialist Consultation',    20000, 1),
            (ServiceCategory.INVESTIGATION,'OCT Scan (Macula)',                   45000, 1),
            (ServiceCategory.INVESTIGATION,'Visual Field Analysis (HVF)',         35000, 1),
            (ServiceCategory.INVESTIGATION,'Fundus Photography',                  20000, 1),
            (ServiceCategory.INVESTIGATION,'B-Scan Ultrasound',                   25000, 1),
            (ServiceCategory.INVESTIGATION,'Corneal Topography',                  30000, 1),
            (ServiceCategory.PHARMACY,     'Timolol 0.5% Eye Drops',              8500, 1),
            (ServiceCategory.PHARMACY,     'Latanoprost 0.005% Eye Drops',        22000, 1),
            (ServiceCategory.PHARMACY,     'Dexamethasone 0.1% Eye Drops',        6500, 1),
            (ServiceCategory.OPTICAL,      'Progressive Spectacle Lenses',        85000, 1),
            (ServiceCategory.OPTICAL,      'Reading Glasses +2.50',               35000, 1),
            (ServiceCategory.SURGICAL,     'Phacoemulsification + IOL (RE)',      450000, 1),
            (ServiceCategory.SURGICAL,     'Trabeculectomy (RE)',                 380000, 1),
            (ServiceCategory.REGISTRATION, 'New Patient Registration',             5000, 1),
        ]

        payment_methods = [
            PaymentMethod.CASH, PaymentMethod.MOBILE_MONEY, PaymentMethod.CARD,
            PaymentMethod.CASH, PaymentMethod.CASH, PaymentMethod.MOBILE_MONEY,
        ]

        # Create invoices spread over the last 30 days
        created = 0
        for i in range(25):
            patient = patients[i % len(patients)]
            inv_date = today - timedelta(days=random.randint(0, 30))

            # Pick 1-3 services for this invoice
            selected = random.sample(services, k=random.randint(1, 3))

            inv = Invoice.objects.create(
                patient=patient,
                issue_date=inv_date,
                status=InvoiceStatus.DRAFT,
                created_by=cashier,
                notes='Demo invoice',
            )
            total = Decimal('0')
            for cat, desc, unit_price, qty in selected:
                item = InvoiceItem.objects.create(
                    invoice=inv,
                    category=cat,
                    description=desc,
                    quantity=qty,
                    unit_price=Decimal(str(unit_price)),
                    created_by=cashier,
                )
                total += item.line_total

            # Make most invoices paid
            if i < 20:
                method = payment_methods[i % len(payment_methods)]
                Payment.objects.create(
                    invoice=inv,
                    payment_method=method,
                    amount=total,
                    reference=f'RCP-{inv_date.strftime("%Y%m%d")}-{i+1:03d}',
                    received_by=cashier,
                    payment_date=timezone.make_aware(
                        __import__('datetime').datetime.combine(inv_date, dtime(9, 0))
                    ),
                    created_by=cashier,
                )
            else:
                # Leave a few as issued (unpaid) — shows outstanding balance
                inv.status = InvoiceStatus.ISSUED
                inv.save(update_fields=['status'])

            created += 1

        self.stdout.write(f'  Created {created} demo invoices with payments')
        self.stdout.write(self.style.SUCCESS('  OK Billing/revenue data seeded'))
