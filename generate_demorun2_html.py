"""Generate the complete Demo Run 2 credentials sheet (32 accounts)."""

PASSWORD = 'DemoRun2@2026'

ALL_ACCOUNTS = [
    # ── GATEKEEPER ──
    dict(username='dr2_gatekeeper',  first='Gate',        last='Security',            role='gatekeeper',               patient_tier='ALL',      consultation_unit='GENERAL'),
    # ── RECEPTIONISTS ──
    dict(username='dr2_recept_vip',  first='VIP',         last='Receptionist',        role='receptionist',             patient_tier='VIP',      consultation_unit='GENERAL'),
    dict(username='dr2_recept_std',  first='Standard',    last='Receptionist',        role='receptionist',             patient_tier='STANDARD', consultation_unit='GENERAL'),
    dict(username='dr2_recept_exp',  first='Express',     last='Receptionist',        role='receptionist',             patient_tier='EXPRESS',  consultation_unit='GENERAL'),
    # ── MEDICAL RECORDS ──
    dict(username='dr2_med_records', first='Medical',     last='Records Officer',     role='medical_records',          patient_tier='ALL',      consultation_unit='GENERAL'),
    # ── TRIAGE NURSES ──
    dict(username='dr2_nurse_vip',   first='VIP',         last='Triage Nurse',        role='nurse',                    patient_tier='VIP',      consultation_unit='GENERAL'),
    dict(username='dr2_nurse_std',   first='Standard',    last='Triage Nurse',        role='nurse',                    patient_tier='STANDARD', consultation_unit='GENERAL'),
    dict(username='dr2_nurse_exp',   first='Express',     last='Triage Nurse',        role='nurse',                    patient_tier='EXPRESS',  consultation_unit='GENERAL'),
    # ── REFRACTIONISTS ──
    dict(username='dr2_ref_vip1',    first='VIP',         last='Refractionist 1',     role='optometrist',              patient_tier='VIP',      consultation_unit='GENERAL'),
    dict(username='dr2_ref_vip2',    first='VIP',         last='Refractionist 2',     role='optometrist',              patient_tier='VIP',      consultation_unit='GENERAL'),
    dict(username='dr2_ref_std1',    first='Standard',    last='Refractionist 1',     role='optometrist',              patient_tier='STANDARD', consultation_unit='GENERAL'),
    dict(username='dr2_ref_std2',    first='Standard',    last='Refractionist 2',     role='optometrist',              patient_tier='STANDARD', consultation_unit='GENERAL'),
    dict(username='dr2_ref_exp1',    first='Express',     last='Refractionist 1',     role='optometrist',              patient_tier='EXPRESS',  consultation_unit='GENERAL'),
    dict(username='dr2_ref_exp2',    first='Express',     last='Refractionist 2',     role='optometrist',              patient_tier='EXPRESS',  consultation_unit='GENERAL'),
    # ── DOCTORS ──
    dict(username='dr2_dr_vip_ret',  first='VIP',         last='Retina Specialist',   role='ophthalmologist',          patient_tier='VIP',      consultation_unit='VIP_CONSULT'),
    dict(username='dr2_dr_vip_gla',  first='VIP',         last='Glaucoma Specialist', role='ophthalmologist',          patient_tier='VIP',      consultation_unit='VIP_CONSULT'),
    dict(username='dr2_dr_std_ret',  first='Standard',    last='Retina Specialist',   role='ophthalmologist',          patient_tier='STANDARD', consultation_unit='GENERAL'),
    dict(username='dr2_dr_std_gla',  first='Standard',    last='Glaucoma Specialist', role='ophthalmologist',          patient_tier='STANDARD', consultation_unit='GENERAL'),
    dict(username='dr2_dr_exp_ret',  first='Express',     last='Retina Specialist',   role='ophthalmologist',          patient_tier='EXPRESS',  consultation_unit='EXP_CONSULT'),
    dict(username='dr2_dr_exp_gla',  first='Express',     last='Glaucoma Specialist', role='ophthalmologist',          patient_tier='EXPRESS',  consultation_unit='EXP_CONSULT'),
    dict(username='dr2_dr_general',  first='General',     last='Doctor',              role='ophthalmologist',          patient_tier='ALL',      consultation_unit='GENERAL'),
    # ── INVESTIGATION & LAB ──
    dict(username='dr2_invest',      first='Investigation', last='Technician',        role='investigation_technician', patient_tier='ALL',      consultation_unit='GENERAL'),
    dict(username='dr2_labtech',     first='Lab',           last='Technician',        role='lab_technician',           patient_tier='ALL',      consultation_unit='GENERAL'),
    # ── OPTICAL SHOP ──
    dict(username='dr2_opt_cash',    first='Optical',     last='Cashier',             role='cashier',                  patient_tier='ALL',      consultation_unit='GENERAL'),
    dict(username='dr2_opt_disp',    first='Optical',     last='Dispenser',           role='optical_dispenser',        patient_tier='ALL',      consultation_unit='GENERAL'),
    # ── PHARMACY ──
    dict(username='dr2_pharma',      first='Pharmacy',    last='Staff',               role='pharmacist',               patient_tier='ALL',      consultation_unit='GENERAL'),
    # ── CASHIERS ──
    dict(username='dr2_cash_vip',    first='VIP',         last='Cashier',             role='cashier',                  patient_tier='VIP',      consultation_unit='GENERAL'),
    dict(username='dr2_cash_std',    first='Standard',    last='Cashier',             role='cashier',                  patient_tier='STANDARD', consultation_unit='GENERAL'),
    dict(username='dr2_cash_exp',    first='Express',     last='Cashier',             role='cashier',                  patient_tier='EXPRESS',  consultation_unit='GENERAL'),
    dict(username='dr2_chief_cash',  first='Chief',       last='Cashier',             role='chief_cashier',            patient_tier='ALL',      consultation_unit='GENERAL'),
    # ── NURSING SHARED ──
    dict(username='dr2_counsel',     first='Counseling',  last='Nurse',               role='counseling_nurse',         patient_tier='ALL',      consultation_unit='GENERAL'),
    dict(username='dr2_admission',   first='Admission',   last='Nurse',               role='ward_nurse',               patient_tier='ALL',      consultation_unit='GENERAL'),
]

