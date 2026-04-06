from django.contrib import admin
from surveillance.models import CCTVCamera


@admin.register(CCTVCamera)
class CCTVCameraAdmin(admin.ModelAdmin):
    list_display = ["name", "location", "stream_name", "is_active", "order"]
    list_filter = ["is_active"]
    search_fields = ["name", "location"]
    ordering = ["order", "name"]
