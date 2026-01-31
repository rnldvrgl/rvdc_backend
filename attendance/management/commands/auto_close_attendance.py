"""
Management command to auto-close attendance sessions at 7 PM.
Should be run via cron/scheduler daily at 7:00 PM.

Usage:
    python manage.py auto_close_attendance
"""
from datetime import datetime, time

from django.core.management.base import BaseCommand
from django.utils import timezone

from attendance.models import DailyAttendance


class Command(BaseCommand):
    help = 'Auto-closes attendance sessions at 7 PM for employees who forgot to clock out'

    def handle(self, *args, **options):
        today = timezone.now().date()
        auto_close_time = time(19, 0)  # 7:00 PM
        
        # Find all attendances for today with clock_in but no clock_out
        open_attendances = DailyAttendance.objects.filter(
            date=today,
            clock_in__isnull=False,
            clock_out__isnull=True,
            attendance_type__in=['PENDING', 'FULL_DAY', 'HALF_DAY', 'PARTIAL'],
        )
        
        count = 0
        for attendance in open_attendances:
            # Set clock_out to 7 PM today
            clock_out_dt = timezone.make_aware(
                datetime.combine(today, auto_close_time),
                timezone.get_current_timezone()
            )
            
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
                    f'(Warning #{attendance.auto_close_warning_count})'
                )
            )
        
        if count == 0:
            self.stdout.write(self.style.WARNING('No open attendance sessions to close'))
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully auto-closed {count} attendance session(s)')
            )
