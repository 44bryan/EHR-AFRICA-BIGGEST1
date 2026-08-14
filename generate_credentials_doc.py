"""Generate Dry Run Credentials Word Document — organised by CLINIC UNIT."""
from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import datetime

OUT      = 'c:/Users/GROD/Desktop/EHR AFRICA BACKUP/workflow_guides/Dry Run Credentials.docx'
TODAY    = datetime.date.today().strftime('%d %B %Y')
URL      = 'http://192.168.30.169'
PASSWORD = 'Demo@2026!'

# ── Colour palette ─────────────────────────────────────────────────────────────
BLUE    = RGBColor(0x1D, 0x4E, 0xD8)
WHITE   = RGBColor(0xFF, 0xFF, 0xFF)
DGRAY   = RGBColor(0x33, 0x41, 0x55)
RED     = RGBColor(0xDC, 0x26, 0x26)
GREEN   = RGBColor(0x05, 0x96, 0x69)
PURPLE  = RGBColor(0x7C, 0x3A, 0xED)
TEAL    = RGBColor(0x08, 0x91, 0xB2)
ORANGE  = RGBColor(0xEA, 0x58, 0x0C)
ROSE    = RGBColor(0xBE, 0x12, 0x5A)
INDIGO  = RGBColor(0x43, 0x38, 0xCA)

# Section colour: (header_fill, row_fill_odd, row_fill_even, accent_rgb)
SECTION_STYLES = {
    'gate':       ('0F172A', 'F8FAFC', 'FFFFFF', DGRAY),
    'reception':  ('1E40AF', 'EFF6FF', 'FFFFFF', BLUE),
    'standard':   ('065F46', 'F0FDF4', 'FFFFFF', GREEN),
    'express':    ('7C3AED', 'F5F3FF', 'FFFFFF', PURPLE),
    'vip':        ('B45309', 'FFFBEB', 'FFFFFF', ORANGE),
    'insured':    ('0E7490', 'ECFEFF', 'FFFFFF', TEAL),
    'specialty':  ('BE185D', 'FFF1F2', 'FFFFFF', ROSE),
    'support':    ('1D4ED8', 'EFF6FF', 'FFFFFF', BLUE),
    'ipd':        ('4338CA', 'EEF2FF', 'FFFFFF', INDIGO),
    'management': ('1E293B', 'F8FAFC', 'FFFFFF', DGRAY),
}

