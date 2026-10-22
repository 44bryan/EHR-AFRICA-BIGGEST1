path = r'c:\Users\GROD\Desktop\EHR AFRICA BACKUP\templates\billing\gl_config_hub.html'
with open(path, encoding='utf-8') as f:
    c = f.read()

# ── SECTION A: Operations ──────────────────────────────────────────────────────
old_a = '            <tbody>\n              {% for op in operations %}\n              <tr class="edit-op-row" data-group="{{ op.group }}">\n                <form method="post">\n                  {% csrf_token %}\n                  <input type="hidden" name="action" value="edit_operation">\n                  <input type="hidden" name="op_id" value="{{ op.pk }}">\n                  <input type="hidden" name="tab_back" value="edit">\n                  <td class="ps-3 fw-bold font-monospace text-primary">{{ op.operation_code }}</td>\n                  <td class="fw-semibold">{{ op.operation_name }}</td>'

new_a = '            <tbody>\n              {% for op in operations %}<form id="opf{{ op.pk }}" method="post">{% csrf_token %}<input type="hidden" name="action" value="edit_operation"><input type="hidden" name="op_id" value="{{ op.pk }}"><input type="hidden" name="tab_back" value="edit"></form>{% endfor %}\n              {% for op in operations %}\n              <tr class="edit-op-row" data-group="{{ op.group }}">\n                  <td class="ps-3 fw-bold font-monospace text-primary">{{ op.operation_code }}</td>\n                  <td class="fw-semibold">{{ op.operation_name }}</td>'

if old_a in c:
    c = c.replace(old_a, new_a, 1)
    print("Section A open: OK")
else:
    print("Section A open: NOT FOUND - skipping")

# Fix the 3 selects + button + close </form></tr> in Section A
for (old_sel, new_sel, label) in [
    ('                    <select name="cost_center" class="form-select form-select-sm">',
     '                    <select name="cost_center" form="opf{{ op.pk }}" class="form-select form-select-sm">',
     'A cost_center'),
    ('                    <select name="default_debit_account" class="form-select form-select-sm">',
     '                    <select name="default_debit_account" form="opf{{ op.pk }}" class="form-select form-select-sm">',
     'A debit'),
    ('                    <select name="default_credit_account" class="form-select form-select-sm">',
     '                    <select name="default_credit_account" form="opf{{ op.pk }}" class="form-select form-select-sm">',
     'A credit'),
]:
    if old_sel in c:
        c = c.replace(old_sel, new_sel, 1)
        print(f"  {label}: OK")
    else:
        print(f"  {label}: NOT FOUND")

old_a_btn = '                  <td>\n                    <button type="submit" class="btn btn-primary btn-sm py-0 px-2" style="font-size:.75rem;">\n                      <i class="bi bi-check-lg"></i> Save\n                    </button>\n                  </td>\n                </form>\n              </tr>\n              {% endfor %}\n            </tbody>\n          </table>\n        </div>\n      </div>\n    </div>\n    <div class="card border-0 shadow-sm mb-4">\n      <div class="card-header bg-white border-bottom py-2 d-flex justify-content-between align-items-center">\n        <span class="fw-semibold small"><i class="bi bi-arrow-left-right text-success me-1"></i>'

new_a_btn = '                  <td>\n                    <button type="submit" form="opf{{ op.pk }}" class="btn btn-primary btn-sm py-0 px-2" style="font-size:.75rem;">\n                      <i class="bi bi-check-lg"></i> Save\n                    </button>\n                  </td>\n              </tr>\n              {% endfor %}\n            </tbody>\n          </table>\n        </div>\n      </div>\n    </div>\n    <div class="card border-0 shadow-sm mb-4">\n      <div class="card-header bg-white border-bottom py-2 d-flex justify-content-between align-items-center">\n        <span class="fw-semibold small"><i class="bi bi-arrow-left-right text-success me-1"></i>'

if old_a_btn in c:
    c = c.replace(old_a_btn, new_a_btn, 1)
    print("Section A button+close: OK")
else:
    print("Section A button+close: NOT FOUND")

