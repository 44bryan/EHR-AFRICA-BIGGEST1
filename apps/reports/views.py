"""
PDF report generation using WeasyPrint.
Each report type renders an HTML template and converts to PDF.
"""
import io
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden
from django.template.loader import render_to_string
from django.conf import settings


def render_pdf(template_name, context):
    """
    Render an HTML template to PDF using WeasyPrint.
    Falls back to a browser-printable HTML page (with auto-print JS) if
    WeasyPrint is not installed — so the print button always works.

    Injects `pdf_logo_url` (base64 data URI) and shared hospital context into
    every PDF template so the letterhead can embed the logo without file-path issues.
    """
    import os, base64 as _b64

    # ── Embed logo as base64 so it works in both WeasyPrint and browser-print ──
    if 'pdf_logo_url' not in context:
        logo_data = ''
        static_dirs = getattr(settings, 'STATICFILES_DIRS', [])
        if static_dirs:
            logo_path = os.path.join(str(static_dirs[0]), 'img', 'gludd_logo.svg')
            if os.path.exists(logo_path):
                try:
                    with open(logo_path, 'rb') as _f:
                        logo_data = 'data:image/svg+xml;base64,' + _b64.b64encode(_f.read()).decode()
                except OSError:
                    pass
        context['pdf_logo_url'] = logo_data

    # ── Shared hospital fields ────────────────────────────────────────────────
    context.setdefault('hospital_name', settings.HOSPITAL_NAME)
    context.setdefault('hospital_address', getattr(settings, 'HOSPITAL_ADDRESS', ''))
    context.setdefault('hospital_phone', getattr(settings, 'HOSPITAL_PHONE', ''))
    context.setdefault('hospital_email', getattr(settings, 'HOSPITAL_EMAIL', ''))
    context.setdefault('hospital_tagline', getattr(settings, 'HOSPITAL_TAGLINE', 'Specialist Eye Hospital'))

    html_string = render_to_string(template_name, context)

    try:
        from weasyprint import HTML
        html = HTML(string=html_string, base_url=settings.STATIC_ROOT if settings.STATIC_ROOT else '.')
        pdf_bytes = html.write_pdf()
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        filename = context.get('pdf_filename', 'report.pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
    except (ImportError, OSError, Exception):
        # ImportError  → WeasyPrint not installed
        # OSError      → WeasyPrint installed but GTK/GLib DLLs missing (common on Windows)
        # Any other    → Unexpected WeasyPrint failure
        # Fall through to browser-print fallback in all cases.
        pass

    # ── Browser-print fallback ────────────────────────────────────────────
    # Inject a small script that fires window.print() on load so the user
    # gets the OS print dialog without needing WeasyPrint installed.
    print_script = """
<script>
window.addEventListener('load', function() {
  // Give fonts / images a moment to load before opening print dialog
  setTimeout(function() { window.print(); }, 400);
});
</script>
"""
    # Insert just before </body> if present, otherwise append
    if '</body>' in html_string:
        html_string = html_string.replace('</body>', print_script + '</body>', 1)
    else:
        html_string += print_script

    return HttpResponse(html_string, content_type='text/html')


@login_required
def consultation_pdf_view(request, pk):
    from apps.consultations.models import Consultation
    consultation = get_object_or_404(
        Consultation.objects.select_related(
            'patient', 'department', 'consulting_doctor', 'visit'
        ).prefetch_related(
            'consultation_diagnoses__diagnosis',
            'drug_prescriptions__items',
            'optical_prescriptions',
        ),
        pk=pk
    )
    context = {
        'consultation': consultation,
        'patient': consultation.patient,
        'hospital_name': settings.HOSPITAL_NAME,
        'hospital_address': settings.HOSPITAL_ADDRESS,
        'hospital_phone': settings.HOSPITAL_PHONE,
        'pdf_filename': f'consultation_{consultation.patient.patient_id}_{consultation.consultation_date:%Y%m%d}.pdf',
    }
    return render_pdf('reports/pdf/consultation_report.html', context)


@login_required
def drug_prescription_pdf_view(request, pk):
    from apps.prescriptions.models import DrugPrescription
    prescription = get_object_or_404(
        DrugPrescription.objects.prefetch_related('items'),
        pk=pk
    )
    context = {
        'prescription': prescription,
        'patient': prescription.patient,
        'hospital_name': settings.HOSPITAL_NAME,
        'hospital_address': settings.HOSPITAL_ADDRESS,
        'hospital_phone': settings.HOSPITAL_PHONE,
        'pdf_filename': f'prescription_{prescription.patient.patient_id}_{prescription.prescription_date}.pdf',
    }
    return render_pdf('reports/pdf/drug_prescription.html', context)


@login_required
def optical_prescription_pdf_view(request, pk):
    from apps.prescriptions.models import OpticalPrescription
    rx = get_object_or_404(OpticalPrescription, pk=pk)
    context = {
        'rx': rx,
        'patient': rx.patient,
        'hospital_name': settings.HOSPITAL_NAME,
        'hospital_address': settings.HOSPITAL_ADDRESS,
        'hospital_phone': settings.HOSPITAL_PHONE,
        'pdf_filename': f'optical_rx_{rx.patient.patient_id}_{rx.prescription_date}.pdf',
    }
    return render_pdf('reports/pdf/optical_prescription.html', context)


@login_required
def investigation_pdf_view(request, pk):
    from apps.investigations.models import InvestigationOrder
    order = get_object_or_404(
        InvestigationOrder.objects.select_related('patient', 'investigation_type', 'ordered_by'),
        pk=pk
    )
    result = getattr(order, 'result', None)
    context = {
        'order': order,
        'result': result,
        'patient': order.patient,
        'hospital_name': settings.HOSPITAL_NAME,
        'hospital_address': settings.HOSPITAL_ADDRESS,
        'hospital_phone': settings.HOSPITAL_PHONE,
        'pdf_filename': f'investigation_{order.patient.patient_id}_{order.created_at:%Y%m%d}.pdf',
    }
    return render_pdf('reports/pdf/investigation_report.html', context)


@login_required
def visit_summary_pdf_view(request, pk):
    from apps.patients.models import Visit
    visit = get_object_or_404(
        Visit.objects.select_related(
            'patient', 'department', 'attending_doctor', 'triage_nurse'
        ).prefetch_related(
            'consultations__consultation_diagnoses__diagnosis',
            'consultations__drug_prescriptions__items',
            'consultations__optical_prescriptions',
            'consultations__investigation_orders__result',
            'consultations__lab_orders__items__result',
        ),
        pk=pk
    )
    from apps.billing.models import Invoice
    invoices = Invoice.objects.filter(
        patient=visit.patient,
        created_at__date=visit.visit_date.date(),
        is_deleted=False,
    ).prefetch_related('items', 'payments')
    context = {
        'visit': visit,
        'patient': visit.patient,
        'invoices': invoices,
        'hospital_name': settings.HOSPITAL_NAME,
        'hospital_address': settings.HOSPITAL_ADDRESS,
        'hospital_phone': settings.HOSPITAL_PHONE,
        'pdf_filename': f'visit_summary_{visit.patient.patient_id}_{visit.visit_date:%Y%m%d}.pdf',
    }
    return render_pdf('reports/pdf/visit_summary.html', context)


@login_required
def lab_report_pdf_view(request, pk):
    from apps.laboratory.models import LabOrder
    order = get_object_or_404(
        LabOrder.objects.select_related('patient', 'ordered_by').prefetch_related('items__test_type', 'items__result'),
        pk=pk
    )
    context = {
        'order': order,
        'patient': order.patient,
        'hospital_name': settings.HOSPITAL_NAME,
        'hospital_address': settings.HOSPITAL_ADDRESS,
        'hospital_phone': settings.HOSPITAL_PHONE,
        'pdf_filename': f'lab_report_{order.patient.patient_id}_{order.created_at:%Y%m%d}.pdf',
    }
    return render_pdf('reports/pdf/lab_report.html', context)


# ── Medical Certificate ──────────────────────────────────────────────────────

@login_required
def medical_certificate_view(request, consultation_pk):
    """Medical certificate / sick note generator."""
    from apps.consultations.models import Consultation
    from django.shortcuts import render, redirect
    from django.utils import timezone as tz

    consult = get_object_or_404(
        Consultation.objects.select_related('patient', 'consulting_doctor', 'department'),
        pk=consultation_pk
    )
    if not (request.user.is_doctor or request.user.is_super_admin or request.user.is_medical_director):
        return HttpResponseForbidden()

    if request.method == 'POST':
        context = {
            'consult': consult,
            'patient': consult.patient,
            'doctor': consult.consulting_doctor,
            'cert_type': request.POST.get('cert_type', 'SICK_NOTE'),
            'days_off': request.POST.get('days_off', ''),
            'date_from': request.POST.get('date_from', ''),
            'date_to': request.POST.get('date_to', ''),
            'fitness_note': request.POST.get('fitness_note', ''),
            'diagnosis_text': request.POST.get('diagnosis_text', ''),
            'issue_date': tz.localdate(),
            'hospital_name': settings.HOSPITAL_NAME,
            'hospital_address': settings.HOSPITAL_ADDRESS,
            'hospital_phone': settings.HOSPITAL_PHONE,
            'hospital_reg': getattr(settings, 'HOSPITAL_REG_NUMBER', ''),
            'pdf_filename': f'medical_certificate_{consult.patient.patient_id}.pdf',
        }
        return render_pdf('reports/pdf/medical_certificate.html', context)

    return render(request, 'reports/medical_certificate_form.html', {
        'consult': consult,
        'patient': consult.patient,
    })


# ── Referral Letter ──────────────────────────────────────────────────────────

@login_required
def referral_letter_view(request, consultation_pk):
    """Formal referral letter PDF generator."""
    from apps.consultations.models import Consultation
    from django.shortcuts import render
    from django.utils import timezone as tz

    consult = get_object_or_404(
        Consultation.objects.select_related(
            'patient', 'consulting_doctor', 'department', 'referral_department'
        ).prefetch_related('consultation_diagnoses__diagnosis'),
        pk=consultation_pk
    )

    if request.method == 'POST':
        diagnoses = [cd.diagnosis for cd in consult.consultation_diagnoses.all()]
        context = {
            'consult': consult,
            'patient': consult.patient,
            'doctor': consult.consulting_doctor,
            'diagnoses': diagnoses,
            'to_doctor': request.POST.get('to_doctor', ''),
            'to_facility': request.POST.get('to_facility', ''),
            'referral_reason': request.POST.get('referral_reason', consult.referral_reason),
            'urgency': request.POST.get('urgency', 'Routine'),
            'clinical_summary': request.POST.get('clinical_summary', ''),
            'issue_date': tz.localdate(),
            'hospital_name': settings.HOSPITAL_NAME,
            'hospital_address': settings.HOSPITAL_ADDRESS,
            'hospital_phone': settings.HOSPITAL_PHONE,
            'hospital_reg': getattr(settings, 'HOSPITAL_REG_NUMBER', ''),
            'pdf_filename': f'referral_{consult.patient.patient_id}.pdf',
        }
        return render_pdf('reports/pdf/referral_letter.html', context)

    return render(request, 'reports/referral_letter_form.html', {
        'consult': consult,
        'patient': consult.patient,
    })


# ── Patient Summary (one-pager) ──────────────────────────────────────────────

@login_required
def patient_summary_pdf_view(request, patient_id):
    """One-page patient overview for handover or referral."""
    from apps.patients.models import Patient
    from apps.consultations.models import Consultation
    from apps.investigations.models import InvestigationOrder

    patient = get_object_or_404(Patient, patient_id=patient_id, is_deleted=False)

    recent_consults = Consultation.objects.filter(
        patient=patient, is_deleted=False
    ).select_related('department', 'consulting_doctor', 'visit').prefetch_related(
        'consultation_diagnoses__diagnosis',
        'optical_prescriptions',
        'drug_prescriptions__items',
    ).order_by('-consultation_date')[:5]

    recent_investigations = InvestigationOrder.objects.filter(
        patient=patient
    ).select_related('investigation_type').order_by('-created_at')[:5]

    try:
        medical_history = patient.medical_history
    except Exception:
        medical_history = None

    context = {
        'patient': patient,
        'recent_consults': recent_consults,
        'recent_investigations': recent_investigations,
        'medical_history': medical_history,
        'hospital_name': settings.HOSPITAL_NAME,
        'hospital_address': settings.HOSPITAL_ADDRESS,
        'hospital_phone': settings.HOSPITAL_PHONE,
        'pdf_filename': f'patient_summary_{patient.patient_id}.pdf',
    }
    return render_pdf('reports/pdf/patient_summary.html', context)
