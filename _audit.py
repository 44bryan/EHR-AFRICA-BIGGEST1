"""Full system audit — Run: python _audit.py"""
import django, os, re, glob, importlib
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.base'
django.setup()

from django.urls import get_resolver
from django.template.loader import get_template
from django.template import TemplateSyntaxError
from django.urls.resolvers import URLPattern, URLResolver

BUGS = []
WARNS = []
def bug(cat, msg): BUGS.append(f'[{cat}] {msg}')
def warn(cat, msg): WARNS.append(f'[{cat}] {msg}')

# ── Collect ALL registered URL names (walk url_patterns tree) ─────────────────
def collect_all_names(resolver, namespace=''):
    names = set()
    for p in resolver.url_patterns:
        if isinstance(p, URLPattern):
            if p.name:
                full = f'{namespace}:{p.name}' if namespace else p.name
                names.add(full)
        elif isinstance(p, URLResolver):
            ns = p.namespace or ''
            child_ns = f'{namespace}:{ns}' if namespace and ns else (ns or namespace)
            names |= collect_all_names(p, child_ns)
    return names

print('Building URL name index...')
ALL_URL_NAMES = collect_all_names(get_resolver())
print(f'   {len(ALL_URL_NAMES)} URL names registered')

# ── 1. Template syntax ────────────────────────────────────────────────────────
print('1. Checking template syntax...')
ok = 0
for tpl in sorted(glob.glob('templates/**/*.html', recursive=True)):
    tname = tpl.replace('\\','/').replace('templates/','',1)
    try:
        get_template(tname); ok += 1
    except TemplateSyntaxError as e:
        bug('TEMPLATE_SYNTAX', f'{tname}: {str(e)[:100]}')
    except Exception:
        pass
print(f'   {ok} templates OK')

# ── 2. URL names in templates ─────────────────────────────────────────────────
print('2. Checking template URL tags...')
url_ok = url_bad = 0
checked = set()
for tpl in sorted(glob.glob('templates/**/*.html', recursive=True)):
    with open(tpl, encoding='utf-8', errors='ignore') as f:
        content = f.read()
    for name in re.findall(r"""\{%-?\s*url\s+['"]([\w:]+)['"]""", content):
        if name in checked: continue
        checked.add(name)
        if name in ALL_URL_NAMES:
            url_ok += 1
        else:
            bug('BROKEN_URL_TAG', f"{{% url '{name}' %}} not registered")
            url_bad += 1
print(f'   {url_ok} OK, {url_bad} broken')

# ── 3. Views in urls.py that don't exist ─────────────────────────────────────
print('3. Checking view references in urls.py files...')
v_ok = v_bad = 0
for app_path in sorted(glob.glob('apps/*/urls.py')):
    app = app_path.replace('\\','/').split('/')[1]
    with open(app_path, encoding='utf-8', errors='ignore') as f:
        content = f.read()
    refs = re.findall(r'views\.(\w+)', content)
    try:
        vmod = importlib.import_module(f'apps.{app}.views')
        for ref in set(refs):
            if hasattr(vmod, ref): v_ok += 1
            else:
                bug('MISSING_VIEW', f'apps/{app}/urls.py -> views.{ref} missing')
                v_bad += 1
    except ImportError as e:
        warn('IMPORT', f'apps.{app}.views: {e}')
print(f'   {v_ok} OK, {v_bad} broken')

# ── 4. Apps with urls.py not in main router ───────────────────────────────────
print('4. Checking app router wiring...')
with open('ehr_project/urls.py', encoding='utf-8', errors='ignore') as f:
    main = f.read()
for app_path in sorted(glob.glob('apps/*/urls.py')):
    app = app_path.replace('\\','/').split('/')[1]
    if app not in main and f'apps.{app}' not in main:
        warn('UNWIRED_APP', f'apps/{app}/urls.py not in main urls.py')
print('   Done')

