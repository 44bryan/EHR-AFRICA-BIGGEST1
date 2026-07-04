"""
Groq LLM Client — Deep reasoning for GLUDD EHR (DeepSeek-R1).

Architecture decision:
  PRIMARY:     Groq (llama-3.3-70b-versatile) — clinical reasoning,
               ophthalmology differential diagnosis, clinical decision support
  FAST:        Groq (llama-3.1-8b-instant) — receptionist, simple Q&A, quick lookups
  PRODUCTION:  Ollama (deepseek-r1:70b local GPU) — same model, zero API cost, on-premises

Why DeepSeek-R1?
  - Built-in chain-of-thought (think step-by-step before answering)
  - Significantly better at differential diagnosis and clinical reasoning than Llama
  - R1 distill on Llama-70b backbone — fast on Groq hardware
  - Free tier on Groq handles full CEO demo

How R1 works here:
  - Model emits <think>...</think> blocks internally for reasoning steps
  - We strip those from the final response shown to users
  - For diagnosis: we extract and surface the reasoning chain in the UI

Routing:
  llama-3.3-70b-versatile → Clinical chat, Diagnosis, Drug queries, Complex reasoning
  llama-3.1-8b-instant          → Receptionist, Analytics summary, Simple Q&A
"""
import re
import logging
from django.conf import settings

logger = logging.getLogger('apps.ai_assistant')

_THINK_RE = re.compile(r'<think>.*?</think>', re.DOTALL)


def _split_reasoning(raw: str) -> tuple[str, str]:
    """
    Extract DeepSeek-R1 chain-of-thought from the raw response.
    Returns (clean_answer, reasoning_chain).
    reasoning_chain is empty string for non-R1 models.
    """
    think_blocks = _THINK_RE.findall(raw)
    reasoning = '\n'.join(b[7:-8].strip() for b in think_blocks)  # strip <think></think>
    clean = _THINK_RE.sub('', raw).strip()
    return clean, reasoning

GLUDD_SYSTEM_PROMPT = """You are an AI clinical assistant embedded in GLUDD Specialist Eye Hospital's Electronic Health Record system in Cameroon.

You assist:
- Ophthalmologists: diagnosis support, management guidance, drug information
- Nurses: triage guidance, parameter interpretation
- Reception staff: patient queries, appointment information
- Management: analytics and hospital performance data

Context — GLUDD Eye Hospital, Cameroon:
- Specialist ophthalmology centre
- Departments: General Ophthalmology, Retina, Glaucoma, Cataract/Surgical, Cornea,
  Oculoplastics, Neuro-ophthalmology, Paediatric Ophthalmology, Refraction/Optometry
- Services: OPD, IPD, Theatre, Laboratory, Pharmacy, Optical Shop
- Patient tiers: Standard, Express, Fast Track, VIP
- Insurance accepted from CNPS, Activa, Sanlam, Allianz, AXA and others

Rules:
1. Clinical decisions always rest with qualified doctors — you support, not replace
2. Be concise and precise — doctors are busy
3. Use proper ophthalmic terminology
4. Flag emergencies prominently (sight-threatening, life-threatening)
5. Consider sub-Saharan African disease patterns and resource availability
6. Never fabricate drug doses — say "verify with current BNF/formulary"
"""


def get_groq_client():
    """Return a Groq client instance."""
    api_key = getattr(settings, 'GROQ_API_KEY', '')
    if not api_key or api_key == 'your-groq-api-key-here':
        return None
    try:
        from groq import Groq
        return Groq(api_key=api_key)
    except ImportError:
        logger.error("groq package not installed. Run: pip install groq")
        return None
    except Exception as e:
        logger.error(f"Groq client init error: {e}")
        return None


