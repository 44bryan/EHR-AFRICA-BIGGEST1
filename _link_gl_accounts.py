"""Auto-link all ServicePrice entries to their correct GL accounts.

Mapping logic:
  Category/Sub → base GL code prefix + tier suffix
  Tier suffix: STANDARD=1, EXPRESS=2, INSURED=3, VIP=4, EVIP=6

  CONSULT/CON  → 7052001-6
  CONSULT/ORT  → 7052121-6 (Orthoptic)
  CONSULT/INT  → 7052007   (Internist, single account)
  SURGICAL/ANE → 7052011-5 (Anesthesia)
  SURGICAL/CAT → 7052021-5 (Cataract)
  SURGICAL/COR → 7052031-5 (Cornea)
  SURGICAL/GLA → 7052041-5 (Glaucoma)
  SURGICAL/VIT → 7052051-5 (Vitreoretinal)
  SURGICAL/OCU → 7052061-5 (Oculoplastic)
  SURGICAL/OTH → 7052071-5 (Other Surg)
  SURGICAL/LAS → 7052091-5 (Laser)
  INVEST/INV   → 7052081-6
  LAB/LAB      → 7052101-5
  ADMISSION/HOS→ 7052111-5 (Hospitalization)
  OTHER/OMS    → 7052131-5 (Other Medical Services)
  OTHER/CSM    → 705180    (Consumables — single account)
  REG/PF001    → 705192    (Patient Folders — single account)
  PHARMACY/MED → 705160    (Medications — single account)
  PHARMACY/CSM → 705180    (Consumables)
"""
import paramiko, time, sys

HOST = '192.168.30.169'
USER = 'grudd420'
PASS = '123456'

SCRIPT = r'''
import os,sys,django
os.chdir('/opt/ehr-africa')
sys.path.insert(0,'/opt/ehr-africa')
os.environ['DJANGO_SETTINGS_MODULE']='ehr_project.settings.production'
django.setup()

from apps.billing.models import ServicePrice, GLAccount

# Tier → suffix digit
TIER_SUFFIX = {
    'STANDARD': '1',
    'EXPRESS':  '2',
    'INSURED':  '3',
    'VIP':      '4',
    'EVIP':     '6',
}

# Sub-category code → (GL base code, has_tier_variants)
# base code is combined with tier suffix for per-tier accounts
SUB_TO_GL = {
    # Consultations
    'CON': ('7052000', True),   # 7052001..7052006
    'INT': ('7052007', False),  # single internist account
    'ORT': ('7052120', True),   # 7052121..7052126
    # Surgical
    'ANE': ('7052010', True),   # 7052011..7052015
    'CAT': ('7052020', True),   # 7052021..7052025
    'COR': ('7052030', True),   # 7052031..7052035
    'GLA': ('7052040', True),   # 7052041..7052045
    'VIT': ('7052050', True),   # 7052051..7052055
    'OCU': ('7052060', True),   # 7052061..7052065
    'OTH': ('7052070', True),   # 7052071..7052075
    'LAS': ('7052090', True),   # 7052091..7052095
    # Investigation & Lab
    'INV': ('7052080', True),   # 7052081..7052086
    'LAB': ('7052100', True),   # 7052101..7052105
    # Admission
    'HOS': ('7052110', True),   # 7052111..7052115
    # Other medical
    'OMS': ('7052130', True),   # 7052131..7052135
    # Special single accounts
    'CSM': ('705180', False),   # Consumables
    'PF001': ('705192', False), # Patient Folders
}

# Category fallbacks (when sub_category is null or code not in map)
CAT_FALLBACK = {
    'CONSULT':   ('7052000', True),
    'SURGICAL':  ('7052000', True),
    'INVEST':    ('7052080', True),
    'LAB':       ('7052100', True),
    'ADMISSION': ('7052110', True),
    'OTHER':     ('7052130', True),
    'PHARMACY':  ('705000',  False),  # General pharmacy revenue
    'REG':       ('705192',  False),
}

# Build GL account lookup dict: code -> GLAccount
gl_map = {g.code: g for g in GLAccount.objects.filter(is_active=True)}
print(f'Loaded {len(gl_map)} GL accounts')

linked = 0
not_found = []
prices = ServicePrice.objects.filter(is_deleted=False).select_related('sub_category')
total = prices.count()
print(f'Processing {total} service price entries...')

for sp in prices:
    sub_code = sp.sub_category.code if sp.sub_category else None
    tier = sp.tier or 'STANDARD'
    suffix = TIER_SUFFIX.get(tier, '1')

    # Determine base GL code and whether it has tier variants
    if sub_code and sub_code in SUB_TO_GL:
        base, has_tier = SUB_TO_GL[sub_code]
    elif sp.entry_type == 'ITEM' and sp.category == 'PHARMACY':
        base, has_tier = '705160', False  # Medications
    elif sp.entry_type == 'ITEM':
        base, has_tier = '705180', False  # Generic items → Consumables
    else:
        base, has_tier = CAT_FALLBACK.get(sp.category, ('7052141', False))

    # Build target GL code
    if has_tier:
        gl_code = base[:-1] + suffix if base.endswith('0') else base + suffix
        # e.g. '7052000' → '7052001' for STANDARD
        # Actually: base is the "0" version, suffix replaces last 0
        # '7052000' + suffix '1' → '7052001'
        gl_code = base[:-1] + suffix
    else:
        gl_code = base

    gl_obj = gl_map.get(gl_code)

    # Fallback: try parent account if specific not found
    if not gl_obj and has_tier:
        gl_obj = gl_map.get(base)

    # Second fallback: category root
    if not gl_obj:
        cat_base, _ = CAT_FALLBACK.get(sp.category, ('705200', False))
        gl_obj = gl_map.get(cat_base) or gl_map.get('705200') or gl_map.get('705000')

    if gl_obj:
        sp.gl_account = gl_obj
        sp.save(update_fields=['gl_account'])
        linked += 1
    else:
        not_found.append(f'{sp.code}|{sp.tier}|{sp.category}|{sub_code} → tried {gl_code}')

print(f'\nLinked: {linked}/{total}')
if not_found:
    print(f'Could not resolve {len(not_found)} entries:')
    for x in not_found[:20]:
        print(f'  {x}')
else:
    print('All entries linked successfully!')

# Summary: count by category
from django.db.models import Count
print('\nLinked breakdown by category:')
for row in ServicePrice.objects.filter(is_deleted=False, gl_account__isnull=False).values('category').annotate(n=Count('id')).order_by('-n'):
    print(f"  {row['category']}: {row['n']}")
'''

print('Uploading and running GL linking script...')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=15)

sftp = ssh.open_sftp()
with sftp.open('/tmp/_link_gl.py', 'w') as f:
    f.write(SCRIPT)
sftp.close()

_, out, err = ssh.exec_command(
    'cd /opt/ehr-africa && source venv/bin/activate && python /tmp/_link_gl.py 2>&1',
    timeout=180
)
start = time.time()
while not out.channel.exit_status_ready():
    if time.time() - start > 175:
        break
    time.sleep(3)

o = out.read().decode('utf-8', errors='replace')
e = err.read().decode('utf-8', errors='replace')
print(o)
if e:
    print('STDERR:', e)

ssh.close()
print('Done.')
