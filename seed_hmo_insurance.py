"""
Seed demo HMO / Insurance data for EHR Africa.

Run: python seed_hmo_insurance.py
"""
import os, sys, django, random
from datetime import date, timedelta
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from django.utils import timezone
from apps.hmo.models import (
    InsuranceScheme, SchemeType,
    InsuredMember,
    PreAuthorization, PreAuthStatus,
    ClaimBatch, ClaimBatchStatus,
    Claim, ClaimStatus, ClaimItem,
)
from apps.patients.models import Patient, Visit

print("=" * 60)
print("  EHR Africa — HMO / Insurance Seed")
print("=" * 60)

# ── 1. Insurance Schemes ──────────────────────────────────────────
SCHEMES = [
    dict(
        name="CNPS Cameroun",
        code="CNPS01",
        scheme_type=SchemeType.CNPS,
        coverage_pct=Decimal("80"),
        pre_auth_required=True,
        max_annual_claim=Decimal("500000"),
        contact_phone="+237 222 23 45 67",
        contact_email="reclamations@cnps.cm",
        address="Avenue des Grandes Puissances, Yaoundé",
        notes="National Social Insurance Fund — government employees + formal sector",
    ),
    dict(
        name="Mutuelle de Santé Bami",
        code="MUTUAL01",
        scheme_type=SchemeType.MUTUAL,
        coverage_pct=Decimal("70"),
        pre_auth_required=False,
        max_annual_claim=Decimal("300000"),
        contact_phone="+237 699 11 22 33",
        contact_email="info@mutuellebami.cm",
        address="Bafoussam, Région Ouest",
        notes="Community mutual for Bamiléké region members",
    ),
    dict(
        name="Société Générale Cameroun — Santé Employés",
        code="CORP01",
        scheme_type=SchemeType.CORPORATE,
        coverage_pct=Decimal("90"),
        pre_auth_required=False,
        max_annual_claim=Decimal("1000000"),
        contact_phone="+237 233 40 12 00",
        contact_email="rh@sgcm.cm",
        address="Avenue du Général de Gaulle, Douala",
        notes="Corporate health plan for SGC employees and dependants",
    ),
    dict(
        name="NHIS Cameroun",
        code="NHIS01",
        scheme_type=SchemeType.NHIS,
        coverage_pct=Decimal("60"),
        pre_auth_required=True,
        max_annual_claim=Decimal("200000"),
        contact_phone="+237 222 30 10 50",
        contact_email="nhis@minsante.cm",
        address="Ministère de la Santé, Yaoundé",
        notes="National Health Insurance Scheme — pilot phase",
    ),
]

schemes = {}
for s in SCHEMES:
    obj, created = InsuranceScheme.objects.update_or_create(
        code=s['code'],
        defaults=s,
    )
    schemes[s['code']] = obj
    print(f"  {'Created' if created else 'Updated'} scheme: {obj.name}")

print(f"\n  {len(schemes)} schemes ready.")

# ── 2. Enrol patients ─────────────────────────────────────────────
patients = list(Patient.objects.filter(is_deleted=False).order_by('?')[:20])
if not patients:
    print("\n  [!] No patients found — run seed_data.py first.")
    sys.exit(1)

print(f"\n  Enrolling {len(patients)} patients in schemes...")

scheme_list = list(schemes.values())
members_created = 0

def make_member_number(scheme_code, patient_id):
    return f"{scheme_code}-{str(patient_id)[:8].upper()}"

enrolled = []  # (member, patient, visit)
for i, patient in enumerate(patients):
    scheme = scheme_list[i % len(scheme_list)]
    mn = make_member_number(scheme.code, patient.pk)
    expiry = date.today() + timedelta(days=random.choice([180, 365, 730]))
    member, created = InsuredMember.objects.update_or_create(
        patient=patient,
        scheme=scheme,
        defaults=dict(
            member_number=mn,
            group_number=f"GRP-{random.randint(100,999)}",
            card_expiry=expiry,
            copay_pct=Decimal(str(100 - int(scheme.coverage_pct))),
            is_primary=True,
            is_active=True,
        )
    )
    if created:
        members_created += 1

    # grab a recent visit if available
    visit = Visit.objects.filter(patient=patient, is_deleted=False).order_by('-created_at').first()
    if visit:
        enrolled.append((member, patient, visit))

