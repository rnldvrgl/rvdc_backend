"""
Management command to send push reminders for attendance clock-in and clock-out.

This command is intended to run at scheduled times via cron or another scheduler.
It only sends a reminder once per user per day for each reminder type.

Usage:
    python manage.py send_attendance_reminders
    python manage.py send_attendance_reminders --mode clock_in
    python manage.py send_attendance_reminders --mode clock_out
    python manage.py send_attendance_reminders --date 2026-04-16
    python manage.py send_attendance_reminders --mode clock_in --force
"""

from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from attendance.models import DailyAttendance, HalfDaySchedule, LeaveRequest
from notifications.business_logic import AttendanceNotifications
from payroll.models import Holiday, PayrollSettings
from users.models import CustomUser


class Command(BaseCommand):
    help = "Send push reminders to employees who have not clocked in or out yet"

    def add_arguments(self, parser):
        parser.add_argument(
            "--mode",
            choices=["all", "clock_in", "clock_out"],
            default="all",
            help="Which reminder(s) to send",
        )
        parser.add_argument(
            "--date",
            type=str,
            help="Target date to process (YYYY-MM-DD). Defaults to today.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even outside the scheduled 7:00 AM / 6:00 PM windows (for manual testing).",
        )

    def handle(self, *args, **options):
        local_now = timezone.localtime(timezone.now())
        target_date = self._parse_target_date(options.get("date"), local_now.date())
        mode = options["mode"]
        force_run = options.get("force", False)

        if not force_run and mode == "clock_in" and local_now.hour != 7:
            self.stdout.write(self.style.WARNING("Skipping clock-in reminders outside 7:00 AM PH time."))
            return

        if not force_run and mode == "clock_out" and local_now.hour != 18:
            self.stdout.write(self.style.WARNING("Skipping clock-out reminders outside 6:00 PM PH time."))
            return

        if not force_run and mode == "all" and local_now.hour not in {7, 18}:
            self.stdout.write(self.style.WARNING("Skipping reminders outside 7:00 AM and 6:00 PM PH time."))
            return

        if force_run:
            self.stdout.write(self.style.WARNING("Force mode enabled: bypassing schedule hour checks."))

        settings = PayrollSettings.objects.first()
        shift_start = self._get_setting_time(settings, "shift_start", time(8, 0))
        shift_end = self._get_setting_time(settings, "shift_end", time(18, 0))
        clock_in_allowance = self._get_setting_minutes(
            settings, "clock_in_allowance_minutes", 60
        )
        clock_out_tolerance = self._get_setting_minutes(
            settings, "clock_out_tolerance_minutes", 30
        )

        reminder_window_open = self._aware_datetime(
            target_date, shift_start
        ) - timedelta(minutes=clock_in_allowance)
        reminder_window_close = self._aware_datetime(target_date, time(21, 0))

        if Holiday.objects.filter(date=target_date, is_deleted=False).exists():
            self.stdout.write(self.style.WARNING(f"Skipping holiday: {target_date}"))
            return

        shop_closed_schedule = HalfDaySchedule.objects.filter(
            date=target_date,
            schedule_type="shop_closed",
            is_deleted=False,
        ).first()
        if shop_closed_schedule:
            self.stdout.write(self.style.WARNING(f"Skipping shop-closed date: {target_date}"))
            return

        forced_half_day = HalfDaySchedule.objects.filter(
            date=target_date,
            schedule_type="half_day",
            is_deleted=False,
        ).exists()
        half_day_cutoff = self._get_half_day_cutoff(shift_start, shift_end)

        employees = (
            CustomUser.objects.filter(
                is_active=True,
                is_deleted=False,
                include_in_payroll=True,
            )
            .exclude(role="admin")
            .order_by("last_name", "first_name", "id")
        )

        stats = {"clock_in": 0, "clock_out": 0, "skipped": 0}

        for employee in employees:
            work_start, work_end = self._get_work_window(
                employee=employee,
                target_date=target_date,
                shift_start=shift_start,
                shift_end=shift_end,
                half_day_cutoff=half_day_cutoff,
                forced_half_day=forced_half_day,
            )

            if work_start is None or work_end is None:
                stats["skipped"] += 1
                continue

            work_start_dt = self._aware_datetime(target_date, work_start)
            work_end_dt = self._aware_datetime(target_date, work_end)
            now_dt = timezone.localtime(timezone.now())

            attendance = DailyAttendance.objects.filter(
                employee=employee,
                date=target_date,
                is_deleted=False,
            ).first()

            should_send_clock_in = self._should_send_clock_in(
                now_dt=now_dt,
                attendance=attendance,
                work_start_dt=work_start_dt,
                work_end_dt=work_end_dt,
            )
            should_send_clock_out = self._should_send_clock_out(
                now_dt=now_dt,
                attendance=attendance,
                work_end_dt=work_end_dt,
                reminder_window_close=reminder_window_close,
                clock_out_tolerance=clock_out_tolerance,
            )

            if mode in ("all", "clock_in") and should_send_clock_in:
                notification = AttendanceNotifications.notify_clock_in_reminder(
                    user=employee,
                    reminder_date=target_date,
                    work_start=work_start_dt.strftime("%I:%M %p").lstrip("0"),
                    work_end=work_end_dt.strftime("%I:%M %p").lstrip("0"),
                    reminder_window_open=reminder_window_open.strftime("%Y-%m-%d %H:%M"),
                    reminder_window_close=reminder_window_close.strftime("%Y-%m-%d %H:%M"),
                )
                if notification:
                    stats["clock_in"] += 1

            if mode in ("all", "clock_out") and should_send_clock_out:
                notification = AttendanceNotifications.notify_clock_out_reminder(
                    user=employee,
                    reminder_date=target_date,
                    work_end=work_end_dt.strftime("%I:%M %p").lstrip("0"),
                    reminder_window_open=reminder_window_open.strftime("%Y-%m-%d %H:%M"),
                    reminder_window_close=reminder_window_close.strftime("%Y-%m-%d %H:%M"),
                )
                if notification:
                    stats["clock_out"] += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Sent {clock_in} clock-in reminder(s) and {clock_out} clock-out reminder(s). "
                "Skipped {skipped} employee(s).".format(**stats)
            )
        )

    def _parse_target_date(self, value, default_date):
        if not value:
            return default_date
        return datetime.strptime(value, "%Y-%m-%d").date()

    def _get_setting_time(self, settings, field_name, fallback):
        if not settings:
            return fallback
        value = getattr(settings, field_name, None)
        return value or fallback

    def _get_setting_minutes(self, settings, field_name, fallback):
        if not settings:
            return fallback
        value = getattr(settings, field_name, None)
        return value if value is not None else fallback

    def _get_half_day_cutoff(self, shift_start, shift_end):
        start_hour = shift_start.hour + (shift_start.minute / 60)
        end_hour = shift_end.hour + (shift_end.minute / 60)
        cutoff_hour = (start_hour + end_hour) / 2
        return time(int(cutoff_hour), int((cutoff_hour % 1) * 60))

    def _get_work_window(
        self,
        employee,
        target_date,
        shift_start,
        shift_end,
        half_day_cutoff,
        forced_half_day,
    ):
        approved_leave = LeaveRequest.objects.filter(
            employee=employee,
            date=target_date,
            status="APPROVED",
        ).first()

        if approved_leave and not approved_leave.is_half_day:
            return None, None

        if forced_half_day:
            return shift_start, half_day_cutoff

        if approved_leave and approved_leave.is_half_day:
            if approved_leave.shift_period == "AM":
                return half_day_cutoff, shift_end
            if approved_leave.shift_period == "PM":
                return shift_start, half_day_cutoff

        return shift_start, shift_end

    def _should_send_clock_in(self, now_dt, attendance, work_start_dt, work_end_dt):
        if attendance and attendance.attendance_type in {"LEAVE", "ABSENT", "SHOP_CLOSED"}:
            return False

        if attendance and attendance.clock_in:
            return False

        return work_start_dt <= now_dt <= work_end_dt

    def _should_send_clock_out(
        self,
        now_dt,
        attendance,
        work_end_dt,
        reminder_window_close,
        clock_out_tolerance,
    ):
        if not attendance or not attendance.clock_in or attendance.clock_out:
            return False

        reminder_open = work_end_dt - timedelta(minutes=clock_out_tolerance)
        return reminder_open <= now_dt <= reminder_window_close

    def _aware_datetime(self, target_date, time_value):
        dt = datetime.combine(target_date, time_value)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
