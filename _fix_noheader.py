"""
Fix templates that have page title in {% block content %} with no {% block page_header %}.
Extracts the title+buttons div and moves it to a new page_header block.
"""
import os, re, glob

TEMPLATES = "c:/Users/GROD/Desktop/EHR AFRICA BACKUP/templates"

# Pattern: {% block content %} optionally followed by letterhead, then title div
TITLE_PAT = re.compile(
    r'(\{%\s*block\s+content\s*%\}\n?)'
    r'(\{%\s*include\s+[\'"]components/letterhead\.html[\'"]\s*%\}\n?\n?)?'
    r'(\s*<div class="(?:gap-2 flex-wrap d-flex|flex-wrap gap-2 d-flex|d-flex[^"]*justify-content-between[^"]*)"[^>]*>\s*'
    r'(?:(?!</div>\s*<div).)*?'   # content of title div (stop before sibling divs)
    r'</div>\s*</div>\n?)',        # close inner div + outer div
    re.DOTALL
)

# Simpler pattern for the outer wrapper div + its two children
OUTER_PAT = re.compile(
    r'\n?(\s*<div class="[^"]*d-flex[^"]*justify-content-between[^"]*"[^>]*>\n'
    r'\s*<div>.*?</div>\n'
    r'\s*<div[^>]*>.*?</div>\n'
    r'\s*</div>)',
    re.DOTALL
)

def fix_file(path):
    with open(path, encoding='utf-8') as f:
        src = f.read()
    orig = src

    # Skip if already has page_header with content
    if re.search(r'\{%\s*block\s+page_header\s*%\}.+?\{%\s*endblock', src, re.DOTALL):
        return False

    # Find content block start + optional letterhead + first d-flex title div
    m = re.search(
        r'(\{%\s*block\s+content\s*%\}\n?)'
        r'(\{%\s*include\s+[\'"]components/letterhead\.html[\'"]\s*%\}\n\n?)?'
        r'(\s*<div class="[^"]*d-flex[^"]*justify-content-between[^"]*"[^>]*>)',
        src, re.DOTALL
    )
    if not m:
        return False

    # Find the matching closing tag for this outer div
    start_outer = m.start(3)
    pos = src.index('>', start_outer) + 1  # after opening >
    depth = 1
    i = pos
    while i < len(src) and depth > 0:
        if src[i:i+4] == '<div':
            depth += 1
            i += 4
        elif src[i:i+6] == '</div>':
            depth -= 1
            if depth == 0:
                break
            i += 6
        else:
            i += 1
    end_outer = i + 6  # include </div>

    title_div = src[start_outer:end_outer]

    # Normalize heading in extracted div: h4 → h5 with fw-bold mb-0
    title_div = re.sub(r'<h4(\s[^>]*)?>', lambda x: x.group(0).replace('<h4', '<h5'), title_div)
    title_div = re.sub(r'</h4>', '</h5>', title_div)
    def ensure_h5(hm):
        tag = hm.group(0)
        if 'mb-0' not in tag:
            tag = tag.replace('class="', 'class="mb-0 ')
        if 'fw-bold' not in tag:
            tag = tag.replace('class="', 'class="fw-bold ')
        return tag
    title_div = re.sub(r'<h5[^>]*>', ensure_h5, title_div)
    # Add flex-wrap gap-2 if missing on wrapper
    def ensure_wrapper(wm):
        tag = wm.group(0)
        if 'gap-' not in tag:
            tag = tag.replace('class="', 'class="gap-2 ')
        if 'flex-wrap' not in tag:
            tag = tag.replace('class="', 'class="flex-wrap ')
        return tag
    title_div = re.sub(
        r'^<div class="[^"]*d-flex[^"]*justify-content-between[^"]*"[^>]*>',
        ensure_wrapper, title_div.strip()
    )

    # Build new page_header block
    new_page_header = (
        '{{% block page_header %}}\n'
        '{title}\n'
        '{{% endblock %}}\n\n'
    ).format(title=title_div.strip())

    # Find where to insert page_header block — before the extends endblock or at block title end
    # Insert before {% block content %}
    content_block_start = m.start(1)

    # Replace: inject page_header before content, remove title div from content
    letterhead = m.group(2) or ''
    block_start_text = m.group(1)

    # What to keep in content block: letterhead (if present) after removing title div
    old_section = src[content_block_start:end_outer]
    new_section = (
        new_page_header +
        block_start_text +
        (letterhead if letterhead else '')
    )

    src = src[:content_block_start] + new_section + src[end_outer:]

    if src != orig:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(src)
        return True
    return False

files = [
    "billing/advance_detail.html","billing/asset_list.html","billing/bank_reconciliation_detail.html",
    "billing/cash_count_form.html","billing/cash_count_list.html","billing/discount_approval_list.html",
    "billing/maintenance_list.html","billing/month_end_detail.html","billing/month_end_form.html",
    "billing/month_end_list.html","billing/wallet_detail.html","billing/wallet_list.html",
    "billing/withholding_tax_form.html","billing/withholding_tax_list.html","billing/work_queue.html",
    "consultations/list.html","consultations/triage_workstation.html",
    "ipd/bed_map.html","ipd/surgical_outcome_list.html","ipd/surgical_outcome_report.html",
    "ipd/theatre_board.html","ipd/theatre_utilization.html",
    "leadership/retina_dashboard.html",
    "opticals/lab_queue.html","opticals/lens_price_matrix.html","opticals/order_detail.html",
    "opticals/order_list.html","opticals/repair_list.html","opticals/uncollected_orders.html","opticals/warranty_list.html",
    "outreach/sync.html",
    "patients/amendment_list.html","patients/chart_deficiency.html","patients/consent_review.html",
    "patients/document_review.html","patients/record_release_list.html","patients/tier_change_log.html",
    "patients/tier_change_requests.html",
    "payroll/assignment_list.html","payroll/dashboard.html","payroll/payslip_detail.html","payroll/run_detail.html",
    "pharmacy/dashboard.html","pharmacy/direct_sale.html","pharmacy/expiry_alerts.html","pharmacy/unavailable_lines.html",
    "procurement/grn_form.html","procurement/po_detail.html","procurement/pr_detail.html",
    "qms/cashier_issue.html","qms/daily_census.html","qms/dashboard.html","qms/receptionist.html",
    "reports/analytics/disease_burden.html","reports/analytics/moh_export_form.html",
    "reports/analytics/revenue_report.html","reports/analytics/staff_performance.html",
    "billing/invoice_list.html",
]

changed = []
errors = []
for rel in files:
    path = f"{TEMPLATES}/{rel}"
    try:
        if fix_file(path):
            changed.append(rel)
    except Exception as e:
        errors.append((rel, str(e)))

print(f"Fixed {len(changed)}/{len(files)}, errors: {len(errors)}")
for c in changed:
    print(f"  OK  {c}")
for p, e in errors:
    print(f"  ERR {p}: {e}")
