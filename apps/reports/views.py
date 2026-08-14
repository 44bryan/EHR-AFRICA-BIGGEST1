"""
PDF report generation using WeasyPrint.
Each report type renders an HTML template and converts to PDF.
"""
import io
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden
from django.template.loader import render_to_string
from django.conf import settings


def _sig_b64(user):
    """
    Return a base64 data URI for a user's uploaded signature image,
    or empty string if none exists.  Safe — never raises.
    """
    import os, base64 as _b64
    try:
        if not user or not user.signature:
            return ''
        path = user.signature.path
        if not os.path.exists(path):
            return ''
        ext = os.path.splitext(path)[1].lower()
        mime = 'image/png' if ext == '.png' else 'image/jpeg'
        with open(path, 'rb') as _f:
            return f'data:{mime};base64,' + _b64.b64encode(_f.read()).decode()
    except Exception:
        return ''


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
        'prescriber_signature': _sig_b64(prescription.prescribed_by),
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
    signer = (result.verified_by if result and result.verified_by else
              result.performed_by if result else None)
    context = {
        'order': order,
        'result': result,
        'patient': order.patient,
        'hospital_name': settings.HOSPITAL_NAME,
        'hospital_address': settings.HOSPITAL_ADDRESS,
        'hospital_phone': settings.HOSPITAL_PHONE,
        'pdf_filename': f'investigation_{order.patient.patient_id}_{order.created_at:%Y%m%d}.pdf',
        'signer_signature': _sig_b64(signer),
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
    # Pick the first result's performer/verifier to sign the lab report
    first_item = order.items.select_related('result__performed_by', 'result__verified_by').first()
    first_result = getattr(first_item, 'result', None) if first_item else None
    lab_signer = (first_result.verified_by if first_result and first_result.verified_by else
                  first_result.performed_by if first_result else None)
    context = {
        'order': order,
        'patient': order.patient,
        'hospital_name': settings.HOSPITAL_NAME,
        'hospital_address': settings.HOSPITAL_ADDRESS,
        'hospital_phone': settings.HOSPITAL_PHONE,
        'pdf_filename': f'lab_report_{order.patient.patient_id}_{order.created_at:%Y%m%d}.pdf',
        'signer_signature': _sig_b64(lab_signer),
    }
    return render_pdf('reports/pdf/lab_report.html', context)


# ── Medical Certificate ──────────────────────────────────────────────────────

@login_required
def medical_certificate_view(request, consultation_pk):
    """Medical certificate / sick note generator."""
    from apps.consultations.models import Consultation
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


# ─────────────────────────────────────────────────────────────────────────────
# MOH DISEASE EXPORT — CSV
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def moh_disease_export_view(request):
    """Ministry of Health disease statistics CSV export."""
    import csv
    from django.utils import timezone
    from datetime import date as _date
    from django.db.models import Count
    from apps.consultations.models import ConsultationDiagnosis

    if not (request.user.is_super_admin or request.user.is_medical_director or
            request.user.is_admin_director or request.user.is_ceo or
            request.user.role == 'medical_records'):
        return HttpResponseForbidden()

    today = timezone.localdate()
    date_from_str = request.GET.get('from', today.replace(day=1).isoformat())
    date_to_str = request.GET.get('to', today.isoformat())

    try:
        date_from = _date.fromisoformat(date_from_str)
        date_to = _date.fromisoformat(date_to_str)
    except ValueError:
        date_from = today.replace(day=1)
        date_to = today

    if 'download' not in request.GET:
        return render(request, 'reports/analytics/moh_export_form.html', {
            'today': today,
            'month_start': today.replace(day=1),
            'date_from': date_from,
            'date_to': date_to,
        })

    qs = (
        ConsultationDiagnosis.objects
        .filter(
            consultation__consultation_date__date__gte=date_from,
            consultation__consultation_date__date__lte=date_to,
            consultation__is_deleted=False,
        )
        .values('diagnosis__icd10_code', 'diagnosis__description', 'laterality')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    response = HttpResponse(content_type='text/csv')
    filename = f'MOH_Disease_Export_{date_from}_{date_to}.csv'
    response['Content-Disposition'] = 'attachment; filename="' + filename + '"'

    writer = csv.writer(response)
    writer.writerow([
        'ICD-10 Code', 'Diagnosis', 'Laterality', 'Case Count',
        'Period From', 'Period To', 'Hospital', 'Export Date',
    ])
    for row in qs:
        writer.writerow([
            row['diagnosis__icd10_code'] or '',
            row['diagnosis__description'] or '',
            row['laterality'] or '',
            row['count'],
            date_from.isoformat(),
            date_to.isoformat(),
            settings.HOSPITAL_NAME,
            today.isoformat(),
        ])
    return response


# ─────────────────────────────────────────────────────────────────────────────
# ANALYTICS HTML REPORT VIEWS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def disease_burden_view(request):
    """Disease burden analytics — top diagnoses by count."""
    from django.utils import timezone
    from datetime import timedelta
    from django.db.models import Count
    from apps.consultations.models import ConsultationDiagnosis

    if not (request.user.is_super_admin or request.user.is_medical_director or
            request.user.is_admin_director or request.user.is_ceo or
            request.user.is_finance_director or request.user.role == 'medical_records'):
        return HttpResponseForbidden()

    today = timezone.localdate()
    period = int(request.GET.get('days', 90))
    date_from = today - timedelta(days=period)

    top_dx = list(
        ConsultationDiagnosis.objects
        .filter(
            consultation__consultation_date__date__gte=date_from,
            consultation__is_deleted=False,
        )
        .values('diagnosis__icd10_code', 'diagnosis__description')
        .annotate(count=Count('id'))
        .order_by('-count')[:20]
    )

    monthly = []
    for i in range(5, -1, -1):
        d = (today.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        nd = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        c = ConsultationDiagnosis.objects.filter(
            consultation__consultation_date__date__gte=d,
            consultation__consultation_date__date__lt=nd,
            consultation__is_deleted=False,
        ).count()
        monthly.append({'month': d.strftime('%b %Y'), 'count': c})

    return render(request, 'reports/analytics/disease_burden.html', {
        'top_dx': top_dx,
        'monthly': monthly,
        'period': period,
        'date_from': date_from,
        'today': today,
    })


@login_required
def revenue_report_view(request):
    """Revenue analytics report."""
    from django.utils import timezone
    from datetime import timedelta
    from django.db.models import Sum

    if not (request.user.is_super_admin or request.user.is_finance_director or
            request.user.is_ceo or request.user.is_admin_director or
            request.user.is_medical_director):
        return HttpResponseForbidden()

    today = timezone.localdate()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    rev_month = 0.0
    rev_year = 0.0
    monthly_revenue = []
    rev_by_method = []

    for i in range(11, -1, -1):
        d = (today.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        nd = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        try:
            from apps.billing.models import Payment
            r = Payment.objects.filter(
                payment_date__date__gte=d, payment_date__date__lt=nd, is_deleted=False,
            ).aggregate(total=Sum('amount'))['total'] or 0
        except Exception:
            r = 0
        monthly_revenue.append({'month': d.strftime('%b %Y'), 'revenue': float(r)})

    rev_by_tier = []
    vip_visits_month = 0
    express_visits_month = 0
    fast_visits_month = 0
    standard_visits_month = 0

    try:
        from apps.billing.models import Payment
        from apps.patients.models import Visit
        raw = list(
            Payment.objects.filter(
                payment_date__date__gte=month_start, is_deleted=False
            ).values('payment_method').annotate(total=Sum('amount')).order_by('-total')
        )
        rev_by_method = [{'method': r['payment_method'], 'total': float(r['total'] or 0)} for r in raw]
        rev_month = float(Payment.objects.filter(
            payment_date__date__gte=month_start, is_deleted=False
        ).aggregate(t=Sum('amount'))['t'] or 0)
        rev_year = float(Payment.objects.filter(
            payment_date__date__gte=year_start, is_deleted=False
        ).aggregate(t=Sum('amount'))['t'] or 0)

        # ── Revenue by service tier (month) ───────────────────────────────────
        for tier_code, tier_label in [('VIP', 'VIP'), ('EXPRESS', 'Express'),
                                       ('FAST_TRACK', 'Fast Track'), ('STANDARD', 'Standard')]:
            tier_rev = Payment.objects.filter(
                payment_date__date__gte=month_start,
                invoice__visit__service_tier=tier_code,
                is_deleted=False,
            ).aggregate(t=Sum('amount'))['t'] or 0
            tier_count = Visit.objects.filter(
                visit_date__date__gte=month_start,
                service_tier=tier_code,
                is_deleted=False,
            ).count()
            rev_by_tier.append({
                'tier': tier_code,
                'label': tier_label,
                'revenue': float(tier_rev),
                'count': tier_count,
            })

        vip_visits_month      = next((r['count'] for r in rev_by_tier if r['tier'] == 'VIP'), 0)
        express_visits_month  = next((r['count'] for r in rev_by_tier if r['tier'] == 'EXPRESS'), 0)
        fast_visits_month     = next((r['count'] for r in rev_by_tier if r['tier'] == 'FAST_TRACK'), 0)
        standard_visits_month = next((r['count'] for r in rev_by_tier if r['tier'] == 'STANDARD'), 0)
    except Exception:
        pass

    return render(request, 'reports/analytics/revenue_report.html', {
        'monthly_revenue': monthly_revenue,
        'rev_by_method': rev_by_method,
        'rev_month': rev_month,
        'rev_year': rev_year,
        'rev_by_tier': rev_by_tier,
        'vip_visits_month': vip_visits_month,
        'express_visits_month': express_visits_month,
        'fast_visits_month': fast_visits_month,
        'standard_visits_month': standard_visits_month,
        'today': today,
        'month_start': month_start,
    })


@login_required
def staff_performance_view(request):
    """Doctor throughput and average wait time analytics."""
    from django.utils import timezone
    from datetime import timedelta
    from django.db.models import Count, Avg
    from apps.consultations.models import Consultation
    from apps.qms.models import QueueToken, TokenStatus

    if not (request.user.is_super_admin or request.user.is_medical_director or
            request.user.is_admin_director or request.user.is_ceo or
            request.user.role == 'medical_records'):
        return HttpResponseForbidden()

    today = timezone.localdate()
    period = int(request.GET.get('days', 30))
    date_from = today - timedelta(days=period)

    doctor_stats = list(
        Consultation.objects.filter(
            created_at__date__gte=date_from, is_deleted=False
        )
        .values(
            'consulting_doctor__first_name', 'consulting_doctor__last_name',
            'consulting_doctor__role', 'department__name',
        )
        .annotate(consultations=Count('id'))
        .order_by('-consultations')[:15]
    )

    wait_by_dept = list(
        QueueToken.objects.filter(
            token_date__gte=date_from,
            status=TokenStatus.COMPLETED,
            wait_time_minutes__isnull=False,
        )
        .values('service_type')
        .annotate(avg_wait=Avg('wait_time_minutes'), count=Count('id'))
        .order_by('service_type')
    )

    return render(request, 'reports/analytics/staff_performance.html', {
        'doctor_stats': doctor_stats,
        'wait_by_dept': wait_by_dept,
        'period': period,
        'date_from': date_from,
        'today': today,
    })
