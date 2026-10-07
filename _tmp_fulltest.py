from django.test import Client
from apps.accounts.models import User
from apps.patients.models import Patient, Visit, VisitStatus
from django.utils import timezone
import json

today = timezone.localdate()
errors = []

def gc(role):
    u = User.objects.filter(role=role, is_active=True).first()
    if not u:
        print('  NO USER:', role)
        return None, None
    c = Client()
    c.force_login(u)
    return c, u

def chk(label, status, ok_range=(200,399)):
    ok = ok_range[0] <= status <= ok_range[1]
    if not ok: errors.append(label + ' got ' + str(status))
    print(('  OK  ' if ok else '  FAIL') + ' [' + str(status) + '] ' + label)

print('=== 1. PATIENT REGISTRATION ===')
c, u = gc('receptionist')
if c:
    chk('Register form', c.get('/patients/register/').status_code)
    chk('Patient search', c.get('/patients/search/?q=test').status_code)
    chk('Patient list', c.get('/patients/').status_code)
    chk('Emergency register', c.get('/patients/emergency/').status_code)

print('=== 2. QMS / GATE ===')
c, u = gc('gatekeeper')
if c:
    chk('Gate issue', c.get('/qms/gate/').status_code)
    chk('Room board', c.get('/qms/room-board/').status_code)
c, u = gc('receptionist')
if c:
    chk('Reception desk', c.get('/reception/').status_code)
    chk('Walk-in', c.get('/reception/walk-in/').status_code)
    chk('QMS receptionist', c.get('/qms/receptionist/').status_code)
    chk('QMS display', c.get('/qms/display/').status_code)

print('=== 3. CASHIER / BILLING ===')
c, u = gc('cashier')
if c:
    chk('Invoice list', c.get('/billing/invoices/').status_code)
    chk('Service prices', c.get('/billing/service-prices/').status_code)
    chk('Cashier queue', c.get('/billing/cashier-queue/').status_code)
c, u = gc('chief_cashier')
if c:
    chk('Cashdesks', c.get('/billing/cashdesks/').status_code)
    chk('All shifts', c.get('/billing/shifts/').status_code)
    chk('Sessions', c.get('/billing/sessions/').status_code)

print('=== 4. TRIAGE / NURSE ===')
c, u = gc('nurse')
if c:
    v = Visit.objects.filter(is_deleted=False, status=VisitStatus.PARAMETERS).first()
    if v:
        chk('Triage form', c.get('/patients/visit/' + str(v.visit_number) + '/triage/').status_code)
    else:
        print('  SKIP no PARAMETERS visits today')

