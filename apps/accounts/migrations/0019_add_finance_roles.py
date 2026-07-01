"""
Migration 0019 — Add Chief Cashier, Accountant, Senior Accountant roles.

Financial module role segregation:
  CASHIER          → bills patients at POS only
  CHIEF_CASHIER    → opens/closes day, verifies cashier shifts, receives cash handover
  ACCOUNTANT       → cancels invoices, processes refunds, AR, corporate accounts
  SENIOR_ACCOUNTANT→ all accountant + expense approval, petty cash, budget management
  FINANCE_DIRECTOR → full financial module + P&L + waivers + strategic reports
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0018_add_cssd_technician_role'),
    ]

    operations = [
        # UserRole is a TextChoices enum on the model — no DB column change needed
        # (role is stored as a varchar; adding new valid values requires no DDL).
        # This migration exists to mark the dependency chain and document the change.
        migrations.RunSQL('SELECT 1', migrations.RunSQL.noop),
    ]
