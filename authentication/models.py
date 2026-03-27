from django.db import models
from django.utils import timezone


class AuthSession(models.Model):
	user = models.ForeignKey(
		"users.CustomUser",
		on_delete=models.CASCADE,
		related_name="auth_sessions",
	)
	refresh_jti = models.CharField(max_length=64, unique=True)
	device_id = models.CharField(max_length=128, blank=True, default="")
	device_label = models.CharField(max_length=255, blank=True, default="Unknown device")
	user_agent = models.TextField(blank=True, default="")
	ip_address = models.GenericIPAddressField(null=True, blank=True)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	last_seen_at = models.DateTimeField(default=timezone.now)
	expires_at = models.DateTimeField(null=True, blank=True)
	revoked_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ["-last_seen_at", "-created_at"]
		indexes = [
			models.Index(fields=["user", "is_active"]),
			models.Index(fields=["device_id"]),
		]

	def __str__(self):
		return f"{self.user_id} - {self.device_label} - {'active' if self.is_active else 'revoked'}"

# Create your models here.
