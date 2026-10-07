import sys, os

path = r"c:\Users\GROD\Desktop\EHR AFRICA BACKUP\templates\consultations\create.html"
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = '      <div id="bodyHistory" class="card-body collapse show">\n        <div class="row g-3">'
end_marker = '        </div>\n        <div class="mt-2 pt-2 border-top d-flex justify-content-end">'

si = content.find(start_marker)
ei = content.find(end_marker)

if si < 0 or ei < 0:
    print(f"ERROR: markers not found si={si} ei={ei}")
    sys.exit(1)

# Build the li helpers
def h(label):
    return f'<li><span class="dropdown-header px-3 py-1 fw-semibold" style="font-size:.72rem;color:#6b7280;">{label}</span></li>\n'

def item(text):
    return f'<li><button type="button" class="dropdown-item">{text}</button></li>'

def items(*texts):
    return ''.join(item(t) for t in texts) + '\n'

def dd(name, field_name, placeholder, body):
    return f'''          <div class="ehr-combo d-flex gap-1 align-items-start">
              <textarea name="{field_name}" rows="2" class="form-control form-control-sm flex-grow-1" placeholder="{placeholder}"></textarea>
              <div class="dropdown" style="flex-shrink:0;">
                <button type="button" class="btn btn-sm ehr-add-btn dropdown-toggle" data-bs-toggle="dropdown">+ Add</button>
                <ul class="dropdown-menu dropdown-menu-end ehr-add-menu" style="max-height:320px;overflow-y:auto;">
                {body}
                </ul>
              </div>
            </div>'''

# === Chief Complaint body ===
oph_depts = '"GEN_OPH" or dept_code == "RETINA" or dept_code == "GLAUC" or dept_code == "GLAUCOMA" or dept_code == "UVEITIS" or dept_code == "CATARACT" or dept_code == "CORNEA" or dept_code == "OCULOPLASTY" or dept_code == "NEURO_OPH" or dept_code == "LOW_VIS"'
ref_depts = '"REFRAC" or dept_code == "PEDS_REFRAC" or dept_code == "ORTHO" or dept_code == "PEDS" or dept_code == "PEDS_OPH"'

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
    h("Other Phenomena") +
    items("Floaters","Flashing lights (photopsia)","Glare / halos around lights","Difficulty reading","Eye turn / squint") +
    h("Follow-up / Review") +
    items("Routine eye check","Post-operative review","Diabetic eye review","Glaucoma follow-up","Pre-operative assessment")
)

cc_ref = (
    h("Visual Symptoms") +
    items("Blurred near vision","Blurred distant vision","Blurred vision at all distances","Difficulty reading",
          "Difficulty seeing board / TV","Eye strain / fatigue","Headache after near work","Squinting to see far",
          "Double vision","Distorted vision") +
    h("Paediatric / Squint") +
    items("Eye turn (squint / strabismus)","Eye turn noticed by parents","Lazy eye (amblyopia)","Poor school performance",
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
    items("Shortness of breath","Chest pain","Wheezing","Orthopnoea","Palpitations") +
    h("GI / Abdominal") +
    items("Abdominal pain","Nausea / vomiting","Diarrhoea","Bloody diarrhoea","Constipation","Jaundice","Haematemesis") +
    h("General / Neurological") +
    items("Headache","Dizziness / vertigo","Fatigue / weakness","Weight loss","Oedema (legs)","Joint pain",
          "Back pain","Urinary frequency","Burning on urination","Haematuria","Skin rash","Numbness / tingling") +
    h("Follow-up") +
    items("Hypertension follow-up","Diabetes follow-up","TB follow-up","HIV follow-up","General check-up")
)

cc_else = items("Blurred vision","Eye pain","Red eye","Reduced vision","Floaters","Double vision","Headache","Fever","Chest pain","Abdominal pain","Fatigue")

cc_body = f"""{{% if dept_code == {oph_depts} %}}
                {cc_oph.strip()}
                {{% elif dept_code == {ref_depts} %}}
                {cc_ref.strip()}
                {{% elif dept_code == "GEN_PHYS" %}}
                {cc_gp.strip()}
                {{% else %}}
                {cc_else.strip()}
                {{% endif %}}"""

# === History & Duration body ===
hpc_body = (
    h("Duration") +
    items("Hours","1 day","2-3 days","1 week","2 weeks","1 month","3 months","6 months","1 year","&gt;1 year","Several years","Since childhood") +
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

# === Ocular History body ===
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
          "Previous anti-VEGF injections","Previous oculoplastic surgery","Previous squint surgery") +
    h("Medical / Ocular") +
    items("Wearing glasses","Wearing contact lenses","Glaucoma (diagnosed)","Diabetic retinopathy",
          "Macular degeneration","Uveitis (recurrent)","Corneal scar / opacity","Ocular trauma",
          "Chemical / alkali injury","Amblyopia","Dry eye disease","Keratoconus","Pterygium",
          "Trachoma","Onchocerciasis-related","Sickle cell retinopathy","Retinitis pigmentosa","Optic neuropathy")
)
oh_body = f"""{item("No previous eye problems")}
                {{% if dept_code == {ref_depts} %}}
                {oh_ref.strip()}
                {{% else %}}
                {oh_oph.strip()}
                {{% endif %}}"""

