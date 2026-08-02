from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from .models import Notification


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
