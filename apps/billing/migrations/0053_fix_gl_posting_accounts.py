"""
Migration 0053 — Fix is_summary flag on GL accounts required for auto-posting.

The imported OHADA COA marks parent accounts as is_summary=True, which blocks
_create_entry() from posting to them. These are the transaction-level accounts
for this hospital and must allow posting.

Accounts fixed (is_summary -> False):
  412000  Patient AR             - Dr on invoice, Cr on payment
  311000  General Store Stock    - Dr on stock receipt / Cr on issue
  331000  Ward/Lab Supplies      - Dr on stock receipt / Cr on issue
  401100  Local Suppliers (AP)   - Cr on stock entry / Dr on AP payment
  521000  Bank Account - Main    - Dr on CARD/TRANSFER payment
  521100  Local Bank             - ensure leaf for bank payment routing
"""
from django.db import migrations

LEAF_CODES = ['412000', '311000', '331000', '401100', '521000', '521100']


def fix_summary_flags(apps, schema_editor):
    GLAccount = apps.get_model('billing', 'GLAccount')
    updated = GLAccount.objects.filter(code__in=LEAF_CODES).update(is_summary=False)
    print(f'  Fixed is_summary=False on {updated} accounts: {LEAF_CODES}')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0052_reseed_stock_operation_types'),
    ]

    operations = [
        migrations.RunPython(fix_summary_flags, reverse_code=noop),
    ]
