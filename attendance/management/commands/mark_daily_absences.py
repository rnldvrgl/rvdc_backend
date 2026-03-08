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
        
        # Check if system has started yet (don't mark absences before attendance system was in use)
        from payroll.models import PayrollSettings
        try:
            settings = PayrollSettings.objects.first()
            if settings and settings.attendance_system_start_date:
                if target_date < settings.attendance_system_start_date:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Skipping date before attendance system start ({settings.attendance_system_start_date}): {target_date}'
                        )
                    )
                    return
        except Exception:
            pass  # If settings don't exist or error, continue
        
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
        
        # Check if shop is closed
        from attendance.models import HalfDaySchedule
        shop_closed_schedule = HalfDaySchedule.objects.filter(
            date=target_date,
            schedule_type='shop_closed',
            is_deleted=False,
        ).first()
        
        if shop_closed_schedule:
            self.stdout.write(
                self.style.WARNING(f'Shop closed on {target_date}: {shop_closed_schedule.reason or "No reason"}')
            )
        
        # Get all active employees included in payroll (excluding admin role as they don't clock in/out)
        employees = CustomUser.objects.filter(
            is_active=True,
            is_deleted=False,
            include_in_payroll=True,
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
            
            # If no clock in/out and not already marked as LEAVE or ABSENT or SHOP_CLOSED
            if not attendance.clock_in and not attendance.clock_out:
                if attendance.attendance_type not in ['LEAVE', 'ABSENT', 'SHOP_CLOSED']:
                    if shop_closed_schedule:
                        # Mark as SHOP_CLOSED instead of ABSENT
                        from decimal import Decimal
                        attendance.attendance_type = 'SHOP_CLOSED'
                        attendance.consecutive_absences = 0
                        attendance.is_awol = False
                        attendance.total_hours = Decimal('0.00')
                        attendance.paid_hours = Decimal('0.00')
                        attendance.break_hours = Decimal('0.00')
                        attendance.is_late = False
                        attendance.late_minutes = 0
                        attendance.late_penalty_amount = Decimal('0.00')
                        attendance.status = 'APPROVED'
                        attendance.notes = f'Shop Closed - {shop_closed_schedule.reason}' if shop_closed_schedule.reason else 'Shop Closed'
                        attendance.save()
                        count += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f'Marked SHOP_CLOSED: {employee.get_full_name()}'
                            )
                        )
                    else:
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
