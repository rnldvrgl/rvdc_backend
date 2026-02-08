"""
Management command to recalculate pending attendance records.

Usage:
    python manage.py recalculate_pending_attendance

This command recalculates paid hours for all pending attendance records
to ensure they use the latest business logic (e.g., half-day = 4 hours).
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from attendance.models import DailyAttendance


class Command(BaseCommand):
    help = 'Recalculate paid hours for pending attendance records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Recalculate all attendance records (not just pending)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        recalculate_all = options['all']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))

        # Get attendance records to recalculate
        if recalculate_all:
            qs = DailyAttendance.objects.filter(
                clock_in__isnull=False,
                clock_out__isnull=False,
                attendance_type__in=['FULL_DAY', 'HALF_DAY', 'PARTIAL'],
            ).exclude(is_deleted=True)
            self.stdout.write(f'Found {qs.count()} total attendance records to recalculate')
        else:
            qs = DailyAttendance.objects.filter(
                status='PENDING',
                clock_in__isnull=False,
                clock_out__isnull=False,
                attendance_type__in=['FULL_DAY', 'HALF_DAY', 'PARTIAL'],
            ).exclude(is_deleted=True)
            self.stdout.write(f'Found {qs.count()} pending attendance records to recalculate')

        if not qs.exists():
            self.stdout.write(self.style.SUCCESS('No records to recalculate'))
            return

        updated_count = 0
        half_day_fixed = 0
        full_day_fixed = 0
        partial_fixed = 0

        with transaction.atomic():
            for attendance in qs:
                old_paid_hours = attendance.paid_hours
                old_type = attendance.attendance_type
                old_break_hours = attendance.break_hours

                # Recalculate metrics
                attendance.compute_attendance_metrics()

                # Check if anything changed
                if (old_paid_hours != attendance.paid_hours or
                    old_type != attendance.attendance_type or
                    old_break_hours != attendance.break_hours):
                    
                    updated_count += 1
                    
                    if attendance.attendance_type == 'HALF_DAY' and old_paid_hours != Decimal('4.00'):
                        half_day_fixed += 1
                    elif attendance.attendance_type == 'FULL_DAY' and old_paid_hours != Decimal('8.00'):
                        full_day_fixed += 1
                    elif attendance.attendance_type == 'PARTIAL':
                        partial_fixed += 1

                    self.stdout.write(
                        f'  [{attendance.employee.get_full_name()}] {attendance.date}: '
                        f'{old_type} ({old_paid_hours}h paid, {old_break_hours}h break) → '
                        f'{attendance.attendance_type} ({attendance.paid_hours}h paid, {attendance.break_hours}h break)'
                    )

                    if not dry_run:
                        # Save without triggering save() method to avoid recalculating late penalties
                        DailyAttendance.objects.filter(id=attendance.id).update(
                            attendance_type=attendance.attendance_type,
                            paid_hours=attendance.paid_hours,
                            break_hours=attendance.break_hours,
                            total_hours=attendance.total_hours,
                        )

            if dry_run:
                self.stdout.write(self.style.WARNING('DRY RUN - No changes were saved'))
            else:
                self.stdout.write(self.style.SUCCESS(f'\nSuccessfully updated {updated_count} records'))

        # Summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write('SUMMARY:')
        self.stdout.write(f'  Total records processed: {qs.count()}')
        self.stdout.write(f'  Records updated: {updated_count}')
        if half_day_fixed:
            self.stdout.write(f'  Half-day records fixed: {half_day_fixed}')
        if full_day_fixed:
            self.stdout.write(f'  Full-day records fixed: {full_day_fixed}')
        if partial_fixed:
            self.stdout.write(f'  Partial records fixed: {partial_fixed}')
        self.stdout.write('='*60)