def groq_chat(messages: list, system: str = None, model: str = None, max_tokens: int = 2048) -> dict:
    """
    Send a chat request to Groq (DeepSeek-R1 by default).
    Returns: { success, text, reasoning, model, usage }
    - text     → clean answer with <think> blocks stripped
    - reasoning → the R1 chain-of-thought (empty for non-R1 models)
    """
    client = get_groq_client()
    if client is None:
        return {'success': False, 'error': 'Groq not configured. Add GROQ_API_KEY to .env', 'text': '', 'reasoning': ''}

    model = model or getattr(settings, 'GROQ_MODEL', 'llama-3.3-70b-versatile')
    system_prompt = system or GLUDD_SYSTEM_PROMPT

    try:
        chat_messages = [{'role': 'system', 'content': system_prompt}] + messages
        response = client.chat.completions.create(
            model=model,
            messages=chat_messages,
            max_tokens=max_tokens,
            temperature=0.6,  # R1 works better with slightly higher temp for reasoning
        )
        raw = response.choices[0].message.content or ''
        # Some Groq R1 responses put reasoning in a separate field
        reasoning_field = getattr(response.choices[0].message, 'reasoning_content', '') or ''
        text, reasoning_from_tags = _split_reasoning(raw)
        reasoning = reasoning_field or reasoning_from_tags
        return {
            'success': True,
            'text': text.strip(),
            'reasoning': reasoning.strip(),
            'model': response.model,
            'usage': {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
            }
        }
    except Exception as e:
        logger.error(f"Groq chat error (model={model}): {e}")
        # Fallback: retry with the fast model if the primary model fails
        fallback = getattr(settings, 'GROQ_FAST_MODEL', 'llama-3.3-70b-versatile')
        if model != fallback:
            logger.info(f"Retrying with fallback model {fallback}")
            try:
                chat_messages = [{'role': 'system', 'content': system_prompt}] + messages
                response = client.chat.completions.create(
                    model=fallback,
                    messages=chat_messages,
                    max_tokens=max_tokens,
                    temperature=0.3,
                )
                raw = response.choices[0].message.content or ''
                text, reasoning = _split_reasoning(raw)
                return {
                    'success': True,
                    'text': text.strip(),
                    'reasoning': '',
                    'model': response.model,
                    'usage': {
                        'prompt_tokens': response.usage.prompt_tokens,
                        'completion_tokens': response.usage.completion_tokens,
                    }
                }
            except Exception as e2:
                logger.error(f"Fallback model error: {e2}")
        return {'success': False, 'error': str(e), 'text': '', 'reasoning': ''}


def groq_json(messages: list, system: str = None, model: str = None, max_tokens: int = 2048) -> dict:
    """
    Request JSON output from Groq (uses JSON mode where supported).
    Falls back to plain text + regex parse if JSON mode is not supported by the model.
    Returns: { success, data (parsed dict), text, error }
    """
    import json, re as _re
    client = get_groq_client()
    if client is None:
        return {'success': False, 'error': 'Groq not configured', 'data': {}}

    model = model or getattr(settings, 'GROQ_MODEL', 'llama-3.3-70b-versatile')
    system_prompt = (system or GLUDD_SYSTEM_PROMPT) + '\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no explanation outside the JSON object.'
    chat_messages = [{'role': 'system', 'content': system_prompt}] + messages

    # Try with JSON mode first (supported by llama models)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=chat_messages,
            max_tokens=max_tokens,
            temperature=0.1,
            response_format={'type': 'json_object'},
        )
        raw = response.choices[0].message.content or ''
        text, _ = _split_reasoning(raw)
        data = json.loads(text)
        return {'success': True, 'data': data, 'text': text}
    except json.JSONDecodeError as e:
        logger.error(f"Groq JSON parse error: {e}")
        return {'success': False, 'error': 'JSON parse failed', 'data': {}}
    except Exception as e:
        err_str = str(e).lower()
        # JSON mode not supported by this model — retry without it
        if 'json' in err_str or 'response_format' in err_str or 'model' in err_str or 'deprecated' in err_str or 'decommissioned' in err_str:
            logger.warning(f"Groq JSON mode unsupported for model {model}, retrying without it: {e}")
            fallback_model = getattr(settings, 'GROQ_FAST_MODEL', 'llama-3.1-8b-instant')
            try:
                response = client.chat.completions.create(
                    model=fallback_model,
                    messages=chat_messages,
                    max_tokens=max_tokens,
                    temperature=0.1,
                    response_format={'type': 'json_object'},
                )
                raw = response.choices[0].message.content or ''
                text, _ = _split_reasoning(raw)
                data = json.loads(text)
                return {'success': True, 'data': data, 'text': text}
            except Exception as e2:
                logger.error(f"Groq JSON fallback error: {e2}")
                return {'success': False, 'error': str(e2), 'data': {}}
        logger.error(f"Groq JSON request error: {e}")
        return {'success': False, 'error': str(e), 'data': {}}


