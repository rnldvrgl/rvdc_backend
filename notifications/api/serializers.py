from django.utils import timezone
from django.utils.timesince import timesince
from notifications.models import Notification
from rest_framework import serializers


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for Notification model."""

    relative_time = serializers.SerializerMethodField()
    formatted_date = serializers.SerializerMethodField()
    type_display = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "type",
            "type_display",
            "title",
            "message",
            "data",
            "is_read",
            "created_at",
            "relative_time",
            "formatted_date",
        ]
        read_only_fields = [
            "id",
            "created_at",
        ]

    def get_formatted_date(self, obj):
        """Get formatted date string (e.g. 'Jan 15, 2025 at 10:30 AM')."""
        local_time = timezone.localtime(obj.created_at)
        return local_time.strftime("%b %d, %Y at %I:%M %p")

    def get_relative_time(self, obj):
        """Get human-readable relative time."""
        now = timezone.now()
        diff = now - obj.created_at
        total_seconds = int(diff.total_seconds())

        if total_seconds < 60:
            return "Just now"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif total_seconds < 604800:
            days = total_seconds // 86400
            return f"{days} day{'s' if days != 1 else ''} ago"
        else:
            return timesince(obj.created_at, now) + " ago"
