"""
Claude API client for the EHR AI Assistant.
Builds context-aware prompts from patient/consultation data.
"""
import time
import logging
from django.conf import settings

logger = logging.getLogger('apps.ai_assistant')

OPHTHALMOLOGY_SYSTEM_PROMPT = """You are an advanced AI clinical decision support assistant embedded in an Electronic Health Record system for GLUDD Specialist Eye Hospital in Cameroon.

You have access to the patient's COMPLETE medical record, including:
- Full consultation history with all examination findings and diagnoses
- All laboratory results (haematology, biochemistry, serology, microbiology, urinalysis) with reference ranges and abnormal flags
- All ophthalmic investigation results: OCT, Humphrey Visual Field, Fundus Photography, Fluorescein Angiography (FFA), Biometry (IOL Master/A-scan), B-scan ultrasound, Corneal Topography (Pentacam), Pachymetry, ERG, Refraction results — with full structured data and reports
- All imaging studies with radiologist/technician reports
- All drug and optical prescriptions
- Problem list, allergies, medical history, family history, social history

Your role is to assist qualified ophthalmologists and medical staff with:
- Advanced differential diagnosis using ALL available clinical and investigation data
- Deep interpretation of investigation results: OCT layers, visual field patterns (MD, PSD, VFI trends), biometry for IOL calculation, corneal topography indices, fundus findings, FFA leak patterns
- Clinical management guidance based on current evidence (AAO, NICE, WHO, ICO guidelines)
- Drug information (ophthalmic drops, intravitreal agents, systemic drugs for ocular disease)
- Drug interaction checking and dosage guidance
- ICD-10 coding for ophthalmic and systemic diagnoses
- Surgical planning: IOL selection, surgical risk assessment, post-op monitoring
- Paediatric ophthalmology, amblyopia management, strabismus
- Glaucoma staging and management (IOP targets, nerve fibre layer analysis)
- Retinal disease: diabetic retinopathy grading, AMD staging, RD risk
- Research context: disease prevalence, clinical trial data, evidence levels
- Patient summary: synthesise the full record into a coherent clinical narrative

IMPORTANT RULES:
1. You are a clinical decision SUPPORT tool — all final clinical decisions rest with qualified medical professionals.
2. Never contradict a treating physician's direct clinical judgment without strong evidence.
3. Always recommend verification of drug doses against current formulary (BNF, WHO).
4. Flag sight-threatening and life-threatening emergencies prominently.
5. If data is not in the record, say "not documented" — do NOT fabricate patient-specific values.
6. Cite evidence levels when making recommendations (Grade A/B/C, Level I/II/III).

RESPONSE FORMAT:
- Be concise and clinically precise
- Use proper ophthalmic terminology
- Structure responses with clear headings for complex analyses
- For investigation interpretation, structure as: Key Findings → Clinical Significance → Recommended Action
- For differential diagnoses, rank by likelihood with supporting/opposing features

Hospital context — Cameroon:
- Consider local disease burden: glaucoma (high prevalence), sickle cell retinopathy, onchocerciasis, trachoma, diabetic eye disease, vitamin A deficiency
- Consider available resources and realistic treatment options in sub-Saharan Africa
- Currency FCFA, language context French/English bilingual"""


def build_consultation_context(consultation):
    """Build a context string from a consultation to inject into the system prompt."""
    if not consultation:
        return ""

    patient = consultation.patient
    lines = [
        f"\n--- CURRENT PATIENT CONTEXT ---",
        f"Patient: {patient.full_name}, {patient.age}yr, {patient.get_gender_display()}",
        f"Department: {consultation.department}",
        f"Chief Complaint: {consultation.presenting_complaint}",
    ]

    if consultation.history_of_presenting_complaint:
        lines.append(f"HPC: {consultation.history_of_presenting_complaint[:300]}")

    if consultation.systemic_history:
        lines.append(f"Systemic History: {consultation.systemic_history[:200]}")

    # Primary diagnosis
    primary = consultation.primary_diagnosis
    if primary:
        lines.append(f"Working Diagnosis: {primary}")

    # Visual acuity from visit
    visit = consultation.visit
    if visit and visit.vital_signs:
        vs = visit.vital_signs
        if vs.get('visual_acuity_right') or vs.get('visual_acuity_left'):
            lines.append(f"VA: RE {vs.get('visual_acuity_right', 'N/R')} | LE {vs.get('visual_acuity_left', 'N/R')}")
        if vs.get('intraocular_pressure_right') or vs.get('intraocular_pressure_left'):
            lines.append(f"IOP: RE {vs.get('intraocular_pressure_right', 'N/R')} | LE {vs.get('intraocular_pressure_left', 'N/R')} mmHg")

    # Department-specific exam data
    exam_data = getattr(consultation, 'department_specific_data', None)
    if exam_data:
        exam_summary = build_exam_context(exam_data)
        if exam_summary:
            lines.append("Examination Findings:")
            lines.append(exam_summary)

    lines.append("--- END PATIENT CONTEXT ---\n")
    return "\n".join(lines)


def _get_chat_fn():
    """Return the appropriate chat function based on AI_ENGINE_REASONING setting."""
    engine = getattr(settings, 'AI_ENGINE_REASONING', 'groq').lower()
    if engine == 'ollama':
        from apps.ai_assistant.ollama_client import ollama_chat
        return ollama_chat
    else:
        from apps.ai_assistant.groq_client import groq_chat
        return groq_chat


def _get_json_fn():
    """Return the appropriate JSON chat function based on AI_ENGINE_REASONING setting."""
    engine = getattr(settings, 'AI_ENGINE_REASONING', 'groq').lower()
    if engine == 'ollama':
        from apps.ai_assistant.ollama_client import ollama_json
        return ollama_json
    else:
        from apps.ai_assistant.groq_client import groq_json
        return groq_json


