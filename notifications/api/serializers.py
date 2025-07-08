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
        d = obj.data or {}

        if t == "expense_created":
            stall = d.get("stall")
            amount = d.get("amount")
            if stall and amount is not None:
                return f"New expense for {stall} of {self.format_currency(amount)}"
            return "New expense created."

        elif t == "appointment_reminder":
            client = d.get("client_name")
            time = d.get("time")
            if client and time:
                return f"Appointment: {client} at {time}"
            return "Upcoming appointment."

        elif t == "stock_low":
            item = d.get("item_name")
            remaining = d.get("remaining")
            if item and remaining is not None:
                return f"Low stock: {item} ({remaining} left)"
            return "Low stock alert."

        return obj.message or "Notification"

    def format_currency(self, amount):
        # customize this for your local currency
        return f"₱{amount:,.2f}"
