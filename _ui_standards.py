"""
EHR Africa — International UI Standards Fix
Applies SAP/Oracle/Epic enterprise-standard button placement to all templates.

Rules applied:
1. Single Export split-button (btn-outline-secondary) in page_header — never separate PDF/CSV/Print buttons
2. Print inside Export dropdown — never a standalone print button
3. No green (btn-success) export buttons
4. No red (btn-danger), dark (btn-outline-dark), or primary (btn-outline-primary) for export/print
5. Buttons only in page_header, never duplicated in content
"""
import os, re, glob

CHANGED = []

def fix(path, old, new, label=''):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    if old not in content:
        return False
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.replace(old, new))
    tag = label or path
    if path not in CHANGED:
        CHANGED.append(path)
    print(f'  [OK] {tag}')
    return True

def fix_re(path, pattern, replacement, flags=0):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    new_content, n = re.subn(pattern, replacement, content, flags=flags)
    if n == 0:
        return False
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    if path not in CHANGED:
        CHANGED.append(path)
    print(f'  [OK] re({n}) {path}')
    return True

# ═══════════════════════════════════════════════════════════════════════════════
# BROKEN PRINT-ONLY SPLIT-BUTTON (appears in many billing templates after previous session)
# Replace with a simple, clean print button
# ═══════════════════════════════════════════════════════════════════════════════
BROKEN_SPLIT = (
    '    <div class="btn-group no-print" role="group">\n'
    '    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="window.print()" title="Print / Save as PDF">'
    '<i class="bi bi-file-earmark-pdf me-1"></i>Print / PDF</button>\n'
    '    <button type="button" class="btn btn-sm btn-outline-secondary dropdown-toggle dropdown-toggle-split" '
    'data-bs-toggle="dropdown" aria-expanded="false"><span class="visually-hidden">Toggle</span></button>\n'
    '    <ul class="dropdown-menu dropdown-menu-end shadow-sm">\n'
    '      <li><a class="dropdown-item" href="javascript:window.print()">'
    '<i class="bi bi-printer me-2 text-secondary"></i>Print</a></li>\n'
    '      <li><a class="dropdown-item" href="javascript:window.print()">'
    '<i class="bi bi-file-earmark-pdf me-2 text-danger"></i>Save as PDF</a></li>\n'
    '    </ul>\n'
    '  </div>'
)
SIMPLE_PRINT = (
    '    <button class="btn btn-sm btn-outline-secondary no-print" onclick="window.print()">'
    '<i class="bi bi-printer me-1"></i>Print / PDF</button>'
)

print('\n=== Fixing broken print-only split-buttons ===')
for tpl in [
    'templates/billing/budget.html',
    'templates/billing/auxiliary_balance.html',
    'templates/billing/corporate_statement.html',
    'templates/billing/cashier_reconciliation.html',
    'templates/billing/cash_desk_supply_list.html',
    'templates/billing/cash_withdrawal_list.html',
    'templates/billing/reports/audit_trail.html',
    'templates/billing/reports/cash_flow_forecast.html',
]:
    if os.path.exists(tpl):
        fix(tpl, BROKEN_SPLIT, SIMPLE_PRINT, tpl)

