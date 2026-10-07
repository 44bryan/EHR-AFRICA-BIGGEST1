import sys, json
sys.path.insert(0, '/opt/ehr-africa')
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.production')
django.setup()

from django.utils import timezone
from django.db.models import Q, Sum, F, Count, Value, IntegerField
from django.db.models.functions import Coalesce
from apps.pharmacy.models import (
    Drug, DrugStock, Dispensing, DispensingItem, DispensingStatus,
    DispensingReturn,
)
import calendar
from datetime import date, timedelta

today = timezone.localdate()
year, month = today.year, today.month
month_start = date(year, month, 1)
last_day = calendar.monthrange(year, month)[1]
month_end = date(year, month, last_day)

print('=== PHARMACY DATA AUDIT - %s %d ===' % (month_start.strftime('%B'), year))
print()

# Raw counts
total_disp = Dispensing.objects.filter(is_deleted=False, dispensed_at__date__gte=month_start, dispensed_at__date__lte=month_end).count()
dispensed = Dispensing.objects.filter(is_deleted=False, dispensed_at__date__gte=month_start, dispensed_at__date__lte=month_end, status='DISPENSED').count()
partial = Dispensing.objects.filter(is_deleted=False, dispensed_at__date__gte=month_start, dispensed_at__date__lte=month_end, status='PARTIAL').count()
cancelled = Dispensing.objects.filter(is_deleted=False, dispensed_at__date__gte=month_start, dispensed_at__date__lte=month_end, status='CANCELLED').count()
pending = Dispensing.objects.filter(is_deleted=False, dispensed_at__date__gte=month_start, dispensed_at__date__lte=month_end, status='PENDING').count()

print('Dispensings:  total=%d  dispensed=%d  partial=%d  cancelled=%d  pending=%d' % (total_disp, dispensed, partial, cancelled, pending))
print('  sum check: %d == %d? %s' % (dispensed+partial+cancelled+pending, total_disp, dispensed+partial+cancelled+pending == total_disp))

# Revenue
revenue = Dispensing.objects.filter(
    is_deleted=False, dispensed_at__date__gte=month_start, dispensed_at__date__lte=month_end,
    status='DISPENSED'
).aggregate(r=Sum('total_amount'))['r'] or 0
print('Revenue: %s FCFA' % '{:,.0f}'.format(float(revenue)))

# Items
total_items = DispensingItem.objects.filter(
    dispensing__is_deleted=False,
    dispensing__dispensed_at__date__gte=month_start,
    dispensing__dispensed_at__date__lte=month_end,
).count()
print('Total items: %d' % total_items)

# Completion rate
comp_rate = round(dispensed / total_disp * 100, 1) if total_disp else 0
print('Completion rate: %s%%' % comp_rate)

# Avg items per rx
avg = round(total_items / total_disp, 2) if total_disp else 0
print('Avg items/Rx: %s' % avg)

# Antibiotic items
ab_items = DispensingItem.objects.filter(
    dispensing__is_deleted=False,
    dispensing__dispensed_at__date__gte=month_start,
    dispensing__dispensed_at__date__lte=month_end,
    drug__category='ANTIBIOTIC',
).count()
ab_rate = round(ab_items / total_items * 100, 1) if total_items else 0
print('Antibiotic items: %d (%s%%)' % (ab_items, ab_rate))

# Generic prescribing
generic_ct = DispensingItem.objects.filter(
    dispensing__is_deleted=False,
    dispensing__dispensed_at__date__gte=month_start,
    dispensing__dispensed_at__date__lte=month_end,
    drug__generic_name__gt='',
).count()
gen_rate = round(generic_ct / total_items * 100, 1) if total_items else 0
print('Generic prescribing rate: %s%% (%d/%d)' % (gen_rate, generic_ct, total_items))

# Injection rate
inj = DispensingItem.objects.filter(
    dispensing__is_deleted=False,
    dispensing__dispensed_at__date__gte=month_start,
    dispensing__dispensed_at__date__lte=month_end,
    drug__form='INJECTION',
).count()
inj_rate = round(inj / total_items * 100, 1) if total_items else 0
print('Injection rate: %s%%' % inj_rate)

# Formulary rate
formulary = DispensingItem.objects.filter(
    dispensing__is_deleted=False,
    dispensing__dispensed_at__date__gte=month_start,
    dispensing__dispensed_at__date__lte=month_end,
    drug__isnull=False,
).count()
form_rate = round(formulary / total_items * 100, 1) if total_items else 0
print('Formulary rate: %s%%' % form_rate)

# Controlled
ctrl = DispensingItem.objects.filter(
    dispensing__is_deleted=False,
    dispensing__dispensed_at__date__gte=month_start,
    dispensing__dispensed_at__date__lte=month_end,
    drug__is_controlled=True,
).count()
print('Controlled items: %d' % ctrl)

