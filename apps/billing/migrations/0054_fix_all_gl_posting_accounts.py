"""
Migration 0054 — Mark every GL account used for auto-posting as is_summary=False.

The imported OHADA COA correctly marks all parent accounts as summary, but our
GL service posts to these same parent codes (e.g. 705160 Sales of Medications,
7052000 Consultation, 661000 Personnel Expenses). Every such account is summary
because it has tier-specific children — but this hospital posts at the parent
level for simplicity.

Strategy: mark is_summary=False on:
  1. Every account referenced in a GLMapping record (Finance Director configured these)
  2. Every hardcoded default account code used in gl_service.py
"""
from django.db import migrations

# Hardcoded default codes from apps/billing/gl_service.py
_GL_SERVICE_DEFAULTS = [
    # System accounts
    '571000', '521100', '552000', '412000', '401100', '499100', '421100',
    '654000', '754000', '281000', '241000',
    # Revenue defaults
    '701000', '702000', '703000', '704000', '705000', '706000',
    '707000', '708000', '709000',
    # Expense defaults
    '602000', '642000', '621000', '641000', '643000', '601000',
    '653000', '651000', '652000', '658000',
    # Payment method defaults
    '572000', '521000', '521100', '552000', '573100',
    # Stock accounts (inventory gl_service)
    '311000', '321000', '322000', '323000', '331000', '603000', '401100',
]


def fix_all_posting_accounts(apps, schema_editor):
    GLAccount = apps.get_model('billing', 'GLAccount')
    GLMapping = apps.get_model('billing', 'GLMapping')

    # Collect all codes from GLMapping (Finance Director's own configuration)
    mapped_codes = list(
        GLMapping.objects.values_list('gl_account__code', flat=True).distinct()
    )

    all_codes = list(set(_GL_SERVICE_DEFAULTS + mapped_codes))
    updated = GLAccount.objects.filter(code__in=all_codes).update(is_summary=False)
    print(f'  Set is_summary=False on {updated} accounts ({len(all_codes)} target codes)')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0053_fix_gl_posting_accounts'),
    ]

    operations = [
        migrations.RunPython(fix_all_posting_accounts, reverse_code=noop),
    ]
