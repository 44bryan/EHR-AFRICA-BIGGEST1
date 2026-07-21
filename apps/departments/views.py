import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_POST
from .models import Department, DepartmentCode, ConsultationRoom
from apps.accounts.models import UserRole, User


def _can_manage_departments(user):
    return user.role in (
        UserRole.ADMIN_DIRECTOR, UserRole.MEDICAL_DIRECTOR,
        UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.CEO,
    ) or user.is_superuser


@login_required
def dept_list(request):
    if not _can_manage_departments(request.user):
        return HttpResponseForbidden()
    departments = Department.objects.select_related('head_of_department').order_by('name')
    return render(request, 'departments/dept_list.html', {'departments': departments})


@login_required
def dept_edit(request, dept_id):
    if not _can_manage_departments(request.user):
        return HttpResponseForbidden()
    dept = get_object_or_404(Department, pk=dept_id)
    doctors = User.objects.filter(
        role__in=[
            UserRole.MEDICAL_DIRECTOR, UserRole.OPHTHALMOLOGIST,
            UserRole.RETINA_SPECIALIST, UserRole.GLAUCOMA_SPECIALIST,
            UserRole.PEDIATRIC_OPHTHALMOLOGIST, UserRole.CATARACT_SURGEON,
            UserRole.CORNEA_SPECIALIST, UserRole.OCULOPLASTICS_SURGEON,
            UserRole.NEURO_OPHTHALMOLOGIST, UserRole.UVEITIS_SPECIALIST,
            UserRole.OPTOMETRIST, UserRole.LOW_VISION_SPECIALIST,
        ],
        is_active=True,
    ).order_by('last_name')

    if request.method == 'POST':
        dept.name = request.POST.get('name', dept.name).strip()
        dept.description = request.POST.get('description', '').strip()
        dept.location = request.POST.get('location', '').strip()
        dept.color_code = request.POST.get('color_code', '#0d6efd').strip()
        dept.icon = request.POST.get('icon', 'bi-eye').strip()
        dept.is_active = request.POST.get('is_active') == 'on'
        hod_id = request.POST.get('head_of_department')
        if hod_id:
            try:
                dept.head_of_department = User.objects.get(pk=hod_id)
            except User.DoesNotExist:
                dept.head_of_department = None
        else:
            dept.head_of_department = None
        dept.save()
        messages.success(request, f'Department "{dept.name}" updated.')
        return redirect('departments:dept_list')

    return render(request, 'departments/dept_edit.html', {
        'dept': dept,
        'doctors': doctors,
    })


# ── Consultation Room management ──────────────────────────────────────────────

def _doctor_choices():
    """All active clinical staff who can be assigned to a consultation room."""
    clinical_roles = [
        UserRole.MEDICAL_DIRECTOR, UserRole.OPHTHALMOLOGIST,
        UserRole.RETINA_SPECIALIST, UserRole.GLAUCOMA_SPECIALIST,
        UserRole.PEDIATRIC_OPHTHALMOLOGIST, UserRole.CATARACT_SURGEON,
        UserRole.CORNEA_SPECIALIST, UserRole.OCULOPLASTICS_SURGEON,
        UserRole.NEURO_OPHTHALMOLOGIST, UserRole.UVEITIS_SPECIALIST,
        UserRole.OPTOMETRIST, UserRole.LOW_VISION_SPECIALIST,
        UserRole.ORTHOPTIST, UserRole.PEDIATRIC_REFRACTIONIST,
    ]
    return User.objects.filter(role__in=clinical_roles, is_active=True).order_by('last_name', 'first_name')


@login_required
def room_manage(request, dept_id):
    """List and add consultation rooms for a department."""
    if not _can_manage_departments(request.user):
        return HttpResponseForbidden()
    dept = get_object_or_404(Department, pk=dept_id)
    rooms = ConsultationRoom.objects.filter(department=dept).select_related('assigned_doctor').order_by('room_number')
    doctors = _doctor_choices()

    if request.method == 'POST':
        action = request.POST.get('action', 'add')

        if action == 'bulk_add':
            raw = request.POST.get('room_numbers', '')
            numbers = [n.strip() for n in raw.replace(';', ',').split(',') if n.strip()]
            if not numbers:
                messages.error(request, 'Enter at least one room number.')
            else:
                added, existed = [], []
                for rn in numbers:
                    room, created = ConsultationRoom.objects.get_or_create(
                        department=dept,
                        room_number=rn,
                        defaults={'label': f'Room {rn}'},
                    )
                    (added if created else existed).append(rn)
                if added:
                    messages.success(request, f'Added {len(added)} room(s): {", ".join(added)}.')
                if existed:
                    messages.info(request, f'{len(existed)} room(s) already existed: {", ".join(existed)}.')

        elif action == 'add':
            room_number = request.POST.get('room_number', '').strip()
            label = request.POST.get('label', '').strip()
            if not room_number:
                messages.error(request, 'Room number is required.')
            else:
                room, created = ConsultationRoom.objects.get_or_create(
                    department=dept,
                    room_number=room_number,
                    defaults={'label': label or f'Room {room_number}'},
                )
                if created:
                    messages.success(request, f'Room {room_number} added to {dept.name}.')
                else:
                    messages.warning(request, f'Room {room_number} already exists in {dept.name}.')

        elif action == 'assign':
            room_id = request.POST.get('room_id')
            doctor_id = request.POST.get('doctor_id', '')
            new_tier = request.POST.get('room_tier', '').strip()
            room = get_object_or_404(ConsultationRoom, pk=room_id, department=dept)
            if doctor_id:
                try:
                    room.assigned_doctor = User.objects.get(pk=doctor_id)
                except User.DoesNotExist:
                    room.assigned_doctor = None
            else:
                room.assigned_doctor = None
            from .models import RoomTier
            if new_tier in dict(RoomTier.choices):
                room.room_tier = new_tier
            room.save(update_fields=['assigned_doctor', 'room_tier'])
            messages.success(request, f'{room.display_label} assignment updated.')

        elif action == 'toggle':
            room_id = request.POST.get('room_id')
            room = get_object_or_404(ConsultationRoom, pk=room_id, department=dept)
            room.is_active = not room.is_active
            room.save(update_fields=['is_active'])
            status = 'activated' if room.is_active else 'deactivated'
            messages.success(request, f'Room {room.room_number} {status}.')

        elif action == 'delete':
            room_id = request.POST.get('room_id')
            room = get_object_or_404(ConsultationRoom, pk=room_id, department=dept)
            room.delete()
            messages.success(request, f'Room {room.room_number} removed.')

        return redirect('departments:room_manage', dept_id=dept_id)

    return render(request, 'departments/dept_rooms.html', {
        'dept': dept,
        'rooms': rooms,
        'doctors': doctors,
    })