# Stock
active_drugs = Drug.objects.filter(is_active=True, is_deleted=False).count()
drugs_with_stock = Drug.objects.filter(
    is_active=True, is_deleted=False,
    stock_items__is_deleted=False, stock_items__expiry_date__gte=today,
    stock_items__quantity_remaining__gt=0,
).distinct().count()
stockout = active_drugs - drugs_with_stock
print('Active drugs: %d  With stock: %d  Stockout: %d (%s%%)' % (
    active_drugs, drugs_with_stock, stockout,
    round(stockout / active_drugs * 100, 1) if active_drugs else 0))

# Inventory value
inv_val = DrugStock.objects.filter(
    is_deleted=False, quantity_remaining__gt=0, expiry_date__gte=today,
).aggregate(val=Sum(F('quantity_remaining') * F('purchase_price')))['val'] or 0
print('Inventory value: %s FCFA' % '{:,.0f}'.format(float(inv_val)))

# COGS
cogs = DispensingItem.objects.filter(
    dispensing__is_deleted=False,
    dispensing__dispensed_at__date__gte=month_start,
    dispensing__dispensed_at__date__lte=month_end,
    drug__isnull=False,
).aggregate(cost=Sum(F('quantity_dispensed') * F('drug__cost_price')))['cost'] or 0
print('COGS: %s FCFA' % '{:,.0f}'.format(float(cogs)))

# Gross margin
margin = round((float(revenue) - float(cogs)) / float(revenue) * 100, 1) if revenue else 0
print('Gross margin: %s%%' % margin)

# Expired this month
expired = DrugStock.objects.filter(
    is_deleted=False, expiry_date__gte=month_start, expiry_date__lte=month_end,
)
exp_units = expired.aggregate(u=Sum('quantity_remaining'))['u'] or 0
exp_val = expired.aggregate(v=Sum(F('quantity_remaining') * F('purchase_price')))['v'] or 0
print('Expired this month: %d units (%s FCFA)' % (exp_units, '{:,.0f}'.format(float(exp_val))))

# Near-expiry
near = DrugStock.objects.filter(
    is_deleted=False, quantity_remaining__gt=0,
    expiry_date__gt=today, expiry_date__lte=today + timedelta(days=30),
).count()
print('Near-expiry batches (<30d): %d' % near)

# Gender
gender_raw = Dispensing.objects.filter(
    is_deleted=False, dispensed_at__date__gte=month_start, dispensed_at__date__lte=month_end,
).values('patient__gender').annotate(c=Count('id'))
gender_map = {g['patient__gender']: g['c'] for g in gender_raw}
print('Male: %d  Female: %d' % (gender_map.get('M', 0), gender_map.get('F', 0)))

# OTC vs Rx
otc = Dispensing.objects.filter(is_deleted=False, dispensed_at__date__gte=month_start, dispensed_at__date__lte=month_end, is_otc=True).count()
rx = Dispensing.objects.filter(is_deleted=False, dispensed_at__date__gte=month_start, dispensed_at__date__lte=month_end, is_otc=False).count()
otc_rev = Dispensing.objects.filter(is_deleted=False, dispensed_at__date__gte=month_start, dispensed_at__date__lte=month_end, is_otc=True, status='DISPENSED').aggregate(r=Sum('total_amount'))['r'] or 0
rx_rev = Dispensing.objects.filter(is_deleted=False, dispensed_at__date__gte=month_start, dispensed_at__date__lte=month_end, is_otc=False, status='DISPENSED').aggregate(r=Sum('total_amount'))['r'] or 0
print('OTC: %d (%s FCFA)  Rx: %d (%s FCFA)' % (otc, '{:,.0f}'.format(float(otc_rev)), rx, '{:,.0f}'.format(float(rx_rev))))

# Returns
ret = DispensingReturn.objects.filter(
    is_deleted=False, created_at__date__gte=month_start, created_at__date__lte=month_end,
)
ret_count = ret.count()
ret_qty = ret.aggregate(q=Sum('quantity_returned'))['q'] or 0
print('Returns: %d (%d units)' % (ret_count, ret_qty))

# Verification / Counseling
verified = Dispensing.objects.filter(
    is_deleted=False, dispensed_at__date__gte=month_start, dispensed_at__date__lte=month_end,
    verified_by_pharmacist__isnull=False,
).count()
counseled = Dispensing.objects.filter(
    is_deleted=False, dispensed_at__date__gte=month_start, dispensed_at__date__lte=month_end,
    counseling_given=True,
).count()
print('Verified: %d/%d (%s%%)' % (verified, dispensed, round(verified/dispensed*100, 1) if dispensed else 0))
print('Counseled: %d/%d (%s%%)' % (counseled, dispensed, round(counseled/dispensed*100, 1) if dispensed else 0))

