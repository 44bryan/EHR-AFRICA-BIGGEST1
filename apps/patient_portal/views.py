"""
Patient Self-Service Portal
===========================
Patients log in with their Patient ID + Date of Birth.
No password required — accessible and low-friction for Cameroon context.

Session key: PORTAL_PATIENT_ID stores the authenticated patient's patient_id.

Features:
  - View upcoming & past appointments
  - View invoices and receipts
  - View prescriptions
  - Book a follow-up appointment request
  - View imaging study links
"""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.cache import never_cache


SESSION_KEY = 'portal_patient_id'


def _get_portal_patient(request):
    """Return the authenticated portal patient, or None."""
    pid = request.session.get(SESSION_KEY)
    if not pid:
        return None
    from apps.patients.models import Patient
    try:
        return Patient.objects.get(patient_id=pid, is_deleted=False)
    except Patient.DoesNotExist:
        return None


def portal_required(view_func):
    """Redirect to login if patient not authenticated in portal session."""
    from functools import wraps
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get(SESSION_KEY):
            return redirect('portal:login')
        return view_func(request, *args, **kwargs)
    return wrapper


# ── Auth ───────────────────────────────────────────────────────────────────────

@never_cache
def portal_login(request):
    """Patient logs in with Patient ID + Date of Birth."""
    if request.session.get(SESSION_KEY):
        return redirect('portal:dashboard')

    error = None
    if request.method == 'POST':
        patient_id = request.POST.get('patient_id', '').strip().upper()
        dob_str = request.POST.get('date_of_birth', '').strip()

        from apps.patients.models import Patient
        from datetime import date
        try:
            dob = date.fromisoformat(dob_str)
        except (ValueError, TypeError):
            error = 'Please enter a valid date of birth.'
        else:
            try:
                patient = Patient.objects.get(
                    patient_id=patient_id,
                    date_of_birth=dob,
                    is_deleted=False,
                )
                request.session[SESSION_KEY] = patient.patient_id
                request.session.set_expiry(3600 * 8)  # 8-hour portal session
                return redirect('portal:dashboard')
            except Patient.DoesNotExist:
                error = 'Patient ID or date of birth is incorrect. Please check and try again.'

    from django.conf import settings
    hospital_name = getattr(settings, 'HOSPITAL_NAME', 'EHR Africa')
    return render(request, 'portal/login.html', {'error': error, 'hospital_name': hospital_name})


def portal_logout(request):
    request.session.pop(SESSION_KEY, None)
    return redirect('portal:login')


# ── Dashboard ─────────────────────────────────────────────────────────────────

@portal_required
def portal_dashboard(request):
    patient = _get_portal_patient(request)
    if not patient:
        return redirect('portal:login')

    today = timezone.localdate()

    from apps.appointments.models import Appointment
    upcoming_appts = Appointment.objects.filter(
        patient=patient,
        appointment_date__gte=today,
        status__in=['SCHEDULED', 'CONFIRMED'],
        is_deleted=False,
    ).order_by('appointment_date', 'appointment_time')[:3]

    from apps.billing.models import Invoice, InvoiceStatus
    unpaid_invoices = Invoice.objects.filter(
        patient=patient,
        status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
        is_deleted=False,
    ).order_by('-issue_date')[:3]

    from apps.prescriptions.models import DrugPrescription as Prescription
    recent_prescriptions = Prescription.objects.filter(
        patient=patient, is_deleted=False
    ).order_by('-created_at')[:3]

    return render(request, 'portal/dashboard.html', {
        'patient': patient,
        'upcoming_appts': upcoming_appts,
        'unpaid_invoices': unpaid_invoices,
        'recent_prescriptions': recent_prescriptions,
        'today': today,
    })


# ── Appointments ──────────────────────────────────────────────────────────────

@portal_required
def portal_appointments(request):
    patient = _get_portal_patient(request)
    if not patient:
        return redirect('portal:login')

    from apps.appointments.models import Appointment
    today = timezone.localdate()

    upcoming = Appointment.objects.filter(
        patient=patient, appointment_date__gte=today, is_deleted=False
    ).exclude(status='CANCELLED').order_by('appointment_date', 'appointment_time')

    past = Appointment.objects.filter(
        patient=patient, appointment_date__lt=today, is_deleted=False
    ).order_by('-appointment_date')[:20]

    return render(request, 'portal/appointments.html', {
        'patient': patient,
        'upcoming': upcoming,
        'past': past,
    })


# ── Invoices ──────────────────────────────────────────────────────────────────

@portal_required
def portal_invoices(request):
    patient = _get_portal_patient(request)
    if not patient:
        return redirect('portal:login')

    from apps.billing.models import Invoice
    invoices = Invoice.objects.filter(
        patient=patient, is_deleted=False
    ).order_by('-issue_date')

    return render(request, 'portal/invoices.html', {
        'patient': patient,
        'invoices': invoices,
    })


# ── Prescriptions ─────────────────────────────────────────────────────────────

@portal_required
def portal_prescriptions(request):
    patient = _get_portal_patient(request)
    if not patient:
        return redirect('portal:login')

    from apps.prescriptions.models import DrugPrescription as Prescription
    prescriptions = Prescription.objects.filter(
        patient=patient, is_deleted=False
    ).select_related('prescribed_by').order_by('-created_at')[:30]

    return render(request, 'portal/prescriptions.html', {
        'patient': patient,
        'prescriptions': prescriptions,
    })


# ── Book Appointment Request ───────────────────────────────────────────────────

@portal_required
def portal_book_appointment(request):
    patient = _get_portal_patient(request)
    if not patient:
        return redirect('portal:login')

    from apps.departments.models import Department
    departments = Department.objects.filter(is_active=True)

    if request.method == 'POST':
        from apps.appointments.models import Appointment
        from apps.core.utils import generate_appointment_number
        dept_id = request.POST.get('department_id')
        appt_date = request.POST.get('appointment_date')
        reason = request.POST.get('reason', '').strip()

        if not appt_date or not reason:
            messages.error(request, 'Please fill in all required fields.')
        else:
            dept = None
            if dept_id:
                try:
                    dept = Department.objects.get(id=dept_id)
                except Department.DoesNotExist:
                    pass

            appt = Appointment.objects.create(
                patient=patient,
                department=dept,
                appointment_date=appt_date,
                appointment_time='08:00',
                appointment_type='FOLLOW_UP',
                reason=reason,
                status='SCHEDULED',
                booked_by=None,
            )
            messages.success(request, f'Appointment request submitted for {appt.appointment_date}. '
                             f'You will be contacted to confirm the time.')
            return redirect('portal:appointments')

    return render(request, 'portal/book_appointment.html', {
        'patient': patient,
        'departments': departments,
        'min_date': (timezone.localdate() + timezone.timedelta(days=1)).isoformat(),
    })
