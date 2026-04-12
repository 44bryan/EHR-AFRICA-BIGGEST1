"""
Voice EMR - AI-first consultation flow for GLUDD Eye Hospital.

Architecture:
  1. Doctor speaks during / after examination (no typing required).
  2. Audio is sent to the backend → transcribed by Whisper (local, on-premises).
  3. Transcript → Claude AI extracts ALL structured clinical data.
  4. A "Review & Approve" panel shows the doctor EVERYTHING that was extracted.
  5. Doctor scans, makes minor edits if needed, clicks "Approve & Sign".
  6. All fields fill automatically — consultation, department exam, diagnoses,
     prescription items, investigation orders, and follow-up plan.

Whisper models (choose based on hardware):
  tiny   — fastest, lowest accuracy  (~75MB)
  base   — good balance              (~142MB)
  small  — recommended for demo      (~466MB)
  medium — high accuracy             (~1.5GB)
  large  — best, needs GPU           (~3GB)

For demo: 'base' works well on CPU.
For production (on-premises GPU server): 'medium' or 'large'.
"""
import json
import logging
import tempfile
import os
from django.conf import settings

logger = logging.getLogger(__name__)

# Whisper model size — override in settings.py with WHISPER_MODEL_SIZE
WHISPER_MODEL_SIZE = getattr(settings, 'WHISPER_MODEL_SIZE', 'base')

# Singleton model cache — loaded once, reused across requests
_whisper_model = None


def get_whisper_model():
    """Load faster-whisper model once and cache in memory."""
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            logger.info(f"Loading Whisper model: {WHISPER_MODEL_SIZE}")
            _whisper_model = WhisperModel(
                WHISPER_MODEL_SIZE,
                device='cpu',          # Change to 'cuda' if GPU available
                compute_type='int8',   # int8 = fast on CPU, no accuracy loss
            )
            logger.info("Whisper model loaded successfully.")
        except ImportError:
            logger.warning("faster-whisper not installed. Audio transcription disabled.")
            return None
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            return None
    return _whisper_model


