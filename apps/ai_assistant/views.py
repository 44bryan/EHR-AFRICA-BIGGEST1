import json
import logging
from django.contrib.auth.decorators import login_required

logger = logging.getLogger(__name__)
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from .models import AIConversation, AIMessage, ContextType
from .claude_client import get_claude_response, suggest_diagnosis, build_exam_context, check_drug_interactions, get_patient_risk_summary


@login_required
def ai_home_view(request):
    if not request.user.can_use_ai_assistant():
        return HttpResponseForbidden()

    conversations = AIConversation.objects.filter(
        user=request.user,
        is_active=True,
        is_deleted=False,
    ).order_by('-created_at')[:20]

    return render(request, 'ai_assistant/home.html', {
        'conversations': conversations,
        'context_types': ContextType.choices,
    })


@login_required
def new_conversation_view(request):
    if not request.user.can_use_ai_assistant():
        return HttpResponseForbidden()

    consultation_id = request.GET.get('consultation')
    patient_id = request.GET.get('patient')
    context_type = request.GET.get('context_type', ContextType.GENERAL)

    consultation = None
    patient = None

    if consultation_id:
        from apps.consultations.models import Consultation
        try:
            consultation = Consultation.objects.get(pk=consultation_id)
            patient = consultation.patient
        except Consultation.DoesNotExist:
            pass
    elif patient_id:
        from apps.patients.models import Patient
        try:
            patient = Patient.objects.get(patient_id=patient_id)
        except Patient.DoesNotExist:
            pass

    # system_prompt is intentionally left blank — live context is rebuilt on
    # every message in send_message_view so the AI always sees the current record.
    conversation = AIConversation.objects.create(
        user=request.user,
        patient=patient,
        consultation=consultation,
        context_type=context_type,
        system_prompt='',
        created_by=request.user,
    )

    return redirect('ai_assistant:conversation', pk=conversation.pk)


@login_required
def conversation_view(request, pk):
    if not request.user.can_use_ai_assistant():
        return HttpResponseForbidden()

    conversation = get_object_or_404(AIConversation, pk=pk, user=request.user)
    messages_qs = conversation.messages.order_by('created_at')

    return render(request, 'ai_assistant/conversation.html', {
        'conversation': conversation,
        'chat_messages': messages_qs,
        'context_types': ContextType.choices,
    })


@login_required
@require_POST
def send_message_view(request, pk):
    if not request.user.can_use_ai_assistant():
        return JsonResponse({'error': 'Permission denied'}, status=403)

    conversation = get_object_or_404(AIConversation, pk=pk, user=request.user)

    try:
        data = json.loads(request.body)
        user_text = data.get('message', '').strip()
    except json.JSONDecodeError:
        user_text = request.POST.get('message', '').strip()

    if not user_text:
        return JsonResponse({'error': 'Empty message'}, status=400)

    try:
        import time as _time
        from .groq_client import groq_chat, GLUDD_SYSTEM_PROMPT

        # Save user message
        AIMessage.objects.create(
            conversation=conversation,
            role=AIMessage.Role.USER,
            content=user_text,
        )

        _start = _time.time()

        # Build conversation history for Groq
        # Django QuerySets don't support negative indexing — evaluate to list first
        all_msgs = list(conversation.messages.order_by('created_at'))
        history = [{'role': m.role, 'content': m.content} for m in all_msgs[:-1]]
        history.append({'role': 'user', 'content': user_text})

        # Choose system prompt based on conversation context type.
        # SYSTEM_KNOWLEDGE → general hospital / guideline knowledge, no patient data.
        # All other types → grounded patient record (anti-hallucination architecture).
        from .models import ContextType as _CT
        from .groq_client import (
            build_live_patient_context, build_grounded_system, build_system_knowledge_prompt
        )
        if conversation.context_type == _CT.SYSTEM_KNOWLEDGE:
            system = build_system_knowledge_prompt()
        else:
            patient_ctx = build_live_patient_context(conversation)
            system = build_grounded_system(patient_ctx)
        result = groq_chat(messages=history, system=system, max_tokens=2048)

        if result['success']:
            response_text = result['text'] or '(No response from AI — please try again)'
            reasoning = result.get('reasoning', '')
            tokens_used = result.get('usage', {}).get('completion_tokens', 0)
            model_name = result.get('model', 'llama-3.3-70b-versatile')
        else:
            response_text = f"AI assistant error: {result.get('error', 'Unknown error')}. Please try again."
            reasoning = ''
            tokens_used = 0
            model_name = 'groq-unavailable'

        response_time_ms = int((_time.time() - _start) * 1000)

        ai_msg = AIMessage.objects.create(
            conversation=conversation,
            role=AIMessage.Role.ASSISTANT,
            content=response_text,
            tokens_used=tokens_used,
            model_used=model_name,
            response_time_ms=response_time_ms,
        )

        if not conversation.title and conversation.messages.count() <= 2:
            conversation.title = user_text[:80]
            conversation.save(update_fields=['title'])

        return JsonResponse({
            'message': response_text,
            'reasoning': reasoning,
            'message_id': str(ai_msg.id),
            'tokens_used': tokens_used,
            'response_time_ms': response_time_ms,
        })

    except Exception as e:
        import logging
        logging.getLogger('apps.ai_assistant').exception('send_message_view error: %s', e)
        return JsonResponse({'error': f'Server error: {e}. Please try again.'}, status=500)


