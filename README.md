<div align="center">

# EHR Africa
### Enterprise Hospital Management System

**Built for Africa. Compliant with OHADA. Ready for JCI.**

[![Django](https://img.shields.io/badge/Django-6.0-092E20?style=for-the-badge&logo=django&logoColor=white)](https://djangoproject.com)
[![Python](https://img.shields.io/badge/Python-3.14-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?style=for-the-badge&logo=bootstrap&logoColor=white)](https://getbootstrap.com)

*A full-stack, production-grade Electronic Health Records & Hospital ERP system — built from the ground up for Cameroonian healthcare operations at Africa Eye Foundation (AEF/MICEI).*

</div>

---

## What Is This?

EHR Africa is a **complete hospital operating system** — not a template, not a starter kit. Every feature was designed, built, and deployed to serve real patients at a live ophthalmology hospital in Cameroon.

It covers the full patient journey from the moment someone walks through the door to the moment they leave — and everything that happens in the accounts department afterward.

---

## The Clinical Journey

```
Patient Arrives
      │
      ▼
┌─────────────┐    ┌──────────────┐    ┌───────────────┐
│  Reception  │───▶│    Triage    │───▶│  Consultation │
│  QMS Token  │    │  Vitals/IOP  │    │  ICD-10/11 Dx │
└─────────────┘    └──────────────┘    └───────────────┘
                                               │
              ┌────────────────────────────────┤
              │                                │
              ▼                                ▼
    ┌──────────────────┐           ┌───────────────────┐
    │   Investigations  │           │    Prescriptions   │
    │  Lab · Imaging   │           │  Pharmacy Dispense │
    └──────────────────┘           └───────────────────┘
              │
              ▼
    ┌──────────────────┐
    │  Surgical Pathway │
    │  Pre-Op · Theatre │
    │  WHO Checklist   │
    │  Operative Report│
    │  Recovery Room   │
    │  Discharge       │
    └──────────────────┘
              │
              ▼
    ┌──────────────────┐    ┌───────────────────────────┐
    │   Cashier POS    │───▶│  GL Auto-Post · OHADA CoA │
    │  Invoice · Shift │    │  P&L · Balance Sheet · TVA│
    └──────────────────┘    └───────────────────────────┘
```

---

## 26 Clinical & Administrative Modules

| Domain | Module | Highlights |
|--------|--------|-----------|
| **Clinical** | Consultations | Ophthalmology workstation, AI macros, drug interaction check |
| | Investigations | Lab orders, results, ISO 15189 antibiogram |
| | Prescriptions | Drug + optical Rx, drug interactions (JCI MMU.7) |
| | IPD & Surgery | Full surgical pathway — Pre-Op → WHO Checklist → Operative Report → Recovery → Discharge |
| | Nursing | Care plans (JCI COP.8), anaesthetic records (JCI ASC.5/6) |
| | Blood Bank | Donor management, 56-day rule, FIFO unit selection, cross-match |
| | Infection Control | CDC/WHO HAI types, antibiogram, outbreak alerts |
| | Dietary | Diet orders, BMI/MUST nutritional assessment, meal plans |
| | Mortuary | Body admission, compartment storage, post-mortem, release |
| **Patient Management** | Patients | Registration, visits, VIP/Standard tiers, consent (JCI PFR.5), problem list |
| | QMS | Queue tokens, counters, kiosk, real-time display board |
| | Outreach | Community screening campaigns, field data collection |
| | Telemedicine | Video consultations, pre-consultation intake |
| **Financial ERP** | Billing & POS | Cashier stations, shift reconciliation, multi-method payments |
| | General Ledger | OHADA SYSCOHADA — 1,086 accounts, double-entry, auto-posting |
| | Financial Statements | P&L, Balance Sheet, Trial Balance, Cash Flow, SYSCOHADA Bilan |
| | Banking | Accounts, reconciliation, cash-to-bank, cheque register |
| | AR / AP | Corporate accounts, vendor bills, AR/AP aging, staff advances |
| | Budgets | Annual wizard, YTD vs actual, variance analysis |
| | Fixed Assets | Asset register, straight-line depreciation, disposal |
| | Tax & Compliance | TVA return, WHT (IRPP/IRCM), DSF, fiscal periods |
| | HMO / Insurance | CNPS, Mutual, Corporate, NHIS — pre-auth, claims, batch submission |
| **Operations** | Pharmacy | Dispensing, controlled drugs, COGS GL posting |
| | Inventory | 13 store types, GRN, inter-store transfers, reorder alerts |
| | Opticals | Frame/lens catalog, refraction, optical billing |
| | HRMS & Payroll | Staff profiles, attendance, leave management, payroll |
| **Intelligence** | AI Assistant | Clinical AI (Groq/Ollama) — differential diagnosis, discharge summaries |

---

## Engineering Highlights

### Role-Based Access Control — 39 Roles
Every role has a completely isolated sidebar and view-level guards. A cashier cannot see a single GL account. A lab technician cannot access billing. Finance Director gets executive dashboards. No role has more access than it needs.

```
CASHIER → POS only, own shift
CHIEF_CASHIER → open day, verify all shifts
ACCOUNTANT → GL read, AR/AP, cancellations
SENIOR_ACCOUNTANT → full GL, statements, budgets
FINANCE_DIRECTOR → strategic oversight + waivers
MEDICAL_DIRECTOR → clinical + management reports
CEO → full read access everywhere
SUPER_ADMIN → system configuration
```

### Double-Entry Accounting — Auto-Posted
Every invoice payment, expense, payroll run, and stock movement automatically creates a balanced journal entry against the OHADA Chart of Accounts. No manual posting required.

### JCI-Standard Surgical Pathway
Built to Joint Commission International ASC/ACC standards:
- Pre-Op counselling checklist (G001–G007)
- 8-point pre-operative investigation clearance
- WHO Surgical Safety Checklist (Sign-In / Time-Out / Sign-Out)
- IOL lot traceability (implant tracking)
- Intraoperative findings and complications
- Recovery room Aldrete score
- 20-point discharge checklist

### Performance-Optimised Queries
- Invoice listing uses `Prefetch` with `to_attr` to eliminate N+1 on `subtotal`, `amount_paid`, `balance_due`
- Dashboard KPI counts use `Count(Case(When(...)))` aggregates — single query for all status buckets
- Balance sheet uses bulk `JournalLine` aggregate instead of per-account queries
- 5-minute cache on investigation stats, 24-hour cache on historical months

---

## Tech Stack

```
Backend     Django 6.0.8 · Python 3.14 · PostgreSQL 16
Async       Redis · Celery · Celery Beat
Server      Gunicorn + gevent · Nginx · Ubuntu 24.04 LTS
Frontend    Bootstrap 5.3 · HTMX 1.9 · Chart.js 4.4 · Bootstrap Icons
AI          Groq API (cloud) · Ollama (local LLM, production)
Security    django-axes · HIPAA PHI logging · 12-char password policy
PDF         WeasyPrint (reports, receipts, shift PDFs)
Currency    XAF/FCFA · TVA 19.25% · Africa/Douala timezone
Compliance  OHADA SYSCOHADA · JCI ASC/ACC/COP/MMU · ICD-10/11
```

---

## Security Architecture

- **Soft-delete everywhere** — nothing is hard-deleted; every record has `is_deleted`, `deleted_at`, `deleted_by`, `deletion_reason`
- **Financial integrity** — invoices are voided, never deleted; payments are refunded, never removed
- **PHI audit logging** — every patient record access is logged with user, timestamp, and action
- **Session security** — IP-locked sessions, auto-logout, django-axes brute-force protection
- **CSRF/XSS** — Django middleware + template auto-escaping throughout

---

## Live Demo Patient

A fully-seeded demo patient is included for demonstration:

```bash
python manage.py seed_demo_patient
```

This creates **Emmanuel Nguema Mbarga** (58-year-old diabetic) with a complete clinical record:
- 5 specialist visits (Optometry, General Ophthalmology, Glaucoma, Retina, Surgical)
- Full phacoemulsification surgical pathway (Pre-Op → Theatre → Recovery → Discharge)
- Drug prescriptions, optical Rx, investigation orders
- WHO checklist, IOL traceability, operative report

---

## Deployment

Production server runs on Ubuntu 24.04 LTS with Nginx + Gunicorn:

```bash
# Clone and set up
git clone https://github.com/44bryan/EHR-AFRICA-BIGGEST1.git
cd EHR-AFRICA-BIGGEST1
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic
sudo systemctl start ehr-gunicorn

# Seed OHADA Chart of Accounts (1,086 accounts)
python manage.py seed_ohada_coa

# Seed demo patient
python manage.py seed_demo_patient
```

---

<div align="center">

**Built with precision for Africa's healthcare sector**

*Django · PostgreSQL · OHADA · JCI*

</div>
