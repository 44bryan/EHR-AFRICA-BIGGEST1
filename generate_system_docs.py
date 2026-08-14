#!/usr/bin/env python3
"""
EHR Africa — Complete System Documentation Generator
Run: python generate_system_docs.py
Output: EHR_AFRICA_SYSTEM_DOCUMENTATION.pdf
"""

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  @page {
    size: A4;
    margin: 18mm 15mm 18mm 15mm;
    @bottom-center {
      content: "EHR Africa — Confidential System Documentation  |  Page " counter(page) " of " counter(pages);
      font-size: 7.5pt; color: #888; font-family: Arial, sans-serif;
    }
    @top-right {
      content: "v1.0 — July 2026";
      font-size: 7pt; color: #aaa; font-family: Arial, sans-serif;
    }
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: Arial, sans-serif; font-size: 9.5pt; color: #222; line-height: 1.55; }
  h1 { font-size: 20pt; color: #0d3d6e; margin-bottom: 6px; }
  h2 { font-size: 13pt; color: #0d3d6e; margin-top: 20px; margin-bottom: 6px;
       border-bottom: 2.5px solid #0d6efd; padding-bottom: 4px; page-break-after: avoid; }
  h3 { font-size: 10.5pt; color: #1a4f8a; margin-top: 14px; margin-bottom: 4px; page-break-after: avoid; }
  h4 { font-size: 9.5pt; color: #333; margin-top: 10px; margin-bottom: 3px;
       text-transform: uppercase; letter-spacing: .04em; page-break-after: avoid; }
  p  { margin-bottom: 7px; }
  ul, ol { margin-left: 18px; margin-bottom: 8px; }
  li { margin-bottom: 3px; }
  .cover { text-align: center; padding: 60px 0 40px; page-break-after: always; }
  .cover .logo-box { font-size: 36pt; font-weight: 900; color: #0d6efd; letter-spacing: 2px; }
  .cover .sub  { font-size: 11pt; color: #555; margin-top: 6px; }
  .cover .rule { border: none; border-top: 3px solid #0d6efd; margin: 30px auto; width: 120px; }
  .cover .title{ font-size: 18pt; font-weight: 700; color: #0d3d6e; margin-top: 10px; }
  .cover .meta { font-size: 9pt; color: #777; margin-top: 30px; }
  .toc  { page-break-after: always; }
  .toc h2 { margin-top: 0; }
  .toc ol { counter-reset: toc; list-style: none; margin-left: 0; }
  .toc > ol > li { margin-bottom: 6px; font-weight: 700; font-size: 10pt; }
  .toc > ol > li > ol { font-weight: 400; font-size: 9pt; margin-left: 14px; margin-top: 3px; }
  .part { background: #0d3d6e; color: #fff; padding: 12px 18px; margin: 24px 0 12px;
          border-radius: 4px; font-size: 12pt; font-weight: 700; page-break-before: always; }
  .flow-box { border: 1.5px solid #0d6efd; border-radius: 6px; padding: 12px 16px;
              margin: 10px 0; background: #f0f6ff; }
  .flow-step { display: flex; align-items: flex-start; margin-bottom: 8px; }
  .step-num { background: #0d6efd; color: #fff; border-radius: 50%; width: 22px; height: 22px;
              min-width: 22px; display: flex; align-items: center; justify-content: center;
              font-size: 8pt; font-weight: 700; margin-right: 10px; margin-top: 1px; }
  .step-body { flex: 1; }
  .step-title { font-weight: 700; font-size: 9.5pt; }
  .step-desc  { font-size: 8.5pt; color: #444; margin-top: 1px; }
  .arrow { text-align: center; color: #0d6efd; font-size: 14pt; line-height: 1; margin: 2px 0; }
  .role-table, .mod-table { width: 100%; border-collapse: collapse; font-size: 8.5pt; margin: 8px 0 14px; }
  .role-table th, .mod-table th { background: #0d3d6e; color: #fff; padding: 5px 8px; text-align: left; }
  .role-table td, .mod-table td { padding: 4px 8px; border-bottom: 1px solid #dee2e6; vertical-align: top; }
  .role-table tr:nth-child(even) td { background: #f8f9fa; }
  .mod-table tr:nth-child(even) td { background: #f8f9fa; }
  .badge { display: inline-block; padding: 1px 7px; border-radius: 10px; font-size: 7.5pt;
           font-weight: 700; white-space: nowrap; }
  .badge-blue  { background: #cfe2ff; color: #084298; }
  .badge-green { background: #d1e7dd; color: #0a3622; }
  .badge-red   { background: #f8d7da; color: #58151c; }
  .badge-gold  { background: #fff3cd; color: #664d03; }
  .badge-gray  { background: #e9ecef; color: #444; }
  .info-box { background: #fff3cd; border-left: 4px solid #ffc107; padding: 8px 12px;
              margin: 8px 0; font-size: 8.5pt; border-radius: 0 4px 4px 0; }
  .warn-box { background: #f8d7da; border-left: 4px solid #dc3545; padding: 8px 12px;
              margin: 8px 0; font-size: 8.5pt; border-radius: 0 4px 4px 0; }
  .grid2 { display: flex; gap: 14px; margin: 8px 0; }
  .grid2 > div { flex: 1; }
  .module-card { border: 1px solid #dee2e6; border-radius: 6px; padding: 10px 12px;
                 margin-bottom: 10px; page-break-inside: avoid; }
  .module-card h4 { margin-top: 0; color: #0d6efd; }
  .interconnect { background: #f8f9fa; border: 1px dashed #adb5bd; border-radius: 6px;
                  padding: 10px 14px; margin: 8px 0; font-size: 8.5pt; }
  hr { border: none; border-top: 1px solid #dee2e6; margin: 14px 0; }
  .page-break { page-break-before: always; }
  table.summary { width: 100%; border-collapse: collapse; font-size: 8.5pt; margin: 8px 0; }
  table.summary th { background: #495057; color: #fff; padding: 4px 8px; }
  table.summary td { padding: 4px 8px; border-bottom: 1px solid #dee2e6; }
  table.summary tr:nth-child(even) td { background: #f8f9fa; }
</style>
</head>
<body>

<!-- ═══════════════════════════════════════════════════════ COVER PAGE -->
<div class="cover">
  <div class="logo-box">EHR AFRICA</div>
  <div class="sub">Electronic Health Records — Ophthalmic Hospital Management System</div>
  <hr class="rule">
  <div class="title">COMPLETE SYSTEM DOCUMENTATION<br>& PATIENT FLOW REFERENCE</div>
  <div class="meta">
    Version 1.0 &nbsp;|&nbsp; July 2026<br>
    Compiled for Clinical, Administrative &amp; Executive Teams<br><br>
    <strong>CONFIDENTIAL — INTERNAL USE ONLY</strong>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════ TABLE OF CONTENTS -->
<div class="toc">
<h2>Table of Contents</h2>
<ol>
  <li>System Overview
    <ol>
      <li>What is EHR Africa</li>
      <li>Technology Stack</li>
      <li>All Modules at a Glance</li>
    </ol>
  </li>
  <li>User Roles &amp; Access Matrix (All 39 Roles)</li>
  <li>Patient Flow — New Patient, Standard Tier
    <ol>
      <li>Gate to Registration</li>
      <li>Triage</li>
      <li>Doctor Consultation</li>
      <li>Laboratory Orders &amp; Results</li>
      <li>Investigation Orders &amp; Results</li>
      <li>Pharmacy &amp; Prescriptions</li>
      <li>Cashier &amp; Payment</li>
      <li>Exit</li>
    </ol>
  </li>
  <li>Patient Flow — Returning Patient</li>
  <li>Patient Flow — Corporate / Insured Patient</li>
  <li>Patient Flow — VIP / Priority Patient</li>
  <li>Patient Flow — Walk-in / Emergency</li>
  <li>Sub-Specialty Clinical Flows
    <ol>
      <li>Ophthalmology: General Consultation</li>
      <li>Ophthalmology: Refraction</li>
      <li>Opticals / Frame Dispensing</li>
      <li>Low Vision Specialist</li>
      <li>Orthoptics</li>
      <li>Paediatric Refraction</li>
    </ol>
  </li>
  <li>Full Surgical Pathway
    <ol>
      <li>Surgery Decision at Consultation</li>
      <li>Surgical Counseling</li>
      <li>Surgical Booking &amp; Pre-op Assessment</li>
      <li>Pre-op Checklist &amp; Theatre Admission</li>
      <li>Theatre / Operation</li>
      <li>Recovery &amp; Ward</li>
      <li>Discharge &amp; Post-op Follow-up</li>
      <li>Surgical Billing</li>
    </ol>
  </li>
  <li>Financial Module
    <ol>
      <li>Cashier Workflow &amp; Shift Management</li>
      <li>Invoice &amp; Payment Lifecycle</li>
      <li>Corporate Billing &amp; Credit</li>
      <li>Reconciliation &amp; Reports</li>
    </ol>
  </li>
  <li>Administrative Module</li>
  <li>Queue Management System (QMS)</li>
  <li>Module Interconnection Map</li>
</ol>
</div>

<!-- ═══════════════════════════════════════════════════════ PART 1 -->
<div class="part">PART 1 — SYSTEM OVERVIEW</div>

<h2>1.1 What is EHR Africa</h2>
<p>EHR Africa is a full-featured, web-based Hospital Management Information System (HMIS) purpose-built for a specialist ophthalmic hospital in Cameroon. It covers every touchpoint in the patient journey — from gate entry to clinical consultation, surgery, pharmacy, laboratory, investigations, billing, and executive reporting — all on a single platform accessible from any browser on the hospital's local area network.</p>
<p>The system is designed around three patient tiers (Standard, VIP, Insured/Corporate) and an optional Queue Management System (QMS) that routes patients through digital queues at every workstation.</p>

<h2>1.2 Technology Stack</h2>
<table class="mod-table">
  <tr><th>Component</th><th>Technology</th><th>Notes</th></tr>
  <tr><td>Backend Framework</td><td>Django 6.0.5 (Python 3.14)</td><td>MVC, ORM, admin panel</td></tr>
  <tr><td>Database</td><td>PostgreSQL 16</td><td>Primary data store</td></tr>
  <tr><td>Cache / Broker</td><td>Redis 7</td><td>Celery task queue + Django cache</td></tr>
  <tr><td>Task Queue</td><td>Celery + Celery Beat</td><td>Async tasks, scheduled backups</td></tr>
  <tr><td>PDF Generation</td><td>WeasyPrint</td><td>All reports, invoices, records</td></tr>
  <tr><td>Web Server</td><td>Gunicorn + gevent + Nginx</td><td>Production deployment</td></tr>
  <tr><td>Frontend</td><td>Bootstrap 5 + Chart.js 4.4</td><td>Responsive UI, charts</td></tr>
  <tr><td>AI Features</td><td>Groq API / Ollama (local)</td><td>Clinical AI assistant</td></tr>
  <tr><td>Currency / Region</td><td>FCFA / Africa/Douala</td><td>Cameroon locale</td></tr>
  <tr><td>Barcode Scanning</td><td>USB HID keyboard emulation</td><td>Patient ID QR/barcode scan</td></tr>
</table>

<h2>1.3 All Modules at a Glance</h2>
<div class="grid2">
<div>
  <div class="module-card">
    <h4>Patients</h4>
    Registration, medical records, allergy alerts, problem list, consent forms, patient wallets, financial history.
  </div>
  <div class="module-card">
    <h4>Appointments</h4>
    Clinic board, booking, online scheduling, follow-up auto-booking after consultation.
  </div>
  <div class="module-card">
    <h4>Consultations</h4>
    Triage, doctor workstation, SOAP notes, prescriptions, lab orders, investigation orders, surgery referral.
  </div>
  <div class="module-card">
    <h4>Laboratory</h4>
    Blood, urine, microbiology. Order placement, specimen tracking, result entry, result verification, auto-return to doctor.
  </div>
  <div class="module-card">
    <h4>Investigations</h4>
    Eye imaging — OCT, B-scan, FFA, Fundus photography. Order, result, verification, auto-return to doctor.
  </div>
  <div class="module-card">
    <h4>Pharmacy</h4>
    Dispensing, stock management, expiry tracking, pilferage protection.
  </div>
  <div class="module-card">
    <h4>Prescriptions</h4>
    Doctor-issued prescriptions, drug interaction checking (JCI MMU.7), optical prescriptions.
  </div>
</div>
<div>
  <div class="module-card">
    <h4>Billing &amp; Finance</h4>
    Invoicing, POS cashier, shift management, reconciliation, corporate accounts, refunds, waivers, P&amp;L, AR aging, expenses, petty cash, budget.
  </div>
  <div class="module-card">
    <h4>IPD / Surgical</h4>
    Surgical counseling, booking, pre-op checklist, ward beds, theatre, anaesthetic records (JCI ASC.5/6), nursing care plans (JCI COP.8).
  </div>
  <div class="module-card">
    <h4>Opticals</h4>
    Frame catalogue, optical orders, dispensing, revenue tracking.
  </div>
  <div class="module-card">
    <h4>CSSD</h4>
    Sterilization cycles, equipment tracking for theatre.
  </div>
  <div class="module-card">
    <h4>HRMS</h4>
    Staff profiles, leave management, attendance, payroll, departments.
  </div>
  <div class="module-card">
    <h4>QMS</h4>
    Digital queue tokens, display boards, counter routing, skip-reason audit, nurse triage workstation.
  </div>
  <div class="module-card">
    <h4>Reporting &amp; Analytics</h4>
    Leadership dashboard, monthly stats, disease burden, revenue reports, MOH export, AI analytics.
  </div>
</div>
</div>

<!-- ═══════════════════════════════════════════════════════ PART 2 -->
<div class="part">PART 2 — USER ROLES &amp; ACCESS MATRIX</div>

<h2>2.1 All 39 Roles</h2>
<table class="role-table">
  <tr><th>Role</th><th>Home Dashboard</th><th>Primary Access</th></tr>
  <tr><td><strong>Super Admin</strong></td><td>System Admin Panel</td><td>Everything — all modules, all patients, all reports</td></tr>
  <tr><td><strong>CEO</strong></td><td>CEO Dashboard</td><td>Finance dashboard, all reports, hospital stats, patient lists</td></tr>
  <tr><td><strong>Medical Director</strong></td><td>Medical Director Dashboard</td><td>All clinical, all reports, staff performance, surgical stats</td></tr>
  <tr><td><strong>Admin Director</strong></td><td>Admin Director Dashboard</td><td>HR, staff, departments, billing overview, operations</td></tr>
  <tr><td><strong>Finance Director</strong></td><td>Finance Dashboard</td><td>Full financial — P&amp;L, AR, general ledger, payroll, assets</td></tr>
  <tr><td><strong>Senior Accountant</strong></td><td>Accounting Dashboard</td><td>Invoices, expenses, petty cash, budget, price catalog, wallets</td></tr>
  <tr><td><strong>Accountant</strong></td><td>Accounting Dashboard</td><td>Invoices, AR aging, reconciliation, expenses, daily summary</td></tr>
  <tr><td><strong>Chief Cashier</strong></td><td>Chief Cashier Dashboard</td><td>Open cashier day, verify shifts, reconciliation, all invoices, patient financial records</td></tr>
  <tr><td><strong>Cashier</strong></td><td>Cashier POS</td><td>Own shift only, POS billing, payment collection, own desk</td></tr>
  <tr><td><strong>Billing Officer</strong></td><td>Billing Module</td><td>Invoice creation, payments, corporate accounts</td></tr>
  <tr><td><strong>Receptionist</strong></td><td>Reception Dashboard</td><td>Patient registration, appointments, patient search, QMS routing</td></tr>
  <tr><td><strong>Gatekeeper</strong></td><td>Gate Module</td><td>Patient entry log, visitor management</td></tr>
  <tr><td><strong>Doctor</strong></td><td>Doctor Workstation</td><td>Consultations, SOAP notes, prescriptions, lab orders, investigations, surgery referrals</td></tr>
  <tr><td><strong>Ophthalmologist</strong></td><td>Doctor Workstation</td><td>Same as Doctor + consultation unit routing (General / Express / Insurance)</td></tr>
  <tr><td><strong>Optometrist</strong></td><td>Refraction / Opticals</td><td>Refraction, opticals, optical prescriptions</td></tr>
  <tr><td><strong>Paediatric Refractionist</strong></td><td>Doctor Workstation</td><td>Paediatric eye exams, refraction</td></tr>
  <tr><td><strong>Low Vision Specialist</strong></td><td>Doctor Workstation</td><td>Low vision assessments</td></tr>
  <tr><td><strong>Orthoptist</strong></td><td>Orthoptics Workstation</td><td>Orthoptic consultations, investigations</td></tr>
  <tr><td><strong>Intern</strong></td><td>Doctor Workstation</td><td>Limited — consultations under supervision, no refund/cancel</td></tr>
  <tr><td><strong>Consultation Nurse</strong></td><td>Clinic Nurse Station</td><td>Triage, vital signs, patient prep, clinic queue management</td></tr>
  <tr><td><strong>Nurse Director</strong></td><td>Nursing Hub</td><td>IPD nursing, ward management, nursing stats, HRMS staff</td></tr>
  <tr><td><strong>Ward Nurse</strong></td><td>IPD / Wards</td><td>Ward beds, nursing care plans, patient monitoring</td></tr>
  <tr><td><strong>Theatre Nurse</strong></td><td>Theatre / IPD</td><td>Pre-op checklist, theatre, CSSD, anaesthetic records view</td></tr>
  <tr><td><strong>Anaesthetist</strong></td><td>Theatre / Pre-op</td><td>Anaesthetic records, pre-op, theatre</td></tr>
  <tr><td><strong>Admission Officer</strong></td><td>IPD / Surgical Booking</td><td>Surgical counseling queue, booking, ward admission</td></tr>
  <tr><td><strong>Counseling Nurse</strong></td><td>Surgical Counseling</td><td>Surgical counseling queue, patient education, consent</td></tr>
  <tr><td><strong>Lab Technician</strong></td><td>Lab Workstation</td><td>Lab orders, specimen logging, result entry, verification</td></tr>
  <tr><td><strong>Investigation Tech</strong></td><td>Investigation Workstation</td><td>Eye imaging orders, result upload, verification</td></tr>
  <tr><td><strong>Pharmacist</strong></td><td>Pharmacy Dashboard</td><td>Dispensing, stock, prescriptions, expiry tracking</td></tr>
  <tr><td><strong>Optical Dispenser</strong></td><td>Opticals Dashboard</td><td>Frame catalogue, optical orders, dispensing</td></tr>
  <tr><td><strong>CSSD Technician</strong></td><td>CSSD Module</td><td>Sterilization cycles, equipment logs</td></tr>
  <tr><td><strong>Quality Officer</strong></td><td>Quality / Audit</td><td>JCI audits, patient feedback, leadership reports</td></tr>
  <tr><td><strong>Admin (System)</strong></td><td>Admin Panel + Staff Hub</td><td>User accounts, system configuration, HR</td></tr>
  <tr><td><strong>Admin Staff</strong></td><td>General Dashboard</td><td>General administrative tasks</td></tr>
  <tr><td><strong>HR Manager</strong></td><td>HRMS</td><td>Staff management, leave, attendance, payroll</td></tr>
  <tr><td><strong>Department Head</strong></td><td>Department Dashboard</td><td>Department-level staff and reporting</td></tr>
  <tr><td><strong>Outreach Officer</strong></td><td>Outreach Module</td><td>Community outreach, lead management</td></tr>
  <tr><td><strong>Consultation Nurse</strong> (Triage)</td><td>Triage Workstation</td><td>Full triage — vital signs, nurse notes, queue management</td></tr>
</table>

<h2>2.2 Financial Role Segregation</h2>
<table class="role-table">
  <tr><th>Role</th><th>Can Cancel Invoice</th><th>Can Refund</th><th>Can Open Day</th><th>Can Approve Expense</th><th>Can See P&amp;L</th></tr>
  <tr><td>Cashier</td><td>No</td><td>No</td><td>No</td><td>No</td><td>No</td></tr>
  <tr><td>Chief Cashier</td><td>No</td><td>No</td><td>Yes</td><td>No</td><td>No</td></tr>
  <tr><td>Accountant</td><td>Yes</td><td>Yes</td><td>No</td><td>No</td><td>No</td></tr>
  <tr><td>Senior Accountant</td><td>Yes</td><td>Yes</td><td>No</td><td>Yes</td><td>Yes</td></tr>
  <tr><td>Finance Director</td><td>Yes</td><td>Yes</td><td>Yes</td><td>Yes</td><td>Yes</td></tr>
</table>

<!-- ═══════════════════════════════════════════════════════ PART 3 -->
<div class="part">PART 3 — NEW PATIENT FLOW (STANDARD TIER)</div>

<h2>3.1 Complete Flow: Gate → Exit</h2>
<p>This is the primary patient journey for a first-time Standard-tier patient requiring consultation, investigations, and pharmacy.</p>

<div class="flow-box">
  <div class="flow-step">
    <div class="step-num">1</div>
    <div class="step-body">
      <div class="step-title">GATE ENTRY — Gatekeeper</div>
      <div class="step-desc">Patient arrives at hospital gate. Gatekeeper logs the visit (name, purpose, time). Issues a visitor pass. For returning patients, scans patient ID barcode. New patients are directed to Reception.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">2</div>
    <div class="step-body">
      <div class="step-title">RECEPTION — Receptionist</div>
      <div class="step-desc">Receptionist searches for patient. If new: registers the patient — Full name, DOB, sex, phone, address, tier (Standard/VIP/Insured), ID type, emergency contact, photo. System assigns a unique Patient ID (e.g. EHR-2026-00142). A new Visit is created with status REGISTRATION. If QMS is active: a queue token is issued automatically for the registration/reception counter.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">3</div>
    <div class="step-body">
      <div class="step-title">PRE-TRIAGE CASHIER — Cashier (Standard Tier)</div>
      <div class="step-desc">For Standard-tier patients: before seeing the doctor, the patient pays the consultation fee at the cashier. Cashier raises an invoice for the consultation service, collects cash/mobile money/card, issues a receipt. Visit status advances to WAITING (triage queue). QMS token issued for Triage counter.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">4</div>
    <div class="step-body">
      <div class="step-title">TRIAGE — Consultation Nurse</div>
      <div class="step-desc">Nurse calls patient from QMS triage queue. Can scan patient barcode to pull up record instantly. Records: Visual Acuity (right/left, unaided/aided), blood pressure, pulse, temperature, weight, height, chief complaint, nurse notes, allergies alert shown if any. Assigns patient to a Doctor queue (General, Express, Insurance). Visit status → IN_CONSULTATION. QMS token issued for the assigned doctor's counter.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">5</div>
    <div class="step-body">
      <div class="step-title">DOCTOR CONSULTATION — Doctor / Ophthalmologist</div>
      <div class="step-desc">Doctor calls patient from queue. Views: triage vitals, patient history, previous visits, problem list, allergies, current medications. Records SOAP note — Subjective (HPC, PMH, drug history, family history), Objective (examination findings, IOP, fundus, etc.), Assessment (diagnosis/ICD codes), Plan (management plan). From here, doctor can: place Lab Orders, place Investigation Orders, write Prescriptions, refer for Surgery, book Follow-up appointment, mark consultation Complete.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">6a</div>
    <div class="step-body">
      <div class="step-title">LAB ORDERS (if needed) — Auto-routed</div>
      <div class="step-desc">When doctor places any lab order, the system automatically: updates visit status to LABORATORY, issues QMS token for Lab counter, sends patient to lab queue. Patient no longer needs to ask where to go — system tells them via QMS display board. Lab technician scans patient barcode, logs specimen, enters results, verifies. When ALL lab results are verified and no other pending results: system auto-returns patient to doctor queue (visit status → WAITING / back to doctor).</div>
    </div>
  </div>
  <div class="flow-step">
    <div class="step-num">6b</div>
    <div class="step-body">
      <div class="step-title">INVESTIGATION ORDERS (if needed) — Auto-routed</div>
      <div class="step-desc">When doctor places an investigation order (OCT, B-scan, FFA, Fundus), system automatically routes patient to Investigation counter (same auto-routing mechanism as Lab). Investigation technician performs the test, uploads images/findings, verifies result. When all investigation results verified + all lab results verified: system auto-returns patient to doctor queue.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">7</div>
    <div class="step-body">
      <div class="step-title">DOCTOR — REVIEW RESULTS &amp; FINALISE</div>
      <div class="step-desc">Patient returns to doctor (auto-routed by system). Doctor reviews lab and investigation results in consultation record. Updates Assessment and Plan. Issues Prescription if medication needed. Prescription sent to Pharmacy queue. If surgery decided: issues surgical referral (see Surgical Pathway). If follow-up: books appointment. Marks consultation COMPLETE. Visit status → PHARMACY (if prescription) or BILLING.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">8</div>
    <div class="step-body">
      <div class="step-title">PHARMACY — Pharmacist</div>
      <div class="step-desc">Pharmacist receives prescription from doctor. Reviews drug interaction alerts (JCI MMU.7 compliance). Prepares and dispenses medications. Patient signs for receipt of drugs. Stock auto-decremented. If any drug is out of stock: pharmacist flags it, patient may need to purchase externally. Visit status → BILLING after dispensing.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">9</div>
    <div class="step-body">
      <div class="step-title">CASHIER — Final Payment</div>
      <div class="step-desc">Cashier consolidates all outstanding charges: consultation (if not pre-paid), lab tests, investigations, investigations, medications, optical items. Issues one or multiple invoices. Accepts payment by cash, mobile money (Orange Money / MTN), card, or corporate credit. Issues printed receipt. Marks invoice PAID. QMS token for cashier counter issued when patient is sent to billing. For Standard tier: cashier at their assigned desk (Standard cashier) handles the transaction.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">10</div>
    <div class="step-body">
      <div class="step-title">EXIT — Gate</div>
      <div class="step-desc">Patient exits through gate. Gatekeeper can verify paid receipt on system. Follow-up appointment card or SMS reminder issued if applicable. Visit closed (status → COMPLETED).</div>
    </div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════ PART 4 -->
<div class="part">PART 4 — RETURNING PATIENT FLOW</div>

<h2>4.1 Returning Patient — Standard Tier</h2>
<p>A returning patient is one who has visited before and has a Patient ID in the system.</p>

<div class="flow-box">
  <div class="flow-step">
    <div class="step-num">1</div>
    <div class="step-body">
      <div class="step-title">GATE — Scan Patient ID</div>
      <div class="step-desc">Gatekeeper scans patient barcode/QR from patient card or phone. System confirms identity. Patient directed to Reception or straight to Triage if they have a prior appointment.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">2</div>
    <div class="step-body">
      <div class="step-title">RECEPTION — Patient Lookup</div>
      <div class="step-desc">Receptionist searches by name, Patient ID, or barcode scan. Opens existing patient record. Creates a new Visit for today. System preloads: previous diagnoses, medications, allergies, problem list. Confirms and updates contact details if needed. Checks if patient has an appointment for today — if yes, links the visit to the appointment.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">3</div>
    <div class="step-body">
      <div class="step-title">CASHIER (Pre-triage payment for Standard tier)</div>
      <div class="step-desc">Same as new patient — consultation fee collected before triage. For follow-up visits, a discounted or waived fee may apply (Finance Director or Senior Accountant can apply waiver).</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">4</div>
    <div class="step-body">
      <div class="step-title">TRIAGE → DOCTOR → RESULTS → PHARMACY → CASHIER → EXIT</div>
      <div class="step-desc">Identical to new patient flow from Step 4 onward. Doctor has full history of all previous consultations, prescriptions, lab results, investigation images, surgical records, and follow-up notes.</div>
    </div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════ PART 5 -->
<div class="part">PART 5 — CORPORATE / INSURED PATIENT FLOW</div>

<h2>5.1 Corporate / Insurance Patient</h2>
<p>Corporate patients are linked to a Corporate Account (e.g. company health plan, CNPS). Billing goes to the company, not the patient.</p>

<div class="flow-box">
  <div class="flow-step">
    <div class="step-num">1</div>
    <div class="step-body">
      <div class="step-title">GATE → RECEPTION</div>
      <div class="step-desc">Receptionist verifies the patient's corporate membership card / CNPS card. Confirms the corporate account is active in the system and has available credit. Links the patient record to the Corporate Account.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">2</div>
    <div class="step-body">
      <div class="step-title">NO PRE-TRIAGE PAYMENT</div>
      <div class="step-desc">Corporate patients do not pay at cashier before triage. The consultation fee is billed to the corporate account. Visit status moves directly to WAITING (triage queue) after registration.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">3</div>
    <div class="step-body">
      <div class="step-title">TRIAGE → DOCTOR (Insured Queue)</div>
      <div class="step-desc">Triage nurse routes patient to the Insurance/Corporate doctor queue. The ophthalmologist with consultation_unit = INSURANCE handles this queue. Consultation proceeds normally.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">4</div>
    <div class="step-body">
      <div class="step-title">LAB / INVESTIGATION / PHARMACY</div>
      <div class="step-desc">All orders placed normally. All costs billed to corporate account. System enforces credit limit — if the corporate account balance is insufficient, a warning is shown and the accountant must approve or patient pays the excess.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">5</div>
    <div class="step-body">
      <div class="step-title">CASHIER — Corporate Invoice</div>
      <div class="step-desc">Insured cashier raises the invoice against the corporate account. Patient may pay a co-payment (if applicable per the corporate agreement). Invoice is marked as Corporate Credit — not collected from patient. Finance team reconciles corporate invoices periodically with the company/insurer.</div>
    </div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════ PART 6 -->
<div class="part">PART 6 — VIP PATIENT FLOW</div>

<h2>6.1 VIP / Priority Patient</h2>

<div class="flow-box">
  <div class="flow-step">
    <div class="step-num">1</div>
    <div class="step-body">
      <div class="step-title">GATE → RECEPTION</div>
      <div class="step-desc">VIP patient registered or looked up. Tier set to VIP on their profile. VIP patients are flagged visually on all screens with a gold badge.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">2</div>
    <div class="step-body">
      <div class="step-title">VIP CASHIER — Pre-triage (Optional)</div>
      <div class="step-desc">VIP cashier (assigned to VIP desk) handles consultation fee. VIP patients may have priority queue tokens — they jump ahead of Standard-tier patients in the same queue category.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">3</div>
    <div class="step-body">
      <div class="step-title">PRIORITY TRIAGE → VIP DOCTOR QUEUE</div>
      <div class="step-desc">VIP patients receive priority QMS token. Displayed separately on the queue board. Doctor serves VIP tokens before Standard tokens. All subsequent steps (Lab, Investigation, Pharmacy) follow the same flow but with VIP priority in queues.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">4</div>
    <div class="step-body">
      <div class="step-title">VIP CASHIER — Final Payment</div>
      <div class="step-desc">VIP cashier consolidates all charges. VIP pricing may apply. Premium services billed at VIP rate. Full receipt issued. Dedicated exit if applicable.</div>
    </div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════ PART 7 -->
<div class="part">PART 7 — WALK-IN / EMERGENCY FLOW</div>

<h2>7.1 Walk-in Patient</h2>

<div class="flow-box">
  <div class="flow-step">
    <div class="step-num">1</div>
    <div class="step-body">
      <div class="step-title">DIRECT RECEPTION — Walk-in Registration</div>
      <div class="step-desc">Patient arrives without appointment. Receptionist uses the Walk-in Search to check if patient exists. If new: quick registration (name, phone, sex minimum required). Full demographic details collected after clinical care if emergency. Visit created immediately.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">2</div>
    <div class="step-body">
      <div class="step-title">EMERGENCY TRIAGE — Priority Assessment</div>
      <div class="step-desc">Triage nurse assesses urgency. Emergency patients can be given a priority token or sent directly to the doctor bypassing the normal queue. Nurse documents clinical reason for emergency routing. System logs all skip-reason audit trails (JCI compliance).</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">3</div>
    <div class="step-body">
      <div class="step-title">DOCTOR → STABILISE → NORMAL FLOW</div>
      <div class="step-desc">Doctor sees patient immediately. Orders lab/investigations as needed. System auto-routes as normal. Billing deferred until patient is stable — accountant can flag for post-care billing. All clinical actions recorded normally for medical-legal purposes.</div>
    </div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════ PART 8 -->
<div class="part">PART 8 — SUB-SPECIALTY CLINICAL FLOWS</div>

<h2>8.1 Ophthalmology — General Consultation</h2>
<p>Standard flow as in Part 3. Doctor uses the full consultation workstation with ophthalmic-specific fields: Visual Acuity, IOP (intraocular pressure), Anterior Segment, Posterior Segment, Refraction findings. IOP trend chart available for glaucoma monitoring.</p>

<h2>8.2 Ophthalmology — Refraction</h2>
<div class="flow-box">
  <div class="flow-step"><div class="step-num">1</div><div class="step-body"><div class="step-title">Optometrist / Paediatric Refractionist / Low Vision Specialist</div><div class="step-desc">Patient routed to refraction workstation after initial triage. Visual acuity measured. Refraction performed (objective + subjective). Optical prescription generated in the system.</div></div></div>
  <div class="arrow">▼</div>
  <div class="flow-step"><div class="step-num">2</div><div class="step-body"><div class="step-title">OPTICALS — Frame Selection &amp; Order</div><div class="step-desc">Optical dispenser receives prescription. Patient selects frame from catalogue. Lens order created (right/left power, type). Order sent to lab/workshop. Pickup date confirmed. Patient billed for frame + lenses at cashier.</div></div></div>
</div>

<h2>8.3 Orthoptics</h2>
<p>Orthoptist receives patients referred by ophthalmologist. Conducts orthoptic assessment (eye movement, binocular vision, amblyopia). Places investigation orders if imaging needed. Reports findings back to referring doctor in the consultation record. Billed at cashier.</p>

<h2>8.4 Low Vision</h2>
<p>Low Vision Specialist sees patients with severe visual impairment. Conducts functional vision assessment. Prescribes low vision aids. Results documented in consultation record. May refer for further investigation (OCT, Fundus). Billed at cashier.</p>

<!-- ═══════════════════════════════════════════════════════ PART 9 -->
<div class="part">PART 9 — FULL SURGICAL PATHWAY</div>

<h2>9.1 Surgery Decision at Consultation</h2>
<p>When a doctor decides a patient needs surgery during consultation, the following is triggered:</p>
<ul>
  <li>Doctor clicks "Refer for Surgery" in the consultation workstation</li>
  <li>Selects the surgery type (e.g. cataract extraction, pterygium, vitrectomy, glaucoma surgery)</li>
  <li>Adds clinical notes, urgency level, and any pre-operative requirements</li>
  <li>Visit status → SURGICAL_COUNSELING</li>
  <li>QMS token issued for Surgical Counseling counter</li>
</ul>

<div class="flow-box">
  <div class="flow-step">
    <div class="step-num">1</div>
    <div class="step-body">
      <div class="step-title">SURGICAL COUNSELING — Counseling Nurse / Admission Officer</div>
      <div class="step-desc">Patient called from Surgical Counseling queue. Counselor explains the procedure: what it involves, risks, expected outcomes, recovery time, pre-op requirements (fasting, medications to stop, etc.). Patient Financial Counseling: provides a cost estimate for the surgery (surgeon fee, anaesthesia, theatre, consumables, ward stay). Patient signs the Surgical Consent Form (JCI PFR.5 — PatientConsent model). Counselor books a surgical date. Patient given a pre-op instruction sheet.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">2</div>
    <div class="step-body">
      <div class="step-title">SURGICAL BOOKING — Admission Officer</div>
      <div class="step-desc">Admission Officer creates the surgical booking: surgery date, surgeon assigned, theatre room, anaesthesia type (general / local / regional), estimated duration. Pre-operative investigations ordered if not already done (blood tests, ECG, chest X-ray as appropriate). Patient added to the surgical booking queue. Patient given a booking confirmation card with date, time, location, and preparation instructions.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">3</div>
    <div class="step-body">
      <div class="step-title">PRE-OP CASHIER — Surgery Deposit</div>
      <div class="step-desc">Before surgery day: patient pays surgery deposit at cashier (or corporate account is pre-authorised). Standard surgery invoice raised for the full amount. At minimum, a defined deposit percentage is collected. Remaining balance payable on discharge. If patient cannot pay deposit, Finance Director or Accountant can approve a payment plan or waiver.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">4</div>
    <div class="step-body">
      <div class="step-title">SURGERY DAY — Pre-op Check-in</div>
      <div class="step-desc">On surgery day, patient reports to the Pre-op Check-in area. Theatre Nurse or Admission Officer performs pre-op checklist: consent form verified, fasting confirmed, allergies confirmed, surgical site marked, IV access, pre-med administered. Anaesthetist performs pre-operative assessment — reviews medical history, documents in AnaestheticRecord (JCI ASC.5). Patient identity confirmed with 2 identifiers (name + patient ID) — JCI IPSG.1. All checklist items ticked and signed. Patient wheeled to theatre.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">5</div>
    <div class="step-body">
      <div class="step-title">THEATRE — Operation</div>
      <div class="step-desc">Surgeon performs procedure. Theatre Nurse documents intraoperative findings. Anaesthetist records: anaesthetic agents used (induction, maintenance agents, analgesics, muscle relaxants, reversal agents), monitoring notes, IV fluids given, intraoperative events/complications, total duration in minutes. All findings entered in AnaestheticRecord (JCI ASC.6). CSSD: all instruments used are logged in CSSD system for sterilization tracking. After surgery: patient transferred to recovery.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">6</div>
    <div class="step-body">
      <div class="step-title">RECOVERY — Ward</div>
      <div class="step-desc">Post-op patient assigned to a ward bed (Wards &amp; Beds module). Ward Nurse creates a Nursing Care Plan (JCI COP.8) — nursing diagnoses, goals, interventions, evaluation schedule. Anaesthetist documents post-op: pain score on discharge, post-op nausea/vomiting, post-op complications, post-op instructions. Surgeon reviews patient in ward (ward round noted in system). Medications administered from prescription — pharmacy dispensed to ward.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">7</div>
    <div class="step-body">
      <div class="step-title">DISCHARGE</div>
      <div class="step-desc">Surgeon authorises discharge. Discharge summary written. Take-home medications prescribed. Follow-up appointment booked (system auto-creates the appointment). Patient receives: discharge letter, follow-up appointment card, take-home drug instructions. Admission Officer closes the inpatient episode.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">8</div>
    <div class="step-body">
      <div class="step-title">SURGICAL BILLING — Cashier</div>
      <div class="step-desc">Cashier generates final surgery invoice: surgeon fee, anaesthesia fee, theatre charges, consumables, ward accommodation (per night), nursing care, medications given in ward, any additional procedures. Deducts deposit already paid. Patient or corporate account pays balance. Full receipt issued. For corporate patients: full amount billed to corporate account. Patient exits with zero balance on surgical episode.</div>
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="flow-step">
    <div class="step-num">9</div>
    <div class="step-body">
      <div class="step-title">POST-OP FOLLOW-UP</div>
      <div class="step-desc">Patient returns for follow-up visit (1 week, 1 month, 3 months as applicable). Follow-up linked to original surgical episode. Doctor reviews healing, checks for complications, adjusts medications. Refraction done after healing for glasses prescription (for cataract patients). Normal billing applies for follow-up consultation. All follow-up notes linked to the patient's surgical record for long-term outcome tracking.</div>
    </div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════ PART 10 -->
<div class="part">PART 10 — FINANCIAL MODULE</div>

<h2>10.1 Cashier Workflow &amp; Shift Management</h2>

<h3>Daily Cashier Lifecycle</h3>
<div class="flow-box">
  <div class="flow-step"><div class="step-num">1</div><div class="step-body"><div class="step-title">Chief Cashier Opens the Day</div><div class="step-desc">At the start of each working day, the Chief Cashier opens the cashier day from their dashboard ("Open Cashier Day" function). This creates a CashierShift record for each active cashier with the day's opening float. No cashier can process payments before the day is opened.</div></div></div>
  <div class="arrow">▼</div>
  <div class="flow-step"><div class="step-num">2</div><div class="step-body"><div class="step-title">Cashier Selects Their Desk</div><div class="step-desc">Each cashier logs in and is prompted to select their Cash Desk: Standard, Express/Fast-Track, VIP, or Insured. This routes them to the correct QMS counter. Cashier stays at their desk all day. If they need to switch desks (e.g. covering another desk), they can change via the dashboard.</div></div></div>
  <div class="arrow">▼</div>
  <div class="flow-step"><div class="step-num">3</div><div class="step-body"><div class="step-title">Cashier Collects Payments</div><div class="step-desc">Throughout the day, cashier processes invoices. Each payment recorded: amount, method (cash/mobile money/card), reference number, patient, time. Running total visible on their shift dashboard. QMS display board shows when patient is called to their counter.</div></div></div>
  <div class="arrow">▼</div>
  <div class="flow-step"><div class="step-num">4</div><div class="step-body"><div class="step-title">Cashier Closes Their Shift</div><div class="step-desc">At end of day/shift, cashier declares their closing cash count. System calculates: Opening Float + Cash Collected = Expected Closing Cash. Variance = Declared − Expected. Cashier submits shift for verification.</div></div></div>
  <div class="arrow">▼</div>
  <div class="flow-step"><div class="step-num">5</div><div class="step-body"><div class="step-title">Chief Cashier Verifies Shift</div><div class="step-desc">Chief Cashier reviews each cashier's shift: checks declared vs. expected cash, reviews variance, countersigns the shift. Flags any discrepancies to Finance Director. Downloads Shift Reconciliation PDF for physical records.</div></div></div>
  <div class="arrow">▼</div>
  <div class="flow-step"><div class="step-num">6</div><div class="step-body"><div class="step-title">Finance Director Reviews Day</div><div class="step-desc">Finance Director downloads: Daily Cash Summary PDF, Shift Reconciliation PDFs, AR Aging report if needed. Reviews net revenue vs. expenses for the day. Approves any expense claims. Signs off on the day. All figures feed automatically into the Monthly P&amp;L.</div></div></div>
</div>

<h2>10.2 Invoice &amp; Payment Lifecycle</h2>
<table class="mod-table">
  <tr><th>Status</th><th>Meaning</th></tr>
  <tr><td>DRAFT</td><td>Invoice created but not yet presented to patient</td></tr>
  <tr><td>PENDING</td><td>Presented to patient — awaiting payment</td></tr>
  <tr><td>PARTIALLY_PAID</td><td>Part payment received (common for surgery deposits)</td></tr>
  <tr><td>PAID</td><td>Fully paid — receipt issued</td></tr>
  <tr><td>CANCELLED</td><td>Invoice cancelled by Accountant or above — reason required</td></tr>
  <tr><td>REFUNDED</td><td>Payment refunded — refund record created, approved by Accountant or above</td></tr>
  <tr><td>WAIVED</td><td>Amount waived by Finance Director — waiver reason documented</td></tr>
  <tr><td>CORPORATE</td><td>Billed to corporate account — payment collected from company not patient</td></tr>
</table>

<h2>10.3 Corporate Billing &amp; Credit</h2>
<p>Corporate accounts have: company name, credit limit, current balance, contact details, billing cycle. Each time a corporate patient is billed, the invoice is linked to the corporate account. If the account balance exceeds the credit limit, the system blocks further billing and alerts the Accountant. Finance team periodically sends consolidated statements to the company. Payment received from the company is recorded against the corporate account.</p>

<h2>10.4 Financial Reports Available</h2>
<table class="mod-table">
  <tr><th>Report</th><th>Who Can Access</th><th>Output</th></tr>
  <tr><td>Daily Cash Summary</td><td>Chief Cashier, Accountant, Senior Accountant, Finance Director, CEO, Admin</td><td>PDF + screen</td></tr>
  <tr><td>Shift Reconciliation</td><td>Chief Cashier, Finance Director, Super Admin</td><td>PDF per shift</td></tr>
  <tr><td>P&amp;L Statement</td><td>Senior Accountant, Finance Director, CEO, Admin</td><td>PDF per month</td></tr>
  <tr><td>AR Aging Report</td><td>Accountant, Senior Accountant, Finance Director, CEO</td><td>PDF (landscape)</td></tr>
  <tr><td>Top Services by Revenue</td><td>Accountant+, CEO, Medical Director</td><td>PDF</td></tr>
  <tr><td>Revenue Report</td><td>Finance Director, CEO, Medical Director, Admin</td><td>PDF</td></tr>
  <tr><td>Sales Journal</td><td>Accountant+</td><td>Screen + export</td></tr>
  <tr><td>Budget vs Actual</td><td>Senior Accountant+</td><td>Screen + PDF</td></tr>
  <tr><td>Invoice PDF</td><td>All cashier roles, Billing Officer</td><td>A4 PDF per invoice</td></tr>
</table>

<!-- ═══════════════════════════════════════════════════════ PART 11 -->
<div class="part">PART 11 — ADMINISTRATIVE MODULE</div>

<h2>11.1 HRMS (Human Resources Management)</h2>
<ul>
  <li><strong>Staff Profiles:</strong> Full employee records — personal details, role, department, employment date, contract type, qualifications</li>
  <li><strong>Departments:</strong> Department management — create, edit, assign department heads and members</li>
  <li><strong>Leave Management:</strong> Staff submit leave requests. HR Manager or Admin Director approves/rejects. Leave calendar visible to management</li>
  <li><strong>Attendance:</strong> Daily attendance register. Linked to shift records</li>
  <li><strong>Payroll:</strong> Monthly payroll runs. Calculates gross pay, deductions (CNPS, income tax), net pay. Payslips generated as PDF. Finance Director approves payroll</li>
</ul>

<h2>11.2 Assets &amp; Inventory</h2>
<ul>
  <li><strong>Asset Register:</strong> All hospital fixed assets — name, category, purchase date, cost, useful life, depreciation method (straight-line). System automatically calculates: annual depreciation, accumulated depreciation, net book value, fully-depreciated flag</li>
  <li><strong>Inventory:</strong> Medical supplies, consumables, drugs (linked to pharmacy). Stock in/out tracking. Low-stock alerts. Expiry tracking</li>
  <li><strong>Pharmacy Stock:</strong> Full drug inventory with batch numbers, expiry dates, supplier records</li>
</ul>

<h2>11.3 Patient Wallets (Pre-payment)</h2>
<p>Patients can pre-load money into a Patient Wallet. Wallet balance used to pay for services without cash transaction at point of care. Wallet deposits recorded with transaction history. Refunds returned to wallet. Finance Director or Senior Accountant can view all wallets and process wallet-based adjustments.</p>

<!-- ═══════════════════════════════════════════════════════ PART 12 -->
<div class="part">PART 12 — QUEUE MANAGEMENT SYSTEM (QMS)</div>

<h2>12.1 QMS Overview</h2>
<p>The QMS (Queue Management System) is an optional module (enabled/disabled via HospitalConfig). When active, it manages patient flow through digital tokens at every counter/workstation.</p>

<h3>How QMS Works</h3>
<ul>
  <li>Every time a patient moves to a new workstation, a QueueToken is issued for the destination counter</li>
  <li>Tokens have a counter type (e.g. RECEPTION, TRIAGE, GENERAL, EXPRESS, INSURANCE, LAB, INVEST, PHARMACY, CASHIER_STD, CASHIER_VIP, etc.)</li>
  <li>Each workstation has a display board showing the current token being served and the queue ahead</li>
  <li>Staff press "Call Next" to advance the queue</li>
  <li>If a patient is skipped (e.g. not present when called), staff record a skip reason — this is audited (JCI compliance)</li>
  <li>Doctor can see their patient queue on their workstation and call the next patient</li>
</ul>

<h3>Auto-Routing (Clinical Automation)</h3>
<ul>
  <li>When doctor places a lab order → system automatically creates a LAB queue token for that patient</li>
  <li>When doctor places an investigation order → system creates an INVEST token</li>
  <li>When all lab results AND all investigation results are verified → system creates a token to return the patient to the doctor queue</li>
  <li>This eliminates the need for patients to wander and ask "where do I go now?"</li>
</ul>

<h3>QMS Display Board</h3>
<p>A large-screen display board shows the current queue status for each counter. Visible to patients in the waiting area. Auto-refreshes every few seconds. Shows: Counter name, Now Serving token, Next 3-5 tokens.</p>

<!-- ═══════════════════════════════════════════════════════ PART 13 -->
<div class="part">PART 13 — MODULE INTERCONNECTION MAP</div>

<h2>13.1 How All Modules Connect</h2>
<div class="interconnect">
<pre style="font-size:8pt; line-height:1.6; font-family: monospace;">
PATIENTS module
  └─ is the CORE of everything — every record links to a Patient
  └─ linked to: Consultations, Lab, Investigations, Pharmacy, Billing, IPD, Appointments

APPOINTMENTS
  └─ links to: Patients, Consultations (auto-create visit from appointment)
  └─ auto-created by: Doctor at end of consultation (follow-up booking)

CONSULTATIONS (Triage + Doctor Workstation)
  ├─ TRIAGE (Consultation Nurse) → creates triage record → routes to Doctor
  ├─ DOCTOR → creates consultation → can trigger:
  │     ├─ LAB ORDERS → Laboratory module (auto-routes patient)
  │     ├─ INVESTIGATION ORDERS → Investigations module (auto-routes patient)
  │     ├─ PRESCRIPTIONS → Pharmacy module
  │     ├─ SURGERY REFERRAL → IPD / Surgical Pathway
  │     └─ FOLLOW-UP APPOINTMENT → Appointments module
  └─ All consultations linked to Visit (Patients module)

LABORATORY
  ├─ Receives orders from: Consultations (doctor)
  ├─ On result verification → notifies Consultations (auto-return to doctor)
  └─ Billed through: Billing module

INVESTIGATIONS
  ├─ Receives orders from: Consultations (doctor)
  ├─ On result verification → notifies Consultations (auto-return to doctor)
  └─ Billed through: Billing module

PHARMACY
  ├─ Receives prescriptions from: Consultations (doctor)
  ├─ Stock linked to: Inventory module
  └─ Billed through: Billing module

IPD / SURGICAL
  ├─ Receives surgical referrals from: Consultations
  ├─ Counseling → Booking → Pre-op → Theatre → Ward → Discharge
  ├─ AnaestheticRecord — documents anaesthesia (JCI ASC.5/6)
  ├─ NursingCarePlan — ward nursing (JCI COP.8)
  ├─ PatientConsent — surgical consent (JCI PFR.5)
  ├─ CSSD — sterilization tracking for theatre instruments
  └─ Billed through: Billing module

BILLING / FINANCE
  ├─ Receives charges from: ALL clinical modules
  ├─ Cashier POS → Invoice → Payment → Receipt
  ├─ Shift Management → Daily Reconciliation → Reports
  ├─ Corporate Accounts → Corporate invoicing
  ├─ PatientWallet → Pre-payment management
  ├─ Expenses + Petty Cash → Operating cost tracking
  ├─ Budget → Budget vs Actual
  ├─ General Ledger → Journal Entries → Trial Balance → Balance Sheet
  └─ Reports → Daily Summary, P&L, AR Aging, Top Services (all PDF)

OPTICALS
  ├─ Receives prescriptions from: Consultations (optometrist)
  └─ Billed through: Billing module

HRMS
  ├─ Linked to: Accounts (User model — staff profiles)
  ├─ Leave, Attendance, Payroll
  └─ Payroll approved by Finance Director

QMS
  ├─ Triggered by: ALL modules that move patients between workstations
  ├─ Reads from: Visit status (Patients module)
  └─ Feeds: All workstation display boards

REPORTS / LEADERSHIP
  ├─ Pulls data from: ALL modules
  ├─ Leadership Dashboard → KPIs from Billing, Consultations, IPD
  ├─ Monthly Stats → Consultations, Lab, Investigations, Billing
  ├─ Disease Burden → Consultations (diagnosis codes)
  ├─ Revenue Report → Billing
  └─ MOH Export → Consultations (diagnosis, demographics)

AI ASSISTANT
  ├─ Clinical AI → reads consultation history, suggests diagnoses
  ├─ Analytics AI → reads hospital-wide data, generates insights
  └─ Virtual Receptionist → appointment booking, patient queries
</pre>
</div>

<h2>13.2 Visit Status State Machine</h2>
<p>Every patient visit has a status that tracks where the patient is in the system. The status drives QMS routing, workstation access, and billing.</p>
<table class="mod-table">
  <tr><th>Status</th><th>Meaning</th><th>Next Status</th></tr>
  <tr><td>REGISTRATION</td><td>Patient being registered at reception</td><td>WAITING (after cashier pre-payment)</td></tr>
  <tr><td>WAITING</td><td>In triage queue or waiting after returning from lab/invest</td><td>IN_CONSULTATION or LABORATORY or INVESTIGATION</td></tr>
  <tr><td>IN_CONSULTATION</td><td>With doctor</td><td>LABORATORY, INVESTIGATION, PHARMACY, SURGICAL_COUNSELING, BILLING, COMPLETED</td></tr>
  <tr><td>LABORATORY</td><td>At lab for blood/specimen tests</td><td>INVESTIGATION or WAITING (auto-return to doctor)</td></tr>
  <tr><td>INVESTIGATION</td><td>At investigation for eye imaging</td><td>LABORATORY or WAITING (auto-return to doctor)</td></tr>
  <tr><td>PHARMACY</td><td>At pharmacy for drug dispensing</td><td>BILLING</td></tr>
  <tr><td>SURGICAL_COUNSELING</td><td>At surgical counseling</td><td>SURGICAL_BOOKING</td></tr>
  <tr><td>SURGICAL_BOOKING</td><td>Surgical date being booked</td><td>BILLING (deposit payment)</td></tr>
  <tr><td>BILLING</td><td>At cashier for payment</td><td>COMPLETED</td></tr>
  <tr><td>COMPLETED</td><td>All done — patient exited</td><td>Terminal state</td></tr>
  <tr><td>ADMITTED</td><td>Admitted to ward (IPD)</td><td>DISCHARGED</td></tr>
  <tr><td>DISCHARGED</td><td>Discharged from IPD</td><td>COMPLETED (after billing)</td></tr>
</table>

<h2>13.3 JCI Compliance Features Built In</h2>
<table class="mod-table">
  <tr><th>JCI Standard</th><th>Feature</th><th>Module</th></tr>
  <tr><td>IPSG.1 — Patient Identification</td><td>2-identifier verification at all critical points (name + patient ID)</td><td>All clinical modules</td></tr>
  <tr><td>PFR.5 — Patient Consent</td><td>PatientConsent model — surgical &amp; procedure consents with digital signature</td><td>IPD / Patients</td></tr>
  <tr><td>ASC.5 — Pre-anaesthesia Assessment</td><td>AnaestheticRecord — pre-op anaesthesia assessment documented</td><td>IPD</td></tr>
  <tr><td>ASC.6 — Intraoperative Monitoring</td><td>AnaestheticRecord — full intraoperative monitoring, agents, complications</td><td>IPD</td></tr>
  <tr><td>COP.8 — Nursing Care Plans</td><td>NursingCarePlan — formal care plans for all admitted patients</td><td>IPD</td></tr>
  <tr><td>MMU.7 — Drug Interactions</td><td>DrugInteraction model — checks all prescriptions against known interactions</td><td>Prescriptions</td></tr>
  <tr><td>QPS — Skip Reason Audit</td><td>All queue skips recorded with reason and staff identity</td><td>QMS</td></tr>
  <tr><td>HIPAA PHI</td><td>PHI access logging — all patient record views logged</td><td>Core / Audit</td></tr>
</table>

<h2>13.4 Key Integration Points</h2>
<div class="info-box">
  <strong>Automatic Patient Routing (No Manual Direction Needed):</strong><br>
  The system automatically routes patients between workstations using QMS tokens. When a doctor places a lab order, the patient's queue token appears at the Lab counter without any staff intervention. When results are ready, the patient returns to the doctor queue automatically. This eliminates lost patients, reduces waiting time, and creates a full audit trail of where each patient was at every moment of their visit.
</div>
<div class="info-box">
  <strong>Barcode / QR Scanning at Every Workstation:</strong><br>
  Every clinical and administrative workstation has a scan bar at the top. Staff can scan a patient's barcode card or phone QR code to instantly pull up their record — no typing required. This works with any USB HID barcode scanner (plug and play, no driver needed).
</div>
<div class="info-box">
  <strong>All Reports Export as Professional PDF:</strong><br>
  Every report in the system — invoices, reconciliation, P&amp;L, AR aging, shift summaries, daily cash summary, top services, lab reports, surgical records — generates a professional A4 PDF with the hospital letterhead, logo, contact details, report metadata, and authorisation signature blocks. All PDFs are WeasyPrint-generated, not browser-print dependent.
</div>

<!-- ═══════════════════════════════════════════════════════ PART 14 -->
<div class="part">PART 14 — COMPLETE FEATURE STATUS MATRIX</div>

<h2>14.1 What is FULLY BUILT &amp; Working</h2>
<p>The following features are complete, tested, and deployed in production.</p>

<table class="mod-table">
  <tr><th style="width:5%">#</th><th style="width:30%">Feature</th><th style="width:40%">Detail</th><th style="width:25%">Module</th></tr>

  <tr><td colspan="4" style="background:#d1e7dd;font-weight:700;color:#0a3622;">PATIENT MANAGEMENT</td></tr>
  <tr><td>1</td><td>Patient Registration</td><td>Full demographic capture, Patient ID auto-assign (EHR-YYYY-#####), photo, tier, emergency contact, ID type</td><td>Patients</td></tr>
  <tr><td>2</td><td>Patient Medical Record</td><td>Full history — visits, consultations, lab, investigations, prescriptions, surgeries, problem list</td><td>Patients</td></tr>
  <tr><td>3</td><td>Patient Problem List</td><td>Persistent chronic conditions tracked across all visits</td><td>Patients</td></tr>
  <tr><td>4</td><td>Allergy Alert System</td><td>Allergy records flagged in red at every prescribing point — JCI IPSG.6</td><td>Patients</td></tr>
  <tr><td>5</td><td>Patient Consent Forms</td><td>Surgical and procedure consents digitally captured — JCI PFR.5</td><td>Patients / IPD</td></tr>
  <tr><td>6</td><td>Patient Financial History</td><td>Full invoice and payment history per patient</td><td>Billing</td></tr>
  <tr><td>7</td><td>Patient Pre-payment Wallet</td><td>Deposit, deduct, refund; balance tracking with full transaction log</td><td>Billing</td></tr>
  <tr><td>8</td><td>QR / Barcode Scan</td><td>USB scanner at every workstation — instant patient lookup</td><td>All</td></tr>
  <tr><td>9</td><td>Walk-in Fast Registration</td><td>Minimal-field emergency registration with full details filled later</td><td>Patients / Reception</td></tr>

  <tr><td colspan="4" style="background:#d1e7dd;font-weight:700;color:#0a3622;">APPOINTMENTS &amp; SCHEDULING</td></tr>
  <tr><td>10</td><td>Clinic Board</td><td>Today's appointments, status tracking (scheduled / checked-in / completed / no-show)</td><td>Appointments</td></tr>
  <tr><td>11</td><td>Appointment Booking</td><td>Receptionist books for any doctor, any date</td><td>Appointments</td></tr>
  <tr><td>12</td><td>Follow-up Auto-booking</td><td>Doctor books follow-up from within consultation — appointment created instantly</td><td>Appointments / Consultations</td></tr>

  <tr><td colspan="4" style="background:#d1e7dd;font-weight:700;color:#0a3622;">CLINICAL — TRIAGE &amp; CONSULTATION</td></tr>
  <tr><td>13</td><td>Triage Workstation</td><td>VA (unaided/aided R/L), BP, pulse, temp, weight, height, chief complaint, nurse notes</td><td>Consultations</td></tr>
  <tr><td>14</td><td>Doctor Consultation</td><td>Full SOAP — HPC, PMH, drug history, family history, ophthalmic exam (IOP, VA, anterior/posterior segment), diagnosis (ICD), plan</td><td>Consultations</td></tr>
  <tr><td>15</td><td>IOP Trend Chart</td><td>Glaucoma monitoring — IOP over multiple visits plotted as interactive Chart.js graph</td><td>Consultations</td></tr>
  <tr><td>16</td><td>Multiple Consultation Units</td><td>Doctors assigned to: General, Express, Insurance — separate queues</td><td>Consultations / QMS</td></tr>
  <tr><td>17</td><td>Prescription Writing</td><td>Doctor writes prescriptions with drug, dose, frequency, duration, route</td><td>Prescriptions</td></tr>
  <tr><td>18</td><td>Drug Interaction Checking</td><td>Automatic alert when two drugs interact — JCI MMU.7</td><td>Prescriptions</td></tr>
  <tr><td>19</td><td>Optical Prescription</td><td>Refraction result → optical prescription for glasses</td><td>Consultations / Opticals</td></tr>

  <tr><td colspan="4" style="background:#d1e7dd;font-weight:700;color:#0a3622;">LABORATORY</td></tr>
  <tr><td>20</td><td>Lab Order Placement</td><td>Doctor places orders from consultation — blood, urine, microbiology</td><td>Laboratory</td></tr>
  <tr><td>21</td><td>Auto-route to Lab Queue</td><td>QMS token issued for lab automatically when order placed — no staff intervention needed</td><td>Laboratory / QMS</td></tr>
  <tr><td>22</td><td>Specimen Logging</td><td>Lab tech logs specimen collection time, container type</td><td>Laboratory</td></tr>
  <tr><td>23</td><td>Result Entry &amp; Verification</td><td>Results entered, then verified by senior lab tech — two-step quality control</td><td>Laboratory</td></tr>
  <tr><td>24</td><td>Auto-return to Doctor</td><td>When ALL lab + investigation results verified → patient automatically returned to doctor queue</td><td>Laboratory / Core</td></tr>
  <tr><td>25</td><td>Lab Result PDF</td><td>Formal lab result printout with letterhead and verification signature</td><td>Laboratory</td></tr>

  <tr><td colspan="4" style="background:#d1e7dd;font-weight:700;color:#0a3622;">INVESTIGATIONS (EYE IMAGING)</td></tr>
  <tr><td>26</td><td>Investigation Order Placement</td><td>Doctor orders OCT, B-scan, FFA, Fundus from consultation</td><td>Investigations</td></tr>
  <tr><td>27</td><td>Auto-route to Investigation Queue</td><td>Same auto-routing as lab — patient sent to investigation workstation automatically</td><td>Investigations / QMS</td></tr>
  <tr><td>28</td><td>Result Upload &amp; Verification</td><td>Technician uploads images/findings, verifies, triggers auto-return to doctor</td><td>Investigations</td></tr>

  <tr><td colspan="4" style="background:#d1e7dd;font-weight:700;color:#0a3622;">PHARMACY</td></tr>
  <tr><td>29</td><td>Prescription Dispensing</td><td>Pharmacist receives, checks interactions, dispenses, patient signs</td><td>Pharmacy</td></tr>
  <tr><td>30</td><td>Drug Stock Management</td><td>Stock levels tracked, batch numbers, expiry dates, low-stock alerts</td><td>Pharmacy</td></tr>
  <tr><td>31</td><td>Pilferage Protection</td><td>Admin/CEO can view dispensing logs and flag discrepancies</td><td>Pharmacy</td></tr>
  <tr><td>32</td><td>Out-of-stock Flagging</td><td>Pharmacist flags unavailable drugs for patient awareness</td><td>Pharmacy</td></tr>

  <tr><td colspan="4" style="background:#d1e7dd;font-weight:700;color:#0a3622;">OPTICALS</td></tr>
  <tr><td>33</td><td>Frame Catalogue</td><td>Full catalogue of available frames with prices and stock</td><td>Opticals</td></tr>
  <tr><td>34</td><td>Optical Orders</td><td>Order created from refraction prescription, pickup date set</td><td>Opticals</td></tr>
  <tr><td>35</td><td>Optical Dispensing</td><td>Order completed, lens fitted, billed at cashier</td><td>Opticals</td></tr>

  <tr><td colspan="4" style="background:#d1e7dd;font-weight:700;color:#0a3622;">SURGICAL PATHWAY (IPD)</td></tr>
  <tr><td>36</td><td>Surgical Counseling Queue</td><td>Doctor refers → patient goes to counseling queue automatically</td><td>IPD</td></tr>
  <tr><td>37</td><td>Surgical Booking</td><td>Date, surgeon, theatre room, anaesthesia type, pre-op investigations</td><td>IPD</td></tr>
  <tr><td>38</td><td>Pre-op Checklist</td><td>Theatre nurse / admission officer checks consent, fasting, IV access, identity, allergies</td><td>IPD</td></tr>
  <tr><td>39</td><td>Ward Beds Management</td><td>Bed allocation, patient assignment to ward, occupancy tracking</td><td>IPD</td></tr>
  <tr><td>40</td><td>Anaesthetic Records</td><td>Full intraoperative anaesthesia documentation — JCI ASC.5 + ASC.6</td><td>IPD</td></tr>
  <tr><td>41</td><td>Nursing Care Plans</td><td>Post-op nursing diagnoses, interventions, goals — JCI COP.8</td><td>IPD</td></tr>
  <tr><td>42</td><td>Ward Round Documentation</td><td>Surgeon writes ward round notes for admitted patients</td><td>IPD</td></tr>
  <tr><td>43</td><td>Surgical Statistics</td><td>Admission stats, theatre utilisation, outcome reports</td><td>IPD / Reports</td></tr>

  <tr><td colspan="4" style="background:#d1e7dd;font-weight:700;color:#0a3622;">BILLING &amp; FINANCE</td></tr>
  <tr><td>44</td><td>Cashier POS</td><td>Invoice creation, payment (cash/mobile money/card), receipt, shift tracking</td><td>Billing</td></tr>
  <tr><td>45</td><td>Cashier Shift Management</td><td>Open day, individual shifts, closing declaration, variance calculation</td><td>Billing</td></tr>
  <tr><td>46</td><td>Cashier Desk Selection</td><td>Cashier selects their desk (Standard/VIP/Express/Insured) at login</td><td>Billing / Dashboard</td></tr>
  <tr><td>47</td><td>Invoice Lifecycle</td><td>Draft → Pending → Partial → Paid → Cancelled / Refunded / Waived</td><td>Billing</td></tr>
  <tr><td>48</td><td>Corporate Accounts</td><td>Credit limit, balance tracking, consolidated billing to company</td><td>Billing</td></tr>
  <tr><td>49</td><td>Proforma Invoices</td><td>Pre-treatment cost estimates for patients and corporates</td><td>Billing</td></tr>
  <tr><td>50</td><td>Refunds &amp; Waivers</td><td>Refund workflow with approval; fee waivers by Finance Director</td><td>Billing</td></tr>
  <tr><td>51</td><td>Expenses &amp; Petty Cash</td><td>Operating expense logging, petty cash fund management with approval</td><td>Billing</td></tr>
  <tr><td>52</td><td>Budget vs Actual</td><td>Monthly budget set, actual spending tracked and compared</td><td>Billing</td></tr>
  <tr><td>53</td><td>General Ledger</td><td>Chart of accounts, journal entries, trial balance, balance sheet, cash flow statement</td><td>Billing</td></tr>
  <tr><td>54</td><td>Accounts Payable</td><td>Vendor management, vendor bills, payment tracking</td><td>Billing</td></tr>
  <tr><td>55</td><td>Service Price Catalog</td><td>All service prices managed centrally by Finance Director</td><td>Billing</td></tr>
  <tr><td>56</td><td>All Finance PDFs</td><td>Daily summary, P&amp;L, AR aging, shift reconciliation, top services — all PDF with letterhead</td><td>Billing</td></tr>
  <tr><td>57</td><td>Sales Journal</td><td>Chronological record of all sales transactions</td><td>Billing</td></tr>
  <tr><td>58</td><td>Cash Desks Live View</td><td>Chief Cashier / Finance can see all cashier desks in real time</td><td>Billing</td></tr>

  <tr><td colspan="4" style="background:#d1e7dd;font-weight:700;color:#0a3622;">QUEUE MANAGEMENT (QMS)</td></tr>
  <tr><td>59</td><td>Digital Queue Tokens</td><td>Issued at every patient transition — reception, triage, doctor, lab, invest, pharmacy, cashier</td><td>QMS</td></tr>
  <tr><td>60</td><td>Display Board</td><td>Large-screen live queue board — now serving + next 5 tokens per counter</td><td>QMS</td></tr>
  <tr><td>61</td><td>Skip-Reason Audit</td><td>Every patient skip recorded with reason and staff identity — JCI compliant</td><td>QMS</td></tr>
  <tr><td>62</td><td>Nurse Triage Workstation</td><td>Dedicated triage workstation with scan bar and patient queue</td><td>QMS / Consultations</td></tr>
  <tr><td>63</td><td>Doctor Routing Panel</td><td>Doctor can see their queue, call next, skip with reason</td><td>QMS / Consultations</td></tr>
  <tr><td>64</td><td>QMS Optional</td><td>QMS can be disabled — all clinical modules work without it</td><td>QMS</td></tr>

  <tr><td colspan="4" style="background:#d1e7dd;font-weight:700;color:#0a3622;">HRMS &amp; ADMINISTRATION</td></tr>
  <tr><td>65</td><td>Staff Profiles</td><td>Employee records, role, department, contract, qualifications</td><td>HRMS</td></tr>
  <tr><td>66</td><td>Department Management</td><td>Create/edit departments, assign heads, manage members</td><td>Departments</td></tr>
  <tr><td>67</td><td>Leave Management</td><td>Leave request → approval workflow → leave calendar</td><td>HRMS</td></tr>
  <tr><td>68</td><td>Attendance Register</td><td>Daily attendance logging</td><td>HRMS</td></tr>
  <tr><td>69</td><td>Payroll</td><td>Monthly payroll runs, CNPS/tax deductions, payslip PDF</td><td>HRMS</td></tr>
  <tr><td>70</td><td>Fixed Asset Register</td><td>Assets with straight-line depreciation — annual, accumulated, net book value</td><td>Billing</td></tr>
  <tr><td>71</td><td>Inventory &amp; Stock</td><td>Medical supplies, consumables tracking</td><td>Inventory</td></tr>
  <tr><td>72</td><td>CSSD</td><td>Sterilization cycles, instrument tracking for theatre</td><td>CSSD</td></tr>

  <tr><td colspan="4" style="background:#d1e7dd;font-weight:700;color:#0a3622;">REPORTS &amp; ANALYTICS</td></tr>
  <tr><td>73</td><td>Leadership Dashboard</td><td>Hospital KPIs — patients, consultations, revenue, surgical stats</td><td>Leadership</td></tr>
  <tr><td>74</td><td>Monthly Statistics</td><td>Detailed monthly report — all departments, all metrics</td><td>Leadership</td></tr>
  <tr><td>75</td><td>Hospital Stats (Segmented)</td><td>Stats by specialty, tier, billing type, time period</td><td>Leadership</td></tr>
  <tr><td>76</td><td>Disease Burden Analytics</td><td>ICD-coded diagnosis frequency analysis — epidemiology view</td><td>Reports</td></tr>
  <tr><td>77</td><td>Revenue Report</td><td>12-month revenue trend, payment methods breakdown</td><td>Reports</td></tr>
  <tr><td>78</td><td>Staff Performance Report</td><td>Consultations per doctor, productivity metrics</td><td>Reports</td></tr>
  <tr><td>79</td><td>MOH Disease Export</td><td>CSV export of diagnosis data in Ministry of Health format</td><td>Reports</td></tr>
  <tr><td>80</td><td>Retina Outcomes Dashboard</td><td>Retina-specific surgical outcomes tracking</td><td>Leadership</td></tr>
  <tr><td>81</td><td>Finance Dashboard</td><td>Revenue vs expenses, cashier summary, AR balance — for Finance Director / CEO</td><td>Leadership</td></tr>
  <tr><td>82</td><td>Audit Log</td><td>Full system audit trail — every staff action logged with timestamp</td><td>Core</td></tr>

  <tr><td colspan="4" style="background:#d1e7dd;font-weight:700;color:#0a3622;">AI &amp; SYSTEM</td></tr>
  <tr><td>83</td><td>Clinical AI Assistant</td><td>AI-assisted clinical decision support — diagnosis suggestions, drug guidance</td><td>AI</td></tr>
  <tr><td>84</td><td>AI Virtual Receptionist</td><td>AI-powered appointment booking assistant</td><td>AI</td></tr>
  <tr><td>85</td><td>AI Analytics</td><td>Hospital-wide AI analytics and insight generation</td><td>AI</td></tr>
  <tr><td>86</td><td>Automated Daily Backup</td><td>Celery Beat runs backup at 02:00 daily — BackupLog tracks success/failure</td><td>Core</td></tr>
  <tr><td>87</td><td>Health Check Dashboard</td><td>Server CPU, RAM, disk, service status — for Super Admin</td><td>Core</td></tr>
  <tr><td>88</td><td>Patient Feedback / NPS</td><td>Patient satisfaction surveys, NPS scoring, complaints and service recovery</td><td>Feedback</td></tr>
  <tr><td>89</td><td>Outreach Module</td><td>Community outreach campaigns, lead management</td><td>Outreach</td></tr>
  <tr><td>90</td><td>HospitalConfig Module Flags</td><td>Each module can be enabled/disabled without code changes</td><td>Core</td></tr>
</table>

<h2>14.2 What is PARTIALLY BUILT (Needs Completion)</h2>
<table class="mod-table">
  <tr><th style="width:5%">#</th><th style="width:28%">Feature</th><th style="width:35%">What's Done</th><th style="width:32%">What's Missing</th></tr>

  <tr><td>1</td><td><strong>VIP / Express Tier Patient Flow</strong></td><td>Cashier desk selection (Standard/VIP/Express/Insured) implemented. Cashier station field on User model.</td><td>Separate VIP and Express QMS queues not fully routed. Doctor workstation doesn't filter by tier. Priority token ordering not enforced end-to-end.</td></tr>

  <tr><td>2</td><td><strong>Stats / Analytics PDF Export</strong></td><td>Revenue report, disease burden, staff performance pages exist with Chart.js charts and data tables. Print CSS hides charts.</td><td>No dedicated WeasyPrint PDF button for stats pages. When printing, charts disappear but tables show. A proper ?format=pdf button with a PDF-optimised template is missing for each stats page.</td></tr>

  <tr><td>3</td><td><strong>Lab Reference Ranges</strong></td><td>Lab results can be entered and verified.</td><td>No normal/abnormal reference ranges per test type. No automatic flagging of out-of-range values (high/low markers). No critical value alert to doctor.</td></tr>

  <tr><td>4</td><td><strong>Vital Signs Trends</strong></td><td>IOP trend chart across visits is done (glaucoma monitoring). Vitals recorded at triage.</td><td>BP, pulse, weight trends over multiple visits not charted. No longitudinal vital signs dashboard for chronic patients.</td></tr>

  <tr><td>5</td><td><strong>Inventory Auto-reorder</strong></td><td>Low-stock alerts exist in pharmacy and inventory.</td><td>No auto-purchase order generation when stock falls below minimum. No supplier integration for automated reorder. Manual reorder only.</td></tr>

  <tr><td>6</td><td><strong>Insurance / CNPS Billing</strong></td><td>Corporate accounts with credit limits. Corporate billing flow implemented.</td><td>No real-time CNPS/NHIS insurance verification API. No electronic claim submission. No claim status tracking. Manual reconciliation with insurer required.</td></tr>

  <tr><td>7</td><td><strong>Surgical Outcome Registry</strong></td><td>Surgical records documented. Post-op follow-up visits linkable to surgery episode.</td><td>No formal long-term surgical outcome registry (visual acuity before vs after, complication rates, re-operation rates). No outcome analytics dashboard.</td></tr>

  <tr><td>8</td><td><strong>Medical Certificate Generation</strong></td><td>Clinical records and diagnoses fully documented.</td><td>No one-click medical certificate or sick leave certificate PDF generation from consultation records.</td></tr>

  <tr><td>9</td><td><strong>MOH Reporting</strong></td><td>MOH disease export as CSV exists.</td><td>No automated MOH submission. No standardised DHIS2 data push. No MOH-format PDF report generation.</td></tr>

  <tr><td>10</td><td><strong>Pharmacy Barcode Dispensing</strong></td><td>Pharmacy dispensing workflow complete.</td><td>No barcode scan on individual drug packs at point of dispensing. No verification that the right drug/batch was picked from the shelf.</td></tr>
</table>

<h2>14.3 What is COMPLETELY MISSING (Not Yet Built)</h2>
<table class="mod-table">
  <tr><th style="width:5%">#</th><th style="width:30%">Feature</th><th style="width:45%">Description</th><th style="width:20%">Priority</th></tr>

  <tr><td colspan="4" style="background:#f8d7da;font-weight:700;color:#58151c;">PATIENT-FACING FEATURES</td></tr>
  <tr><td>1</td><td><strong>Patient Web Portal</strong></td><td>Patients cannot self-register online, view their records, download results, or see upcoming appointments from outside the hospital. No patient-facing login.</td><td><span class="badge badge-red">HIGH</span></td></tr>
  <tr><td>2</td><td><strong>Online Appointment Booking</strong></td><td>No public-facing appointment booking page. Patients must call or come in person to book.</td><td><span class="badge badge-red">HIGH</span></td></tr>
  <tr><td>3</td><td><strong>SMS / WhatsApp Notifications</strong></td><td>No appointment reminders sent to patients. No prescription ready alerts. No discharge summary sent by SMS. No integration with Orange SMS, MTN, or WhatsApp Business API.</td><td><span class="badge badge-red">HIGH</span></td></tr>
  <tr><td>4</td><td><strong>Patient Mobile App</strong></td><td>No iOS or Android app for patients. No mobile appointment booking, no e-card, no result viewing.</td><td><span class="badge badge-gold">MEDIUM</span></td></tr>
  <tr><td>5</td><td><strong>Self-registration Kiosk</strong></td><td>No touch-screen kiosk for patients to self-check-in at the gate or reception.</td><td><span class="badge badge-gold">MEDIUM</span></td></tr>

  <tr><td colspan="4" style="background:#f8d7da;font-weight:700;color:#58151c;">CLINICAL FEATURES</td></tr>
  <tr><td>6</td><td><strong>Telemedicine / Video Consultation</strong></td><td>No video call capability. Doctors cannot do remote consultations. No telemedicine module.</td><td><span class="badge badge-red">HIGH</span></td></tr>
  <tr><td>7</td><td><strong>DICOM Medical Imaging Viewer</strong></td><td>OCT, B-scan, and other eye imaging machines produce DICOM files. The system stores text findings but cannot display or import DICOM images directly. No PACS integration.</td><td><span class="badge badge-red">HIGH</span></td></tr>
  <tr><td>8</td><td><strong>Lab Analyser Integration (LIS)</strong></td><td>Lab results are entered manually. No automated import from blood analyzers or other lab equipment. No HL7/ASTM interface.</td><td><span class="badge badge-red">HIGH</span></td></tr>
  <tr><td>9</td><td><strong>Biometric Patient Identification</strong></td><td>No fingerprint or iris scan for patient identification. All identification is by ID card or barcode.</td><td><span class="badge badge-gold">MEDIUM</span></td></tr>
  <tr><td>10</td><td><strong>Referral Network</strong></td><td>No ability to formally refer patients to another hospital and track the referral outcome. No inter-hospital communication.</td><td><span class="badge badge-gold">MEDIUM</span></td></tr>
  <tr><td>11</td><td><strong>Clinical Decision Support Rules</strong></td><td>Beyond drug interaction checking, no rule-based clinical alerts (e.g. IOP &gt; 21 triggers glaucoma alert, abnormal lab values trigger doctor notification).</td><td><span class="badge badge-gold">MEDIUM</span></td></tr>
  <tr><td>12</td><td><strong>Discharge Summary PDF</strong></td><td>No auto-generated discharge summary PDF with diagnosis, procedures done, drugs on discharge, follow-up plan, and surgeon signature.</td><td><span class="badge badge-red">HIGH</span></td></tr>
  <tr><td>13</td><td><strong>Medical Certificate / Sick Note PDF</strong></td><td>No one-click sick leave or fitness certificate generation from consultation.</td><td><span class="badge badge-gold">MEDIUM</span></td></tr>
  <tr><td>14</td><td><strong>Prescription Print / e-Prescription</strong></td><td>No formatted prescription printout that patient can take to external pharmacy. No e-prescription integration with pharmacy chains.</td><td><span class="badge badge-red">HIGH</span></td></tr>

  <tr><td colspan="4" style="background:#f8d7da;font-weight:700;color:#58151c;">FINANCIAL FEATURES</td></tr>
  <tr><td>15</td><td><strong>Insurance / CNPS API Integration</strong></td><td>No real-time electronic verification with CNPS or private insurers. Claims are managed manually outside the system.</td><td><span class="badge badge-red">HIGH</span></td></tr>
  <tr><td>16</td><td><strong>Payment Gateway Integration</strong></td><td>Cash and mobile money recorded manually. No automated integration with Orange Money API, MTN Mobile Money API, or card payment terminals.</td><td><span class="badge badge-red">HIGH</span></td></tr>
  <tr><td>17</td><td><strong>Financial Forecasting</strong></td><td>No AI-based revenue forecasting, expense prediction, or cash flow projections for next month/quarter.</td><td><span class="badge badge-gray">LOW</span></td></tr>
  <tr><td>18</td><td><strong>Supplier Purchase Orders</strong></td><td>Accounts Payable has vendor bills but no formal purchase order (PO) generation with approval workflow before bill receipt.</td><td><span class="badge badge-gold">MEDIUM</span></td></tr>

  <tr><td colspan="4" style="background:#f8d7da;font-weight:700;color:#58151c;">OPERATIONAL &amp; INFRASTRUCTURE</td></tr>
  <tr><td>19</td><td><strong>Offline / Low-connectivity Mode</strong></td><td>System requires LAN connection at all times. If the server goes down or network is cut, no one can work. No offline-first capability.</td><td><span class="badge badge-red">HIGH</span></td></tr>
  <tr><td>20</td><td><strong>Multi-branch Support</strong></td><td>System is single-site only. If the hospital opens a second branch, a completely separate installation is needed. No shared patient records, no consolidated reporting across branches.</td><td><span class="badge badge-gold">MEDIUM</span></td></tr>
  <tr><td>21</td><td><strong>Document Scanning &amp; Storage</strong></td><td>No ability to scan and attach physical documents (referral letters, external lab reports, ID cards) to a patient record.</td><td><span class="badge badge-gold">MEDIUM</span></td></tr>
  <tr><td>22</td><td><strong>Multi-language (French)</strong></td><td>All screens are in English only. Cameroon is bilingual — many staff and patients read French. No French interface or French PDF reports.</td><td><span class="badge badge-red">HIGH</span></td></tr>
  <tr><td>23</td><td><strong>Two-Factor Authentication (2FA)</strong></td><td>Staff log in with username + password only. No 2FA, no session timeout on sensitive roles, no IP restriction for Finance Director / CEO access.</td><td><span class="badge badge-gold">MEDIUM</span></td></tr>
  <tr><td>24</td><td><strong>Role-based Data Export Controls</strong></td><td>Any authorised user can export CSVs. No watermarking of exports, no DLP (data loss prevention) controls on bulk patient data exports.</td><td><span class="badge badge-gold">MEDIUM</span></td></tr>
  <tr><td>25</td><td><strong>Bed Occupancy Real-time Board</strong></td><td>Ward beds tracked in the system but no live visual board (like a hospital floor plan showing occupied/free beds in real time) for the ward manager.</td><td><span class="badge badge-gold">MEDIUM</span></td></tr>
</table>

<!-- ═══════════════════════════════════════════════════════ PART 15 -->
<div class="part">PART 15 — RECOMMENDED BUILD ORDER (WHAT TO DO NEXT)</div>

<h2>15.1 Immediate Priority (Complete These First)</h2>
<div class="info-box">
  <strong>Why these first:</strong> These are features that directly affect daily patient care quality, revenue capture, and legal compliance. Staff are already requesting them or workarounds are creating inefficiencies.
</div>
<table class="mod-table">
  <tr><th>#</th><th>What to Build</th><th>Why It's Urgent</th><th>Estimated Complexity</th></tr>
  <tr><td>1</td><td><strong>VIP / Express Tier Flow (End-to-End)</strong></td><td>Currently cashiers select a desk but VIP patients are not truly separated in the QMS routing. Completing this means VIP patients get genuine priority and dedicated cashier from gate to exit.</td><td><span class="badge badge-gold">Medium</span></td></tr>
  <tr><td>2</td><td><strong>Prescription Print PDF</strong></td><td>When a doctor writes a prescription, patients need a formatted paper prescription to take to the hospital pharmacy or external pharmacy. Without this, a core clinical output is missing.</td><td><span class="badge badge-green">Low</span></td></tr>
  <tr><td>3</td><td><strong>Discharge Summary PDF</strong></td><td>Every discharged surgical patient needs a formal document. Required for JCI, for insurance claims, and for the patient's GP/referral doctor.</td><td><span class="badge badge-gold">Medium</span></td></tr>
  <tr><td>4</td><td><strong>SMS / WhatsApp Appointment Reminders</strong></td><td>Reduces no-show rate. Most effective patient engagement tool. Can use Africa's Talking or Twilio for SMS, or WhatsApp Business API.</td><td><span class="badge badge-gold">Medium</span></td></tr>
  <tr><td>5</td><td><strong>Stats Pages — PDF Export Button</strong></td><td>Finance Director and CEO need to download proper PDFs of revenue, staff performance, and disease burden reports — not just browser print. Add ?format=pdf to each stats page.</td><td><span class="badge badge-green">Low</span></td></tr>
  <tr><td>6</td><td><strong>Lab Reference Ranges &amp; Abnormal Flagging</strong></td><td>Lab results without normal ranges are clinically incomplete. Doctors need to see which values are HIGH or LOW at a glance — standard in any lab system.</td><td><span class="badge badge-gold">Medium</span></td></tr>
  <tr><td>7</td><td><strong>French Language Support</strong></td><td>Many staff in Cameroon are French-speaking. Key patient-facing documents (receipts, prescriptions, discharge summaries) should be available in French.</td><td><span class="badge badge-red">High Effort</span></td></tr>
</table>

<h2>15.2 Short-term Priority (Next 3 Months)</h2>
<table class="mod-table">
  <tr><th>#</th><th>What to Build</th><th>Notes</th></tr>
  <tr><td>1</td><td>Online Appointment Booking</td><td>Public-facing page. Patient selects doctor, date, time. Confirmation email/SMS sent. Links to existing appointments module.</td></tr>
  <tr><td>2</td><td>Medical Certificate / Sick Note PDF</td><td>One-click generation from consultation. Doctor name, stamp, diagnosis, recommended rest period.</td></tr>
  <tr><td>3</td><td>Insurance Claim Management</td><td>Track CNPS and private insurer claims — claim number, submission date, approval status, payment received. Even without API, a structured tracking system reduces revenue leakage.</td></tr>
  <tr><td>4</td><td>Vital Signs Trends</td><td>BP, pulse, weight, temperature plotted over multiple visits. Especially important for diabetic patients, hypertension monitoring, glaucoma.</td></tr>
  <tr><td>5</td><td>Surgical Outcome Registry</td><td>Track best-corrected visual acuity before and after surgery. Complication rates. Re-operation rates. Essential for JCI quality indicators and eye bank accreditation.</td></tr>
  <tr><td>6</td><td>Document Scanning &amp; Attachment</td><td>Allow staff to upload and attach scanned documents (referral letters, external results, ID scans) to any patient record.</td></tr>
  <tr><td>7</td><td>Purchase Orders for Inventory</td><td>Create PO → approve → receive → auto-update stock. Closes the procurement gap in accounts payable.</td></tr>
</table>

<h2>15.3 Medium-term Priority (3–6 Months)</h2>
<table class="mod-table">
  <tr><th>#</th><th>What to Build</th><th>Notes</th></tr>
  <tr><td>1</td><td>DICOM Viewer Integration</td><td>Connect to OCT machine, B-scan machine. View DICOM files inside the patient record. Requires PACS server (Orthanc is free/open-source).</td></tr>
  <tr><td>2</td><td>Lab Analyser Auto-import (LIS)</td><td>Connect to blood analysers via serial/HL7. Auto-populate lab results. Eliminates manual entry errors.</td></tr>
  <tr><td>3</td><td>Payment Gateway (MTN / Orange Money)</td><td>Auto-confirm mobile money payments via API. Reduces fraud, eliminates manual verification.</td></tr>
  <tr><td>4</td><td>Patient Web Portal</td><td>Patient login, view records, download results, see appointments. Django can serve this as an extension of the existing app.</td></tr>
  <tr><td>5</td><td>Offline Mode / PWA</td><td>Progressive Web App with service workers. At minimum, allow triage to work offline (store data locally, sync when connection returns).</td></tr>
  <tr><td>6</td><td>Clinical Decision Support Rules</td><td>Rule engine: IOP &gt; 21 + cup-to-disc &gt; 0.6 → glaucoma risk alert. Abnormal lab → push notification to doctor. Configurable by Medical Director.</td></tr>
  <tr><td>7</td><td>Two-Factor Authentication</td><td>For Finance Director, CEO, Senior Accountant, Super Admin — TOTP or SMS OTP at login.</td></tr>
</table>

<h2>15.4 Long-term Vision (6+ Months)</h2>
<table class="mod-table">
  <tr><th>#</th><th>Feature</th><th>Notes</th></tr>
  <tr><td>1</td><td>Telemedicine</td><td>Video consultation via WebRTC (Jitsi Meet self-hosted). Doctor joins from their workstation. Patient connects via phone/tablet.</td></tr>
  <tr><td>2</td><td>Multi-branch Support</td><td>Shared patient database across branches. Separate financial reporting per branch. Consolidated CEO view. Requires significant architectural work.</td></tr>
  <tr><td>3</td><td>Patient Mobile App</td><td>React Native / Flutter app. Appointment booking, results, e-card, pharmacy status, wallet top-up.</td></tr>
  <tr><td>4</td><td>CNPS / NHIS API Integration</td><td>Real-time insurance eligibility check at registration. Electronic claim submission. Requires government API access agreement.</td></tr>
  <tr><td>5</td><td>Biometric Identification</td><td>Fingerprint scanner at reception. Links fingerprint to patient record. Eliminates wrong-patient errors entirely.</td></tr>
  <tr><td>6</td><td>AI Diagnostic Imaging</td><td>AI analysis of fundus photos and OCT scans for diabetic retinopathy, glaucoma, AMD grading. Requires trained ML models or third-party API (e.g. Retinal AI).</td></tr>
  <tr><td>7</td><td>National Disease Registry Integration</td><td>Automated push to national blindness registry, MOH DHIS2 platform for epidemiological surveillance.</td></tr>
</table>

<h2>15.5 Summary Score Card</h2>
<table class="mod-table">
  <tr><th>Category</th><th>Status</th><th>Completeness</th></tr>
  <tr><td>Patient Registration &amp; Records</td><td><span class="badge badge-green">COMPLETE</span></td><td>95% — missing document scanning</td></tr>
  <tr><td>Clinical Workflow (Triage to Consultation)</td><td><span class="badge badge-green">COMPLETE</span></td><td>95% — missing prescription print PDF</td></tr>
  <tr><td>Laboratory</td><td><span class="badge badge-gold">NEAR COMPLETE</span></td><td>85% — missing reference ranges &amp; auto-import</td></tr>
  <tr><td>Investigations (Eye Imaging)</td><td><span class="badge badge-gold">NEAR COMPLETE</span></td><td>80% — missing DICOM viewer</td></tr>
  <tr><td>Pharmacy</td><td><span class="badge badge-green">COMPLETE</span></td><td>90% — missing barcode dispense verify</td></tr>
  <tr><td>Opticals</td><td><span class="badge badge-green">COMPLETE</span></td><td>90%</td></tr>
  <tr><td>Surgical Pathway</td><td><span class="badge badge-gold">NEAR COMPLETE</span></td><td>85% — missing discharge summary PDF &amp; outcome registry</td></tr>
  <tr><td>Billing &amp; Finance</td><td><span class="badge badge-green">COMPLETE</span></td><td>90% — missing payment gateway API</td></tr>
  <tr><td>QMS (Queue Management)</td><td><span class="badge badge-gold">NEAR COMPLETE</span></td><td>85% — VIP/Express tier routing incomplete</td></tr>
  <tr><td>HRMS</td><td><span class="badge badge-green">COMPLETE</span></td><td>90%</td></tr>
  <tr><td>Reports &amp; Analytics</td><td><span class="badge badge-gold">NEAR COMPLETE</span></td><td>80% — missing stats page PDF buttons, outcome reports</td></tr>
  <tr><td>Patient-facing Features</td><td><span class="badge badge-red">NOT STARTED</span></td><td>5% — only AI receptionist exists</td></tr>
  <tr><td>External Integrations (APIs)</td><td><span class="badge badge-red">NOT STARTED</span></td><td>0% — all manual</td></tr>
  <tr><td>Offline / Multi-branch</td><td><span class="badge badge-red">NOT STARTED</span></td><td>0%</td></tr>
  <tr><td>JCI Compliance</td><td><span class="badge badge-green">LARGELY COMPLETE</span></td><td>85% — key standards covered</td></tr>
  <tr><td style="font-weight:700;">OVERALL SYSTEM</td><td><span class="badge badge-blue">PRODUCTION READY (Core)</span></td><td style="font-weight:700;">~82% of an enterprise hospital system</td></tr>
</table>

<div class="pdf-footer" style="margin-top:40px; border-top:1px solid #dee2e6; padding-top:10px; font-size:8pt; color:#888; text-align:center;">
  EHR Africa — Complete System Documentation v1.0 — July 2026 — CONFIDENTIAL
</div>

</body>
</html>"""


def generate_pdf():
    import os
    import sys
    import platform

    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_pdf  = os.path.join(base_dir, "EHR_AFRICA_SYSTEM_DOCUMENTATION.pdf")
    output_html = os.path.join(base_dir, "EHR_AFRICA_SYSTEM_DOCUMENTATION.html")

    # On Windows WeasyPrint needs GTK — skip directly to HTML + print instructions
    if platform.system() == "Windows":
        with open(output_html, "w", encoding="utf-8") as f:
            f.write(HTML_CONTENT)
        print(f"HTML saved: {output_html}")
        print()
        print("TO GENERATE THE PDF (Windows steps):")
        print("  1. Open the HTML file in Google Chrome or Microsoft Edge")
        print("  2. Press Ctrl+P  (Print)")
        print("  3. Destination: Save as PDF")
        print("  4. Paper size: A4  |  Margins: Default  |  Background graphics: ON")
        print("  5. Click Save -> name it EHR_AFRICA_SYSTEM_DOCUMENTATION.pdf")
        print()
        print("OR: On the production Linux server run:")
        print(f"  python generate_system_docs.py")
        print("  (WeasyPrint works natively on Linux with GTK installed)")
        return

    # Linux / Mac — try WeasyPrint
    try:
        from weasyprint import HTML
        print("Generating PDF with WeasyPrint...")
        HTML(string=HTML_CONTENT, base_url="/").write_pdf(output_pdf)
        print(f"SUCCESS: {output_pdf}")
    except Exception as e:
        print(f"WeasyPrint error: {e}")
        with open(output_html, "w", encoding="utf-8") as f:
            f.write(HTML_CONTENT)
        print(f"HTML fallback saved: {output_html}")


if __name__ == "__main__":
    generate_pdf()