@login_required
@require_POST
def clear_conversation_view(request, pk):
    conversation = get_object_or_404(AIConversation, pk=pk, user=request.user)
    conversation.messages.all().delete()
    conversation.title = ''
    conversation.save(update_fields=['title'])
    messages.success(request, 'Conversation cleared.')
    return redirect('ai_assistant:conversation', pk=pk)


@login_required
@require_POST
def voice_extract_view(request):
    """
    Stateless Voice EMR extraction endpoint — no consultation ID required.
    Used on the NEW consultation create page (consultation doesn't exist yet).

    Accepts: audio file (Whisper) OR text transcription (browser Web Speech API)
    Returns: structured JSON extraction the frontend uses to fill form inputs.
    """
    if not request.user.can_use_ai_assistant():
        return JsonResponse({'error': 'Permission denied'}, status=403)

    from .voice_emr import transcribe_audio_file, transcribe_voice_to_consultation

    transcription = ''
    whisper_meta = None

    audio_file = request.FILES.get('audio')
    if audio_file:
        whisper_result = transcribe_audio_file(audio_file)
        if not whisper_result['success']:
            return JsonResponse({'error': whisper_result['error']}, status=500)
        transcription = whisper_result['text']
        whisper_meta = {
            'language': whisper_result.get('language', 'en'),
            'duration_seconds': whisper_result.get('duration_seconds', 0),
        }
    else:
        try:
            body = json.loads(request.body)
            transcription = body.get('transcription', '').strip()
            dept_code_from_body = body.get('dept_code', '').strip()
        except json.JSONDecodeError:
            transcription = request.POST.get('transcription', '').strip()
            dept_code_from_body = request.POST.get('dept_code', '').strip()

    if not transcription:
        return JsonResponse({'error': 'No audio or transcription provided.'}, status=400)

    # Determine dept_code: prefer what frontend sends, fallback to user's dept
    dept_code = dept_code_from_body or request.user.role_department_code or ''

    result = transcribe_voice_to_consultation(transcription, dept_code=dept_code)
    if not result['success']:
        return JsonResponse({'error': result['error']}, status=500)

    data = result['data']
    data['_dept_code'] = dept_code  # echo back so JS knows which schema was used

    response_data = {
        'success': True,
        'transcription': transcription,
        'data': data,
    }
    if whisper_meta:
        response_data['whisper'] = whisper_meta
    return JsonResponse(response_data)


