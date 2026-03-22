from django.db.models import Q
from django.utils import timezone
from notifications.api.serializers import NotificationSerializer
from notifications.business_logic import NotificationManager
from notifications.models import Notification, PushSubscription
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class NotificationCursorPagination(CursorPagination):
    page_size = 10
    ordering = ["-created_at", "-id"]


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    pagination_class = NotificationCursorPagination
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Get notifications for current user with filtering.

        Query params:
        - unread_only: Filter to unread notifications only
        - type: Filter by notification type
        """
        qs = Notification.objects.filter(user=self.request.user)

        # Filter by read status
        unread_only = self.request.query_params.get("unread_only", "false").lower() == "true"
        if unread_only:
            qs = qs.filter(is_read=False)

        # Filter by type
        notification_type = self.request.query_params.get("type")
        if notification_type:
            qs = qs.filter(type=notification_type)

        return qs.order_by("-created_at", "-id")

    def retrieve(self, request, *args, **kwargs):
        """Get a notification and mark it as read."""
        instance = self.get_object()
        instance.mark_as_read()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="unread-count")
    def count_unread(self, request):
        """Get count of unread notifications."""
        count = NotificationManager.get_unread_count(request.user)
        return Response({"unread_count": count})

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_as_read(self, request, pk=None):
        """Mark a notification as read."""
        notification = self.get_object()
        notification.mark_as_read()
        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_as_read(self, request):
        """Mark all notifications as read for current user."""
        count = NotificationManager.mark_all_as_read(request.user)
        return Response({
            "status": "success",
            "message": "All notifications marked as read",
            "count": count,
        })

    @action(detail=False, methods=["delete"], url_path="delete-read")
    def delete_read(self, request):
        """Delete all read notifications for current user."""
        count, _ = Notification.objects.filter(
            user=request.user,
            is_read=True,
        ).delete()

        return Response({
            "status": "success",
            "message": "Read notifications deleted",
            "count": count,
        })

    def destroy(self, request, *args, **kwargs):
        """Delete a notification."""
        notification = self.get_object()
        notification.delete()
        return Response(
            {"status": "success", "message": "Notification deleted"},
            status=status.HTTP_204_NO_CONTENT,
        )


class VapidPublicKeyView(APIView):
    """Return the VAPID public key so the frontend can subscribe."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.conf import settings

        key = getattr(settings, "VAPID_PUBLIC_KEY", "")
        return Response({"public_key": key})


class PushSubscriptionView(APIView):
    """Create or delete a Web Push subscription for the current user."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        endpoint = request.data.get("endpoint")
        keys = request.data.get("keys", {})
        p256dh = keys.get("p256dh", "")
        auth = keys.get("auth", "")

        if not endpoint or not p256dh or not auth:
            return Response(
                {"error": "endpoint, keys.p256dh, and keys.auth are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={"user": request.user, "p256dh": p256dh, "auth": auth},
        )
        return Response({"status": "subscribed"}, status=status.HTTP_201_CREATED)

    def delete(self, request):
        endpoint = request.data.get("endpoint")
        if endpoint:
            PushSubscription.objects.filter(
                user=request.user, endpoint=endpoint
            ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