# ── SECTION B: Entry/Exit Types ────────────────────────────────────────────────
old_b_open = '              {% for sot in all_sot %}\n              <tr class="edit-sot-row" data-cat="{{ sot.category }}">\n                <form method="post">\n                  {% csrf_token %}\n                  <input type="hidden" name="action" value="edit_entry_exit">\n                  <input type="hidden" name="sot_id" value="{{ sot.pk }}">\n                  <input type="hidden" name="tab_back" value="edit">\n                  <td class="ps-3 fw-bold font-monospace text-success">{{ sot.code }}</td>'

new_b_open = '              {% for sot in all_sot %}<form id="sotf{{ sot.pk }}" method="post">{% csrf_token %}<input type="hidden" name="action" value="edit_entry_exit"><input type="hidden" name="sot_id" value="{{ sot.pk }}"><input type="hidden" name="tab_back" value="edit"></form>{% endfor %}\n              {% for sot in all_sot %}\n              <tr class="edit-sot-row" data-cat="{{ sot.category }}">\n                  <td class="ps-3 fw-bold font-monospace text-success">{{ sot.code }}</td>'

if old_b_open in c:
    c = c.replace(old_b_open, new_b_open, 1)
    print("Section B open: OK")
else:
    print("Section B open: NOT FOUND")

for (old_sel, new_sel, label) in [
    ('                    <select name="billing_operation" class="form-select form-select-sm">',
     '                    <select name="billing_operation" form="sotf{{ sot.pk }}" class="form-select form-select-sm">',
     'B billing_operation'),
    ('                    <select name="debit_account" class="form-select form-select-sm">',
     '                    <select name="debit_account" form="sotf{{ sot.pk }}" class="form-select form-select-sm">',
     'B debit'),
    ('                    <select name="credit_account" class="form-select form-select-sm">',
     '                    <select name="credit_account" form="sotf{{ sot.pk }}" class="form-select form-select-sm">',
     'B credit'),
]:
    if old_sel in c:
        c = c.replace(old_sel, new_sel, 1)
        print(f"  {label}: OK")
    else:
        print(f"  {label}: NOT FOUND")

old_b_btn = '                  <td>\n                    <button type="submit" class="btn btn-success btn-sm py-0 px-2" style="font-size:.75rem;">\n                      <i class="bi bi-check-lg"></i> Save\n                    </button>\n                  </td>\n                </form>\n              </tr>\n              {% endfor %}'

new_b_btn = '                  <td>\n                    <button type="submit" form="sotf{{ sot.pk }}" class="btn btn-success btn-sm py-0 px-2" style="font-size:.75rem;">\n                      <i class="bi bi-check-lg"></i> Save\n                    </button>\n                  </td>\n              </tr>\n              {% endfor %}'

if old_b_btn in c:
    c = c.replace(old_b_btn, new_b_btn, 1)
    print("Section B button+close: OK")
else:
    print("Section B button+close: NOT FOUND")

# ── SECTION C: Item Category GL Routing ───────────────────────────────────────
old_c_open = '              {% for cat_val, cat_label in all_item_cats %}\n              <tr>\n                <form method="post">\n                  {% csrf_token %}\n                  <input type="hidden" name="action" value="edit_item_gl">\n                  <input type="hidden" name="category" value="{{ cat_val }}">\n                  <input type="hidden" name="tab_back" value="edit">\n                  <td class="ps-3 fw-semibold">{{ cat_label }}</td>'

new_c_open = '              {% for cat_val, cat_label in all_item_cats %}<form id="itemglf-{{ cat_val }}" method="post">{% csrf_token %}<input type="hidden" name="action" value="edit_item_gl"><input type="hidden" name="category" value="{{ cat_val }}"><input type="hidden" name="tab_back" value="edit"></form>{% endfor %}\n              {% for cat_val, cat_label in all_item_cats %}\n              <tr>\n                  <td class="ps-3 fw-semibold">{{ cat_label }}</td>'

if old_c_open in c:
    c = c.replace(old_c_open, new_c_open, 1)
    print("Section C open: OK")
else:
    print("Section C open: NOT FOUND")

