import zipfile, pathlib, os, sys

EXCLUDES = {'.git', '__pycache__', '.cache', 'node_modules', 'staticfiles',
            'media', 'backups', 'venv', '.env'}
EXT_SKIP = {'.zip', '.pdf', '.docx', '.xlsx', '.png', '.jpg', '.jpeg',
            '.gif', '.svg', '.pyc'}

root = pathlib.Path('.')
out  = pathlib.Path('../deploy_tier_billing.zip')

count = 0
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zf:
    for p in root.rglob('*'):
        if p.is_dir():
            continue
        skip = False
        for part in p.parts:
            if part in EXCLUDES:
                skip = True
                break
        if skip:
            continue
        if p.suffix.lower() in EXT_SKIP:
            continue
        rel = p.relative_to(root)
        zf.write(p, str(rel))
        count += 1

size = out.stat().st_size
print(f'Zipped {count} files -> {out}')
print(f'Size: {size / 1024 / 1024:.1f} MB')