@login_required
@require_POST
def voice_transcribe_view(request, consultation_id):
    """
    AI-first consultation voice endpoint.

    Accepts EITHER:
      a) An uploaded audio file  → Whisper transcribes → Claude extracts
      b) A text transcription    → Claude extracts directly

    Returns full structured extraction for the doctor to review.
    Doctor then calls voice_approve_view to apply everything.
    """
    if not request.user.can_use_ai_assistant():
        return JsonResponse({'error': 'Permission denied'}, status=403)

    from apps.consultations.models import Consultation
    from .voice_emr import transcribe_audio_file, transcribe_voice_to_consultation

    consultation = get_object_or_404(Consultation, pk=consultation_id)
    transcription = ''

    # ── Path A: audio file upload (Whisper) ───────────────────────────────
    audio_file = request.FILES.get('audio')
    if audio_file:
        whisper_result = transcribe_audio_file(audio_file)
        if not whisper_result['success']:
            return JsonResponse({'error': whisper_result['error']}, status=500)
        transcription = whisper_result['text']
        whisper_meta = {
            'language': whisper_result.get('language', 'en'),
            'duration_seconds': whisper_result.get('duration_seconds', 0),
        }
    else:
        # ── Path B: text from browser Web Speech API ──────────────────────
        try:
            body = json.loads(request.body)
            transcription = body.get('transcription', '').strip()
        except json.JSONDecodeError:
            transcription = request.POST.get('transcription', '').strip()
        whisper_meta = None

    if not transcription:
        return JsonResponse({'error': 'No audio or transcription provided.'}, status=400)

    # ── Claude extraction ─────────────────────────────────────────────────
    result = transcribe_voice_to_consultation(transcription)
    if not result['success']:
        return JsonResponse({'error': result['error']}, status=500)

    data = result['data']

    # Filter missing_fields to only show fields relevant for this doctor's role
    dept_code = getattr(consultation.department, 'code', '') if consultation.department else ''
    if dept_code in ('REFRAC', 'PEDS_REFRAC'):
        _not_refrac = {
            'anterior segment', 'posterior segment', 'iop', 'intraocular pressure',
            'cover test', 'rapd', 'colour vision', 'color vision',
            'slit lamp', 'fundus', 'fundoscopy', 'adnexa',
        }
        data['missing_fields'] = [
            f for f in data.get('missing_fields', [])
            if not any(kw in f.lower() for kw in _not_refrac)
        ]

    response_data = {
        'success': True,
        'transcription': transcription,
        'data': data,
        'consultation_id': str(consultation_id),
    }
    if whisper_meta:
        response_data['whisper'] = whisper_meta

    return JsonResponse(response_data)


@login_required
@require_POST
def voice_approve_view(request, consultation_id):
    """
    Doctor reviewed the AI extraction and clicked 'Approve & Sign'.
    Applies all extracted data to the consultation immediately.
    Also creates prescription items and investigation orders if approved.
    """
    if not request.user.can_use_ai_assistant():
        return JsonResponse({'error': 'Permission denied'}, status=403)

    from apps.consultations.models import Consultation
    from .voice_emr import apply_voice_data_to_consultation

    consultation = get_object_or_404(Consultation, pk=consultation_id)

    try:
        body = json.loads(request.body)
        voice_data = body.get('data', {})
        approve_prescriptions = body.get('approve_prescriptions', False)
        approve_investigations = body.get('approve_investigations', False)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    if not voice_data:
        return JsonResponse({'error': 'No data to apply'}, status=400)

    apply_result = apply_voice_data_to_consultation(consultation, voice_data)

    created_rx = []
    if approve_prescriptions and apply_result.get('pending_prescriptions'):
        created_rx = _create_prescriptions_from_voice(
            consultation, apply_result['pending_prescriptions'], request.user
        )

    created_inv = []
    if approve_investigations and apply_result.get('pending_investigations'):
        created_inv = _create_investigations_from_voice(
            consultation, apply_result['pending_investigations'], request.user
        )

    return JsonResponse({
        'success': True,
        'fields_applied': apply_result['applied'],
        'fields_count': apply_result['count'],
        'prescriptions_created': created_rx,
        'investigations_created': created_inv,
        'missing_fields': apply_result.get('missing_fields', []),
        'confidence': apply_result.get('confidence', 0.0),
        'message': (
            f"{apply_result['count']} fields filled automatically. "
            + (f"{len(created_rx)} prescription(s) created. " if created_rx else '')
            + (f"{len(created_inv)} investigation(s) ordered. " if created_inv else '')
        )
    })


def _create_prescriptions_from_voice(consultation, rx_list, user):
    """Create PrescriptionItem records from AI-extracted prescription data."""
    created = []
    try:
        from apps.prescriptions.models import DrugPrescription, PrescriptionItem
        # Get or create a drug prescription for this consultation
        drug_rx, _ = DrugPrescription.objects.get_or_create(
            consultation=consultation,
            defaults={
                'patient': consultation.patient,
                'prescriber': user,
                'status': 'DRAFT',
            }
        )
        for item in rx_list:
            if item.get('drug_name'):
                PrescriptionItem.objects.create(
                    prescription=drug_rx,
                    drug_name=item.get('drug_name', ''),
                    dose=item.get('dose', ''),
                    frequency=item.get('frequency', ''),
                    duration=item.get('duration', ''),
                    route=item.get('route', 'topical'),
                    eye=item.get('eye', 'OU'),
                    instructions=item.get('instructions', ''),
                )
                created.append(item['drug_name'])
    except Exception as e:
        logger.error(f"Voice prescription creation error: {e}")
    return created


