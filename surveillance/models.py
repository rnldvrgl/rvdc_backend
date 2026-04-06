from django.db import models


class CCTVCamera(models.Model):
    """Represents an iCSee/XMEye P2P camera streamed via go2rtc."""

    name = models.CharField(max_length=100)
    uid = models.CharField(
        max_length=200,
        help_text="XMEye device serial number / cloud UID (e.g. ABCD1234EFGH)",
    )
    username = models.CharField(max_length=100, default="admin")
    password = models.CharField(max_length=100, blank=True)
    channel = models.PositiveSmallIntegerField(
        default=0,
        help_text="Camera channel: 0 = main lens, 1 = sub lens (for dual-lens models)",
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
        return f"{self.name} ({self.uid})"

    @property
    def stream_name(self) -> str:
        """Unique stream identifier used in go2rtc."""
        return f"cam_{self.pk}"

    @property
    def xmeye_url(self) -> str:
        """go2rtc XMEye source URL."""
        auth = f"{self.username}:{self.password}@" if self.password else f"{self.username}@"
        return f"xmeye://{auth}{self.uid}?channel={self.channel}"
