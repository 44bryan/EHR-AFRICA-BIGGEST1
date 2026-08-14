"""
Demo account seeder for presentation.
Creates one account per role, all with the same password.
Also exports an Excel file: demo_accounts.xlsx

Run:  python seed_demo_accounts.py
"""
import os, sys, django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from apps.accounts.models import User, UserRole
from apps.departments.models import Department

PASSWORD   = 'Micei@2021@@'
EMAIL_DOMAIN = 'demo.gludd.cm'

# ── Dept lookup helpers ───────────────────────────────────────────────────────
def dept(code):
    try:
        return Department.objects.get(code=code)
    except Department.DoesNotExist:
        return None

# ── Account definitions ───────────────────────────────────────────────────────
ACCOUNTS = [
    # (first_name, last_name, role, username_slug, dept_code, cashier_station, consultation_unit)
    # ── Executive ─────────────────────────────────────────────────────────────
    ('Super',      'Admin',        'super_admin',              'super.admin',        None,          'ALL',      'GENERAL'),
    ('Emmanuel',   'Mbarga',       'ceo',                      'e.mbarga',           None,          'ALL',      'GENERAL'),
    ('Christelle', 'Fouda',        'finance_director',         'c.fouda',            None,          'ALL',      'GENERAL'),
    ('Patrick',    'Atanga',       'admin_director',           'p.atanga',           None,          'ALL',      'GENERAL'),
    # ── Medical Leadership ────────────────────────────────────────────────────
    ('Dr. Samuel', 'Nkeng',        'medical_director',         's.nkeng',            'GEN_OPH',     'ALL',      'GENERAL'),
    # ── Doctors ──────────────────────────────────────────────────────────────
    ('Dr. Alice',  'Betrand',      'ophthalmologist',          'a.betrand',          'GEN_OPH',     'ALL',      'GENERAL'),
    ('Dr. Jean',   'Noa',          'retina_specialist',        'j.noa',              'RETINA',      'ALL',      'GENERAL'),
    ('Dr. Marie',  'Essomba',      'glaucoma_specialist',      'm.essomba',          'GLAUC',       'ALL',      'GENERAL'),
    ('Dr. Paul',   'Tchoua',       'cataract_surgeon',         'p.tchoua',           'CATARACT',    'ALL',      'GENERAL'),
    ('Dr. Grace',  'Nnomo',        'cornea_specialist',        'g.nnomo',            'CORNEA',      'ALL',      'GENERAL'),
    ('Dr. Simon',  'Mvondo',       'pediatric_ophthalmologist','s.mvondo',           'PEDS_OPH',    'ALL',      'GENERAL'),
    ('Dr. Claire', 'Abena',        'oculoplastics_surgeon',    'c.abena',            'OCULOPLASTY', 'ALL',      'GENERAL'),
    ('Dr. Eric',   'Biyong',       'neuro_ophthalmologist',    'e.biyong',           'NEURO_OPH',   'ALL',      'GENERAL'),
    ('Dr. Ruth',   'Owona',        'uveitis_specialist',       'r.owona',            'UVEITIS',     'ALL',      'GENERAL'),
    ('Dr. Felix',  'Manga',        'optometrist',              'f.manga',            'REFRAC',      'ALL',      'GENERAL'),
    ('Dr. Diane',  'Mba',          'low_vision_specialist',    'd.mba',              'LOW_VIS',     'ALL',      'GENERAL'),
    ('Dr. Kevin',  'Simo',         'intern',                   'k.simo',             'GEN_OPH',     'ALL',      'GENERAL'),
    ('Dr. Laure',  'Ndjock',       'pediatric_refractionist',  'l.ndjock',           'PEDS_REFRAC', 'ALL',      'GENERAL'),
    # ── Allied Clinical ───────────────────────────────────────────────────────
    ('Bernard',    'Tsimi',        'anaesthetist',             'b.tsimi',            'CATARACT',    'ALL',      'GENERAL'),
    ('Hélène',    'Nkoa',          'orthoptist',               'h.nkoa',             'PEDS_OPH',    'ALL',      'GENERAL'),
    # ── Nursing ──────────────────────────────────────────────────────────────
    ('Sylvie',     'Etoa',         'nurse',                    's.etoa',             'GEN_OPH',     'ALL',      'GENERAL'),
    ('Josephine',  'Bebe',         'consultation_nurse',       'j.bebe',             'RETINA',      'ALL',      'GENERAL'),
    ('Florence',   'Ngono',        'ward_nurse',               'f.ngono',            None,          'ALL',      'GENERAL'),
    ('Rodrigue',   'Amvam',        'theatre_nurse',            'r.amvam',            'CATARACT',    'ALL',      'GENERAL'),
    ('Angele',     'Minlo',        'counseling_nurse',         'a.minlo',            None,          'ALL',      'GENERAL'),
    ('Martine',    'Onana',        'nurse_director',           'm.onana',            None,          'ALL',      'GENERAL'),
    # ── Technical ────────────────────────────────────────────────────────────
    ('Denis',      'Mengue',       'investigation_technician', 'd.mengue',           'INVEST',      'ALL',      'GENERAL'),
    ('Gaston',     'Eboue',        'lab_technician',           'g.eboue',            'LAB',         'ALL',      'GENERAL'),
    ('Valerie',    'Mballa',       'pharmacist',               'v.mballa',           None,          'ALL',      'GENERAL'),
    ('Thierry',    'Nkolo',        'optical_dispenser',        't.nkolo',            None,          'ALL',      'GENERAL'),
    ('Herve',      'Mekongo',      'cssd_technician',          'h.mekongo',          None,          'ALL',      'GENERAL'),
    # ── Administrative ────────────────────────────────────────────────────────
    ('Cecile',     'Ndongo',       'receptionist',             'c.ndongo',           None,          'ALL',      'GENERAL'),
    ('Blaise',     'Zoua',         'admission_officer',        'b.zoua',             None,          'ALL',      'GENERAL'),
    ('Raissa',     'Etoundi',      'cashier',                  'r.etoundi',          None,          'STANDARD', 'GENERAL'),
    ('Ornella',    'Ndoumbe',      'cashier',                  'o.ndoumbe',          None,          'VIP',      'GENERAL'),
    ('Leopold',    'Mfou',         'chief_cashier',            'l.mfou',             None,          'ALL',      'GENERAL'),
    ('Nadege',     'Ekwalla',      'accountant',               'n.ekwalla',          None,          'ALL',      'GENERAL'),
    ('Josue',      'Nkemba',       'senior_accountant',        'j.nkemba',           None,          'ALL',      'GENERAL'),
    ('Bertrand',   'Amougou',      'billing_officer',          'b.amougou',          None,          'ALL',      'GENERAL'),
    ('Serge',      'Nlend',        'gatekeeper',               's.nlend',            None,          'ALL',      'GENERAL'),
    ('Lydie',      'Binyom',       'medical_records',          'l.binyom',           None,          'ALL',      'GENERAL'),
    ('Sandra',     'Mekuate',      'quality_officer',          's.mekuate',          None,          'ALL',      'GENERAL'),
    ('IT',         'Administrator','admin',                    'it.admin',           None,          'ALL',      'GENERAL'),
]

