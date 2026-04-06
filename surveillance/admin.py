from django.contrib import admin
from surveillance.models import CCTVCamera


@admin.register(CCTVCamera)
class CCTVCameraAdmin(admin.ModelAdmin):
    list_display = ["name", "uid", "location", "channel", "is_active", "order"]
    list_filter = ["is_active"]
    search_fields = ["name", "uid", "location"]
    ordering = ["order", "name"]
