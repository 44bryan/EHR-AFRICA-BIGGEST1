from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q

from apps.accounts.models import UserRole
from apps.ipd.models import Admission
from .models import (
    DietOrder, DietOrderStatus, DietaryRestriction,
    NutritionalAssessment, MealPlan, MealItem, DietType
)


def _is_dietary_staff(user):
    return user.role in [
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR, UserRole.MEDICAL_DIRECTOR,
        UserRole.NURSE, UserRole.WARD_NURSE, UserRole.CONSULTATION_NURSE, UserRole.NURSE_DIRECTOR,
        UserRole.GENERAL_PHYSICIAN, UserRole.OPHTHALMOLOGIST, UserRole.ORTHOPTIST,
    ]


def _is_nutritionist(user):
    """Nutritionists are mapped to ADMIN role for now (no dedicated role)."""
    return user.role in [
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR, UserRole.MEDICAL_DIRECTOR,
        UserRole.NURSE_DIRECTOR,
    ]


@login_required
def dashboard(request):
    if not _is_dietary_staff(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    active_orders = DietOrder.objects.filter(
        status=DietOrderStatus.ACTIVE, is_deleted=False
    ).select_related('admission__patient', 'ordered_by')

    today = timezone.localdate()
    todays_plans = MealPlan.objects.filter(
        plan_date=today, is_deleted=False
    ).select_related('diet_order__admission__patient')

    unserved_today = todays_plans.filter(served=False).count()
    npo_count = active_orders.filter(diet_type=DietType.NPO).count()

    stats = {
        'active_orders': active_orders.count(),
        'todays_plans': todays_plans.count(),
        'unserved_today': unserved_today,
        'npo_count': npo_count,
    }

    context = {
        'stats': stats,
        'active_orders': active_orders[:10],
        'todays_plans': todays_plans[:10],
    }
    return render(request, 'dietary/dashboard.html', context)


@login_required
def order_list(request):
    if not _is_dietary_staff(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    orders = DietOrder.objects.filter(is_deleted=False).select_related(
        'admission__patient', 'ordered_by'
    )

    status_filter = request.GET.get('status', '')
    if status_filter:
        orders = orders.filter(status=status_filter)

    diet_filter = request.GET.get('diet', '')
    if diet_filter:
        orders = orders.filter(diet_type=diet_filter)

    context = {
        'orders': orders,
        'status_choices': DietOrderStatus.choices,
        'diet_choices': DietType.choices,
        'status_filter': status_filter,
        'diet_filter': diet_filter,
    }
    return render(request, 'dietary/order_list.html', context)


@login_required
def order_create(request):
    if not _is_dietary_staff(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    admissions = Admission.objects.filter(
        status='ADMITTED', is_deleted=False
    ).select_related('patient').order_by('patient__first_name')

    if request.method == 'POST':
        admission_id = request.POST.get('admission')
        diet_type = request.POST.get('diet_type')
        admission = get_object_or_404(Admission, pk=admission_id, is_deleted=False)

        order = DietOrder(
            admission=admission,
            diet_type=diet_type,
            diet_type_other=request.POST.get('diet_type_other', ''),
            calorie_target=request.POST.get('calorie_target') or None,
            protein_target=request.POST.get('protein_target') or None,
            fluid_restriction=request.POST.get('fluid_restriction') or None,
            special_instructions=request.POST.get('special_instructions', ''),
            ordered_by=request.user,
            created_by=request.user,
        )
        order.save()
        messages.success(request, 'Diet order created.')
        return redirect('dietary:order_detail', pk=order.pk)

    context = {
        'admissions': admissions,
        'diet_choices': DietType.choices,
    }
    return render(request, 'dietary/order_form.html', context)


@login_required
def order_detail(request, pk):
    if not _is_dietary_staff(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    order = get_object_or_404(DietOrder, pk=pk, is_deleted=False)
    restrictions = DietaryRestriction.objects.filter(admission=order.admission)
    meal_plans = order.meal_plans.filter(is_deleted=False).prefetch_related('items')
    assessments = NutritionalAssessment.objects.filter(
        admission=order.admission, is_deleted=False
    ).select_related('assessed_by')

    if request.method == 'POST' and 'update_status' in request.POST:
        new_status = request.POST.get('status')
        if new_status in DietOrderStatus.values:
            order.status = new_status
            order.updated_by = request.user
            order.save()
            messages.success(request, f'Order status updated to {order.get_status_display()}.')
        return redirect('dietary:order_detail', pk=pk)

    context = {
        'order': order,
        'restrictions': restrictions,
        'meal_plans': meal_plans,
        'assessments': assessments,
        'status_choices': DietOrderStatus.choices,
    }
    return render(request, 'dietary/order_detail.html', context)


@login_required
def restriction_add(request, admission_id):
    if not _is_dietary_staff(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    admission = get_object_or_404(Admission, pk=admission_id, is_deleted=False)

    if request.method == 'POST':
        DietaryRestriction.objects.create(
            admission=admission,
            category=request.POST.get('category'),
            description=request.POST.get('description', ''),
            severity=request.POST.get('severity', 'MILD'),
            recorded_by=request.user,
        )
        messages.success(request, 'Dietary restriction recorded.')
        next_url = request.POST.get('next', '')
        if next_url:
            return redirect(next_url)
        return redirect('dietary:dashboard')

    from .models import AllergyCategory
    context = {
        'admission': admission,
        'category_choices': AllergyCategory.choices,
    }
    return render(request, 'dietary/restriction_form.html', context)


@login_required
def assessment_create(request, admission_id):
    if not _is_dietary_staff(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    admission = get_object_or_404(Admission, pk=admission_id, is_deleted=False)

    if request.method == 'POST':
        assessment = NutritionalAssessment(
            admission=admission,
            weight_kg=request.POST.get('weight_kg'),
            height_cm=request.POST.get('height_cm'),
            must_score=request.POST.get('must_score', 0),
            nutritional_status=request.POST.get('nutritional_status', 'NORMAL'),
            appetite=request.POST.get('appetite', 'GOOD'),
            feeding_route=request.POST.get('feeding_route', 'ORAL'),
            notes=request.POST.get('notes', ''),
            assessed_by=request.user,
            created_by=request.user,
        )
        assessment.save()
        messages.success(request, 'Nutritional assessment saved.')
        next_url = request.POST.get('next', '')
        if next_url:
            return redirect(next_url)
        return redirect('dietary:dashboard')

    from .models import NutritionalStatus
    context = {
        'admission': admission,
        'nutritional_status_choices': NutritionalStatus.choices,
    }
    return render(request, 'dietary/assessment_form.html', context)


@login_required
def meal_plan_create(request, order_id):
    if not _is_dietary_staff(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    order = get_object_or_404(DietOrder, pk=order_id, is_deleted=False)

    if request.method == 'POST':
        plan_date = request.POST.get('plan_date')
        plan = MealPlan(
            diet_order=order,
            plan_date=plan_date,
            total_calories=request.POST.get('total_calories') or None,
            notes=request.POST.get('notes', ''),
            prepared_by=request.user,
            created_by=request.user,
        )
        plan.save()

        # Create meal items from POST arrays
        descriptions = request.POST.getlist('description[]')
        meal_times = request.POST.getlist('meal_time[]')
        calories = request.POST.getlist('calories_kcal[]')
        proteins = request.POST.getlist('protein_g[]')
        carbs = request.POST.getlist('carbs_g[]')
        fats = request.POST.getlist('fat_g[]')

        for i, desc in enumerate(descriptions):
            if desc.strip():
                MealItem.objects.create(
                    meal_plan=plan,
                    meal_time=meal_times[i] if i < len(meal_times) else 'BREAKFAST',
                    description=desc.strip(),
                    calories_kcal=calories[i] if i < len(calories) and calories[i] else None,
                    protein_g=proteins[i] if i < len(proteins) and proteins[i] else None,
                    carbs_g=carbs[i] if i < len(carbs) and carbs[i] else None,
                    fat_g=fats[i] if i < len(fats) and fats[i] else None,
                )

        messages.success(request, 'Meal plan created.')
        return redirect('dietary:order_detail', pk=order_id)

    from .models import MealTime
    context = {
        'order': order,
        'meal_time_choices': MealTime.choices,
        'today': timezone.localdate(),
    }
    return render(request, 'dietary/meal_plan_form.html', context)


@login_required
def meal_plan_serve(request, pk):
    if not _is_dietary_staff(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    plan = get_object_or_404(MealPlan, pk=pk, is_deleted=False)
    if request.method == 'POST':
        plan.served = True
        plan.served_at = timezone.now()
        plan.updated_by = request.user
        plan.save()
        messages.success(request, 'Meal plan marked as served.')
    return redirect('dietary:order_detail', pk=plan.diet_order_id)