created = []
skipped = []

for first, last, role, slug, dept_code, c_station, c_unit in ACCOUNTS:
    email    = f"{slug}@{EMAIL_DOMAIN}"
    username = slug
    emp_id   = f"EMP{len(created)+len(skipped)+1:03d}"

    if User.objects.filter(email=email).exists():
        skipped.append(email)
        print(f"  SKIP  {email} (already exists)")
        continue

    # Make sure employee_id is unique
    while User.objects.filter(employee_id=emp_id).exists():
        emp_id = emp_id[:-3] + f"{int(emp_id[-3:])+100:03d}"

    u = User(
        first_name          = first,
        last_name           = last,
        email               = email,
        username            = username,
        employee_id         = emp_id,
        role                = role,
        cashier_station     = c_station,
        consultation_unit   = c_unit,
        must_change_password= False,   # disabled for demo
        is_active           = True,
    )
    if dept_code:
        u.department = dept(dept_code)

    # Super Admin gets staff + superuser flags
    if role == 'super_admin':
        u.is_staff      = True
        u.is_superuser  = True

    u.set_password(PASSWORD)
    u.save()

    full_name = f"{first} {last}"
    created.append({
        'name':       full_name,
        'email':      email,
        'username':   username,
        'password':   PASSWORD,
        'role':       str(dict(UserRole.choices).get(role, role)),
        'dept':       dept_code or '—',
        'emp_id':     emp_id,
    })
    print(f"  OK    {email}  [{role}]")