# ── 5. FK integrity ───────────────────────────────────────────────────────────
print('5. Checking FK integrity...')
from django.apps import apps as dapps
fk_ok = fk_bad = 0
for cfg in dapps.get_app_configs():
    if not cfg.name.startswith('apps.'): continue
    for model in cfg.get_models():
        for field in model._meta.get_fields():
            if hasattr(field, 'related_model') and field.related_model is not None:
                try:
                    _ = field.related_model._meta.db_table; fk_ok += 1
                except Exception as e:
                    bug('FK_INTEGRITY', f'{model.__name__}.{field.name}: {e}'); fk_bad += 1
print(f'   {fk_ok} OK, {fk_bad} broken')

# ── 6. DB tables ──────────────────────────────────────────────────────────────
print('6. Checking DB tables...')
from django.db import connection
with connection.cursor() as c:
    c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    db_tables = {r[0] for r in c.fetchall()}
t_ok = t_bad = 0
for cfg in dapps.get_app_configs():
    if not cfg.name.startswith('apps.'): continue
    for model in cfg.get_models():
        tbl = model._meta.db_table
        if tbl in db_tables: t_ok += 1
        else: bug('MISSING_TABLE', f'{model.__name__} -> {tbl}'); t_bad += 1
print(f'   {t_ok} OK, {t_bad} missing')

# ── 7. Pending migrations ─────────────────────────────────────────────────────
print('7. Checking migrations...')
from django.db.migrations.executor import MigrationExecutor
executor = MigrationExecutor(connection)
plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
if plan:
    for mig, _ in plan: bug('PENDING_MIGRATION', str(mig))
else:
    print('   All applied')

# ── 8. render() template references ─────────────────────────────────────────
print('8. Checking render() template references...')
r_ok = r_bad = 0
seen = set()
for vpath in sorted(glob.glob('apps/*/views.py')):
    with open(vpath, encoding='utf-8', errors='ignore') as f:
        content = f.read()
    for t in re.findall(r"""render\s*\(\s*request\s*,\s*['\"]([\w/._-]+\.html)['\"]""", content):
        if t in seen: continue
        seen.add(t)
        try:
            get_template(t); r_ok += 1
        except Exception:
            bug('MISSING_RENDER_TPL', f'{vpath} -> {t}'); r_bad += 1
print(f'   {r_ok} OK, {r_bad} missing')

# ── 9. Redirect URL names in views ───────────────────────────────────────────
print('9. Checking reverse() calls in views...')
from django.urls import reverse, NoReverseMatch
rev_ok = rev_bad = 0
rev_seen = set()
for vpath in sorted(glob.glob('apps/*/views.py')):
    with open(vpath, encoding='utf-8', errors='ignore') as f:
        content = f.read()
    for name in re.findall(r"""reverse\s*\(\s*['"]([\w:]+)['"]""", content):
        if name in rev_seen: continue
        rev_seen.add(name)
        if name in ALL_URL_NAMES: rev_ok += 1
        else:
            bug('BROKEN_REVERSE', f'{vpath}: reverse("{name}") — name not registered')
            rev_bad += 1
print(f'   {rev_ok} OK, {rev_bad} broken')

# ── Summary ───────────────────────────────────────────────────────────────────
print()
print('=' * 70)
print(f'BUGS FOUND: {len(BUGS)}')
cats = {}
for b in BUGS:
    cat = b.split(']')[0][1:]
    cats.setdefault(cat, []).append(b)
for cat, items in sorted(cats.items()):
    print(f'\n  [{cat}] — {len(items)} issues:')
    for i in items[:20]:
        print(f'    {i[len(cat)+3:]}')
    if len(items) > 20:
        print(f'    ... and {len(items)-20} more')

print()
print(f'WARNINGS: {len(WARNS)}')
for w in WARNS[:30]:
    print(f'  {w}')
print('=' * 70)
