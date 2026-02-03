from django.utils import timezone
from django.utils.timesince import timesince
from notifications.models import Notification
from rest_framework import serializers


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for Notification model."""

    relative_time = serializers.SerializerMethodField()
    type_display = serializers.CharField(source="get_type_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "user",
            "type",
            "type_display",
            "priority",
            "priority_display",
            "title",
            "message",
            "data",
            "action_url",
            "action_text",
            "is_read",
            "read_at",
            "is_archived",
            "archived_at",
            "created_at",
            "updated_at",
            "expires_at",
            "is_expired",
            "relative_time",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "read_at",
            "archived_at",
        ]

    def get_relative_time(self, obj):
        """Get human-readable relative time."""
        return timesince(obj.created_at, timezone.now()) + " ago"


class NotificationSummarySerializer(serializers.Serializer):
    """Serializer for notification summary."""

    total_notifications = serializers.IntegerField()
    unread_count = serializers.IntegerField()
    read_count = serializers.IntegerField()
    by_priority = serializers.DictField()
