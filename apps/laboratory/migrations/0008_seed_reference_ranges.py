"""
Data migration: seed reference ranges and techniques from the
BIOCHEMISTRY LAB turbo.docx document into LabTestType.normal_range and .method.

Only updates rows where the field is currently empty — never overwrites
manually entered data.
"""
from django.db import migrations


# ── Data extracted from "BIOCHEMISTRY LAB turbo.docx" ──────────────────────
# Format: (test_name, normal_range_json, method_string)
#   normal_range_json uses gender-keyed dicts where the doc specifies adult male/female;
#   otherwise a single "default" key is used.

BIOCHEMISTRY = [
    ('Glucose F',       {'default': {'min': 70, 'max': 110, 'unit': 'mg/dl'}},         'Enzymatic colorimetric / One Touch Ultra'),
    ('Glucose pp',      {'default': {'min': 70, 'max': 140, 'unit': 'mg/dl'}},         'Enzymatic colorimetric / One Touch Ultra'),
    ('Urea',            {'default': {'min': 10.0, 'max': 50.0, 'unit': 'mg/dl'}},      'Enzymatic colorimetric'),
    ('Creatinine',      {'default': {'min': 0.6, 'max': 1.2, 'unit': 'mg/dl'}},        'Photometric Colorimetric'),
    ('Sodium',          {'default': {'min': 135, 'max': 155, 'unit': 'mmol/l'}},        'Enzymatic colorimetric'),
    ('Potassium',       {'default': {'min': 3.5, 'max': 5.5, 'unit': 'mmol/l'}},       'Enzymatic colorimetric'),
    ('Chlore',          {'default': {'min': 95, 'max': 115, 'unit': 'mmol/l'}},         'Enzymatic colorimetric'),
    ('Cholesterol Total', {'default': {'min': 0, 'max': 200, 'unit': 'mg/dl'}},        'Enzymatic colorimetric'),
    ('Triglycerides',   {'default': {'min': 0, 'max': 150, 'unit': 'mg/dl'}},          'Enzymatic colorimetric'),
    ('HDL Cholesterol', {'default': {'min': 35, 'max': 55, 'unit': 'mg/dl'}},          'Enzymatic colorimetric'),
    ('LDL Cholesterol', {'default': {'min': 0, 'max': 100, 'unit': 'mg/dl'}},          'Enzymatic colorimetric'),
]

HAEMATOLOGY_MALE = [
    ('Red blood cells',  {'male': {'min': 4500000, 'max': 5500000, 'unit': '/\u00b5L'}, 'female': {'min': 4000000, 'max': 5000000, 'unit': '/\u00b5L'}, 'child': {'min': 3900000, 'max': 5300000, 'unit': '/\u00b5L'}}, 'HUMACOUNT 30'),
    ('White blood cells', {'male': {'min': 5000, 'max': 10000, 'unit': '/\u00b5L'}, 'female': {'min': 5000, 'max': 10000, 'unit': '/\u00b5L'}, 'child': {'min': 5000, 'max': 19000, 'unit': '/\u00b5L'}}, 'HUMACOUNT 30'),
    ('Haemoglobin',      {'male': {'min': 14.0, 'max': 17.4, 'unit': 'g/dL'}, 'female': {'min': 12.0, 'max': 16.0, 'unit': 'g/dL'}, 'child': {'min': 9.5, 'max': 14.1, 'unit': 'g/dL'}}, 'HUMACOUNT 30'),
    ('Haematocrit',      {'male': {'min': 45.0, 'max': 52.0, 'unit': '%'}, 'female': {'min': 36.0, 'max': 48.0, 'unit': '%'}, 'child': {'min': 30.0, 'max': 40.0, 'unit': '%'}}, 'HUMACOUNT 30'),
    ('MCV',              {'male': {'min': 84, 'max': 96, 'unit': 'fL'}, 'female': {'min': 76, 'max': 96, 'unit': 'fL'}, 'child': {'min': 70, 'max': 84, 'unit': 'fL'}}, 'HUMACOUNT 30'),
    ('MCH',              {'male': {'min': 27.0, 'max': 32.0, 'unit': 'pg'}, 'female': {'min': 27.0, 'max': 32.0, 'unit': 'pg'}, 'child': {'min': 23.0, 'max': 29.0, 'unit': 'pg'}}, 'HUMACOUNT 30'),
    ('MCHC',             {'male': {'min': 30.0, 'max': 35.0, 'unit': 'g/dL'}, 'female': {'min': 30.0, 'max': 35.0, 'unit': 'g/dL'}, 'child': {'min': 31.0, 'max': 35.0, 'unit': 'g/dL'}}, 'HUMACOUNT 30'),
    ('Platelets',        {'male': {'min': 150000, 'max': 400000, 'unit': '/\u00b5L'}, 'female': {'min': 150000, 'max': 400000, 'unit': '/\u00b5L'}, 'child': {'min': 150000, 'max': 450000, 'unit': '/\u00b5L'}}, 'HUMACOUNT 30'),
    ('Neutrophils',      {'male': {'min': 50.0, 'max': 75.0, 'unit': '%'}, 'female': {'min': 50.0, 'max': 75.0, 'unit': '%'}, 'child': {'min': 20.0, 'max': 45.0, 'unit': '%'}}, 'HUMACOUNT 30'),
    ('Eosinophils',      {'default': {'min': 0.0, 'max': 4.0, 'unit': '%'}}, 'HUMACOUNT 30'),
    ('Basophils',        {'default': {'min': 0, 'max': 1, 'unit': '%'}}, 'HUMACOUNT 30'),
    ('Lymphocytes',      {'male': {'min': 25.0, 'max': 40.0, 'unit': '%'}, 'female': {'min': 25.0, 'max': 40.0, 'unit': '%'}, 'child': {'min': 46.0, 'max': 76.0, 'unit': '%'}}, 'HUMACOUNT 30'),
    ('Monocytes',        {'male': {'min': 3.0, 'max': 7.0, 'unit': '%'}, 'female': {'min': 3.0, 'max': 7.0, 'unit': '%'}, 'child': {'min': 0.0, 'max': 5.0, 'unit': '%'}}, 'HUMACOUNT 30'),
]

