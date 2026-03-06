"""
Notification views – unread count, recent notifications, mark as read.
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from core.models import Notification, Message
from core.services import NotificationService

@login_required
def notifications(request):
    """View to list all notifications for the user."""
    # Get notifications as a list to preserve unread state for this specific view
    notifications_list = list(Notification.objects.filter(recipient=request.user).order_by('-created_at'))
    
    # Mark all as read so the header badge clears
    NotificationService.mark_all_as_read(request.user)
    
    base_template = 'core/client_master.html'
    if hasattr(request.user, 'freelancer'):
        base_template = 'core/freelancer_master.html'
    
    return render(request, 'core/notifications.html', {
        'notifications': notifications_list,
        'base_template': base_template
    })


@login_required
def api_unread_notifications_count(request):
    """API to get unread notifications and messages count."""
    notification_count = NotificationService.get_unread_count(request.user)
    
    # Message unread count (excluding muted conversations)
    message_count = Message.objects.filter(
        conversation__chatparticipant__user=request.user,
        conversation__chatparticipant__is_muted=False,
        is_read=False
    ).exclude(sender=request.user).distinct().count()
    
    return JsonResponse({
        'notification_count': notification_count,
        'message_count': message_count,
        'total_count': notification_count + message_count
    })


@login_required
def api_get_recent_notifications(request):
    """API to get the latest 5 notifications."""
    notifications = NotificationService.get_recent_notifications(request.user)
    
    data = []
    for n in notifications:
        data.append({ 
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'link': n.link,
            'is_read': n.is_read,
            'created_at': n.created_at.strftime('%Y-%m-%d %H:%M'),
            'type': n.notification_type
        })
    
    return JsonResponse({'notifications': data})


@login_required
def api_mark_all_notifications_as_read(request):
    """API to mark all notifications as read."""
    if request.method == 'POST':
        NotificationService.mark_all_as_read(request.user)
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)
