import json
import logging
from datetime import datetime, timezone

from django.http import HttpResponse
from django.utils import timezone as dj_timezone
from django.views.decorators.csrf import csrf_exempt
from messaging.api.serializers import (
    ConversationDetailSerializer,
    ConversationListSerializer,
    LinkClientSerializer,
    SendMessageSerializer,
)
from messaging.models import Conversation, FacebookPage, Message
from messaging.services import get_verify_token, send_message, verify_signature, get_user_profile
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

logger = logging.getLogger(__name__)


# ─── REST API ViewSet ────────────────────────────────────────────────────────


class ConversationViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve conversations with messages."""

    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        qs = Conversation.objects.select_related("client", "page").all()
        search = self.request.query_params.get("search")
        if search:
            from django.db.models import Q

            qs = qs.filter(
                Q(fb_user_name__icontains=search)
                | Q(client__full_name__icontains=search)
            )
        return qs

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ConversationDetailSerializer
        return ConversationListSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Mark conversation as read
        if instance.unread_count > 0:
            instance.unread_count = 0
            instance.save(update_fields=["unread_count"])
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="send")
    def send_reply(self, request, pk=None):
        """Send a reply message to the Facebook user."""
        conversation = self.get_object()
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        text = serializer.validated_data["text"]
        result = send_message(conversation.fb_user_id, text)

        if not result:
            return Response(
                {"detail": "Failed to send message to Facebook."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Store the outgoing message
        now = dj_timezone.now()
        fb_msg_id = result.get("message_id") if isinstance(result, dict) else None
        Message.objects.create(
            conversation=conversation,
            direction="out",
            text=text,
            fb_message_id=fb_msg_id,
            sent_by=request.user,
            timestamp=now,
        )
        conversation.last_message_at = now
        conversation.last_message_preview = text[:255]
        conversation.save(update_fields=["last_message_at", "last_message_preview"])

        return Response({"detail": "Message sent."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="link-client")
    def link_client(self, request, pk=None):
        """Link or unlink a conversation to an existing client."""
        conversation = self.get_object()
        serializer = LinkClientSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client_id = serializer.validated_data.get("client_id")
        if client_id is not None:
            from clients.models import Client

            conversation.client = Client.objects.get(id=client_id)
        else:
            conversation.client = None
        conversation.save(update_fields=["client"])

        return Response(
            ConversationListSerializer(conversation).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        """Mark a conversation as read."""
        conversation = self.get_object()
        conversation.unread_count = 0
        conversation.save(update_fields=["unread_count"])
        return Response({"detail": "Marked as read."})


# ─── Facebook Webhook Endpoints ──────────────────────────────────────────────


@csrf_exempt
def webhook_handler(request):
    """Handle Facebook webhook - verification (GET) and events (POST)."""
    if request.method == "GET":
        return _webhook_verify(request)
    elif request.method == "POST":
        return _webhook_receive(request)
    return HttpResponse("Method not allowed", status=405)


def _webhook_verify(request):
    """Handle Facebook webhook verification (GET)."""
    mode = request.GET.get("hub.mode")
    token = request.GET.get("hub.verify_token")
    challenge = request.GET.get("hub.challenge")

    verify_token = get_verify_token()
    if mode == "subscribe" and token == verify_token:
        logger.info("Webhook verified successfully.")
        return HttpResponse(challenge, content_type="text/plain")

    logger.warning("Webhook verification failed.")
    return HttpResponse("Forbidden", status=403)


def _webhook_receive(request):
    """Handle incoming Facebook webhook events (POST)."""
    # Verify signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(request.body, signature):
        logger.warning("Invalid webhook signature.")
        return HttpResponse("Invalid signature", status=403)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse("Bad request", status=400)

    if body.get("object") != "page":
        return HttpResponse("Not a page event", status=200)

    for entry in body.get("entry", []):
        page_id = str(entry.get("id", ""))
        for event in entry.get("messaging", []):
            _handle_messaging_event(page_id, event)

    return HttpResponse("EVENT_RECEIVED", status=200)


def _handle_messaging_event(page_id, event):
    """Process a single messaging event from the webhook."""
    sender_id = str(event.get("sender", {}).get("id", ""))
    recipient_id = str(event.get("recipient", {}).get("id", ""))
    message_data = event.get("message")

    if not message_data or not sender_id:
        return

    # Ignore echo messages (messages sent by the page itself)
    if message_data.get("is_echo"):
        return

    # The sender is the Facebook user, recipient is our page
    fb_user_id = sender_id

    # Get or create the page record
    page, _ = FacebookPage.objects.get_or_create(
        page_id=page_id,
        defaults={"page_name": f"Page {page_id}"},
    )

    # Get or create the conversation
    conversation, created = Conversation.objects.get_or_create(
        page=page,
        fb_user_id=fb_user_id,
        defaults={"fb_user_name": ""},
    )

    # Fetch user name if we don't have it yet
    if not conversation.fb_user_name:
        profile = get_user_profile(fb_user_id)
        name = profile.get("name", "")
        if name:
            conversation.fb_user_name = name
            conversation.save(update_fields=["fb_user_name"])

    # Extract message content
    text = message_data.get("text", "")
    fb_message_id = message_data.get("mid")
    timestamp_ms = event.get("timestamp")
    msg_time = (
        datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        if timestamp_ms
        else dj_timezone.now()
    )

    # Extract attachments
    attachments = []
    for att in message_data.get("attachments", []):
        attachments.append(
            {
                "type": att.get("type"),
                "url": att.get("payload", {}).get("url"),
            }
        )

    # Avoid duplicate messages
    if fb_message_id and Message.objects.filter(fb_message_id=fb_message_id).exists():
        return

    # Create the message
    Message.objects.create(
        conversation=conversation,
        direction="in",
        text=text,
        fb_message_id=fb_message_id,
        attachments=attachments,
        timestamp=msg_time,
    )

    # Update conversation metadata
    preview = text[:255] if text else "[Attachment]"
    conversation.last_message_at = msg_time
    conversation.last_message_preview = preview
    conversation.unread_count = (conversation.unread_count or 0) + 1
    conversation.save(
        update_fields=["last_message_at", "last_message_preview", "unread_count"]
    )
