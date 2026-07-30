from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden
from django.utils import timezone
from django.db.models import Sum, Count, Q
from .models import OutreachActivity, OutreachRecord, OutreachStatus, OutreachType


def _can_manage(user):
    return (user.is_super_admin or user.is_medical_director
            or user.is_admin_staff or user.can_see_everything)


@login_required
def dashboard(request):
    today = timezone.localdate()
    year = today.year

    activities = OutreachActivity.objects.prefetch_related('records', 'team_members')
    upcoming = activities.filter(
        status=OutreachStatus.PLANNED, activity_date__gte=today
    ).order_by('activity_date')[:5]
    recent = activities.filter(
        status=OutreachStatus.COMPLETED
    ).order_by('-activity_date')[:5]
    in_progress = activities.filter(status=OutreachStatus.IN_PROGRESS)

    # This year's totals
    yearly = OutreachRecord.objects.filter(activity__activity_date__year=year)
    yearly_agg = yearly.aggregate(
        screened=Sum('total_screened'),
        treated=Sum('total_treated'),
        referred=Sum('total_referred'),
        surgeries=Sum('surgeries_performed'),
        glasses=Sum('glasses_dispensed'),
        camps=Count('activity', distinct=True),
    )

    # By type this year
    by_type = (
        OutreachActivity.objects.filter(activity_date__year=year)
        .values('activity_type')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    type_label = dict(OutreachType.choices)
    for t in by_type:
        t['label'] = type_label.get(t['activity_type'], t['activity_type'])

    # Monthly trend this year (screened)
    monthly = []
    for m in range(1, 13):
        agg = OutreachRecord.objects.filter(
            activity__activity_date__year=year,
            record_date__month=m,
        ).aggregate(s=Sum('total_screened'))
        monthly.append(agg['s'] or 0)

    return render(request, 'outreach/dashboard.html', {
        'upcoming': upcoming,
        'recent': recent,
        'in_progress': in_progress,
        'yearly_agg': yearly_agg,
        'by_type': list(by_type),
        'monthly_labels': ['Jan','Feb','Mar','Apr','May','Jun',
                           'Jul','Aug','Sep','Oct','Nov','Dec'],
        'monthly_data': monthly,
        'year': year,
        'today': today,
        'total_activities_year': OutreachActivity.objects.filter(
            activity_date__year=year).count(),
    })


@login_required
def activity_list(request):
    qs = OutreachActivity.objects.prefetch_related('records').select_related('team_leader')
    status_f = request.GET.get('status', '')
    type_f   = request.GET.get('type', '')
    year_f   = request.GET.get('year', str(timezone.localdate().year))
    if status_f:
        qs = qs.filter(status=status_f)
    if type_f:
        qs = qs.filter(activity_type=type_f)
    if year_f:
        qs = qs.filter(activity_date__year=year_f)
    return render(request, 'outreach/list.html', {
        'activities': qs[:100],
        'status_choices': OutreachStatus.choices,
        'type_choices': OutreachType.choices,
        'status_f': status_f,
        'type_f': type_f,
        'year_f': year_f,
    })


@login_required
def activity_create(request):
    if not _can_manage(request.user):
        return HttpResponseForbidden()
    if request.method == 'POST':
        p = request.POST
        act = OutreachActivity.objects.create(
            title=p.get('title', '').strip(),
            activity_type=p.get('activity_type', OutreachType.EYE_CAMP),
            status=OutreachStatus.PLANNED,
            location_name=p.get('location_name', '').strip(),
            region=p.get('region', '').strip(),
            town=p.get('town', '').strip(),
            gps_coordinates=p.get('gps_coordinates', '').strip(),
            activity_date=p.get('activity_date'),
            end_date=p.get('end_date') or None,
            start_time=p.get('start_time') or None,
            end_time=p.get('end_time') or None,
            partner_org=p.get('partner_org', '').strip(),
            sponsor=p.get('sponsor', '').strip(),
            sponsor_amount=p.get('sponsor_amount', 0) or 0,
            objectives=p.get('objectives', '').strip(),
            vehicle_details=p.get('vehicle_details', '').strip(),
            equipment_notes=p.get('equipment_notes', '').strip(),
            created_by=request.user,
        )
        # Team leader
        leader_id = p.get('team_leader')
        if leader_id:
            from apps.accounts.models import User
            try:
                act.team_leader = User.objects.get(pk=leader_id)
                act.save(update_fields=['team_leader'])
            except User.DoesNotExist:
                pass
        messages.success(request, f'Outreach activity "{act.title}" created.')
        return redirect('outreach:detail', pk=act.pk)
    from apps.accounts.models import User
    staff = User.objects.filter(is_active=True).order_by('last_name')
    return render(request, 'outreach/create.html', {
        'type_choices': OutreachType.choices,
        'staff': staff,
    })


@login_required
def activity_detail(request, pk):
    act = get_object_or_404(OutreachActivity, pk=pk)
    records = act.records.select_related('recorded_by').order_by('record_date')
    totals = records.aggregate(
        screened=Sum('total_screened'),
        treated=Sum('total_treated'),
        referred=Sum('total_referred'),
        surgeries=Sum('surgeries_performed'),
        glasses=Sum('glasses_dispensed'),
        cost=Sum('drugs_cost') + Sum('transport_cost') + Sum('other_cost'),
    )
    return render(request, 'outreach/detail.html', {
        'act': act,
        'records': records,
        'totals': totals,
        'can_manage': _can_manage(request.user),
    })


@login_required
def activity_edit(request, pk):
    if not _can_manage(request.user):
        return HttpResponseForbidden()
    act = get_object_or_404(OutreachActivity, pk=pk)
    if request.method == 'POST':
        p = request.POST
        act.title          = p.get('title', act.title).strip()
        act.activity_type  = p.get('activity_type', act.activity_type)
        act.status         = p.get('status', act.status)
        act.location_name  = p.get('location_name', act.location_name).strip()
        act.region         = p.get('region', '').strip()
        act.town           = p.get('town', '').strip()
        act.activity_date  = p.get('activity_date', act.activity_date)
        act.end_date       = p.get('end_date') or None
        act.partner_org    = p.get('partner_org', '').strip()
        act.sponsor        = p.get('sponsor', '').strip()
        act.sponsor_amount = p.get('sponsor_amount', 0) or 0
        act.objectives     = p.get('objectives', '').strip()
        act.notes          = p.get('notes', '').strip()
        act.challenges     = p.get('challenges', '').strip()
        act.recommendations= p.get('recommendations', '').strip()
        act.save()
        messages.success(request, 'Activity updated.')
        return redirect('outreach:detail', pk=act.pk)
    from apps.accounts.models import User
    staff = User.objects.filter(is_active=True).order_by('last_name')
    return render(request, 'outreach/edit.html', {
        'act': act,
        'type_choices': OutreachType.choices,
        'status_choices': OutreachStatus.choices,
        'staff': staff,
    })


@login_required
def record_add(request, pk):
    """Add a daily statistics record for an outreach activity."""
    act = get_object_or_404(OutreachActivity, pk=pk)
    if request.method == 'POST':
        p = request.POST
        rec_date = p.get('record_date', str(timezone.localdate()))
        existing = OutreachRecord.objects.filter(activity=act, record_date=rec_date).first()
        if existing:
            messages.warning(request, f'A record for {rec_date} already exists. Edit it instead.')
            return redirect('outreach:detail', pk=act.pk)

        OutreachRecord.objects.create(
            activity=act,
            record_date=rec_date,
            recorded_by=request.user,
            total_screened    =int(p.get('total_screened', 0) or 0),
            male_screened     =int(p.get('male_screened', 0) or 0),
            female_screened   =int(p.get('female_screened', 0) or 0),
            children_screened =int(p.get('children_screened', 0) or 0),
            elderly_screened  =int(p.get('elderly_screened', 0) or 0),
            normal_vision     =int(p.get('normal_vision', 0) or 0),
            refractive_errors =int(p.get('refractive_errors', 0) or 0),
            cataract          =int(p.get('cataract', 0) or 0),
            glaucoma_suspects =int(p.get('glaucoma_suspects', 0) or 0),
            diabetic_retinopathy=int(p.get('diabetic_retinopathy', 0) or 0),
            pterygium         =int(p.get('pterygium', 0) or 0),
            trachoma          =int(p.get('trachoma', 0) or 0),
            corneal_opacity   =int(p.get('corneal_opacity', 0) or 0),
            other_pathology   =int(p.get('other_pathology', 0) or 0),
            glasses_dispensed =int(p.get('glasses_dispensed', 0) or 0),
            medications_given =int(p.get('medications_given', 0) or 0),
            surgeries_performed=int(p.get('surgeries_performed', 0) or 0),
            total_treated     =int(p.get('total_treated', 0) or 0),
            total_referred    =int(p.get('total_referred', 0) or 0),
            referred_cataract =int(p.get('referred_cataract', 0) or 0),
            referred_glaucoma =int(p.get('referred_glaucoma', 0) or 0),
            referred_retina   =int(p.get('referred_retina', 0) or 0),
            referred_other    =int(p.get('referred_other', 0) or 0),
            drugs_cost        =p.get('drugs_cost', 0) or 0,
            transport_cost    =p.get('transport_cost', 0) or 0,
            other_cost        =p.get('other_cost', 0) or 0,
            notes             =p.get('notes', '').strip(),
            created_by        =request.user,
        )
        # Auto-mark activity as completed if end_date reached
        if act.end_date and rec_date >= str(act.end_date):
            act.status = OutreachStatus.COMPLETED
            act.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Statistics record saved.')
        return redirect('outreach:detail', pk=act.pk)
    return render(request, 'outreach/record_form.html', {
        'act': act,
        'today': timezone.localdate(),
    })


@login_required
def stats_view(request):
    """Annual and monthly outreach statistics for management reports."""
    if not _can_manage(request.user):
        return HttpResponseForbidden()
    today = timezone.localdate()
    year = int(request.GET.get('year', today.year))

    records = OutreachRecord.objects.filter(activity__activity_date__year=year)
    activities_qs = OutreachActivity.objects.filter(activity_date__year=year)

    totals = records.aggregate(
        screened=Sum('total_screened'),
        male=Sum('male_screened'),
        female=Sum('female_screened'),
        children=Sum('children_screened'),
        elderly=Sum('elderly_screened'),
        treated=Sum('total_treated'),
        referred=Sum('total_referred'),
        surgeries=Sum('surgeries_performed'),
        glasses=Sum('glasses_dispensed'),
        ref_cataract=Sum('referred_cataract'),
        ref_glaucoma=Sum('referred_glaucoma'),
        ref_retina=Sum('referred_retina'),
        ref_other=Sum('referred_other'),
        cost_drugs=Sum('drugs_cost'),
        cost_transport=Sum('transport_cost'),
        cost_other=Sum('other_cost'),
    )

    # Pathology breakdown totals
    path_totals = records.aggregate(
        normal=Sum('normal_vision'),
        refractive=Sum('refractive_errors'),
        cataract=Sum('cataract'),
        glaucoma=Sum('glaucoma_suspects'),
        dr=Sum('diabetic_retinopathy'),
        pterygium=Sum('pterygium'),
        trachoma=Sum('trachoma'),
        corneal=Sum('corneal_opacity'),
        other=Sum('other_pathology'),
    )

    # Monthly breakdown
    monthly = []
    for m in range(1, 13):
        agg = records.filter(record_date__month=m).aggregate(
            s=Sum('total_screened'), t=Sum('total_treated'), r=Sum('total_referred')
        )
        monthly.append({
            'month': m,
            'screened': agg['s'] or 0,
            'treated': agg['t'] or 0,
            'referred': agg['r'] or 0,
        })

    # By activity type
    by_type = []
    for at, label in OutreachType.choices:
        agg = records.filter(activity__activity_type=at).aggregate(
            count=Count('id'), s=Sum('total_screened'), t=Sum('total_treated')
        )
        if agg['count']:
            by_type.append({'type': at, 'label': label, **agg})

    return render(request, 'outreach/stats.html', {
        'year': year,
        'totals': totals,
        'path_totals': path_totals,
        'monthly': monthly,
        'by_type': by_type,
        'activities_count': activities_qs.count(),
        'completed_count': activities_qs.filter(status=OutreachStatus.COMPLETED).count(),
        'today': today,
    })