# === Systemic History body ===
sys_body = (
    item("No significant systemic history") + "\n" +
    h("Metabolic / Endocrine") +
    items("Hypertension","DM Type 1","DM Type 2","Gestational diabetes",
          "Thyroid disease (hypothyroid)","Thyroid disease (hyperthyroid)","Obesity") +
    h("Blood / Haematology") +
    items("Sickle cell disease (HbSS)","Sickle cell trait (HbAS)","Sickle cell HbSC",
          "Anaemia","G6PD deficiency","Bleeding disorder") +
    h("Infections / Tropical") +
    items("HIV / AIDS (on ARVs)","HIV / AIDS (not on ARVs)","Tuberculosis (active)","Tuberculosis (past / treated)",
          "Malaria (recurrent)","Onchocerciasis (river blindness)","Toxoplasmosis","Leprosy","Hepatitis B","Hepatitis C") +
    h("Autoimmune / Rheumatic") +
    items("Rheumatoid arthritis","SLE","Ankylosing spondylitis","Sarcoidosis",
          "Behcet disease","Psoriasis","Inflammatory bowel disease") +
    h("Neurological / Cardiovascular") +
    items("Stroke / CVA","TIA","Migraine","Multiple sclerosis","Myasthenia gravis",
          "Cardiac disease","Atrial fibrillation","Renal disease / CKD","Liver disease / cirrhosis") +
    h("Other") +
    items("Cancer / malignancy","On chemotherapy","Asthma / COPD","Epilepsy","Mental health condition","Pregnancy")
)

# === Drug History body ===
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
dh_else = items("On topical eye drops","On systemic steroids","On anti-hypertensives","On oral hypoglycaemics",
                "On insulin","On immunosuppressants","On ARVs","On anti-TB medications")

dh_oph_depts = '"GEN_OPH" or dept_code == "GLAUC" or dept_code == "GLAUCOMA" or dept_code == "RETINA" or dept_code == "UVEITIS" or dept_code == "CATARACT" or dept_code == "CORNEA" or dept_code == "OCULOPLASTY" or dept_code == "NEURO_OPH" or dept_code == "LOW_VIS"'
dh_body = f"""{item("No current medication")} {item("NKDA (no known drug allergies)")}
                {{% if dept_code == {dh_oph_depts} %}}
                {dh_oph.strip()}
                {{% elif dept_code == "GEN_PHYS" %}}
                {dh_gp.strip()}
                {{% else %}}
                {dh_else.strip()}
                {{% endif %}}"""

# === Family History body ===
fh_gp = (
    h("Common") +
    items("Hypertension","Diabetes mellitus","Cardiac disease","Stroke","Cancer","Tuberculosis",
          "Sickle cell disease","Sickle cell trait","Asthma","Renal disease","Mental illness")
)
fh_oph = (
    h("Ocular") +
    items("Glaucoma","Cataract (early onset)","Retinal disease","Macular degeneration",
          "Corneal disease / keratoconus","Retinitis pigmentosa","Squint / amblyopia",
          "Colour blindness","Blindness (cause unknown)") +
    h("Systemic") +
    items("Diabetes mellitus","Hypertension","Sickle cell disease","Sickle cell trait",
          "Thyroid disease","SLE / autoimmune disease","Cancer","Stroke / CVA")
)
fh_body = f"""{item("No significant family history")}
                {{% if dept_code == "GEN_PHYS" %}}
                {fh_gp.strip()}
                {{% else %}}
                {fh_oph.strip()}
                {{% endif %}}"""

# === Social History body ===
sh_body = (
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

new_section = f"""      <div id="bodyHistory" class="card-body collapse show">
        <div class="row g-3">

          {{# Chief Complaint #}}
          <div class="col-12 col-lg-6">
            <label class="form-label fw-semibold small">Chief Complaint <span class="text-danger">*</span></label>
            {dd("Chief Complaint", "presenting_complaint", "Type here, or pick from list", cc_body)}
          </div>

          {{# History of Presenting Complaint #}}
          <div class="col-12 col-lg-6">
            <label class="form-label fw-semibold small">History &amp; Duration</label>
            {dd("History", "history_of_presenting_complaint", "Duration, onset, course...", hpc_body.strip())}
          </div>

          {{# Ocular History #}}
          <div class="col-12 col-lg-6">
            <label class="form-label fw-semibold small">Ocular History</label>
            {dd("Ocular History", "ocular_history", "Previous eye conditions, surgeries...", oh_body)}
          </div>

          {{# Systemic History #}}
          <div class="col-12 col-lg-6">
            <label class="form-label fw-semibold small">Systemic History</label>
            {dd("Systemic History", "systemic_history", "Systemic conditions...", sys_body.strip())}
          </div>

          {{# Drug History #}}
          <div class="col-12 col-lg-4">
            <label class="form-label fw-semibold small">Drug History</label>
            {dd("Drug History", "drug_history", "Current medications...", dh_body)}
          </div>

          {{# Family History #}}
          <div class="col-12 col-lg-4">
            <label class="form-label fw-semibold small">Family History</label>
            {dd("Family History", "family_history", "Family conditions...", fh_body)}
          </div>

          {{# Social History #}}
          <div class="col-12 col-lg-4">
            <label class="form-label fw-semibold small">Social History</label>
            {dd("Social History", "social_history", "Occupation, lifestyle...", sh_body.strip())}
          </div>

"""

new_content = content[:si] + new_section + content[ei:]
with open(path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("OK")
print("Sickle cell:", "Sickle cell disease (HbSS)" in new_content)
print("Onchocerciasis:", "Onchocerciasis" in new_content)
print("Traditional:", "traditional eye medicine" in new_content)
print("Trachoma:", "Trachoma" in new_content)
print("ARVs:", "ARVs (antiretrovirals)" in new_content)
print("Lines:", new_content.count("\n"))