def build_patient_context(patient):
    """
    Compile a patient's COMPLETE medical record into a text context block for the AI.
    Includes demographics, medical history, problem list, all consultations with full
    clinical data, lab results, investigations, optical Rx, drug Rx, and vital signs.
    """
    phone = getattr(patient, 'phone_number', None) or getattr(patient, 'phone', None) or 'N/A'
    lines = [
        "=" * 60,
        f"PATIENT MEDICAL RECORD",
        "=" * 60,
        f"Name:   {patient.full_name}",
        f"ID:     {patient.patient_id}",
        f"DOB:    {patient.date_of_birth}  |  Age: {patient.age}  |  Gender: {patient.get_gender_display()}",
        f"Phone:  {phone}",
    ]
    for attr in ('region', 'occupation', 'address', 'nationality'):
        val = getattr(patient, attr, None)
        if val:
            lines.append(f"{attr.capitalize()}: {val}")

    # ── 1. ALLERGIES ──────────────────────────────────────────────────────
    try:
        from apps.patients.models import PatientAllergy
        allergies = PatientAllergy.objects.filter(patient=patient, is_deleted=False)
        if allergies.exists():
            lines.append("\n⚠ ALLERGIES:")
            for a in allergies:
                sev = getattr(a, 'severity', '') or ''
                rxn = getattr(a, 'reaction', '') or ''
                lines.append(f"  • {a.allergen}{' — ' + sev if sev else ''}{' (' + rxn + ')' if rxn else ''}")
        else:
            lines.append("\nAllergies: None documented")
    except Exception:
        pass

    # ── 2. MEDICAL HISTORY ────────────────────────────────────────────────
    try:
        mh = patient.medical_history
        lines.append("\n── MEDICAL HISTORY ──")
        if mh.chronic_conditions:
            lines.append(f"  Chronic Conditions:      {mh.chronic_conditions}")
        if mh.systemic_history:
            lines.append(f"  Systemic History:        {mh.systemic_history}")
        if mh.previous_eye_conditions:
            lines.append(f"  Previous Eye Conditions: {mh.previous_eye_conditions}")
        if mh.previous_eye_surgeries:
            lines.append(f"  Previous Eye Surgeries:  {mh.previous_eye_surgeries}")
        if mh.spectacle_history:
            lines.append(f"  Spectacle History:       {mh.spectacle_history}")
        if mh.previous_surgeries:
            lines.append(f"  Previous Surgeries:      {mh.previous_surgeries}")
        if mh.current_medications:
            lines.append(f"  Current Medications:     {mh.current_medications}")
        if mh.family_ocular_history:
            lines.append(f"  Family Ocular History:   {mh.family_ocular_history}")
        if mh.social_history:
            lines.append(f"  Social History:          {mh.social_history}")
        if mh.known_allergies:
            lines.append(f"  Known Allergies (notes): {mh.known_allergies}")
    except Exception:
        pass

    # ── 3. ACTIVE MEDICATIONS ─────────────────────────────────────────────
    try:
        from apps.patients.models import PatientMedication
        meds = PatientMedication.objects.filter(patient=patient, is_active=True)
        if meds.exists():
            lines.append("\n── CURRENT MEDICATIONS ──")
            for m in meds:
                parts = [m.drug_name]
                if m.dose: parts.append(m.dose)
                if m.frequency: parts.append(m.frequency)
                if m.route: parts.append(m.route)
                if m.indication: parts.append(f"for {m.indication}")
                lines.append(f"  • {' — '.join(parts)}")
    except Exception:
        pass

    # ── 4. PROBLEM LIST ───────────────────────────────────────────────────
    try:
        from apps.patients.models import PatientProblem
        problems = PatientProblem.objects.filter(
            patient=patient, status__in=['ACTIVE', 'CHRONIC', 'MONITORED']
        ).order_by('status', '-created_at')
        if problems.exists():
            lines.append("\n── PROBLEM LIST ──")
            for p in problems:
                code = f" [{p.icd10_code}]" if p.icd10_code else ""
                onset = f" (onset: {p.onset_date})" if p.onset_date else ""
                lines.append(f"  • [{p.get_status_display()}] {p.problem}{code}{onset}")
                if p.notes:
                    lines.append(f"    Notes: {p.notes[:150]}")
    except Exception:
        pass

    # ── 5. CONSULTATIONS (full clinical detail) ───────────────────────────
    try:
        from apps.consultations.models import Consultation, ConsultationDiagnosis
        consults = list(
            Consultation.objects.filter(patient=patient, is_deleted=False)
            .order_by('-consultation_date')
            .select_related('department', 'consulting_doctor')
            .prefetch_related('consultation_diagnoses__diagnosis',
                              'drug_prescriptions__items',
                              'optical_prescriptions',
                              'lab_orders__items__result',
                              'investigation_orders__result')[:12]
        )
        if consults:
            lines.append("\n── CONSULTATION RECORDS ──")
            for c in consults:
                dept = c.department.name if c.department else 'Unknown'
                doc = c.consulting_doctor.get_full_name() if c.consulting_doctor else 'Unknown'
                lines.append(f"\n  [{c.consultation_date.strftime('%d %b %Y %H:%M')}] {dept} — Dr. {doc} ({c.get_status_display()})")

                if c.presenting_complaint:
                    lines.append(f"    Complaint:    {c.presenting_complaint}")
                if c.history_of_presenting_complaint:
                    lines.append(f"    HPC:          {c.history_of_presenting_complaint[:300]}")
                if c.ocular_history:
                    lines.append(f"    Ocular Hx:    {c.ocular_history[:200]}")
                if c.systemic_history:
                    lines.append(f"    Systemic Hx:  {c.systemic_history[:200]}")
                if c.drug_history:
                    lines.append(f"    Drug Hx:      {c.drug_history[:200]}")
                if c.family_history:
                    lines.append(f"    Family Hx:    {c.family_history[:150]}")

                # Vital signs from this visit
                try:
                    vs = c.visit.vital_signs if c.visit else None
                    if vs:
                        va_r = getattr(vs, 'visual_acuity_right', None) or vs.get('visual_acuity_right', '') if isinstance(vs, dict) else getattr(vs, 'visual_acuity_right', '')
                        va_l = getattr(vs, 'visual_acuity_left', None) or vs.get('visual_acuity_left', '') if isinstance(vs, dict) else getattr(vs, 'visual_acuity_left', '')
                        iop_r = getattr(vs, 'intraocular_pressure_right', None) or vs.get('intraocular_pressure_right', '') if isinstance(vs, dict) else getattr(vs, 'intraocular_pressure_right', '')
                        iop_l = getattr(vs, 'intraocular_pressure_left', None) or vs.get('intraocular_pressure_left', '') if isinstance(vs, dict) else getattr(vs, 'intraocular_pressure_left', '')
                        if any([va_r, va_l, iop_r, iop_l]):
                            lines.append(f"    VA:  OD {va_r or 'N/R'}  |  OS {va_l or 'N/R'}")
                            lines.append(f"    IOP: OD {iop_r or 'N/R'} mmHg  |  OS {iop_l or 'N/R'} mmHg")
                except Exception:
                    pass

                # Department-specific exam data (JSON)
                try:
                    dd = c.department_specific_data
                    if dd and isinstance(dd, dict):
                        exam_lines = []
                        for key, val in dd.items():
                            if val and str(val).strip() and str(val) not in ('None', '{}', '[]', ''):
                                label = key.replace('_', ' ').title()
                                exam_lines.append(f"      {label}: {val}")
                        if exam_lines:
                            lines.append("    Examination Findings:")
                            lines.extend(exam_lines[:20])  # cap at 20 fields
                except Exception:
                    pass

                # Diagnoses
                try:
                    diags = c.consultation_diagnoses.all()
                    if diags:
                        diag_strs = []
                        for cd in diags:
                            lat = f" ({cd.get_laterality_display()})" if cd.laterality and cd.laterality != 'BILATERAL' else ""
                            pri = " [PRIMARY]" if cd.is_primary else ""
                            diag_strs.append(f"{cd.diagnosis.icd10_code} {cd.diagnosis.description}{lat}{pri}")
                        lines.append(f"    Diagnoses:    {' | '.join(diag_strs)}")
                except Exception:
                    pass

                if c.management_plan:
                    lines.append(f"    Plan:         {c.management_plan[:300]}")
                if c.follow_up_date:
                    lines.append(f"    Follow-up:    {c.follow_up_date.strftime('%d %b %Y')}"
                                 + (f" — {c.follow_up_instructions[:100]}" if c.follow_up_instructions else ""))

                # Lab orders & results for this consultation
                try:
                    for lab in c.lab_orders.all():
                        items_info = []
                        for item in lab.items.all():
                            test_name = item.test_type.name
                            try:
                                r = item.result
                                flag = ' ⚠CRITICAL' if r.is_critical else (' ↑↓ABNORMAL' if r.is_abnormal else ' ✓NORMAL')
                                items_info.append(f"{test_name}: {r.result_value} {r.result_unit} (ref: {r.reference_range}){flag}")
                            except Exception:
                                items_info.append(f"{test_name}: pending")
                        if items_info:
                            lines.append(f"    Lab ({lab.get_status_display()}): {' | '.join(items_info)}")
                except Exception:
                    pass

                # Investigation results
                try:
                    for inv in c.investigation_orders.all():
                        inv_name = inv.investigation_type.name if inv.investigation_type else 'Investigation'
                        try:
                            res = inv.result
                            lines.append(f"    Investigation — {inv_name}: {getattr(res, 'findings', '') or getattr(res, 'result_summary', '') or 'Result recorded'}")
                        except Exception:
                            lines.append(f"    Investigation — {inv_name}: {inv.get_status_display()}")
                except Exception:
                    pass

    except Exception:
        pass

    # ── 6. OPTICAL PRESCRIPTIONS ──────────────────────────────────────────
    try:
        from apps.prescriptions.models import OpticalPrescription
        rxs = OpticalPrescription.objects.filter(
            patient=patient, is_deleted=False
        ).order_by('-prescription_date')[:8]
        if rxs.exists():
            lines.append("\n── OPTICAL PRESCRIPTIONS ──")
            for rx in rxs:
                lines.append(f"  [{rx.prescription_date.strftime('%d %b %Y')}] {rx.get_prescription_type_display()}"
                             + (" — Dispensed" if rx.is_dispensed else ""))
                def _sph(v):
                    if v is None: return 'Plano'
                    return f"+{v:.2f}" if v > 0 else f"{v:.2f}"
                lines.append(f"    OD: Sph {_sph(rx.re_sphere)}  Cyl {rx.re_cylinder or '—'}  "
                             f"Ax {rx.re_axis or '—'}  Add {'+'+str(rx.re_add) if rx.re_add else '—'}  VA {rx.re_visual_acuity or '—'}")
                lines.append(f"    OS: Sph {_sph(rx.le_sphere)}  Cyl {rx.le_cylinder or '—'}  "
                             f"Ax {rx.le_axis or '—'}  Add {'+'+str(rx.le_add) if rx.le_add else '—'}  VA {rx.le_visual_acuity or '—'}")
                if rx.lens_type:
                    lines.append(f"    Lens: {rx.lens_type}"
                                 + (f"  IPD: {rx.interpupillary_distance}mm" if rx.interpupillary_distance else ""))
    except Exception:
        pass

    # ── 7. DRUG PRESCRIPTIONS (with full dosage) ──────────────────────────
    try:
        from apps.prescriptions.models import DrugPrescription, DrugPrescriptionItem
        rxs = DrugPrescription.objects.filter(
            patient=patient, is_deleted=False
        ).order_by('-created_at')[:8]
        if rxs.exists():
            lines.append("\n── DRUG PRESCRIPTIONS ──")
            for rx in rxs:
                doc = rx.prescribed_by.get_full_name() if getattr(rx, 'prescribed_by', None) else ''
                lines.append(f"  [{rx.created_at.strftime('%d %b %Y')}]{' — Dr. ' + doc if doc else ''}")
                for item in DrugPrescriptionItem.objects.filter(prescription=rx):
                    parts = [f"• {item.drug_name}"]
                    if item.dosage: parts.append(item.dosage)
                    if item.frequency: parts.append(item.frequency)
                    if item.duration: parts.append(f"× {item.duration}")
                    if getattr(item, 'route', None): parts.append(item.route)
                    if getattr(item, 'instructions', None): parts.append(item.instructions)
                    lines.append(f"    {' — '.join(parts)}")
    except Exception:
        pass

    # ── 8. ALL LAB RESULTS (full history, deduplicated) ───────────────────
    try:
        from apps.laboratory.models import LabOrder
        all_lab_orders = LabOrder.objects.filter(
            patient=patient, is_deleted=False
        ).prefetch_related('items__result', 'items__test_type').order_by('-created_at')[:25]
        seen_results = set()
        lab_history = []
        for lab in all_lab_orders:
            date_str = lab.created_at.strftime('%d %b %Y')
            for item in lab.items.all():
                try:
                    r = item.result
                    uid = f"{item.test_type.name}_{r.result_date.date()}"
                    if uid in seen_results:
                        continue
                    seen_results.add(uid)
                    flag = ' ⚠CRITICAL' if r.is_critical else (' ↑↓ABNORMAL' if r.is_abnormal else ' ✓normal')
                    comment = f" — {r.comment}" if r.comment else ""
                    lab_history.append(
                        f"  [{date_str}] {item.test_type.name}: "
                        f"{r.result_value} {r.result_unit or ''} "
                        f"(ref: {r.reference_range or 'N/A'}){flag}{comment}"
                    )
                except Exception:
                    lab_history.append(f"  [{date_str}] {item.test_type.name}: pending")
        if lab_history:
            lines.append("\n── COMPLETE LAB HISTORY ──")
            lines.extend(lab_history)
    except Exception:
        pass

    # ── 9. ALL INVESTIGATION RESULTS (full structured data) ───────────────
    try:
        from apps.investigations.models import InvestigationOrder
        all_invs = InvestigationOrder.objects.filter(
            patient=patient, is_deleted=False, status='COMPLETED'
        ).select_related('investigation_type').prefetch_related('result').order_by('-created_at')[:20]
        inv_lines = []
        for inv in all_invs:
            inv_name = inv.investigation_type.name if inv.investigation_type else 'Investigation'
            eye = inv.get_eye_display()
            try:
                res = inv.result
                date_str = res.result_date.strftime('%d %b %Y') if res.result_date else 'Unknown date'
                normal_tag = ' ✓NORMAL' if res.is_normal else (' ABNORMAL' if res.is_normal is False else '')
                verified = ' [VERIFIED]' if res.is_verified else ''
                inv_lines.append(f"\n  [{date_str}] {inv_name} ({eye}){normal_tag}{verified}")
                inv_lines.append(f"    Indication: {inv.clinical_indication}")
                if res.interpretation:
                    inv_lines.append(f"    Interpretation: {res.interpretation[:500]}")
                if res.result_data and isinstance(res.result_data, dict):
                    import json as _json
                    for k, v in res.result_data.items():
                        if v and k != 'ai_analysis' and str(v).strip():
                            inv_lines.append(f"    {k.replace('_', ' ').title()}: {v}")
            except Exception:
                inv_lines.append(f"  {inv_name} ({eye}): {inv.get_status_display()}")
        if inv_lines:
            lines.append("\n── COMPLETE INVESTIGATION RESULTS ──")
            lines.extend(inv_lines)
    except Exception:
        pass

    # ── 10. IMAGING STUDIES (OCT, VF, FFA, Biometry, B-Scan, etc.) ────────
    try:
        from apps.investigations.models import ImagingStudy
        studies = ImagingStudy.objects.filter(
            patient=patient, is_deleted=False
        ).order_by('-study_date')[:20]
        study_lines = []
        for s in studies:
            date_str = s.study_date.strftime('%d %b %Y') if s.study_date else 'Unknown date'
            reported = ' [REPORTED]' if s.is_reported else ' [AWAITING REPORT]'
            study_lines.append(f"\n  [{date_str}] {s.get_modality_display()} — {s.description}{reported}")
            if s.report:
                study_lines.append(f"    Report: {s.report[:800]}")
            if s.series_count > 1:
                study_lines.append(f"    Series: {s.series_count}")
        if study_lines:
            lines.append("\n── IMAGING STUDIES ──")
            lines.extend(study_lines)
    except Exception:
        pass

    lines.append("\n" + "=" * 60)
    lines.append("END OF PATIENT RECORD")
    lines.append("=" * 60)
    return "\n".join(lines)


