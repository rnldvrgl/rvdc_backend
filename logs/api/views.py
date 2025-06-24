from rest_framework import generics, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from logs.models import ActivityLog
from .serializers import ActivityLogSerializer


class ActivityLogListView(generics.ListAPIView):
    queryset = ActivityLog.objects.all().order_by("-timestamp")
    serializer_class = ActivityLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["content_type__model", "performed_by"]
    search_fields = ["action", "note"]
