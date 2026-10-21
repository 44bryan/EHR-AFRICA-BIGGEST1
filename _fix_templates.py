"""Fix scrambled export buttons in billing templates."""
import os

def fix(path, old, new=''):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    if old not in content:
        print(f'  [SKIP] pattern not found: {path}')
        return False
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.replace(old, new, 1))
    print(f'  [OK] {path}')
    return True

B = 'templates/billing'

# ─── ar_aging.html ───────────────────────────────────────────────────────────
# Remove: Download CSV button + duplicate split-button + old fmt buttons + print
fix(f'{B}/ar_aging.html',
    '\n    <a href="{% url \'billing:export_ar_aging\' %}" class="btn btn-success btn-sm">\n'
    '      Download CSV\n'
    '    </a>\n'
    '    <div class="btn-group no-print" role="group">\n'
    '    <a href="?format=pdf" class="btn btn-sm btn-outline-secondary" target="_blank" title="Export as PDF with hospital letterhead">'
    '<i class="bi bi-download me-1"></i>Export</a>\n'
    '    <button type="button" class="btn btn-sm btn-outline-secondary dropdown-toggle dropdown-toggle-split" '
    'data-bs-toggle="dropdown" aria-expanded="false"><span class="visually-hidden">Select format</span></button>\n'
    '    <ul class="dropdown-menu dropdown-menu-end shadow-sm" style="min-width:220px;">\n'
    '      <li><a class="dropdown-item py-2" href="?format=pdf" target="_blank">'
    '<i class="bi bi-file-earmark-pdf me-2 text-danger"></i><strong>PDF Report</strong>'
    '<small class="text-muted d-block ms-4">With hospital letterhead</small></a></li>\n'
    '      <li><a class="dropdown-item py-2" href="?format=excel" target="_blank">'
    '<i class="bi bi-file-earmark-excel me-2 text-success"></i>Excel Spreadsheet (.xlsx)'
    '<small class="text-muted d-block ms-4">With hospital header rows</small></a></li>\n'
    '      <li><a class="dropdown-item py-2" href="?format=csv">'
    '<i class="bi bi-filetype-csv me-2 text-primary"></i>CSV Data File'
    '<small class="text-muted d-block ms-4">With hospital header rows</small></a></li>\n'
    '      <li><hr class="dropdown-divider"></li>\n'
    '      <li><a class="dropdown-item" href="javascript:window.print()">'
    '<i class="bi bi-printer me-2 text-secondary"></i>Print</a></li>\n'
    '    </ul>\n'
    '  </div>\n'
    '      <a href="?format=excel" class="btn-export-fmt fmt-excel" target="_blank" title="Download Excel with hospital header">'
    '<i class="bi bi-file-earmark-excel"></i> <span class="d-none d-sm-inline">Excel</span></a>\n'
    '      <a href="?format=csv" class="btn-export-fmt fmt-csv" title="Download CSV with hospital header">'
    '<i class="bi bi-filetype-csv"></i> <span class="d-none d-sm-inline">CSV</span></a>\n'
    '    </div>\n'
    '    <button class="btn btn-sm btn-outline-secondary no-print ms-1" onclick="window.print()" title="Print">'
    '<i class="bi bi-printer"></i></button>',
    ''
)

# ─── balance_sheet.html ──────────────────────────────────────────────────────
fix(f'{B}/balance_sheet.html',
    '\n      <a href="?as_at={{ date_to }}&format=excel" class="btn-export-fmt fmt-excel" target="_blank" title="Download Excel with hospital header">'
    '<i class="bi bi-file-earmark-excel"></i> <span class="d-none d-sm-inline">Excel</span></a>\n'
    '      <a href="?as_at={{ date_to }}&format=csv" class="btn-export-fmt fmt-csv" title="Download CSV with hospital header">'
    '<i class="bi bi-filetype-csv"></i> <span class="d-none d-sm-inline">CSV</span></a>\n'
    '    </div>\n'
    '    <button class="btn btn-sm btn-outline-secondary no-print ms-1" onclick="window.print()" title="Print">'
    '<i class="bi bi-printer"></i></button>',
    ''
)

# ─── cash_flow.html ──────────────────────────────────────────────────────────
fix(f'{B}/cash_flow.html',
    '\n      <a href="?date_from={{ date_from }}&date_to={{ date_to }}&format=excel" class="btn-export-fmt fmt-excel" target="_blank" title="Download Excel with hospital header">'
    '<i class="bi bi-file-earmark-excel"></i> <span class="d-none d-sm-inline">Excel</span></a>\n'
    '      <a href="?date_from={{ date_from }}&date_to={{ date_to }}&format=csv" class="btn-export-fmt fmt-csv" title="Download CSV with hospital header">'
    '<i class="bi bi-filetype-csv"></i> <span class="d-none d-sm-inline">CSV</span></a>\n'
    '    </div>\n'
    '    <button class="btn btn-sm btn-outline-secondary no-print ms-1" onclick="window.print()" title="Print">'
    '<i class="bi bi-printer"></i></button>',
    ''
)