print(f"\nCreated {len(created)} accounts, skipped {len(skipped)}.")

# ── Excel export ─────────────────────────────────────────────────────────────
import openpyxl
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, GradientFill
)
from openpyxl.utils import get_column_letter

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Demo Accounts"

# ── Header banner ─────────────────────────────────────────────────────────────
ws.merge_cells('A1:H1')
banner = ws['A1']
banner.value = "GLUDD EYE HOSPITAL — DEMO ACCOUNTS FOR PRESENTATION"
banner.font      = Font(name='Calibri', bold=True, size=14, color='FFFFFF')
banner.fill      = PatternFill('solid', fgColor='1D4ED8')
banner.alignment = Alignment(horizontal='center', vertical='center')
ws.row_dimensions[1].height = 32

ws.merge_cells('A2:H2')
sub = ws['A2']
sub.value = f"All accounts use the same password: {PASSWORD}   •   For authorised demo use only."
sub.font      = Font(name='Calibri', italic=True, size=10, color='374151')
sub.fill      = PatternFill('solid', fgColor='DBEAFE')
sub.alignment = Alignment(horizontal='center', vertical='center')
ws.row_dimensions[2].height = 20

# ── Column headers ────────────────────────────────────────────────────────────
headers = ['#', 'Full Name', 'Login Email', 'Username', 'Password', 'Role', 'Department', 'Emp. ID']
col_widths = [5, 24, 34, 22, 18, 32, 22, 12]

hdr_fill   = PatternFill('solid', fgColor='1E3A5F')
hdr_font   = Font(name='Calibri', bold=True, size=10, color='FFFFFF')
hdr_border = Border(
    bottom=Side(style='medium', color='1D4ED8'),
    left=Side(style='thin', color='CCCCCC'),
    right=Side(style='thin', color='CCCCCC'),
)

for col_idx, (h, w) in enumerate(zip(headers, col_widths), start=1):
    cell = ws.cell(row=3, column=col_idx, value=h)
    cell.font      = hdr_font
    cell.fill      = hdr_fill
    cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    cell.border    = hdr_border
    ws.column_dimensions[get_column_letter(col_idx)].width = w

ws.row_dimensions[3].height = 22

# ── Data rows ─────────────────────────────────────────────────────────────────
thin_border = Border(
    left=Side(style='thin', color='E5E7EB'),
    right=Side(style='thin', color='E5E7EB'),
    bottom=Side(style='thin', color='E5E7EB'),
)

# Group colours by section
SECTION_COLORS = {
    'Executive / Leadership':     'EFF6FF',
    'Medical Direction':          'F0FDF4',
    'Doctors / Specialists':      'FAFAFA',
    'Allied Clinical':            'FFF7ED',
    'Nursing':                    'FFF1F2',
    'Technical / Paramedical':    'F5F3FF',
    'Administrative / Finance':   'FFFBEB',
}