print(f"  {members_created} new memberships created ({len(enrolled)} with visits).")

# ── 3. Pre-Authorisations (for schemes that require them) ─────────
print("\n  Creating pre-authorisations...")
pre_auths_created = 0
pre_auth_map = {}  # member_id → pre_auth

pre_auth_schemes = [s for s in scheme_list if s.pre_auth_required]
for member, patient, visit in enrolled:
    if member.scheme not in pre_auth_schemes:
        continue
    service = random.choice([
        "Phacoemulsification + IOL (Cataract Surgery)",
        "Retinal Laser Photocoagulation",
        "Glaucoma Trabeculectomy",
        "Optical Coherence Tomography (OCT)",
        "Fluorescein Angiography",
        "Pterygium Excision",
    ])
    cost = Decimal(str(random.randint(50000, 350000)))
    status = random.choice([
        PreAuthStatus.APPROVED, PreAuthStatus.APPROVED,
        PreAuthStatus.APPROVED, PreAuthStatus.PENDING,
        PreAuthStatus.REJECTED,
    ])
    auth_code = f"AUTH-{random.randint(10000,99999)}" if status == PreAuthStatus.APPROVED else ""
    pa = PreAuthorization.objects.create(
        member=member,
        visit=visit,
        service_description=service,
        estimated_cost=cost,
        status=status,
        auth_code=auth_code,
        requested_at=timezone.now() - timedelta(days=random.randint(1, 90)),
        responded_at=timezone.now() - timedelta(days=random.randint(0, 30)) if status != PreAuthStatus.PENDING else None,
        valid_until=date.today() + timedelta(days=90) if status == PreAuthStatus.APPROVED else None,
        rejection_reason="Service not covered under current plan" if status == PreAuthStatus.REJECTED else "",
    )
    pre_auth_map[member.pk] = pa
    pre_auths_created += 1

print(f"  {pre_auths_created} pre-authorisations created.")

# ── 4. Claim Batches + Claims ──────────────────────────────────────
print("\n  Creating claim batches & claims...")

SERVICES = [
    ("Comprehensive Eye Examination", 15000),
    ("Refraction & Spectacle Prescription", 8000),
    ("Tonometry (IOP)", 5000),
    ("Fundus Photography", 20000),
    ("Phacoemulsification + IOL", 280000),
    ("YAG Laser Capsulotomy", 45000),
    ("Retinal Laser", 80000),
    ("Intravitreal Injection (Anti-VEGF)", 120000),
    ("OCT Scan", 35000),
    ("Visual Field Test", 12000),
    ("Fluorescein Angiography", 55000),
    ("Contact Lens Fitting", 25000),
    ("Optical Coherence Tomography", 38000),
    ("Corneal Topography", 30000),
    ("Low Vision Assessment", 18000),
]

total_claims = 0
total_batches = 0

