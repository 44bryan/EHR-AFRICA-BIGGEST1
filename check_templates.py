import django, os, glob
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.base'
django.setup()

from django.template.loader import get_template
from django.template import TemplateSyntaxError

broken = []
ok = 0
for tpl in sorted(glob.glob('templates/**/*.html', recursive=True)):
    # Convert Windows path to template name
    tname = tpl.replace('templates/', '').replace('templates\\', '').lstrip('/')
    tname = tname.replace('\\', '/')
    try:
        get_template(tname)
        ok += 1
    except TemplateSyntaxError as e:
        broken.append((tname, str(e)[:200]))
    except Exception as e:
        pass  # TemplateDoesNotExist etc are not errors

print(f'Templates OK: {ok}  |  Syntax errors: {len(broken)}')
for t, e in broken:
    print(f'\n  BROKEN: {t}')
    print(f'  ERROR:  {e}')
