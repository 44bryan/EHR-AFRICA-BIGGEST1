import django, os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'ehr_project.settings.production'
django.setup()
from apps.investigations.models import InvestigationType

eye_types = [
  ('VA','Visual Acuity','REFRACTION'),
  ('REF','Refraction / Auto-refraction','REFRACTION'),
  ('COL','Colour Vision Test','REFRACTION'),
  ('IOP-NCT','IOP Non-Contact Tonometry (NCT)','TONOMETRY'),
  ('IOP-GAT','IOP Goldman Applanation Tonometry (GAT)','TONOMETRY'),
  ('SCHTZ','Schiotz Tonometry','TONOMETRY'),
  ('FUND','Fundus Photography','IMAGING'),
  ('FFA','Fluorescein Angiography','IMAGING'),
  ('BSCAN','B-Scan Ultrasound','IMAGING'),
  ('ASCAN','A-Scan Biometry','IMAGING'),
  ('SLAMP','Slit Lamp Examination','IMAGING'),
  ('PENTA','Pentacam / Corneal Topography','IMAGING'),
  ('OCT','OCT Optical Coherence Tomography','IMAGING'),
  ('OCT-A','OCT Angiography','IMAGING'),
  ('VF-HVF','Humphrey Visual Field (HVF)','VISUAL_FIELD'),
  ('VF-FDT','FDT Perimetry','VISUAL_FIELD'),
  ('VF-GOLD','Goldmann Perimetry','VISUAL_FIELD'),
  ('BIOT','Biometry / IOL Calculation','BIOMETRY'),
  ('ENDO','Specular Microscopy (Endothelial Cell Count)','BIOMETRY'),
  ('PACH','Corneal Pachymetry (CCT)','PACHYMETRY'),
  ('ERG','Electroretinography (ERG)','ELECTROPHYSIOLOGY'),
  ('VEP','Visual Evoked Potential (VEP)','ELECTROPHYSIOLOGY'),
  ('EOG','Electro-Oculogram (EOG)','ELECTROPHYSIOLOGY'),
  ('GCT','Gonioscopy','ANT_SEG'),
  ('KERATO','Keratometry','ANT_SEG'),
  ('RET','Retinoscopy','ANT_SEG'),
  ('AMSLER','Amsler Grid Test','OTHER'),
  ('COVER','Cover / Prism Cover Test','OTHER'),
]

created = 0
for code, name, cat in eye_types:
    obj, is_new = InvestigationType.objects.get_or_create(
        code=code, defaults={'name': name, 'category': cat, 'is_active': True})
    if is_new:
        created += 1
        sys.stdout.write('  Created: ' + code + ' — ' + name + '\n')

sys.stdout.write('Done. ' + str(created) + ' new. Total: ' + str(InvestigationType.objects.count()) + '\n')