ROLE_LABELS = {
    'gatekeeper':               'Gate Security / Ticket Issuer',
    'receptionist':             'Receptionist',
    'medical_records':          'Medical Records Officer',
    'nurse':                    'OPD Nurse (Triage)',
    'optometrist':              'Optometrist / Refractionist',
    'ophthalmologist':          'Ophthalmologist / Doctor',
    'investigation_technician': 'Investigation Technician',
    'lab_technician':           'Lab Technician',
    'cashier':                  'Cashier',
    'chief_cashier':            'Chief Cashier',
    'optical_dispenser':        'Optical Dispenser',
    'pharmacist':               'Pharmacist',
    'counseling_nurse':         'Surgical Counseling Nurse',
    'ward_nurse':               'Admission / Ward Nurse',
}

ACCESS_NOTES = {
    'gatekeeper':               'Issues entry tickets at the gate; registers walk-in patients',
    'receptionist':             'Registers patients, manages check-in queue for assigned tier',
    'medical_records':          'Searches and retrieves patient records; prints summaries',
    'nurse':                    'Records vitals in triage workstation; routes patients to doctor',
    'optometrist':              'Performs refraction; records VA & IOP in workstation',
    'ophthalmologist':          'Full consultation: prescriptions, investigations, referrals, routing',
    'investigation_technician': 'Receives investigation orders; records results',
    'lab_technician':           'Receives lab orders; enters test results',
    'cashier':                  'Collects patient payments; prints receipts',
    'chief_cashier':            'Opens billing day; verifies cashier shifts; reconciliation',
    'optical_dispenser':        'Dispenses optical products; manages optical shop orders',
    'pharmacist':               'Dispenses medications; manages pharmacy queue',
    'counseling_nurse':         'Pre-surgical counseling; patient education',
    'ward_nurse':               'Admission nurse; manages IPD ward patients',
}

