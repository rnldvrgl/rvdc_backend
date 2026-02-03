from django.db.models import Q
from django.utils import timezone
from notifications.api.serializers import NotificationSerializer
from notifications.business_logic import NotificationManager
from notifications.models import Notification, NotificationPriority
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


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
        - include_archived: Include archived notifications
        - type: Filter by notification type
        - priority: Filter by priority level
        """
        qs = Notification.objects.filter(user=self.request.user)

        # Filter by read status
        unread_only = self.request.query_params.get('unread_only', 'false').lower() == 'true'
        if unread_only:
            qs = qs.filter(is_read=False)

        # Filter by archived status
        include_archived = self.request.query_params.get('include_archived', 'false').lower() == 'true'
        if not include_archived:
            qs = qs.filter(is_archived=False)

        # Filter by type
        notification_type = self.request.query_params.get('type')
        if notification_type:
            qs = qs.filter(type=notification_type)

        # Filter by priority
        priority = self.request.query_params.get('priority')
        if priority:
            qs = qs.filter(priority=priority)

        # Exclude expired notifications
        qs = qs.filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
        )

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

    @action(detail=True, methods=["post"], url_path="mark-unread")
    def mark_as_unread(self, request, pk=None):
        """Mark a notification as unread."""
        notification = self.get_object()
        notification.mark_as_unread()
        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_as_read(self, request):
        """Mark all notifications as read for current user."""
        count = NotificationManager.mark_all_as_read(request.user)
        return Response({
            "status": "success",
            "message": "All notifications marked as read",
            "count": count
        })

    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request, pk=None):
        """Archive a notification."""
        notification = self.get_object()
        notification.archive()
        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="unarchive")
    def unarchive(self, request, pk=None):
        """Unarchive a notification."""
        notification = self.get_object()
        notification.unarchive()
        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="by-type")
    def by_type(self, request):
        """Get notifications grouped by type."""
        notifications = self.get_queryset()

        grouped = {}
        for notif in notifications:
            notif_type = notif.type
            if notif_type not in grouped:
                grouped[notif_type] = []
            grouped[notif_type].append(NotificationSerializer(notif).data)

        return Response(grouped)

    @action(detail=False, methods=["get"], url_path="by-priority")
    def by_priority(self, request):
        """Get notifications grouped by priority."""
        notifications = self.get_queryset()

        grouped = {
            NotificationPriority.URGENT: [],
            NotificationPriority.HIGH: [],
            NotificationPriority.NORMAL: [],
            NotificationPriority.LOW: [],
        }

        for notif in notifications:
            if notif.priority in grouped:
                grouped[notif.priority].append(NotificationSerializer(notif).data)

        return Response(grouped)

    @action(detail=False, methods=["delete"], url_path="delete-read")
    def delete_read(self, request):
        """Delete all read notifications for current user."""
        count, _ = Notification.objects.filter(
            user=request.user,
            is_read=True
        ).delete()

        return Response({
            "status": "success",
            "message": "Read notifications deleted",
            "count": count
        })

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """Get notification summary for current user."""
        user = request.user

        total = Notification.objects.filter(user=user, is_archived=False).count()
        unread = NotificationManager.get_unread_count(user)

        by_priority = {}
        for priority in NotificationPriority:
            count = Notification.objects.filter(
                user=user,
                is_archived=False,
                priority=priority.value,
                is_read=False
            ).count()
            by_priority[priority.value] = count

        return Response({
            "total_notifications": total,
            "unread_count": unread,
            "read_count": total - unread,
            "by_priority": by_priority,
        })

    def destroy(self, request, *args, **kwargs):
        """Delete a notification."""
        notification = self.get_object()
        notification.delete()
        return Response(
            {"status": "success", "message": "Notification deleted"},
            status=status.HTTP_204_NO_CONTENT
        )
