# EHR Africa — Ophthalmology Electronic Health Record System
## Complete System Guide

**Version:** Phase 2 (Full Build)
**Stack:** Django 6.x · Bootstrap 5 · SQLite (dev) / PostgreSQL (prod)
**Running at:** http://127.0.0.1:8000 (development)
**Default Login:** admin@eyecare.com / Admin@1234 (Medical Director)

---

## Table of Contents

1. [What This System Is](#1-what-this-system-is)
2. [How to Start the System](#2-how-to-start-the-system)
3. [User Roles & Permissions](#3-user-roles--permissions)
4. [Patient Journey (End-to-End Flow)](#4-patient-journey-end-to-end-flow)
5. [Queue Management System (QMS)](#5-queue-management-system-qms)
6. [Clinical Modules](#6-clinical-modules)
7. [Department-Specific Examination Forms](#7-department-specific-examination-forms)
8. [AI Features](#8-ai-features)
9. [Prescriptions & Optical](#9-prescriptions--optical)
10. [Investigations & Laboratory](#10-investigations--laboratory)
11. [Pharmacy](#11-pharmacy)
12. [Billing & Invoicing](#12-billing--invoicing)
13. [Inpatient (IPD) & Theatre](#13-inpatient-ipd--theatre)
14. [Appointments & Scheduling](#14-appointments--scheduling)
15. [OPD / Triage](#15-opd--triage)
16. [HRMS (Staff Management)](#16-hrms-staff-management)
17. [Other Support Modules](#17-other-support-modules)
18. [Reporting & PDF Generation](#18-reporting--pdf-generation)
19. [System Administration](#19-system-administration)
20. [URL Quick Reference](#20-url-quick-reference)

---

## 1. What This System Is

**EHR Africa** is an open-source Electronic Health Record (EHR) system built specifically for a specialist ophthalmology hospital in Nigeria. It replaces paper-based records with a fully digital platform that:

- Registers and tracks patients from gate entry to discharge
- Records detailed ophthalmic examinations (Visual Acuity, Slit Lamp, IOP, Fundoscopy with drawing canvas, etc.)
- Issues drug and optical prescriptions linked to consultations
- Orders eye investigations and laboratory tests
- Manages a multi-tier patient queue with real-time display board
- Generates professional PDF reports for consultations, prescriptions, and visit summaries
- Provides AI-assisted diagnosis suggestions and clinical analytics powered by Claude AI
- Manages pharmacy dispensing with FEFO (First Expiry First Out) stock control
- Tracks inpatient admissions, theatre cases, and post-operative care
- Manages staff, leave, and payroll via HRMS

---

## 2. How to Start the System

```bash
# Navigate to project
cd C:/Users/bry30/Desktop/EHR-AFRICA-BIGGEST

# First time only — creates departments, seeds data, creates admin user
python manage.py setup_ehr

# Run migrations (after any model changes)
python manage.py migrate

# Start development server
python manage.py runserver
```

Open browser: **http://127.0.0.1:8000**

You will be redirected to the login page. Use:
- **Email:** admin@eyecare.com
- **Password:** Admin@1234
- **Role:** Medical Director (sees everything)

---

## 3. User Roles & Permissions

The system has **24 distinct user roles**, each with specific access:

| Role | Code | What They Can Do |
|------|------|-----------------|
| Super Administrator | `super_admin` | Full system access, staff management |
| Medical Director | `medical_director` | All clinical + admin access, override rights |
| Ophthalmologist (General) | `ophthalmologist` | Create/edit consultations, prescribe, order investigations |
| Retina Specialist | `retina_specialist` | Same as ophthalmologist, retina dept focus |
| Glaucoma Specialist | `glaucoma_specialist` | Same as ophthalmologist, glaucoma dept focus |
| Pediatric Ophthalmologist | `pediatric_ophthalmologist` | Pediatric-specific clinical access |
| Cataract Surgeon | `cataract_surgeon` | Clinical + theatre/surgical access |
| Cornea Specialist | `cornea_specialist` | Cornea clinic access |
| Oculoplastics Surgeon | `oculoplastics_surgeon` | Oculoplastics + surgical access |
| Neuro-ophthalmologist | `neuro_ophthalmologist` | Neuro-ophthalmology clinic access |
| Optometrist / Refractionist | `optometrist` | Refraction, optical prescriptions |
| Intern / House Officer | `intern` | Limited consultation access (supervised) |
| OPD Nurse | `nurse` | Record vitals/triage, QMS routing |
| Theatre Nurse | `theatre_nurse` | Theatre checklist, instrument tracking |
| Ward Nurse (IPD) | `ward_nurse` | Nursing notes, ward management |
| Investigation Technician | `investigation_technician` | Eye investigation results entry |
| Lab Technician | `lab_technician` | Lab test results entry |
| Pharmacist | `pharmacist` | Drug dispensing, stock management |
| Optical Dispenser | `optical_dispenser` | Optical orders, frame/lens catalogue |
| Receptionist | `receptionist` | Patient registration, queue ticket issuance |
| Admission Officer | `admission_officer` | IPD admissions, bed management |
| Billing Officer | `billing_officer` | Invoice creation, payment recording |
| Medical Records Officer | `medical_records` | View all records, PDF generation |
| System Administrator | `admin` | Settings, user management |

---

## 4. Patient Journey (End-to-End Flow)

Every patient follows a structured 9-step clinical pathway, tracked in real time:

```
[1] GATE ENTRY
    Patient arrives → Gate staff issues entry ticket (QMS)
    Ticket type: S-001 (Standard), E-001 (Express), FT-001 (Fast Track), V-001 (VIP)
          ↓
[2] CASHIER / REGISTRATION
    Patient registers or pays → Cashier records details
    New patient: full demographic capture (name, DOB, address, blood group, genotype)
    Returning patient: visit linked to existing record
          ↓
[3] PARAMETERS / TRIAGE
    Nurse records vital signs:
    → Visual Acuity (RE/LE, unaided + pinhole)
    → Intraocular Pressure (IOP mmHg)
    → Blood Pressure, Pulse, Weight, Height, Temperature
    Nurse routes patient to appropriate clinic
          ↓
[4] COMPLEMENTARY EXAMINATIONS (if ordered)
    Eye investigations (OCT, VF, Biometry, Fundus Photography, etc.)
    Laboratory tests (FBS, HbA1c, CBC, etc.)
          ↓
[5] SPECIALIST CONSULTATION
    Doctor opens consultation form:
    → Records history (chief complaint, HPC, ocular/systemic history)
    → Enters full specialist examination (dept-specific form)
    → AI suggests differential diagnoses
    → Records diagnosis and management plan
    → Issues prescriptions, orders investigations
          ↓
[6] THERAPEUTIC MANAGEMENT
    Drug prescriptions printed
    Optical prescriptions issued
    Referrals to other departments
          ↓
[7] PHARMACY / OPTICAL SERVICE
    Pharmacist dispenses drugs (FEFO stock control)
    Optical dispenser fills spectacle / contact lens order
          ↓
[8] BILLING & PAYMENT
    Billing officer creates invoice
    Patient pays → receipt generated
    Invoice covers: consultation fee, drugs, investigations, procedures
          ↓
[9] DISCHARGE & FOLLOW-UP
    Discharge notes recorded
    Follow-up appointment booked
    Visit summary PDF generated and printed
```

**URL to view a patient's journey:** `/patients/visit/<visit_number>/`

---

## 5. Queue Management System (QMS)

The QMS manages the physical patient queue across all hospital departments with multi-tier priority.

### Service Tiers (Patient Classes)

| Tier | Token Prefix | Priority | Visual |
|------|-------------|----------|--------|
| Standard | S-001 | 0 (normal) | Grey |
| Express | E-001 | 10 | Blue |
| Fast Track | FT-001 | 20 | Yellow |
| VIP | V-001 | 30 (first served) | Red |

Higher-priority patients are called first within any service queue.

### Entry Points

- **Gate (`/qms/gate/`)** — Gate staff issues entry tickets for all tiers. Each ticket links to a patient record. Walk-ins can be issued without a patient ID.
- **Cashier (`/qms/cashier/`)** — Cashier issues tickets for VIP/Express/FastTrack patients entering through the back. Prevents duplicate tickets — alerts if patient already has a ticket today.

### Department Routing

When a doctor or nurse routes a patient to the next service:
1. A **department token** is auto-created (e.g., `RX-001` for pharmacy)
2. The token inherits the patient's tier for priority in the destination queue
3. The Visit status is updated to match the destination
4. Staff at the destination counter see the token appear in their queue

**Route endpoint:** `POST /qms/route/`
Available from:
- The **Visit Journey page** (`/patients/visit/<number>/`) — Route panel at the top
- The **Consultation detail page** — "Route" dropdown button in the header

### Service Departments (17 service stations)

| Code | Department | Token Prefix |
|------|-----------|-------------|
| CASHIER | Cashier / Registration | CASH |
| PARAMETERS | Parameters & Triage | PARAM |
| GENERAL | General Ophthalmology | GEN |
| RETINA | Retina Clinic | RET |
| GLAUCOMA | Glaucoma Clinic | GLAUC |
| CATARACT | Cataract / Surgical | CAT |
| PEDIATRIC | Pediatric Ophthalmology | PEDS |
| NEURO | Neuro-ophthalmology | NEURO |
| OCULOPLASTY | Oculoplastics | OCUP |
| CORNEA | Cornea Clinic | CORN |
| REFRACTION | Refraction / Optometry | REF |
| INVEST | Eye Investigations | INV |
| LAB | Laboratory | LAB |
| PHARMACY | Pharmacy | RX |
| OPTICAL | Optical Shop | OPT |
| COUNSEL | Surgical Counseling | COUNS |
| BILLING | Billing / Accounts | BILL |

### Counter Staff View (`/qms/counter/<id>/`)

Each service counter has its own view showing:
- The waiting list ordered by tier priority + arrival time
- "Call Next" button — marks current token as SERVED and calls the next
- Complete / Skip / No-show controls

### TV Display Board (`/qms/display/`) — No Login Required

Large-screen display for waiting areas showing:
- Currently being served (token number + counter + tier badge)
- Recently called tokens
- Auto-refreshes every 15 seconds

### Daily Census (`/qms/census/`)

Shows total entry tickets issued today broken down by tier and issuance point (Gate vs. Cashier).

---

## 6. Clinical Modules

### Patient Registration (`/patients/`)

- **Register new patient:** Full demographic capture — name, DOB, gender, marital status, occupation, address, blood group, genotype, HMO/insurance details, next of kin
- **Patient ID:** Auto-generated (e.g., `EYE-240001`)
- **Medical history:** Stored per patient — chronic conditions, allergies, current medications, previous surgeries, family history
- **Patient card:** Compact card component used across all clinical screens showing photo placeholder, key demographics, and alert badges (allergies, HMO)

### Consultations (`/consultations/`)

The central clinical record. Each consultation is linked to:
- A patient
- A visit
- A department
- The consulting doctor

**Consultation fields:**
- Presenting complaint & history
- Ocular history, systemic history, drug history, family history
- Examination findings (structured JSON)
- Management plan
- Follow-up date and instructions
- Referral department
- Status: `IN_PROGRESS` → `COMPLETED`

**Tabs on the consultation detail page:**
1. **History** — Complaints and history fields
2. **Examination** — Generic VA / IOP summary table
3. **Diagnosis & Plan** — ICD-10 linked diagnoses, management plan, follow-up
4. **Prescriptions** — Drug and optical prescriptions with print links
5. **Investigations** — Eye investigations and lab orders
6. **Notes** — Clinical notes (nursing, doctor, etc.)
7. **[Dept] Exam** — Full specialist examination form (department-specific)
8. **Voice EMR** — Dictate to auto-fill clinical fields via AI

---

## 7. Department-Specific Examination Forms

Each of the 9 clinical departments has a bespoke examination template. The form is shown in the "Dept Exam" tab of every consultation and auto-saves to `department_specific_data` (JSON field on the Consultation model).

### General Ophthalmology (`_gen_oph_form.html`) — 8 Sections

**1. Visual Acuity**
- RE and LE: Unaided (sc), Pinhole (PH), Best Corrected (BCVA), Near Vision
- VA Method: Snellen 6m, LogMAR, ETDRS, Kay Pictures, Cardiff Cards
- VA Remarks

**2. Refraction / Spectacle Prescription**
- RE and LE: Sphere (DS), Cylinder (DC), Axis (°), Add (DS), VA with Rx
- Refraction Type: Dry, Cycloplegic, Post-Cycloplegic, Manifest, Auto-Refraction
- Lens Type: Single Vision, Bifocal, Progressive, Contact Lens

**3. Cover Test & Ocular Motility**
- Cover Test: Orthophoria, Esophoria, Exophoria, Esotropia, Exotropia, etc.
- Ocular Motility: Full OU, Limited RE/LE, Restricted
- RAPD: Absent / Present RE / Present LE (highlighted red if present)
- Colour Vision: Normal OU / Defective RE/LE / Not tested

**4. External Eye / Adnexa**
- RE and LE free-text: Lids, Lashes & Lacrimal
- Placeholders: Ptosis, Ectropion, Entropion, Discharge

**5. Slit Lamp — Anterior Segment**
- Table with RE and LE for each structure:
  - Conjunctiva, Cornea, Anterior Chamber, Iris, Pupil, Lens/Media
- Contextual placeholders (e.g., "Deep & Quiet / Cells / Flare" for AC)

**6. Intraocular Pressure (IOP)**
- RE and LE in mmHg
- Method: NCT, Goldmann (GAT), Perkins, iCare, Schiotz, Digital
- Time of measurement
- IOP Remarks (e.g., "on Timolol BD")

**7. Posterior Segment / Fundoscopy**
- **Interactive drawing canvas** (280×280px per eye) with:
  - Anatomically accurate fundus background (disc, macula, vessels pre-drawn)
  - Pen / Eraser tools
  - Color picker and brush size slider
  - Touch support (tablet/stylus compatible)
  - Drawing saved as base64 PNG in hidden field, persists on reload
- Text fields: Optic Disc, Macula, Vessels & Periphery, Vitreous (RE & LE each)
- Method: Direct / BIO / Slit Lamp 90D / 78D / Not done
- Dilation status + dilating agent

**8. Diagnosis**
- RE Diagnosis, LE Diagnosis, Overall Summary
- **AI Differential Diagnosis button** — sends exam findings to Claude AI
  - Returns: ranked differentials with ICD-10 codes, confidence, supporting/against evidence
  - Red flag alerts, referral urgency
  - "Apply to Summary" button injects diagnosis into the summary field

### Other Specialist Forms

| Department | Key Unique Fields |
|-----------|-----------------|
| **Retina** | OCT findings, fluorescein angiography, laser treatment history, injection history |
| **Glaucoma** | Visual field results, nerve fibre layer, CCT, gonioscopy, target IOP, treatment ladder |
| **Refraction** | Full prescription history, K-readings, contact lens parameters, patient advice |
| **Pediatric** | Birth history, developmental milestones, amblyopia treatment, orthoptic assessment |
| **Cornea** | Topography, specular microscopy, corneal thickness, transplant status |
| **Oculoplastics** | Lid measurements, Hertel exophthalmometry, lacrimal assessment, surgical plan |
| **Neuro-oph** | Pupil assessment, visual fields, OCT nerve fibre, colour vision, neuroimaging |
| **Cataract** | Biometry (IOL power), surgical technique, IOL type, post-op refraction |

The read-only view (`_gen_oph.html` etc.) is shown when the exam tab is in view mode, displaying findings in clean formatted tables. Click **Edit** to open the inline form without leaving the page.

---

## 8. AI Features

All AI features use **Anthropic Claude** via the `ai_assistant` app.

### 1. AI Diagnosis Suggestion (in every consultation)

**Where:** Consultation dept exam tab → "AI Suggest Differentials" button

**How it works:**
1. Doctor fills in exam findings (VA, slit lamp, IOP, fundoscopy, history)
2. Clicks the AI button
3. System sends all `dept_` prefixed fields + chief complaint to Claude
4. Claude returns structured JSON:
   ```json
   {
     "differentials": [
       {"rank": 1, "diagnosis": "Primary Open Angle Glaucoma",
        "icd10": "H40.1", "confidence": "high",
        "supporting": ["IOP 26mmHg RE", "C:D ratio 0.7"],
        "against": ["No visual field defect documented"]}
     ],
     "red_flags": ["Elevated IOP requires urgent follow-up"],
     "referral_urgency": "routine",
     "investigations": ["Humphrey Visual Fields", "OCT Nerve Fibre Layer"],
     "management": ["Start topical antihypertensive", "Review in 6 weeks"]
   }
   ```
5. Each differential has an "Apply to Summary" button

**Endpoint:** `POST /ai-assistant/suggest-diagnosis/`

### 2. Voice EMR (Speech-to-Text + AI Extraction)

**Where:** Consultation detail → "Voice EMR" tab

**How it works:**
1. Doctor clicks the microphone button
2. Browser Web Speech API captures speech
3. Transcription sent to Claude AI
4. AI extracts structured clinical data (VA, IOP, diagnosis, plan, etc.)
5. Fields are auto-populated in the consultation form

**Endpoint:** `POST /ai-assistant/voice/process/`

### 3. AI Virtual Receptionist

**Where:** `/ai-assistant/receptionist/`

Chat interface where patients/staff can ask questions about the hospital — appointment booking, services, locations, visiting hours. Powered by Claude with hospital-specific context.

### 4. AI Clinical Analytics

**Where:** `/ai-assistant/analytics/`

Ask natural language questions about hospital data:
- "How many cataract cases this month?"
- "Which doctor has the most glaucoma consultations?"
- "What are the top 5 diagnoses this week?"

Claude queries the database and returns formatted answers with charts.

---

## 9. Prescriptions & Optical

### Drug Prescriptions (`/prescriptions/`)

- Linked to a specific consultation
- Multi-item prescription (one form, many drugs)
- Each item: drug name, concentration, dose, frequency, duration, eye (RE/LE/OU)
- Route: Topical, Oral, Subconjunctival, Intravitreal, Subtenon, IV, IM
- Special instructions, dispensing notes
- PDF printout with hospital header, patient details, doctor signature line

### Optical Prescriptions (`/prescriptions/optical/`)

- Full spectacle Rx: Sphere, Cylinder, Axis, Add, VA
- Lens recommendations: Single Vision / Bifocal / Progressive / Contact Lens
- Frame preference, tint, anti-reflection notes
- Validity period
- PDF printout in standard optical format

---

## 10. Investigations & Laboratory

### Eye Investigations (`/investigations/`)

Ordered by doctors from within a consultation. Types include:
- OCT (Macula, Nerve Fibre Layer, Anterior Segment)
- Visual Field Testing (Humphrey, Goldmann)
- Fundus Photography / Fluorescein Angiography
- Biometry / IOL calculation
- Corneal Topography / Tomography
- Pachymetry / Specular Microscopy
- Electroretinogram (ERG)
- Ultrasound B-scan

Results entered by investigation technicians with image upload support.

### Laboratory Tests (`/laboratory/`)

Standard lab orders:
- Fasting Blood Sugar (FBS), HbA1c
- Full Blood Count (FBC / CBC)
- Urea, Creatinine, Electrolytes
- Liver Function Tests
- HIV, HBsAg, Hepatitis C screening
- INR / PT (pre-surgical)
- Sickle Cell screening

Results entered with reference ranges and flagging for abnormal values.

---

## 11. Pharmacy

**URL:** `/pharmacy/`

### Drug Formulary
20 ophthalmic drugs pre-seeded including:
- **Antibiotics:** Chloramphenicol, Ciprofloxacin, Tobramycin, Gentamicin
- **Anti-glaucoma:** Timolol, Latanoprost, Brimonidine, Dorzolamide
- **Steroids:** Prednisolone, Dexamethasone
- **Lubricants:** Artificial Tears, Carmellose
- **Mydriatics:** Tropicamide, Cyclopentolate
- **Antifungals:** Natamycin
- **Anaesthetic:** Proxymetacaine
- **Oral:** Acetazolamide, Prednisolone tablets, Ibuprofen, Amoxicillin

### Stock Management
- Batch-based stock (lot number, expiry date, supplier, purchase price)
- **FEFO dispensing** — oldest expiry date dispensed first automatically
- Reorder level alerts and expiry warnings on dashboard
- Stock movements tracked (received, dispensed, adjusted, expired)

### Dispensing
- Pharmacist opens a prescription linked to the consultation
- Add drugs with quantities (system suggests from FEFO batches)
- Mark dispensing as complete → invoice auto-created
- Dispensing record shows pharmacist, date, batch used

---

## 12. Billing & Invoicing

**URL:** `/billing/`

### Invoice Structure
- Linked to patient (and optionally a visit)
- Line items: consultation fee, drug costs, investigation fees, procedure charges
- Currency: Nigerian Naira (₦)
- Statuses: `DRAFT` → `SENT` → `PARTIAL` → `PAID` → `WAIVED` / `CANCELLED`

### Payment Recording
- Accepts cash, bank transfer, POS, mobile payment (USSD)
- Partial payments supported
- Receipt generation

### HMO / Insurance
- Patient can have an HMO provider
- HMO-covered items flagged during billing
- Waiver workflow for approved cases

---

## 13. Inpatient (IPD) & Theatre

**URL:** `/ipd/`

### Wards & Beds
Pre-seeded ward structure:
- Eye Ward A & B (general post-op)
- VIP Suite
- Surgical Day-Case Unit
- Paediatric Bay
- ICU

### Admissions
- Admit patient to a specific bed from any consultation
- Nursing notes with timestamps (every shift)
- Discharge planning with discharge summary

### Theatre (Operating Theatre)

**Day-Case Dashboard** — lists all scheduled cases for today with:
- Patient, surgeon, anaesthetist, procedure, time slot
- Pre-op checklist (consent, FBS, IV access, site marking, allergy check)
- Intra-op record (anaesthesia type, instruments used, duration)
- Post-op recovery status

**CSSD Integration** (`/cssd/`)
- Instrument tracking with sterilization cycle records
- Biological indicator (BI) test logging
- Dispatch tracking to theatre

---

## 14. Appointments & Scheduling

**URL:** `/appointments/`

### Clinic Board (`/appointments/clinic-board/`)
- Weekly calendar view showing all booked appointments by doctor
- Colour-coded by status: Scheduled, Confirmed, Completed, No-Show, Cancelled
- Click to view appointment details

### Booking (`/appointments/book/`)
- Select patient, doctor, department, date, time slot, visit type
- **Service tier** assigned at booking (Standard / Express / FastTrack / VIP)
- When patient arrives, appointment converts to a Visit automatically

### Appointment Types
- New Patient, Follow-up, Review, Emergency, Procedure

---

## 15. OPD / Triage

**URL:** `/opd/`

The OPD module tracks the clinical flow of walk-in and appointment patients through the triage process.

### OPD Dashboard
- Today's patient list ordered by arrival
- Live counts: Registered → Triage → With Doctor → Completed
- Colour-coded status badges

### Triage Record (`/opd/triage/<id>/`)
Nurse enters:
- Vital signs (BP, pulse, temperature, SpO2, weight)
- **Visual Acuity** (RE/LE unaided, with correction, near vision)
- **IOP** (RE/LE, method)
- Chief complaint confirmation
- Allergy alert review
- Assigns to doctor

### Visit Status Flow
```
REGISTERED → AT_CASHIER → PARAMETERS → WAITING → IN_CONSULTATION
    → INVESTIGATION / REFRACTION / LABORATORY
    → PHARMACY → OPTICAL
    → COUNSELING → WAITING_ADMISSION → ADMITTED
    → PRE_OP → IN_THEATRE → POST_OP
    → BILLING → COMPLETED → DISCHARGED
```

---

## 16. HRMS (Staff Management)

**URL:** `/hrms/`

### Staff Profiles
- Full employee record: personal details, qualifications, department, role
- Staff ID, joining date, employment type (full-time, part-time, locum, intern)
- Document uploads (licence, certificates)

### Attendance
- Clock-in / Clock-out via the HRMS portal
- Daily attendance report per department
- Late arrival flagging

### Leave Management
7 pre-seeded leave types:
- Annual Leave, Sick Leave, Compassionate Leave
- Study Leave, Maternity Leave, Paternity Leave
- Emergency Leave

Apply for leave → Medical Director approves/rejects → Leave balance updated

---

## 17. Other Support Modules

### Inventory (`/inventory/`)
- Hospital consumable items (gloves, syringes, sutures, eye pads, etc.)
- Vendors and purchase orders
- Stock movements and adjustments
- Low stock alerts

### Opticals (`/opticals/`)
- Frame catalogue (brand, style, colour, size, price)
- Lens catalogue (type, material, coating, index)
- Optical orders linked to optical prescriptions
- Order status: Ordered → In Fabrication → Ready → Dispensed

### Lead Management (`/leads/`)
- Track potential patients / referrals
- Pipeline stages: New Lead → Contacted → Appointment Booked → Converted
- Activity log for each lead
- Conversion metrics and source tracking

### Patient Feedback (`/feedback/`)
- Public feedback form at `/feedback/submit/` (no login required)
- Patient satisfaction survey (1-5 star ratings per service area)
- NPS (Net Promoter Score) tracking
- Complaint management with resolution workflow
- Analytics dashboard for management

### Notifications (`/notifications/`)
- System-wide notification bell (top-right in all authenticated pages)
- Clinical events trigger notifications (e.g., lab result ready, consultation assigned)
- Mark as read individually or all at once
- Notification types: Info, Warning, Urgent, Clinical

### Leadership Dashboard (`/leadership/`)
- Hospital-wide KPIs visible only to Medical Director / Admin
- Total patients, consultations, revenue (this month vs. last month)
- Top 10 diagnoses (bar chart)
- Department breakdown — consultations per dept
- Daily patient volume trend (line chart)
- All charts powered by Chart.js

---

## 18. Reporting & PDF Generation

All PDFs generated by **WeasyPrint** — pixel-perfect A4 documents with hospital header.

| Report | URL | Description |
|--------|-----|-------------|
| Visit Summary | `/reports/visit/<pk>/pdf/` | Full A4: vitals, consultations, diagnoses, prescriptions, billing |
| Consultation Report | `/reports/consultation/<pk>/pdf/` | Single consultation with exam findings and plan |
| Drug Prescription | `/reports/prescription/drug/<pk>/pdf/` | Prescription pad format with barcode |
| Optical Prescription | `/reports/prescription/optical/<pk>/pdf/` | Standard optical Rx format |
| Lab Results | `/reports/lab/<pk>/pdf/` | Lab report with reference ranges |
| Investigation Report | `/reports/investigation/<pk>/pdf/` | Investigation findings report |

All reports include hospital name, address, logo placeholder, doctor registration number, and date.

---

## 19. System Administration

### Django Admin (`/admin/`)
Full admin access for superusers. Manage all models directly.

### First-Time Setup
```bash
python manage.py setup_ehr
```
This seeds:
- 12 clinical departments
- 150+ ICD-10 ophthalmic diagnosis codes
- 15 investigation types
- 12 lab test types
- 17 QMS service counters
- 20 pharmacy drugs
- 7 leave types
- IPD wards and beds
- Creates superuser (admin@eyecare.com / Admin@1234)

### Staff Hub (`/accounts/staff-hub/`) — Super Admin Only
- Create, edit, activate/deactivate staff accounts
- Assign roles and departments
- Reset passwords
- View login history

### Settings & Configuration
Configured in `ehr_project/settings.py`:
- `HOSPITAL_NAME` — shown in all headers and PDFs
- `HOSPITAL_ADDRESS`, `HOSPITAL_PHONE`, `HOSPITAL_EMAIL`
- `ANTHROPIC_API_KEY` — required for AI features
- `DATABASE_URL` — SQLite (dev) or PostgreSQL (prod)
- `MEDIA_ROOT` — for uploaded files (investigation images, etc.)

---

## 20. URL Quick Reference

| Area | URL | Who Uses It |
|------|-----|------------|
| Login | `/accounts/login/` | Everyone |
| Main Dashboard | `/` | Everyone |
| Register Patient | `/patients/register/` | Receptionist |
| All Patients | `/patients/` | All clinical staff |
| Patient Record | `/patients/<patient_id>/` | All clinical staff |
| Patient Journey | `/patients/visit/<visit_number>/` | All clinical staff |
| Gate Entry Ticket | `/qms/gate/` | Gate staff |
| Cashier Ticket | `/qms/cashier/` | Cashier |
| QMS Dashboard | `/qms/` | Management, nurses |
| TV Display Board | `/qms/display/` | Waiting area TVs (no login) |
| Daily Census | `/qms/census/` | Management |
| Counter View | `/qms/counter/<id>/` | Counter staff |
| OPD / Triage | `/opd/` | Nurses |
| Appointments | `/appointments/` | Receptionist, doctors |
| Clinic Board | `/appointments/clinic-board/` | Doctors, management |
| Consultations | `/consultations/` | Doctors |
| New Consultation | `/consultations/new/<patient_id>/` | Doctors |
| Drug Prescription | `/prescriptions/drug/new/<consult_pk>/` | Doctors |
| Optical Prescription | `/prescriptions/optical/new/<consult_pk>/` | Doctors, optometrists |
| Eye Investigations | `/investigations/` | Investigation techs |
| Laboratory | `/laboratory/` | Lab technicians |
| Pharmacy | `/pharmacy/` | Pharmacists |
| Opticals | `/opticals/` | Optical dispensers |
| Billing | `/billing/` | Billing officers |
| IPD (Inpatient) | `/ipd/` | Ward nurses, doctors |
| CSSD | `/cssd/` | Theatre nurses |
| HRMS | `/hrms/` | HR / Admin |
| Inventory | `/inventory/` | Admin staff |
| Leads | `/leads/` | Front desk, admin |
| Feedback | `/feedback/` | Management |
| AI Receptionist | `/ai-assistant/receptionist/` | Reception staff |
| AI Analytics | `/ai-assistant/analytics/` | Medical director |
| Leadership Dashboard | `/leadership/` | Medical director |
| Reports | `/reports/` | Medical records |
| Django Admin | `/admin/` | Super admin |

---

## Database Models Summary

The system has **~45 database models** across 20+ Django apps:

- **Core:** `AuditModel`, `TimeStampedModel` (base models with UUID PK, soft-delete)
- **Accounts:** `User` (custom auth model with role field)
- **Patients:** `Patient`, `Visit`, `MedicalHistory`
- **Consultations:** `Consultation`, `ConsultationDiagnosis`, `ConsultationNote`, `Diagnosis`
- **QMS:** `QueueToken`, `ServiceCounter`, `DailyTokenSequence`
- **Prescriptions:** `DrugPrescription`, `PrescriptionItem`, `OpticalPrescription`
- **Investigations:** `InvestigationOrder`, `InvestigationType`
- **Laboratory:** `LabOrder`, `LabOrderItem`, `LabTest`
- **Pharmacy:** `Drug`, `StockBatch`, `DispensingRecord`, `DispensingItem`
- **Billing:** `Invoice`, `InvoiceItem`, `Payment`
- **Appointments:** `Appointment`
- **IPD:** `Ward`, `Bed`, `Admission`, `NursingNote`
- **CSSD:** `Instrument`, `SterilizationCycle`
- **HRMS:** `StaffProfile`, `Attendance`, `LeaveApplication`, `LeaveType`
- **AI:** `AIConversation`, `AIMessage`
- **Notifications:** `Notification`

---

*Document generated: 2026-03-26 | EHR Africa v2.0 — Built for specialist ophthalmology, Nigeria*
