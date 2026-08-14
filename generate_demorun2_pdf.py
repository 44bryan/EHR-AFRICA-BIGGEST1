"""Generate professional Demo Run 2 participant briefing PDF."""

from datetime import date

TODAY = date.today().strftime("%d %B %Y")
PASSWORD = "DemoRun2@2026"
URL = "http://192.168.30.169"

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>EHR Africa — Demo Run 2 Participant Briefing</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: Arial, sans-serif;
    font-size: 10pt;
    color: #1a1a2e;
    background: #fff;
    padding: 0;
  }}

  /* ── Print settings ── */
  @media print {{
    body {{ padding: 0; background: #fff; }}
    .no-print {{ display: none !important; }}
    .page-break {{ page-break-before: always; }}
    @page {{ margin: 14mm 12mm; size: A4; }}
    tr {{ page-break-inside: avoid; }}
    .section-block {{ page-break-inside: avoid; }}
  }}

  /* ── Screen preview wrapper ── */
  .page-wrapper {{
    max-width: 210mm;
    margin: 0 auto;
    padding: 14mm 12mm;
    background: #fff;
  }}

  /* ── Print button ── */
  .print-bar {{
    background: #1e3a5f;
    color: #fff;
    padding: 10px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: sticky;
    top: 0;
    z-index: 99;
  }}
  .print-bar button {{
    background: #f59e0b;
    color: #1a1a2e;
    border: none;
    padding: 7px 22px;
    border-radius: 5px;
    font-weight: 800;
    font-size: 11pt;
    cursor: pointer;
  }}

  /* ── Header ── */
  .doc-header {{
    border-bottom: 4px solid #1e3a5f;
    padding-bottom: 10px;
    margin-bottom: 14px;
  }}
  .doc-header-top {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
  }}
  .hospital-name {{
    font-size: 18pt;
    font-weight: 900;
    color: #1e3a5f;
    letter-spacing: .04em;
    line-height: 1.1;
  }}
  .hospital-sub {{
    font-size: 9pt;
    color: #4b5563;
    margin-top: 2px;
  }}
  .doc-meta {{
    text-align: right;
    font-size: 8.5pt;
    color: #4b5563;
    line-height: 1.7;
  }}
  .doc-meta strong {{ color: #1e3a5f; }}
  .doc-title {{
    margin-top: 10px;
    font-size: 15pt;
    font-weight: 900;
    color: #1e3a5f;
    text-transform: uppercase;
    letter-spacing: .06em;
  }}
  .doc-subtitle {{
    font-size: 9pt;
    color: #6b7280;
    margin-top: 2px;
  }}

  /* ── Notice boxes ── */
  .notice {{
    border-radius: 5px;
    padding: 8px 13px;
    font-size: 8.5pt;
    margin-bottom: 10px;
    line-height: 1.55;
  }}
  .notice-yellow {{ background: #fffbeb; border-left: 4px solid #f59e0b; color: #78350f; }}
  .notice-blue   {{ background: #eff6ff; border-left: 4px solid #2563eb; color: #1e3a5f; }}
  .notice-red    {{ background: #fef2f2; border-left: 4px solid #dc2626; color: #7f1d1d; }}

  /* ── Section headings ── */
  .section-block {{ margin-bottom: 16px; }}
  .section-heading {{
    display: flex;
    align-items: center;
    gap: 8px;
    background: #1e3a5f;
    color: #fff;
    padding: 6px 12px;
    border-radius: 5px 5px 0 0;
    font-size: 9.5pt;
    font-weight: 800;
    letter-spacing: .07em;
    text-transform: uppercase;
  }}
  .section-heading .tier-pill {{
    font-size: 7.5pt;
    font-weight: 700;
    padding: 1px 8px;
    border-radius: 8px;
    margin-left: auto;
  }}
  .pill-vip      {{ background: #7c3aed; color: #fff; }}
  .pill-express  {{ background: #d97706; color: #fff; }}
  .pill-standard {{ background: #2563eb; color: #fff; }}
  .pill-all      {{ background: #374151; color: #fff; }}
  .pill-shared   {{ background: #059669; color: #fff; }}

  /* ── Credential tables ── */
  .cred-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 8.5pt;
    border: 1px solid #1e3a5f;
    border-top: none;
    border-radius: 0 0 5px 5px;
    overflow: hidden;
    margin-bottom: 0;
  }}
  .cred-table thead tr {{
    background: #dbeafe;
    color: #1e3a5f;
    font-weight: 700;
  }}
  .cred-table th,
  .cred-table td {{
    padding: 5px 9px;
    border-bottom: 1px solid #e5e7eb;
    border-right: 1px solid #e5e7eb;
    vertical-align: top;
  }}
  .cred-table th:last-child,
  .cred-table td:last-child {{ border-right: none; }}
  .cred-table tbody tr:last-child td {{ border-bottom: none; }}
  .cred-table tbody tr:nth-child(even) {{ background: #f9fafb; }}
  .cred-table code {{
    font-family: "Courier New", monospace;
    font-weight: 700;
    color: #1d4ed8;
    font-size: 9pt;
  }}
  .tier-dot {{
    display: inline-block;
    width: 9px; height: 9px;
    border-radius: 50%;
    margin-right: 4px;
    vertical-align: middle;
  }}
  .dot-vip      {{ background: #7c3aed; }}
  .dot-express  {{ background: #d97706; }}
  .dot-standard {{ background: #2563eb; }}
  .dot-all      {{ background: #374151; }}

  /* ── Quick reference table ── */
  .qr-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 8pt;
    margin-top: 6px;
  }}
  .qr-table th {{
    background: #1e3a5f;
    color: #fff;
    padding: 5px 8px;
    text-align: left;
    font-size: 8pt;
  }}
  .qr-table td {{
    padding: 5px 8px;
    border-bottom: 1px solid #e5e7eb;
    border-right: 1px solid #e5e7eb;
    vertical-align: top;
  }}
  .qr-table td:last-child {{ border-right: none; }}
  .qr-table tr:nth-child(even) {{ background: #f9fafb; }}

  /* ── Summary boxes ── */
  .summary-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin-bottom: 12px;
  }}
  .summary-box {{
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    padding: 8px 10px;
    text-align: center;
  }}
  .summary-box .num {{
    font-size: 22pt;
    font-weight: 900;
    line-height: 1;
  }}
  .summary-box .lbl {{
    font-size: 7.5pt;
    color: #6b7280;
    margin-top: 2px;
  }}

  /* ── Footer ── */
  .doc-footer {{
    border-top: 2px solid #1e3a5f;
    margin-top: 20px;
    padding-top: 8px;
    display: flex;
    justify-content: space-between;
    font-size: 7.5pt;
    color: #9ca3af;
  }}

  h3 {{ font-size: 10pt; color: #1e3a5f; margin: 12px 0 6px; }}
</style>
</head>
<body>

<!-- Print bar (screen only) -->
<div class="print-bar no-print">
  <span style="font-weight:700;font-size:13pt;">EHR Africa — Demo Run 2 Briefing Document</span>
  <button onclick="window.print()">🖨 Print / Save as PDF</button>
</div>

<div class="page-wrapper">

<!-- ══════════════════════════════════════════════════════════
     HEADER
══════════════════════════════════════════════════════════ -->
<div class="doc-header">
  <div class="doc-header-top">
    <div>
      <div class="hospital-name">EHR AFRICA</div>
      <div class="hospital-sub">Electronic Health Records System &nbsp;|&nbsp; Ophthalmology Division</div>
    </div>
    <div class="doc-meta">
      <div><strong>Document Date:</strong> {TODAY}</div>
      <div><strong>System URL:</strong> {URL}</div>
      <div><strong>Password (all accounts):</strong> <code style="font-family:monospace;font-weight:700;color:#1e3a5f;">{PASSWORD}</code></div>
      <div><strong>Classification:</strong> <span style="color:#dc2626;font-weight:700;">CONFIDENTIAL</span></div>
    </div>
  </div>
  <div class="doc-title">Demo Run 2 — Participant Briefing &amp; Credentials</div>
  <div class="doc-subtitle">Full-Scale Two-Month System Evaluation &nbsp;|&nbsp; All Service Tiers &nbsp;|&nbsp; 32 Staff Accounts</div>
</div>

<!-- ══════════════════════════════════════════════════════════
     EXECUTIVE SUMMARY
══════════════════════════════════════════════════════════ -->
<div class="notice notice-blue">
  <strong>PURPOSE OF THIS DOCUMENT:</strong> Following a successful first dry run with a smaller group, the management team has approved a full-scale two-month evaluation of the EHR Africa system. This document is the official participant briefing — it assigns roles, provides login credentials, and outlines operating instructions for every staff member involved in Demo Run 2.
</div>

<div class="summary-grid">
  <div class="summary-box">
    <div class="num" style="color:#1e3a5f;">2</div>
    <div class="lbl">Month Test Duration</div>
  </div>
  <div class="summary-box">
    <div class="num" style="color:#7c3aed;">3</div>
    <div class="lbl">Service Tiers Covered</div>
  </div>
  <div class="summary-box">
    <div class="num" style="color:#059669;">32</div>
    <div class="lbl">Staff Accounts Issued</div>
  </div>
  <div class="summary-box">
    <div class="num" style="color:#d97706;">11</div>
    <div class="lbl">Departments Involved</div>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════════
     OPERATING INSTRUCTIONS
══════════════════════════════════════════════════════════ -->
<h3>📋 Operating Instructions — Read Before First Login</h3>

<div class="notice notice-yellow">
  <strong>HOW TO LOG IN:</strong> Open any web browser (Chrome recommended) on any computer connected to the hospital network.
  Navigate to <strong>{URL}</strong>. Enter your username and the shared password <strong>{PASSWORD}</strong> shown at the top of this document.
  You will be taken directly to your personal dashboard — only your department's queues and tools will be visible.
</div>

<div class="notice notice-red">
  <strong>⚠ CRITICAL — CHIEF CASHIER MUST ACT FIRST EACH MORNING:</strong> Before any cashier can collect patient payments, the Chief Cashier
  (<code style="font-family:monospace;">dr2_chief_cash</code>) must log in and open the billing day via the Billing menu.
  If this step is skipped, all cashiers will receive an error when processing payments. The Chief Cashier should be the first person to log in every morning.
</div>

<div style="font-size:8.5pt; line-height:1.65; margin-bottom:12px;">
  <strong>Key rules for the test period:</strong>
  <ol style="margin-left:18px; margin-top:4px;">
    <li>Each account is locked to its assigned service tier — VIP staff will only see VIP patients, Standard staff see Standard patients, etc.</li>
    <li>Do <strong>not</strong> share login credentials with other staff. Each person must use only their assigned account.</li>
    <li>To simulate concurrent users on one computer, open a new browser tab in <em>Incognito / Private mode</em> for each additional user.</li>
    <li>The system auto-refreshes queues in real time — no manual page refresh is needed.</li>
    <li>Patient prescriptions, lab reports, and investigation results generate printable PDFs directly from the system.</li>
    <li>Report any errors or unexpected behaviour immediately to the IT team. <strong>Do not attempt to work around errors.</strong></li>
  </ol>
</div>

<!-- ══════════════════════════════════════════════════════════
     TIER COLOUR LEGEND
══════════════════════════════════════════════════════════ -->
<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:8pt;margin-bottom:14px;padding:7px 12px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:5px;">
  <strong style="color:#1e3a5f;">Tier colour codes used in this document:</strong>
  <span><span class="tier-dot dot-vip"></span><strong>VIP</strong> — Premium lane, priority service</span>
  <span><span class="tier-dot dot-express"></span><strong>EXPRESS</strong> — Fast-track / speed lane</span>
  <span><span class="tier-dot dot-standard"></span><strong>STANDARD</strong> — Regular OPD patients</span>
  <span><span class="tier-dot dot-all"></span><strong>ALL TIERS</strong> — Shared departments serving every tier</span>
</div>

<!-- ══════════════════════════════════════════════════════════
     SECTION 1: GATE & ENTRY
══════════════════════════════════════════════════════════ -->
<div class="section-block">
  <div class="section-heading">
    🔒 Section 1 &nbsp;·&nbsp; Gate &amp; Entry
    <span class="tier-pill pill-all">ALL TIERS</span>
  </div>
  <table class="cred-table">
    <thead><tr><th style="width:22%;">Username</th><th style="width:18%;">Password</th><th style="width:28%;">Role / Title</th><th>Position &amp; Notes</th></tr></thead>
    <tbody>
      <tr>
        <td><code>dr2_gatekeeper</code></td>
        <td><code>{PASSWORD}</code></td>
        <td>Gate Security / Ticket Issuer</td>
        <td>Main hospital gate. Screens arrivals and issues entry tickets. First staff contact for every patient.</td>
      </tr>
    </tbody>
  </table>
</div>

<!-- ══════════════════════════════════════════════════════════
     SECTION 2: RECEPTION & MEDICAL RECORDS
══════════════════════════════════════════════════════════ -->
<div class="section-block">
  <div class="section-heading">
    📋 Section 2 &nbsp;·&nbsp; Reception &amp; Medical Records
    <span class="tier-pill pill-vip">VIP</span>
    <span class="tier-pill pill-express" style="margin-left:4px;">EXPRESS</span>
    <span class="tier-pill pill-standard" style="margin-left:4px;">STANDARD</span>
  </div>
  <table class="cred-table">
    <thead><tr><th style="width:22%;">Username</th><th style="width:18%;">Password</th><th style="width:28%;">Role / Title</th><th>Position &amp; Notes</th></tr></thead>
    <tbody>
      <tr>
        <td><code>dr2_recept_vip</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-vip"></span>VIP Receptionist</td>
        <td>Registers and checks in <strong>VIP-tier</strong> patients only. Manages VIP appointment queue.</td>
      </tr>
      <tr>
        <td><code>dr2_recept_std</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-standard"></span>Standard Receptionist</td>
        <td>Registers and checks in <strong>Standard</strong> patients. Main OPD reception desk.</td>
      </tr>
      <tr>
        <td><code>dr2_recept_exp</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-express"></span>Express Receptionist</td>
        <td>Registers and checks in <strong>Express / Fast-Track</strong> patients. Speed lane desk.</td>
      </tr>
      <tr>
        <td><code>dr2_med_records</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-all"></span>Medical Records Officer</td>
        <td>Retrieves patient files, updates demographics, prints summaries. Serves all tiers.</td>
      </tr>
    </tbody>
  </table>
</div>

<!-- ══════════════════════════════════════════════════════════
     SECTION 3: TRIAGE NURSING
══════════════════════════════════════════════════════════ -->
<div class="section-block">
  <div class="section-heading">
    🩺 Section 3 &nbsp;·&nbsp; Triage Nursing
    <span class="tier-pill pill-vip">VIP</span>
    <span class="tier-pill pill-express" style="margin-left:4px;">EXPRESS</span>
    <span class="tier-pill pill-standard" style="margin-left:4px;">STANDARD</span>
  </div>
  <table class="cred-table">
    <thead><tr><th style="width:22%;">Username</th><th style="width:18%;">Password</th><th style="width:28%;">Role / Title</th><th>Position &amp; Notes</th></tr></thead>
    <tbody>
      <tr>
        <td><code>dr2_nurse_vip</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-vip"></span>VIP Triage Nurse</td>
        <td>Records vitals (BP, weight, temp, VA, IOP) for VIP patients. Routes to VIP consulting room.</td>
      </tr>
      <tr>
        <td><code>dr2_nurse_std</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-standard"></span>Standard Triage Nurse</td>
        <td>Records vitals for Standard OPD patients. Routes to standard consulting rooms.</td>
      </tr>
      <tr>
        <td><code>dr2_nurse_exp</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-express"></span>Express Triage Nurse</td>
        <td>Records vitals for Express lane patients. Priority routing — minimal wait time.</td>
      </tr>
    </tbody>
  </table>
</div>

<!-- ══════════════════════════════════════════════════════════
     SECTION 4: REFRACTION
══════════════════════════════════════════════════════════ -->
<div class="section-block">
  <div class="section-heading">
    👁 Section 4 &nbsp;·&nbsp; Refraction Unit
    <span class="tier-pill pill-vip">VIP ×2</span>
    <span class="tier-pill pill-express" style="margin-left:4px;">EXPRESS ×2</span>
    <span class="tier-pill pill-standard" style="margin-left:4px;">STANDARD ×2</span>
  </div>
  <table class="cred-table">
    <thead><tr><th style="width:22%;">Username</th><th style="width:18%;">Password</th><th style="width:28%;">Role / Title</th><th>Position &amp; Notes</th></tr></thead>
    <tbody>
      <tr><td><code>dr2_ref_vip1</code></td><td><code>{PASSWORD}</code></td><td><span class="tier-dot dot-vip"></span>VIP Refractionist 1</td><td>Refraction room — VIP patients. Records VA &amp; full refraction data.</td></tr>
      <tr><td><code>dr2_ref_vip2</code></td><td><code>{PASSWORD}</code></td><td><span class="tier-dot dot-vip"></span>VIP Refractionist 2</td><td>Refraction room — VIP patients. Backup / concurrent sessions.</td></tr>
      <tr><td><code>dr2_ref_std1</code></td><td><code>{PASSWORD}</code></td><td><span class="tier-dot dot-standard"></span>Standard Refractionist 1</td><td>Refraction room — Standard patients. Primary unit.</td></tr>
      <tr><td><code>dr2_ref_std2</code></td><td><code>{PASSWORD}</code></td><td><span class="tier-dot dot-standard"></span>Standard Refractionist 2</td><td>Refraction room — Standard patients. Overflow / concurrent.</td></tr>
      <tr><td><code>dr2_ref_exp1</code></td><td><code>{PASSWORD}</code></td><td><span class="tier-dot dot-express"></span>Express Refractionist 1</td><td>Refraction room — Express patients. Fast-track refraction.</td></tr>
      <tr><td><code>dr2_ref_exp2</code></td><td><code>{PASSWORD}</code></td><td><span class="tier-dot dot-express"></span>Express Refractionist 2</td><td>Refraction room — Express patients. Backup / concurrent.</td></tr>
    </tbody>
  </table>
</div>

<!-- PAGE BREAK -->
<div class="page-break"></div>

<!-- ══════════════════════════════════════════════════════════
     SECTION 5: DOCTORS / CONSULTANTS
══════════════════════════════════════════════════════════ -->
<div class="section-block">
  <div class="section-heading">
    🔬 Section 5 &nbsp;·&nbsp; Doctors &amp; Consultants
    <span class="tier-pill pill-vip">VIP ×2</span>
    <span class="tier-pill pill-express" style="margin-left:4px;">EXPRESS ×2</span>
    <span class="tier-pill pill-standard" style="margin-left:4px;">STANDARD ×2</span>
    <span class="tier-pill pill-all" style="margin-left:4px;">GENERAL ×1</span>
  </div>
  <table class="cred-table">
    <thead><tr><th style="width:22%;">Username</th><th style="width:18%;">Password</th><th style="width:36%;">Role / Specialty</th><th>Consultation Unit</th></tr></thead>
    <tbody>
      <tr>
        <td><code>dr2_dr_vip_ret</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-vip"></span>Ophthalmologist — Retina Specialist</td>
        <td>VIP Consultation Unit. Manages retinal disease cases for VIP patients.</td>
      </tr>
      <tr>
        <td><code>dr2_dr_vip_gla</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-vip"></span>Ophthalmologist — Glaucoma Specialist</td>
        <td>VIP Consultation Unit. Manages glaucoma cases for VIP patients.</td>
      </tr>
      <tr>
        <td><code>dr2_dr_std_ret</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-standard"></span>Ophthalmologist — Retina Specialist</td>
        <td>Standard OPD Unit. Retinal disease consultations for Standard patients.</td>
      </tr>
      <tr>
        <td><code>dr2_dr_std_gla</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-standard"></span>Ophthalmologist — Glaucoma Specialist</td>
        <td>Standard OPD Unit. Glaucoma consultations for Standard patients.</td>
      </tr>
      <tr>
        <td><code>dr2_dr_exp_ret</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-express"></span>Ophthalmologist — Retina Specialist</td>
        <td>Express Consultation Unit. Retinal consultations — fast-track lane.</td>
      </tr>
      <tr>
        <td><code>dr2_dr_exp_gla</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-express"></span>Ophthalmologist — Glaucoma Specialist</td>
        <td>Express Consultation Unit. Glaucoma — fast-track lane.</td>
      </tr>
      <tr style="background:#f0fdf4;">
        <td><code>dr2_dr_general</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-all"></span>Ophthalmologist — General Doctor</td>
        <td>General / cross-tier. Sees patients across all tiers. Overflow &amp; general eye complaints.</td>
      </tr>
    </tbody>
  </table>
  <div class="notice notice-blue" style="border-radius:0 0 5px 5px; margin-top:0; font-size:8pt;">
    <strong>Doctors can:</strong> write prescriptions, order investigations &amp; lab tests, record VA/IOP, refer patients to other departments, and route patients to pharmacy or cashier — all directly from their workstation.
  </div>
</div>

<!-- ══════════════════════════════════════════════════════════
     SECTION 6: INVESTIGATION & LABORATORY
══════════════════════════════════════════════════════════ -->
<div class="section-block">
  <div class="section-heading">
    🧪 Section 6 &nbsp;·&nbsp; Investigation &amp; Laboratory
    <span class="tier-pill pill-all">ALL TIERS</span>
  </div>
  <table class="cred-table">
    <thead><tr><th style="width:22%;">Username</th><th style="width:18%;">Password</th><th style="width:28%;">Role / Title</th><th>Position &amp; Notes</th></tr></thead>
    <tbody>
      <tr>
        <td><code>dr2_invest</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-all"></span>Investigation Technician</td>
        <td>Receives investigation orders from doctors (imaging, OCT, visual fields, etc.). Records and uploads results. Serves patients from all tiers.</td>
      </tr>
      <tr>
        <td><code>dr2_labtech</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-all"></span>Lab Technician</td>
        <td>Receives laboratory orders. Enters test results (haematology, biochemistry, microbiology). Generates lab PDF reports.</td>
      </tr>
    </tbody>
  </table>
</div>

<!-- ══════════════════════════════════════════════════════════
     SECTION 7: OPTICAL SHOP
══════════════════════════════════════════════════════════ -->
<div class="section-block">
  <div class="section-heading">
    🕶 Section 7 &nbsp;·&nbsp; Optical Shop
    <span class="tier-pill pill-all">ALL TIERS</span>
  </div>
  <table class="cred-table">
    <thead><tr><th style="width:22%;">Username</th><th style="width:18%;">Password</th><th style="width:28%;">Role / Title</th><th>Position &amp; Notes</th></tr></thead>
    <tbody>
      <tr>
        <td><code>dr2_opt_cash</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-all"></span>Optical Shop Cashier</td>
        <td>Processes payment for optical products (spectacles, lenses, accessories). Issues receipts.</td>
      </tr>
      <tr>
        <td><code>dr2_opt_disp</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-all"></span>Optical Dispenser</td>
        <td>Receives optical prescriptions from doctors. Dispenses spectacles and contact lenses. Manages optical orders queue.</td>
      </tr>
    </tbody>
  </table>
</div>

<!-- ══════════════════════════════════════════════════════════
     SECTION 8: PHARMACY
══════════════════════════════════════════════════════════ -->
<div class="section-block">
  <div class="section-heading">
    💊 Section 8 &nbsp;·&nbsp; Pharmacy
    <span class="tier-pill pill-all">ALL TIERS</span>
  </div>
  <table class="cred-table">
    <thead><tr><th style="width:22%;">Username</th><th style="width:18%;">Password</th><th style="width:28%;">Role / Title</th><th>Position &amp; Notes</th></tr></thead>
    <tbody>
      <tr>
        <td><code>dr2_pharma</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-all"></span>Pharmacist</td>
        <td>Views and processes drug prescriptions from all tiers. Marks medications as dispensed. Manages pharmacy queue and drug inventory.</td>
      </tr>
    </tbody>
  </table>
</div>

<!-- ══════════════════════════════════════════════════════════
     SECTION 9: CASHIERS & BILLING
══════════════════════════════════════════════════════════ -->
<div class="section-block">
  <div class="section-heading">
    💰 Section 9 &nbsp;·&nbsp; Cashiers &amp; Billing
    <span class="tier-pill pill-vip">VIP</span>
    <span class="tier-pill pill-express" style="margin-left:4px;">EXPRESS</span>
    <span class="tier-pill pill-standard" style="margin-left:4px;">STANDARD</span>
    <span class="tier-pill pill-all" style="margin-left:4px;">CHIEF CASHIER</span>
  </div>
  <table class="cred-table">
    <thead><tr><th style="width:22%;">Username</th><th style="width:18%;">Password</th><th style="width:28%;">Role / Title</th><th>Position &amp; Notes</th></tr></thead>
    <tbody>
      <tr style="background:#fefce8;">
        <td><code>dr2_chief_cash</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-all"></span><strong>Chief Cashier ⭐</strong></td>
        <td><strong>MUST LOG IN FIRST EVERY MORNING</strong> to open the billing day. Verifies cashier shifts, handles reconciliation, approves exceptions. Has oversight of all cashier desks.</td>
      </tr>
      <tr>
        <td><code>dr2_cash_vip</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-vip"></span>VIP Cashier</td>
        <td>VIP billing desk. Processes invoices and payments for VIP-tier patients only.</td>
      </tr>
      <tr>
        <td><code>dr2_cash_std</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-standard"></span>Standard Cashier</td>
        <td>Standard billing desk. Processes invoices and payments for Standard patients.</td>
      </tr>
      <tr>
        <td><code>dr2_cash_exp</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-express"></span>Express Cashier</td>
        <td>Express billing desk. Processes payments for Express / Fast-Track patients.</td>
      </tr>
    </tbody>
  </table>
</div>

<!-- ══════════════════════════════════════════════════════════
     SECTION 10: NURSING (SHARED)
══════════════════════════════════════════════════════════ -->
<div class="section-block">
  <div class="section-heading">
    🏥 Section 10 &nbsp;·&nbsp; Nursing — Shared Services
    <span class="tier-pill pill-all">ALL TIERS</span>
  </div>
  <table class="cred-table">
    <thead><tr><th style="width:22%;">Username</th><th style="width:18%;">Password</th><th style="width:28%;">Role / Title</th><th>Position &amp; Notes</th></tr></thead>
    <tbody>
      <tr>
        <td><code>dr2_counsel</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-all"></span>Surgical Counseling Nurse</td>
        <td>Pre-operative counseling. Obtains patient consents. Educates patients on surgical procedures.</td>
      </tr>
      <tr>
        <td><code>dr2_admission</code></td>
        <td><code>{PASSWORD}</code></td>
        <td><span class="tier-dot dot-all"></span>Admission / Ward Nurse</td>
        <td>Processes patient admissions to IPD. Manages nursing care plans and ward patient records.</td>
      </tr>
    </tbody>
  </table>
</div>

<!-- PAGE BREAK -->
<div class="page-break"></div>

<!-- ══════════════════════════════════════════════════════════
     QUICK REFERENCE TABLE
══════════════════════════════════════════════════════════ -->
<h3>📊 Quick Reference — Staff Assignment by Tier &amp; Function</h3>
<table class="qr-table">
  <thead>
    <tr>
      <th style="width:18%;">Function</th>
      <th style="width:24%;">VIP Tier</th>
      <th style="width:24%;">Express / Fast-Track</th>
      <th style="width:24%;">Standard OPD</th>
      <th style="width:10%;">Shared</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Gate / Entry</strong></td>
      <td colspan="3" style="text-align:center;">dr2_gatekeeper (serves all)</td>
      <td>—</td>
    </tr>
    <tr>
      <td><strong>Reception</strong></td>
      <td>dr2_recept_vip</td>
      <td>dr2_recept_exp</td>
      <td>dr2_recept_std</td>
      <td>dr2_med_records</td>
    </tr>
    <tr>
      <td><strong>Triage Nurse</strong></td>
      <td>dr2_nurse_vip</td>
      <td>dr2_nurse_exp</td>
      <td>dr2_nurse_std</td>
      <td>—</td>
    </tr>
    <tr>
      <td><strong>Refraction</strong></td>
      <td>dr2_ref_vip1<br>dr2_ref_vip2</td>
      <td>dr2_ref_exp1<br>dr2_ref_exp2</td>
      <td>dr2_ref_std1<br>dr2_ref_std2</td>
      <td>—</td>
    </tr>
    <tr>
      <td><strong>Doctor (Retina)</strong></td>
      <td>dr2_dr_vip_ret</td>
      <td>dr2_dr_exp_ret</td>
      <td>dr2_dr_std_ret</td>
      <td>dr2_dr_general</td>
    </tr>
    <tr>
      <td><strong>Doctor (Glaucoma)</strong></td>
      <td>dr2_dr_vip_gla</td>
      <td>dr2_dr_exp_gla</td>
      <td>dr2_dr_std_gla</td>
      <td>—</td>
    </tr>
    <tr>
      <td><strong>Investigation</strong></td>
      <td colspan="3" style="text-align:center;">dr2_invest (serves all tiers)</td>
      <td>—</td>
    </tr>
    <tr>
      <td><strong>Laboratory</strong></td>
      <td colspan="3" style="text-align:center;">dr2_labtech (serves all tiers)</td>
      <td>—</td>
    </tr>
    <tr>
      <td><strong>Optical Shop</strong></td>
      <td colspan="3" style="text-align:center;">dr2_opt_cash · dr2_opt_disp (serves all tiers)</td>
      <td>—</td>
    </tr>
    <tr>
      <td><strong>Pharmacy</strong></td>
      <td colspan="3" style="text-align:center;">dr2_pharma (serves all tiers)</td>
      <td>—</td>
    </tr>
    <tr>
      <td><strong>Cashier</strong></td>
      <td>dr2_cash_vip</td>
      <td>dr2_cash_exp</td>
      <td>dr2_cash_std</td>
      <td>dr2_chief_cash</td>
    </tr>
    <tr>
      <td><strong>IPD / Nursing</strong></td>
      <td colspan="3" style="text-align:center;">dr2_counsel · dr2_admission (serves all tiers)</td>
      <td>—</td>
    </tr>
  </tbody>
</table>

<!-- ══════════════════════════════════════════════════════════
     PATIENT FLOW SUMMARY
══════════════════════════════════════════════════════════ -->
<h3 style="margin-top:14px;">🔄 Typical Patient Flow Through the System</h3>
<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;padding:10px 14px;font-size:8.5pt;line-height:1.8;">
  <strong style="color:#1e3a5f;">1. Gate</strong> → Patient enters, Gatekeeper issues entry ticket
  &nbsp;<strong>▶</strong>&nbsp;
  <strong style="color:#1e3a5f;">2. Reception</strong> → Receptionist registers patient, assigns tier
  &nbsp;<strong>▶</strong>&nbsp;
  <strong style="color:#1e3a5f;">3. Triage</strong> → Nurse records vitals, routes to appropriate doctor
  &nbsp;<strong>▶</strong>&nbsp;
  <strong style="color:#1e3a5f;">4. Refraction</strong> *(if applicable)* → Refractionist records full refraction data
  &nbsp;<strong>▶</strong>&nbsp;
  <strong style="color:#1e3a5f;">5. Doctor</strong> → Consultation, prescriptions, investigation/lab orders, referrals
  &nbsp;<strong>▶</strong>&nbsp;
  <strong style="color:#1e3a5f;">6. Investigation / Lab</strong> *(if ordered)* → Results recorded, PDF generated
  &nbsp;<strong>▶</strong>&nbsp;
  <strong style="color:#1e3a5f;">7. Pharmacy / Optical</strong> *(if prescribed)* → Dispensing
  &nbsp;<strong>▶</strong>&nbsp;
  <strong style="color:#1e3a5f;">8. Cashier</strong> → Invoice processed, payment collected, receipt printed
</div>

<!-- ══════════════════════════════════════════════════════════
     SIGN-OFF
══════════════════════════════════════════════════════════ -->
<div style="margin-top:20px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;font-size:8.5pt;">
  <div>
    <div style="border-bottom:1px solid #374151;margin-bottom:4px;padding-bottom:20px;"></div>
    <div style="color:#374151;font-weight:600;">IT Department / System Administrator</div>
    <div style="color:#6b7280;">Date: ___________________</div>
  </div>
  <div>
    <div style="border-bottom:1px solid #374151;margin-bottom:4px;padding-bottom:20px;"></div>
    <div style="color:#374151;font-weight:600;">Medical Director</div>
    <div style="color:#6b7280;">Date: ___________________</div>
  </div>
  <div>
    <div style="border-bottom:1px solid #374151;margin-bottom:4px;padding-bottom:20px;"></div>
    <div style="color:#374151;font-weight:600;">Chief Executive Officer</div>
    <div style="color:#6b7280;">Date: ___________________</div>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════════
     FOOTER
══════════════════════════════════════════════════════════ -->
<div class="doc-footer">
  <span>EHR Africa &nbsp;|&nbsp; Demo Run 2 Participant Briefing &nbsp;|&nbsp; Generated {TODAY}</span>
  <span>32 Accounts Issued &nbsp;|&nbsp; CONFIDENTIAL — FOR INTERNAL USE ONLY</span>
</div>

</div><!-- /page-wrapper -->
</body>
</html>"""

out_path = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP\DemoRun2_Briefing_Document.html'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'Document written: {out_path}')
print('Open in Chrome → Ctrl+P → Save as PDF (set margins to Minimum, enable Background graphics)')
