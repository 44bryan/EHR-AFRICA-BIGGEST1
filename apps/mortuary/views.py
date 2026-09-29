from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q

from apps.accounts.models import UserRole
from .models import (
    MortuaryAdmission, MortuaryStorage, PostMortemRequest,
    BodyRelease, BodyStatus, StorageStatus, PostMortemStatus,
    PostMortemType, CauseOfDeath
)


def _can_access(user):
    return user.role in [
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR, UserRole.FINANCE_DIRECTOR,
        UserRole.MEDICAL_DIRECTOR, UserRole.CEO, UserRole.OPHTHALMOLOGIST,
        UserRole.NURSE, UserRole.WARD_NURSE, UserRole.NURSE_DIRECTOR,
        UserRole.MEDICAL_RECORDS,
    ]


def _can_manage(user):
    return user.role in [
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR, UserRole.FINANCE_DIRECTOR,
        UserRole.MEDICAL_DIRECTOR, UserRole.NURSE_DIRECTOR,
    ]


@login_required
def dashboard(request):
    if not _can_access(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    bodies = MortuaryAdmission.objects.filter(is_deleted=False)
    storage = MortuaryStorage.objects.all()
    pending_pm = PostMortemRequest.objects.filter(
        status__in=[PostMortemStatus.REQUESTED, PostMortemStatus.APPROVED]
    ).select_related('admission')

    stats = {
        'total_bodies': bodies.count(),
        'in_storage': bodies.filter(status=BodyStatus.IN_STORAGE).count(),
        'awaiting_pm': bodies.filter(status=BodyStatus.POST_MORTEM).count(),
        'released': bodies.filter(status=BodyStatus.RELEASED).count(),
        'total_compartments': storage.count(),
        'available_compartments': storage.filter(status=StorageStatus.AVAILABLE).count(),
    }

    recent_admissions = bodies.select_related('patient', 'received_by')[:10]
    context = {
        'stats': stats,
        'recent_admissions': recent_admissions,
        'pending_pm': pending_pm[:5],
        'storage': storage.select_related('current_body'),
    }
    return render(request, 'mortuary/dashboard.html', context)


@login_required
def admission_list(request):
    if not _can_access(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    admissions = MortuaryAdmission.objects.filter(is_deleted=False).select_related('patient', 'received_by')
    status_filter = request.GET.get('status', '')
    q = request.GET.get('q', '')
    if status_filter:
        admissions = admissions.filter(status=status_filter)
    if q:
        admissions = admissions.filter(
            Q(full_name__icontains=q) | Q(body_number__icontains=q)
            | Q(next_of_kin_name__icontains=q)
        )

    context = {
        'admissions': admissions,
        'status_choices': BodyStatus.choices,
        'status_filter': status_filter,
        'q': q,
    }
    return render(request, 'mortuary/admission_list.html', context)


@login_required
def admission_create(request):
    if not _can_access(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    if request.method == 'POST':
        adm = MortuaryAdmission(
            full_name=request.POST.get('full_name'),
            age_years=request.POST.get('age_years') or None,
            gender=request.POST.get('gender', 'U'),
            date_of_death=request.POST.get('date_of_death'),
            place_of_death=request.POST.get('place_of_death', ''),
            cause_of_death=request.POST.get('cause_of_death', 'PENDING'),
            provisional_cause_text=request.POST.get('provisional_cause_text', ''),
            body_condition=request.POST.get('body_condition', 'GOOD'),
            identifying_marks=request.POST.get('identifying_marks', ''),
            next_of_kin_name=request.POST.get('next_of_kin_name', ''),
            next_of_kin_phone=request.POST.get('next_of_kin_phone', ''),
            next_of_kin_relationship=request.POST.get('next_of_kin_relationship', ''),
            police_case_number=request.POST.get('police_case_number', ''),
            doctor_who_certified=request.POST.get('doctor_who_certified', ''),
            notes=request.POST.get('notes', ''),
            received_by=request.user,
            created_by=request.user,
        )
        adm.save()
        messages.success(request, f'Body received. Reference: {adm.body_number}')
        return redirect('mortuary:admission_detail', pk=adm.pk)

    context = {
        'cause_choices': CauseOfDeath.choices,
    }
    return render(request, 'mortuary/admission_form.html', context)


@login_required
def admission_detail(request, pk):
    if not _can_access(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    adm = get_object_or_404(MortuaryAdmission, pk=pk, is_deleted=False)
    storage = getattr(adm, 'storage_compartment', None)
    post_mortem = getattr(adm, 'post_mortem', None)
    release = getattr(adm, 'release', None)

    # Storage assignment form
    available_compartments = MortuaryStorage.objects.filter(status=StorageStatus.AVAILABLE)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'assign_storage' and _can_manage(request.user):
            comp_id = request.POST.get('compartment')
            if comp_id:
                comp = get_object_or_404(MortuaryStorage, pk=comp_id)
                # Release previous if any
                if storage:
                    storage.current_body = None
                    storage.status = StorageStatus.AVAILABLE
                    storage.save()
                comp.current_body = adm
                comp.status = StorageStatus.OCCUPIED
                comp.save()
                adm.status = BodyStatus.IN_STORAGE
                adm.updated_by = request.user
                adm.save()
                messages.success(request, f'Assigned to compartment {comp.compartment_number}.')
        elif action == 'update_status' and _can_manage(request.user):
            new_status = request.POST.get('status')
            if new_status in BodyStatus.values:
                adm.status = new_status
                adm.updated_by = request.user
                adm.save()
                messages.success(request, 'Status updated.')
        return redirect('mortuary:admission_detail', pk=pk)

    context = {
        'adm': adm,
        'storage': storage,
        'post_mortem': post_mortem,
        'release': release,
        'available_compartments': available_compartments,
        'status_choices': BodyStatus.choices,
        'can_manage': _can_manage(request.user),
    }
    return render(request, 'mortuary/admission_detail.html', context)


@login_required
def postmortem_create(request, admission_id):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    adm = get_object_or_404(MortuaryAdmission, pk=admission_id, is_deleted=False)

    if hasattr(adm, 'post_mortem'):
        messages.warning(request, 'A post-mortem request already exists for this body.')
        return redirect('mortuary:admission_detail', pk=admission_id)

    if request.method == 'POST':
        pm = PostMortemRequest(
            admission=adm,
            pm_type=request.POST.get('pm_type'),
            reason=request.POST.get('reason', ''),
            pathologist=request.POST.get('pathologist', ''),
            scheduled_at=request.POST.get('scheduled_at') or None,
            requested_by=request.user,
            created_by=request.user,
        )
        pm.save()
        adm.status = BodyStatus.POST_MORTEM
        adm.updated_by = request.user
        adm.save()
        messages.success(request, 'Post-mortem request submitted.')
        return redirect('mortuary:admission_detail', pk=admission_id)

    context = {
        'adm': adm,
        'pm_type_choices': PostMortemType.choices,
    }
    return render(request, 'mortuary/postmortem_form.html', context)


@login_required
def postmortem_update(request, pk):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    pm = get_object_or_404(PostMortemRequest, pk=pk, is_deleted=False)

    if request.method == 'POST':
        pm.status = request.POST.get('status', pm.status)
        pm.pathologist = request.POST.get('pathologist', pm.pathologist)
        pm.findings = request.POST.get('findings', pm.findings)
        pm.final_cause_of_death = request.POST.get('final_cause_of_death', pm.final_cause_of_death)
        pm.report_reference = request.POST.get('report_reference', pm.report_reference)
        if pm.status == PostMortemStatus.IN_PROGRESS and not pm.started_at:
            pm.started_at = timezone.now()
        if pm.status == PostMortemStatus.COMPLETED and not pm.completed_at:
            pm.completed_at = timezone.now()
            if pm.final_cause_of_death:
                adm = pm.admission
                adm.cause_of_death = CauseOfDeath.NATURAL  # default; staff can override
                adm.provisional_cause_text = pm.final_cause_of_death
                adm.updated_by = request.user
                adm.save()
        pm.updated_by = request.user
        pm.save()
        messages.success(request, 'Post-mortem record updated.')
    return redirect('mortuary:admission_detail', pk=pm.admission_id)


@login_required
def release_create(request, admission_id):
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    adm = get_object_or_404(MortuaryAdmission, pk=admission_id, is_deleted=False)

    if hasattr(adm, 'release'):
        messages.warning(request, 'Body has already been released.')
        return redirect('mortuary:admission_detail', pk=admission_id)

    if request.method == 'POST':
        rel = BodyRelease(
            admission=adm,
            released_to_name=request.POST.get('released_to_name', ''),
            released_to_id_type=request.POST.get('released_to_id_type', ''),
            released_to_id_number=request.POST.get('released_to_id_number', ''),
            released_to_phone=request.POST.get('released_to_phone', ''),
            relationship=request.POST.get('relationship', ''),
            funeral_home=request.POST.get('funeral_home', ''),
            transport_provider=request.POST.get('transport_provider', ''),
            death_certificate_issued='death_certificate_issued' in request.POST,
            certificate_number=request.POST.get('certificate_number', ''),
            notes=request.POST.get('notes', ''),
            released_by=request.user,
            created_by=request.user,
        )
        rel.save()
        # Free storage compartment
        storage = getattr(adm, 'storage_compartment', None)
        if storage:
            storage.current_body = None
            storage.status = StorageStatus.AVAILABLE
            storage.save()
        adm.status = BodyStatus.RELEASED
        adm.updated_by = request.user
        adm.save()
        messages.success(request, f'Body released to {rel.released_to_name}.')
        return redirect('mortuary:admission_detail', pk=admission_id)

    context = {'adm': adm}
    return render(request, 'mortuary/release_form.html', context)


@login_required
def storage_list(request):
    if not _can_access(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    compartments = MortuaryStorage.objects.select_related('current_body')
    context = {
        'compartments': compartments,
        'can_manage': _can_manage(request.user),
    }
    return render(request, 'mortuary/storage_list.html', context)


@login_required
def storage_manage(request):
    """Add/edit storage compartments."""
    if not _can_manage(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            MortuaryStorage.objects.create(
                compartment_number=request.POST.get('compartment_number'),
                section=request.POST.get('section', ''),
                temperature_celsius=request.POST.get('temperature_celsius') or None,
                notes=request.POST.get('notes', ''),
            )
            messages.success(request, 'Compartment added.')
        elif action == 'update_temp':
            comp_id = request.POST.get('compartment_id')
            temp = request.POST.get('temperature_celsius')
            MortuaryStorage.objects.filter(pk=comp_id).update(
                temperature_celsius=temp or None
            )
            messages.success(request, 'Temperature updated.')
        return redirect('mortuary:storage_list')

    return redirect('mortuary:storage_list')
