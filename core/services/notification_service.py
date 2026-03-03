from core.models import Notification
from django.urls import reverse

class NotificationService:
    @staticmethod
    def create_notification(recipient, notification_type, title, message, link=None):
        """Create a notification for a user if their settings allow it."""
        from core.models import NotificationSetting
        
        # Get or create settings for the user
        settings, _ = NotificationSetting.objects.get_or_create(user=recipient)
        
        # Map notification type to setting field
        should_send = True
        
        if 'payment' in notification_type or 'topup' in notification_type or 'withdrawal' in notification_type:
            should_send = settings.payment_notifications
        elif 'project' in notification_type or 'milestone' in notification_type or 'proposal' in notification_type:
            should_send = settings.project_updates
        elif 'review' in notification_type:
            should_send = settings.review_notifications
            
        if not should_send:
            return None

        return Notification.objects.create(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            message=message,
            link=link
        )

    @staticmethod
    def get_unread_count(user):
        """Get the count of unread notifications for a user."""
        return Notification.objects.filter(recipient=user, is_read=False).count()

    @staticmethod
    def mark_as_read(notification_id, user):
        """Mark a notification as read if it belongs to the user."""
        Notification.objects.filter(id=notification_id, recipient=user).update(is_read=True)

    @staticmethod
    def mark_all_as_read(user):
        """Mark all notifications of a user as read."""
        Notification.objects.filter(recipient=user, is_read=False).update(is_read=True)

    @staticmethod
    def get_recent_notifications(user, limit=5):
        """Get the latest notifications for a user."""
        return Notification.objects.filter(recipient=user).order_by('-created_at')[:limit]