# ── Account data ───────────────────────────────────────────────────────────────
# (Full Name, Username, Role / Title, Notes / Position)
SECTIONS = [
    # ── Gate & QMS ─────────────────────────────────────────────────────────────
    (
        'gate',
        'GATE / QMS — Entry & Queue Management',
        'These staff control patient entry and issue queue tickets.',
        [
            ('Demo Gatekeeper',   'gate01',   'Gatekeeper',         'Main hospital gate — screens and grants entry'),
            ('Demo TSO',          'tso01',    'Gatekeeper (TSO)',    'Queue Management desk — issues QMS ticket after entry'),
        ],
    ),

    # ── Reception & Medical Records ────────────────────────────────────────────
    (
        'reception',
        'RECEPTION & MEDICAL RECORDS',
        'Registration, pre-registration, patient file retrieval.',
        [
            ('Demo Receptionist', 'recep01',  'Receptionist',             'New patient registration & appointment booking'),
            ('Demo Med Records',  'medrec01', 'Medical Records Officer',  'Pull existing files, update demographics'),
        ],
    ),

    # ── Standard OPD — 5 dedicated doctors ────────────────────────────────────
    (
        'standard',
        'STANDARD OPD — General Ophthalmology (5 Doctors)',
        'Each doctor sees STANDARD queue patients only. Log in separately with each account to simulate concurrent clinics.',
        [
            ('Demo Doctor 1',  'doctor01', 'Ophthalmologist — Standard OPD', 'Consulting Room 1'),
            ('Demo Doctor 2',  'doctor02', 'Ophthalmologist — Standard OPD', 'Consulting Room 2'),
            ('Demo Doctor 3',  'doctor03', 'Ophthalmologist — Standard OPD', 'Consulting Room 3'),
            ('Demo Doctor 4',  'doctor04', 'Ophthalmologist — Standard OPD', 'Consulting Room 4'),
            ('Demo Doctor 5',  'doctor05', 'Ophthalmologist — Standard OPD', 'Consulting Room 5'),
            ('Demo Triage Nurse 1', 'nurse01',   'OPD / Triage Nurse', 'Triage station — vitals & visual acuity'),
            ('Demo Triage Nurse 2', 'nurse02',   'OPD / Triage Nurse', 'Triage station — backup nurse'),
            ('Demo Triage Nurse 3', 'nurse03',   'OPD / Triage Nurse', 'Triage station — backup nurse'),
            ('Demo Consult Nurse 1','cnurse01',  'Consultation Nurse', 'Supports doctor in consulting room'),
            ('Demo Consult Nurse 2','cnurse02',  'Consultation Nurse', 'Supports doctor in consulting room'),
            ('Demo Cashier 1',  'cashier01', 'Cashier — Standard Desk', 'Standard billing desk 1'),
            ('Demo Cashier 2',  'cashier02', 'Cashier — Standard Desk', 'Standard billing desk 2'),
            ('Demo Cashier 3',  'cashier03', 'Cashier — Standard Desk', 'Standard billing desk 3'),
        ],
    ),

    # ── Express / Fast Track Clinic ────────────────────────────────────────────
    (
        'express',
        'EXPRESS CLINIC — Fast Track (2 Doctors)',
        'Patients pay BEFORE seeing the doctor (prepaid flow). Express cashier collects payment at entry.',
        [
            ('Demo Express Doc 1',   'expdoc01',   'Ophthalmologist — Express Clinic', 'Express Room 1 — fast consult'),
            ('Demo Express Doc 2',   'expdoc02',   'Ophthalmologist — Express Clinic', 'Express Room 2 — fast consult'),
            ('Demo Express Nurse',   'expnurse01', 'OPD / Triage Nurse — Express',    'Triage & assist in Express clinic'),
            ('Demo Cashier Express', 'cashierexp', 'Cashier — Express Desk',           'Collects payment BEFORE consultation'),
        ],
    ),

    # ── VIP Clinic ────────────────────────────────────────────────────────────
    (
        'vip',
        'VIP CLINIC — Private / Executive (2 Doctors)',
        'Premium service lane. VIP cashier handles billing separately from standard desk.',
        [
            ('Demo VIP Doctor 1', 'vipdoc01',   'Ophthalmologist — VIP Clinic', 'VIP Suite 1'),
            ('Demo VIP Doctor 2', 'vipdoc02',   'Ophthalmologist — VIP Clinic', 'VIP Suite 2'),
            ('Demo VIP Nurse',    'vipnurse01', 'OPD / Triage Nurse — VIP',    'Triage & assist in VIP clinic'),
            ('Demo Cashier VIP',  'cashiervip', 'Cashier — VIP Desk',           'Billing for VIP patients only'),
        ],
    ),

    # ── Insured / HMO Clinic ──────────────────────────────────────────────────
    (
        'insured',
        'INSURED / HMO CLINIC (2 Doctors)',
        'Corporate / insurance patients. Billing officer verifies cover; cashier collects co-pay.',
        [
            ('Demo Insured Doc 1',   'insdoc01',   'Ophthalmologist — Insured Clinic', 'HMO Room 1'),
            ('Demo Insured Doc 2',   'insdoc02',   'Ophthalmologist — Insured Clinic', 'HMO Room 2'),
            ('Demo Insured Nurse',   'insnurse01', 'OPD / Triage Nurse — Insured',    'Triage & assist in HMO clinic'),
            ('Demo Billing Officer', 'billing01',  'Billing Officer',                  'Verifies insurance, raises proforma'),
            ('Demo Cashier (HMO)',   'cashier01',  'Cashier — General Desk',           'Co-pay collection (shared desk)'),
        ],
    ),

    # ── Specialty Clinics ─────────────────────────────────────────────────────
    (
        'specialty',
        'SPECIALTY CLINICS',
        'Each specialist manages their own dedicated sub-clinic queue.',
        [
            ('Demo Retina Spec',   'retina01',  'Retina Specialist',            'Retina clinic'),
            ('Demo Glaucoma Spec', 'glauco01',  'Glaucoma Specialist',          'Glaucoma clinic'),
            ('Demo Cataract Surg', 'cataract01','Ophthalmologist — Cataract',   'Surgical / Cataract clinic'),
            ('Demo Pediatric Oph', 'paedoph01', 'Pediatric Refractionist',      'Pediatric eye clinic'),
            ('Demo Low Vision',    'lowvis01',  'Low Vision Specialist',         'Low vision clinic'),
            ('Demo Optometrist 1', 'optom01',   'Optometrist',                  'Refraction / optometry room 1'),
            ('Demo Optometrist 2', 'optom02',   'Optometrist',                  'Refraction / optometry room 2'),
            ('Demo Optometrist 3', 'optom03',   'Optometrist',                  'Refraction / optometry room 3'),
        ],
    ),

    # ── Support Services ──────────────────────────────────────────────────────
    (
        'support',
        'PHARMACY, LABORATORY & OPTICAL',
        '',
        [
            ('Demo Pharmacist',    'pharma01',  'Pharmacist',                 'Dispenses prescriptions'),
            ('Demo Lab Tech',      'labtech01', 'Lab Technician',             'Processes laboratory orders'),
            ('Demo Invest Tech',   'invest01',  'Investigation Technician',   'Imaging & investigations'),
            ('Demo Opt Dispenser', 'optics01',  'Optical Dispenser',          'Spectacles & contact lens orders'),
        ],
    ),

    # ── IPD / Theatre ─────────────────────────────────────────────────────────
    (
        'ipd',
        'IPD / WARD & THEATRE',
        '',
        [
            ('Demo Ward Nurse',    'wardnurse01', 'Ward Nurse',       'Inpatient nursing — ward rounds'),
            ('Demo Theatre Nurse', 'theatre01',   'Theatre Nurse',    'Surgical suite nursing'),
            ('Demo Anaesthetist',  'anaes01',     'Anaesthetist',     'Pre-op & intra-op anaesthesia'),
            ('Demo Admission Ofc', 'admiss01',    'Admission Officer','IPD admissions & surgical booking'),
        ],
    ),

    # ── Management ────────────────────────────────────────────────────────────
    (
        'management',
        'MANAGEMENT & ADMINISTRATION',
        '',
        [
            ('Demo Med Director',  'meddir01',    'Medical Director',   'Clinical governance & oversight'),
            ('Demo Chief Cashier', 'chiefcash01', 'Chief Cashier',      'Opens day, verifies shifts, oversight'),
            ('Demo Accountant',    'account01',   'Accountant',         'Invoices, refunds, AR aging'),
            ('Demo Finance Dir',   'findir01',    'Finance Director',   'Full financial access + strategy'),
            ('Demo Admin Director','admindir01',  'Admin Director',     'HR & administration'),
            ('Demo CEO',           'ceo01',       'CEO',                'Executive dashboard'),
        ],
    ),
]