for (old_sel, new_sel, label) in [
    ('                    <select name="inventory_account" class="form-select form-select-sm">',
     '                    <select name="inventory_account" form="itemglf-{{ cat_val }}" class="form-select form-select-sm">',
     'C inventory'),
    ('                    <select name="cogs_account" class="form-select form-select-sm">',
     '                    <select name="cogs_account" form="itemglf-{{ cat_val }}" class="form-select form-select-sm">',
     'C cogs'),
    ('                    <select name="loss_account" class="form-select form-select-sm">',
     '                    <select name="loss_account" form="itemglf-{{ cat_val }}" class="form-select form-select-sm">',
     'C loss'),
]:
    if old_sel in c:
        c = c.replace(old_sel, new_sel, 1)
        print(f"  {label}: OK")
    else:
        print(f"  {label}: NOT FOUND")

old_c_btn = '                  <td>\n                    <button type="submit" class="btn btn-info btn-sm py-0 px-2" style="font-size:.75rem;">\n                      <i class="bi bi-check-lg"></i> Save\n                    </button>\n                  </td>\n                </form>\n              </tr>\n              {% endfor %}'

new_c_btn = '                  <td>\n                    <button type="submit" form="itemglf-{{ cat_val }}" class="btn btn-info btn-sm py-0 px-2" style="font-size:.75rem;">\n                      <i class="bi bi-check-lg"></i> Save\n                    </button>\n                  </td>\n              </tr>\n              {% endfor %}'

if old_c_btn in c:
    c = c.replace(old_c_btn, new_c_btn, 1)
    print("Section C button: OK")
else:
    print("Section C button: NOT FOUND")

# ── SECTION D: System GL Accounts ─────────────────────────────────────────────
old_d_open = '                {% for m in mgrp.list %}\n                <tr>\n                  {% if can_edit %}\n                  <form method="post">\n                    {% csrf_token %}\n                    <input type="hidden" name="action" value="edit_gl_mapping">\n                    <input type="hidden" name="mapping_id" value="{{ m.pk }}">\n                    <input type="hidden" name="tab_back" value="system">\n                    <td class="ps-3 font-monospace fw-semibold text-primary" style="font-size:.78rem;">{{ m.source_key }}</td>'

new_d_open = '                {% if can_edit %}{% for m in mgrp.list %}<form id="glmapf{{ m.pk }}" method="post">{% csrf_token %}<input type="hidden" name="action" value="edit_gl_mapping"><input type="hidden" name="mapping_id" value="{{ m.pk }}"><input type="hidden" name="tab_back" value="system"></form>{% endfor %}{% endif %}\n                {% for m in mgrp.list %}\n                <tr>\n                  {% if can_edit %}\n                    <td class="ps-3 font-monospace fw-semibold text-primary" style="font-size:.78rem;">{{ m.source_key }}</td>'

if old_d_open in c:
    c = c.replace(old_d_open, new_d_open, 1)
    print("Section D open: OK")
else:
    print("Section D open: NOT FOUND")

old_d_sel = '                      <select name="gl_account" class="form-select form-select-sm">'
new_d_sel = '                      <select name="gl_account" form="glmapf{{ m.pk }}" class="form-select form-select-sm">'
if old_d_sel in c:
    c = c.replace(old_d_sel, new_d_sel, 1)
    print("  D gl_account: OK")
else:
    print("  D gl_account: NOT FOUND")

old_d_btn = '                    <td>\n                      <button type="submit" class="btn btn-primary btn-sm py-0 px-2" style="font-size:.75rem;">\n                        <i class="bi bi-check-lg"></i>\n                      </button>\n                    </td>\n                  </form>\n                  {% else %}'

new_d_btn = '                    <td>\n                      <button type="submit" form="glmapf{{ m.pk }}" class="btn btn-primary btn-sm py-0 px-2" style="font-size:.75rem;">\n                        <i class="bi bi-check-lg"></i>\n                      </button>\n                    </td>\n                  {% else %}'

if old_d_btn in c:
    c = c.replace(old_d_btn, new_d_btn, 1)
    print("Section D button: OK")
else:
    print("Section D button: NOT FOUND")

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
print("\nDone. Lines:", c.count('\n'))