TIER_BADGE = {
    'VIP':      '<span style="background:#7c3aed;color:#fff;padding:2px 9px;border-radius:10px;font-size:9.5px;font-weight:700;white-space:nowrap;">VIP</span>',
    'EXPRESS':  '<span style="background:#d97706;color:#fff;padding:2px 9px;border-radius:10px;font-size:9.5px;font-weight:700;white-space:nowrap;">EXPRESS</span>',
    'STANDARD': '<span style="background:#2563eb;color:#fff;padding:2px 9px;border-radius:10px;font-size:9.5px;font-weight:700;white-space:nowrap;">STANDARD</span>',
    'ALL':      '<span style="background:#374151;color:#fff;padding:2px 9px;border-radius:10px;font-size:9.5px;font-weight:700;white-space:nowrap;">ALL TIERS</span>',
}

CU_LABELS = {
    'VIP_CONSULT':  'VIP Consultation Unit',
    'EXP_CONSULT':  'Express Consultation Unit',
    'GENERAL':      'General / Standard Unit',
}

SECTIONS = [
    ('🔒  GATE & ENTRY',        ['dr2_gatekeeper']),
    ('📋  RECEPTION',           ['dr2_recept_vip', 'dr2_recept_std', 'dr2_recept_exp']),
    ('📁  MEDICAL RECORDS',     ['dr2_med_records']),
    ('🩺  TRIAGE NURSING',      ['dr2_nurse_vip', 'dr2_nurse_std', 'dr2_nurse_exp']),
    ('👁  REFRACTION',          ['dr2_ref_vip1', 'dr2_ref_vip2', 'dr2_ref_std1', 'dr2_ref_std2', 'dr2_ref_exp1', 'dr2_ref_exp2']),
    ('🔬  DOCTORS',             ['dr2_dr_vip_ret', 'dr2_dr_vip_gla', 'dr2_dr_std_ret', 'dr2_dr_std_gla', 'dr2_dr_exp_ret', 'dr2_dr_exp_gla', 'dr2_dr_general']),
    ('🧪  INVESTIGATION & LAB', ['dr2_invest', 'dr2_labtech']),
    ('🕶  OPTICAL SHOP',        ['dr2_opt_cash', 'dr2_opt_disp']),
    ('💊  PHARMACY',            ['dr2_pharma']),
    ('💰  CASHIERS & BILLING',  ['dr2_cash_vip', 'dr2_cash_std', 'dr2_cash_exp', 'dr2_chief_cash']),
    ('🏥  NURSING (SHARED)',    ['dr2_counsel', 'dr2_admission']),
]

by_username = {a['username']: a for a in ALL_ACCOUNTS}

def card(a):
    tier = a.get('patient_tier', 'ALL')
    cu = a.get('consultation_unit', 'GENERAL')
    cu_note = ''
    if a['role'] == 'ophthalmologist':
        cu_note = f'<div style="font-size:9.5px;color:#6b7280;margin-top:1px;">Unit: {CU_LABELS.get(cu, cu)}</div>'
    access = ACCESS_NOTES.get(a['role'], '')
    return f'''<div style="border:1px solid #e5e7eb;border-radius:7px;padding:11px 14px;margin:5px 0;page-break-inside:avoid;background:#fff;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
        <div style="flex:1;">
          <div style="font-size:13px;font-weight:700;color:#111827;">{a['first']} {a['last']}</div>
          <div style="font-size:10.5px;color:#4b5563;">{ROLE_LABELS.get(a['role'], a['role'])}</div>
          {cu_note}
          <div style="font-size:9.5px;color:#9ca3af;margin-top:2px;font-style:italic;">{access}</div>
        </div>
        <div>{TIER_BADGE.get(tier, tier)}</div>
      </div>
      <div style="display:flex;gap:24px;margin-top:9px;padding-top:9px;border-top:1px dashed #e5e7eb;">
        <div>
          <div style="font-size:9px;color:#9ca3af;text-transform:uppercase;letter-spacing:.06em;">Username</div>
          <div style="font-family:'Courier New',monospace;font-size:12.5px;font-weight:700;color:#1d4ed8;">{a['username']}</div>
        </div>
        <div>
          <div style="font-size:9px;color:#9ca3af;text-transform:uppercase;letter-spacing:.06em;">Password</div>
          <div style="font-family:'Courier New',monospace;font-size:12.5px;font-weight:700;color:#1d4ed8;">{PASSWORD}</div>
        </div>
      </div>
    </div>'''