# ── Helpers ────────────────────────────────────────────────────────────────────
def set_cell_bg(cell, hex_color):
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd  = OxmlElement('w:shd')
    shd.set(qn('w:val'),   'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'),  hex_color)
    tcPr.append(shd)


def add_section(doc, style_key, title, subtitle, accounts):
    style       = SECTION_STYLES[style_key]
    hdr_fill    = style[0]
    odd_fill    = style[1]
    even_fill   = style[2]
    accent_rgb  = style[3]

    # Section header bar
    hdr_tbl = doc.add_table(rows=1, cols=1)
    hdr_tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    hdr_cell = hdr_tbl.rows[0].cells[0]
    set_cell_bg(hdr_cell, hdr_fill)
    hp = hdr_cell.paragraphs[0]
    hp.paragraph_format.space_before = Pt(4)
    hp.paragraph_format.space_after  = Pt(4)
    hr = hp.add_run(f'  {title}')
    hr.bold = True
    hr.font.color.rgb = WHITE
    hr.font.size = Pt(10)

    if subtitle:
        sp = doc.add_paragraph()
        sr = sp.add_run(subtitle)
        sr.font.size = Pt(8)
        sr.font.color.rgb = DGRAY
        sr.italic = True
        sp.paragraph_format.space_before = Pt(2)
        sp.paragraph_format.space_after  = Pt(2)

    # Table
    tbl = doc.add_table(rows=1, cols=4)
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    tbl.style = 'Table Grid'

    headers    = ['Username', 'Password', 'Role / Title', 'Position / Notes']
    col_widths = [Cm(3.4), Cm(3.0), Cm(5.5), Cm(8.5)]

    hrow = tbl.rows[0]
    for i, (h, w) in enumerate(zip(headers, col_widths)):
        cell = hrow.cells[i]
        cell.width = w
        set_cell_bg(cell, '1E3A5F')
        p   = cell.paragraphs[0]
        run = p.add_run(h)
        run.bold = True
        run.font.color.rgb = WHITE
        run.font.size = Pt(8.5)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    for j, (name, uname, role, notes) in enumerate(accounts):
        row = tbl.add_row()
        bg  = odd_fill if j % 2 == 0 else even_fill
        values = [uname, PASSWORD, role, notes]
        for i, (val, w) in enumerate(zip(values, col_widths)):
            cell = row.cells[i]
            cell.width = w
            set_cell_bg(cell, bg)
            p   = cell.paragraphs[0]
            run = p.add_run(val)
            run.font.size = Pt(8.5)
            if i == 0:                      # username — coloured + bold
                run.bold = True
                run.font.color.rgb = accent_rgb
            elif i == 1:                    # password — green
                run.bold = True
                run.font.color.rgb = GREEN
            else:
                run.font.color.rgb = DGRAY
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    doc.add_paragraph()