def patient_chat_response(patient_context, history, question):
    """
    Answer a clinical question about a specific patient using their chart as context.
    history: list of {'role': 'user'|'assistant', 'content': str}
    Returns {'success': bool, 'text': str, 'error': str}
    """
    chat_fn = _get_chat_fn()
    system_prompt = (
        OPHTHALMOLOGY_SYSTEM_PROMPT
        + "\n\n--- PATIENT CHART CONTEXT (this conversation only) ---\n"
        + patient_context
        + "\n\nYou are the clinical AI assistant for this patient. Answer questions about their "
          "medical history, diagnoses, medications and management based on the chart data above. "
          "Be concise and clinically precise. If information is not in the data, say so clearly."
    )
    messages = [h for h in history[-10:] if h.get('role') in ('user', 'assistant') and h.get('content')]
    messages.append({'role': 'user', 'content': question})
    try:
        return chat_fn(messages=messages, system=system_prompt, max_tokens=2048)
    except Exception as e:
        return {'success': False, 'error': str(e), 'text': ''}


def get_claude_response(conversation, user_message_text):
    """
    Send a message to the AI and return the response.
    Routes to Groq (testing) or Ollama (production) based on AI_ENGINE_REASONING.
    Returns (response_text, tokens_used, response_time_ms) tuple.
    """
    chat_fn = _get_chat_fn()

    # Build system prompt
    system_prompt = OPHTHALMOLOGY_SYSTEM_PROMPT
    if conversation.system_prompt:
        system_prompt += "\n" + conversation.system_prompt

    # Build message history
    prior_messages = conversation.messages.order_by('created_at')
    messages = []
    for msg in prior_messages:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": user_message_text})

    start_time = time.time()
    try:
        result = chat_fn(
            messages=messages,
            system=system_prompt,
            max_tokens=getattr(settings, 'AI_MAX_TOKENS', 2048),
        )
        elapsed_ms = int((time.time() - start_time) * 1000)
        if result['success']:
            tokens = result.get('usage', {}).get('prompt_tokens', 0) + result.get('usage', {}).get('completion_tokens', 0)
            return result['text'], tokens, elapsed_ms
        return f"AI error: {result.get('error', 'Unknown')}", 0, elapsed_ms
    except Exception as e:
        logger.exception('Unexpected AI error: %s', e)
        return f"An error occurred: {str(e)}", 0, 0