ROLE_SECTIONS = {
    'Super Administrator':                          'Executive / Leadership',
    'Chief Executive Officer':                      'Executive / Leadership',
    'Finance Director':                             'Executive / Leadership',
    'Administrative Director':                      'Executive / Leadership',
    'Medical Director':                             'Medical Direction',
    'Ophthalmologist (General)':                    'Doctors / Specialists',
    'Retina Specialist':                            'Doctors / Specialists',
    'Glaucoma Specialist':                          'Doctors / Specialists',
    'Cataract Surgeon':                             'Doctors / Specialists',
    'Cornea Specialist':                            'Doctors / Specialists',
    'Pediatric Ophthalmologist':                    'Doctors / Specialists',
    'Oculoplastics Surgeon':                        'Doctors / Specialists',
    'Neuro-ophthalmologist':                        'Doctors / Specialists',
    'Uveitis Specialist':                           'Doctors / Specialists',
    'Optometrist / Refractionist':                  'Doctors / Specialists',
    'Low Vision Specialist / Rehabilitation':       'Doctors / Specialists',
    'Intern / House Officer':                       'Doctors / Specialists',
    'Pediatric Refractionist / Orthoptist':         'Doctors / Specialists',
    'Anaesthetist':                                 'Allied Clinical',
    'Orthoptist / Binocular Vision Therapist':      'Allied Clinical',
    'OPD Nurse (Triage)':                           'Nursing',
    'Consultation Room Nurse':                      'Nursing',
    'Ward Nurse (IPD)':                             'Nursing',
    'Theatre Nurse':                                'Nursing',
    'Surgical Counseling Nurse':                    'Nursing',
    'Director of Nursing / Head Nurse':             'Nursing',
    'Investigation Technician':                     'Technical / Paramedical',
    'Lab Technician':                               'Technical / Paramedical',
    'Pharmacist':                                   'Technical / Paramedical',
    'Optical Dispenser':                            'Technical / Paramedical',
    'CSSD Technician (Sterilization)':              'Technical / Paramedical',
    'Receptionist':                                 'Administrative / Finance',
    'Admission Officer':                            'Administrative / Finance',
    'Cashier':                                      'Administrative / Finance',
    'Chief Cashier':                                'Administrative / Finance',
    'Accountant':                                   'Administrative / Finance',
    'Senior Accountant':                            'Administrative / Finance',
    'Billing Officer':                              'Administrative / Finance',
    'Gate Security / Ticket Issuer':                'Administrative / Finance',
    'Medical Records Officer':                      'Administrative / Finance',
    'Quality / JCI Compliance Officer':             'Administrative / Finance',
    'System Administrator':                         'Administrative / Finance',
}

row_num = 4
for idx, acc in enumerate(created, start=1):
    section  = ROLE_SECTIONS.get(acc['role'], 'Administrative / Finance')
    bg_color = SECTION_COLORS.get(section, 'FFFFFF')
    row_fill = PatternFill('solid', fgColor=bg_color)
    # Alternate slightly darker shade every other row
    if idx % 2 == 0:
        # Darken by ~5% — just use the base colour (good enough for print)
        row_fill = PatternFill('solid', fgColor=bg_color)

    values = [idx, acc['name'], acc['email'], acc['username'], acc['password'], acc['role'], acc['dept'], acc['emp_id']]
    for col_idx, val in enumerate(values, start=1):
        cell = ws.cell(row=row_num, column=col_idx, value=val)
        cell.fill      = row_fill
        cell.border    = thin_border
        cell.alignment = Alignment(vertical='center', wrap_text=(col_idx in (6, 7)))
        if col_idx == 1:
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.font = Font(name='Calibri', bold=True, size=9)
        elif col_idx == 5:
            # Password column — bold red
            cell.font = Font(name='Courier New', bold=True, size=10, color='DC2626')
        elif col_idx == 3:
            # Email — blue underline feel
            cell.font = Font(name='Calibri', size=9, color='1D4ED8')
        else:
            cell.font = Font(name='Calibri', size=9)
    ws.row_dimensions[row_num].height = 18
    row_num += 1

# ── Footer ────────────────────────────────────────────────────────────────────
ws.merge_cells(f'A{row_num}:H{row_num}')
footer = ws.cell(row=row_num, column=1, value=f"CONFIDENTIAL — {len(created)} accounts  •  All passwords: {PASSWORD}  •  Disable must_change_password = True for all demo accounts")
footer.font      = Font(name='Calibri', italic=True, size=9, color='6B7280')
footer.fill      = PatternFill('solid', fgColor='F9FAFB')
footer.alignment = Alignment(horizontal='center')
ws.row_dimensions[row_num].height = 16

# Freeze header rows
ws.freeze_panes = 'A4'

out_path = os.path.join(os.path.dirname(__file__), 'demo_accounts.xlsx')
wb.save(out_path)
print(f"\nExcel file saved → {out_path}")
