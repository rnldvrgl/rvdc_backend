from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import CursorPagination
from notifications.models import Notification
from notifications.api.serializers import NotificationSerializer


class NotificationCursorPagination(CursorPagination):
    page_size = 10
    ordering = ["-created_at", "-id"]


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    pagination_class = NotificationCursorPagination
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by(
            "-created_at", "-id"
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if not instance.is_read:
            instance.is_read = True
            instance.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def count_unread(self, request):
        count = self.get_queryset().filter(is_read=False).count()
        return Response({"unread_count": count})

    @action(detail=True, methods=["post"])
    def mark_as_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({"status": "marked as read"})

    @action(detail=False, methods=["post"])
    def mark_all_as_read(self, request):
        count = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"status": "marked all as read", "updated": count})

    @action(detail=True, methods=["post"])
    def delete(self, request, pk=None):
        notification = self.get_object()
        notification.delete()
        return Response({"status": "deleted"})
