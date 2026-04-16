"""
Send a weekly admin reminder for employees with incomplete attendance.

Default schedule target: Friday 6:00 AM PH time via cron.
The command scans from last Saturday up to yesterday and flags employees who have:
- missing attendance records on working days
- open attendance (clock-in without clock-out)

Skipped days:
- holidays
- shop-closed schedules
- approved full-day leave
"""

from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from attendance.models import DailyAttendance, HalfDaySchedule, LeaveRequest
from notifications.business_logic import NotificationManager
from notifications.models import Notification, NotificationType
from payroll.models import Holiday
from users.models import CustomUser


class Command(BaseCommand):
    help = "Send weekly reminder to admins about employees with incomplete attendance"

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            help="Reference date in YYYY-MM-DD (defaults to today).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run regardless of weekday and create reminder immediately.",
        )

    def handle(self, *args, **options):
        local_now = timezone.localtime(timezone.now())
        force_run = options.get("force", False)
        run_date = self._parse_target_date(options.get("date"), local_now.date())

        # Friday=4. Keep schedule strict unless force-run is explicitly used.
        if not force_run and run_date.weekday() != 4:
            self.stdout.write(
                self.style.WARNING("Skipping weekly attendance admin reminder outside Friday PH time.")
            )
            return

        window_start, window_end = self._get_window(run_date)
        if window_end < window_start:
            self.stdout.write(self.style.WARNING("Window is empty. Nothing to process."))
            return

        admins = CustomUser.objects.filter(
            is_active=True,
            is_deleted=False,
            role="admin",
        )
        if not admins.exists():
            self.stdout.write(self.style.WARNING("No active admins found. Nothing to notify."))
            return

        employees = CustomUser.objects.filter(
            is_active=True,
            is_deleted=False,
            include_in_payroll=True,
        ).exclude(role="admin")

        holidays = set(
            Holiday.objects.filter(
                is_deleted=False,
                date__gte=window_start,
                date__lte=window_end,
            ).values_list("date", flat=True)
        )
        shop_closed_days = set(
            HalfDaySchedule.objects.filter(
                is_deleted=False,
                schedule_type="shop_closed",
                date__gte=window_start,
                date__lte=window_end,
            ).values_list("date", flat=True)
        )

        issues = []
        total_missing_days = 0
        total_open_days = 0

        for employee in employees:
            missing_days = []
            open_clock_out_days = []

            current = window_start
            while current <= window_end:
                if current in holidays or current in shop_closed_days:
                    current += timedelta(days=1)
                    continue

                if self._has_approved_full_day_leave(employee, current):
                    current += timedelta(days=1)
                    continue

                attendance = DailyAttendance.objects.filter(
                    employee=employee,
                    date=current,
                    is_deleted=False,
                ).first()

                if not attendance:
                    missing_days.append(current)
                elif attendance.attendance_type in {"LEAVE", "SHOP_CLOSED"}:
                    pass
                elif attendance.clock_in and not attendance.clock_out:
                    open_clock_out_days.append(current)

                current += timedelta(days=1)

            if missing_days or open_clock_out_days:
                total_missing_days += len(missing_days)
                total_open_days += len(open_clock_out_days)
                issues.append(
                    {
                        "employee_id": employee.id,
                        "employee_name": employee.get_full_name() or employee.username,
                        "missing_days": [d.isoformat() for d in missing_days],
                        "open_clock_out_days": [d.isoformat() for d in open_clock_out_days],
                    }
                )

        if not issues:
            self.stdout.write(
                self.style.SUCCESS(
                    f"No incomplete attendance found from {window_start} to {window_end}."
                )
            )
            return

        reminder_key = f"weekly_attendance_gap:{window_start.isoformat()}:{window_end.isoformat()}"
        title = "Weekly Attendance Check Needed"
        message = (
            f"{len(issues)} employee(s) have incomplete attendance from {window_start:%b %d} "
            f"to {window_end:%b %d}. Missing days: {total_missing_days}, open clock-outs: {total_open_days}."
        )
        preview = [
            {
                "employee_name": item["employee_name"],
                "missing_days": item["missing_days"][:3],
                "open_clock_out_days": item["open_clock_out_days"][:3],
            }
            for item in issues[:10]
        ]

        notified = 0
        for admin in admins:
            if Notification.objects.filter(
                user=admin,
                type=NotificationType.SYSTEM_ALERT,
                data__reminder_key=reminder_key,
            ).exists():
                continue

            NotificationManager.create_notification(
                user=admin,
                notification_type=NotificationType.SYSTEM_ALERT,
                title=title,
                message=message,
                data={
                    "kind": "weekly_attendance_gap",
                    "reminder_key": reminder_key,
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                    "employees_flagged": len(issues),
                    "missing_days_total": total_missing_days,
                    "open_clock_out_total": total_open_days,
                    "preview": preview,
                    "url": "/attendance/records",
                },
            )
            notified += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Weekly admin attendance reminder sent to {notified} admin(s). "
                f"Employees flagged: {len(issues)}."
            )
        )

    def _parse_target_date(self, value, default_date):
        if not value:
            return default_date
        return datetime.strptime(value, "%Y-%m-%d").date()

    def _get_window(self, run_date):
        # Window: last Saturday up to yesterday relative to run date.
        end_date = run_date - timedelta(days=1)
        days_since_saturday = (end_date.weekday() - 5) % 7
        start_date = end_date - timedelta(days=days_since_saturday)
        return start_date, end_date

    def _has_approved_full_day_leave(self, employee, day):
        leave_qs = LeaveRequest.objects.filter(
            employee=employee,
            status="APPROVED",
        ).filter(
            Q(start_date__lte=day, end_date__gte=day)
            | Q(date=day)
        )

        for leave in leave_qs:
            if not leave.is_half_day or leave.shift_period == "FULL":
                return True
        return False
