import os, re, sys

base = os.path.join(os.path.dirname(__file__), 'templates')
opacity_colors = ['primary', 'success', 'warning', 'danger', 'info', 'dark']

changed = []
for root, dirs, files in os.walk(base):
    for f in files:
        if not f.endswith('.html'):
            continue
        path = os.path.join(root, f)
        with open(path, encoding='utf-8', errors='ignore') as fh:
            content = fh.read()
        new = content

        for color in opacity_colors:
            new = new.replace('card-header bg-' + color + ' bg-opacity-10 border-bottom', 'card-header bg-white border-bottom')
            new = new.replace('card-header bg-' + color + ' bg-opacity-10', 'card-header bg-white border-bottom')
            new = new.replace('card-header bg-' + color + '-subtle border-bottom', 'card-header bg-white border-bottom')
            new = new.replace('card-header bg-' + color + '-subtle', 'card-header bg-white border-bottom')
            new = re.sub(r'card-header (py-\d) bg-' + color + r' text-(?:white|dark)', r'card-header \1 bg-white border-bottom', new)

        if new != content:
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(new)
            changed.append(os.path.relpath(path, base))

print('Fixed ' + str(len(changed)) + ' more files:')
for fn in sorted(changed):
    print('  ' + fn)