# ─── reports/ap_aging.html ───────────────────────────────────────────────────
fix(f'{B}/reports/ap_aging.html',
    '\n      <a href="?format=excel" class="btn-export-fmt fmt-excel" target="_blank" title="Download Excel with hospital header">'
    '<i class="bi bi-file-earmark-excel"></i> <span class="d-none d-sm-inline">Excel</span></a>\n'
    '      <a href="?format=csv" class="btn-export-fmt fmt-csv" title="Download CSV with hospital header">'
    '<i class="bi bi-filetype-csv"></i> <span class="d-none d-sm-inline">CSV</span></a>\n'
    '    </div>\n'
    '    <button class="btn btn-sm btn-outline-secondary no-print ms-1" onclick="window.print()" title="Print">'
    '<i class="bi bi-printer"></i></button>',
    ''
)

# ─── reports/monthly_summary.html ────────────────────────────────────────────
fix(f'{B}/reports/monthly_summary.html',
    '\n      <a href="?year={{ year }}&month={{ month }}&format=excel" class="btn-export-fmt fmt-excel" target="_blank" title="Download Excel with hospital header">'
    '<i class="bi bi-file-earmark-excel"></i> <span class="d-none d-sm-inline">Excel</span></a>\n'
    '      <a href="?year={{ year }}&month={{ month }}&format=csv" class="btn-export-fmt fmt-csv" title="Download CSV with hospital header">'
    '<i class="bi bi-filetype-csv"></i> <span class="d-none d-sm-inline">CSV</span></a>\n'
    '    </div>\n'
    '    <button class="btn btn-sm btn-outline-secondary no-print ms-1" onclick="window.print()" title="Print">'
    '<i class="bi bi-printer"></i></button>',
    ''
)

# ─── reports/top_services.html ───────────────────────────────────────────────
fix(f'{B}/reports/top_services.html',
    '\n      <a href="?date_from={{ date_from_str }}&date_to={{ date_to_str }}&format=excel" class="btn-export-fmt fmt-excel" target="_blank" title="Download Excel with hospital header">'
    '<i class="bi bi-file-earmark-excel"></i> <span class="d-none d-sm-inline">Excel</span></a>\n'
    '      <a href="?date_from={{ date_from_str }}&date_to={{ date_to_str }}&format=csv" class="btn-export-fmt fmt-csv" title="Download CSV with hospital header">'
    '<i class="bi bi-filetype-csv"></i> <span class="d-none d-sm-inline">CSV</span></a>\n'
    '    </div>\n'
    '    <button class="btn btn-sm btn-outline-secondary no-print ms-1" onclick="window.print()" title="Print">'
    '<i class="bi bi-printer"></i></button>',
    ''
)

# ─── reports/daily_summary.html ──────────────────────────────────────────────
# Remove old "Download PDF" danger button
fix(f'{B}/reports/daily_summary.html',
    '\n    <a href="?date={{ report_date|date:\'Y-m-d\' }}&format=pdf" class="btn btn-sm btn-danger" target="_blank">\n'
    '      Download PDF\n'
    '    </a>',
    ''
)
# Remove old fmt buttons + print
fix(f'{B}/reports/daily_summary.html',
    '\n      <a href="?date={{ report_date }}&format=excel" class="btn-export-fmt fmt-excel" target="_blank" title="Download Excel with hospital header">'
    '<i class="bi bi-file-earmark-excel"></i> <span class="d-none d-sm-inline">Excel</span></a>\n'
    '      <a href="?date={{ report_date }}&format=csv" class="btn-export-fmt fmt-csv" title="Download CSV with hospital header">'
    '<i class="bi bi-filetype-csv"></i> <span class="d-none d-sm-inline">CSV</span></a>\n'
    '    </div>\n'
    '    <button class="btn btn-sm btn-outline-secondary no-print ms-1" onclick="window.print()" title="Print">'
    '<i class="bi bi-printer"></i></button>',
    ''
)

# ─── reports/pl.html ─────────────────────────────────────────────────────────
# Read first to find pattern
with open(f'{B}/reports/pl.html', 'r', encoding='utf-8') as f:
    pl = f.read()
