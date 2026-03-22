from django.contrib import admin

from messaging.models import Conversation, FacebookPage, Message


@admin.register(FacebookPage)
class FacebookPageAdmin(admin.ModelAdmin):
    list_display = ["page_name", "page_id", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["page_name", "page_id"]


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ["fb_message_id", "direction", "text", "timestamp", "sent_by"]
    ordering = ["-timestamp"]


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ["fb_user_name", "fb_user_id", "client", "last_message_at", "unread_count"]
    list_filter = ["page"]
    search_fields = ["fb_user_name", "fb_user_id"]
    raw_id_fields = ["client"]
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["conversation", "direction", "text_preview", "timestamp"]
    list_filter = ["direction"]
    search_fields = ["text", "fb_message_id"]

    @admin.display(description="Text")
    def text_preview(self, obj):
        return obj.text[:80] if obj.text else ""