@login_required
def room_list_all(request):
    """
    Unified view — all consultation rooms across every department on one page.
    Allows admin/medical director to see, assign, and tier-set all rooms without
    navigating department-by-department.
    """
    if not _can_manage_departments(request.user):
        return HttpResponseForbidden()

    departments = Department.objects.prefetch_related(
        'rooms', 'rooms__assigned_doctor'
    ).order_by('name')
    doctors = _doctor_choices()
    from .models import RoomTier

    if request.method == 'POST':
        action = request.POST.get('action', '')
        dept_id = request.POST.get('dept_id', '')

        if action == 'assign':
            room_id = request.POST.get('room_id')
            doctor_id = request.POST.get('doctor_id', '')
            new_tier = request.POST.get('room_tier', '').strip()
            room = get_object_or_404(ConsultationRoom, pk=room_id)
            if not _can_manage_departments(request.user):
                return HttpResponseForbidden()
            room.assigned_doctor = User.objects.get(pk=doctor_id) if doctor_id else None
            if new_tier in dict(RoomTier.choices):
                room.room_tier = new_tier
            room.save(update_fields=['assigned_doctor', 'room_tier'])
            messages.success(request, f'{room.display_label} updated.')

        elif action == 'toggle':
            room_id = request.POST.get('room_id')
            room = get_object_or_404(ConsultationRoom, pk=room_id)
            room.is_active = not room.is_active
            room.save(update_fields=['is_active'])
            messages.success(request, f'Room {room.room_number} {"activated" if room.is_active else "deactivated"}.')

        elif action == 'delete':
            room_id = request.POST.get('room_id')
            room = get_object_or_404(ConsultationRoom, pk=room_id)
            label = room.room_number
            room.delete()
            messages.success(request, f'Room {label} removed.')

        elif action == 'bulk_add':
            dept = get_object_or_404(Department, pk=dept_id)
            raw = request.POST.get('room_numbers', '')
            numbers = [n.strip() for n in raw.replace(';', ',').split(',') if n.strip()]
            if not numbers:
                messages.error(request, 'Enter at least one room number.')
            else:
                added, existed = [], []
                for rn in numbers:
                    _, created = ConsultationRoom.objects.get_or_create(
                        department=dept, room_number=rn,
                        defaults={'label': f'Room {rn}'},
                    )
                    (added if created else existed).append(rn)
                if added:
                    messages.success(request, f'Added {len(added)} room(s) to {dept.name}: {", ".join(added)}.')
                if existed:
                    messages.info(request, f'{len(existed)} already existed: {", ".join(existed)}.')

        return redirect('departments:room_list_all')

    return render(request, 'departments/room_list_all.html', {
        'departments': departments,
        'doctors': doctors,
        'room_tiers': RoomTier.choices,
    })


@login_required
def room_ajax(request, dept_id):
    """
    AJAX endpoint — returns active rooms for a department as JSON.
    Used by triage.html to dynamically populate room buttons.
    GET /departments/<dept_id>/rooms-ajax/
    """
    dept = get_object_or_404(Department, pk=dept_id, is_active=True)
    rooms = (
        ConsultationRoom.objects
        .filter(department=dept, is_active=True)
        .select_related('assigned_doctor')
        .order_by('room_number')
    )
    data = [
        {
            'id': str(r.id),
            'room_number': r.room_number,
            'label': r.display_label,
            'doctor': r.assigned_doctor.get_full_name() if r.assigned_doctor else None,
            'doctor_id': str(r.assigned_doctor.pk) if r.assigned_doctor else None,
            'room_tier': r.room_tier,
            'service_type': r.tier_service_type,
        }
        for r in rooms
    ]
    return JsonResponse({'dept_name': dept.name, 'rooms': data})