VIRTUAL_RECEPTIONIST_PROMPT = """You are a friendly and professional AI virtual receptionist for EyeCare Specialist Hospital, a specialist ophthalmology hospital in Cameroon.

Your role:
- Answer questions about hospital services (eye consultations, surgery, investigations, pharmacy, opticals)
- Provide general appointment information and guidance
- Explain what to expect during an eye examination
- Give general eye health information and awareness
- Direct patients to the right department or service
- Answer FAQs about eye conditions (cataracts, glaucoma, retina problems, spectacles)

Tone: Warm, professional, reassuring. Use simple language suitable for patients.
Always encourage patients to book an appointment for proper examination.
Do NOT give specific medical diagnoses — always recommend seeing a doctor.
Do NOT share any patient data or specific billing amounts.

Hospital services include:
- General Ophthalmology (routine eye checks, refractive errors, spectacles)
- Retina Clinic (diabetic eye disease, macular degeneration, retinal detachment)
- Glaucoma Clinic (glaucoma monitoring and treatment)
- Pediatric Eye Clinic (children's eye care, squint, amblyopia)
- Investigation Suite (OCT, visual fields, fundus photography, biometry)
- Laboratory (blood tests for pre-op and systemic conditions)
- Pharmacy (eye drops and medications)
- Opticals (spectacle frames, lenses, contact lenses)"""


