import logging
import os
import subprocess

from django.conf import settings
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from surveillance.api.serializers import CCTVCameraListSerializer, CCTVCameraSerializer
from surveillance.models import CCTVCamera
from users.api.views import IsSuperAdminUser

logger = logging.getLogger(__name__)

GO2RTC_CONFIG_PATH = getattr(settings, "GO2RTC_CONFIG_PATH", "/go2rtc-config/go2rtc.yaml")
GO2RTC_CONTAINER = getattr(settings, "GO2RTC_CONTAINER", "rvdc_backend-go2rtc-1")


def _write_go2rtc_yaml() -> bool:
    """
    Write go2rtc.yaml from all active cameras, then restart the go2rtc container.
    Returns True if the file was written and the restart was triggered.
    """
    cameras = CCTVCamera.objects.filter(is_active=True)
    lines = ["streams:\n"]
    for cam in cameras:
        lines.append(f"  {cam.stream_name}:\n")
        lines.append(f"    - {cam.xmeye_url}\n")
    if not lines[1:]:
        lines = ["streams: {}\n"]

    try:
        os.makedirs(os.path.dirname(GO2RTC_CONFIG_PATH), exist_ok=True)
        with open(GO2RTC_CONFIG_PATH, "w") as f:
            f.writelines(lines)
    except OSError as exc:
        logger.warning("Failed to write go2rtc.yaml: %s", exc)
        return False

    # Restart go2rtc so it picks up the new config (Docker socket is mounted)
    try:
        subprocess.run(
            ["docker", "restart", GO2RTC_CONTAINER],
            capture_output=True,
            timeout=20,
        )
    except Exception as exc:
        logger.warning("Failed to restart go2rtc container: %s", exc)

    return True


class CCTVCameraViewSet(viewsets.ModelViewSet):
    queryset = CCTVCamera.objects.all()
    permission_classes = [IsAuthenticated, IsSuperAdminUser]
    pagination_class = None  # cameras are always few; no pagination needed
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "location", "uid"]
    ordering_fields = ["order", "name", "created_at"]

    def get_serializer_class(self):
        if self.action == "list" and self.request.query_params.get("minimal") == "true":
            return CCTVCameraListSerializer
        return CCTVCameraSerializer

    # ── Write hooks – keep go2rtc in sync ──────────────────────────────────

    def perform_create(self, serializer):
        serializer.save()
        _write_go2rtc_yaml()

    def perform_update(self, serializer):
        serializer.save()
        _write_go2rtc_yaml()

    def perform_destroy(self, instance):
        instance.delete()
        _write_go2rtc_yaml()

    # ── Extra actions ───────────────────────────────────────────────────────

    @action(detail=False, methods=["post"], url_path="sync-all")
    def sync_all(self, request):
        """Rewrite go2rtc.yaml with all active cameras and restart go2rtc."""
        ok = _write_go2rtc_yaml()
        cameras = CCTVCamera.objects.filter(is_active=True)
        return Response({
            "ok": ok,
            "synced": cameras.count() if ok else 0,
            "total": cameras.count(),
        })

    @action(detail=True, methods=["post"], url_path="sync")
    def sync_one(self, request, pk=None):
        """Sync all cameras (go2rtc.yaml is always written in full)."""
        ok = _write_go2rtc_yaml()
        camera = self.get_object()
        return Response({"ok": ok, "stream_name": camera.stream_name})

    @action(detail=False, methods=["get"], url_path="go2rtc-status")
    def go2rtc_status(self, request):
        """Check go2rtc health by reading the config file and container state."""
        config_exists = os.path.exists(GO2RTC_CONFIG_PATH)
        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Status}}", GO2RTC_CONTAINER],
                capture_output=True, text=True, timeout=5,
            )
            container_state = result.stdout.strip()
            running = container_state == "running"
        except Exception:
            running = False

        return Response({
            "configured": config_exists,
            "running": running,
            "streams": {},
        })
