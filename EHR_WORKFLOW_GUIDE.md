# Eye Care Hospital — EHR System Workflow Guide
### Demo Presentation Document · April 2026

---

## Overview

This system is a fully integrated Electronic Health Record (EHR) platform built for a specialist ophthalmology hospital in Cameroon. It manages the complete patient journey — from arrival at the gate through consultation, investigations, surgery, pharmacy, optical shop, and discharge — across four service tiers with a built-in Queue Management System (QMS).

---

## 1. Service Tiers

| Tier | Description | Cashier Station |
|---|---|---|
| **Standard** | Walk-in patients, normal queue | Standard Cashier |
| **Fast Track / Express** | Priority queue, faster service | Fast Track Cashier |
| **VIP** | Premium service, private consultation rooms | VIP Cashier (all-in-one) |
| **Insured / HMO** | Insurance-covered patients | Insured Cashier |

> **Cashier Station Assignment**: The Admin assigns a `cashier_station` to each Cashier/Billing Officer account (Standard / Fast Track / VIP / Insured / All). QMS tokens are routed only to the matching cashier station.

---

## 2. Patient Journey — Standard / Fast Track

### Step 1 — Gate Entry / Pre-Registration (Kiosk)
- Patient arrives and uses the **self-service kiosk** (public pre-registration form)
- Enters: name, date of birth, gender, phone number, address (Cameroonian fields: quarter, division, region), nature of consultation (Standard/Fast Track/Insured/VIP), answers two questions:
  - "Have you consulted here before?" (yes/no)
  - "Do you have a referral letter?" (yes → upload scan/photo)
- System generates a **QR code slip** with a token number
- Patient takes the printed slip to the reception desk

### Step 2 — Reception (Receptionist)
- Receptionist **scans the QR code** from the patient's slip
- System auto-fills the registration form from pre-registration data
- Receptionist reviews, completes missing fields (photo, blood group, genotype, next of kin), and **registers the patient**
- System creates a new `Patient` record + `Visit` record
- **QMS CASHIER token** is automatically issued and patient joins the cashier queue
- Patient is told: "Go to Cashier Window [N]"

### Step 3 — Cashier (Standard / Fast Track Station)
- Cashier sees their queue of patients assigned to their station
- Calls the next patient to their window
- Confirms patient identity, records chief complaint
- Collects **consultation fee** (or records insurance details)
- Issues a **QMS CONSULTATION token** → patient joins the doctor's queue
- System records the payment in billing

### Step 4 — Triage (OPD Nurse)
- Nurse calls patient from the triage queue
- Records **vital signs**: BP, pulse, temperature, weight, height, BMI
- Records **visual acuity** (VA OD / OS unaided + aided), IOP if indicated
- Routes patient to the appropriate doctor's queue

### Step 5 — Doctor Consultation
- Doctor sees their queue in the workstation
- Calls patient, records:
  - Chief complaint, history of presenting complaint
  - Ocular examination (anterior + posterior segment)
  - Department-specific findings (e.g. cataract grading, fundus findings)
  - Diagnosis (ICD-10 coded)
  - Management plan
- **If surgery is recommended**: Doctor enables the Surgical Plan panel, selects:
  - Procedure (dropdown: Phaco, Trabeculectomy, Vitrectomy, etc.)
  - Eye (RE / LE / BE)
  - Anaesthesia type (Local / General / Sedation)
  - Pre-op requirements and notes
  - Sends patient to **Counseling Queue**
- **If investigations required**: Doctor orders investigations → patient joins investigations queue
- **If optical prescription**: Doctor records refraction → patient visits optical shop

---

## 3. Surgical Pathway

### Step A — Surgical Counseling (Counseling Nurse)
- Counseling Nurse calls patient from their counter queue
- **Reads doctor's surgical plan** (shown in read-only panel at top of form):
  - Procedure, eye, anaesthesia, pre-op notes, management plan
- Conducts counseling session covering 10 standard topics (checklist):
  - Purpose & benefits, risks, alternatives, anaesthesia, fasting/medication instructions, post-op care, follow-up schedule, warning signs, what to bring, cost & payment
- Records **Counseling Notes**
- Records **Pre-op Requirements** (blood work, medications to stop, fasting instructions)
- Records **Patient Decision**:
  - ✅ Consent signed → patient proceeds to Admission (QMS ADMISSION token issued)
  - ⏰ Needs more time → counseling saved, follow-up appointment scheduled
- **VIP patients**: Counseling nurse comes to the VIP consultation room — the VIP patient does not go to the counseling desk

### Step B — Surgical Booking (Admission Officer)
- Admission Officer sees the **Surgical Booking Queue**
- Reviews counseling summary at top of form (consent status, counseling notes, pre-op requirements)
- Confirms / updates:
  - Procedure (dropdown), eye laterality, anaesthesia type
  - Assigned surgeon
  - Surgery date & time
  - Theatre (Theatre 1 / Theatre 2 / Laser Room / Minor Procedures)
