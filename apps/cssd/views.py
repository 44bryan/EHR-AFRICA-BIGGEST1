from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Instrument, InstrumentSet, SterilizationCycle, DispatchRecord, InstrumentStatus


@login_required
def cssd_dashboard(request):
    context = {
        'total_instruments': Instrument.objects.filter(is_active=True, is_deleted=False).count(),
        'available_sterile': Instrument.objects.filter(
            status=InstrumentStatus.AVAILABLE, is_deleted=False
        ).count(),
        'dirty_count': Instrument.objects.filter(
            status=InstrumentStatus.DIRTY, is_deleted=False
        ).count(),
        'in_use': Instrument.objects.filter(
            status=InstrumentStatus.IN_USE, is_deleted=False
        ).count(),
        'recent_cycles': SterilizationCycle.objects.filter(
            is_deleted=False
        ).order_by('-start_time')[:5],
    }
    return render(request, 'cssd/dashboard.html', context)


@login_required
def instrument_list(request):
    instruments = Instrument.objects.filter(is_deleted=False).order_by('name')
    return render(request, 'cssd/instrument_list.html', {'instruments': instruments})


@login_required
def sterilization_cycles(request):
    cycles = SterilizationCycle.objects.filter(is_deleted=False).order_by('-start_time')[:50]
    return render(request, 'cssd/cycles.html', {'cycles': cycles})


@login_required
def dispatch_list(request):
    dispatches = DispatchRecord.objects.filter(is_deleted=False).select_related(
        'to_department', 'dispatched_by'
    ).order_by('-dispatch_time')[:50]
    return render(request, 'cssd/dispatch_list.html', {'dispatches': dispatches})


@login_required
def add_instrument(request):
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