def _create_investigations_from_voice(consultation, inv_list, user):
    """Create InvestigationOrder records from AI-extracted investigation orders."""
    created = []
    try:
        from apps.investigations.models import InvestigationOrder, InvestigationType
        for inv_name in inv_list:
            inv_name = inv_name.strip()
            if not inv_name:
                continue
            inv_type = InvestigationType.objects.filter(
                name__icontains=inv_name.split()[0]
            ).first()
            InvestigationOrder.objects.create(
                consultation=consultation,
                patient=consultation.patient,
                investigation_type=inv_type,
                custom_name=inv_name if not inv_type else '',
                ordered_by=user,
                status='PENDING',
            )
            created.append(inv_name)
    except Exception as e:
        logger.error(f"Voice investigation creation error: {e}")
    return created


@login_required
def virtual_receptionist_view(request):
    """AI Virtual Receptionist — answers patient queries about services, hours, appointments."""
    if not request.user.can_use_ai_assistant():
        return JsonResponse({'error': 'Permission denied'}, status=403)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_message = data.get('message', '').strip()
        except json.JSONDecodeError:
            user_message = request.POST.get('message', '').strip()

        if not user_message:
            return JsonResponse({'error': 'Empty message'}, status=400)

        # Use Groq (fast) for receptionist — fallback to Claude
        engine = getattr(__import__('django.conf', fromlist=['settings']).settings, 'AI_ENGINE_REASONING', 'groq')
        if engine == 'groq':
            from .groq_client import get_receptionist_response
            response = get_receptionist_response(user_message)
        else:
            from .claude_client import get_virtual_receptionist_response
            response = get_virtual_receptionist_response(user_message)
        return JsonResponse({'response': response})

    return render(request, 'ai_assistant/virtual_receptionist.html')


@login_required
@require_POST
def suggest_diagnosis_view(request):
    """
    AI Diagnosis Assistant — given CC + exam findings, returns differential diagnoses as JSON.
    POST body: { chief_complaint, hpc, exam_data (dict), consultation_pk (optional) }
    """
    if not request.user.can_use_ai_assistant():
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    chief_complaint = data.get('chief_complaint', '').strip()
    if not chief_complaint:
        return JsonResponse({'error': 'chief_complaint is required'}, status=400)

    hpc = data.get('hpc', '')
    exam_data = data.get('exam_data', {})
    age = str(data.get('age', ''))
    gender = str(data.get('gender', ''))

    # If a consultation PK is provided, enrich context from the saved record
    consultation_pk = data.get('consultation_pk')
    if consultation_pk:
        from apps.consultations.models import Consultation
        try:
            consultation = Consultation.objects.get(pk=consultation_pk)
            if not hpc and consultation.history_of_presenting_complaint:
                hpc = consultation.history_of_presenting_complaint
            if not age:
                age = str(consultation.patient.age)
            if not gender:
                gender = consultation.patient.get_gender_display()
            if not exam_data and consultation.department_specific_data:
                exam_data = consultation.department_specific_data
        except Consultation.DoesNotExist:
            pass

    exam_summary = build_exam_context(exam_data) if isinstance(exam_data, dict) else ''

    # Use Groq for diagnosis suggestions (fast) — fallback to Claude
    from django.conf import settings as django_settings
    engine = getattr(django_settings, 'AI_ENGINE_REASONING', 'groq')
    if engine == 'groq':
        from .groq_client import suggest_diagnosis_groq
        result = suggest_diagnosis_groq(chief_complaint, exam_data, history=hpc)
    else:
        result = suggest_diagnosis(chief_complaint, hpc=hpc, exam_summary=exam_summary,
                                   age=age, gender=gender)

    if result['success']:
        return JsonResponse({'success': True, 'data': result['data']})
    return JsonResponse({'success': False, 'error': result.get('error', 'AI error')}, status=500)


