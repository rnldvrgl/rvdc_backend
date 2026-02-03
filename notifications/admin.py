from django.contrib import admin
from django.utils.html import format_html

from notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "type_badge",
        "priority_badge",
        "short_title",
        "is_read",
        "is_archived",
        "created_at",
    )
    list_filter = (
        "type",
        "priority",
        "is_read",
        "is_archived",
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
        "archived_at",
        "is_expired",
    )

    fieldsets = (
        ("Basic Information", {
            "fields": (
                "user",
                "type",
                "priority",
                "title",
                "message",
            )
        }),
        ("Action/Link", {
            "fields": (
                "action_url",
                "action_text",
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
                "is_archived",
                "archived_at",
            )
        }),
        ("Timestamps", {
            "fields": (
                "created_at",
                "updated_at",
                "expires_at",
                "is_expired",
            )
        }),
    )

    actions = [
        "mark_as_read",
        "mark_as_unread",
        "archive_notifications",
        "unarchive_notifications",
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
            "warranty_claim_created": "#17a2b8",
        }
        color = colors.get(obj.type, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_type_display(),
        )

    type_badge.short_description = "Type"

    def priority_badge(self, obj):
        """Display priority with color coding."""
        colors = {
            "urgent": "#dc3545",
            "high": "#fd7e14",
            "normal": "#28a745",
            "low": "#6c757d",
        }
        color = colors.get(obj.priority, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_priority_display(),
        )

    priority_badge.short_description = "Priority"

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

    def mark_as_unread(self, request, queryset):
        """Mark selected notifications as unread."""
        count = 0
        for notification in queryset:
            if notification.is_read:
                notification.mark_as_unread()
                count += 1
        self.message_user(request, f"{count} notification(s) marked as unread.")

    mark_as_unread.short_description = "Mark selected as unread"

    def archive_notifications(self, request, queryset):
        """Archive selected notifications."""
        count = 0
        for notification in queryset:
            if not notification.is_archived:
                notification.archive()
                count += 1
        self.message_user(request, f"{count} notification(s) archived.")

    archive_notifications.short_description = "Archive selected notifications"

    def unarchive_notifications(self, request, queryset):
        """Unarchive selected notifications."""
        count = 0
        for notification in queryset:
            if notification.is_archived:
                notification.unarchive()
                count += 1
        self.message_user(request, f"{count} notification(s) unarchived.")

    unarchive_notifications.short_description = "Unarchive selected notifications"
