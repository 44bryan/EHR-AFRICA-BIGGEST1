"""
Seed InvestigationType catalog with proper optometry, orthoptics, and refraction exam types.
Also fixes miscategorized existing types.
Run: python seed_optometry_types.py
"""
import django, os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.production'
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from apps.investigations.models import InvestigationType

# ── Fix miscategorized existing types ──
fixes = {
    'RET': {'category': 'REFRACTION', 'name': 'Retinoscopy'},
    'COVER': {'category': 'ORTHOPTICS', 'name': 'Cover / Prism Cover Test'},
}
for code, updates in fixes.items():
    fixed = InvestigationType.objects.filter(code=code).update(**updates)
    if fixed:
        print(f'  Fixed: {code} → category={updates["category"]}')

# ── Optometry / Refraction exams ──
refraction_types = [
    ('AUTOREF', 'Autorefraction', 'REFRACTION', {
        'fields': ['sph_od', 'cyl_od', 'axis_od', 'sph_os', 'cyl_os', 'axis_os', 'pd'],
        'notes': 'Automated objective refraction measurement'
    }),
    ('SUBJ-REF', 'Subjective Refraction', 'REFRACTION', {
        'fields': ['best_va_od', 'best_va_os', 'sph_od', 'cyl_od', 'axis_od', 'add_od',
                    'sph_os', 'cyl_os', 'axis_os', 'add_os', 'pd_dist', 'pd_near'],
        'notes': 'Manual phoropter/trial lens refraction'
    }),
    ('CYCLO-REF', 'Cycloplegic Refraction', 'REFRACTION', {
        'fields': ['cycloplegic_agent', 'instillation_time', 'sph_od', 'cyl_od', 'axis_od',
                    'sph_os', 'cyl_os', 'axis_os'],
        'notes': 'Refraction under cycloplegia (children/latent hyperopia)'
    }),
    ('CL-ASSESS', 'Contact Lens Assessment', 'REFRACTION', {
        'fields': ['cl_type', 'base_curve', 'diameter', 'power_od', 'power_os',
                    'over_refraction_od', 'over_refraction_os', 'fit_assessment'],
        'notes': 'Contact lens fitting and evaluation'
    }),
    ('DRY-REF', 'Dry (Manifest) Refraction', 'REFRACTION', {
        'fields': ['sph_od', 'cyl_od', 'axis_od', 'sph_os', 'cyl_os', 'axis_os',
                    'best_va_od', 'best_va_os'],
        'notes': 'Non-cycloplegic manifest refraction'
    }),
    ('LENSOMETRY', 'Lensometry (Current Rx)', 'REFRACTION', {
        'fields': ['current_sph_od', 'current_cyl_od', 'current_axis_od', 'current_add_od',
                    'current_sph_os', 'current_cyl_os', 'current_axis_os', 'current_add_os'],
        'notes': 'Reading current spectacle prescription with lensometer'
    }),
]

# ── Orthoptics exams ──
orthoptics_types = [
    ('NPC', 'Near Point of Convergence (NPC)', 'ORTHOPTICS', {
        'fields': ['break_point_cm', 'recovery_point_cm', 'method'],
        'notes': 'Measure convergence amplitude'
    }),
    ('NPA', 'Near Point of Accommodation (NPA)', 'ORTHOPTICS', {
        'fields': ['npa_od_cm', 'npa_os_cm', 'npa_ou_cm', 'method'],
        'notes': 'Measure accommodation amplitude'
    }),
    ('STEREO', 'Stereopsis Test', 'ORTHOPTICS', {
        'fields': ['test_used', 'stereo_seconds_arc', 'result'],
        'notes': 'Titmus/Randot/Lang stereopsis assessment'
    }),
    ('WORTH4', 'Worth Four Dot Test', 'ORTHOPTICS', {
        'fields': ['distance_result', 'near_result', 'interpretation'],
        'notes': 'Assess fusion/suppression'
    }),
    ('BAGOLINI', 'Bagolini Striated Lenses', 'ORTHOPTICS', {
        'fields': ['result', 'interpretation'],
        'notes': 'Assess binocular single vision'
    }),
    ('MADDOX', 'Maddox Rod Test', 'ORTHOPTICS', {
        'fields': ['horizontal_phoria', 'vertical_phoria', 'distance', 'near'],
        'notes': 'Measure phorias'
    }),
    ('PRISM-BAR', 'Prism Bar Assessment', 'ORTHOPTICS', {
        'fields': ['base_out_break', 'base_out_recovery', 'base_in_break', 'base_in_recovery',
                    'vertical_break', 'vertical_recovery'],
        'notes': 'Measure fusional vergence ranges'
    }),
    ('HESS', 'Hess Chart', 'ORTHOPTICS', {
        'fields': ['chart_data', 'interpretation'],
        'notes': 'Hess screen test for EOM restriction/paresis'
    }),
    ('MOTILITY', 'Ocular Motility Assessment', 'ORTHOPTICS', {
        'fields': ['versions', 'ductions', 'saccades', 'pursuits', 'convergence',
                    'nystagmus', 'head_posture'],
        'notes': 'Full extraocular muscle assessment'
    }),
    ('RAF-RULE', 'RAF Rule Test', 'ORTHOPTICS', {
        'fields': ['npc_cm', 'npa_od_cm', 'npa_os_cm', 'npa_ou_cm'],
        'notes': 'Royal Air Force near-point rule'
    }),
    ('PRISM-COVER', 'Prism Cover Test', 'ORTHOPTICS', {
        'fields': ['distance_horizontal', 'distance_vertical', 'near_horizontal',
                    'near_vertical', 'with_correction', 'without_correction'],
        'notes': 'Measure angle of deviation'
    }),
    ('SYNOPT', 'Synoptophore Assessment', 'ORTHOPTICS', {
        'fields': ['simultaneous_perception', 'fusion', 'stereopsis',
                    'angle_h', 'angle_v', 'torsion'],
        'notes': 'Major amblyoscope / synoptophore full assessment'
    }),
]

all_types = refraction_types + orthoptics_types
created = 0
updated = 0

for code, name, category, template in all_types:
    obj, is_new = InvestigationType.objects.get_or_create(
        code=code,
        defaults={
            'name': name,
            'category': category,
            'is_active': True,
            'result_template': template,
            'laterality_required': True,
            'typical_duration_minutes': 15,
        }
    )
    if is_new:
        created += 1
        print(f'  Created: {code} — {name} [{category}]')
    else:
        # Update result_template if empty
        changed = False
        if not obj.result_template:
            obj.result_template = template
            changed = True
        if obj.category != category:
            obj.category = category
            changed = True
        if changed:
            obj.save()
            updated += 1
            print(f'  Updated: {code} — {name} [{category}]')

print(f'\nDone. {created} new, {updated} updated.')
print(f'Total active types: {InvestigationType.objects.filter(is_active=True).count()}')
print(f'  REFRACTION: {InvestigationType.objects.filter(category="REFRACTION", is_active=True).count()}')
print(f'  ORTHOPTICS: {InvestigationType.objects.filter(category="ORTHOPTICS", is_active=True).count()}')
