"""Generate 4 Workflow Guide PDFs using ReportLab (no HTML markup)."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
import datetime, os

W, H = A4
today = datetime.date.today().strftime('%d %B %Y')
OUT = 'c:/Users/GROD/Desktop/EHR AFRICA BACKUP/workflow_guides'
os.makedirs(OUT, exist_ok=True)

# ─── Styles ─────────────────────────────────────────────────────────────────
def S(name, **kw):
    return ParagraphStyle(name, fontName=kw.pop('font','Helvetica'),
                          fontSize=kw.pop('size',9), leading=kw.pop('leading',13),
                          textColor=kw.pop('color', black), **kw)

sHdr1  = S('h1', font='Helvetica-Bold', size=18, color=white, leading=22)
sHdr2  = S('h2', font='Helvetica',      size=9,  color=white, leading=13)
sHdrLbl= S('hl', font='Helvetica',      size=6.5,color=HexColor('#ffffff'), leading=9)
sMeta_l= S('ml', font='Helvetica',      size=6,  color=HexColor('#64748b'), leading=8)
sMeta_v= S('mv', font='Helvetica-Bold', size=8,  color=black, leading=11)
sSecHdr= S('sh', font='Helvetica-Bold', size=10, leading=14)
sStepT = S('st', font='Helvetica-Bold', size=10.5, leading=14)
sStepTC= S('stc',font='Helvetica-Bold', size=10.5, leading=14, color=HexColor('#dc2626'))
sRole  = S('sr', font='Helvetica-Bold', size=7.5, color=HexColor('#4b5563'), leading=10)
sRoleC = S('src',font='Helvetica-Bold', size=7.5, color=HexColor('#dc2626'), leading=10)
sScreen= S('ss', font='Helvetica',      size=7.5, color=HexColor('#64748b'), leading=10)
sBullet= S('sb', font='Helvetica',      size=8.5, color=HexColor('#1e293b'), leading=12,
           leftIndent=8, firstLineIndent=0)
sBulletW=S('sbw',font='Helvetica-Bold', size=8.5, color=HexColor('#dc2626'), leading=12,
           leftIndent=8, firstLineIndent=0)
sNote  = S('sn', font='Helvetica',      size=8.5, leading=12)
sNoteLbl=S('snl',font='Helvetica-Bold', size=8.5, leading=12)
sFootL = S('sfl',font='Helvetica',      size=7, color=HexColor('#94a3b8'), leading=10)
sFootR = S('sfr',font='Helvetica',      size=7, color=HexColor('#94a3b8'), leading=10, alignment=TA_RIGHT)
sNumW  = S('snw',font='Helvetica-Bold', size=11, color=white, alignment=TA_CENTER, leading=14)
sFlowNode=S('fn',font='Helvetica-Bold', size=6,  color=white, alignment=TA_CENTER, leading=9)

CASH_BG = HexColor('#fff1f2')
CASH_COL= HexColor('#dc2626')

# ─── Flow definitions ────────────────────────────────────────────────────────
FLOWS = [
  {
    'fname': '1. Standard Patient Flow',
    'title': 'Standard Patient Flow',
    'subtitle': 'New or returning patient  |  Pay at CASHIER AFTER consultation',
    'accent': HexColor('#1d4ed8'), 'light': HexColor('#dbeafe'),
    'meta': [('Flow Type','Standard'),('Avg Duration','45-90 min'),('Starts At','Hospital Gate'),
             ('Ends At','Pharmacy / Exit'),('QMS','Required'),('Payment','AFTER consultation at Cashier')],
    'flow': ['Gate','Registration','Triage','Doctor Queue','Consultation',
             '** CASHIER **','Pharmacy','Lab / Imaging','Exit'],
    'steps': [
      (False,'1','Patient Arrives at Hospital Gate','Gate Staff',
       'QMS > Gate Ticket Issue',
       ['Gate staff issues QMS ticket to patient.',
        'Select patient type: New or Returning.',
        'Select destination: OPD / Consultation.',
        'Print ticket and direct patient to Registration counter.']),
      (False,'2','Registration / Patient Check-In','Receptionist',
       'Patients > Register  OR  Patients > Search',
       ['NEW patient: complete full registration (name, DOB, phone, address, next-of-kin, ID).',
        'RETURNING patient: search by name or Patient ID, open record, confirm details.',
        'Assign or confirm Visit for today.']),
      (False,'3','Triage - Vitals & Chief Complaint','OPD / Triage Nurse',
       'Consultations > Triage Workstation',
       ['Open patient in Triage Workstation.',
        'Record Visual Acuity (VA): right eye and left eye - unaided and aided.',
        'Record Intraocular Pressure (IOP), blood pressure, weight if relevant.',
        'Record Chief Complaint (reason for visit).',
        'Note any known allergies or urgent symptoms.',
        'Click Submit Triage - patient enters doctor queue automatically.']),
      (False,'4','Doctor Queue - Patient Waiting','QMS Display / Nurse Dispatcher',
       'QMS > Doctor Queue',
       ['Patient waits to be called - queue board shows ticket number and room.',
        'Nurse/dispatcher calls next patient from the doctor queue screen.']),
      (False,'5','Doctor Consultation','Ophthalmologist / Doctor',
       'Consultations > Workstation',
       ['Open patient from the queue - vitals pre-populated from triage.',
        'Select Consultation Type (Gen Ophthalmology, Retina, Glaucoma, Cataract, etc.).',
        'Complete clinical examination form.',
        'Add Diagnosis (ICD-10 codes).',
        'Issue orders: Drug Prescription > Pharmacy | Lab Order > Laboratory | Investigation > Imaging.',
        'Click Complete Consultation.',
        'Optionally book Follow-up Appointment.']),
      (True,'6','CASHIER - PATIENT PAYS (MANDATORY STOP)','Cashier',
       'Billing > Cashier POS  OR  Billing > Work Queue',
       ['EVERY PATIENT MUST PAY AT THE CASHIER BEFORE RECEIVING MEDICATION.',
        'Cashier searches patient by name or Patient ID.',
        'Pending charges appear automatically: consultation fee + any ordered services.',
        'Select payment method: Cash / Mobile Money / Card.',
        'Process payment - system generates Receipt automatically.',
        'PHARMACY WILL NOT RELEASE MEDICATION UNTIL PAYMENT IS CONFIRMED IN SYSTEM.',
        'Print or show digital receipt to patient.']),
      (False,'7','Pharmacy - Medication Dispensing','Pharmacist',
       'Pharmacy > Dispensing Queue',
       ['Prescription appears in dispensing queue ONLY after payment is confirmed.',
        'Pharmacist reviews drug list and checks for interactions.',
        'Dispense medications and mark as dispensed.',
        'Counsel patient on dosage and instructions.']),
      (False,'8','Laboratory / Investigations (if ordered)','Lab Tech / Investigation Tech',
       'Investigations > Workstation  OR  Laboratory > Dashboard',
       ['Patient goes to lab/imaging unit with order slip.',
        'Tech locates order in workstation queue and performs test.',
        'Enter results into system - report auto-linked to patient record.',
        'Doctor is notified of completed results.']),
      (False,'9','Patient Exit / Discharge','Receptionist / Gate Staff',
       'Visit marked Completed automatically on payment',
       ['Patient collects medication from pharmacy.',
        'If follow-up was booked, patient receives appointment card or SMS.',
        'Patient exits - QMS token closed.']),
    ],
    'note': 'KEY RULE: Payment at the Cashier (Step 6) is MANDATORY for ALL standard patients. The pharmacy will NOT release medication until the invoice is marked PAID. No exceptions.',
    'warn': 'DRY RUN CHECKLIST: QMS display working > Registration creates patient > Triage workstation accessible > Doctor queue loads > Cashier POS processes test payment > Pharmacy queue shows prescription ONLY after payment confirmed.',
  },
  {
    'fname': '2. VIP Patient Flow',
    'title': 'VIP Patient Flow',
    'subtitle': 'Private / VIP patient  |  Dedicated VIP cashier terminal  |  No main queue waiting',
    'accent': HexColor('#b45309'), 'light': HexColor('#fef3c7'),
    'meta': [('Flow Type','VIP'),('Avg Duration','20-45 min'),('Starts At','VIP Reception'),
             ('Ends At','Pharmacy / VIP Exit'),('QMS','VIP Priority Channel'),
             ('Payment','VIP Cashier desk - MANDATORY')],
    'flow': ['VIP Arrival','VIP Reception','Nurse (Bedside)','VIP Consult',
             '** VIP CASHIER **','Priority Pharmacy','VIP Exit'],
    'steps': [
      (False,'1','VIP Patient Arrives','VIP Receptionist / Security',
       'QMS > VIP Reception',
       ['VIP patient uses dedicated VIP entrance.',
        'Security notifies VIP reception immediately.',
        'No gate queue ticket - VIP patients skip the standard gate process.',
        'VIP receptionist greets patient and escorts to VIP desk.',
        'Open QMS > VIP Reception to log arrival and issue VIP token.']),
      (False,'2','VIP Check-In & Registration','VIP Receptionist',
       'Patients > Search  OR  Patients > Register',
       ['RETURNING VIP: search and open existing record, confirm demographics.',
        'NEW VIP: complete full registration - VIP tag noted in record.',
        'Confirm pre-booked appointment if applicable.',
        'Notify the assigned doctor immediately by phone/intercom.']),
      (False,'3','Nurse Assessment (Bedside in VIP Room)','OPD Nurse',
       'Consultations > Triage Workstation',
       ['Nurse goes to VIP consultation room, takes vitals bedside (not at triage bay).',
        'Record VA, IOP, blood pressure, chief complaint in system.',
        'No queue - results go directly to attending doctor\'s workstation.']),
      (False,'4','VIP Consultation - Doctor','Senior Ophthalmologist',
       'Consultations > Workstation > VIP Consultation Room',
       ['Doctor opens patient - triage vitals already populated.',
        'Select department: VIP Consultation Room.',
        'Perform full clinical examination.',
        'Add diagnoses, issue prescriptions, lab or investigation orders.',
        'Print Consultation Summary for patient if needed.',
        'Book follow-up appointment if required.']),
      (True,'5','VIP CASHIER - PATIENT PAYS (MANDATORY STOP)','VIP Receptionist / Cashier',
       'Billing > Cashier POS (at the dedicated VIP terminal)',
       ['ALL VIP PATIENTS MUST PAY BEFORE LEAVING - NO EXCEPTIONS.',
        'VIP patients pay at the DEDICATED VIP CASHIER TERMINAL (not the main cashier queue).',
        'The VIP terminal is faster and more private - but payment process is the same.',
        'Invoice is auto-generated from the consultation orders.',
        'Accept: Cash, card, mobile money, or corporate account charge.',
        'PAYMENT MUST BE CONFIRMED BEFORE PHARMACY RELEASES MEDICATION.',
        'Print official receipt for patient.']),
      (False,'6','Priority Pharmacy Dispensing','Pharmacist',
       'Pharmacy > Dispensing Queue',
       ['Prescription appears ONLY after VIP cashier confirms payment.',
        'Pharmacist prioritises VIP prescription above regular queue.',
        'Medications delivered to VIP lounge or reception desk.',
        'Counsel patient on dosage.']),
      (False,'7','VIP Exit','VIP Receptionist','',
       ['Escort patient to exit or vehicle if required.',
        'Provide appointment reminder card.',
        'Record satisfaction feedback in Feedback module.']),
    ],
    'note': 'VIP SERVICE STANDARD: Max wait between any step is 5 minutes. Doctor and nurse must be notified as soon as VIP patient arrives - not when called.',
    'warn': 'IMPORTANT: VIP patients STILL PAY. They use a dedicated VIP cashier terminal (not the main cashier queue). Do NOT skip the payment step. System enforces this - pharmacy will not release until paid.',
  },
  {
    'fname': '3. Express Fast Track Flow',
    'title': 'Express / Fast Track Patient Flow',
    'subtitle': 'Patient pays cashier FIRST  |  Gets priority queue ticket  |  Seen before standard patients',
    'accent': HexColor('#059669'), 'light': HexColor('#d1fae5'),
    'meta': [('Flow Type','Express / Fast Track'),('Avg Duration','15-35 min'),
             ('Starts At','Express Cashier Desk'),('Ends At','Pharmacy / Exit'),
             ('QMS','Express Priority Queue'),('Payment','BEFORE consultation - pays cashier first')],
    'flow': ['Arrival','** CASHIER (PAY FIRST) **','Express Ticket','Brief Triage',
             'Priority Consult','Pharmacy','Exit'],
    'steps': [
      (False,'1','Patient Arrives & Requests Express Service','Gate Staff / Receptionist',
       'QMS > Gate Issue',
       ['Patient arrives and requests Express / Fast Track service.',
        'Gate staff directs them to the EXPRESS CASHIER DESK - skips standard registration queue.',
        'Returning patients already registered; new patients registered at the express desk.']),
      (True,'2','EXPRESS CASHIER DESK - PATIENT PAYS FIRST (START HERE)','Cashier (Express Desk)',
       'Billing > Cashier POS (Express terminal)  +  QMS > Express Desk',
       ['THIS IS THE FIRST STOP - patient pays consultation fee BEFORE seeing the doctor.',
        'Search for existing patient or do quick registration if new.',
        'Create invoice for Consultation Fee (Express rate if applicable).',
        'COLLECT PAYMENT NOW: Cash / Mobile Money / Card.',
        'Issue payment receipt to patient.',
        'Open QMS > Express Desk and issue Express Priority Ticket.',
        'Ticket shows EXPRESS prefix - appears at TOP of queue board.']),
      (False,'3','Brief Triage','OPD Nurse',
       'Consultations > Triage Workstation',
       ['Express patients still need basic vitals - nurse sees them immediately ahead of standard queue.',
        'Record VA (right eye, left eye), IOP, chief complaint.',
        'Takes 3-5 minutes maximum.',
        'Patient enters Express Doctor Queue after triage.']),
      (False,'4','Priority Doctor Consultation','Doctor',
       'Consultations > Workstation',
       ['Express tickets appear at TOP of doctor queue (marked EXPRESS).',
        'Doctor calls express patient BEFORE standard patients.',
        'Perform consultation in normal way.',
        'Issue prescriptions / additional orders as needed.']),
      (False,'5','Additional Billing for Extra Services (if needed)','Cashier',
       'Billing > Work Queue',
       ['Consultation fee was pre-paid at Step 2.',
        'If doctor added new orders (lab tests, investigations, medications), those create a NEW bill.',
        'Patient returns to cashier to pay for additional services before receiving them.']),
      (False,'6','Priority Pharmacy Dispensing','Pharmacist',
       'Pharmacy > Dispensing Queue',
       ['Express prescriptions flagged for priority service.',
        'Dispense medications - target: patient waits no more than 5 minutes.',
        'Mark prescription as dispensed.']),
      (False,'7','Patient Exit','','',
       ['Patient exits with medication and receipt.',
        'Target: entire visit completed within 35 minutes from arrival.']),
    ],
    'note': 'WHAT IS EXPRESS? A patient who does not want to wait in the standard queue pays the consultation fee UPFRONT at the Express Cashier Desk, then receives a priority ticket and is seen before standard-queue patients.',
    'warn': 'STAFF NOTE: Express lane is a paid priority upgrade. Do NOT allow patients to join without completing payment at Step 2. Express patients needing extra services must pay for those separately.',
  },
  {
    'fname': '4. Insured Patient Flow',
    'title': 'Insured Patient Flow',
    'subtitle': 'Corporate / NHIF / Company Insurance  |  Patient pays CO-PAY only at cashier',
    'accent': HexColor('#7c3aed'), 'light': HexColor('#ede9fe'),
    'meta': [('Flow Type','Insured / Corporate'),('Avg Duration','45-90 min'),
             ('Starts At','Gate / Insurance Desk'),('Ends At','Pharmacy / Exit'),
             ('Billing','Proforma + Co-pay'),('Payment','Patient pays CO-PAY at cashier')],
    'flow': ['Gate','Insurance Verify','Registration','Triage','Consultation',
             'Proforma','** CO-PAY CASHIER **','Pharmacy','Exit'],
    'steps': [
      (False,'1','Patient Arrives - Insurance Card Identified','Gate Staff',
       'QMS > Gate Issue',
       ['Gate staff identifies patient as insured when they show their insurance/company card.',
        'Issue QMS gate ticket - select patient type: Insured.',
        'Direct patient to Reception / Insurance Verification Desk.']),
      (False,'2','Insurance Verification at Reception','Receptionist / Medical Records',
       'Patients > Detail > Insurance Tab',
       ['Ask patient for: Insurance card, Company ID, Authorization letter (if required).',
        'Retrieve or register patient in system.',
        'Open patient record, go to Insurance tab.',
        'Verify: Insurance company, policy number, coverage type, expiry date.',
        'Confirm ophthalmology / eye care services are covered.',
        'Note: Does insurance require Pre-Authorization before procedures?']),
      (False,'3','Triage - Vitals & Chief Complaint','OPD Nurse',
       'Consultations > Triage Workstation',
       ['Record VA (right and left eye), IOP, blood pressure, chief complaint.',
        'Note any allergies.',
        'Submit triage - patient enters normal doctor queue.']),
      (False,'4','Doctor Consultation','Ophthalmologist / Doctor',
       'Consultations > Workstation',
       ['Consultation follows standard clinical workflow.',
        'Doctor must be aware patient is insured - warn about uncovered services.',
        'If surgery or costly procedure recommended: Pre-Authorization may be required.',
        'Complete diagnosis, prescriptions, lab orders, investigation orders.',
        'Click Complete Consultation.']),
      (False,'5','Pre-Authorization if Required','Medical Records / Billing Officer',
       'Billing > Proforma  OR  Corporate Accounts',
       ['For procedures (surgery, costly investigations): call/email insurer for pre-auth.',
        'Record pre-authorization number in system on the proforma.',
        'If not required: skip directly to Step 6.']),
      (False,'6','Billing - Proforma / Insurance Claim','Billing Officer / Cashier',
       'Billing > Proforma  OR  Billing > Cashier POS',
       ['Open patient billing screen - charges auto-populated from consultation.',
        'Create Proforma Invoice addressed to insurance company / employer.',
        'Set billing tier: Insurance / Corporate Rate.',
        'SPLIT the bill: Insurance portion (billed to company on credit) + Co-pay (patient pays now).']),
      (True,'7','CASHIER - PATIENT PAYS CO-PAY (MANDATORY STOP)','Cashier',
       'Billing > Cashier POS',
       ['INSURED PATIENTS STILL PAY AT THE CASHIER - they pay the CO-PAY AMOUNT only.',
        'Patient pays ONLY the co-payment amount (not the full bill).',
        'Insurance portion stays as outstanding on corporate account - claimed later by billing team.',
        'Process co-pay payment - receipt issued to patient.',
        'PHARMACY WILL NOT RELEASE MEDICATION UNTIL CO-PAY IS CONFIRMED PAID.']),
      (False,'8','Pharmacy Dispensing','Pharmacist',
       'Pharmacy > Dispensing Queue',
       ['Prescription appears in queue ONLY after co-pay is confirmed.',
        'Dispense insurance-covered medications.',
        'Non-covered medications: patient pays full price separately.',
        'Mark as dispensed.']),
      (False,'9','Patient Exit & Claim Filing','Billing / Medical Records','',
       ['Patient exits with medication and co-pay receipt.',
        'Billing officer consolidates claim at end of day/week and submits to insurer.',
        'Track reimbursements in Billing > Corporate Accounts > Statement.']),
    ],
    'note': 'COVERAGE TIP: If unsure whether a service is covered, ask patient to confirm with their insurer before ordering. Document this in the consultation notes.',
    'warn': 'DRY RUN: (1) Insurance info recorded before consultation. (2) Proforma references correct corporate account. (3) Do NOT release medication until co-pay confirmed paid - even for insured patients.',
  },
]


def flow_bar(nodes, accent, cw_total):
    n = len(nodes)
    arr_w = 10
    node_w = (cw_total - arr_w * (n-1)) / n
    cells, widths = [], []
    for i, nd in enumerate(nodes):
        is_pay = '**' in nd
        bg = CASH_COL if is_pay else accent
        txt = nd.replace('**','').strip()
        c = Table([[Paragraph(txt, sFlowNode)]], colWidths=[node_w])
        c.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),bg),
                                ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
                                ('LEFTPADDING',(0,0),(-1,-1),2),('RIGHTPADDING',(0,0),(-1,-1),2)]))
        cells.append(c); widths.append(node_w)
        if i < n-1:
            cells.append(Paragraph('>', S('a',font='Helvetica',size=9,color=HexColor('#94a3b8'),alignment=TA_CENTER)))
            widths.append(arr_w)
    t = Table([cells], colWidths=widths)
    t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                            ('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0),
                            ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]))
    return t


def step_row(is_cash, num, title, role, screen, bullets, accent, cw_total):
    num_bg = CASH_COL if is_cash else accent
    row_bg = CASH_BG if is_cash else white
    border = CASH_COL if is_cash else HexColor('#e2e8f0')

    tStyle = sStepTC if is_cash else sStepT
    rStyle = sRoleC  if is_cash else sRole

    body = [Paragraph(title, tStyle)]
    if role:
        body.append(Paragraph('[' + role + ']', rStyle))
    if screen:
        body.append(Paragraph('System: ' + screen, sScreen))
    body.append(Spacer(1, 2))
    for b in bullets:
        bS = sBulletW if (is_cash and any(w in b for w in ['MUST','MANDATORY','WILL NOT','PAYMENT','PAY','CONFIRMED'])) else sBullet
        body.append(Paragraph('• ' + b, bS))

    body_cell = [Spacer(1,2)] + body + [Spacer(1,2)]
    nc = Table([[Paragraph(num, sNumW)]], colWidths=[20], rowHeights=[20])
    nc.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),num_bg),
                             ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                             ('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))

    row = Table([[nc, body_cell]], colWidths=[24, cw_total-28])
    rs = [('BACKGROUND',(1,0),(1,0),row_bg),
          ('BOX',(0,0),(-1,-1),1.2 if is_cash else 0.5, border),
          ('VALIGN',(0,0),(-1,-1),'TOP'),
          ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
          ('LEFTPADDING',(0,0),(0,0),2),('RIGHTPADDING',(0,0),(0,0),2),
          ('LEFTPADDING',(1,0),(1,0),7),('RIGHTPADDING',(1,0),(1,0),6)]
    row.setStyle(TableStyle(rs))
    return row


def note_box(text, label, bg, line_color):
    t = Table([[Paragraph(label + ' ' + text, sNote)]], colWidths=[W-36*mm])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),bg),
                            ('LINEBEFORE',(0,0),(0,-1),3,line_color),
                            ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
                            ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8)]))
    return t


def make_pdf(flow):
    fname = f"{OUT}/{flow['fname']}.pdf"
    doc = SimpleDocTemplate(fname, pagesize=A4,
                            leftMargin=18*mm, rightMargin=18*mm,
                            topMargin=15*mm, bottomMargin=20*mm)
    accent = flow['accent']
    light  = flow['light']
    cw = W - 36*mm
    story = []

    # Header
    hdr = Table([[Paragraph('EHR AFRICA  --  DRY RUN WORKFLOW GUIDE', sHdrLbl)],
                 [Paragraph(flow['title'],  sHdr1)],
                 [Paragraph(flow['subtitle'], sHdr2)]],
                colWidths=[cw])
    hdr.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),accent),
                              ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
                              ('LEFTPADDING',(0,0),(-1,-1),14),('RIGHTPADDING',(0,0),(-1,-1),14)]))
    story.append(hdr)
    story.append(Spacer(1, 6))

    # Meta strip
    n = len(flow['meta'])
    meta_rows_l = [Paragraph(l, sMeta_l) for l,v in flow['meta']]
    meta_rows_v = [Paragraph(v, sMeta_v) for l,v in flow['meta']]
    mt = Table([meta_rows_l, meta_rows_v], colWidths=[cw/n]*n)
    mt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),light),
                             ('BOX',(0,0),(-1,-1),0.5,HexColor('#d1d5db')),
                             ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
                             ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6)]))
    story.append(mt)
    story.append(Spacer(1, 8))

    # Flow bar label + bar
    story.append(Paragraph('PATIENT JOURNEY:', S('fb_lbl', font='Helvetica-Bold', size=7.5,
                                                  color=HexColor('#64748b'))))
    story.append(Spacer(1, 3))
    story.append(flow_bar(flow['flow'], accent, cw))
    story.append(Spacer(1, 10))

    # Steps
    story.append(Paragraph('STEP-BY-STEP PROCEDURE', S('sh2', font='Helvetica-Bold', size=10,
                                                         color=accent)))
    story.append(HRFlowable(width='100%', thickness=1.5, color=accent, spaceAfter=6))

    for is_cash, num, title, role, screen, bullets in flow['steps']:
        r = step_row(is_cash, num, title, role, screen, bullets, accent, cw)
        story.append(KeepTogether([r, Spacer(1, 4)]))

    story.append(Spacer(1, 6))
    story.append(note_box(flow['note'], 'NOTE:', light, accent))
    story.append(Spacer(1, 4))
    story.append(note_box(flow['warn'], 'CHECKLIST:', HexColor('#fffbeb'), HexColor('#f59e0b')))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width='100%', thickness=0.5, color=HexColor('#e2e8f0')))
    story.append(Spacer(1, 3))

    ft = Table([[Paragraph('EHR Africa -- Internal Staff Reference -- CONFIDENTIAL', sFootL),
                 Paragraph(f"{flow['title']}  v1.0  {today}", sFootR)]],
               colWidths=[cw/2]*2)
    ft.setStyle(TableStyle([('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
    story.append(ft)

    doc.build(story)
    size = os.path.getsize(fname)
    print(f"Generated: {flow['fname']}.pdf  ({size//1024} KB)")


for flow in FLOWS:
    make_pdf(flow)
print('ALL DONE')
