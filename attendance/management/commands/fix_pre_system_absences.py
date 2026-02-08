"""
Management command to fix incorrectly marked absences before system start date
and set the attendance system start date in PayrollSettings.

Usage:
    python manage.py fix_pre_system_absences --start-date 2026-02-07
"""
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db.models import Q

from attendance.models import DailyAttendance
from payroll.models import PayrollSettings


class Command(BaseCommand):
    help = 'Removes attendance records marked before system start date and updates PayrollSettings'

    def add_arguments(self, parser):
        parser.add_argument(
            '--start-date',
            type=str,
            required=True,
            help='Date when attendance system started (YYYY-MM-DD). Absences before this will be removed.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        start_date_str = options['start_date']
        dry_run = options.get('dry_run', False)
        
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            self.stdout.write(
                self.style.ERROR('Invalid date format. Use YYYY-MM-DD')
            )
            return
        
        self.stdout.write(
            self.style.WARNING(
                f'\n{"DRY RUN MODE - No changes will be made" if dry_run else "LIVE MODE - Changes will be applied"}\n'
            )
        )
        
        # Find all attendance records before start date
        pre_system_attendance = DailyAttendance.objects.filter(
            date__lt=start_date
        )
        
        count = pre_system_attendance.count()
        
        if count == 0:
            self.stdout.write(
                self.style.SUCCESS(f'\nNo attendance records found before {start_date}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'\nFound {count} attendance record(s) before {start_date}:')
            )
            
            # Show details
            for attendance in pre_system_attendance:
                self.stdout.write(
                    f'  - {attendance.employee.get_full_name()}: {attendance.date} ({attendance.attendance_type})'
                )
            
            if not dry_run:
                # Delete records
                deleted_count, _ = pre_system_attendance.delete()
                self.stdout.write(
                    self.style.SUCCESS(f'\n✅ Deleted {deleted_count} attendance record(s)')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'\n[DRY RUN] Would delete {count} record(s)')
                )
        
        # Update PayrollSettings
        settings, created = PayrollSettings.objects.get_or_create(pk=1)
        
        if created:
            self.stdout.write(
                self.style.WARNING('\nCreated new PayrollSettings')
            )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'\n[DRY RUN] Would set attendance_system_start_date to {start_date}'
                )
            )
        else:
            old_date = settings.attendance_system_start_date
            settings.attendance_system_start_date = start_date
            settings.save()
            
            if old_date:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\n✅ Updated attendance_system_start_date: {old_date} → {start_date}'
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\n✅ Set attendance_system_start_date to {start_date}'
                    )
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n{"[DRY RUN] Preview complete" if dry_run else "Fix complete!"}'
            )
        )
        self.stdout.write(
            '\nThe cron job will now skip marking absences before this date.'
        )
