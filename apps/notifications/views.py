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
