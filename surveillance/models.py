from django.db import models


class CCTVCamera(models.Model):
    """Represents a camera streamed via go2rtc."""

    name = models.CharField(max_length=100)
    stream_name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Stream identifier used in go2rtc, e.g. cam_1, cam_2",
    )
    stream_url = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Full go2rtc source URL (optional — streams are configured directly in go2rtc)",
    )
    location = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "CCTV Camera"
        verbose_name_plural = "CCTV Cameras"

    def __str__(self):
        return self.name