# ── Build document ─────────────────────────────────────────────────────────────
doc = Document()

section = doc.sections[0]
section.top_margin    = Cm(1.8)
section.bottom_margin = Cm(1.8)
section.left_margin   = Cm(1.8)
section.right_margin  = Cm(1.8)

# Title
title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title.add_run('EHR AFRICA — DRY RUN CREDENTIALS')
run.bold = True
run.font.size = Pt(18)
run.font.color.rgb = BLUE

subtitle_p = doc.add_paragraph()
subtitle_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
sr = subtitle_p.add_run('Organised by Clinic Unit — Each section is independent')
sr.font.size = Pt(9)
sr.font.color.rgb = DGRAY
sr.italic = True

doc.add_paragraph()

# System info box
info_tbl = doc.add_table(rows=3, cols=2)
info_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
info_data = [
    ('System URL:',                URL),
    ('Password (all accounts):',   PASSWORD),
    ('Document Date:',             TODAY),
]
for i, (lbl, val) in enumerate(info_data):
    row      = info_tbl.rows[i]
    lbl_cell = row.cells[0]
    val_cell = row.cells[1]
    set_cell_bg(lbl_cell, 'DBEAFE')
    set_cell_bg(val_cell, 'EFF6FF')
    lp = lbl_cell.paragraphs[0]
    lp.add_run(lbl).bold = True
    lp.runs[0].font.color.rgb = BLUE
    lp.runs[0].font.size = Pt(9)
    vp = val_cell.paragraphs[0]
    vp.add_run(val).bold = True
    vp.runs[0].font.size = Pt(9)
    vp.runs[0].font.color.rgb = DGRAY

doc.add_paragraph()

# Confidential notice
note_para = doc.add_paragraph()
note_run = note_para.add_run(
    'CONFIDENTIAL — FOR INTERNAL DRY RUN USE ONLY. '
    'All accounts share the same password above. Change all passwords before going live.'
)
note_run.bold = True
note_run.font.color.rgb = RED
note_run.font.size = Pt(8.5)

doc.add_paragraph()