- Sets **Payment Terms**:
  - Total surgery cost (XAF)
  - Deposit required to confirm booking
  - Payment notes (e.g. "Balance of 150,000 XAF due on surgery day")
- Confirms pre-op requirements for patient
- System creates `SurgicalBooking` record with status: **Pending Payment / Deposit**
- A **proforma** is generated showing:
  - Doctor's recommendation
  - Surgery cost breakdown
  - Available ward/bed options and nightly rates
  - Payment terms

### Step C — Surgery Deposit Payment (Cashier)
- Patient pays deposit at the cashier
- Cashier records payment against the booking
- Status changes to **Confirmed** → patient is officially booked for surgery

### Step D — Admission (Surgery Day)
- Patient arrives on surgery day
- Admission Officer assigns a **bed/ward**:
  - Day Case (for day surgery), General Ward, Private Room, ICU
- System creates `Admission` record linked to the `SurgicalBooking`
- Bed status changes to **Occupied**

### Step E — Theatre / Surgery
- Theatre Nurse manages the theatre workflow
- MAR (Medication Administration Record) tracks pre-op medications
- Nursing notes record all pre/intra/post-op observations

### Step F — Discharge
- Ward Nurse or Admission Officer initiates discharge
- Records discharge summary
- Bed status returns to **Available**
- Final billing is settled before discharge

---

## 4. VIP Patient Workflow

The VIP workflow is streamlined — the **VIP Cashier does everything**:

1. **No separate receptionist** — VIP cashier handles registration (new patients) or checks returning patients
2. **Gate entry** → patient proceeds directly to VIP reception window (no kiosk queue)
3. **VIP Cashier**:
   - Registers new patients (full form) OR confirms returning patient identity
   - Confirms consultation type + insurance if applicable
   - Issues QMS CONSULTATION token for VIP doctor queue
   - Collects payment / processes insurance
4. **Triage** → in private VIP triage area
5. **Doctor** → in private VIP consultation room
6. **Counseling** → Counseling Nurse visits the VIP consultation room (patient does not move)
7. **Admission / Booking** → as above, VIP ward/private room options shown in proforma
8. **Pharmacy for VIP**: VIP patients do not go to the pharmacy. A staff member (nurse or dispenser) collects medications on behalf of the patient and delivers them to the consultation room or ward.

---

## 5. Optical Shop Workflow

1. **Doctor** records refraction/optical prescription in the consultation workstation
2. **Optical Receptionist**:
   - Opens the patient's consultation record
   - Prints the **spectacle/contact lens prescription**
   - Sends patient to the optical shop frame selection area
   - Issues a **QMS OPTICAL CASHIER token** → patient joins optical cashier queue
3. **Patient** selects frames/lenses in the optical shop
4. **Optical Cashier** calls patient from optical queue:
   - Reviews prescription
   - Confirms frame/lens selection and pricing
   - Processes payment
   - Issues job card to the optical lab/dispenser
5. **Optical Dispenser** prepares lenses, fits frames, and issues to patient

---

## 6. Investigations Workflow

1. **Doctor** orders investigations during consultation (lab, imaging, biometry, etc.)
2. Patient receives an **investigations QMS token**
3. **Investigation Technician** calls patient from their counter queue
4. Records investigation results in the patient's record
5. Results are visible to the doctor on the workstation
6. Doctor reviews results and updates management plan

---

## 7. Pharmacy Workflow

1. **Doctor** issues a prescription at end of consultation
2. Prescription generates a **QMS PHARMACY token**
3. **Pharmacist** calls patient from their pharmacy queue
4. Dispenses medications, records on patient record
5. Patient pays at the pharmacy cashier window (or pharmacy POS)
6. **VIP exception**: Nurse/staff collects medications and delivers to patient

---

## 8. Outreach Workflow

Outreach sessions are conducted in the field (village, community center, school, etc.) by the hospital's outreach team.

### Team Composition
- **Outreach Ophthalmologist** (General Ophthalmologist assigned to outreach)
- **Outreach Nurse** (handles triage/vitals)
- **Support staff**

### Flow
1. **Registration**: Patients are registered by outreach staff using the mobile/tablet EHR interface
2. **Triage**: Outreach Nurse records vitals and visual acuity
3. **Consultation**: Outreach Ophthalmologist consults patients using the standard consultation workstation (general ophthalmology workflow)
4. **All services are FREE at the outreach site**:
   - No consultation fee
   - No investigation fee
   - Medications dispensed free of charge
5. **Surgical referrals**: If surgery is recommended, patient is:
   - Counseled on-site
   - Given a referral letter / booking slip for the main hospital
   - Booked into the hospital's surgical booking queue
   - Follows the standard surgical pathway from Step B onwards
6. **Statistics**: Outreach module tracks:
   - Total patients seen
   - Procedures performed (injections, minor treatments)
   - Referrals to hospital (for surgery, investigations)
   - Surgeries completed from outreach referrals

---

## 9. Queue Management System (QMS)

