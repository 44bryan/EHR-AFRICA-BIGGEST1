"""
Transform remaining clinical form fields:
- Add VA combo boxes to retina/glaucoma plain VA inputs
- Add management plan quick-pick buttons to treatment textareas
- Add qfAppend JS to workstation, edit, create templates
"""
import os

BASE = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP'

VA_OPTS = "6/6,6/9,6/12,6/18,6/24,6/36,6/60,CF,HM,PL,NPL"

def va_combo(fid, name, placeholder, val_expr):
    return (
        '<div class="input-group input-group-sm">\n'
        f'            <input type="text" id="{fid}" name="{name}" class="form-control form-control-sm" '
        f'placeholder="{placeholder}" value="{val_expr}">\n'
        '            <button type="button" class="btn btn-outline-secondary dropdown-toggle dropdown-toggle-split px-2" '
        'data-bs-toggle="dropdown" aria-expanded="false"><span class="visually-hidden">Options</span></button>\n'
        '            <ul class="dropdown-menu dropdown-menu-end" style="max-height:200px;overflow-y:auto;font-size:.8rem;">\n'
        f'              {{% for v in "{VA_OPTS}"|split:"," %}}\n'
        '              <li><a class="dropdown-item py-1" href="#" '
        f'onclick="qfAppend(\'{fid}\',\'{{{{ v }}}}\');return false;">{{{{ v }}}}</a></li>\n'
        '              {% endfor %}\n'
        '            </ul>\n'
        '          </div>'
    )

def mgmt_quickpick(tid, name, rows, val_expr, placeholder, opts):
    """Textarea prefixed with a quick-fill dropdown button."""
    return (
        '<div class="d-flex justify-content-end mb-1">\n'
        '            <div class="dropdown">\n'
        '              <button type="button" class="btn btn-sm btn-outline-secondary dropdown-toggle" '
        'data-bs-toggle="dropdown" style="font-size:.75rem;padding:1px 6px;">Quick fill</button>\n'
        '              <ul class="dropdown-menu dropdown-menu-end" style="max-height:240px;overflow-y:auto;font-size:.8rem;">\n'
        f'                {{% for v in "{opts}"|split:"," %}}\n'
        '                <li><a class="dropdown-item py-1" href="#" '
        f'onclick="qfAppend(\'{tid}\',\'{{{{ v }}}}\');return false;">{{{{ v }}}}</a></li>\n'
        '                {% endfor %}\n'
        '              </ul>\n'
        '            </div>\n'
        '          </div>\n'
        f'          <textarea name="{name}" id="{tid}" rows="{rows}" class="form-control form-control-sm" '
        f'placeholder="{placeholder}">{val_expr}</textarea>'
    )

# ─── RETINA: VA + management plan ────────────────────────────────────────────
p = os.path.join(BASE, r'templates\consultations\clinical\_retina_form.html')
with open(p, encoding='utf-8') as f:
    html = f.read()

# VA OD unaided
html = html.replace(
    '<div class="col-md-2"><label class="form-label small">VA OD (unaided)</label>'
    '<input type="text" name="dept_va_od_un" class="form-control form-control-sm" '
    "placeholder=\"6/60\" value=\"{{ d.va_od_un|default:'' }}\"></div>",
    '<div class="col-md-2"><label class="form-label small">VA OD (unaided)</label>\n          '
    + va_combo("ret_va_od_un", "dept_va_od_un", "6/60", "{{ d.va_od_un|default:'' }}")
    + '\n        </div>'
)
# VA OS unaided
html = html.replace(
    '<div class="col-md-2"><label class="form-label small">VA OS (unaided)</label>'
    '<input type="text" name="dept_va_os_un" class="form-control form-control-sm" '
    "placeholder=\"6/60\" value=\"{{ d.va_os_un|default:'' }}\"></div>",
    '<div class="col-md-2"><label class="form-label small">VA OS (unaided)</label>\n          '
    + va_combo("ret_va_os_un", "dept_va_os_un", "6/60", "{{ d.va_os_un|default:'' }}")
    + '\n        </div>'
)
# BCVA OD
html = html.replace(
    '<div class="col-md-2"><label class="form-label small">BCVA OD</label>'
    '<input type="text" name="dept_bcva_od" class="form-control form-control-sm" '
    "placeholder=\"6/6\" value=\"{{ d.bcva_od|default:'' }}\"></div>",
    '<div class="col-md-2"><label class="form-label small">BCVA OD</label>\n          '
    + va_combo("ret_bcva_od", "dept_bcva_od", "6/6", "{{ d.bcva_od|default:'' }}")
    + '\n        </div>'
)
# BCVA OS
html = html.replace(
    '<div class="col-md-2"><label class="form-label small">BCVA OS</label>'
    '<input type="text" name="dept_bcva_os" class="form-control form-control-sm" '
    "placeholder=\"6/6\" value=\"{{ d.bcva_os|default:'' }}\"></div>",
    '<div class="col-md-2"><label class="form-label small">BCVA OS</label>\n          '
    + va_combo("ret_bcva_os", "dept_bcva_os", "6/6", "{{ d.bcva_os|default:'' }}")
    + '\n        </div>'
)

