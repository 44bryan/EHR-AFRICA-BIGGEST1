"""
Convert ALL remaining pure <select name="dept_xxx"> fields in clinical forms
to the unified input-group combo box pattern for visual consistency.
"""
import re, os

BASE = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP'

# Matches: <select name="dept_FIELD" class="form-select form-select-sm...">
#   <option value="">anything</option>
#   {% for VAR in "OPT1,OPT2"|split:"," %}
#   <option value="{{ VAR }}" {% if ... %}selected{% endif %}>{{ VAR }}</option>
#   {% endfor %}
# </select>
PATTERN = re.compile(
    r'<select\s+name="(dept_[^"]+)"\s+class="form-select form-select-sm[^"]*">\s*'
    r'<option\s+value="">[^<]*</option>\s*'
    r'\{%[-\s]*for\s+(\w+)\s+in\s+"([^"]+)"\|split:","\s*[-\s]*%\}\s*'
    r'(?:\s*<option\s[^>]*>\{\{\s*\2\s*\}\}</option>\s*)*'
    r'\{%[-\s]*endfor\s*[-\s]*%\}\s*'
    r'</select>',
    re.DOTALL
)

def field_name(dept_name):
    """dept_cover_test → cover_test"""
    return dept_name[5:] if dept_name.startswith('dept_') else dept_name

def replacer(m):
    name    = m.group(1)          # e.g. dept_cover_test
    options = m.group(3)          # e.g. "Orthophoria,Esophoria,..."
    field   = field_name(name)    # e.g. cover_test
    return (
        '<div class="input-group input-group-sm">\n'
        f'  <input type="text" id="{name}" name="{name}" class="form-control form-control-sm" '
        f"value=\"{{{{ d.{field}|default:'' }}}}\" placeholder=\"\">\n"
        '  <button type="button" class="btn btn-outline-secondary dropdown-toggle dropdown-toggle-split px-2" '
        'data-bs-toggle="dropdown" aria-expanded="false"><span class="visually-hidden">Options</span></button>\n'
        '  <ul class="dropdown-menu dropdown-menu-end" style="max-height:220px;overflow-y:auto;font-size:.8rem;">\n'
        f'    {{% for v in "{options}"|split:"," %}}\n'
        "    <li><a class=\"dropdown-item py-1\" href=\"#\" "
        f"onclick=\"qfAppend('{name}','{{{{ v }}}}');return false;\">{{{{ v }}}}</a></li>\n"
        '    {% endfor %}\n'
        '  </ul>\n'
        '</div>'
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
    orig_count = len(PATTERN.findall(html))
    new_html = PATTERN.sub(replacer, html)
    replaced = orig_count - len(PATTERN.findall(new_html))
    if replaced:
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(new_html)
        print(f'{os.path.basename(fp)}: converted {replaced} selects')
        total += replaced
    else:
        print(f'{os.path.basename(fp)}: no remaining selects')

print(f'\nTotal converted: {total}')