print('=== 5. CONSULTATIONS ===')
c, u = gc('ophthalmologist')
if c:
    chk('Workstation', c.get('/consultations/workstation/').status_code)
    chk('List', c.get('/consultations/').status_code)
    chk('VIP dashboard', c.get('/consultations/vip/').status_code)
    chk('Triage workstation', c.get('/consultations/triage-workstation/').status_code)
    chk('Route rooms STANDARD', c.get('/consultations/route/rooms/?tier=STANDARD', HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code)
    chk('Route rooms VIP', c.get('/consultations/route/rooms/?tier=VIP', HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code)
c, u = gc('consultation_nurse')
if c:
    chk('Unit queue', c.get('/consultations/unit-queue/').status_code)

print('=== 6. PHARMACY ===')
c, u = gc('pharmacist')
if c:
    chk('Dashboard', c.get('/pharmacy/').status_code)
    chk('Dispensing', c.get('/pharmacy/dispensing/').status_code)
    chk('Drugs', c.get('/pharmacy/drugs/').status_code)
    chk('Chronic Rx (was crashing)', c.get('/pharmacy/chronic-rx/').status_code)
    chk('Controlled drugs', c.get('/pharmacy/controlled/').status_code)
    chk('Stock adjustments', c.get('/pharmacy/stock-adjustments/').status_code)
    chk('Stats', c.get('/pharmacy/stats/').status_code)
    chk('Expiry alerts', c.get('/pharmacy/expiry-alerts/').status_code)

print('=== 7. LABORATORY ===')
c, u = gc('lab_technician')
if c:
    chk('Dashboard', c.get('/laboratory/').status_code)
    chk('Orders', c.get('/laboratory/list/').status_code)
    chk('Stats', c.get('/laboratory/stats/').status_code)

print('=== 8. INVESTIGATIONS ===')
c, u = gc('investigation_technician')
if c:
    chk('List', c.get('/investigations/').status_code)
    chk('Workstation', c.get('/investigations/workstation/').status_code)
    chk('Stats', c.get('/investigations/stats/').status_code)
    chk('Imaging', c.get('/investigations/imaging/').status_code)

print('=== 9. OPTICALS ===')
c, u = gc('optical_dispenser')
if c:
    chk('Dashboard', c.get('/opticals/').status_code)
    chk('Orders', c.get('/opticals/orders/').status_code)
    chk('Lab jobs', c.get('/opticals/lab/').status_code)
    chk('Stats', c.get('/opticals/stats/').status_code)

print('=== 10. IPD / WARD ===')
c, u = gc('nurse')
if c:
    chk('IPD', c.get('/ipd/').status_code)
    chk('Ward list', c.get('/ipd/wards/').status_code)
    chk('Bed map', c.get('/ipd/bed-map/').status_code)
    chk('Theatre', c.get('/ipd/theatre/').status_code)
    chk('Surgical booking', c.get('/ipd/surgical-bookings/').status_code)

print('=== 11. APPOINTMENTS ===')
c, u = gc('receptionist')
if c:
    chk('Appointments', c.get('/appointments/').status_code)
    chk('Clinic board', c.get('/appointments/clinic-board/').status_code)

print('=== 12. LEADERSHIP ===')
c, u = gc('medical_director')
if c:
    chk('Dashboard', c.get('/leadership/').status_code)
    chk('Hospital stats', c.get('/leadership/hospital-stats/').status_code)
    chk('Finance', c.get('/leadership/finance/').status_code)
    chk('Analytics', c.get('/leadership/analytics/').status_code)
    chk('Monthly stats', c.get('/leadership/monthly-stats/').status_code)
    chk('Retina dashboard', c.get('/leadership/retina/').status_code)

print('=== 13. FINANCE DIRECTOR ===')
c, u = gc('finance_director')
if c:
    chk('Billing home', c.get('/billing/').status_code)
    chk('Wallets', c.get('/billing/wallets/').status_code)
    chk('Assets', c.get('/billing/assets/').status_code)
    chk('Budget', c.get('/billing/budget/').status_code)
    chk('Balance sheet', c.get('/billing/gl/balance-sheet/').status_code)
    chk('Cash flow', c.get('/billing/gl/cash-flow/').status_code)
    chk('AR aging', c.get('/billing/reports/ar-aging/').status_code)
    chk('Corporate', c.get('/billing/corporate/').status_code)
    chk('AP bills', c.get('/billing/ap/bills/').status_code)
    chk('AP vendors', c.get('/billing/ap/vendors/').status_code)
    chk('Petty cash', c.get('/billing/petty-cash/').status_code)
    chk('Proforma', c.get('/billing/proforma/').status_code)
    chk('Void register', c.get('/billing/void-register/').status_code)

print('=== 14. NOTIFICATIONS ===')
c, u = gc('ophthalmologist')
if c:
    r = c.get('/notifications/poll/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    chk('Poll status', r.status_code)
    try:
        json.loads(r.content)
        print('  OK   Poll returns valid JSON')
    except Exception as je:
        errors.append('Notifications poll not JSON')
        print('  FAIL Poll not JSON:', str(je)[:80])

print('=== 15. SYSADMIN ===')
c, u = gc('super_admin')
if c:
    chk('Sysadmin', c.get('/sysadmin/').status_code)
    chk('Health check', c.get('/sysadmin/health/').status_code)
    chk('Staff hub', c.get('/accounts/staff/').status_code)
    chk('Departments', c.get('/departments/').status_code)

print('=== 16. AI ASSISTANT ===')
c, u = gc('ophthalmologist')
if c:
    chk('AI home', c.get('/ai-assistant/').status_code)

print('=== 17. PATIENT DETAIL (multi-role) ===')
p = Patient.objects.filter(is_deleted=False).first()
if p:
    pid = p.patient_id
    for role in ('ophthalmologist', 'receptionist', 'cashier', 'nurse', 'medical_director'):
        c, u = gc(role)
        if c:
            chk('Patient detail as ' + role, c.get('/patients/' + pid + '/').status_code)

print('=== 18. VIP ROUTING - billing to doctor ===')
from apps.qms.models import QueueToken, ServiceType, ServiceTier, TokenStatus
vip_token = QueueToken.objects.filter(
    service_tier=ServiceTier.VIP,
    service_type=ServiceType.VIP_CONSULT,
    token_date=today,
    is_deleted=False,
).first()
if vip_token:
    print('  OK   VIP_CONSULT token exists for today:', vip_token.patient.full_name)
else:
    print('  INFO No VIP billing done today yet (expected if no VIP patient billed today)')

std_token = QueueToken.objects.filter(
    service_type=ServiceType.PARAMETERS,
    token_date=today,
    is_deleted=False,
).first()
if std_token:
    print('  OK   PARAMETERS token exists (standard triage routing works)')

print()
total = len(errors)
if total:
    print('=== ' + str(total) + ' FAILURES ===')
    for e in errors:
        print('  FAIL:', e)
else:
    print('=== ALL CHECKS PASSED - SYSTEM CLEAN FOR DRY RUN ===')
