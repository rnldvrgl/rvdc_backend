import logging
import os
import subprocess
from urllib.request import urlopen, Request
from urllib.error import URLError
import json

from django.conf import settings
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from surveillance.api.serializers import (
    CCTVCameraListSerializer,
    CCTVCameraSerializer,
)
from surveillance.models import CCTVCamera
from users.api.views import IsSuperAdminUser

logger = logging.getLogger(__name__)

GO2RTC_CONFIG_PATH = getattr(settings, "GO2RTC_CONFIG_PATH", "/go2rtc-config/go2rtc.yaml")
GO2RTC_CONTAINER = getattr(settings, "GO2RTC_CONTAINER", "rvdc_backend-go2rtc-1")
GO2RTC_AUTO_RESTART = getattr(settings, "GO2RTC_AUTO_RESTART", True)
GO2RTC_URL = getattr(settings, "GO2RTC_URL", "http://go2rtc:1984")


# ─────────────────────────────────────────────────────────────
# 🔧 Core Helpers
# ─────────────────────────────────────────────────────────────

def build_rtsp_url(cam: CCTVCamera) -> str:
    """
    Normalize RTSP URL for go2rtc.
    Credentials are already embedded in stream_url by the user.
    """
    return cam.stream_url.strip()


def build_stream_entry(cam: CCTVCamera) -> str:
    """
    Build final stream line.
    RTSP inputs are routed through an exec-based ffmpeg source because the
    shop PC go2rtc RTSP server works with a plain ffmpeg command, but fails
    with go2rtc's built-in ffmpeg wrapper arguments.
    """
    url = build_rtsp_url(cam)

    if url.startswith("rtsp://") or url.startswith("rtsps://"):
        if getattr(cam, "force_transcode", False):
            url = (
                f"exec:ffmpeg -hide_banner -rtsp_transport tcp -i {url} "
                f"-c:v libx264 -an -preset superfast -tune zerolatency "
                f"-pix_fmt yuv420p -rtsp_transport tcp -f rtsp {{output}}"
            )
        else:
            url = (
                f"exec:ffmpeg -hide_banner -rtsp_transport tcp -i {url} "
                f"-c:v copy -an -rtsp_transport tcp -f rtsp {{output}}"
            )

    return f"  {cam.stream_name}:\n    - {url}\n"


def generate_go2rtc_config() -> str:
    """
    Generate full go2rtc.yaml content.
    """
    cameras = CCTVCamera.objects.filter(is_active=True)

    lines = [
        "log:\n",
        "  level: info\n",
        "\n",
        "hls:\n",
        "  window_duration: 30\n",
        "\n",
        "streams:\n",
    ]

    if not cameras.exists():
        lines.append("  {}\n")
        return "".join(lines)

    for cam in cameras:
        lines.append(build_stream_entry(cam))

    return "".join(lines)


def write_go2rtc_config() -> bool:
    """
    Write config file + optionally restart container
    """
    config_content = generate_go2rtc_config()

    try:
        os.makedirs(os.path.dirname(GO2RTC_CONFIG_PATH), exist_ok=True)
        with open(GO2RTC_CONFIG_PATH, "w") as f:
            f.write(config_content)
    except OSError as exc:
        logger.error("Failed to write go2rtc.yaml: %s", exc)
        return False

    if GO2RTC_AUTO_RESTART:
        try:
            subprocess.run(
                ["docker", "restart", GO2RTC_CONTAINER],
                capture_output=True,
                timeout=20,
            )
        except Exception as exc:
            logger.warning("Failed to restart go2rtc: %s", exc)

    return True


# ─────────────────────────────────────────────────────────────
# 📦 ViewSet
# ─────────────────────────────────────────────────────────────

class CCTVCameraViewSet(viewsets.ModelViewSet):
    queryset = CCTVCamera.objects.all()
    permission_classes = [IsAuthenticated, IsSuperAdminUser]
    pagination_class = None
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "location"]
    ordering_fields = ["order", "name", "created_at"]

    def get_serializer_class(self):
        if self.action == "list" and self.request.query_params.get("minimal") == "true":
            return CCTVCameraListSerializer
        return CCTVCameraSerializer

    # ── Auto sync hooks ───────────────────────────────────────

    def perform_create(self, serializer):
        serializer.save()
        write_go2rtc_config()

    def perform_update(self, serializer):
        serializer.save()
        write_go2rtc_config()

    def perform_destroy(self, instance):
        instance.delete()
        write_go2rtc_config()

    # ── Actions ──────────────────────────────────────────────

    @action(detail=False, methods=["post"], url_path="sync-all")
    def sync_all(self, request):
        ok = write_go2rtc_config()
        count = CCTVCamera.objects.filter(is_active=True).count()

        return Response({
            "ok": ok,
            "synced": count if ok else 0,
            "total": count,
        })

    @action(detail=True, methods=["post"], url_path="sync")
    def sync_one(self, request, pk=None):
        ok = write_go2rtc_config()
        camera = self.get_object()

        return Response({
            "ok": ok,
            "stream_name": camera.stream_name
        })

    @action(detail=False, methods=["get"], url_path="go2rtc-status")
    def go2rtc_status(self, request):
        running = False
        version = None
        streams = {}
        error = None

        if not GO2RTC_URL:
            return Response({
                "running": False,
                "error": "GO2RTC_URL not configured",
            })

        # Check go2rtc health via GET /api
        try:
            req = Request(f"{GO2RTC_URL}/api", method="GET")
            with urlopen(req, timeout=5) as resp:
                info = json.loads(resp.read())
                running = True
                version = info.get("version")
        except (URLError, OSError, json.JSONDecodeError) as exc:
            error = f"Cannot reach go2rtc at {GO2RTC_URL}: {exc}"
            logger.warning(error)

        # Fetch active streams list
        if running:
            try:
                req = Request(f"{GO2RTC_URL}/api/streams", method="GET")
                with urlopen(req, timeout=5) as resp:
                    streams = json.loads(resp.read())
            except Exception as exc:
                logger.warning("Failed to fetch go2rtc streams: %s", exc)

        return Response({
            "running": running,
            "version": version,
            "streams": streams,
            "stream_count": len(streams),
            "error": error,
        })
