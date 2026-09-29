# EHR Africa — Enterprise Hospital Management System

Africa Eye Foundation (AEF/MICEI) Electronic Health Records system built with Django 6.0, designed for Cameroon healthcare operations with OHADA SYSCEBNL accounting compliance.

## Stack

- **Backend:** Django 6.0.5, Python 3.14, PostgreSQL, Redis, Celery + Beat
- **Frontend:** Bootstrap 5, HTMX 1.9, Chart.js 4.4, Bootstrap Icons
- **Deployment:** Gunicorn + gevent, Nginx, systemd (Ubuntu 24.04 LTS)
- **Currency:** XAF (FCFA), TVA 19.25%, Africa/Douala timezone

## Key Modules

| Module | Description |
|--------|-------------|
| **Accounts** | 39 roles, RBAC, consultation units, cashier stations |
| **Patients** | Registration, visits, tiers (Standard/VIP), consent, problem list |
| **Consultations** | Ophthalmology workstation, AI macros, diagnosis (ICD-10/11) |
| **Billing** | POS, invoicing, cashier shifts/sessions, service price catalog |
| **Finance (GL)** | OHADA Chart of Accounts (1,086 accounts), double-entry journal, Trial Balance, Balance Sheet, P&L, Cash Flow |
| **Banking** | Bank accounts, reconciliation, cash deposits, cheque management |
| **AP/AR** | Vendor bills, corporate accounts, AR/AP aging, staff advances |
| **Budgets** | Annual budget wizard, YTD reporting, variance analysis |
| **Fixed Assets** | Asset register, depreciation, disposal workflow |
| **Tax** | TVA return, DSF (Cameroon annual tax), fiscal period management |
| **HMO/Insurance** | CNPS, Mutual, Corporate, NHIS schemes; claims, batches, pre-auth |
| **Pharmacy** | Prescriptions, dispensing, controlled drugs, COGS GL posting |
| **Inventory** | 13 store types, GRN, inter-store transfers, reorder alerts |
| **Laboratory** | ISO 15189 lab, investigations, antibiogram |
| **IPD** | Admissions, surgical pathway, nursing care plans, anaesthetic records |
| **Opticals** | Dispensing, frame/lens catalog, refraction, optical billing |
| **QMS** | Queue tokens, counters, kiosk, real-time display board |
| **HRMS** | Staff profiles, attendance, leave, payroll |
| **Blood Bank** | Donors, units, cross-match, FIFO issue |
| **Infection Control** | HAI reporting, outbreak alerts, antibiotic sensitivity |
| **Dietary** | Diet orders, nutritional assessment, meal plans |
| **Mortuary** | Body admission, storage, post-mortem, release |
| **Outreach** | Community screening campaigns, field data |
| **Telemedicine** | Video consultations, pre-consultation intake |
| **AI Assistant** | Clinical AI (Groq/Ollama), virtual receptionist |
| **Reports** | Revenue, disease burden, staff performance, MOH export |

## Security

- **RBAC:** 39 roles with strict sidebar isolation — each role sees only authorized pages
- **Soft-delete with audit:** All deletions require a reason; logged to `DeletionLog` with who/when/why
- **Recycle bin:** Soft-deleted records are restorable by Super Admin; permanent delete only after review
- **Financial controls:** Invoice void/cancel (never hard-delete), cashier session verification, shift reconciliation
- **HIPAA:** PHI_READ audit logging, password min 12 chars, session security
- **CSRF/XSS:** Django middleware, template auto-escaping

## Finance Role Hierarchy

```
Cashier           -> POS, own shift/session only
Chief Cashier     -> Open day, verify all shifts, cash management
Accountant        -> GL read, AR/AP, cheques, cash oversight
Senior Accountant -> Full GL, financial statements, budgets, tax, assets
Finance Director  -> Strategic oversight, all reports, no cashier operations
```

## Deployment

```bash
# Production (192.168.30.169)
cd /opt/ehr-africa
source venv/bin/activate
python manage.py migrate
sudo systemctl restart ehr-gunicorn
```

## License

Proprietary — Africa Eye Foundation / MICEI. All rights reserved.
