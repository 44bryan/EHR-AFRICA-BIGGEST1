import sys

path = r"c:\Users\GROD\Desktop\EHR AFRICA BACKUP\templates\consultations\edit.html"
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find start: the row g-3 div inside bodyHistory
start_marker = '      <div id="bodyHistory" class="card-body">\n        <div class="row g-3">'
# End marker: closing tags after social history
end_marker = '        </div>\n      </div>\n    </div>\n  </div>\n  {% endif %}{# /GEN_PHYS Section 1 hide #}'

si = content.find(start_marker)
ei = content.find(end_marker)
print(f"Start={si}, End={ei}")
if si < 0 or ei < 0:
    sys.exit("Markers not found")

def h(label):
    return f'<li><span class="dropdown-header px-3 py-1 fw-semibold" style="font-size:.72rem;color:#6b7280;">{label}</span></li>\n                '

def items(*texts):
    return ''.join(f'<li><button type="button" class="dropdown-item">{t}</button></li>' for t in texts) + '\n                '

oph = '"GEN_OPH" or dept_code == "RETINA" or dept_code == "GLAUC" or dept_code == "GLAUCOMA" or dept_code == "UVEITIS" or dept_code == "CATARACT" or dept_code == "CORNEA" or dept_code == "OCULOPLASTY" or dept_code == "NEURO_OPH" or dept_code == "LOW_VIS"'
ref = '"REFRAC" or dept_code == "PEDS_REFRAC" or dept_code == "ORTHO" or dept_code == "PEDS" or dept_code == "PEDS_OPH"'
doph = '"GEN_OPH" or dept_code == "GLAUC" or dept_code == "GLAUCOMA" or dept_code == "RETINA" or dept_code == "UVEITIS" or dept_code == "CATARACT" or dept_code == "CORNEA" or dept_code == "OCULOPLASTY" or dept_code == "NEURO_OPH" or dept_code == "LOW_VIS"'

cc_oph = (
    h("Vision") +
    items("Blurred vision","Reduced vision","Sudden loss of vision","Gradual loss of vision","Partial loss of vision",
          "Distorted vision (metamorphopsia)","Central scotoma","Peripheral vision loss","Night blindness (nyctalopia)",
          "Poor vision in dim light","Double vision (diplopia)","Hazy / foggy vision","Curtain / shadow over vision","Colour vision problem") +
    h("Pain and Discomfort") +
    items("Eye pain","Deep eye ache","Foreign body sensation","Gritty / sandy sensation","Itching / burning",
          "Photophobia","Headache with eye symptoms","Brow ache") +
    h("External / Appearance") +
    items("Red eye","Ocular discharge (watery)","Ocular discharge (purulent)","Swelling around eye","Swollen eyelid",
          "Drooping eyelid (ptosis)","Watery / excessive tearing","Eye protrusion (proptosis)",
          "White spot on cornea","Whitish pupil (leukocoria)","Yellow discolouration of eye") +
    h("Other / Follow-up") +
    items("Floaters","Flashing lights (photopsia)","Glare / halos around lights","Difficulty reading","Eye turn / squint",
          "Routine eye check","Post-operative review","Diabetic eye review","Glaucoma follow-up","Pre-operative assessment")
)
cc_ref = (
    h("Visual Symptoms") +
    items("Blurred near vision","Blurred distant vision","Blurred vision at all distances","Difficulty reading",
          "Difficulty seeing board / TV","Eye strain / fatigue","Headache after near work","Squinting to see far",
          "Double vision","Distorted vision") +
    h("Paediatric / Squint") +
    items("Eye turn (squint / strabismus)","Lazy eye (amblyopia)","Poor school performance",
          "Child rubbing eyes frequently","Tilting head to see","Whitish reflex from eye","Nystagmus (wobbling eyes)") +
    h("Glasses / Lenses") +
    items("New glasses needed","Glasses check / renewal","Glasses no longer working","Broken glasses",
          "Contact lens fitting","Contact lens problem","Photophobia")
)
cc_gp = (
    h("Fever / Infections") +
    items("Fever","Fever with rigors / chills","Malaria symptoms","Typhoid fever","Persistent cough",
          "Productive cough","Cough with haemoptysis","Night sweats") +
    h("Cardiorespiratory") +
    items("Shortness of breath","Chest pain","Wheezing","Palpitations","Orthopnoea") +
    h("GI / General") +
    items("Abdominal pain","Nausea / vomiting","Diarrhoea","Jaundice","Fatigue / weakness",
          "Weight loss","Oedema","Skin rash","Headache","Urinary symptoms") +
    h("Follow-up") +
    items("Hypertension follow-up","Diabetes follow-up","TB follow-up","HIV follow-up","General check-up")
)