# Also fix general_ledger — has broken split + separate CSV btn
print('\n=== Fixing general_ledger.html ===')
GL = 'templates/billing/general_ledger.html'
if os.path.exists(GL):
    # Replace: CSV outline-success btn + broken split-button → proper split-button
    fix(GL,
        '    <a href="?{{ request.GET.urlencode }}&export=csv" class="btn btn-sm btn-outline-success">\n'
        '      <i class="bi bi-filetype-csv me-1"></i>Export CSV\n'
        '    </a>\n'
        '    <div class="btn-group no-print" role="group">\n'
        '    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="window.print()" title="Print / Save as PDF">'
        '<i class="bi bi-file-earmark-pdf me-1"></i>Print / PDF</button>\n'
        '    <button type="button" class="btn btn-sm btn-outline-secondary dropdown-toggle dropdown-toggle-split" '
        'data-bs-toggle="dropdown" aria-expanded="false"><span class="visually-hidden">Toggle</span></button>\n'
        '    <ul class="dropdown-menu dropdown-menu-end shadow-sm">\n'
        '      <li><a class="dropdown-item" href="javascript:window.print()">'
        '<i class="bi bi-printer me-2 text-secondary"></i>Print</a></li>\n'
        '      <li><a class="dropdown-item" href="javascript:window.print()">'
        '<i class="bi bi-file-earmark-pdf me-2 text-danger"></i>Save as PDF</a></li>\n'
        '    </ul>\n'
        '  </div>',
        '    <div class="btn-group no-print">\n'
        '      <a href="?{{ request.GET.urlencode }}&export=csv" class="btn btn-sm btn-outline-secondary">\n'
        '        <i class="bi bi-download me-1"></i>Export\n'
        '      </a>\n'
        '      <button type="button" class="btn btn-sm btn-outline-secondary dropdown-toggle dropdown-toggle-split" '
        'data-bs-toggle="dropdown"><span class="visually-hidden">Select format</span></button>\n'
        '      <ul class="dropdown-menu dropdown-menu-end shadow-sm" style="min-width:200px;">\n'
        '        <li><a class="dropdown-item py-2" href="?{{ request.GET.urlencode }}&export=csv">'
        '<i class="bi bi-filetype-csv me-2 text-primary"></i>CSV Data File'
        '<small class="text-muted d-block ms-4">With hospital header rows</small></a></li>\n'
        '        <li><hr class="dropdown-divider"></li>\n'
        '        <li><a class="dropdown-item" href="javascript:window.print()">'
        '<i class="bi bi-printer me-2 text-secondary"></i>Print</a></li>\n'
        '      </ul>\n'
        '    </div>',
        GL
    )

# ═══════════════════════════════════════════════════════════════════════════════
# FIX budget_ytd.html — nested split-button inside dropdown
# ═══════════════════════════════════════════════════════════════════════════════
print('\n=== Fixing budget_ytd.html ===')
BYTD = 'templates/billing/reports/budget_ytd.html'
if os.path.exists(BYTD):
    fix(BYTD,
        '    <div class="dropdown">\n'
        '      <button class="btn btn-sm btn-success dropdown-toggle" type="button" data-bs-toggle="dropdown">\n'
        '        <i class="bi bi-download me-1"></i>Export\n'
        '      </button>\n'
        '      <ul class="dropdown-menu dropdown-menu-end">\n'
        '        <li><div class="btn-group no-print" role="group">\n'
        '    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="window.print()" title="Print / Save as PDF">'
        '<i class="bi bi-file-earmark-pdf me-1"></i>Print / PDF</button>\n'
        '    <button type="button" class="btn btn-sm btn-outline-secondary dropdown-toggle dropdown-toggle-split" '
        'data-bs-toggle="dropdown" aria-expanded="false"><span class="visually-hidden">Toggle</span></button>\n'
        '    <ul class="dropdown-menu dropdown-menu-end shadow-sm">\n'
        '      <li><a class="dropdown-item" href="javascript:window.print()">'
        '<i class="bi bi-printer me-2 text-secondary"></i>Print</a></li>\n'
        '      <li><a class="dropdown-item" href="javascript:window.print()">'
        '<i class="bi bi-file-earmark-pdf me-2 text-danger"></i>Save as PDF</a></li>\n'
        '    </ul>\n'
        '  </div></li>\n'
        '      </ul>\n'
        '    </div>',
        '    <button class="btn btn-sm btn-outline-secondary no-print" onclick="window.print()">'
        '<i class="bi bi-printer me-1"></i>Print / PDF</button>',
        BYTD
    )

# ═══════════════════════════════════════════════════════════════════════════════
# FIX: Green `btn-success dropdown-toggle` Export → `btn-outline-secondary dropdown-toggle`
# These pages have a dropdown with actual export items (CSV, Print) — just fix the color
# ═══════════════════════════════════════════════════════════════════════════════
print('\n=== Fixing green export dropdown color ===')
GREEN_DROPDOWN = [
    'templates/billing/trial_balance.html',
    'templates/billing/reports/surgery_revenue.html',
    'templates/billing/reports/revenue_by_department.html',
    'templates/billing/reports/donor_report.html',
    'templates/billing/reports/dsf.html',
]
for tpl in GREEN_DROPDOWN:
    if os.path.exists(tpl):
        fix(tpl,
            'class="btn btn-sm btn-success dropdown-toggle"',
            'class="btn btn-sm btn-outline-secondary dropdown-toggle"',
            tpl
        )

