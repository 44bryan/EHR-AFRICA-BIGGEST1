"""Fix colored borders and backgrounds on all clinical form templates."""
import re, glob, os

base = 'templates/consultations/clinical'
files = glob.glob(f'{base}/*_form.html')

for fp in files:
    with open(fp, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content

    # 1. Remove colored border classes on zone wrappers
    for color in ['primary', 'info', 'success', 'warning', 'secondary']:
        content = content.replace(f' border border-{color} border-opacity-25', '')

    # 2. Replace blue header background with neutral bg-light
    content = re.sub(
        r'style="background:#e7f1ff;\s*border-bottom:1px solid #b6d4fe;\s*cursor:pointer;"',
        'class="bg-light border-bottom" style="cursor:pointer;"',
        content
    )
    content = re.sub(
        r'style="background:#e7f1ff;\s*border-bottom:1px solid #b6d4fe;"',
        'class="bg-light border-bottom"',
        content
    )

    # 3. Remove grey zone background
    content = re.sub(r'\s*style="background:#f8f9fa;opacity:\.\d+;"', '', content)
    content = re.sub(r'\s*style="background:#f8f9fa;"', '', content)

    # 4. Neutralize colored text classes
    for color in ['primary', 'info', 'success', 'warning']:
        content = content.replace(f' text-uppercase text-{color}', ' text-uppercase text-secondary')
        content = content.replace(f' fw-bold text-{color}', ' fw-bold text-secondary')
        content = content.replace(f' text-{color} small text-uppercase', ' text-secondary small text-uppercase')

    # 5. Remove inline color styles
    for c in ['#0aa2c0', '#198754', '#6f42c1', '#155724', '#92400e', '#856404', '#2563eb', '#0d6efd']:
        content = content.replace(f';color:{c}', '')
        content = content.replace(f'color:{c};', '')
        content = content.replace(f'color:{c}', '')

    if content != original:
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'Updated: {os.path.basename(fp)}')
    else:
        print(f'No change: {os.path.basename(fp)}')