# Find and remove any btn-export-fmt / duplicate buttons block
import re
# Remove trailing old fmt buttons pattern (generic regex for pl)
pl_fixed = re.sub(
    r"\n      <a href=\"[^\"]+\" class=\"btn-export-fmt fmt-excel\"[^>]*>[^<]*(?:<[^>]*>[^<]*</[^>]*>)*</a>\n"
    r"      <a href=\"[^\"]+\" class=\"btn-export-fmt fmt-csv\"[^>]*>[^<]*(?:<[^>]*>[^<]*</[^>]*>)*</a>\n"
    r"    </div>\n"
    r"    <button class=\"btn btn-sm btn-outline-secondary no-print ms-1\" onclick=\"window\.print\(\)\" title=\"Print\">"
    r"<i class=\"bi bi-printer\"></i></button>",
    '',
    pl
)
if pl_fixed != pl:
    with open(f'{B}/reports/pl.html', 'w', encoding='utf-8') as f:
        f.write(pl_fixed)
    print(f'  [OK] {B}/reports/pl.html')
else:
    print(f'  [SKIP] no regex match in {B}/reports/pl.html')

# ─── List pages: replace broken split-button with simple CSV + Print ─────────
# These pages have: old "Download CSV" btn-success + broken split-btn (only Print)
# Pattern: remove the broken split-button; keep the CSV export button as-is

BROKEN_SPLIT_PRINT_PDF = (
    '\n    <div class="btn-group no-print" role="group">\n'
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
SIMPLE_PRINT_BTN = (
    '\n    <button class="btn btn-sm btn-outline-secondary no-print" onclick="window.print()" title="Print">'
    '<i class="bi bi-printer"></i></button>'
)

for tpl in ['invoice_list.html', 'expenses.html', 'corporate_list.html', 'patient_accounts.html']:
    fix(f'{B}/{tpl}', BROKEN_SPLIT_PRINT_PDF, SIMPLE_PRINT_BTN)

# ─── shift_list.html: has old export-format-group + fmt buttons ──────────────
fix(f'{B}/shift_list.html',
    '\n    <div class="export-format-group ms-1" title="Export">\n'
    '      <a href="?format=pdf" class="btn-export-fmt fmt-pdf" target="_blank">'
    '<i class="bi bi-file-earmark-pdf"></i> <span class="d-none d-sm-inline">PDF</span></a>\n'
    '      <a href="?format=excel" class="btn-export-fmt fmt-excel" target="_blank">'
    '<i class="bi bi-file-earmark-spreadsheet"></i> <span class="d-none d-sm-inline">Excel</span></a>\n'
    '      <a href="?format=csv" class="btn-export-fmt fmt-csv">'
    '<i class="bi bi-filetype-csv"></i> <span class="d-none d-sm-inline">CSV</span></a>\n'
    '    </div>\n'
    '    <button class="btn btn-sm btn-outline-secondary" onclick="window.print()">'
    '<i class="bi bi-printer"></i></button>',
    '\n    <button class="btn btn-sm btn-outline-secondary no-print" onclick="window.print()" title="Print">'
    '<i class="bi bi-printer"></i></button>'
)

# ─── remaining files with btn-export-fmt: generic regex cleanup ──────────────
remaining = [
    f'{B}/revenue_analysis.html',
    f'{B}/sales_journal.html',
    f'{B}/service_prices.html',
    f'{B}/shift_detail.html',
    f'{B}/void_register.html',
    f'{B}/reports/surgical_cost_summary.html',
    f'{B}/reports/syscohada_bilan.html',
    f'{B}/reports/tva_return.html',
]

EXPORT_FMT_PAT = re.compile(
    r'<div class="export-format-group[^"]*"[^>]*>.*?</div>\s*'
    r'(?:<button[^>]+onclick="window\.print\(\)"[^>]*>.*?</button>)?',
    re.DOTALL
)
LONE_FMT_LINKS = re.compile(
    r'<a\s+href="[^"]*"\s+class="btn-export-fmt[^"]*"[^>]*>.*?</a>\s*',
    re.DOTALL
)
LONE_PRINT_BTN = re.compile(
    r'<button\s+class="btn btn-sm btn-outline-secondary(?:\s+no-print)?(?:\s+ms-1)?"\s+onclick="window\.print\(\)"[^>]*>'
    r'<i class="bi bi-printer"></i></button>',
    re.DOTALL
)

for path in remaining:
    if not os.path.exists(path):
        print(f'  [MISSING] {path}')
        continue
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    original = content
    content = EXPORT_FMT_PAT.sub('', content)
    content = LONE_FMT_LINKS.sub('', content)
    # Only remove lone print buttons that aren't inside a proper split-btn group
    # (keep print buttons inside dropdown-menu items)
    if content != original:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'  [OK] {path}')
    else:
        print(f'  [SKIP] {path}')

print('\nAll done.')
