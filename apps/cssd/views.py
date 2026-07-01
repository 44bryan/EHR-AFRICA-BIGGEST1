from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import Instrument, InstrumentSet, SterilizationCycle, DispatchRecord, InstrumentStatus
from apps.accounts.models import UserRole


def _can_access_cssd(user):
    return (
        user.role in (
            UserRole.CSSD_TECHNICIAN,
            UserRole.THEATRE_NURSE,
            UserRole.MEDICAL_DIRECTOR,
        )
        or user.is_super_admin
    )


@login_required
def cssd_dashboard(request):
    if not _can_access_cssd(request.user):
        return HttpResponseForbidden()
    def ic(status):
        return Instrument.objects.filter(status=status, is_deleted=False).count()

    status_pipeline = [
        (ic(InstrumentStatus.IN_USE),        'In Use',         '#2563eb', 'bi-person-badge'),
        (ic(InstrumentStatus.DIRTY),         'Returned/Dirty', '#dc2626', 'bi-exclamation-triangle'),
        (ic(InstrumentStatus.WASHING),       'Decon/Washing',  '#d97706', 'bi-droplet'),
        (ic(InstrumentStatus.STERILIZING),   'Sterilizing',    '#7c3aed', 'bi-thermometer-half'),
        (ic(InstrumentStatus.PACKING),       'Packing',        '#0891b2', 'bi-box'),
        (ic(InstrumentStatus.AVAILABLE),     'Sterile/Ready',  '#059669', 'bi-shield-check'),
    ]

    context = {
        'total_instruments': Instrument.objects.filter(is_deleted=False).count(),
        'available_sterile': ic(InstrumentStatus.AVAILABLE),
        'dirty_count': ic(InstrumentStatus.DIRTY),
        'in_use': ic(InstrumentStatus.IN_USE),
        'recent_cycles': SterilizationCycle.objects.filter(
            is_deleted=False
        ).select_related('operator').prefetch_related('instruments', 'sets').order_by('-start_time')[:10],
        'status_pipeline': status_pipeline,
    }
    return render(request, 'cssd/dashboard.html', context)


@login_required
def instrument_list(request):
    if not _can_access_cssd(request.user):
        return HttpResponseForbidden()
    instruments = Instrument.objects.filter(is_deleted=False).order_by('name')
    return render(request, 'cssd/instrument_list.html', {'instruments': instruments})


@login_required
def sterilization_cycles(request):
    if not _can_access_cssd(request.user):
        return HttpResponseForbidden()
    cycles = SterilizationCycle.objects.filter(is_deleted=False).order_by('-start_time')[:50]
    return render(request, 'cssd/cycles.html', {'cycles': cycles})


@login_required
def dispatch_list(request):
    if not _can_access_cssd(request.user):
        return HttpResponseForbidden()
    dispatches = DispatchRecord.objects.filter(is_deleted=False).select_related(
        'to_department', 'dispatched_by'
    ).order_by('-dispatch_time')[:50]
    return render(request, 'cssd/dispatch_list.html', {'dispatches': dispatches})


@login_required
def add_instrument(request):
    if not _can_access_cssd(request.user):
        return HttpResponseForbidden()
    from apps.departments.models import Department
    departments = Department.objects.filter(is_active=True)
    if request.method == 'POST':
        code = request.POST.get('instrument_code', '').strip()
        name = request.POST.get('name', '').strip()
        if not code or not name:
            messages.error(request, 'Instrument code and name are required.')
        elif Instrument.objects.filter(instrument_code=code).exists():
            messages.error(request, f'Instrument code "{code}" already exists.')
        else:
            dept_id = request.POST.get('department')
            Instrument.objects.create(
                instrument_code=code,
                name=name,
                description=request.POST.get('description', ''),
                department_id=dept_id if dept_id else None,
                notes=request.POST.get('notes', ''),
                created_by=request.user,
            )
            messages.success(request, f'Instrument {code} — {name} added.')
            return redirect('cssd:instrument_list')
    return render(request, 'cssd/add_instrument.html', {'departments': departments})


