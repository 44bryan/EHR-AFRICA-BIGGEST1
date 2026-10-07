"""
Convert ALL input-group combo boxes back to plain <select> dropdowns
for visual uniformity across the whole system.
"""
import re, os

BASE = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP'

# Match any input-group combo box with dropdown-toggle + qfAppend
PATTERN = re.compile(
    r'<div class="input-group input-group-sm">\s*'
    r'<input\b[^>]*\bname="([^"]+)"[^>]*>\s*'
    r'<button\b[^>]*\bdropdown-toggle\b[^>]*>.*?</button>\s*'
    r'<ul\b[^>]*\bdropdown-menu\b[^>]*>\s*'
    r'\{%-?\s*for v in "([^"]+)"\|split:","\s*-?%\}\s*'
    r'<li>.*?</li>\s*'
    r'\{%-?\s*endfor\s*-?%\}\s*'
    r'</ul>\s*'
    r'</div>',
    re.DOTALL
)

def replacer(m):
    name    = m.group(1)   # e.g. dept_cover_test
    options = m.group(2)   # e.g. Orthophoria,Esophoria,...
    field   = name[5:] if name.startswith('dept_') else name
    return (
        f'<select name="{name}" class="form-select form-select-sm">\n'
        f'  <option value="">—</option>\n'
        f'  {{% for v in "{options}"|split:"," %}}\n'
        f'  <option value="{{{{ v }}}}" {{% if d.{field} == v %}}selected{{% endif %}}>{{{{ v }}}}</option>\n'
        f'  {{% endfor %}}\n'
        f'</select>'
    )

forms = [
    r'templates\consultations\clinical\_gen_oph_form.html',
    r'templates\consultations\clinical\_glaucoma_form.html',
    r'templates\consultations\clinical\_retina_form.html',
    r'templates\consultations\clinical\_cornea_form.html',
    r'templates\consultations\clinical\_cataract_form.html',
    r'templates\consultations\clinical\_neuro_oph_form.html',
    r'templates\consultations\clinical\_oculoplastics_form.html',
    r'templates\consultations\clinical\_low_vision_form.html',
    r'templates\consultations\clinical\_pediatric_form.html',
    r'templates\consultations\clinical\_pediatric_refraction_form.html',
    r'templates\consultations\clinical\_uveitis_form.html',
    r'templates\consultations\clinical\_refraction_form.html',
    r'templates\consultations\clinical\_dispatcher_form.html',
]

total = 0
for rel in forms:
    fp = os.path.join(BASE, rel)
    if not os.path.exists(fp):
        print(f'SKIP (not found): {rel}')
        continue
    with open(fp, encoding='utf-8') as f:
        html = f.read()
    count_before = len(PATTERN.findall(html))
    new_html = PATTERN.sub(replacer, html)
    count_after = len(PATTERN.findall(new_html))
    converted = count_before - count_after
    if converted:
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(new_html)
        print(f'{os.path.basename(fp)}: converted {converted} combo boxes -> selects')
        total += converted
    else:
        print(f'{os.path.basename(fp)}: no combo boxes found')

print(f'\nTotal converted: {total}')
