import logging

import requests
from django.conf import settings
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from surveillance.api.serializers import CCTVCameraListSerializer, CCTVCameraSerializer
from surveillance.models import CCTVCamera
from users.api.views import IsSuperAdminUser

logger = logging.getLogger(__name__)


def _go2rtc_url() -> str | None:
    return getattr(settings, "GO2RTC_URL", None)


def _push_to_go2rtc(camera: CCTVCamera) -> bool:
    """Register (or replace) a camera stream in go2rtc."""
    base = _go2rtc_url()
    if not base:
        return False
    try:
        resp = requests.put(
            f"{base}/api/streams",
            params={"name": camera.stream_name},
            json=[camera.xmeye_url],
            timeout=5,
        )
        return resp.ok
    except Exception as exc:
        logger.warning("go2rtc push failed for %s: %s", camera.stream_name, exc)
        return False


def _delete_from_go2rtc(camera: CCTVCamera) -> bool:
    """Remove a camera stream from go2rtc."""
    base = _go2rtc_url()
    if not base:
        return False
    try:
        resp = requests.delete(
            f"{base}/api/streams",
            params={"name": camera.stream_name},
            timeout=5,
        )
        return resp.ok
    except Exception as exc:
        logger.warning("go2rtc delete failed for %s: %s", camera.stream_name, exc)
        return False


class CCTVCameraViewSet(viewsets.ModelViewSet):
    queryset = CCTVCamera.objects.all()
    permission_classes = [IsAuthenticated, IsSuperAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "location", "uid"]
    ordering_fields = ["order", "name", "created_at"]

    def get_serializer_class(self):
        if self.action == "list" and self.request.query_params.get("minimal") == "true":
            return CCTVCameraListSerializer
        return CCTVCameraSerializer

    # ── Write hooks – keep go2rtc in sync ──────────────────────────────────

    def perform_create(self, serializer):
        camera = serializer.save()
        if camera.is_active:
            _push_to_go2rtc(camera)

    def perform_update(self, serializer):
        # Delete the old stream key first in case stream_name changed
        old = serializer.instance
        _delete_from_go2rtc(old)
        camera = serializer.save()
        if camera.is_active:
            _push_to_go2rtc(camera)

    def perform_destroy(self, instance):
        _delete_from_go2rtc(instance)
        instance.delete()

    # ── Extra actions ───────────────────────────────────────────────────────

    @action(detail=False, methods=["post"], url_path="sync-all")
    def sync_all(self, request):
        """Re-push every active camera to go2rtc (useful after go2rtc restarts)."""
        base = _go2rtc_url()
        if not base:
            return Response(
                {"detail": "GO2RTC_URL is not configured on the server."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        cameras = CCTVCamera.objects.filter(is_active=True)
        synced, failed = 0, 0
        for cam in cameras:
            if _push_to_go2rtc(cam):
                synced += 1
            else:
                failed += 1
        return Response({"synced": synced, "failed": failed, "total": cameras.count()})

    @action(detail=True, methods=["post"], url_path="sync")
    def sync_one(self, request, pk=None):
        """Re-push a single camera to go2rtc."""
        camera = self.get_object()
        ok = _push_to_go2rtc(camera) if camera.is_active else _delete_from_go2rtc(camera)
        return Response({"ok": ok, "stream_name": camera.stream_name})

    @action(detail=False, methods=["get"], url_path="go2rtc-status")
    def go2rtc_status(self, request):
        """Proxy go2rtc's /api/streams to check which streams are active."""
        base = _go2rtc_url()
        if not base:
            return Response({"configured": False, "streams": {}})
        try:
            resp = requests.get(f"{base}/api/streams", timeout=5)
            return Response({"configured": True, "streams": resp.json()})
        except Exception as exc:
            return Response(
                {"configured": True, "streams": {}, "error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