@login_required
def record_cycle(request):
    if not _can_access_cssd(request.user):
        return HttpResponseForbidden()
    instruments = Instrument.objects.filter(
        is_deleted=False, is_active=True
    ).exclude(status=InstrumentStatus.IN_USE).order_by('name')
    instrument_sets = InstrumentSet.objects.filter(is_deleted=False, is_active=True).order_by('name')

    if request.method == 'POST':
        method = request.POST.get('method')
        if not method:
            messages.error(request, 'Sterilization method is required.')
        else:
            from django.utils import timezone as tz
            cycle = SterilizationCycle.objects.create(
                method=method,
                operator=request.user,
                temperature=request.POST.get('temperature') or None,
                pressure=request.POST.get('pressure') or None,
                duration_minutes=request.POST.get('duration_minutes') or None,
                notes=request.POST.get('notes', ''),
                created_by=request.user,
            )
            # Link selected instruments
            selected_ids = request.POST.getlist('instruments')
            if selected_ids:
                cycle.instruments.set(Instrument.objects.filter(id__in=selected_ids))
                # Update each instrument status → STERILIZING
                Instrument.objects.filter(id__in=selected_ids).update(status=InstrumentStatus.STERILIZING)

            selected_sets = request.POST.getlist('sets')
            if selected_sets:
                cycle.sets.set(InstrumentSet.objects.filter(id__in=selected_sets))

            messages.success(request, f'Sterilization cycle {cycle.cycle_number} recorded.')
            return redirect('cssd:cycles')

    from apps.cssd.models import SterilizationMethod
    return render(request, 'cssd/record_cycle.html', {
        'instruments': instruments,
        'instrument_sets': instrument_sets,
        'methods': SterilizationMethod.choices,
    })


@login_required
@require_POST
def complete_cycle(request, cycle_id):
    """Mark a sterilization cycle as complete and set all instruments to AVAILABLE/STERILE."""
    if not _can_access_cssd(request.user):
        return HttpResponseForbidden()
    cycle = get_object_or_404(SterilizationCycle, id=cycle_id, is_deleted=False)

    if cycle.end_time:
        messages.warning(request, f'Cycle {cycle.cycle_number} is already completed.')
        return redirect('cssd:cycles')

    bi_result = request.POST.get('bi_test_result', 'NOT_DONE')
    cycle.end_time = timezone.now()
    cycle.bi_test_result = bi_result
    cycle.save(update_fields=['end_time', 'bi_test_result'])

    # Move all linked instruments to AVAILABLE (sterile & ready)
    instrument_ids = list(cycle.instruments.values_list('id', flat=True))
    if instrument_ids:
        from django.utils import timezone as tz
        from datetime import timedelta
        expiry = tz.now() + timedelta(days=30)
        Instrument.objects.filter(id__in=instrument_ids).update(
            status=InstrumentStatus.AVAILABLE,
            sterilization_expiry=expiry,
        )

    messages.success(request, f'Cycle {cycle.cycle_number} completed. {len(instrument_ids)} instrument(s) marked sterile.')
    return redirect('cssd:cycles')


@login_required
def dispatch_instrument(request):
    if not _can_access_cssd(request.user):
        return HttpResponseForbidden()
    """Dispatch sterile instruments to a department/theatre."""
    from apps.departments.models import Department
    departments = Department.objects.filter(is_active=True)
    available = Instrument.objects.filter(status=InstrumentStatus.AVAILABLE, is_deleted=False).order_by('name')

    if request.method == 'POST':
        dept_id = request.POST.get('department')
        instrument_ids = request.POST.getlist('instruments')
        notes = request.POST.get('notes', '')

        if not dept_id or not instrument_ids:
            messages.error(request, 'Select a department and at least one instrument.')
        else:
            dept = get_object_or_404(Department, id=dept_id)
            record = DispatchRecord.objects.create(
                to_department=dept,
                dispatched_by=request.user,
                notes=notes,
                created_by=request.user,
            )
            record.instruments.set(Instrument.objects.filter(id__in=instrument_ids))
            # Mark instruments as IN_USE
            Instrument.objects.filter(id__in=instrument_ids).update(status=InstrumentStatus.IN_USE)
            messages.success(request, f'{len(instrument_ids)} instrument(s) dispatched to {dept.name}.')
            return redirect('cssd:dispatch_list')

    return render(request, 'cssd/dispatch_instrument.html', {
        'departments': departments, 'available': available,
    })
