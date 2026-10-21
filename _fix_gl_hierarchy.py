"""
One-shot fix: create missing summary accounts and reparent all tier child accounts
within the 705200 (Services Sold) group.

Run: python _fix_gl_hierarchy.py
"""
import django, os
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.base'
django.setup()

from apps.billing.models import GLAccount, AccountType

SERVICES_PARENT_CODE = '705200'

# (summary_code, summary_name, [child_posting_codes])
GROUPS = [
    ('7052000', 'Consultation',            ['7052001','7052002','7052003','7052004','7052005','7052006','7052007']),
    ('7052010', 'Anesthesia',              ['7052011','7052012','7052013','7052014','7052015']),
    ('7052020', 'Cataract Surgeries',      ['7052021','7052022','7052023','7052024','7052025']),
    ('7052030', 'Cornea Surgeries',        ['7052031','7052032','7052033','7052034','7052035']),
    ('7052040', 'Glaucoma Surgeries',      ['7052041','7052042','7052043','7052044','7052045']),
    ('7052050', 'Vitreoretinal Surgeries', ['7052051','7052052','7052053','7052054','7052055']),
    ('7052060', 'Oculoplasty Surgeries',   ['7052061','7052062','7052063','7052064','7052065']),
    ('7052070', 'Other Surgeries',         ['7052071','7052072','7052073','7052074','7052075']),
    ('7052080', 'Investigation',           ['7052081','7052082','7052083','7052084','7052085','7052086']),
    ('7052090', 'Laser Treatment',         ['7052091','7052092','7052093','7052094','7052095']),
    ('7052100', 'Laboratory',              ['7052101','7052102','7052103','7052104','7052105']),
    ('7052110', 'Hospitalization',         ['7052111','7052112','7052113','7052114','7052115']),
    ('7052120', 'Orthoptic',               ['7052121','7052122','7052123','7052124','7052125']),
    ('7052130', 'Other Medical Services',  ['7052131','7052132','7052133','7052134','7052135']),
    ('7052150', 'Refractive Surgeries',    ['7052151','7052152','7052153','7052154']),
]

services_parent = GLAccount.objects.get(code=SERVICES_PARENT_CODE)
created_count = 0
reparented = 0

for base_code, base_name, child_codes in GROUPS:
    base_acct, was_created = GLAccount.objects.get_or_create(
        code=base_code,
        defaults={
            'name': base_name,
            'account_type': AccountType.REVENUE,
            'parent': services_parent,
            'is_summary': True,
            'allow_manual_posting': False,
            'is_active': True,
            'is_deleted': False,
        }
    )
    if was_created:
        print(f'  CREATED: {base_code} -- {base_name}')
        created_count += 1
    else:
        changed = False
        if not base_acct.is_summary:
            base_acct.is_summary = True
            base_acct.allow_manual_posting = False
            changed = True
        if base_acct.parent_id != services_parent.pk:
            base_acct.parent = services_parent
            changed = True
        if changed:
            base_acct.save(update_fields=['is_summary', 'allow_manual_posting', 'parent'])
            print(f'  FIXED:   {base_code} -- {base_name}')

    for child_code in child_codes:
        child = GLAccount.objects.filter(code=child_code, is_deleted=False).first()
        if child is not None and child.parent_id != base_acct.pk:
            child.parent = base_acct
            child.is_summary = False
            child.allow_manual_posting = True
            child.save(update_fields=['parent', 'is_summary', 'allow_manual_posting'])
            reparented += 1

# Global re-run of is_summary fix
parent_ids = set(
    GLAccount.objects.filter(is_deleted=False, parent__isnull=False)
    .values_list('parent_id', flat=True)
)
s1 = GLAccount.objects.filter(pk__in=parent_ids, is_summary=False).update(
    is_summary=True, allow_manual_posting=False
)
s2 = (GLAccount.objects.filter(is_deleted=False)
      .exclude(pk__in=parent_ids)
      .filter(is_summary=True)
      .update(is_summary=False, allow_manual_posting=True))

total = GLAccount.objects.filter(is_deleted=False).count()
summary = GLAccount.objects.filter(is_deleted=False, is_summary=True).count()
leaf = GLAccount.objects.filter(is_deleted=False, is_summary=False).count()

print()
print(f'Summary accounts created : {created_count}')
print(f'Tier accounts reparented : {reparented}')
print(f'is_summary re-fixed      : {s1} newly marked summary, {s2} unmarked')
print(f'Total: {total}  |  Summary headers: {summary}  |  Posting accounts: {leaf}')
