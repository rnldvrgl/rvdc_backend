from clients.models import Client
from messaging.models import Conversation, FacebookPage, Message
from rest_framework import serializers


class FacebookPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = FacebookPage
        fields = ["id", "page_id", "page_name", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class MessageSerializer(serializers.ModelSerializer):
    sent_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id",
            "direction",
            "text",
            "fb_message_id",
            "attachments",
            "sent_by",
            "sent_by_name",
            "timestamp",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_sent_by_name(self, obj):
        if obj.sent_by:
            return obj.sent_by.get_full_name() or obj.sent_by.username
        return None


class ConversationListSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    page_name = serializers.CharField(source="page.page_name", read_only=True)

    class Meta:
        model = Conversation
        fields = [
            "id",
            "fb_user_id",
            "fb_user_name",
            "client",
            "client_name",
            "page",
            "page_name",
            "last_message_at",
            "last_message_preview",
            "unread_count",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_client_name(self, obj):
        if obj.client:
            return obj.client.full_name
        return None


class ConversationDetailSerializer(ConversationListSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta(ConversationListSerializer.Meta):
        fields = ConversationListSerializer.Meta.fields + ["messages"]


class SendMessageSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=2000)


class LinkClientSerializer(serializers.Serializer):
    client_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_client_id(self, value):
        if value is not None:
            try:
                Client.objects.get(id=value, is_deleted=False)
            except Client.DoesNotExist:
                raise serializers.ValidationError("Client not found.")
        return value
