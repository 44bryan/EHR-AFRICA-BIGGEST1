"""UI/UX audit — button placement, colors, spacing, export patterns."""
import glob, re, collections, os

templates = glob.glob('templates/**/*.html', recursive=True)

btn_classes = collections.Counter()
justify = collections.Counter()
btn_xs_count = 0
export_pages = []
filter_pages = []
btn_placement_issues = []  # pages where primary action is NOT on the right

for t in templates:
    with open(t, encoding='utf-8', errors='ignore') as f:
        content = f.read()

    tname = t.replace(os.sep, '/').replace('templates/', '', 1)

    # Button classes
    for cls in re.findall(r'class="[^"]*btn-(\w[\w-]*)[^"]*"', content):
        if cls.startswith('btn'): continue
        btn_classes[cls] += 1

    # Justify-content
    for jc in re.findall(r'justify-content-(\w+)', content):
        justify[jc] += 1

    # btn-xs usage (non-standard Bootstrap class)
    if 'btn-xs' in content:
        btn_xs_count += 1

    # Export pages
    has_export = bool(re.search(r'export|download|\.pdf|print.*slip|print.*pdf', content, re.I))
    if has_export:
        export_pages.append(tname)

    # Filter pages (GET forms)
    if re.search(r'method=["\']get["\']', content, re.I):
        filter_pages.append(tname)

    # Button placement — check if primary action btn on wrong side
    # Pattern: d-flex with btn-primary NOT in justify-content-end/between
    if 'btn-primary' in content or 'btn-success' in content:
        # Check if form actions use justify-content-start (wrong)
        if 'justify-content-start' in content and ('btn-primary' in content or 'btn-success' in content):
            btn_placement_issues.append(tname)

print("=== BUTTON COLOR CLASSES (frequency) ===")
color_map = {}
for cls, cnt in btn_classes.most_common(30):
    color_map[cls] = cnt
    print(f"  btn-{cls}: {cnt}")

print(f"\n=== JUSTIFY-CONTENT USAGE ===")
for jc, cnt in justify.most_common():
    print(f"  justify-content-{jc}: {cnt}")

print(f"\n=== btn-xs (non-standard): {btn_xs_count} files ===")

print(f"\n=== PAGES WITH EXPORT/PDF ({len(export_pages)}) ===")
for e in sorted(export_pages)[:40]:
    print(f"  {e}")
if len(export_pages) > 40:
    print(f"  ... and {len(export_pages)-40} more")

print(f"\n=== PAGES WITH FILTER FORMS ({len(filter_pages)}) ===")
for f in sorted(filter_pages)[:20]:
    print(f"  {f}")

print(f"\n=== POTENTIAL BUTTON PLACEMENT ISSUES ({len(btn_placement_issues)}) ===")
for p in btn_placement_issues[:20]:
    print(f"  {p}")
