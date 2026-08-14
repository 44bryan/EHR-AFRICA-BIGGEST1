from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
import datetime

doc = Document()

section = doc.sections[0]
section.top_margin = Inches(1)
section.bottom_margin = Inches(1)
section.left_margin = Inches(1.2)
section.right_margin = Inches(1.2)


def h(text, level=1):
    return doc.add_heading(text, level=level)


def body(text):
    p = doc.add_paragraph(text)
    p.style.font.size = Pt(11)
    return p


def bullet(text, bold_prefix=None):
    p = doc.add_paragraph(style='List Bullet')
    if bold_prefix:
        r1 = p.add_run(bold_prefix + ': ')
        r1.bold = True
        r1.font.size = Pt(11)
        r2 = p.add_run(text)
        r2.font.size = Pt(11)
    else:
        r = p.add_run(text)
        r.font.size = Pt(11)
    return p


# ── Title ──────────────────────────────────────────────────────────────────
doc.add_paragraph('')
title = doc.add_heading('EHR AFRICA — Electronic Health Records System', 0)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER

sub = doc.add_paragraph('System Capability Summary — Prepared for Human Resources')
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
sub.runs[0].font.size = Pt(12)
sub.runs[0].font.color.rgb = RGBColor(100, 100, 100)

date_p = doc.add_paragraph('Date: ' + datetime.date.today().strftime('%d %B %Y'))
date_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
date_p.runs[0].font.size = Pt(10)
date_p.runs[0].font.color.rgb = RGBColor(130, 130, 130)
doc.add_paragraph('')

# ── 1. Overview ────────────────────────────────────────────────────────────
h('1. Overview')
body(
    'EHR Africa is a fully web-based Electronic Health Records system designed specifically '
    'for eye care hospitals and clinics. It replaces paper records and manual processes with '
    'a single secure digital platform that all departments can access from any computer on '
    'the hospital network. The system covers the entire patient journey — from arrival at '
    'the gate, through consultation, pharmacy, billing, and follow-up.'
)

# ── 2. Who Uses It ─────────────────────────────────────────────────────────
h('2. Who Uses the System')
body(
    'The system has 36 distinct staff roles. Each role has its own personalised dashboard '
    'and can only access what is relevant to that role — a cashier cannot see clinical notes, '
    'and a doctor cannot change financial records.'
)
roles = [
    ('Doctors & Specialists', 'Ophthalmologists across 11 subspecialties, Anaesthetists'),
    ('Nursing & Allied Health', 'Consultation Nurses, Triage Nurses, Orthoptists, Counselling Nurses'),
    ('Records & Reception', 'Medical Records Officers, Receptionists, Gatekeepers'),
    ('Pharmacy & Lab', 'Pharmacists, Laboratory Technicians, CSSD Technicians'),
    ('Optical Department', 'Optometrists, Opticians'),
    ('Billing & Finance', 'Cashiers, Chief Cashiers, Accountants, Senior Accountants, Finance Director'),
    ('Administration', 'HRMS Officers, Admission Officers'),
    ('Leadership', 'CEO, Medical Director, Admin Director, Nurse Director, Quality Officer'),
    ('IT', 'System Administrator'),
]
for role, detail in roles:
    bullet(detail, bold_prefix=role)

# ── 3. What It Can Do ──────────────────────────────────────────────────────
h('3. What the System Can Do')

h('3.1  Patient Registration and Records', 2)
body('Every patient gets a unique ID and a permanent digital file that follows them across all visits.')
for item in [
    'Register new patients with full demographics, contact, and insurance information',
    'Pre-register patients before arrival so reception is faster',
    'Record patient allergies with automatic alerts when a doctor prescribes a conflicting drug',
    'Maintain a permanent problem list per patient (chronic conditions, surgical history)',
    'Generate patient registration cards and printable medical record summaries',
    'Search the entire patient database instantly by name, ID, or phone number',
]:
    bullet(item)

h('3.2  Queue Management (Patient Flow)', 2)
body('Eliminates paper tickets and manual queuing. Patients receive a digital queue number on arrival.')
for item in [
    'Gate staff issue queue tickets at entry',
    'Receptionists assign patients to the correct doctor or department queue',
    'Doctors see a live list of patients waiting for them',
    'VIP and express lanes supported',
    'Digital display boards show queue status in waiting areas',
    'Cashier queue managed separately from the clinical queue',
]:
    bullet(item)

h('3.3  Appointments and Scheduling', 2)
body('Reduces walk-in congestion and helps the hospital plan the day.')
for item in [
    'Book, reschedule, and cancel patient appointments',
    'Doctors set their own availability schedules',
    'Clinic board shows the full day schedule at a glance',
    'Follow-up appointments created automatically at end of consultation',
    'Check patients in on arrival against their booked appointment',
]:
    bullet(item)

h('3.4  Clinical Consultations', 2)
body('Doctors work entirely on screen. Paper consultation notes are fully eliminated.')
for item in [
    '13 specialised clinical forms — one for each eye care subspecialty (Retina, Glaucoma, Cataract, Paediatric, Low Vision, Cornea, Neuro-Ophthalmology, Oculoplastics, Uveitis, and more)',
    'Triage nurses record vitals (blood pressure, visual acuity, IOP, complaints) before the doctor sees the patient',
    'Doctors record diagnosis, treatment plan, and prescriptions digitally',
    'ICD-10 coded diagnoses for accurate disease tracking and government reporting',
    'Intraocular Pressure (IOP) trend charts for glaucoma monitoring',
    'Referral letters and medical certificates generated as printable PDFs',
    'Trainees can have their consultations co-signed by a senior doctor',
]:
    bullet(item)

