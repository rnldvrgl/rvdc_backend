"""
Management command to recalculate pending attendance records.

Usage:
    python manage.py recalculate_pending_attendance

This command recalculates paid hours for all pending attendance records
to ensure they use the latest business logic (e.g., half-day = 4 hours).
"""
import traceback
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction, connection
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
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed error information',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        recalculate_all = options['all']
        verbose = options.get('verbose', False)

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))

        # Get attendance records to recalculate
        if recalculate_all:
            qs = DailyAttendance.objects.filter(
                clock_in__isnull=False,
                clock_out__isnull=False,
                attendance_type__in=['FULL_DAY', 'HALF_DAY', 'PARTIAL'],
            ).exclude(is_deleted=True).select_related('employee')
            self.stdout.write(f'Found {qs.count()} total attendance records to recalculate')
        else:
            qs = DailyAttendance.objects.filter(
                status='PENDING',
                clock_in__isnull=False,
                clock_out__isnull=False,
                attendance_type__in=['FULL_DAY', 'HALF_DAY', 'PARTIAL'],
            ).exclude(is_deleted=True).select_related('employee')
            self.stdout.write(f'Found {qs.count()} pending attendance records to recalculate')

        if not qs.exists():
            self.stdout.write(self.style.SUCCESS('No records to recalculate'))
            return

        updated_count = 0
        half_day_fixed = 0
        full_day_fixed = 0
        partial_fixed = 0
        error_count = 0

        # Ensure we're in autocommit mode
        connection.set_autocommit(True)

        for attendance in qs:
            # Store identifying info first (in case of errors)
            attendance_id = attendance.id
            try:
                employee_name = attendance.employee.get_full_name()
            except Exception:
                employee_name = f"Employee ID {attendance.employee_id}"
            date_str = str(attendance.date)
            
            # Store old values before transaction
            old_paid_hours = attendance.paid_hours
            old_type = attendance.attendance_type
            old_break_hours = attendance.break_hours
            
            try:
                # Use atomic to create a savepoint that can be rolled back independently
                with transaction.atomic():
                    # Reload object inside transaction with all related data
                    fresh_attendance = DailyAttendance.objects.select_related('employee').get(id=attendance_id)
                    
                    # Recalculate metrics
                    fresh_attendance.compute_attendance_metrics()

                    # Check if anything changed
                    if (old_paid_hours != fresh_attendance.paid_hours or
                        old_type != fresh_attendance.attendance_type or
                        old_break_hours != fresh_attendance.break_hours):
                        
                        updated_count += 1
                        
                        if fresh_attendance.attendance_type == 'HALF_DAY' and old_paid_hours != Decimal('4.00'):
                            half_day_fixed += 1
                        elif fresh_attendance.attendance_type == 'FULL_DAY' and old_paid_hours != Decimal('8.00'):
                            full_day_fixed += 1
                        elif fresh_attendance.attendance_type == 'PARTIAL':
                            partial_fixed += 1

                        self.stdout.write(
                            f'  [{employee_name}] {date_str}: '
                            f'{old_type} ({old_paid_hours}h paid, {old_break_hours}h break) → '
                            f'{fresh_attendance.attendance_type} ({fresh_attendance.paid_hours}h paid, {fresh_attendance.break_hours}h break)'
                        )

                        if not dry_run:
                            # Save without triggering save() method to avoid recalculating late penalties
                            DailyAttendance.objects.filter(id=attendance_id).update(
                                attendance_type=fresh_attendance.attendance_type,
                                paid_hours=fresh_attendance.paid_hours,
                                break_hours=fresh_attendance.break_hours,
                                total_hours=fresh_attendance.total_hours,
                            )
            except Exception as e:
                error_count += 1
                # Force rollback and close connection to reset state
                try:
                    connection.close()
                except Exception:
                    pass
                error_msg = f'  ERROR [{employee_name}] {date_str}: {str(e)}'
                self.stdout.write(self.style.ERROR(error_msg))
                if verbose:
                    self.stdout.write(self.style.ERROR(traceback.format_exc()))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY RUN - No changes were saved'))
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
        if error_count:
            self.stdout.write(self.style.ERROR(f'  Errors encountered: {error_count}'))
        self.stdout.write('='*60)
