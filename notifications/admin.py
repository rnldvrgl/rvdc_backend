from django.contrib import admin
from django.utils.html import format_html

from notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "type_badge",
        "short_title",
        "is_read",
        "created_at",
    )
    list_filter = (
        "type",
        "is_read",
        "created_at",
    )
    search_fields = (
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
        "title",
        "message",
    )
    ordering = ("-created_at",)
    readonly_fields = (
        "created_at",
        "updated_at",
        "read_at",
    )

    fieldsets = (
        ("Basic Information", {
            "fields": (
                "user",
                "type",
                "title",
                "message",
            )
        }),
        ("Additional Data", {
            "fields": ("data",),
            "classes": ("collapse",),
        }),
        ("Status", {
            "fields": (
                "is_read",
                "read_at",
            )
        }),
        ("Timestamps", {
            "fields": (
                "created_at",
                "updated_at",
            )
        }),
    )

    actions = [
        "mark_as_read",
    ]

    def type_badge(self, obj):
        """Display notification type with color coding."""
        colors = {
            "payment_received": "#28a745",
            "payment_overdue": "#dc3545",
            "service_created": "#007bff",
            "service_completed": "#28a745",
            "stock_low": "#ffc107",
            "stock_out": "#dc3545",
            "stock_restocked": "#6f42c1",
            "warranty_claim_created": "#17a2b8",
        }
        color = colors.get(obj.type, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_type_display(),
        )

    type_badge.short_description = "Type"

    def short_title(self, obj):
        """Display shortened title."""
        return (
            (obj.title[:60] + "...")
            if obj.title and len(obj.title) > 60
            else obj.title
        )

    short_title.short_description = "Title"

    def mark_as_read(self, request, queryset):
        """Mark selected notifications as read."""
        count = 0
        for notification in queryset:
            if not notification.is_read:
                notification.mark_as_read()
                count += 1
        self.message_user(request, f"{count} notification(s) marked as read.")

    mark_as_read.short_description = "Mark selected as read"