def get_virtual_receptionist_response(user_message: str) -> str:
    """Get a response from the AI virtual receptionist."""
    try:
        chat_fn = _get_chat_fn()
        result = chat_fn(
            messages=[{"role": "user", "content": user_message}],
            system=VIRTUAL_RECEPTIONIST_PROMPT,
            max_tokens=512,
        )
        return result.get('text', "I'm sorry, I'm having trouble right now. Please contact our reception directly.")
    except Exception as e:
        logger.error(f"Virtual receptionist error: {e}")
        return "I'm sorry, I'm having trouble right now. Please contact our reception directly for assistance."


DIAGNOSIS_ASSIST_PROMPT = """You are a clinical decision support AI for an ophthalmology hospital in Cameroon. A clinician is asking for differential diagnosis assistance.

Given the patient's history and examination findings, provide:
1. Top 3 differential diagnoses (most likely first)
2. Key supporting and opposing features for each
3. Recommended immediate investigations
4. First-line management steps
5. ICD-10 codes for the top 2 differentials

Respond ONLY with valid JSON in this exact schema (no markdown, no explanation outside the JSON):
{
  "differentials": [
    {
      "rank": 1,
      "diagnosis": "...",
      "icd10": "...",
      "supporting": ["...", "..."],
      "against": ["..."],
      "confidence": "high|medium|low"
    }
  ],
  "investigations": ["...", "..."],
  "management": ["...", "..."],
  "red_flags": ["..."],
  "referral_urgency": "routine|urgent|emergency"
}

Be concise. Use proper medical terminology. Consider Cameroonian disease prevalence (high rates of glaucoma, onchocerciasis, trachoma, vitamin A deficiency, sickle cell retinopathy)."""