### Token Types
| Token | Issued At | Goes To |
|---|---|---|
| CASHIER | Registration / Gate | Cashier window (matched to station) |
| CONSULTATION | Cashier | Doctor queue |
| TRIAGE | After consultation registration | Nurse triage |
| INVESTIGATIONS | Doctor orders | Investigation Technician |
| PHARMACY | Doctor prescription | Pharmacist |
| OPTICAL | Optical Receptionist | Optical Cashier |
| COUNSELING | Doctor sends to surgery | Counseling Nurse |
| ADMISSION | After consent signed | Admission Officer |

### Counter Assignment
- Each staff member with a counter role (receptionist, cashier, nurse, pharmacist, counseling nurse, admission officer, investigation technician, optical dispenser) is assigned a **Service Counter** by the admin
- Staff see only the queue for their own counter
- Cashier staff additionally have a **Cashier Station** (Standard/Fast Track/VIP/Insured) to further filter tokens

### Calling Patients
- Staff click "Call Next Patient" on their counter workstation
- Displays are updated hospital-wide
- Current and next patient names/token numbers are shown on waiting area screens

---

## 10. Billing & POS

### Point of Sale (POS)
- The **POS link** is always visible in the left sidebar for all cashier accounts
- Clicking POS intelligently navigates to:
  1. The active QMS token currently at the counter (if one exists) → goes to POS for that invoice
  2. The most recently opened invoice → goes to invoice detail
  3. The billing dashboard (if no active work)

### Invoice Lifecycle
1. Created when patient visits and pays consultation fee
2. Line items added for consultations, investigations, medications, optical, surgery
3. Payments recorded (cash, mobile money, insurance, cheque)
4. Invoice closed when fully settled

### Cashier Station Routing
- Admin sets each cashier's station in their user profile
- Standard cashier: sees Standard consultation tokens only
- VIP cashier: sees VIP tokens + can register patients
- Insured cashier: sees insurance/HMO tokens
- "All" station: sees every token (for general/overflow use)

---

## 11. Staff Roles Summary

| Role | Primary Responsibility | Key Access |
|---|---|---|
| Medical Director | Clinic management, supervision, own consultations | Full system access |
| Ophthalmologist | Patient consultations (general) | Workstation, consultation records |
| Specialist (Retina/Glaucoma/Cornea/etc.) | Specialist consultations | Workstation, department-specific forms |
| Optometrist | Refraction, low vision | Refraction workstation |
| OPD Nurse (Triage) | Vitals, visual acuity, queue routing | Triage workstation |
| Counseling Nurse | Surgical counseling, consent | Counseling queue + form |
| Theatre Nurse | Theatre preparation, nursing notes | IPD nursing notes, MAR |
| Ward Nurse | Inpatient nursing care | IPD nursing notes, MAR |
| Receptionist | Patient registration, QMS | Registration, QMS |
| Cashier (Standard) | Payment collection (standard patients) | POS, billing, QMS |
| Cashier (Fast Track) | Payment collection (express patients) | POS, billing, QMS |
| Cashier (VIP) | Registration + payment (VIP all-in-one) | Registration, POS, billing |
| Cashier (Insured) | Insurance verification + payment | POS, billing, insurance |
| Admission Officer | Surgical booking, ward admission | IPD, surgical booking queue |
| Investigation Technician | Investigation results entry | Investigations workstation |
| Pharmacist | Medication dispensing | Pharmacy queue, prescriptions |
| Optical Dispenser | Optical prescription fulfilment | Optical workstation |
| Medical Records | Patient file management | Patient records |
| Admin | System configuration, user management | Admin panel |

---

## 12. Doctor Schedule & Clinic Board

- **Medical Director** manages the weekly clinic timetable via Doctor Schedules
- Each schedule slot records: doctor, department, day of week, start/end time, room/location, max patients per session
- The **Clinic Board** is visible to all staff and shows today's schedule — which doctor is in which room at what time
- Reception uses the clinic board to direct patients to the correct consultation room
- Doctors can view their own schedule from the dashboard

---

## 13. Key System Features

- **Cameroonian address fields**: Post address, Quarter, Village/Town, Division, Region, Country
- **Referral documents**: Patients with referral letters can upload a scan at registration; document is attached to the patient record
- **Surgery type standardisation**: All 30+ ophthalmic procedure types are available as a dropdown throughout the system (Doctor → Counselor → Admission Officer) — no free-text entry
- **Consent tracking**: Counseling records capture consent status, date, and counseling topics covered
- **Length of stay tracking**: Automatic calculation of inpatient stay duration
- **Bed management**: Ward occupancy, bed availability, per-bed pricing overrides for VIP rooms
- **Pre-op checklist**: JSON-stored checklist (CBC, RBG, ECG, chest X-ray, etc.) attached to each surgical booking
- **Audit trail**: All records include created_at, updated_at, created_by fields
- **Soft delete**: Records are never permanently deleted — flagged as is_deleted=True

---

*Document generated for demo presentation — April 2026*