sections_html = ''
for title, usernames in SECTIONS:
    accts = [by_username[u] for u in usernames if u in by_username]
    if not accts:
        continue
    # Two-column grid for large sections
    if len(accts) > 3:
        mid = (len(accts) + 1) // 2
        col1 = ''.join(card(a) for a in accts[:mid])
        col2 = ''.join(card(a) for a in accts[mid:])
        inner = f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:0 12px;">{col1}{col2}</div>'
    else:
        inner = ''.join(card(a) for a in accts)

    sections_html += f'''<div style="margin-bottom:20px;page-break-inside:avoid;">
      <div style="background:#1e3a5f;color:#fff;padding:7px 14px;border-radius:6px 6px 0 0;font-size:11.5px;font-weight:700;letter-spacing:.06em;">{title}</div>
      <div style="border:1px solid #1e3a5f;border-top:none;border-radius:0 0 6px 6px;padding:8px 8px 4px;background:#f9fafb;">{inner}</div>
    </div>'''

html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>EHR Africa — Demo Run 2 Staff Credentials</title>
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:Arial,sans-serif; background:#f3f4f6; padding:20px; font-size:13px; }}
  @media print {{
    body {{ background:#fff !important; padding:6px; }}
    .no-print {{ display:none !important; }}
    @page {{ margin:12mm; size:A4; }}
  }}
</style>
</head>
<body>

<div class="no-print" style="background:#1e3a5f;color:#fff;padding:12px 20px;border-radius:8px;margin-bottom:16px;display:flex;justify-content:space-between;align-items:center;">
  <span style="font-weight:700;font-size:15px;">EHR Africa — Demo Run 2 Credentials</span>
  <button onclick="window.print()" style="background:#fff;color:#1e3a5f;border:none;padding:8px 22px;border-radius:6px;font-weight:700;cursor:pointer;font-size:13px;">🖨 Print / Save PDF</button>
</div>

<div style="text-align:center;margin-bottom:18px;padding-bottom:14px;border-bottom:3px double #1e3a5f;">
  <div style="font-size:22px;font-weight:900;color:#1e3a5f;letter-spacing:.05em;">EHR AFRICA</div>
  <div style="font-size:15px;font-weight:700;color:#374151;margin-top:3px;">DEMO RUN 2 — STAFF LOGIN CREDENTIALS</div>
  <div style="font-size:11px;color:#6b7280;margin-top:5px;">
    System URL: <strong style="color:#1d4ed8;">http://192.168.30.169</strong>
    &nbsp;|&nbsp; Total Accounts: <strong>{len(ALL_ACCOUNTS)}</strong>
    &nbsp;|&nbsp; Test Duration: 2 Months
    &nbsp;|&nbsp; <span style="color:#dc2626;font-weight:600;">CONFIDENTIAL — DO NOT SHARE</span>
  </div>
</div>

<div style="background:#fef3c7;border:1px solid #f59e0b;border-radius:6px;padding:10px 16px;margin-bottom:16px;font-size:11px;color:#78350f;">
  <strong>INSTRUCTIONS FOR ALL STAFF:</strong>&nbsp; Open any browser → go to <strong>http://192.168.30.169</strong> → enter your username &amp; password.
  You will land directly on your personal dashboard. Each account is locked to your department — you will only see patients assigned to your tier.
  <br><strong>Chief Cashier must open the billing day first each morning</strong> before cashiers can collect payments.
</div>

<div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap;font-size:10.5px;font-weight:600;color:#374151;">
  <span>Tier colour codes:</span>
  {TIER_BADGE['VIP']} VIP &nbsp;
  {TIER_BADGE['EXPRESS']} Express / Fast Track &nbsp;
  {TIER_BADGE['STANDARD']} Standard &nbsp;
  {TIER_BADGE['ALL']} Shared / All Tiers
</div>

{sections_html}

<div style="text-align:center;margin-top:16px;padding-top:10px;border-top:1px solid #d1d5db;font-size:9.5px;color:#9ca3af;">
  EHR Africa &nbsp;|&nbsp; IT Department &nbsp;|&nbsp; Demo Run 2 &nbsp;|&nbsp; {len(ALL_ACCOUNTS)} accounts &nbsp;|&nbsp; Confidential
</div>
</body>
</html>'''

out_path = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP\DemoRun2_Credentials.html'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'Credentials sheet written: {out_path}')
print(f'Total: {len(ALL_ACCOUNTS)} accounts')
