from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden
from .models import Department, DepartmentCode
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
