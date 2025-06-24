from django.contrib import admin
from .models import ActivityLog


# Register your models here.
@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("action", "performed_by", "content_type", "object_id", "timestamp")
    search_fields = ("action", "note", "performed_by__username")
    list_filter = ("content_type", "timestamp")
