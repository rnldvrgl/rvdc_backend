"""
Management command to auto-close attendance sessions at 9 PM.
Should be run via cron/scheduler daily at 9:00 PM.

Usage:
    python manage.py auto_close_attendance
    python manage.py auto_close_attendance --backfill  # Process past dates
"""
from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from attendance.models import DailyAttendance, LeaveRequest


class Command(BaseCommand):
    help = 'Auto-closes attendance sessions at 9 PM for employees who forgot to clock out'

    def add_arguments(self, parser):
        parser.add_argument(
            '--backfill',
            action='store_true',
            help='Process all open attendance records from the past 7 days',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Number of days to look back when using --backfill (default: 7)',
        )

    def handle(self, *args, **options):
        today = timezone.now().date()
        auto_close_time = time(21, 0)  # 9:00 PM
        
        if options['backfill']:
            # Process past dates
            days_back = options['days']
            start_date = today - timedelta(days=days_back)
            
            self.stdout.write(
                self.style.WARNING(
                    f'Backfilling from {start_date} to {today} ({days_back} days)'
                )
            )
            
            # Find all open attendances within the date range
            # Exclude ABSENT and LEAVE types (they shouldn't have clock times)
            open_attendances = DailyAttendance.objects.filter(
                date__gte=start_date,
                date__lte=today,
                clock_in__isnull=False,
                clock_out__isnull=True,
                is_deleted=False,
            ).exclude(
                attendance_type__in=['ABSENT', 'LEAVE']
            ).order_by('date')
        else:
            # Normal mode: only process today
            # Find all attendances for today with clock_in but no clock_out
            # Exclude ABSENT and LEAVE types (they shouldn't have clock times)
            open_attendances = DailyAttendance.objects.filter(
                date=today,
                clock_in__isnull=False,
                clock_out__isnull=True,
                is_deleted=False,
            ).exclude(
                attendance_type__in=['ABSENT', 'LEAVE']
            )
        
        count = 0
        for attendance in open_attendances:
            close_time = auto_close_time  # Default: 9 PM

            # Check if the employee has an approved half-day leave for this date
            half_day_leave = LeaveRequest.objects.filter(
                employee=attendance.employee,
                date=attendance.date,
                status='APPROVED',
                is_half_day=True,
                shift_period='PM',  # On leave in afternoon → should clock out at cutoff
            ).first()

            if half_day_leave:
                # Use half-day cutoff time instead of 9 PM
                try:
                    from payroll.models import PayrollSettings
                    settings = PayrollSettings.objects.first()
                    if settings and settings.shift_start and settings.shift_end:
                        morning_hour = settings.shift_start.hour + settings.shift_start.minute / 60
                        end_hour = settings.shift_end.hour + settings.shift_end.minute / 60
                        cutoff_hour = int((morning_hour + end_hour) / 2)
                        close_time = time(cutoff_hour, 0)
                except Exception:
                    close_time = time(13, 0)  # Fallback: 1 PM

            clock_out_dt = timezone.make_aware(
                datetime.combine(attendance.date, close_time),
                timezone.get_current_timezone()
            )
            
            # Set clock_out on the attendance date
            attendance.clock_out = clock_out_dt
            attendance.auto_closed = True
            
            # Increment warning count
            attendance.auto_close_warning_count += 1
            
            # Recompute metrics
            attendance.save()
            
            count += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f'Auto-closed: {attendance.employee.get_full_name()} '
                    f'on {attendance.date} (Warning #{attendance.auto_close_warning_count})'
                )
            )
        
        if count == 0:
            self.stdout.write(self.style.WARNING('No open attendance sessions to close'))
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully auto-closed {count} attendance session(s)')
            )