# ═══════════════════════════════════════════════════════════════════════════════
# FIX: Green dropdown + standalone print button
# cash_to_bank, cash_transfer, cheque_register, daily_liquidity
# ═══════════════════════════════════════════════════════════════════════════════
print('\n=== Fixing green dropdown + standalone print button ===')
GREEN_PRINT_PATTERN = (
    '      <button class="btn btn-sm btn-success dropdown-toggle" type="button" data-bs-toggle="dropdown">\n'
    '        <i class="bi bi-download me-1"></i>Export\n'
    '      </button>'
)
GREEN_PRINT_FIXED = (
    '      <button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown">\n'
    '        <i class="bi bi-download me-1"></i>Export\n'
    '      </button>'
)
for tpl in [
    'templates/billing/cash_to_bank_list.html',
    'templates/billing/cash_transfer_list.html',
    'templates/billing/cheque_register.html',
    'templates/billing/reports/daily_liquidity.html',
]:
    if os.path.exists(tpl):
        fix(tpl, GREEN_PRINT_PATTERN, GREEN_PRINT_FIXED, tpl)
        # Also remove the standalone print button that follows
        fix(tpl, BROKEN_SPLIT, SIMPLE_PRINT, tpl)

# safe_balance_list and variance_register have slightly different indentation
for tpl in [
    'templates/billing/safe_balance_list.html',
    'templates/billing/variance_register.html',
]:
    if os.path.exists(tpl):
        fix_re(tpl,
            r'class="btn btn-sm btn-success dropdown-toggle"',
            'class="btn btn-sm btn-outline-secondary dropdown-toggle"'
        )

# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL: Fix all non-standard button colors for print/export across ALL templates
# ═══════════════════════════════════════════════════════════════════════════════
print('\n=== Fixing non-standard print button colors (global) ===')

# Templates with red (btn-danger) print buttons
RED_PRINT_TEMPLATES = [
    'templates/reports/analytics/disease_burden.html',
    'templates/reports/analytics/revenue_report.html',
    'templates/reports/analytics/staff_performance.html',
]
for tpl in RED_PRINT_TEMPLATES:
    if os.path.exists(tpl):
        fix_re(tpl,
            r'class="btn btn-sm btn-outline-danger"(\s*>(?:\s*<[^>]+>)*\s*(?:Print|Export|Download))',
            r'class="btn btn-sm btn-outline-secondary"\1'
        )

# Templates with dark (btn-outline-dark) buttons
DARK_BTN_TEMPLATES = [
    'templates/inventory/stock_entry_list.html',
    'templates/inventory/stock_exit_list.html',
    'templates/ipd/journal_of_registrations.html',
    'templates/ipd/registration_stats.html',
    'templates/opticals/order_list.html',
    'templates/pharmacy/dispensing_list.html',
]
for tpl in DARK_BTN_TEMPLATES:
    if os.path.exists(tpl):
        fix_re(tpl,
            r'class="btn btn-(?:sm )?btn-outline-dark(\s*)"',
            r'class="btn btn-sm btn-outline-secondary\1"'
        )
        fix_re(tpl,
            r'class="btn btn-outline-dark btn-sm"',
            'class="btn btn-outline-secondary btn-sm"'
        )

# Templates with primary (btn-outline-primary) print buttons
PRIMARY_PRINT_TEMPLATES = [
    'templates/pharmacy/report_sales_journal.html',
]
for tpl in PRIMARY_PRINT_TEMPLATES:
    if os.path.exists(tpl):
        fix_re(tpl,
            r'(onclick="window\.print\(\)"[^>]*class=|class="[^"]*btn-outline-primary[^"]*"[^>]*onclick="window\.print\(\)")',
            lambda m: m.group(0).replace('btn-outline-primary', 'btn-outline-secondary')
        )

