"""
Management command to auto-close attendance sessions at 11 PM.
Should be run via cron/scheduler daily at 11:00 PM.

Usage:
    python manage.py auto_close_attendance
    python manage.py auto_close_attendance --backfill  # Process past dates
"""
from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from attendance.models import DailyAttendance


class Command(BaseCommand):
    help = 'Auto-closes attendance sessions at 11 PM for employees who forgot to clock out'

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
        auto_close_time = time(23, 0)  # 11:00 PM
        
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
            # Set clock_out to 7 PM on the attendance date (not today)
            clock_out_dt = timezone.make_aware(
                datetime.combine(attendance.date, auto_close_time),
                timezone.get_current_timezone()
            )
            
            # Set clock_out to 11 PM on the attendance date (not today)
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

