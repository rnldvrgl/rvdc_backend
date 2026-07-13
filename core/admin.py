from django.contrib import admin
from django_celery_beat.admin import (
    CrontabScheduleAdmin,
    PeriodicTaskAdmin,
)
from django_celery_beat.models import (
    CrontabSchedule,
    PeriodicTask,
)


#
# Periodic Tasks
#
admin.site.unregister(PeriodicTask)


@admin.register(PeriodicTask)
class CustomPeriodicTaskAdmin(PeriodicTaskAdmin):
    list_display = (
        "name",
        "task",
        "enabled",
        "schedule",
        "last_run_at",
        "total_run_count",
    )

    list_filter = (
        "enabled",
        "crontab",
    )

    search_fields = (
        "name",
        "task",
    )

    ordering = (
        "name",
    )

    def schedule(self, obj):
        if obj.crontab:
            return obj.crontab.human_readable
        if obj.interval:
            return obj.interval
        if obj.solar:
            return obj.solar
        if obj.clocked:
            return obj.clocked
        return "-"
    schedule.short_description = "Schedule"


#
# Crontab Schedules
#
admin.site.unregister(CrontabSchedule)


@admin.register(CrontabSchedule)
class CustomCrontabScheduleAdmin(CrontabScheduleAdmin):
    list_display = (
        "__str__",
        "human_readable",
        "used_by",
    )

    search_fields = (
        "minute",
        "hour",
    )

    ordering = (
        "hour",
        "minute",
    )

    def used_by(self, obj):
        tasks = (
            PeriodicTask.objects.filter(crontab=obj)
            .order_by("name")
            .values_list("name", flat=True)
        )
        return ", ".join(tasks) if tasks else "-"

    used_by.short_description = "Used By"
