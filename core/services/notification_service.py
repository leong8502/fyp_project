from core.models import Notification
from django.urls import reverse

class NotificationService:
    @staticmethod
    def create_notification(recipient, notification_type, title, message, link=None):
        """Create a notification for a user."""
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