def transcribe_audio_file(audio_file) -> dict:
    """
    Transcribe an uploaded audio file using faster-whisper.
    audio_file: Django InMemoryUploadedFile or similar file-like object.
    Returns: { success, text, language, duration_seconds }
    """
    model = get_whisper_model()
    if model is None:
        return {
            'success': False,
            'error': 'Whisper model not available. Install faster-whisper.',
            'text': ''
        }

    # Save to temp file (faster-whisper needs a file path)
    suffix = '.webm'
    if hasattr(audio_file, 'name'):
        ext = os.path.splitext(audio_file.name)[-1].lower()
        if ext in ['.wav', '.mp3', '.m4a', '.ogg', '.webm', '.mp4']:
            suffix = ext

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            for chunk in audio_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        segments, info = model.transcribe(
            tmp_path,
            beam_size=5,
            language=None,            # Auto-detect language (supports French, English, etc.)
            vad_filter=True,         # Remove silence
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        text = ' '.join(seg.text.strip() for seg in segments)
        return {
            'success': True,
            'text': text.strip(),
            'language': info.language,
            'duration_seconds': round(info.duration, 1),
        }
    except Exception as e:
        logger.error(f"Whisper transcription error: {e}")
        return {'success': False, 'error': str(e), 'text': ''}
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


VOICE_EMR_SYSTEM_PROMPT = """You are an expert clinical AI assistant embedded in an ophthalmology EHR for GLUDD Eye Hospital.

Your role: Doctors speak during or after examinations in English, French, or a mix of both. You listen, understand, and fill EVERY field in the consultation form so the doctor just reviews and approves — NO typing required.

The transcription may be in French, English, or code-switched. Always extract the clinical data and return the JSON in English regardless of the input language.

Extract ALL of the following from the transcription. Fill only what is mentioned; leave others blank.

Return ONLY valid JSON (no markdown, no explanation) matching this exact schema:

{
  "chief_complaint": "",
  "history_of_presenting_illness": "",
  "ocular_history": "",
  "systemic_history": "",
  "drug_history": "",
  "family_history": "",
  "allergies": "",

  "examination": {
    "va_re_unaided": "",
    "va_le_unaided": "",
    "va_re_ph": "",
    "va_le_ph": "",
    "va_re_bcva": "",
    "va_le_bcva": "",
    "va_re_near": "",
    "va_le_near": "",
    "iop_re": "",
    "iop_le": "",
    "iop_method": "",
    "cover_test": "",
    "rapd": "",
    "colour_vision": "",
    "anterior_segment": {
      "conjunctiva_re": "",
      "conjunctiva_le": "",
      "cornea_re": "",
      "cornea_le": "",
      "anterior_chamber_re": "",
      "anterior_chamber_le": "",
      "iris_re": "",
      "iris_le": "",
      "pupil_re": "",
      "pupil_le": "",
      "lens_re": "",
      "lens_le": ""
    },
    "posterior_segment": {
      "disc_re": "",
      "disc_le": "",
      "macula_re": "",
      "macula_le": "",
      "periphery_re": "",
      "periphery_le": "",
      "vitreous_re": "",
      "vitreous_le": ""
    },
    "refraction_re_sphere": "",
    "refraction_re_cyl": "",
    "refraction_re_axis": "",
    "refraction_le_sphere": "",
    "refraction_le_cyl": "",
    "refraction_le_axis": ""
  },

  "diagnoses": [
    {"eye": "RE", "diagnosis": "", "icd10": ""}
  ],
  "overall_diagnosis_summary": "",

  "management_plan": "",
  "follow_up_days": null,
  "follow_up_instructions": "",
  "referral_department": "",

  "prescriptions": [
    {
      "drug_name": "",
      "dose": "",
      "frequency": "",
      "duration": "",
      "route": "topical",
      "eye": "OU",
      "instructions": ""
    }
  ],

  "investigations_ordered": [""],
  "lab_tests_ordered": [""],

  "confidence": 0.0,
  "missing_fields": ["list of important missing items the doctor should complete"]
}

Rules:
- VA: use notation like 6/6, 6/9, 6/18, CF, HM, PL, NPL
- IOP: numeric mmHg values only (no units)
- anterior_segment: fill each structure (conjunctiva, cornea, anterior_chamber, iris, pupil, lens) separately for RE and LE
- posterior_segment: fill disc, macula, periphery, vitreous separately for RE and LE
- cover_test: "Orthophoric" / "Esotropia" / "Exotropia" / "Hypertropia" / "Normal"
- rapd: "None" / "RE present" / "LE present" / "Bilateral"
- colour_vision: "Normal" / "Reduced RE" / "Reduced LE" / "Reduced OU"
- Route options: topical, oral, subconjunctival, intravitreal, subtenon, IV, IM
- Eye options: RE, LE, OU
- follow_up_days: integer days from today (e.g. 30 for "review in a month")
- confidence: 0.0-1.0 rating of how complete the extracted data is
- If the doctor mentions a drug without full details, fill what you can and add to missing_fields
"""


VOICE_EMR_REFRACTION_PROMPT = """You are an expert optometry AI assistant at GLUDD Eye Hospital.
The refractionist has just dictated their findings. Extract ALL refraction data and return ONLY valid JSON.
The input may be in French, English, or both. Always return JSON in English.

Return ONLY valid JSON matching this exact schema:

{
  "chief_complaint": "",
  "history": "",
  "refraction": {
    "auto_sph_od": "", "auto_cyl_od": "", "auto_axis_od": "",
    "auto_sph_os": "", "auto_cyl_os": "", "auto_axis_os": "",
    "va_unaided_od": "", "va_unaided_os": "",
    "va_corrected_od": "", "va_corrected_os": "",
    "final_sph_od": "", "final_cyl_od": "", "final_axis_od": "",
    "final_sph_os": "", "final_cyl_os": "", "final_axis_os": "",
    "add_od": "", "add_os": "",
    "bcva_od": "", "bcva_os": "",
    "rx_sph_od": "", "rx_cyl_od": "", "rx_axis_od": "", "rx_add_od": "", "rx_prism_od": "", "rx_bcva_od": "",
    "rx_sph_os": "", "rx_cyl_os": "", "rx_axis_os": "", "rx_add_os": "", "rx_prism_os": "", "rx_bcva_os": "",
    "near_vision": "",
    "pd_dist_od": "", "pd_dist_os": "",
    "pd_near_od": "", "pd_near_os": "",
    "lens_type": "",
    "refraction_type": "",
    "rx_wear_schedule": "",
    "rx_frame": "",
    "rx_dispensing": "",
    "rx_remarks": ""
  },
  "management_plan": "",
  "follow_up_days": null,
  "follow_up_instructions": "",
  "confidence": 0.0,
  "missing_fields": []
}

Rules:
- VA: use notation like 6/6, 6/9, 6/18, CF, HM, PL, NPL or N5, N8 for near
- Sphere/Cyl: include sign, e.g. +1.50 or -2.25
- Axis: numeric only, 1-180
- Add power: e.g. +2.50
- Prism: e.g. 2Δ BI
- If doctor says "final prescription" or "Rx" fill rx_sph_od etc.; if "auto-ref" or "objective" fill auto_sph_od etc.
- If only one set of values mentioned, fill both auto AND rx with same values.
- lens_type: "Single Vision (Distance)" / "Single Vision (Near)" / "Bifocal" / "Progressive (PAL)" / "Contact Lens Rx"
- refraction_type: "Dry Refraction" / "Cycloplegic Refraction" / "Post-Cycloplegic"
- rx_wear_schedule: "Full-time wear" / "Distance only" / "Near / reading only" / "As needed"
- confidence: 0.0-1.0 based on completeness
"""

VOICE_EMR_TRIAGE_PROMPT = """You are a clinical triage AI at GLUDD Eye Hospital.
A triage nurse has dictated patient vitals and visual acuity. Extract ALL data and return ONLY valid JSON.
The input may be in French, English, or both. Always return JSON in English.

Return ONLY valid JSON matching this exact schema:

{
  "chief_complaint": "",
  "triage": {
    "va_re_unaided": "", "va_le_unaided": "",
    "va_re_ph": "", "va_le_ph": "",
    "va_re_near": "", "va_le_near": "",
    "iop_re": "", "iop_le": "",
    "blood_pressure_systolic": "", "blood_pressure_diastolic": "",
    "pulse": "", "temperature": "", "weight": "", "height": "",
    "blood_sugar": "", "spo2": "",
    "pain_score": ""
  },
  "triage_notes": "",
  "priority": "",
  "dispatch_department": "",
  "confidence": 0.0,
  "missing_fields": []
}

Rules:
- VA: 6/6, 6/9, CF, HM, PL, NPL, etc.
- IOP: mmHg numerics only
- BP: separate systolic and diastolic
- priority: "NORMAL" / "URGENT" / "EMERGENCY"
- dispatch_department: use the name as spoken (e.g. "General Ophthalmology", "Refraction", "Glaucoma")
- confidence: 0.0-1.0 based on completeness
"""


def get_prompt_for_dept(dept_code: str) -> str:
    """Return the correct AI system prompt for the given department code."""
    if dept_code in ('REFRAC', 'PEDS_REFRAC'):
        return VOICE_EMR_REFRACTION_PROMPT
    if dept_code == 'TRIAGE':
        return VOICE_EMR_TRIAGE_PROMPT
    return VOICE_EMR_SYSTEM_PROMPT


def transcribe_voice_to_consultation(text_transcription: str, dept_code: str = '') -> dict:
    """
    Takes a text transcription and extracts ALL consultation data using Groq.
    Returns structured JSON ready to fill every form field.
    """
    from .groq_client import groq_json
    prompt = get_prompt_for_dept(dept_code)
    result = groq_json(
        messages=[
            {
                'role': 'user',
                'content': (
                    "Extract all clinical data from this consultation voice note. "
                    "Fill every field you can identify.\n\n"
                    f"TRANSCRIPTION:\n{text_transcription}"
                )
            }
        ],
        system=prompt,
        max_tokens=4096,
    )
    if not result.get('success'):
        logger.error(f"Voice EMR extraction error: {result.get('error')}")
        return {'success': False, 'error': result.get('error', 'AI extraction failed. Please try again.'), 'data': {}}
    return {'success': True, 'data': result.get('data', {})}


def apply_voice_data_to_consultation(consultation, voice_data: dict) -> dict:
    """
    AI-first consultation fill: applies ALL extracted voice data to consultation.
    Covers history, examination, dept-specific fields, diagnosis, plan,
    prescriptions, investigations, and follow-up.
    Returns a summary of every field applied.
    """
    applied = []

    # ── History fields ────────────────────────────────────────────────────
    text_fields = {
        'chief_complaint':              ('chief_complaint', 'Chief Complaint'),
        'history_of_presenting_illness':('history_of_presenting_illness', 'HPC'),
        'ocular_history':               ('ocular_history', 'Ocular History'),
        'systemic_history':             ('systemic_history', 'Systemic History'),
        'drug_history':                 ('drug_history', 'Drug History'),
        'family_history':               ('family_history', 'Family History'),
        'management_plan':              ('management_plan', 'Management Plan'),
        'follow_up_instructions':       ('follow_up_instructions', 'Follow-up Instructions'),
    }
    for key, (field, label) in text_fields.items():
        value = voice_data.get(key, '').strip()
        if value and hasattr(consultation, field):
            setattr(consultation, field, value)
            applied.append(label)

    # ── Follow-up date ────────────────────────────────────────────────────
    follow_up_days = voice_data.get('follow_up_days')
    if follow_up_days and hasattr(consultation, 'follow_up_date'):
        from datetime import date, timedelta
        consultation.follow_up_date = date.today() + timedelta(days=int(follow_up_days))
        applied.append(f'Follow-up date (+{follow_up_days} days)')

    # ── Examination findings → dept_specific_data (ophthalmology fields) ─
    exam = voice_data.get('examination', {})
    dept = consultation.department_specific_data or {}

    exam_map = {
        'va_re_unaided':       'va_re_unaided',
        'va_le_unaided':       'va_le_unaided',
        'va_re_ph':            'va_re_ph',
        'va_le_ph':            'va_le_ph',
        'va_re_bcva':          'va_re_bcva',
        'va_le_bcva':          'va_le_bcva',
        'va_re_near':          'va_re_near',
        'va_le_near':          'va_le_near',
        'iop_re':              'iop_re',
        'iop_le':              'iop_le',
        'iop_method':          'iop_method',
        'anterior_segment_re': 'slamp_re_anterior',
        'anterior_segment_le': 'slamp_le_anterior',
        'posterior_segment_re':'fundus_re_disc',
        'posterior_segment_le':'fundus_le_disc',
        'cover_test':          'cover_test',
        'rapd':                'rapd',
        'colour_vision':       'colour_vision',
        'refraction_re_sphere':'rx_re_sphere',
        'refraction_re_cyl':   'rx_re_cyl',
        'refraction_re_axis':  'rx_re_axis',
        'refraction_le_sphere':'rx_le_sphere',
        'refraction_le_cyl':   'rx_le_cyl',
        'refraction_le_axis':  'rx_le_axis',
    }
    for src_key, dest_key in exam_map.items():
        val = exam.get(src_key, '').strip() if isinstance(exam.get(src_key), str) else ''
        if val:
            dept[dest_key] = val
            applied.append(src_key.replace('_', ' ').title())

    # Overall diagnosis summary
    overall = voice_data.get('overall_diagnosis_summary', '').strip()
    if overall:
        dept['diagnosis_summary'] = overall
        applied.append('Overall Diagnosis Summary')

    consultation.department_specific_data = dept

    # ── Save consultation ─────────────────────────────────────────────────
    consultation.save()

    # ── Prescription items (return for display — doctor approves before saving) ─
    prescriptions = voice_data.get('prescriptions', [])
    cleaned_rx = [p for p in prescriptions if p.get('drug_name', '').strip()]

    # ── Investigation + lab orders (returned for display) ─────────────────
    investigations = [i for i in voice_data.get('investigations_ordered', []) if i.strip()]
    lab_tests = [l for l in voice_data.get('lab_tests_ordered', []) if l.strip()]

    return {
        'applied': applied,
        'count': len(applied),
        'pending_prescriptions': cleaned_rx,
        'pending_investigations': investigations,
        'pending_lab_tests': lab_tests,
        'missing_fields': voice_data.get('missing_fields', []),
        'confidence': voice_data.get('confidence', 0.0),
    }