@login_required
def patient_risk_summary_view(request, patient_id):
    """AI clinical risk summary for a patient. GET returns JSON."""
    if not request.user.can_use_ai_assistant():
        return JsonResponse({'error': 'Permission denied'}, status=403)

    from apps.patients.models import Patient
    patient = get_object_or_404(Patient, patient_id=patient_id, is_deleted=False)
    result = get_patient_risk_summary(patient)
    if result['success']:
        return JsonResponse({'success': True, 'data': result['data']})
    return JsonResponse({'success': False, 'error': result['error']}, status=500)


@login_required
@require_POST
def drug_interaction_view(request):
    """
    AI Drug Interaction Checker.
    POST body: { drugs: ["Drug A 0.5%", "Drug B", ...] }
    Returns JSON with interactions, cautions, safe flag.
    """
    if not request.user.can_use_ai_assistant():
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    drugs = data.get('drugs', [])
    if not isinstance(drugs, list) or len(drugs) < 2:
        return JsonResponse({'success': True, 'data': {'interactions': [], 'cautions': [], 'safe': True}})

    from .groq_client import groq_chat
    drug_list = ', '.join(drugs)
    msg = [{
        'role': 'user',
        'content': (
            f'You are an ophthalmic clinical pharmacist. Check for interactions between these drugs: {drug_list}.\n\n'
            'Respond with ONLY valid JSON in this exact format, no other text:\n'
            '{"safe": true, "interactions": [], "cautions": []}\n\n'
            'Rules:\n'
            '- "safe": boolean — false if any significant interaction exists\n'
            '- "interactions": array of objects, each with keys: "drugs" (array of 2 drug names), "severity" ("major"|"moderate"|"minor"), "description" (string), "recommendation" (string)\n'
            '- "cautions": array of plain strings (general warnings, monitoring tips)\n'
            '- If no interactions found: {"safe": true, "interactions": [], "cautions": []}\n'
        )
    }]
    gr = groq_chat(msg, max_tokens=800)
    if gr['success']:
        import re as _re
        raw = gr['text']
        json_match = _re.search(r'\{.*\}', raw, _re.DOTALL)
        try:
            parsed = json.loads(json_match.group()) if json_match else {}
            interactions = parsed.get('interactions', [])
            # Normalise: if AI returned strings instead of objects, wrap them
            normalised = []
            for ix in interactions:
                if isinstance(ix, str):
                    normalised.append({
                        'drugs': drugs[:2],
                        'severity': 'moderate',
                        'description': ix,
                        'recommendation': 'Monitor closely.',
                    })
                elif isinstance(ix, dict):
                    if 'drugs' not in ix or not isinstance(ix.get('drugs'), list):
                        ix['drugs'] = drugs[:2]
                    normalised.append(ix)
            return JsonResponse({'success': True, 'data': {
                'interactions': normalised,
                'cautions': parsed.get('cautions', []),
                'safe': parsed.get('safe', len(normalised) == 0),
            }})
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'success': True, 'data': {
                'interactions': [],
                'cautions': [raw[:500]] if raw else [],
                'safe': True,
            }})
    return JsonResponse({'success': False, 'error': gr.get('error', 'AI unavailable')}, status=500)


@login_required
def analytics_ai_view(request):
    """AI Analytics assistant — answers questions about patient data, trends, KPIs."""
    if not request.user.can_use_ai_assistant():
        return JsonResponse({'error': 'Permission denied'}, status=403)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            question = data.get('question', '').strip()
        except json.JSONDecodeError:
            question = request.POST.get('question', '').strip()

        if not question:
            return JsonResponse({'error': 'Empty question'}, status=400)

        # Build hospital context dict
        from django.utils import timezone
        from django.db.models import Count
        from apps.patients.models import Patient
        from apps.appointments.models import Appointment
        from apps.consultations.models import Consultation

        hospital_data = {}
        try:
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

            hospital_data = {
                'total_patients': total_patients,
                'new_patients_month': new_patients_month,
                'today_appts': today_appts,
                'week_appts': week_appts,
                'dept_counts': {r['department__name']: r['n'] for r in dept_counts},
            }
        except Exception:
            pass

        from . import groq_client
        response = groq_client.get_analytics_response(question, hospital_data)
        return JsonResponse({'response': response})

    return render(request, 'ai_assistant/analytics.html')
