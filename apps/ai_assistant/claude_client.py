"""
Claude API client for the EHR AI Assistant.
Builds context-aware prompts from patient/consultation data.
"""
import time
import logging
from django.conf import settings

logger = logging.getLogger('apps.ai_assistant')

OPHTHALMOLOGY_SYSTEM_PROMPT = """You are an AI clinical decision support assistant embedded in an Electronic Health Record system for a specialist ophthalmology hospital in Cameroon.

Your role is to assist qualified ophthalmologists and medical staff with:
- Differential diagnosis suggestions for ophthalmic presentations
- Clinical management guidance based on current evidence
- Drug information (especially ophthalmic drugs — eye drops, intravitreal agents)
- Interpretation of investigation results (OCT, visual fields, fundus findings)
- ICD-10 coding assistance for ophthalmic diagnoses
- Ophthalmic surgical planning information
- Paediatric ophthalmology guidance
- Glaucoma and retinal disease management

IMPORTANT DISCLAIMERS:
1. You are a clinical decision SUPPORT tool. All clinical decisions must be made by qualified medical professionals.
2. Never contradict a treating physician's direct clinical judgment.
3. Always recommend verification against current clinical guidelines.
4. For emergency situations, recommend immediate clinical attention.
5. You do not have access to real-time drug databases — always verify drug interactions with current resources.

RESPONSE FORMAT:
- Be concise and clinically precise
- Use proper medical terminology
- Structure responses with clear headings when appropriate
- Cite evidence levels when making recommendations (e.g., Grade A, B, C)
- Flag important red-flag symptoms or emergency situations prominently

You are operating in an African hospital context (Cameroon) — consider local disease prevalence, available treatments, and resource limitations where relevant."""


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


def get_claude_response(conversation, user_message_text):
    """
    Send a message to the AI and return the response via Groq.
    Returns (response_text, tokens_used, response_time_ms) tuple.
    """
    from apps.ai_assistant.groq_client import groq_chat

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
        result = groq_chat(
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
        from apps.ai_assistant.groq_client import groq_chat
        result = groq_chat(
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
    Suggest ophthalmic differential diagnoses using Groq.
    Returns a dict with keys: success, data (parsed JSON), error.
    """
    try:
        from apps.ai_assistant.groq_client import groq_json

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

        result = groq_json(
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