hpc = (
    h("Duration") +
    items("Hours","1 day","2-3 days","1 week","2 weeks","1 month","3 months","6 months","1 year",">1 year","Several years","Since childhood") +
    h("Onset") +
    items("Sudden onset","Gradual onset","Insidious onset","On waking","After trauma / injury") +
    h("Course") +
    items("Worsening","Improving","Stable / unchanged","Intermittent","Recurrent episodes","Fluctuating") +
    h("Modifying Factors") +
    items("Worse in morning","Worse at night","Worse with reading","Worse in bright light","Worse in dim light",
          "Worse after screen use","Relieved by rest","No relieving factors") +
    h("Associated Symptoms") +
    items("Associated headache","Associated nausea / vomiting","Associated fever","No associated symptoms") +
    h("Prior Treatment") +
    items("No prior treatment","Used traditional eye medicine","Applied herbal remedy to eye",
          "Used OTC eye drops","Seen at another hospital","Referred from primary care")
)

oh_ref = (
    h("Refractive / Squint") +
    items("Wearing glasses (current)","Wearing contact lenses","Previously wore glasses","Amblyopia (lazy eye)",
          "Squint / strabismus","Patching therapy (ongoing)","Completed patching therapy","Orthoptic treatment",
          "Previous squint surgery","Nystagmus","Ptosis (eyelid droop)","Congenital cataract","Retinopathy of prematurity (ROP)")
)
oh_oph = (
    h("Surgery") +
    items("Previous cataract surgery (RE)","Previous cataract surgery (LE)","Previous cataract surgery (both)",
          "Previous trabeculectomy (glaucoma)","Previous glaucoma drainage device","Previous vitrectomy",
          "Previous retinal detachment repair","Previous corneal transplant","Previous laser photocoagulation",
          "Previous anti-VEGF injections","Previous oculoplastic surgery") +
    h("Medical / Ocular") +
    items("Wearing glasses","Wearing contact lenses","Glaucoma (diagnosed)","Diabetic retinopathy",
          "Macular degeneration","Uveitis (recurrent)","Corneal scar / opacity","Ocular trauma",
          "Chemical / alkali injury","Amblyopia","Dry eye disease","Keratoconus","Pterygium",
          "Trachoma","Onchocerciasis-related","Sickle cell retinopathy","Retinitis pigmentosa","Optic neuropathy")
)

sys_hist = (
    '<li><button type="button" class="dropdown-item">No significant systemic history</button></li>\n                ' +
    h("Metabolic / Endocrine") +
    items("Hypertension","DM Type 1","DM Type 2","Gestational diabetes","Thyroid disease (hypothyroid)","Thyroid disease (hyperthyroid)","Obesity") +
    h("Blood / Haematology") +
    items("Sickle cell disease (HbSS)","Sickle cell trait (HbAS)","Sickle cell HbSC","Anaemia","G6PD deficiency","Bleeding disorder") +
    h("Infections / Tropical") +
    items("HIV / AIDS (on ARVs)","HIV / AIDS (not on ARVs)","Tuberculosis (active)","Tuberculosis (past / treated)",
          "Malaria (recurrent)","Onchocerciasis (river blindness)","Toxoplasmosis","Leprosy","Hepatitis B","Hepatitis C") +
    h("Autoimmune / Rheumatic") +
    items("Rheumatoid arthritis","SLE","Ankylosing spondylitis","Sarcoidosis","Behcet disease","Psoriasis","Inflammatory bowel disease") +
    h("Neurological / Cardiovascular") +
    items("Stroke / CVA","TIA","Migraine","Multiple sclerosis","Myasthenia gravis","Cardiac disease","Atrial fibrillation","Renal disease / CKD","Liver disease / cirrhosis") +
    h("Other") +
    items("Cancer / malignancy","On chemotherapy","Asthma / COPD","Epilepsy","Mental health condition","Pregnancy")
)