def suggest_diagnosis(chief_complaint: str, hpc: str = '', exam_summary: str = '',
                      age: str = '', gender: str = '') -> dict:
    """
    Suggest ophthalmic differential diagnoses.
    Routes to Groq or Ollama based on AI_ENGINE_REASONING setting.
    Returns a dict with keys: success, data (parsed JSON), error.
    """
    try:
        json_fn = _get_json_fn()

        parts = [f"Chief Complaint: {chief_complaint}"]
        if age or gender:
            parts.append(f"Patient: {age}yr {gender}".strip())
        if hpc:
            hpc_str = hpc if isinstance(hpc, str) else str(hpc)
            parts.append(f"History: {hpc_str[:400]}")
        if exam_summary:
            exam_str = exam_summary if isinstance(exam_summary, str) else str(exam_summary)
            parts.append(f"Examination Findings:\n{exam_str[:600]}")

        user_msg = "\n".join(parts)

        result = json_fn(
            messages=[{"role": "user", "content": user_msg}],
            system=DIAGNOSIS_ASSIST_PROMPT,
            max_tokens=1024,
        )

        if result['success']:
            return {'success': True, 'data': result['data']}
        return {'success': False, 'error': result.get('error', 'AI error')}

    except Exception as e:
        logger.exception('suggest_diagnosis error: %s', e)
        return {'success': False, 'error': str(e)}


def build_exam_context(exam_data: dict) -> str:
    """Format department_specific_data dict into readable exam summary for AI prompts."""
    if not exam_data:
        return ''
    lines = []

    # Visual Acuity
    va_re = exam_data.get('va_re_unaided') or exam_data.get('va_re_bcva')
    va_le = exam_data.get('va_le_unaided') or exam_data.get('va_le_bcva')
    if va_re or va_le:
        lines.append(f"VA: RE {va_re or 'N/R'} | LE {va_le or 'N/R'}")

    # IOP
    iop_re = exam_data.get('iop_re')
    iop_le = exam_data.get('iop_le')
    if iop_re or iop_le:
        lines.append(f"IOP: RE {iop_re or 'N/R'} | LE {iop_le or 'N/R'} mmHg")

    # Slit Lamp
    sl_fields = ['conjunctiva', 'cornea', 'anterior_chamber', 'iris', 'pupil', 'lens']
    sl_lines = []
    for f in sl_fields:
        re_val = exam_data.get(f'sl_{f}_re')
        le_val = exam_data.get(f'sl_{f}_le')
        if re_val or le_val:
            sl_lines.append(f"  {f.replace('_', ' ').title()}: RE={re_val or '-'} LE={le_val or '-'}")
    if sl_lines:
        lines.append("Slit Lamp:")
        lines.extend(sl_lines)

    # Fundoscopy
    fund_fields = [('disc', 'Optic Disc'), ('macula', 'Macula'),
                   ('periphery', 'Periphery'), ('vitreous', 'Vitreous')]
    fund_lines = []
    for key, label in fund_fields:
        re_val = exam_data.get(f'{key}_re')
        le_val = exam_data.get(f'{key}_le')
        if re_val or le_val:
            fund_lines.append(f"  {label}: RE={re_val or '-'} LE={le_val or '-'}")
    if fund_lines:
        lines.append("Fundoscopy:")
        lines.extend(fund_lines)

    # RAPD / Cover test
    for fld, label in [('rapd', 'RAPD'), ('cover_test', 'Cover Test'), ('color_vision', 'Colour Vision')]:
        if exam_data.get(fld):
            lines.append(f"{label}: {exam_data[fld]}")

    return "\n".join(lines)


ANALYTICS_AI_PROMPT = """You are an AI analytics assistant for hospital management at EyeCare Specialist Hospital.

You help medical directors and administrators understand:
- Patient volume trends and patterns
- Clinical outcome metrics
- Operational efficiency (wait times, throughput)
- Department performance comparisons
- Revenue and service utilization insights

When asked a question, provide:
1. A direct answer if data is provided
2. Insights and patterns you notice
3. Actionable recommendations for improvement
4. Benchmarks from ophthalmology best practices where relevant

Be concise, data-driven, and actionable. Format responses clearly with bullet points where appropriate."""


DRUG_INTERACTION_PROMPT = """You are a clinical pharmacology expert specialising in ophthalmic drugs for a hospital in Cameroon.

Given a list of drugs a patient is being prescribed, check for:
1. Clinically significant drug-drug interactions
2. Important ophthalmic-specific cautions (e.g. beta-blocker eye drops + systemic beta-blockers)
3. Contraindications for the listed drug forms (e.g. preserved drops in contact lens wearers)

Respond ONLY with valid JSON — no markdown, no text outside the JSON:
{
  "interactions": [
    {
      "drugs": ["Drug A", "Drug B"],
      "severity": "major|moderate|minor",
      "description": "...",
      "recommendation": "..."
    }
  ],
  "cautions": ["..."],
  "safe": true
}

If no interactions are found, return "interactions": [], "cautions": [], "safe": true.
Be concise. Focus on clinically relevant information for ophthalmology practice."""


def check_drug_interactions(drug_names: list) -> dict:
    """
    Check drug-drug interactions for a list of drug names using Groq.
    Returns dict with keys: success, data (parsed JSON), error.
    """
    if not drug_names:
        return {'success': True, 'data': {'interactions': [], 'cautions': [], 'safe': True}}
    try:
        from apps.ai_assistant.groq_client import groq_json

        drug_list = "\n".join(f"- {d}" for d in drug_names if d.strip())
        user_msg = f"Check interactions for the following drugs:\n{drug_list}"

        result = groq_json(
            messages=[{"role": "user", "content": user_msg}],
            system=DRUG_INTERACTION_PROMPT,
            max_tokens=512,
        )
        if result['success']:
            return {'success': True, 'data': result['data']}
        return {'success': False, 'error': result.get('error', 'AI error')}
    except Exception as e:
        logger.exception('check_drug_interactions error: %s', e)
        return {'success': False, 'error': str(e)}


