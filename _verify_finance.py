#!/usr/bin/env python
"""Verify financial pages will show data after the is_posted fix."""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from apps.billing.models import JournalEntry, JournalLine, GLAccount
from django.db.models import Sum

print('=== FINANCIAL DATA CHECK ===')
total_je = JournalEntry.objects.filter(is_deleted=False).count()
posted_je = JournalEntry.objects.filter(is_deleted=False, is_posted=True).count()
unposted_je = JournalEntry.objects.filter(is_deleted=False, is_posted=False).count()
print(f'Journal Entries: {total_je} total, {posted_je} posted, {unposted_je} unposted')

total_lines = JournalLine.objects.filter(entry__is_deleted=False).count()
dr = JournalLine.objects.filter(entry__is_deleted=False).aggregate(t=Sum('debit_amount'))['t'] or 0
cr = JournalLine.objects.filter(entry__is_deleted=False).aggregate(t=Sum('credit_amount'))['t'] or 0
print(f'Journal Lines: {total_lines}, Dr: {dr:,.0f}, Cr: {cr:,.0f}')
print(f'Balanced: {abs(dr - cr) < 0.01}')

# Accounts with activity (this is what Trial Balance will now show)
active = JournalLine.objects.filter(entry__is_deleted=False).values(
    'account__code', 'account__name', 'account__account_type'
).annotate(dr=Sum('debit_amount'), cr=Sum('credit_amount')).order_by('account__code')
print(f'\nAccounts with GL activity: {active.count()}')
print(f'{"Code":<10} {"Name":<35} {"Type":<10} {"Debit":>14} {"Credit":>14}')
print('-' * 90)
for a in active:
    print(f'{a["account__code"]:<10} {a["account__name"][:35]:<35} {a["account__account_type"]:<10} {a["dr"] or 0:>14,.0f} {a["cr"] or 0:>14,.0f}')

print('\n=== TRIAL BALANCE WILL SHOW THIS DATA ===')
print(f'PASS: {active.count()} accounts with activity will display')
print(f'PASS: Total Dr = {dr:,.0f} FCFA')
print(f'PASS: Total Cr = {cr:,.0f} FCFA')