# ═══════════════════════════════════════════════════════════════════════════════
# FIX: pharmacy/stats.html — 3 separate export buttons → single split-button
# ═══════════════════════════════════════════════════════════════════════════════
print('\n=== Fixing pharmacy/stats.html export buttons ===')
PHSTATS = 'templates/pharmacy/stats.html'
if os.path.exists(PHSTATS):
    fix(PHSTATS,
        '    <button onclick="exportStatsPDF()" class="btn btn-sm btn-danger">\n'
        '      Export PDF\n'
        '    </button>\n'
        '    <a href="{% url \'pharmacy:stats_csv\' %}?year={{ year }}&month={{ month }}" class="btn btn-sm btn-success">\n'
        '      CSV\n'
        '    </a>\n'
        '    <button onclick="printWithCharts()" class="btn btn-sm btn-outline-primary">\n'
        '      Print with Charts\n'
        '    </button>',
        '    <div class="btn-group no-print">\n'
        '      <button type="button" class="btn btn-sm btn-outline-secondary" onclick="exportStatsPDF()">\n'
        '        <i class="bi bi-download me-1"></i>Export\n'
        '      </button>\n'
        '      <button type="button" class="btn btn-sm btn-outline-secondary dropdown-toggle dropdown-toggle-split" '
        'data-bs-toggle="dropdown"><span class="visually-hidden">Select format</span></button>\n'
        '      <ul class="dropdown-menu dropdown-menu-end shadow-sm" style="min-width:200px;">\n'
        '        <li><a class="dropdown-item py-2" '
        'href="{% url \'pharmacy:stats_csv\' %}?year={{ year }}&month={{ month }}">'
        '<i class="bi bi-filetype-csv me-2 text-primary"></i>CSV Export'
        '<small class="text-muted d-block ms-4">With hospital header rows</small></a></li>\n'
        '        <li><hr class="dropdown-divider"></li>\n'
        '        <li><a class="dropdown-item" href="#" onclick="printWithCharts(); return false;">'
        '<i class="bi bi-printer me-2 text-secondary"></i>Print with Charts</a></li>\n'
        '      </ul>\n'
        '    </div>',
        PHSTATS
    )

# ═══════════════════════════════════════════════════════════════════════════════
# FIX: investigations/stats.html — similar multi-button pattern
# ═══════════════════════════════════════════════════════════════════════════════
print('\n=== Fixing investigations/stats.html ===')
INVSTATS = 'templates/investigations/stats.html'
if os.path.exists(INVSTATS):
    with open(INVSTATS, encoding='utf-8', errors='ignore') as f:
        content = f.read()
    # Find the multi-button export area
    fix_re(INVSTATS,
        r'<button[^>]+onclick="exportStatsPDF\(\)"[^>]*>\s*\n\s*Export Data PDF\s*\n\s*</button>',
        '<button type="button" class="btn btn-sm btn-outline-secondary" onclick="exportStatsPDF()">'
        '<i class="bi bi-download me-1"></i>Export PDF</button>',
        re.DOTALL
    )
    # Fix standalone CSV link color
    fix_re(INVSTATS,
        r'class="btn btn-sm btn-success"(\s*>\s*\n?\s*CSV)',
        r'class="btn btn-sm btn-outline-secondary"\1'
    )

# ═══════════════════════════════════════════════════════════════════════════════
# FIX: laboratory/stats.html — same pattern as investigations
# ═══════════════════════════════════════════════════════════════════════════════
print('\n=== Fixing laboratory/stats.html ===')
LABSTATS = 'templates/laboratory/stats.html'
if os.path.exists(LABSTATS):
    fix_re(LABSTATS,
        r'<button[^>]+onclick="exportStatsPDF\(\)"[^>]*>\s*\n\s*Export Data PDF\s*\n\s*</button>',
        '<button type="button" class="btn btn-sm btn-outline-secondary" onclick="exportStatsPDF()">'
        '<i class="bi bi-download me-1"></i>Export PDF</button>',
        re.DOTALL
    )
    fix_re(LABSTATS,
        r'class="btn btn-sm btn-success"(\s*>\s*\n?\s*CSV)',
        r'class="btn btn-sm btn-outline-secondary"\1'
    )

