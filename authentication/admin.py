from django.contrib import admin
from authentication.models import AuthSession


@admin.register(AuthSession)
class AuthSessionAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"user",
		"device_label",
		"ip_address",
		"is_active",
		"last_seen_at",
		"created_at",
	)
	list_filter = ("is_active", "created_at", "last_seen_at")
	search_fields = ("user__username", "device_id", "device_label", "refresh_jti")
	readonly_fields = (
		"user",
		"refresh_jti",
		"device_id",
		"device_label",
		"user_agent",
		"ip_address",
		"is_active",
		"created_at",
		"last_seen_at",
		"expires_at",
		"revoked_at",
	)
