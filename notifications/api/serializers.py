from notifications.models import Notification
from django.utils.timesince import timesince
from django.utils import timezone
from rest_framework import serializers


class NotificationSerializer(serializers.ModelSerializer):
    relative_time = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()
    entity_id = serializers.SerializerMethodField()

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
            "entity_id",
        ]

    def get_relative_time(self, obj):
        return timesince(obj.created_at, timezone.now()) + " ago"

    def get_summary(self, obj):
        t = obj.type
        d = obj.data or {}

        if t == "expense_created":
            from_stall = d.get("from_stall")
            to_stall = d.get("to_stall")
            amount = d.get("amount")

            if from_stall and to_stall and amount is not None:
                return (
                    f"Transfer expense: {from_stall} ➔ {to_stall} "
                    f"({self.format_currency(amount)})"
                )
            elif to_stall and amount is not None:
                return f"Expense for {to_stall} ({self.format_currency(amount)})"
            return "New expense recorded."

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

    def get_entity_id(self, obj):
        d = obj.data or {}
        t = obj.type

        if t == "expense_created":
            return d.get("expense_id")
        elif t == "appointment_reminder":
            return d.get("appointment_id")
        elif t == "stock_low" or t == "restock":
            return d.get("stock_id") or d.get("item_id")
        return None

    def format_currency(self, amount):
        return f"₱{amount:,.2f}"