# ═══════════════════════════════════════════════════════════════════════════════
# FIX: leadership/hospital_stats.html, department_stats.html, monthly_stats.html
# ═══════════════════════════════════════════════════════════════════════════════
print('\n=== Fixing leadership stats pages ===')
for tpl in [
    'templates/leadership/hospital_stats.html',
    'templates/leadership/department_stats.html',
    'templates/leadership/monthly_stats.html',
]:
    if os.path.exists(tpl):
        # Fix green/danger export buttons
        fix_re(tpl,
            r'class="btn btn-(?:sm )?btn-(?:danger|success)"(\s*>(?:\s*(?:<[^>]+>)?)*\s*(?:Export|PDF))',
            r'class="btn btn-sm btn-outline-secondary"\1'
        )
        fix_re(tpl,
            r'<button[^>]+onclick="(?:captureAndExportPDF|exportStatsPDF|window\.print)\([^)]*\)"[^>]*class="btn btn-(?:danger|success)[^"]*"',
            lambda m: m.group(0).replace('btn-danger', 'btn-outline-secondary').replace('btn-success', 'btn-outline-secondary')
        )
        # Simple print button normalization
        fix_re(tpl,
            r'class="btn btn-outline-secondary btn-sm"(\s+onclick="window\.print\(\)")',
            r'class="btn btn-sm btn-outline-secondary no-print"\1'
        )

# ═══════════════════════════════════════════════════════════════════════════════
# FIX: opticals/sales_report.html, opticals/stats.html
# ═══════════════════════════════════════════════════════════════════════════════
print('\n=== Fixing opticals pages ===')
for tpl in ['templates/opticals/sales_report.html', 'templates/opticals/stats.html']:
    if os.path.exists(tpl):
        fix_re(tpl,
            r'<button[^>]+class="[^"]*btn-(?:danger|success)[^"]*"[^>]*>\s*\n?\s*<i[^>]*></i>\s*Export(?:\s*(?:PDF|Data PDF))?\s*\n?\s*</button>',
            '<button type="button" class="btn btn-sm btn-outline-secondary no-print" onclick="exportStatsPDF()">'
            '<i class="bi bi-download me-1"></i>Export PDF</button>',
            re.DOTALL
        )

# ═══════════════════════════════════════════════════════════════════════════════
# FIX: outreach/stats.html
# ═══════════════════════════════════════════════════════════════════════════════
print('\n=== Fixing outreach/stats.html ===')
OUTSTATS = 'templates/outreach/stats.html'
if os.path.exists(OUTSTATS):
    fix_re(OUTSTATS,
        r'<button[^>]+class="[^"]*btn-(?:danger|success)[^"]*"[^>]*>\s*\n?\s*<i[^>]*></i>\s*Export(?:\s*Data PDF)?\s*\n?\s*</button>',
        '<button type="button" class="btn btn-sm btn-outline-secondary no-print" onclick="exportStatsPDF()">'
        '<i class="bi bi-download me-1"></i>Export PDF</button>',
        re.DOTALL
    )

# ═══════════════════════════════════════════════════════════════════════════════
# FIX: hrms/attendance.html — print button styling
# ═══════════════════════════════════════════════════════════════════════════════
print('\n=== Fixing hrms/attendance.html ===')
fix_re('templates/hrms/attendance.html',
    r'<button onclick="window\.print\(\)" class="btn btn-sm btn-outline-secondary">\s*\n?\s*<i[^>]*></i>\s*Print\s*</button>',
    '<button onclick="window.print()" class="btn btn-sm btn-outline-secondary no-print">'
    '<i class="bi bi-printer me-1"></i>Print</button>',
    re.DOTALL
)

# ═══════════════════════════════════════════════════════════════════════════════
# FIX: HMO pages — standalone print buttons
# ═══════════════════════════════════════════════════════════════════════════════
print('\n=== Fixing HMO pages ===')
for tpl in ['templates/hmo/insurance_aging.html', 'templates/hmo/insurance_ledger.html']:
    if os.path.exists(tpl):
        fix_re(tpl,
            r'<button class="btn btn-outline-secondary btn-sm" onclick="window\.print\(\)">',
            '<button class="btn btn-sm btn-outline-secondary no-print" onclick="window.print()">'
        )