# Substitution
sub = DispensingItem.objects.filter(
    dispensing__is_deleted=False,
    dispensing__dispensed_at__date__gte=month_start,
    dispensing__dispensed_at__date__lte=month_end,
    substituted_for__gt='',
).count()
sub_rate = round(sub / total_items * 100, 1) if total_items else 0
print('Substitutions: %d (%s%%)' % (sub, sub_rate))

# Top 5 drugs
top = DispensingItem.objects.filter(
    dispensing__is_deleted=False,
    dispensing__dispensed_at__date__gte=month_start,
    dispensing__dispensed_at__date__lte=month_end,
).values('drug__name', 'custom_drug_name').annotate(
    cnt=Count('id'), qty=Sum('quantity_dispensed')
).order_by('-qty')[:5]
print()
print('Top 5 drugs:')
for d in top:
    name = d['drug__name'] or d['custom_drug_name'] or 'Non-formulary'
    print('  %s: %d rx, %d qty' % (name, d['cnt'], d['qty'] or 0))

# Staff throughput
staff = Dispensing.objects.filter(
    is_deleted=False, dispensed_at__date__gte=month_start, dispensed_at__date__lte=month_end,
    status='DISPENSED',
).values('dispensed_by__first_name', 'dispensed_by__last_name').annotate(
    c=Count('id'), r=Sum('total_amount')
).order_by('-c')[:5]
print()
print('Staff throughput (top 5):')
for s in staff:
    name = '%s %s' % (s['dispensed_by__first_name'], s['dispensed_by__last_name'])
    print('  %s: %d rx, %s FCFA' % (name.strip(), s['c'], '{:,.0f}'.format(float(s['r'] or 0))))

# Low stock count
_stock_q = Q(stock_items__is_deleted=False, stock_items__expiry_date__gte=today)
low_stock = Drug.objects.filter(is_active=True, is_deleted=False).annotate(
    _stock=Coalesce(Sum('stock_items__quantity_remaining', filter=_stock_q), Value(0, output_field=IntegerField()))
).filter(_stock__lte=F('reorder_level')).count()
print()
print('Low stock drugs: %d' % low_stock)

# Rx decline
try:
    from apps.prescriptions.models import DrugPrescription
    total_rx = DrugPrescription.objects.filter(
        is_deleted=False, prescription_date__date__gte=month_start, prescription_date__date__lte=month_end,
    ).count()
    declined_rx = DrugPrescription.objects.filter(
        is_deleted=False, prescription_date__date__gte=month_start, prescription_date__date__lte=month_end,
        notes__icontains='Bought elsewhere',
    ).count()
    print('Rx decline: %d/%d (%s%%)' % (declined_rx, total_rx, round(declined_rx/total_rx*100, 1) if total_rx else 0))
except Exception as e:
    print('Rx decline check error: %s' % e)

# Working days
_end = min(month_end, today)
working_days = sum(1 for i in range((_end - month_start).days + 1) if (month_start + timedelta(days=i)).weekday() < 6)
working_days = max(working_days, 1)
rx_per_day = round(dispensed / working_days, 1)
print('Working days: %d  Rx/day: %s' % (working_days, rx_per_day))

# Stock turnover
turnover = round(float(cogs) / float(inv_val), 2) if inv_val else 0
print('Stock turnover: %sx' % turnover)

print()
print('=== FIELD EXISTENCE CHECK ===')
d = Dispensing.objects.first()
if d:
    for f in ['is_otc', 'verified_by_pharmacist', 'counseling_given', 'total_amount', 'status']:
        print('  Dispensing.%s: %s' % (f, hasattr(d, f)))
di = DispensingItem.objects.first()
if di:
    for f in ['quantity_dispensed', 'unit_price', 'subtotal', 'drug', 'stock_batch', 'substituted_for', 'custom_drug_name']:
        print('  DispensingItem.%s: %s' % (f, hasattr(di, f)))
dr = Drug.objects.first()
if dr:
    for f in ['cost_price', 'selling_price', 'price_express', 'price_vip', 'price_executive_vip', 'price_staff', 'price_outreach', 'insurance_markup_pct', 'is_controlled', 'generic_name', 'form', 'category']:
        print('  Drug.%s: %s' % (f, hasattr(dr, f)))

# Category choices check
from apps.pharmacy.models import DrugCategory
print()
print('Drug categories: %s' % [c[0] for c in DrugCategory.choices])
print('Drugs with ANTIBIOTIC category: %d' % Drug.objects.filter(category='ANTIBIOTIC', is_deleted=False).count())
print('Drugs with INJECTION form: %d' % Drug.objects.filter(form='INJECTION', is_deleted=False).count())