COAGULATION = [
    ('PT (TP)',   {'default': {'min': 12.6, 'max': 18, 'unit': 'Seconds'}}, 'Hemostat Thromboplastine'),
    ('aPTT (TCA)', {'default': {'min': 25, 'max': 42, 'unit': 'Seconds'}}, 'Hemostat'),
]

PARASITOLOGY = [
    ('Malaria Parasite',    {}, 'Microscopy / Thick blood film'),
    ('Malaria Parasite MP', {}, 'Malaria Pf/Pv Ag Rapid Test'),
]

SEROLOGY = [
    ('ASLO',            {}, 'Latex agglutination'),
    ('CRP',             {}, 'Latex agglutination'),
    ('Rheumatoid fact', {}, 'Latex agglutination'),
    ('H. Pylori',       {}, 'Immunochromatography Assay'),
    ('Hepatitis B. HBsAg', {}, 'Immunochromatography Assay'),
    ('Hepatitis C. HCV',   {}, 'Immunochromatography Assay'),
    ('HIV 1/2 Abs',     {}, 'Determine Abbott / Hexagon'),
]

URINALYSIS = [
    ('Urobilinogen',    {'default': {'min': 1.7, 'max': 30, 'unit': 'umol/l'}},   'Dipstick'),
    ('Bilirubin',       {'default': {'min': 0, 'max': 0, 'unit': 'umol/l'}},      'Dipstick'),
    ('Ketones',         {'default': {'min': 0, 'max': 0, 'unit': 'mmol/l'}},      'Dipstick'),
    ('Creatinine (Urine)', {'default': {'min': 0.9, 'max': 26.5, 'unit': 'mmol/l'}}, 'Dipstick'),
    ('Blood (Urine)',   {'default': {'min': 0, 'max': 0, 'unit': 'GR/ul'}},       'Dipstick'),
    ('Protein (Urine)', {'default': {'min': 0, 'max': 0, 'unit': 'mg/dl'}},       'Dipstick'),
    ('Microalbumin',    {'default': {'min': 0, 'max': 20, 'unit': 'mg/l'}},       'Dipstick'),
    ('Nitrite',         {'default': {'min': 0, 'max': 0, 'unit': 'mg/dl'}},       'Dipstick'),
    ('Leucocytes (Urine)', {'default': {'min': 0, 'max': 0, 'unit': 'Leu/ul'}},  'Dipstick'),
    ('Glucose (Urine)', {'default': {'min': 0, 'max': 2.8, 'unit': 'mmol/l'}},   'Dipstick'),
    ('Specific Gravity', {'default': {'min': 1.015, 'max': 1.025, 'unit': ''}},   'Dipstick'),
    ('pH (Urine)',      {'default': {'min': 5.0, 'max': 6.0, 'unit': ''}},        'Dipstick'),
    ('Ascorbic Acid',   {'default': {'min': 0, 'max': 0, 'unit': 'mmol/l'}},      'Dipstick'),
]

ALL_TESTS = BIOCHEMISTRY + HAEMATOLOGY_MALE + COAGULATION + PARASITOLOGY + SEROLOGY + URINALYSIS


def seed_ranges(apps, schema_editor):
    LabTestType = apps.get_model('laboratory', 'LabTestType')
    updated = 0
    not_found = []
    for name, normal_range, method in ALL_TESTS:
        # Try exact match first, then case-insensitive contains
        tt = LabTestType.objects.filter(name__iexact=name).first()
        if not tt:
            tt = LabTestType.objects.filter(name__icontains=name).first()
        if not tt:
            # Try shorter name (e.g. "Platele" in DB for "Platelets")
            short = name[:6]
            tt = LabTestType.objects.filter(name__istartswith=short).first()
        if not tt:
            not_found.append(name)
            continue

        changed = False
        if normal_range and not tt.normal_range:
            tt.normal_range = normal_range
            changed = True
        if method and not tt.method:
            tt.method = method
            changed = True
        if changed:
            tt.save(update_fields=['normal_range', 'method'])
            updated += 1

    if updated:
        print(f'  Updated {updated} LabTestType entries with reference ranges and techniques.')
    if not_found:
        print(f'  Not found in DB (create manually if needed): {not_found}')


class Migration(migrations.Migration):
    dependencies = [
        ('laboratory', '0007_alter_laborder_options_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_ranges, migrations.RunPython.noop),
    ]