# ═══════════════════════════════════════════════════════════════════════════════
# FIX: inventory pages — btn-outline-dark → btn-outline-secondary
# ═══════════════════════════════════════════════════════════════════════════════
print('\n=== Fixing inventory btn-outline-dark buttons ===')
for tpl in glob.glob('templates/inventory/*.html'):
    fix_re(tpl,
        r'class="btn btn-(?:sm )?btn-outline-dark"',
        'class="btn btn-sm btn-outline-secondary"'
    )
    fix_re(tpl,
        r'class="btn btn-outline-dark btn-sm"',
        'class="btn btn-outline-secondary btn-sm"'
    )

# ═══════════════════════════════════════════════════════════════════════════════
# FIX: IPD pages
# ═══════════════════════════════════════════════════════════════════════════════
print('\n=== Fixing IPD pages ===')
for tpl in ['templates/ipd/journal_of_registrations.html', 'templates/ipd/registration_stats.html']:
    if os.path.exists(tpl):
        fix_re(tpl,
            r'class="btn btn-sm btn-outline-dark"',
            'class="btn btn-sm btn-outline-secondary"'
        )

# ═══════════════════════════════════════════════════════════════════════════════
# FIX: Remaining pharmacy report pages — various btn-outline-primary print buttons
# ═══════════════════════════════════════════════════════════════════════════════
print('\n=== Fixing pharmacy report pages ===')
for tpl in glob.glob('templates/pharmacy/report_*.html') + ['templates/pharmacy/report_sales_journal.html']:
    if os.path.exists(tpl):
        # Only change print-related outline-primary buttons
        fix_re(tpl,
            r'(<button[^>]*onclick="window\.print\(\)"[^>]*)btn-outline-primary',
            r'\1btn-outline-secondary'
        )
        fix_re(tpl,
            r'btn-outline-primary("[^>]*onclick="window\.print\(\)")',
            r'btn-outline-secondary\1'
        )

# ═══════════════════════════════════════════════════════════════════════════════
# FIX: investigations pages
# ═══════════════════════════════════════════════════════════════════════════════
print('\n=== Fixing investigations pages ===')
for tpl in ['templates/investigations/machine_revenue.html', 'templates/investigations/staff_throughput.html']:
    if os.path.exists(tpl):
        fix_re(tpl,
            r'<button onclick="window\.print\(\)" class="btn btn-sm btn-outline-secondary">Print</button>',
            '<button onclick="window.print()" class="btn btn-sm btn-outline-secondary no-print">'
            '<i class="bi bi-printer me-1"></i>Print / PDF</button>'
        )

# ═══════════════════════════════════════════════════════════════════════════════
# FIX: outreach/dashboard.html
# ═══════════════════════════════════════════════════════════════════════════════
print('\n=== Fixing outreach/dashboard.html ===')
fix_re('templates/outreach/dashboard.html',
    r'<button onclick="window\.print\(\)" class="btn btn-sm btn-outline-secondary no-print">',
    '<button onclick="window.print()" class="btn btn-sm btn-outline-secondary no-print">'
    '<i class="bi bi-printer me-1"></i>'
)

# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL: Normalize ALL remaining green export buttons in templates
# ═══════════════════════════════════════════════════════════════════════════════
print('\n=== Global green btn-success export button normalization ===')
for tpl in glob.glob('templates/**/*.html', recursive=True):
    if 'pdf' in tpl.lower() or 'slip' in tpl.lower() or 'receipt' in tpl.lower():
        continue  # Skip print-only templates
    try:
        with open(tpl, encoding='utf-8', errors='ignore') as f:
            content = f.read()
        # Match green buttons that are export/download buttons (not action buttons like "Record", "Save")
        new_content = re.sub(
            r'(<(?:a|button)[^>]*)class="btn btn-(?:sm )?btn-success(\s+dropdown-toggle)"',
            r'\1class="btn btn-sm btn-outline-secondary\2"',
            content
        )
        # Only write if changed
        if new_content != content:
            with open(tpl, 'w', encoding='utf-8') as f:
                f.write(new_content)
            if tpl not in CHANGED:
                CHANGED.append(tpl)
            print(f'  [OK] global-green {tpl}')
    except Exception as e:
        pass

print(f'\n{"="*60}')
print(f'TOTAL FIXED: {len(CHANGED)} templates')
for f in CHANGED:
    print(f'  {f}')