# ── Feature-specific functions ────────────────────────────────────────────────

def get_receptionist_response(user_message: str) -> str:
    """Virtual receptionist — answers patient queries about the hospital."""
    receptionist_system = """You are the friendly AI virtual receptionist at GLUDD Specialist Eye Hospital, Cameroon.

Answer patient and visitor queries about:
- Services offered (OPD, consultations, surgery, investigations, pharmacy, opticals)
- Patient tiers (Standard, Express, Fast Track, VIP) and what they mean
- How the queue system works — ticket at gate, called by cashier, then parameters, then doctor
- Hospital hours, location, appointments
- What to bring (referral letter, ID, insurance card, old records)
- Basic eye health questions (when to see a doctor urgently)

Tone: Warm, professional, clear. Use simple language — patients may not have medical backgrounds.
For clinical questions beyond your scope: "Please ask one of our doctors when you see them."
For emergencies: "Please go to our emergency desk immediately or call [number]."
"""
    result = groq_chat(
        messages=[{'role': 'user', 'content': user_message}],
        system=receptionist_system,
        model=getattr(settings, 'GROQ_FAST_MODEL', 'llama-3.1-8b-instant'),
        max_tokens=512,
    )
    return result.get('text', 'I apologize, the AI assistant is temporarily unavailable. Please speak with our reception staff.')


def get_analytics_response(question: str, hospital_data: dict) -> str:
    """Answer analytics questions about hospital data."""
    analytics_system = f"""You are a hospital analytics assistant for GLUDD Eye Hospital in Cameroon.

You have access to REAL-TIME hospital data pulled directly from the database RIGHT NOW:
{hospital_data}

CRITICAL RULES:
1. Answer ONLY from the data provided above. Do NOT guess or hallucinate numbers.
2. If the data does not contain the answer to the specific question, say clearly: "I do not have that specific data in the current report. The data I have covers: [list what you do have]."
3. Today is {hospital_data.get('today', 'unknown')}. Yesterday was {hospital_data.get('yesterday', 'unknown')}.
4. All patient counts are real figures from the live database.
5. Currency is FCFA (CFA franc). Revenue figures are in FCFA.

Answer the question directly with:
- The exact number from the data (if available)
- A brief context note if helpful
- Keep it under 120 words unless the question needs more detail.
"""
    result = groq_chat(
        messages=[{'role': 'user', 'content': question}],
        system=analytics_system,
        max_tokens=600,
    )
    return result.get('text', 'Analytics query could not be processed.')