# Management plan textarea
MGMT = (
    "Continue current management,Review in 1 month,Review in 3 months,Review in 6 months,"
    "Anti-VEGF injection given today,Laser photocoagulation performed,"
    "Panretinal photocoagulation (PRP),Refer for vitreoretinal surgery,"
    "Refer to glaucoma clinic,Refer to anterior segment,Patient counselled and discharged,"
    "Urgent referral — same day,Follow-up next available appointment"
)
old_ta = (
    '        <div class="col-md-12"><label class="form-label small">Management Plan &amp; Treatment Notes</label>\n'
    '          <textarea name="dept_treatment_given" class="form-control form-control-sm" rows="3"\n'
    '                    placeholder="e.g. IVT Bevacizumab 1.25mg OD given today. No immediate complications. '
    "Continue loading phase (1 of 3). Review CMT at next visit. Refer for MFC...\">{{ d.treatment_given|default:'' }}</textarea>\n"
    '        </div>'
)
new_ta = (
    '        <div class="col-md-12"><label class="form-label small">Management Plan &amp; Treatment Notes</label>\n          '
    + mgmt_quickpick("ret_mgmt", "dept_treatment_given", "3",
                     "{{ d.treatment_given|default:'' }}",
                     "e.g. IVT Bevacizumab 1.25mg OD given today...", MGMT)
    + '\n        </div>'
)
if old_ta in html:
    html = html.replace(old_ta, new_ta)

with open(p, 'w', encoding='utf-8') as f:
    f.write(html)
print('Retina: done')

# ─── GLAUCOMA: BCVA + Near VA + management plan ───────────────────────────────
p = os.path.join(BASE, r'templates\consultations\clinical\_glaucoma_form.html')
with open(p, encoding='utf-8') as f:
    html = f.read()

html = html.replace(
    '<div class="col-md-3"><label class="form-label small fw-semibold">BCVA OD</label>'
    '<input type="text" name="dept_bcva_od" class="form-control form-control-sm" '
    "placeholder=\"6/6\" value=\"{{ d.bcva_od|default:'' }}\"></div>",
    '<div class="col-md-3"><label class="form-label small fw-semibold">BCVA OD</label>\n          '
    + va_combo("glauc_bcva_od", "dept_bcva_od", "6/6", "{{ d.bcva_od|default:'' }}")
    + '\n        </div>'
)
html = html.replace(
    '<div class="col-md-3"><label class="form-label small fw-semibold">BCVA OS</label>'
    '<input type="text" name="dept_bcva_os" class="form-control form-control-sm" '
    "placeholder=\"6/6\" value=\"{{ d.bcva_os|default:'' }}\"></div>",
    '<div class="col-md-3"><label class="form-label small fw-semibold">BCVA OS</label>\n          '
    + va_combo("glauc_bcva_os", "dept_bcva_os", "6/6", "{{ d.bcva_os|default:'' }}")
    + '\n        </div>'
)
html = html.replace(
    '<div class="col-md-3"><label class="form-label small fw-semibold">Near VA</label>'
    '<input type="text" name="dept_near_va" class="form-control form-control-sm" '
    "placeholder=\"N8 / N18\" value=\"{{ d.near_va|default:'' }}\"></div>",
    '<div class="col-md-3"><label class="form-label small fw-semibold">Near VA</label>\n          '
    + va_combo("glauc_near_va", "dept_near_va", "N8 / N18", "{{ d.near_va|default:'' }}")
    .replace(VA_OPTS, "N5,N6,N8,N10,N12,N14,N18,N24,N36,N48")
    + '\n        </div>'
)

with open(p, 'w', encoding='utf-8') as f:
    f.write(html)
print('Glaucoma: done')

# ─── Update JS in workstation.html, edit.html, create.html ───────────────────
QADD = '''
// qfAppend — used by combo-box dropdowns to append picked value to a text input
function qfAppend(id, val) {
  var inp = document.getElementById(id);
  if (!inp || !val) return;
  inp.value = inp.value.trim() ? inp.value.trim() + '. ' + val : val;
  inp.focus();
}
'''

js_files = [
    r'templates\consultations\workstation.html',
    r'templates\consultations\edit.html',
    r'templates\consultations\create.html',
]

for rel in js_files:
    fp = os.path.join(BASE, rel)
    with open(fp, encoding='utf-8') as f:
        html = f.read()
    if 'function qfAppend' not in html:
        html = html.replace('function qfPick(', QADD + 'function qfPick(', 1)
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f'{rel.split(chr(92))[-1]}: qfAppend added')
    else:
        print(f'{rel.split(chr(92))[-1]}: qfAppend already present')

print('\nAll done!')
