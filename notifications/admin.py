from django.contrib import admin
from notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "type", "short_message", "is_read", "created_at")
    list_filter = ("type", "is_read", "created_at")
    search_fields = ("user__username", "user__email", "type", "message")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)

    def short_message(self, obj):
        return (
            (obj.message[:50] + "...")
            if obj.message and len(obj.message) > 50
            else obj.message
        )

    short_message.short_description = "Message"