def build_live_patient_context(conversation) -> str:
    """
    Build a fresh, complete patient context string from the database on every call.

    Why not use conversation.system_prompt?
    - system_prompt is a snapshot taken at conversation creation.
    - If the doctor records exam findings, diagnoses, or vitals AFTER opening
      the chat, the snapshot is already stale.
    - This function always reads the current DB state so the AI sees the
      full, up-to-date picture of what has actually been documented.

    Grounding rule: the returned string explicitly instructs the AI to treat
    undocumented data as unknown, preventing confabulation of patient-specific facts.
    """
    if not conversation:
        return ''

    patient = getattr(conversation, 'patient', None)
    consultation = getattr(conversation, 'consultation', None)

    # ── No patient context at all ─────────────────────────────────────────
    if not patient and not consultation:
        return ''

    if not patient and consultation:
        patient = consultation.patient

    lines = [
        '═══ PATIENT RECORD (live from EHR) ═══',
        f'Patient : {patient.full_name}',
        f'Age     : {getattr(patient, "age", "—")} years',
        f'Gender  : {patient.get_gender_display() if hasattr(patient, "get_gender_display") else "—"}',
        f'ID      : {patient.patient_id}',
    ]

    # Service tier if on today's visit
    try:
        from django.utils import timezone as _tz
        today = _tz.localdate()
        from apps.patients.models import Visit
        todays_visit = Visit.objects.filter(
            patient=patient, visit_date__date=today, is_deleted=False
        ).order_by('-visit_date').first()

        if todays_visit:
            lines.append(f'Tier    : {todays_visit.get_service_tier_display()}')
            lines.append(f'Visit # : {todays_visit.visit_number}')
            if todays_visit.chief_complaint:
                lines.append(f'Chief Complaint: {todays_visit.chief_complaint}')

            # Triage vitals — the most commonly hallucinated data
            vs = todays_visit.vital_signs or {}
            if vs:
                lines.append('\n── Triage Vitals ──')
                for key, label in [
                    ('visual_acuity_right', 'VA RE'),
                    ('visual_acuity_left',  'VA LE'),
                    ('visual_acuity_near_right', 'VA Near RE'),
                    ('visual_acuity_near_left',  'VA Near LE'),
                    ('intraocular_pressure_right', 'IOP RE'),
                    ('intraocular_pressure_left',  'IOP LE'),
                    ('blood_pressure', 'BP'),
                    ('pulse',          'Pulse'),
                    ('weight',         'Weight'),
                    ('height',         'Height'),
                    ('temperature',    'Temp'),
                ]:
                    val = vs.get(key, '')
                    if val:
                        lines.append(f'  {label}: {val}')
            else:
                lines.append('\n── Triage Vitals: NOT YET RECORDED ──')
    except Exception:
        pass

    # ── Current consultation (if linked) ─────────────────────────────────
    if consultation:
        lines.append(f'\n── Current Consultation ({consultation.department}) ──')
        if consultation.presenting_complaint:
            lines.append(f'Presenting Complaint: {consultation.presenting_complaint}')
        if consultation.history_of_presenting_complaint:
            lines.append(f'HPC: {consultation.history_of_presenting_complaint[:400]}')
        if consultation.ocular_history:
            lines.append(f'Ocular Hx: {consultation.ocular_history[:200]}')
        if consultation.systemic_history:
            lines.append(f'Systemic Hx: {consultation.systemic_history[:200]}')
        if consultation.drug_history:
            lines.append(f'Drug Hx: {consultation.drug_history[:200]}')

        # Examination findings
        exam = consultation.examination_findings or {}
        if any(v for v in exam.values() if v):
            lines.append('Examination:')
            va = exam.get('visual_acuity', {})
            if any(va.values()):
                lines.append(f'  VA: RE {va.get("right_unaided","—")} unaided / {va.get("right_best_corrected","—")} BCVA | LE {va.get("left_unaided","—")} unaided / {va.get("left_best_corrected","—")} BCVA')
            iop = exam.get('intraocular_pressure', {})
            if iop.get('right') or iop.get('left'):
                lines.append(f'  IOP: RE {iop.get("right","—")} | LE {iop.get("left","—")} mmHg ({iop.get("method","NCT")})')
            for seg in ('anterior_segment', 'posterior_segment'):
                s = exam.get(seg, {})
                if s.get('right') or s.get('left'):
                    label = 'Ant. Seg' if seg == 'anterior_segment' else 'Post. Seg'
                    lines.append(f'  {label}: RE: {s.get("right","—")} | LE: {s.get("left","—")}')

        # Dept-specific data
        dept_data = consultation.department_specific_data or {}
        if dept_data:
            lines.append('Dept-specific findings:')
            for k, v in dept_data.items():
                if v:
                    lines.append(f'  {k.replace("_"," ").title()}: {v}')

        # Diagnoses
        try:
            diagnoses = list(consultation.consultation_diagnoses.select_related('diagnosis').all())
            if diagnoses:
                lines.append('Diagnoses:')
                for cd in diagnoses:
                    flag = ' [PRIMARY]' if cd.is_primary else ''
                    lines.append(f'  • {cd.diagnosis.icd10_code} — {cd.diagnosis.description}{flag}')
        except Exception:
            pass

        if consultation.management_plan:
            lines.append(f'Management Plan: {consultation.management_plan[:300]}')

    # ── Previous consultations for this patient ───────────────────────────
    try:
        from apps.consultations.models import Consultation
        prev = Consultation.objects.filter(
            patient=patient, is_deleted=False
        ).exclude(
            pk=consultation.pk if consultation else None
        ).select_related('department').order_by('-consultation_date')[:5]

        if prev:
            lines.append('\n── Previous Consultations ──')
            for c in prev:
                dx = c.primary_diagnosis
                lines.append(
                    f'  {c.consultation_date:%d/%m/%Y} | {c.department} | '
                    f'CC: {c.presenting_complaint[:60]} | '
                    f'Dx: {dx or "—"}'
                )
    except Exception:
        pass

    lines.append('═══ END PATIENT RECORD ═══')

    return '\n'.join(lines)