# How to use note
how_tbl = doc.add_table(rows=1, cols=1)
how_cell = how_tbl.rows[0].cells[0]
set_cell_bg(how_cell, 'FEF9C3')
howp = how_cell.paragraphs[0]
howp.paragraph_format.space_before = Pt(4)
howp.paragraph_format.space_after  = Pt(4)
how_text = (
    'HOW TO USE THIS DOCUMENT:\n'
    '• Each section below is a separate clinic unit — accounts in one unit do NOT appear in another.\n'
    '• To simulate concurrent clinics: open a new browser tab for each user. '
    'Use the session switcher (S1–S5 button) in the top bar to run 5 users in the same browser simultaneously.\n'
    '• Standard OPD: doctor01–05 all serve the standard queue. Assign one doctor per consulting room.\n'
    '• Express, VIP, Insured: dedicated doctors and cashiers for each lane.\n'
    '• Specialty clinics: each specialist manages their own sub-clinic independently.'
)
howr = howp.add_run(how_text)
howr.font.size = Pt(8.5)
howr.font.color.rgb = RGBColor(0x78, 0x35, 0x00)

doc.add_paragraph()

# Sections
for style_key, title_text, subtitle_text, accounts in SECTIONS:
    add_section(doc, style_key, title_text, subtitle_text, accounts)

# Flow reference
flow_hdr_tbl = doc.add_table(rows=1, cols=1)
fh_cell = flow_hdr_tbl.rows[0].cells[0]
set_cell_bg(fh_cell, '065F46')
fhp = fh_cell.paragraphs[0]
fhp.paragraph_format.space_before = Pt(4)
fhp.paragraph_format.space_after  = Pt(4)
fhr = fhp.add_run('  DRY RUN SCENARIO QUICK REFERENCE')
fhr.bold = True
fhr.font.color.rgb = WHITE
fhr.font.size = Pt(10)

flow_tbl = doc.add_table(rows=1, cols=4)
flow_tbl.style = 'Table Grid'
frow = flow_tbl.rows[0]
fhdrs = ['CLINIC UNIT', 'DOCTORS', 'NURSES / SUPPORT', 'CASHIER']
for i, h in enumerate(fhdrs):
    c = frow.cells[i]
    set_cell_bg(c, '1E293B')
    p = c.paragraphs[0]
    r = p.add_run(h)
    r.bold = True
    r.font.color.rgb = WHITE
    r.font.size = Pt(8.5)

scenarios = [
    ('Standard OPD',     'doctor01 – doctor05',         'nurse01–03  |  cnurse01–02',   'cashier01 / cashier02 / cashier03'),
    ('Express Clinic',   'expdoc01, expdoc02',           'expnurse01',                    'cashierexp  (pay FIRST)'),
    ('VIP Clinic',       'vipdoc01, vipdoc02',           'vipnurse01',                    'cashiervip'),
    ('Insured / HMO',    'insdoc01, insdoc02',           'insnurse01  |  billing01',      'cashier01  (co-pay)'),
    ('Specialty',        'retina01, glauco01, cataract01\npaedoph01, lowvis01, optom01–03', '—',      '—'),
    ('Pharmacy / Lab',   '—',                            'pharma01, labtech01\ninvest01, optics01', '—'),
    ('IPD / Theatre',    'anaes01',                      'wardnurse01, theatre01\nadmiss01', '—'),
]
fwidths = [Cm(3.2), Cm(4.8), Cm(5.8), Cm(5.0)]
bgs     = ['EFF6FF', 'F0FDF4', 'F5F3FF', 'FFFBEB']
for row_data in scenarios:
    row = flow_tbl.add_row()
    for i, (val, w) in enumerate(zip(row_data, fwidths)):
        c = row.cells[i]
        c.width = w
        set_cell_bg(c, bgs[i % len(bgs)])
        p = c.paragraphs[0]
        r = p.add_run(val)
        r.font.size = Pt(8.5)
        r.font.color.rgb = DGRAY
        if i == 0:
            r.bold = True

doc.add_paragraph()
foot = doc.add_paragraph()
foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
fr = foot.add_run(f'EHR Africa Dry Run  |  Generated {TODAY}  |  CONFIDENTIAL')
fr.font.size = Pt(7.5)
fr.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)

doc.save(OUT)
import os
print(f'Saved:  {OUT}')
print(f'Size:   {os.path.getsize(OUT) // 1024} KB')
