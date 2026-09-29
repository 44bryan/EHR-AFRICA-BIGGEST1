from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from .models import Notification, PatientMessage, MessageTemplate, MessageType


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(
        recipient=request.user
    ).order_by('-created_at')[:50]
    # Mark all as read when page is opened
    Notification.objects.filter(recipient=request.user, is_read=False).update(
        is_read=True
    )
    return render(request, 'notifications/list.html', {'notifications': notifications})


@login_required
@require_POST
def mark_read(request, pk):
    notif = Notification.objects.filter(pk=pk, recipient=request.user).first()
    if notif:
        notif.mark_read()
    return JsonResponse({'ok': True})


@login_required
def unread_count(request):
    count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({'count': count})


@login_required
def poll_notifications(request):
    """
    Lightweight AJAX poll — returns unread count + latest unread notification
    for the toast popup. Called every 30s by main.js.
    Does NOT mark notifications as read (that only happens on the list page).
    Always returns valid JSON — never 500s to the client.
    """
    try:
        qs = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).order_by('-created_at')
        count = qs.count()
        latest = qs.first()
        return JsonResponse({
            'count': count,
            'latest': {
                'id': latest.pk,
                'title': latest.title or '',
                'message': (latest.message or '')[:120],
                'link': latest.link or '',
                'priority': latest.priority or 'NORMAL',
            } if latest else None,
        })
    except Exception:
        return JsonResponse({'count': 0, 'latest': None})


# ── Patient SMS / WhatsApp Management ────────────────────────────────────────

def _can_send_sms(user):
    from apps.accounts.models import UserRole
    return user.role in [
        UserRole.SUPER_ADMIN, UserRole.ADMIN_DIRECTOR, UserRole.FINANCE_DIRECTOR,
        UserRole.MEDICAL_DIRECTOR, UserRole.RECEPTIONIST, UserRole.NURSE,
        UserRole.WARD_NURSE,
    ]


@login_required
def sms_log(request):
    """Message history — all SMS/WhatsApp sent to patients."""
    if not _can_send_sms(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    q = request.GET.get('q', '').strip()
    channel = request.GET.get('channel', '')
    qs = PatientMessage.objects.select_related('patient', 'sent_by')
    if q:
        qs = qs.filter(
            Q(patient__first_name__icontains=q) |
            Q(patient__last_name__icontains=q) |
            Q(recipient_number__icontains=q)
        )
    if channel:
        qs = qs.filter(channel=channel)

    return render(request, 'notifications/sms_log.html', {
        'messages_log': qs[:150],
        'q': q,
        'channel': channel,
    })


@login_required
def sms_send(request, patient_id=None):
    """Manually send an SMS/WhatsApp to a patient."""
    if not _can_send_sms(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')

    from apps.patients.models import Patient
    patient = None
    if patient_id:
        patient = Patient.objects.filter(pk=patient_id, is_deleted=False).first()

    if request.method == 'POST':
        p = request.POST
        pid = p.get('patient')
        try:
            pat = Patient.objects.get(pk=pid, is_deleted=False)
        except Patient.DoesNotExist:
            messages.error(request, 'Patient not found.')
            return redirect('notifications:sms_send')

        channel = p.get('channel', 'SMS')
        body = p.get('body', '').strip()
        if not body:
            messages.error(request, 'Message body is required.')
            return redirect('notifications:sms_send')

        from .utils import notify_patient_sms, notify_patient_whatsapp
        if channel == 'WHATSAPP':
            notify_patient_whatsapp(pat, body, message_type=p.get('message_type', 'CUSTOM'),
                                    sent_by=request.user)
        else:
            notify_patient_sms(pat, body, message_type=p.get('message_type', 'CUSTOM'),
                               sent_by=request.user)
        messages.success(request, f'{channel} sent to {pat.full_name}.')
        return redirect('notifications:sms_log')

    templates = MessageTemplate.objects.filter(is_active=True)
    patients = Patient.objects.filter(is_deleted=False).order_by('last_name')[:200]
    return render(request, 'notifications/sms_send.html', {
        'patient': patient,
        'patients': patients,
        'templates': templates,
        'message_types': MessageType.choices,
    })


@login_required
def template_list(request):
    if not _can_send_sms(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    tmpls = MessageTemplate.objects.all()
    return render(request, 'notifications/template_list.html', {'templates': tmpls})


@login_required
def template_create(request):
    if not _can_send_sms(request.user):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    if request.method == 'POST':
        p = request.POST
        MessageTemplate.objects.create(
            name=p.get('name', '').strip(),
            channel=p.get('channel', 'SMS'),
            message_type=p.get('message_type', 'CUSTOM'),
            body=p.get('body', '').strip(),
            created_by=request.user,
        )
        messages.success(request, 'Template saved.')
        return redirect('notifications:template_list')
    return render(request, 'notifications/template_form.html', {
        'message_types': MessageType.choices,
    })
