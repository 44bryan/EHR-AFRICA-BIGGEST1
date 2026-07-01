"""
FHIR R4 API endpoints for interoperability with external systems.

Authentication: Same Bearer token as Power BI endpoints.
  Authorization: Bearer <your-token>

Base URL: /api/fhir/

Implemented resources:
  GET /api/fhir/metadata                       → CapabilityStatement
  GET /api/fhir/Patient/{patient_id}/          → Patient resource
  GET /api/fhir/Patient/                       → Patient search (?name=, ?identifier=)
  GET /api/fhir/Encounter/{consultation_id}/   → Encounter resource
  GET /api/fhir/Invoice/{invoice_id}/          → Invoice resource
  GET /api/fhir/Observation/{visit_id}/        → Observations (vitals) for a visit

Ref: https://hl7.org/fhir/R4/
"""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import functools
import logging

logger = logging.getLogger(__name__)

FHIR_VERSION = '4.0.1'
FHIR_BASE = '/api/fhir'


# ── Auth (reuse APIToken) ──────────────────────────────────────────────────────

def fhir_auth(view_func):
    """Validate Bearer token; sets request.api_token."""
    @functools.wraps(view_func)
    @csrf_exempt
    def wrapper(request, *args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return _fhir_error(401, 'security', 'Missing or invalid Authorization header')
        raw = auth.split(' ', 1)[1].strip()
        from .models import APIToken
        try:
            token = APIToken.objects.get(token=raw)
        except APIToken.DoesNotExist:
            return _fhir_error(403, 'security', 'Invalid token')
        if not token.is_valid:
            return _fhir_error(403, 'security', 'Token expired or inactive')
        token.touch()
        request.api_token = token
        return view_func(request, *args, **kwargs)
    return wrapper


def _fhir_error(status, code, message):
    return JsonResponse({
        'resourceType': 'OperationOutcome',
        'issue': [{'severity': 'error', 'code': code, 'diagnostics': message}],
    }, status=status)


def _fhir_response(data):
    r = JsonResponse(data)
    r['Content-Type'] = 'application/fhir+json'
    return r


# ── CapabilityStatement ────────────────────────────────────────────────────────

@fhir_auth
def fhir_metadata(request):
    """FHIR CapabilityStatement — declares what this server supports."""
    data = {
        'resourceType': 'CapabilityStatement',
        'status': 'active',
        'date': timezone.now().isoformat(),
        'kind': 'instance',
        'fhirVersion': FHIR_VERSION,
        'format': ['application/fhir+json'],
        'software': {'name': 'EHR Africa', 'version': '2.0'},
        'rest': [{
            'mode': 'server',
            'resource': [
                {'type': 'Patient',     'interaction': [{'code': 'read'}, {'code': 'search-type'}]},
                {'type': 'Encounter',   'interaction': [{'code': 'read'}]},
                {'type': 'Invoice',     'interaction': [{'code': 'read'}]},
                {'type': 'Observation', 'interaction': [{'code': 'read'}]},
            ],
        }],
    }
    return _fhir_response(data)


# ── Patient ────────────────────────────────────────────────────────────────────

def _patient_to_fhir(patient):
    gender_map = {'M': 'male', 'F': 'female', 'Other': 'other'}
    resource = {
        'resourceType': 'Patient',
        'id': patient.patient_id,
        'meta': {'lastUpdated': patient.updated_at.isoformat() if patient.updated_at else None},
        'identifier': [{'system': 'urn:ehr-africa:patient-id', 'value': patient.patient_id}],
        'active': not patient.is_deleted,
        'name': [{
            'use': 'official',
            'family': patient.last_name,
            'given': [n for n in [patient.first_name, patient.middle_name] if n],
        }],
        'gender': gender_map.get(patient.gender, 'unknown'),
        'birthDate': patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        'telecom': [],
        'address': [],
    }
    if patient.phone_number:
        resource['telecom'].append({'system': 'phone', 'value': str(patient.phone_number), 'use': 'mobile'})
    if patient.email:
        resource['telecom'].append({'system': 'email', 'value': patient.email})
    if patient.address:
        resource['address'].append({'text': patient.address, 'country': 'CM'})
    return resource


@fhir_auth
def fhir_patient_read(request, patient_id):
    """GET /api/fhir/Patient/{patient_id}/ — read a single patient."""
    from apps.patients.models import Patient
    try:
        patient = Patient.objects.get(patient_id=patient_id)
    except Patient.DoesNotExist:
        return _fhir_error(404, 'not-found', f'Patient {patient_id} not found')
    return _fhir_response(_patient_to_fhir(patient))


@fhir_auth
def fhir_patient_search(request):
    """
    GET /api/fhir/Patient/?name=Ndongo&identifier=EHR-2024-00001
    Returns a FHIR Bundle of matching patients.
    """
    from apps.patients.models import Patient
    from django.db.models import Q

    qs = Patient.objects.filter(is_deleted=False)
    name = request.GET.get('name', '').strip()
    identifier = request.GET.get('identifier', '').strip()
    phone = request.GET.get('phone', '').strip()

    if name:
        qs = qs.filter(Q(first_name__icontains=name) | Q(last_name__icontains=name))
    if identifier:
        qs = qs.filter(patient_id__iexact=identifier)
    if phone:
        qs = qs.filter(phone_number__icontains=phone)

    entries = [{'resource': _patient_to_fhir(p)} for p in qs[:50]]
    bundle = {
        'resourceType': 'Bundle',
        'type': 'searchset',
        'total': len(entries),
        'entry': entries,
    }
    return _fhir_response(bundle)


# ── Encounter (Consultation) ───────────────────────────────────────────────────

def _consultation_to_fhir(consult):
    status_map = {
        'IN_PROGRESS': 'in-progress',
        'COMPLETED': 'finished',
        'CANCELLED': 'cancelled',
    }
    resource = {
        'resourceType': 'Encounter',
        'id': str(consult.id),
        'status': status_map.get(getattr(consult, 'status', ''), 'finished'),
        'class': {'system': 'http://terminology.hl7.org/CodeSystem/v3-ActCode', 'code': 'AMB', 'display': 'ambulatory'},
        'subject': {'reference': f'Patient/{consult.patient.patient_id}', 'display': consult.patient.full_name},
        'period': {'start': consult.created_at.isoformat() if consult.created_at else None},
        'reasonCode': [],
        'serviceProvider': {'display': 'EHR Africa Ophthalmology'},
    }
    if hasattr(consult, 'doctor') and consult.doctor:
        resource['participant'] = [{
            'individual': {'display': consult.doctor.get_full_name() or consult.doctor.username}
        }]
    if hasattr(consult, 'chief_complaint') and consult.chief_complaint:
        resource['reasonCode'] = [{'text': consult.chief_complaint}]
    return resource


@fhir_auth
def fhir_encounter_read(request, consultation_id):
    """GET /api/fhir/Encounter/{consultation_id}/"""
    from apps.consultations.models import Consultation
    try:
        consult = Consultation.objects.select_related('patient', 'doctor').get(
            id=consultation_id, is_deleted=False
        )
    except Consultation.DoesNotExist:
        return _fhir_error(404, 'not-found', 'Encounter not found')
    return _fhir_response(_consultation_to_fhir(consult))


# ── Invoice ────────────────────────────────────────────────────────────────────

def _invoice_to_fhir(invoice):
    status_map = {
        'DRAFT': 'draft',
        'ISSUED': 'issued',
        'PARTIAL': 'issued',
        'PAID': 'balanced',
        'CANCELLED': 'cancelled',
        'WAIVED': 'cancelled',
    }
    line_items = []
    for item in invoice.items.filter(is_deleted=False):
        line_items.append({
            'chargeItem': {'display': item.description},
            'priceComponent': [{
                'type': 'base',
                'amount': {'value': float(item.unit_price), 'currency': 'XAF'},
            }],
        })
    resource = {
        'resourceType': 'Invoice',
        'id': str(invoice.id),
        'status': status_map.get(invoice.status, 'issued'),
        'subject': {'reference': f'Patient/{invoice.patient.patient_id}', 'display': invoice.patient.full_name},
        'date': invoice.issue_date.isoformat(),
        'identifier': [{'system': 'urn:ehr-africa:invoice', 'value': invoice.invoice_number}],
        'lineItem': line_items,
        'totalNet': {'value': float(invoice.subtotal), 'currency': 'XAF'},
        'totalGross': {'value': float(invoice.total), 'currency': 'XAF'},
    }
    if invoice.insurance_amount > 0:
        resource['totalPriceComponent'] = [
            {'type': 'surcharge', 'code': {'text': 'Insurance Coverage'},
             'amount': {'value': float(invoice.insurance_amount), 'currency': 'XAF'}},
            {'type': 'base', 'code': {'text': 'Patient Share'},
             'amount': {'value': float(invoice.patient_amount), 'currency': 'XAF'}},
        ]
    return resource


@fhir_auth
def fhir_invoice_read(request, invoice_id):
    """GET /api/fhir/Invoice/{invoice_id}/"""
    from apps.billing.models import Invoice
    try:
        invoice = Invoice.objects.select_related('patient').prefetch_related('items').get(
            id=invoice_id, is_deleted=False
        )
    except Invoice.DoesNotExist:
        return _fhir_error(404, 'not-found', 'Invoice not found')
    return _fhir_response(_invoice_to_fhir(invoice))


# ── Observation (Vitals) ───────────────────────────────────────────────────────

def _vital_observation(visit, code_system, code, display, value, unit, unit_code):
    return {
        'resourceType': 'Observation',
        'status': 'final',
        'code': {'coding': [{'system': code_system, 'code': code, 'display': display}]},
        'subject': {'reference': f'Patient/{visit.patient.patient_id}'},
        'effectiveDateTime': visit.visit_date.isoformat() if hasattr(visit.visit_date, 'isoformat') else str(visit.visit_date),
        'valueQuantity': {'value': value, 'unit': unit, 'system': 'http://unitsofmeasure.org', 'code': unit_code},
    }


@fhir_auth
def fhir_observation_list(request, visit_id):
    """
    GET /api/fhir/Observation/{visit_id}/
    Returns a FHIR Bundle of vital sign observations for a visit.
    """
    from apps.patients.models import Visit
    LOINC = 'http://loinc.org'
    try:
        visit = Visit.objects.select_related('patient').get(id=visit_id, is_deleted=False)
    except Visit.DoesNotExist:
        return _fhir_error(404, 'not-found', 'Visit not found')

    observations = []
    if getattr(visit, 'weight', None):
        observations.append(_vital_observation(visit, LOINC, '29463-7', 'Body weight', float(visit.weight), 'kg', 'kg'))
    if getattr(visit, 'height', None):
        observations.append(_vital_observation(visit, LOINC, '8302-2', 'Body height', float(visit.height), 'cm', 'cm'))
    if getattr(visit, 'temperature', None):
        observations.append(_vital_observation(visit, LOINC, '8310-5', 'Body temperature', float(visit.temperature), '°C', 'Cel'))
    if getattr(visit, 'pulse', None):
        observations.append(_vital_observation(visit, LOINC, '8867-4', 'Heart rate', float(visit.pulse), 'bpm', '/min'))
    if getattr(visit, 'systolic_bp', None):
        observations.append(_vital_observation(visit, LOINC, '8480-6', 'Systolic BP', float(visit.systolic_bp), 'mmHg', 'mm[Hg]'))
    if getattr(visit, 'diastolic_bp', None):
        observations.append(_vital_observation(visit, LOINC, '8462-4', 'Diastolic BP', float(visit.diastolic_bp), 'mmHg', 'mm[Hg]'))
    if getattr(visit, 'oxygen_saturation', None):
        observations.append(_vital_observation(visit, LOINC, '2708-6', 'SpO2', float(visit.oxygen_saturation), '%', '%'))

    bundle = {
        'resourceType': 'Bundle',
        'type': 'searchset',
        'total': len(observations),
        'entry': [{'resource': o} for o in observations],
    }
    return _fhir_response(bundle)