def build_grounded_system(patient_context: str) -> str:
    """
    Combine the base GLUDD system prompt with live patient data and
    a hard grounding instruction to prevent hallucination.
    """
    grounding_rule = """
CRITICAL — ANTI-HALLUCINATION RULES:
1. Patient-specific data (VA, IOP, diagnoses, vitals, medications):
   • Only state what is explicitly documented in the PATIENT RECORD above.
   • If a field is blank or shows "NOT YET RECORDED" → say "not yet documented."
   • NEVER invent, estimate, or infer specific patient values from general knowledge.
2. General medical knowledge (disease mechanisms, drug actions, guidelines):
   • Answer freely from your medical training.
   • Clearly prefix with: "In general, ..." to distinguish from this patient's data.
3. If asked "What is this patient's VA/IOP/diagnosis?" and it is not in the record:
   → Reply: "That has not been recorded yet in today's visit."
4. Prescriptions and drug doses: always say "verify with current formulary."
"""
    if patient_context:
        return GLUDD_SYSTEM_PROMPT + grounding_rule + '\n' + patient_context
    return GLUDD_SYSTEM_PROMPT + grounding_rule


SYSTEM_KNOWLEDGE_PROMPT = """You are the Clinical AI Support assistant for GLUDD Specialist Eye Hospital, Cameroon.

Your role is to answer questions about:
- Ophthalmology clinical guidelines (AAO, NICE, WHO, ICO)
- Evidence-based management protocols for eye conditions
- Drug information, dosages, and interaction principles
- Surgical procedures and post-operative care standards
- ICD-10 coding for ophthalmic conditions
- Hospital systems, workflows, and operational best practices
- Medical education and training topics in ophthalmology
- Sub-Saharan African disease burden and public health context
- Hospital performance interpretation and clinical audit questions

Hospital context — GLUDD Eye Hospital, Cameroon:
- Departments: General Ophthalmology, Retina, Glaucoma, Cataract/Surgical, Cornea,
  Oculoplastics, Neuro-ophthalmology, Paediatric Ophthalmology, Paediatric Refraction,
  Refraction/Optometry, Low Vision, Laser
- Staff roles: Ophthalmologists, Refractionists, Nurses, Technicians, Cashiers, Reception
- Patient tiers: Standard, Express, Fast Track, VIP
- Investigations: OCT, Humphrey VF, Fundus Photography, B-scan, IOL Master, Topography

IMPORTANT: You answer from medical knowledge and hospital guidelines.
You do NOT have access to individual patient records in this mode.
If asked about a specific patient's data, explain: "This session is not linked to a patient
record. Please open AI Assistant from a patient's profile for patient-specific support."

Rules:
1. Be concise and clinically precise — cite guidelines where relevant
2. Use proper ophthalmic terminology
3. Flag sight-threatening and life-threatening emergencies prominently
4. Always note when drug doses should be verified with current formulary
5. Consider African disease patterns and resource availability
"""


def build_system_knowledge_prompt() -> str:
    """Return the system prompt for SYSTEM_KNOWLEDGE context conversations."""
    return SYSTEM_KNOWLEDGE_PROMPT


def suggest_diagnosis_groq(chief_complaint: str, exam_data: dict, history: str = '') -> dict:
    """
    Deep-reasoning diagnosis suggestion via DeepSeek-R1 on Groq.
    R1 thinks through differentials step-by-step before producing structured JSON.
    """
    system = """You are a specialist ophthalmology AI at GLUDD Eye Hospital.

Given clinical findings, provide differential diagnoses as JSON:
{
  "differentials": [
    {
      "rank": 1,
      "diagnosis": "Name",
      "icd10": "H00.0",
      "confidence": "high|moderate|low",
      "supporting": ["finding 1", "finding 2"],
      "against": ["finding against"],
      "next_step": "What to do next"
    }
  ],
  "red_flags": ["any urgent findings"],
  "referral_urgency": "routine|urgent|emergency",
  "suggested_investigations": ["OCT", "VF"],
  "management_summary": "Brief plan"
}

Provide 3-5 differentials ranked by likelihood. Be clinically precise."""

    content = f"""Chief Complaint: {chief_complaint}
History: {history}
Examination findings: {exam_data}

Provide differential diagnoses."""

    result = groq_json(
        messages=[{'role': 'user', 'content': content}],
        system=system,
        max_tokens=4096,  # R1 needs room for reasoning + JSON output
    )
    return result
