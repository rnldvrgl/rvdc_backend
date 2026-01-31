"""
Management command to mark employees as absent if they didn't clock in/out and have no approved leave.
Should be run via cron/scheduler daily at 12:01 AM.

Usage:
    python manage.py mark_daily_absences [--date YYYY-MM-DD]
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from attendance.models import DailyAttendance
from users.models import CustomUser


class Command(BaseCommand):
    help = 'Marks employees as absent if they have no attendance and no approved leave'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Date to mark absences for (YYYY-MM-DD). Defaults to yesterday.',
        )

    def handle(self, *args, **options):
        # Default to yesterday
        if options['date']:
            from datetime import datetime
            target_date = datetime.strptime(options['date'], '%Y-%m-%d').date()
        else:
            target_date = (timezone.now() - timedelta(days=1)).date()
        
        # Skip weekends (optional - adjust based on your business rules)
        if target_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
            self.stdout.write(
                self.style.WARNING(f'Skipping weekend date: {target_date}')
            )
            return
        
        # Check if it's a holiday
        from payroll.models import Holiday
        if Holiday.objects.filter(date=target_date, is_deleted=False).exists():
            self.stdout.write(
                self.style.WARNING(f'Skipping holiday: {target_date}')
            )
            return
        
        # Get all active employees (excluding admin role as they don't clock in/out)
        employees = CustomUser.objects.filter(
            is_active=True,
            is_deleted=False,
        ).exclude(role='admin')
        
        count = 0
        for employee in employees:
            # Check if attendance record exists
            attendance, created = DailyAttendance.objects.get_or_create(
                employee=employee,
                date=target_date,
                defaults={
                    'attendance_type': 'PENDING',
                }
            )
            
            # If no clock in/out and not already marked as LEAVE or ABSENT
            if not attendance.clock_in and not attendance.clock_out:
                if attendance.attendance_type not in ['LEAVE', 'ABSENT']:
                    attendance.mark_absent()
                    attendance.save()
                    
                    count += 1
                    status = 'AWOL' if attendance.is_awol else 'ABSENT'
                    self.stdout.write(
                        self.style.WARNING(
                            f'Marked {status}: {employee.get_full_name()} '
                            f'({attendance.consecutive_absences} consecutive)'
                        )
                    )
        
        if count == 0:
            self.stdout.write(
                self.style.SUCCESS(f'No absences to mark for {target_date}')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully marked {count} absence(s) for {target_date}'
                )
            )