for scheme_code, scheme in schemes.items():
    # 2-3 batches per scheme
    num_batches = random.randint(2, 3)
    scheme_members = [m for (m, p, v) in enrolled if m.scheme == scheme]
    if not scheme_members:
        continue

    for b_idx in range(num_batches):
        batch_date = date.today() - timedelta(days=random.randint(0, 300))
        batch_number = f"BATCH-{scheme_code}-2026-{b_idx+1:02d}"
        b_status = random.choice([
            ClaimBatchStatus.PAID, ClaimBatchStatus.PAID,
            ClaimBatchStatus.SUBMITTED, ClaimBatchStatus.PROCESSING,
            ClaimBatchStatus.PARTIAL,
        ])
        batch = ClaimBatch.objects.create(
            batch_number=batch_number,
            scheme=scheme,
            submission_date=batch_date,
            status=b_status,
            total_claimed=0,
            total_approved=0,
            total_paid=0,
            payment_ref=f"PMT-{random.randint(100000,999999)}" if b_status in [ClaimBatchStatus.PAID, ClaimBatchStatus.PARTIAL] else "",
            payment_date=batch_date + timedelta(days=random.randint(30, 90)) if b_status == ClaimBatchStatus.PAID else None,
        )
        total_batches += 1

        # 3–8 claims per batch
        num_claims = random.randint(3, min(8, len(scheme_members)))
        batch_members = random.sample(scheme_members, num_claims)

        for c_idx, member in enumerate(batch_members):
            visit = Visit.objects.filter(patient=member.patient, is_deleted=False).order_by('-created_at').first()
            if not visit:
                continue

            claim_status = ClaimStatus.PAID if b_status == ClaimBatchStatus.PAID else \
                           ClaimStatus.APPROVED if b_status == ClaimBatchStatus.PROCESSING else \
                           ClaimStatus.SUBMITTED if b_status == ClaimBatchStatus.SUBMITTED else \
                           ClaimStatus.PARTIAL if b_status == ClaimBatchStatus.PARTIAL else ClaimStatus.SUBMITTED

            svc_date = batch_date - timedelta(days=random.randint(1, 30))
            claim_number = f"CLM-{scheme_code}-2026-{b_idx+1:02d}-{c_idx+1:03d}"

            claim = Claim.objects.create(
                claim_number=claim_number,
                batch=batch,
                member=member,
                visit=visit,
                pre_auth=pre_auth_map.get(member.pk),
                status=claim_status,
                service_date=svc_date,
                claimed_amount=0,
                approved_amount=0,
                paid_amount=0,
                patient_copay=0,
            )

            # 1–3 line items per claim
            claim_total = Decimal("0")
            for _ in range(random.randint(1, 3)):
                svc_name, unit_price = random.choice(SERVICES)
                qty = 1
                item_total = Decimal(str(unit_price * qty))
                ClaimItem.objects.create(
                    claim=claim,
                    service_name=svc_name,
                    quantity=qty,
                    unit_price=Decimal(str(unit_price)),
                    claimed_amount=item_total,
                    approved_amount=item_total * scheme.coverage_pct / 100,
                )
                claim_total += item_total

            approved = claim_total * scheme.coverage_pct / 100
            paid = approved if claim_status in [ClaimStatus.PAID] else \
                   approved * Decimal("0.5") if claim_status == ClaimStatus.PARTIAL else Decimal("0")
            copay = claim_total - approved

            claim.claimed_amount  = claim_total
            claim.approved_amount = approved
            claim.paid_amount     = paid
            claim.patient_copay   = copay
            claim.save(update_fields=['claimed_amount','approved_amount','paid_amount','patient_copay'])
            total_claims += 1

        # Recalculate batch totals
        batch.recalculate_totals()

print(f"  {total_batches} batches, {total_claims} claims created.")

# ── Summary ───────────────────────────────────────────────────────
from apps.hmo.models import ClaimBatch as CB
from django.db.models import Sum
agg = CB.objects.aggregate(
    tc=Sum('total_claimed'),
    tp=Sum('total_paid'),
)
print("\n" + "=" * 60)
print("  SEED COMPLETE")
print("=" * 60)
print(f"  Schemes:        {InsuranceScheme.objects.count()}")
print(f"  Members:        {InsuredMember.objects.count()}")
print(f"  Pre-Auths:      {PreAuthorization.objects.count()}")
print(f"  Claim Batches:  {ClaimBatch.objects.count()}")
print(f"  Claims:         {Claim.objects.count()}")
print(f"  Total Claimed:  {agg['tc'] or 0:,.0f} FCFA")
print(f"  Total Paid:     {agg['tp'] or 0:,.0f} FCFA")
print("=" * 60)
