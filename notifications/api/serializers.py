from notifications.models import Notification
from django.utils.timesince import timesince
from django.utils import timezone
from rest_framework import serializers


class NotificationSerializer(serializers.ModelSerializer):
    relative_time = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "user",
            "type",
            "data",
            "message",
            "is_read",
            "created_at",
            "relative_time",
            "summary",
        ]

    def get_relative_time(self, obj):
        return timesince(obj.created_at, timezone.now()) + " ago"

    def get_summary(self, obj):
        t = obj.type
        d = obj.data
        if t == "expense_created":
            return f"New expense for {d.get('stall')} of {d.get('amount')}"
        elif t == "appointment_reminder":
            return f"Appointment: {d.get('client_name')} at {d.get('time')}"
        elif t == "stock_low":
            return f"Low stock: {d.get('item_name')} ({d.get('remaining')} left)"
        else:
            return obj.message or "Notification"
