from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask

TIMEZONE = "Asia/Manila"


TASKS = [
    #
    # ==========================
    # Attendance
    # ==========================
    #
    {
        "name": "Attendance • Auto Close Attendance",
        "task": "attendance.tasks.auto_close_attendance",
        "minute": "0",
        "hour": "23",
    },
    {
        "name": "Attendance • Mark Daily Absences",
        "task": "attendance.tasks.mark_daily_absences",
        "minute": "10",
        "hour": "23",
    },
    {
        "name": "Attendance • Clock In Reminder",
        "task": "attendance.tasks.send_clock_in_reminder",
        "minute": "30",
        "hour": "7",
    },
    {
        "name": "Attendance • Clock Out Reminder",
        "task": "attendance.tasks.send_clock_out_reminder",
        "minute": "45",
        "hour": "16",
    },
    {
        "name": "Attendance • Weekly Incomplete Attendance Reminder",
        "task": "attendance.tasks.send_weekly_incomplete_attendance_admin_reminder",
        "minute": "0",
        "hour": "8",
        "day_of_week": "5",  # Friday
    },

    #
    # ==========================
    # Users
    # ==========================
    #
    {
        "name": "Users • Cleanup Unused Images",
        "task": "users.tasks.cleanup_unused_images",
        "minute": "0",
        "hour": "2",
    },
    {
        "name": "Users • Create Annual Leave Balances",
        "task": "users.tasks.create_leave_balances",
        "minute": "0",
        "hour": "0",
        "day_of_month": "1",
        "month_of_year": "1",
    },

    #
    # ==========================
    # Notifications
    # ==========================
    #
    {
        "name": "Notifications • Delete Old Notifications",
        "task": "notifications.tasks.delete_old_notifications",
        "minute": "30",
        "hour": "2",
    },

    #
    # ==========================
    # Payroll
    # ==========================
    #
    {
        "name": "Payroll • Add Philippine Holidays",
        "task": "payroll.tasks.add_philippine_holidays",
        "minute": "30",
        "hour": "0",
        "day_of_month": "1",
        "month_of_year": "1",
    },
    {
        "name": "Payroll • Update Holiday Years",
        "task": "payroll.tasks.update_holiday_years",
        "minute": "0",
        "hour": "1",
        "day_of_month": "1",
        "month_of_year": "1",
    },
    {
        "name": "Payroll • Archive Old Payrolls",
        "task": "payroll.tasks.archive_old_payrolls",
        "minute": "0",
        "hour": "3",
        "day_of_month": "1",
    },

    #
    # ==========================
    # Quotations
    # ==========================
    #
    {
        "name": "Quotations • Cleanup Archived Quotations",
        "task": "quotations.tasks.cleanup_archived_quotations",
        "minute": "0",
        "hour": "3",
        "day_of_week": "0",  # Sunday
    },
]


class Command(BaseCommand):
    help = "Create or update Celery Beat Periodic Tasks"

    def handle(self, *args, **options):
        created = 0
        updated = 0

        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write("Setting up Celery Beat Periodic Tasks")
        self.stdout.write("=" * 70)

        for task in TASKS:
            schedule, _ = CrontabSchedule.objects.get_or_create(
                minute=task["minute"],
                hour=task["hour"],
                day_of_week=task.get("day_of_week", "*"),
                day_of_month=task.get("day_of_month", "*"),
                month_of_year=task.get("month_of_year", "*"),
                timezone=TIMEZONE,
            )

            periodic_task, was_created = PeriodicTask.objects.update_or_create(
                name=task["name"],
                defaults={
                    "task": task["task"],
                    "crontab": schedule,
                    "enabled": True,
                },
            )

            if was_created:
                created += 1
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Created  : {periodic_task.name}")
                )
            else:
                updated += 1
                self.stdout.write(
                    self.style.WARNING(f"↻ Updated  : {periodic_task.name}")
                )

        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write(self.style.SUCCESS("Celery Beat setup completed"))
        self.stdout.write("=" * 70)
        self.stdout.write(f"Created : {created}")
        self.stdout.write(f"Updated : {updated}")
        self.stdout.write(f"Total   : {created + updated}")
        self.stdout.write("=" * 70)
