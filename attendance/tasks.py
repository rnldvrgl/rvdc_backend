from celery import shared_task
from django.core.management import call_command


@shared_task
def auto_close_attendance():
    call_command("auto_close_attendance")


@shared_task
def mark_daily_absences():
    call_command("mark_daily_absences")


@shared_task
def send_clock_in_reminder():
    call_command(
        "send_attendance_reminders",
        mode="clock_in",
    )


@shared_task
def send_clock_out_reminder():
    call_command(
        "send_attendance_reminders",
        mode="clock_out",
    )


@shared_task
def send_weekly_incomplete_attendance_admin_reminder():
    call_command("send_weekly_incomplete_attendance_admin_reminder")