def get_patient_risk_summary(patient) -> dict:
    """
    Generate an AI clinical risk summary for a patient using Groq.
    Returns dict with keys: success, data (dict with summary/risk_flags/follow_up_priority), error.
    """
    try:
        from apps.ai_assistant.groq_client import groq_json

        # Build patient context
        lines = [
            f"Patient: {patient.full_name}, Age {patient.age}, {patient.get_gender_display()}",
        ]

        # Medical history
        try:
            mh = patient.medical_history
            if mh.known_allergies:
                lines.append(f"Allergies: {mh.known_allergies}")
            if mh.chronic_conditions:
                lines.append(f"Chronic conditions: {mh.chronic_conditions}")
            if mh.current_medications:
                lines.append(f"Current medications: {mh.current_medications}")
            if mh.previous_eye_conditions:
                lines.append(f"Previous eye conditions: {mh.previous_eye_conditions}")
            if mh.previous_eye_surgeries:
                lines.append(f"Previous eye surgeries: {mh.previous_eye_surgeries}")
            if mh.family_ocular_history:
                lines.append(f"Family ocular history: {mh.family_ocular_history}")
        except Exception:
            pass

        # Recent consultations (last 3)
        try:
            from apps.consultations.models import Consultation
            recent = Consultation.objects.filter(
                patient=patient, is_deleted=False
            ).order_by('-created_at')[:3]
            for c in recent:
                lines.append(f"Visit ({c.created_at.strftime('%d %b %Y')}) — {c.department}: {c.presenting_complaint}")
                if c.primary_diagnosis:
                    lines.append(f"  Dx: {c.primary_diagnosis}")
        except Exception:
            pass

        prompt = (
            "Review this ophthalmology patient's record and respond with a JSON object containing:\n"
            "- summary: A 2-3 sentence clinical risk summary\n"
            "- risk_flags: A list of up to 5 key risk flags (e.g. 'Uncontrolled IOP', 'Diabetic retinopathy risk')\n"
            "- follow_up_priority: One of 'routine', '1 month', or 'urgent'\n\n"
            "Patient data:\n" + "\n".join(lines)
        )

        result = groq_json(
            messages=[{"role": "user", "content": prompt}],
            system=OPHTHALMOLOGY_SYSTEM_PROMPT,
            max_tokens=512,
        )

        if result['success']:
            return {'success': True, 'data': result['data']}
        return {'success': False, 'error': result.get('error', 'AI service error')}

    except Exception as e:
        logger.exception('get_patient_risk_summary error: %s', e)
        return {'success': False, 'error': str(e)}


def get_analytics_response(question: str, user) -> str:
    """Get an AI analytics response for a management question using Groq."""
    try:
        from apps.ai_assistant.groq_client import groq_chat

        context_lines = [f"Question from: {user.get_full_name()} ({user.role})"]

        try:
            from django.utils import timezone
            from django.db.models import Count
            from apps.patients.models import Patient
            from apps.appointments.models import Appointment
            from apps.consultations.models import Consultation
            today = timezone.localdate()
            week_ago = today - timezone.timedelta(days=7)
            month_ago = today - timezone.timedelta(days=30)

            total_patients = Patient.objects.filter(is_deleted=False).count()
            new_patients_month = Patient.objects.filter(is_deleted=False, created_at__date__gte=month_ago).count()
            today_appts = Appointment.objects.filter(appointment_date=today, is_deleted=False).count()
            week_appts = Appointment.objects.filter(appointment_date__gte=week_ago, is_deleted=False).count()

            dept_counts = (
                Consultation.objects.filter(is_deleted=False, created_at__date__gte=month_ago)
                .values('department__name')
                .annotate(n=Count('id'))
                .order_by('-n')[:8]
            )

            context_lines.append(f"Today: {today}")
            context_lines.append(f"Total registered patients: {total_patients}")
            context_lines.append(f"New patients (last 30 days): {new_patients_month}")
            context_lines.append(f"Today's appointments: {today_appts}")
            context_lines.append(f"Appointments last 7 days: {week_appts}")
            if dept_counts:
                dept_str = ", ".join(f"{r['department__name']}: {r['n']}" for r in dept_counts)
                context_lines.append(f"Consultations by dept (30d): {dept_str}")
        except Exception:
            pass

        full_question = "\n".join(context_lines) + "\n\nQuestion: " + question

        result = groq_chat(
            messages=[{"role": "user", "content": full_question}],
            system=ANALYTICS_AI_PROMPT,
            max_tokens=1024,
        )
        return result.get('text', 'Analytics AI is temporarily unavailable.')
    except Exception as e:
        logger.error(f"Analytics AI error: {e}")
        return f"Analytics AI encountered an error: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────
# AI TRIAGE SCORING
# ─────────────────────────────────────────────────────────────────────────────

