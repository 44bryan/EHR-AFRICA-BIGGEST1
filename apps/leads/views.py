from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from .models import Lead, LeadActivity, LeadStatus, LeadSource
from apps.accounts.models import User


@login_required
def leads_dashboard(request):
    context = {
        'new_leads': Lead.objects.filter(status=LeadStatus.NEW, is_deleted=False).count(),
        'contacted': Lead.objects.filter(status=LeadStatus.CONTACTED, is_deleted=False).count(),
        'interested': Lead.objects.filter(status=LeadStatus.INTERESTED, is_deleted=False).count(),
        'converted': Lead.objects.filter(status=LeadStatus.CONVERTED, is_deleted=False).count(),
        'follow_up_today': Lead.objects.filter(
            next_follow_up=timezone.localdate(), is_deleted=False
        ).exclude(status__in=[LeadStatus.CONVERTED, LeadStatus.LOST]),
        'recent_leads': Lead.objects.filter(is_deleted=False).select_related(
            'assigned_to'
        ).order_by('-created_at')[:10],
    }
    return render(request, 'leads/dashboard.html', context)


@login_required
def lead_list(request):
    q = request.GET.get('q', '')
    status = request.GET.get('status', '')
    source = request.GET.get('source', '')
    leads = Lead.objects.filter(is_deleted=False)
    if q:
        leads = leads.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(phone__icontains=q)
        )
    if status:
        leads = leads.filter(status=status)
    if source:
        leads = leads.filter(source=source)
    return render(request, 'leads/lead_list.html', {
        'leads': leads.select_related('assigned_to').order_by('-created_at'),
        'search': q, 'status': status, 'source': source,
        'statuses': LeadStatus.choices,
        'sources': LeadSource.choices,
        'today': timezone.localdate(),
    })


@login_required
def lead_detail(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id, is_deleted=False)
    activities = lead.activities.order_by('-created_at')
    return render(request, 'leads/lead_detail.html', {'lead': lead, 'activities': activities})


@login_required
def add_activity(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id, is_deleted=False)
    if request.method == 'POST':
        LeadActivity.objects.create(
            lead=lead,
            activity_type=request.POST.get('activity_type', ''),
            summary=request.POST.get('summary', ''),
            outcome=request.POST.get('outcome', ''),
            next_action=request.POST.get('next_action', ''),
            performed_by=request.user,
        )
        # Update status if provided
        new_status = request.POST.get('new_status')
        if new_status:
            lead.status = new_status
        next_follow_up = request.POST.get('next_follow_up')
        if next_follow_up:
            lead.next_follow_up = next_follow_up
        lead.save()
        messages.success(request, 'Activity logged.')
        return redirect('leads:lead_detail', lead_id=lead.id)
    return render(request, 'leads/add_activity.html', {
        'lead': lead,
        'statuses': LeadStatus.choices,
    })


@login_required
def lead_create(request):
    staff = User.objects.filter(is_active=True).order_by('first_name')
    if request.method == 'POST':
        lead = Lead.objects.create(
            first_name=request.POST.get('first_name', ''),
            last_name=request.POST.get('last_name', ''),
            phone=request.POST.get('phone', ''),
            email=request.POST.get('email', ''),
            age=request.POST.get('age') or None,
            source=request.POST.get('source', ''),
            inquiry=request.POST.get('inquiry', ''),
            priority=request.POST.get('priority', 0),
            next_follow_up=request.POST.get('next_follow_up') or None,
            assigned_to_id=request.POST.get('assigned_to') or None,
            created_by=request.user,
        )
        messages.success(request, f'Lead created for {lead.full_name}.')
        return redirect('leads:lead_detail', lead_id=lead.id)
    return render(request, 'leads/lead_form.html', {
        'sources': LeadSource.choices,
        'staff': staff,
        'title': 'New Lead',
    })


@login_required
def lead_edit(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id, is_deleted=False)
    staff = User.objects.filter(is_active=True).order_by('first_name')
    if request.method == 'POST':
        lead.first_name = request.POST.get('first_name', lead.first_name)
        lead.last_name = request.POST.get('last_name', lead.last_name)
        lead.phone = request.POST.get('phone', lead.phone)
        lead.email = request.POST.get('email', '')
        lead.age = request.POST.get('age') or None
        lead.source = request.POST.get('source', lead.source)
        lead.inquiry = request.POST.get('inquiry', lead.inquiry)
        lead.priority = request.POST.get('priority', 0)
        lead.next_follow_up = request.POST.get('next_follow_up') or None
        lead.assigned_to_id = request.POST.get('assigned_to') or None
        lead.save()
        messages.success(request, 'Lead updated.')
        return redirect('leads:lead_detail', lead_id=lead.id)
    return render(request, 'leads/lead_form.html', {
        'lead': lead,
        'sources': LeadSource.choices,
        'staff': staff,
        'title': 'Edit Lead',
    })