h('3.5  Pharmacy', 2)
body('Doctor prescriptions flow directly to the pharmacy counter — no paper needed.')
for item in [
    'Pharmacists receive prescriptions electronically from the doctor',
    'Drug stock tracked in real time with low-stock alerts',
    'Dispensing records kept permanently per patient',
    'Automatic drug interaction checker alerts pharmacists to dangerous combinations',
    'Dispensing receipts printed for patients',
]:
    bullet(item)

h('3.6  Laboratory', 2)
for item in [
    'Doctors request lab tests from the consultation screen',
    'Lab technicians receive requests and enter results electronically',
    'Results visible to the requesting doctor immediately upon completion',
    'Lab reports generated as printable PDFs',
    'Imaging studies (OCT, fundus photos, etc.) stored and linked to patient records',
]:
    bullet(item)

h('3.7  Optical Department', 2)
for item in [
    'Optometrists create optical prescriptions digitally',
    'Optical orders tracked from prescription through to lens dispensing',
    'Dispensing status updated in real time',
    'Optical prescription PDFs generated for patients',
]:
    bullet(item)

h('3.8  Inpatient and Theatre (IPD)', 2)
body('Manages admitted patients, ward assignments, and surgical scheduling.')
for item in [
    'Admit patients to specific wards and beds',
    'Ward rounds and nursing notes recorded digitally',
    'Nursing care plans created and tracked per admission',
    'Surgical bookings managed with a theatre scheduling board',
    'Anaesthetic records completed digitally (meets JCI accreditation standard)',
    'Post-operative notes and discharge summaries recorded',
]:
    bullet(item)

h('3.9  CSSD (Central Sterile Supply Department)', 2)
for item in [
    'Sterilization cycles logged and tracked',
    'Instruments dispatched and received recorded',
    'Full traceability of sterilized equipment per surgical procedure',
]:
    bullet(item)

h('3.10  Billing and Finance', 2)
body('Complete financial management from patient invoice to executive reporting.')
for item in [
    'Invoices created automatically from services rendered (consultations, tests, drugs, procedures)',
    'Cashier POS for collecting payments — cash, mobile money, card, or insurance',
    'Proforma invoices for insurance and corporate clients before payment',
    'Corporate and HMO account management with credit limits and monthly statements',
    'Cashier shift management — shifts opened, closed, and reconciled daily',
    'Expense management with approval workflow',
    'Petty cash fund tracking',
    'Annual and departmental budget vs actual spending reports',
    'Void and refund register with full audit trail',
    'Accounts receivable aging report',
    'Daily and monthly revenue summaries',
]:
    bullet(item)

h('3.11  Human Resources (HRMS)', 2)
for item in [
    'Staff profiles for all 36 roles',
    'Leave requests and management approval workflow',
    'Attendance tracking',
    'Payroll processing and payslip generation',
    'Department management and staff assignment',
]:
    bullet(item)

h('3.12  Reporting and Analytics', 2)
body('Management and government reports generated automatically from live system data.')
for item in [
    'Disease burden analysis — most common diagnoses over any date range',
    'Ministry of Health (MoH) disease statistics export for government submissions',
    'Revenue reports — monthly, annual, broken down by payment method',
    'Staff performance — number of consultations per doctor over any period',
    'Complete patient visit history PDF',
    'Retina outcomes dashboard for tracking long-term treatment results',
    'Executive dashboards for CEO, Medical Director, Finance Director, and Admin Director',
]:
    bullet(item)

h('3.13  AI Clinical Assistant', 2)
body('An artificial intelligence assistant built into the system to support clinical decisions.')
for item in [
    'Doctors can ask clinical questions and receive evidence-based answers instantly',
    'Drug interaction checking powered by AI',
    'Works both online and fully offline on the local hospital network',
]:
    bullet(item)

# ── 4. Security ────────────────────────────────────────────────────────────
h('4. Security and Compliance')
for item in [
    'All staff log in with a username and password (minimum 12 characters required)',
    'Every action is logged with the staff name, date, time, and computer address',
    'Patient health information access is audited on every view',
    'Role-based access — staff only see what their role permits',
    'Automatic account lockout after repeated failed login attempts',
    'Data backed up automatically every night',
    'Designed to meet JCI (Joint Commission International) accreditation standards',
]:
    bullet(item)

# ── 5. Benefits ────────────────────────────────────────────────────────────
h('5. Key Benefits for the Hospital')
benefits = [
    ('No lost records', 'Patient files can never be lost, misfiled, or damaged.'),
    ('Faster patient flow', 'Digital queuing and pre-registration reduce waiting times significantly.'),
    ('Fewer medical errors', 'Allergy alerts, drug interaction warnings, and legible prescriptions protect patients.'),
    ('Real-time visibility', 'Management can see what is happening across all departments at any moment.'),
    ('Accurate billing', 'Services billed automatically — no missed charges and no manual calculation errors.'),
    ('One-click reporting', 'MoH reports, revenue summaries, and disease statistics generated instantly.'),
    ('Staff accountability', 'Every action is time-stamped and attributed to a named staff member.'),
    ('Scalable', 'Supports multiple departments, wards, and hundreds of staff using the system simultaneously.'),
]
for title_text, detail in benefits:
    bullet(detail, bold_prefix=title_text)

# ── Footer note ────────────────────────────────────────────────────────────
doc.add_paragraph('')
note = doc.add_paragraph(
    'This document is prepared for Human Resources and general management orientation. '
    'For technical specifications or IT deployment details, please refer to the IT department.'
)
note.runs[0].font.size = Pt(9)
note.runs[0].font.color.rgb = RGBColor(130, 130, 130)
note.runs[0].font.italic = True

doc.save(r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP\EHR_Africa_System_Summary.docx')
print('Done')