AI_TRIAGE_PROMPT = """You are an expert ophthalmic triage nurse at a specialist eye hospital in Cameroon.

Score this patient's urgency from 1 to 5:
  1 = EMERGENCY — life/sight-threatening. Must be seen immediately.
  2 = URGENT — significant risk of vision loss. Seen within 1 hour.
  3 = SEMI-URGENT — active eye problem needing prompt attention. Seen within 2-3 hours.
  4 = ROUTINE — non-urgent eye complaint. Seen in normal queue.
  5 = NON-CLINICAL — admin/spectacle pick-up/follow-up with no active symptoms.

EMERGENCY triggers (auto score 1): sudden vision loss, chemical burn, penetrating injury,
  IOP >40 mmHg, acute angle closure, retinal detachment symptoms, amaurosis fugax.

URGENT triggers (score 2): VA worse than 6/60 either eye, uveitis flare, significant corneal problem,
  IOP 30-40 mmHg, recent trauma.

Respond ONLY with valid JSON — no markdown, no explanation:
{
  "priority": <1-5>,
  "label": "EMERGENCY|URGENT|SEMI-URGENT|ROUTINE|NON-CLINICAL",
  "reason": "<one concise sentence explaining the score>",
  "urgent_flags": ["<flag1>", "<flag2>"]
}"""


def ai_triage_score(
    chief_complaint: str,
    va_re: str = '',
    va_le: str = '',
    iop_re: str = '',
    iop_le: str = '',
    age: str = '',
    arrival_type: str = '',
) -> dict:
    """
    Score a patient's triage priority 1-5 using AI.
    Returns dict: { success, data: { priority, label, reason, urgent_flags }, error }
    """
    try:
        from apps.ai_assistant.groq_client import groq_json

        parts = [f"Chief Complaint: {chief_complaint}"]
        if age:
            parts.append(f"Age: {age}")
        if arrival_type:
            parts.append(f"Arrival type: {arrival_type}")
        if va_re or va_le:
            parts.append(f"Visual Acuity: RE={va_re or 'not measured'}, LE={va_le or 'not measured'}")
        if iop_re or iop_le:
            parts.append(f"IOP: RE={iop_re or 'not measured'}, LE={iop_le or 'not measured'} mmHg")

        user_msg = "\n".join(parts)

        result = groq_json(
            messages=[{"role": "user", "content": user_msg}],
            system=AI_TRIAGE_PROMPT,
            max_tokens=256,
        )
        if result['success']:
            return {'success': True, 'data': result['data']}
        return {'success': False, 'error': result.get('error', 'AI triage error')}
    except Exception as e:
        logger.exception('ai_triage_score error: %s', e)
        return {'success': False, 'error': str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# AI IMAGING / INVESTIGATION ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

AI_IMAGING_PROMPT = """You are an ophthalmic imaging specialist and clinical AI assistant for a specialist eye hospital in Cameroon.

Given clinical investigation findings, provide a structured analysis.

Respond ONLY with valid JSON — no markdown, no text outside the JSON:
{
  "key_findings": ["<finding1>", "<finding2>"],
  "severity": "normal|mild|moderate|severe",
  "likely_conditions": [
    { "condition": "...", "icd10": "...", "confidence": "high|medium|low" }
  ],
  "management_recommendations": ["<step1>", "<step2>"],
  "follow_up": "<recommended follow-up timeframe and action>",
  "confidence": 0.85
}

Consider Cameroonian disease prevalence: glaucoma, diabetic retinopathy, onchocerciasis,
sickle cell retinopathy, macular degeneration, cataract."""


def ai_analyze_investigation(investigation_type: str, eye: str, clinical_indication: str,
                              result_data: dict, interpretation: str = '') -> dict:
    """
    Run AI analysis on an investigation result.
    Returns dict: { success, data: { key_findings, severity, likely_conditions, ... }, error }
    """
    try:
        from apps.ai_assistant.groq_client import groq_json

        parts = [
            f"Investigation: {investigation_type}",
            f"Eye: {eye}",
            f"Clinical Indication: {clinical_indication}",
        ]
        if result_data:
            import json
            parts.append(f"Result Data:\n{json.dumps(result_data, indent=2)[:800]}")
        if interpretation:
            parts.append(f"Technician Interpretation: {interpretation[:400]}")

        user_msg = "\n".join(parts)

        result = groq_json(
            messages=[{"role": "user", "content": user_msg}],
            system=AI_IMAGING_PROMPT,
            max_tokens=768,
        )
        if result['success']:
            return {'success': True, 'data': result['data']}
        return {'success': False, 'error': result.get('error', 'AI imaging error')}
    except Exception as e:
        logger.exception('ai_analyze_investigation error: %s', e)
        return {'success': False, 'error': str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# AI SOAP NOTE GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

AI_SOAP_PROMPT = """You are a clinical documentation specialist for an ophthalmology hospital in Cameroon.

Convert raw dictated or typed clinical text into a structured SOAP note for an ophthalmology encounter.

Respond ONLY with valid JSON — no markdown, no text outside the JSON:
{
  "subjective": "<Chief complaint and history in patient's words, HPC, past history>",
  "objective": "<Examination findings — VA, IOP, slit lamp, fundus, special tests>",
  "assessment": "<Diagnosis or differential diagnoses with ICD-10 codes where possible>",
  "plan": "<Management plan, investigations ordered, prescriptions, follow-up, referrals>"
}

Keep clinical terminology. Be concise but complete. Preserve all clinically significant details."""


def ai_generate_soap_note(raw_text: str) -> dict:
    """
    Convert free-form clinical dictation into a structured SOAP note.
    Returns dict: { success, data: { subjective, objective, assessment, plan }, error }
    """
    try:
        from apps.ai_assistant.groq_client import groq_json

        result = groq_json(
            messages=[{"role": "user", "content": f"Convert this clinical text into a SOAP note:\n\n{raw_text[:2000]}"}],
            system=AI_SOAP_PROMPT,
            max_tokens=1024,
        )
        if result['success']:
            return {'success': True, 'data': result['data']}
        return {'success': False, 'error': result.get('error', 'SOAP generation error')}
    except Exception as e:
        logger.exception('ai_generate_soap_note error: %s', e)
        return {'success': False, 'error': str(e)}