dh_oph = (
    h("Topical Eye") +
    items("Topical anti-glaucoma drops","Topical steroid eye drops","Topical antibiotic eye drops",
          "Topical antiviral eye drops","Topical lubricants / artificial tears","Topical NSAID drops",
          "Topical antifungal drops","Mydriatic drops") +
    h("Systemic") +
    items("Oral steroids (prednisolone)","Anti-VEGF injections (IVT)","Immunosuppressants (methotrexate)",
          "Immunosuppressants (azathioprine)","Carbonic anhydrase inhibitor (Diamox)","Anti-hypertensives",
          "Oral hypoglycaemics","Insulin","Anticoagulants (warfarin)","Aspirin","Ethambutol (for TB)",
          "Chloroquine / hydroxychloroquine","ARVs (antiretrovirals)","Anti-TB medications (RHZE)","Ivermectin (onchocerciasis)")
)
dh_gp = (
    h("Cardiovascular / Metabolic") +
    items("Anti-hypertensives (amlodipine)","Anti-hypertensives (lisinopril)","Anti-hypertensives (atenolol)",
          "Oral hypoglycaemics (metformin)","Oral hypoglycaemics (glibenclamide)",
          "Insulin (short acting)","Insulin (long acting)","Statins (atorvastatin)","Aspirin","Warfarin") +
    h("Infections") +
    items("ARVs (antiretrovirals)","Anti-TB (RHZE)","Cotrimoxazole prophylaxis",
          "Anti-malarials (artemether-lumefantrine)","Antibiotics (ongoing course)","Ivermectin") +
    h("Other") +
    items("Oral steroids","Inhalers (salbutamol)","Antiepileptics","Iron / folic acid supplements","Vitamins / supplements")
)

fh_oph = (
    h("Ocular") +
    items("Glaucoma","Cataract (early onset)","Retinal disease","Macular degeneration",
          "Corneal disease / keratoconus","Retinitis pigmentosa","Squint / amblyopia","Colour blindness","Blindness (cause unknown)") +
    h("Systemic") +
    items("Diabetes mellitus","Hypertension","Sickle cell disease","Sickle cell trait",
          "Thyroid disease","SLE / autoimmune disease","Cancer","Stroke / CVA")
)
fh_gp = (
    h("Common") +
    items("Hypertension","Diabetes mellitus","Cardiac disease","Stroke","Cancer","Tuberculosis",
          "Sickle cell disease","Sickle cell trait","Asthma","Renal disease","Mental illness")
)

sh = (
    h("Smoking / Alcohol") +
    items("Non-smoker","Smoker (active)","Ex-smoker","No alcohol use","Alcohol use (moderate)","Alcohol use (heavy)") +
    h("Occupation / Exposure") +
    items("Farmer / agriculture","Outdoor worker (sun exposure)","Welder / arc exposure","Office / computer work",
          "Driver / transport","Healthcare worker","Teacher","Student","Retired","Housewife / homemaker",
          "Fisherman","Chemical exposure (workplace)","Dusty / smoky environment") +
    h("Traditional Medicine") +
    items("Uses traditional eye medicine","Applied herbal remedy to eye","Visited traditional healer","No traditional medicine use") +
    h("Diet / Nutrition") +
    items("Adequate diet","Poor nutrition / malnutrition","Vitamin A deficiency suspected") +
    h("Living Situation") +
    items("Lives alone","Lives with family","Rural community","Urban area","No electricity at home")
)

