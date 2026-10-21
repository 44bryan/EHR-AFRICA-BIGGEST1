"""
Spacing & heading normalization across all templates.

Pass 1 — page_header blocks:
  · h4 → h5 (normalize heading level)
  · Add mb-0 to h5 that's missing it
  · Add flex-wrap gap-2 to page-header d-flex wrappers missing them
  · Subtitle small/p: add page-subtitle class (targets #ehr-page-header .page-subtitle CSS)

Pass 2 — content block title divs that should be in page_header:
  · Templates where {% block content %} starts with letterhead then h4/h5 title
  · Move title+buttons div to page_header, remove it from content

Pass 3 — Card spacing consistency:
  · <div class="card border-0 shadow-sm"> without mb-3/mb-4 → add mb-3
  · row g-2 → row g-3 in KPI rows (inside card body/main content)
"""

import os, re, glob

TEMPLATES = "c:/Users/GROD/Desktop/EHR AFRICA BACKUP/templates"

def fix_file(path):
    with open(path, encoding='utf-8') as f:
        src = f.read()
    orig = src

    # ── Pass 1a: h4 → h5 in page_header blocks only ────────────────
    # Extract page_header blocks, fix h4, put back
    def fix_page_header_block(m):
        block = m.group(0)
        # h4 → h5
        block = re.sub(r'<h4(\s[^>]*)?>', lambda x: x.group(0).replace('<h4', '<h5'), block)
        block = re.sub(r'</h4>', '</h5>', block)
        # Ensure h5 has fw-bold mb-0 (add mb-0 if missing)
        def ensure_h5_classes(hm):
            tag = hm.group(0)
            if 'mb-0' not in tag:
                tag = tag.replace('class="', 'class="mb-0 ')
            if 'fw-bold' not in tag:
                tag = tag.replace('class="', 'class="fw-bold ')
            return tag
        block = re.sub(r'<h5[^>]*>', ensure_h5_classes, block)
        # Normalize wrapper: d-flex justify-content-between → add flex-wrap gap-2 if missing
        def ensure_wrapper_classes(wm):
            tag = wm.group(0)
            if 'gap-' not in tag:
                tag = tag.replace('class="', 'class="gap-2 ')
            if 'flex-wrap' not in tag:
                tag = tag.replace('class="', 'class="flex-wrap ')
            return tag
        block = re.sub(
            r'<div class="[^"]*d-flex[^"]*justify-content-between[^"]*"',
            ensure_wrapper_classes, block
        )
        return block

    src = re.sub(
        r'\{%\s*block\s+page_header\s*%\}.*?\{%\s*endblock\s*%\}',
        fix_page_header_block, src, flags=re.DOTALL
    )

    # ── Pass 1b: subtitle text-muted paragraphs in page_header ──────
    # <p class="text-muted small mb-0"> → add page-subtitle
    def add_subtitle_class(m):
        tag = m.group(0)
        if 'page-subtitle' not in tag and 'text-muted' in tag:
            tag = re.sub(r'class="', 'class="page-subtitle ', tag)
        return tag
    src = re.sub(
        r'\{%\s*block\s+page_header\s*%\}.*?\{%\s*endblock\s*%\}',
        lambda m: re.sub(r'<(?:p|div|small)[^>]*class="[^"]*text-muted[^"]*"[^>]*>',
                         add_subtitle_class, m.group(0)),
        src, flags=re.DOTALL
    )

    # ── Pass 2: Move title from content block to page_header ─────────
    # Pattern: template with empty/missing page_header block AND
    # content block starts with letterhead then title div
    has_page_header_block = bool(re.search(r'\{%\s*block\s+page_header\s*%\}\s*\{%\s*endblock', src))

    if has_page_header_block:
        # Has an EMPTY page_header block — try to find title in content
        content_match = re.search(
            r'(\{%\s*block\s+content\s*%\}\s*)'
            r'(\{%\s*include\s+[\'"]components/letterhead\.html[\'"]\s*%\}\s*\n?)?'
            r'(\s*<div class="d-flex[^"]*justify-content-between[^"]*"[^>]*>\s*'
            r'<div>\s*<h[45][^>]*>[^<]+</h[45]>.*?</div>\s*</div>)',
            src, re.DOTALL
        )
        if content_match:
            block_start = content_match.group(1)
            letterhead = content_match.group(2) or ''
            title_div = content_match.group(3)

            # Fix heading in extracted div
            title_div = re.sub(r'<h4(\s[^>]*)?>', lambda x: x.group(0).replace('<h4', '<h5'), title_div)
            title_div = re.sub(r'</h4>', '</h5>', title_div)

            # Replace empty page_header with the extracted title div
            new_page_header = '{{% block page_header %}}\n{title}\n{{% endblock %}}'.format(
                title=title_div.strip()
            )
            src = re.sub(
                r'\{%\s*block\s+page_header\s*%\}\s*\{%\s*endblock\s*(%\s+page_header)?\s*%\}',
                new_page_header, src
            )

            # Remove the title div from content block (keep letterhead)
            old_content_section = content_match.group(0)
            new_content_section = block_start + (letterhead if letterhead else '\n')
            src = src.replace(old_content_section, new_content_section, 1)

    # ── Pass 3: Card spacing ─────────────────────────────────────────
    # Cards without margin-bottom get mb-3
    def add_card_mb(m):
        tag = m.group(0)
        if 'mb-' not in tag and 'mt-' not in tag:
            tag = tag.replace('class="card ', 'class="card mb-3 ')
        return tag
    src = re.sub(
        r'<div class="card [^"]*shadow-sm"(?!\s*style)',
        add_card_mb, src
    )

    if src != orig:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(src)
        return True
    return False

def main():
    files = glob.glob(f"{TEMPLATES}/**/*.html", recursive=True)
    changed = []
    errors = []
    for path in files:
        try:
            if fix_file(path):
                rel = path.replace(TEMPLATES + '/', '').replace(TEMPLATES + '\\', '')
                changed.append(rel)
        except Exception as e:
            errors.append((path, str(e)))

    print(f"\n{'='*60}")
    print(f"Fixed {len(changed)} templates, {len(errors)} errors")
    if changed:
        print("\nChanged:")
        for c in sorted(changed):
            print(f"  {c}")
    if errors:
        print("\nErrors:")
        for path, err in errors:
            print(f"  {path}: {err}")

if __name__ == '__main__':
    main()
