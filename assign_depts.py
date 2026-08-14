from apps.accounts.models import User
from apps.departments.models import Department
from apps.qms.models import ServiceCounter

def dept(code):
    try:
        return Department.objects.get(code=code)
    except Department.DoesNotExist:
        return None

def counter(code):
    try:
        return ServiceCounter.objects.get(code=code)
    except ServiceCounter.DoesNotExist:
        return None

updates = [
    # (username, dept_code, consultation_unit, counter_code)
    # General Ophthalmologists
    ('doctor01',   'GEN_OPH', 'GENERAL',   'GEN-01'),
    ('doctor02',   'GEN_OPH', 'GENERAL',   'DR-01'),
    ('doctor03',   'GEN_OPH', 'GENERAL',   'DR-02'),
    ('doctor04',   'GEN_OPH', 'GENERAL',   'DR-03'),
    ('doctor05',   'GEN_OPH', 'GENERAL',   'DR-04'),
    ('expdoc01',   'GEN_OPH', 'EXPRESS',   'EXP-01'),
    ('expdoc02',   'GEN_OPH', 'EXPRESS',   'EXP-02'),
    ('vipdoc01',   'GEN_OPH', 'VIP',       'VIP-01'),
    ('vipdoc02',   'GEN_OPH', 'VIP',       'VIP-02'),
    ('insdoc01',   'GEN_OPH', 'INSURANCE', 'DR-05'),
    ('insdoc02',   'GEN_OPH', 'INSURANCE', 'DR-06'),
    # Specialists
    ('glauco01',   'GLAUC',       'GENERAL', 'GLAUC-01'),
    ('retina01',   'RETINA',      'GENERAL', 'RET-01'),
    ('cataract01', 'CATARACT',    'GENERAL', 'CAT-01'),
    # Optometrists / Refraction
    ('optom01',    'REFRAC',      'GENERAL', 'REF-01'),
    ('optom02',    'REFRAC',      'GENERAL', 'REF-02'),
    ('optom03',    'REFRAC',      'GENERAL', 'REF-03'),
    ('paedoph01',  'PEDS_REFRAC', 'GENERAL', None),
    # Low Vision
    ('lowvis01',   'LOW_VIS',     'GENERAL', None),
    # Investigations / Lab
    ('invest01',   'INVEST', None, 'INV-01'),
    ('labtech01',  'LAB',    None, 'LAB-01'),
    # OPD Nurses (triage / parameters)
    ('nurse02',    'GEN_OPH', None, 'PARAM-01'),
    ('nurse03',    'GEN_OPH', None, None),
    ('expnurse01', 'GEN_OPH', None, 'PVIP-01'),
    ('insnurse01', 'GEN_OPH', None, None),
    ('vipnurse01', 'GEN_OPH', None, None),
    # Consultation Nurses
    ('cnurse01',   'GEN_OPH', None, 'PARAM-02'),
    ('cnurse02',   'GEN_OPH', None, None),
    # Other clinical staff
    ('nurse01',     'GEN_OPH',  None, None),
    ('anaes01',     'CATARACT', None, None),
    ('theatre01',   'CATARACT', None, None),
    ('wardnurse01', 'GEN_OPH',  None, None),
    ('admiss01',    'GEN_OPH',  None, None),
    # Cashiers (station already set; no dept needed)
    ('cashier01',   None, None, 'CASH-04'),
    ('cashier02',   None, None, 'CASH-08'),
    ('cashier03',   None, None, 'CASH-09'),
    ('cashierexp',  None, None, 'CASH-06'),
    ('cashiervip',  None, None, 'CASH-05'),
    # Optical / Pharmacy / Reception
    ('optics01',    None, None, 'OPT-02'),
    ('pharma01',    None, None, 'RX-02'),
    ('recep01',     None, None, 'RECEP-03'),
]

changed = 0
for username, dept_code, cu, cnt_code in updates:
    try:
        u = User.objects.get(username=username)
        save_fields = []
        if dept_code:
            d = dept(dept_code)
            if d and u.department != d:
                u.department = d
                save_fields.append('department')
        if cu and hasattr(u, 'consultation_unit'):
            if u.consultation_unit != cu:
                u.consultation_unit = cu
                save_fields.append('consultation_unit')
        if save_fields:
            u.save(update_fields=save_fields)
        if cnt_code:
            c = counter(cnt_code)
            if c and c.staff_assigned != u:
                c.staff_assigned = u
                c.save(update_fields=['staff_assigned'])
        changed += 1
        print(f"  OK  {username:<18} dept={dept_code or '-':<12} unit={cu or '-':<12} counter={cnt_code or '-'}")
    except User.DoesNotExist:
        print(f"  SKIP {username} (not found)")
    except Exception as e:
        print(f"  ERR  {username}: {e}")

print(f"\nDone. {changed} accounts processed.")