def ul(body):
    return f'<ul class="dropdown-menu dropdown-menu-end ehr-add-menu" style="max-height:320px;overflow-y:auto;">\n                {body.strip()}\n                </ul>'

new_section = f"""      <div id="bodyHistory" class="card-body">
        <div class="row g-3">
          {{% with dept_code=consultation.department.code|default:consultation.consulting_doctor.role_department_code %}}
          <div class="col-md-4">
            <label class="form-label fw-semibold small">Department</label>
            {{{{ form.department }}}}
          </div>
          <div class="col-md-8">
            <label class="form-label fw-semibold small">Chief Complaint <span class="text-danger">*</span></label>
            <div class="ehr-combo d-flex gap-1 align-items-start">
              <textarea name="presenting_complaint" rows="2" class="form-control form-control-sm flex-grow-1"
                        placeholder="Type here, or pick from list">{{{{ form.presenting_complaint.value|default:'' }}}}</textarea>
              <div class="dropdown" style="flex-shrink:0;">
                <button type="button" class="btn btn-sm ehr-add-btn dropdown-toggle" data-bs-toggle="dropdown">+ Add</button>
                {{% if dept_code == {oph} %}}
                {ul(cc_oph)}
                {{% elif dept_code == {ref} %}}
                {ul(cc_ref)}
                {{% elif dept_code == "GEN_PHYS" %}}
                {ul(cc_gp)}
                {{% else %}}
                {ul(cc_oph)}
                {{% endif %}}
              </div>
            </div>
          </div>
          <div class="col-md-6">
            <label class="form-label fw-semibold small">History of Presenting Complaint</label>
            <div class="ehr-combo d-flex gap-1 align-items-start">
              <textarea name="history_of_presenting_complaint" rows="2" class="form-control form-control-sm flex-grow-1"
                        placeholder="Duration, onset, course">{{{{ form.history_of_presenting_complaint.value|default:'' }}}}</textarea>
              <div class="dropdown" style="flex-shrink:0;">
                <button type="button" class="btn btn-sm ehr-add-btn dropdown-toggle" data-bs-toggle="dropdown">+ Add</button>
                {ul(hpc)}
              </div>
            </div>
          </div>
          <div class="col-md-6">
            <label class="form-label fw-semibold small">Ocular History</label>
            <div class="ehr-combo d-flex gap-1 align-items-start">
              <textarea name="ocular_history" rows="2" class="form-control form-control-sm flex-grow-1"
                        placeholder="Previous eye conditions, surgeries">{{{{ form.ocular_history.value|default:'' }}}}</textarea>
              <div class="dropdown" style="flex-shrink:0;">
                <button type="button" class="btn btn-sm ehr-add-btn dropdown-toggle" data-bs-toggle="dropdown">+ Add</button>
                <ul class="dropdown-menu dropdown-menu-end ehr-add-menu" style="max-height:320px;overflow-y:auto;">
                <li><button type="button" class="dropdown-item">No previous eye problems</button></li>
                {{% if dept_code == {ref} %}}
                {oh_ref.strip()}
                {{% else %}}
                {oh_oph.strip()}
                {{% endif %}}
                </ul>
              </div>
            </div>
          </div>
          <div class="col-md-6">
            <label class="form-label fw-semibold small">Systemic History</label>
            <div class="ehr-combo d-flex gap-1 align-items-start">
              <textarea name="systemic_history" rows="2" class="form-control form-control-sm flex-grow-1"
                        placeholder="Systemic conditions">{{{{ form.systemic_history.value|default:'' }}}}</textarea>
              <div class="dropdown" style="flex-shrink:0;">
                <button type="button" class="btn btn-sm ehr-add-btn dropdown-toggle" data-bs-toggle="dropdown">+ Add</button>
                {ul(sys_hist)}
              </div>
            </div>
          </div>
          <div class="col-md-3">
            <label class="form-label fw-semibold small">Drug History</label>
            <div class="ehr-combo d-flex gap-1 align-items-start">
              <textarea name="drug_history" rows="2" class="form-control form-control-sm flex-grow-1"
                        placeholder="Current medications">{{{{ form.drug_history.value|default:'' }}}}</textarea>
              <div class="dropdown" style="flex-shrink:0;">
                <button type="button" class="btn btn-sm ehr-add-btn dropdown-toggle" data-bs-toggle="dropdown">+ Add</button>
                <ul class="dropdown-menu dropdown-menu-end ehr-add-menu" style="max-height:320px;overflow-y:auto;">
                <li><button type="button" class="dropdown-item">No current medication</button></li>
                <li><button type="button" class="dropdown-item">NKDA (no known drug allergies)</button></li>
                {{% if dept_code == {doph} %}}
                {dh_oph.strip()}
                {{% elif dept_code == "GEN_PHYS" %}}
                {dh_gp.strip()}
                {{% else %}}
                <li><button type="button" class="dropdown-item">On topical eye drops</button></li>
                <li><button type="button" class="dropdown-item">On systemic steroids</button></li>
                <li><button type="button" class="dropdown-item">On anti-hypertensives</button></li>
                <li><button type="button" class="dropdown-item">On oral hypoglycaemics</button></li>
                <li><button type="button" class="dropdown-item">On insulin</button></li>
                <li><button type="button" class="dropdown-item">On ARVs</button></li>
                <li><button type="button" class="dropdown-item">On anti-TB medications</button></li>
                {{% endif %}}
                </ul>
              </div>
            </div>
          </div>
          <div class="col-md-3">
            <label class="form-label fw-semibold small">Family History</label>
            <div class="ehr-combo d-flex gap-1 align-items-start">
              <textarea name="family_history" rows="2" class="form-control form-control-sm flex-grow-1"
                        placeholder="Family conditions">{{{{ form.family_history.value|default:'' }}}}</textarea>
              <div class="dropdown" style="flex-shrink:0;">
                <button type="button" class="btn btn-sm ehr-add-btn dropdown-toggle" data-bs-toggle="dropdown">+ Add</button>
                <ul class="dropdown-menu dropdown-menu-end ehr-add-menu" style="max-height:320px;overflow-y:auto;">
                <li><button type="button" class="dropdown-item">No significant family history</button></li>
                {{% if dept_code == "GEN_PHYS" %}}
                {fh_gp.strip()}
                {{% else %}}
                {fh_oph.strip()}
                {{% endif %}}
                </ul>
              </div>
            </div>
          </div>
          <div class="col-md-6">
            <label class="form-label fw-semibold small">Social History</label>
            <div class="ehr-combo d-flex gap-1 align-items-start">
              <textarea name="social_history" rows="2" class="form-control form-control-sm flex-grow-1"
                        placeholder="Occupation, lifestyle">{{{{ form.social_history.value|default:'' }}}}</textarea>
              <div class="dropdown" style="flex-shrink:0;">
                <button type="button" class="btn btn-sm ehr-add-btn dropdown-toggle" data-bs-toggle="dropdown">+ Add</button>
                {ul(sh)}
              </div>
            </div>
          </div>
          {{% endwith %}}
        </div>
      </div>
    </div>
  </div>
  {{% endif %}}{{# /GEN_PHYS Section 1 hide #}}"""

new_content = content[:si] + new_section + content[ei + len(end_marker):]
with open(path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("OK lines:", new_content.count("\n"))
print("Sickle cell:", "Sickle cell disease (HbSS)" in new_content)
print("Onchocerciasis:", "Onchocerciasis" in new_content)
print("Traditional:", "traditional eye medicine" in new_content)
