"""
Django management command to fix attendance time entry calculations.

This command recalculates attendance metrics (paid hours, lateness, penalties,
attendance type) for existing attendance records to ensure accuracy.

Usage:
    # Dry run (show what would be fixed)
    python manage.py fix_attendance_time_entries --dry-run

    # Fix all pending/approved attendance records
    python manage.py fix_attendance_time_entries

    # Fix specific date range
    python manage.py fix_attendance_time_entries --start-date 2024-01-01 --end-date 2024-01-31

    # Fix specific employee
    python manage.py fix_attendance_time_entries --employee-id 5

    # Fix specific attendance IDs
    python manage.py fix_attendance_time_entries --ids 1,2,3

    # Fix all statuses (including rejected)
    python manage.py fix_attendance_time_entries --all-status

    # Verify without fixing
    python manage.py fix_attendance_time_entries --verify-only
"""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from attendance.models import DailyAttendance


class Command(BaseCommand):
    help = 'Fix attendance time entry calculations by recalculating metrics'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )
        parser.add_argument(
            '--ids',
            type=str,
            help='Comma-separated list of attendance IDs to fix',
        )
        parser.add_argument(
            '--employee-id',
            type=int,
            help='Fix attendance for a specific employee',
        )
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start date (YYYY-MM-DD) for date range filter',
        )
        parser.add_argument(
            '--end-date',
            type=str,
            help='End date (YYYY-MM-DD) for date range filter',
        )
        parser.add_argument(
            '--all-status',
            action='store_true',
            help='Fix attendance with any status (default: pending/approved only)',
        )
        parser.add_argument(
            '--verify-only',
            action='store_true',
            help='Only verify attendance without fixing',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )
        parser.add_argument(
            '--recalculate-all',
            action='store_true',
            help='Recalculate all metrics even if they seem correct',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verify_only = options['verify_only']
        verbose = options['verbose']
        attendance_ids = options['ids']
        employee_id = options['employee_id']
        start_date = options['start_date']
        end_date = options['end_date']
        all_status = options['all_status']
        recalculate_all = options['recalculate_all']

        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('ATTENDANCE TIME ENTRY FIX'))
        self.stdout.write(self.style.SUCCESS('=' * 80))

        # Get attendance records to process
        queryset = DailyAttendance.objects.filter(is_deleted=False)

        if attendance_ids:
            ids_list = [int(x.strip()) for x in attendance_ids.split(',')]
            queryset = queryset.filter(id__in=ids_list)
            self.stdout.write(f"Targeting specific attendance IDs: {ids_list}")
        else:
            if employee_id:
                queryset = queryset.filter(employee_id=employee_id)
                self.stdout.write(f"Targeting employee ID: {employee_id}")

            if start_date:
                start = datetime.strptime(start_date, '%Y-%m-%d').date()
                queryset = queryset.filter(date__gte=start)
                self.stdout.write(f"Start date: {start}")

            if end_date:
                end = datetime.strptime(end_date, '%Y-%m-%d').date()
                queryset = queryset.filter(date__lte=end)
                self.stdout.write(f"End date: {end}")

            if not all_status:
                queryset = queryset.filter(status__in=['PENDING', 'APPROVED'])
                self.stdout.write("Targeting pending/approved attendance only")
            else:
                self.stdout.write("Targeting all attendance statuses")

        # Exclude ABSENT and LEAVE types as they don't need time calculations
        queryset = queryset.exclude(attendance_type__in=['ABSENT', 'LEAVE'])

        attendances = queryset.order_by('-date', 'employee__first_name')
        total_count = attendances.count()

        if total_count == 0:
            self.stdout.write(self.style.WARNING('\nNo attendance records found to process.'))
            return

        self.stdout.write(f"\nFound {total_count} attendance record(s) to process")

        if verify_only:
            self.stdout.write(self.style.WARNING('\nMode: VERIFICATION ONLY'))
            self._verify_attendances(attendances, verbose)
        elif dry_run:
            self.stdout.write(self.style.WARNING('\nMode: DRY RUN (no changes will be made)'))
            self._fix_attendances(attendances, verbose, dry_run=True, recalculate_all=recalculate_all)
        else:
            self.stdout.write(self.style.SUCCESS('\nMode: LIVE (will update records)'))
            confirm = input('\nAre you sure you want to fix these attendance records? (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.WARNING('Aborted.'))
                return
            self._fix_attendances(attendances, verbose, dry_run=False, recalculate_all=recalculate_all)

    def _verify_attendances(self, attendances, verbose):
        """Verify attendance calculations without fixing."""
        passed = 0
        failed = 0
        issues = []

        self.stdout.write('\n' + '-' * 80)

        for attendance in attendances:
            attendance_issues = self._check_attendance(attendance, verbose)

            if attendance_issues:
                failed += 1
                issues.extend([f"Attendance {attendance.id}: {issue}" for issue in attendance_issues])
                if verbose:
                    self.stdout.write(self.style.ERROR(f'\n❌ Attendance {attendance.id} - Issues found:'))
                    for issue in attendance_issues:
                        self.stdout.write(self.style.ERROR(f'   - {issue}'))
            else:
                passed += 1
                if verbose:
                    self.stdout.write(self.style.SUCCESS(f'\n✅ Attendance {attendance.id} - OK'))

            if verbose:
                self.stdout.write('-' * 80)

        # Summary
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('VERIFICATION SUMMARY'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(f'Total Checked: {passed + failed}')
        self.stdout.write(self.style.SUCCESS(f'Passed: {passed} ✅'))
        self.stdout.write(self.style.ERROR(f'Failed: {failed} ❌'))

        if issues:
            self.stdout.write(self.style.ERROR('\nIssues Found:'))
            for issue in issues:
                self.stdout.write(self.style.ERROR(f'  - {issue}'))
        else:
            self.stdout.write(self.style.SUCCESS('\n🎉 All attendance records passed verification!'))

        self.stdout.write(self.style.SUCCESS('=' * 80 + '\n'))

    def _check_attendance(self, attendance, verbose):
        """Check a single attendance record for issues."""
        issues = []
        tolerance = Decimal('0.01')

        if verbose:
            self.stdout.write(f'\nAttendance ID: {attendance.id}')
            self.stdout.write(f'Employee: {attendance.employee.get_full_name()}')
            self.stdout.write(f'Date: {attendance.date}')
            self.stdout.write(f'Type: {attendance.attendance_type}')

        # Check 1: Clock times exist
        if not attendance.clock_in:
            issues.append('Missing clock_in time')
            return issues

        if not attendance.clock_out and attendance.attendance_type not in ['ABSENT', 'LEAVE']:
            issues.append('Missing clock_out time')

        # Check 2: Total hours calculation
        if attendance.clock_in and attendance.clock_out:
            delta = attendance.clock_out - attendance.clock_in
            expected_total = Decimal(delta.total_seconds()) / Decimal(3600)
            expected_total = self._round(expected_total)

            if abs(expected_total - attendance.total_hours) > tolerance:
                issues.append(
                    f'Total hours mismatch: {expected_total}h (calculated) vs '
                    f'{attendance.total_hours}h (stored)'
                )

        # Check 3: Lateness calculation
        from payroll.models import PayrollSettings
        try:
            settings = PayrollSettings.objects.first()
            grace_minutes = settings.grace_minutes if settings else 15
            shift_start = settings.shift_start if settings else time(8, 0)
        except Exception:
            grace_minutes = 15
            shift_start = time(8, 0)

        if attendance.clock_in:
            tz = timezone.get_current_timezone()
            clock_in_local = attendance.clock_in
            if not timezone.is_aware(clock_in_local):
                clock_in_local = timezone.make_aware(clock_in_local, tz)

            local_date = clock_in_local.astimezone(tz).date()
            grace_limit = datetime.combine(local_date, shift_start) + timedelta(minutes=grace_minutes)
            grace_limit = timezone.make_aware(grace_limit, tz)

            if clock_in_local > grace_limit:
                late_delta = (clock_in_local - grace_limit).total_seconds() / 60
                expected_late_minutes = int(late_delta)
                expected_penalty = Decimal(str(expected_late_minutes * 2))

                if not attendance.is_late:
                    issues.append(f'Should be marked as late ({expected_late_minutes} min)')
                elif attendance.late_minutes != expected_late_minutes:
                    issues.append(
                        f'Late minutes mismatch: {expected_late_minutes} (calc) vs '
                        f'{attendance.late_minutes} (stored)'
                    )
                elif abs(attendance.late_penalty_amount - expected_penalty) > tolerance:
                    issues.append(
                        f'Late penalty mismatch: ₱{expected_penalty} (calc) vs '
                        f'₱{attendance.late_penalty_amount} (stored)'
                    )

        # Check 4: Uniform penalties
        expected_uniform_penalty = Decimal('0.00')
        if attendance.missing_uniform_shirt:
            expected_uniform_penalty += Decimal('50.00')
        if attendance.missing_uniform_pants:
            expected_uniform_penalty += Decimal('50.00')
        if attendance.missing_uniform_shoes:
            expected_uniform_penalty += Decimal('50.00')

        if abs(attendance.uniform_penalty_amount - expected_uniform_penalty) > tolerance:
            issues.append(
                f'Uniform penalty mismatch: ₱{expected_uniform_penalty} (calc) vs '
                f'₱{attendance.uniform_penalty_amount} (stored)'
            )

        # Check 5: Paid hours reasonableness
        if attendance.paid_hours < 0:
            issues.append(f'Negative paid hours: {attendance.paid_hours}')
        elif attendance.paid_hours > attendance.total_hours:
            issues.append(
                f'Paid hours ({attendance.paid_hours}) exceeds total hours ({attendance.total_hours})'
            )

        # Check 6: Attendance type validation
        if attendance.total_hours >= Decimal('10.00') and attendance.paid_hours < Decimal('8.00'):
            if attendance.attendance_type != 'FULL_DAY':
                issues.append(
                    f'Should be FULL_DAY (worked {attendance.total_hours}h) but is {attendance.attendance_type}'
                )

        if verbose and not issues:
            self.stdout.write(f'Clock In: {attendance.clock_in}')
            self.stdout.write(f'Clock Out: {attendance.clock_out}')
            self.stdout.write(f'Total Hours: {attendance.total_hours}h')
            self.stdout.write(f'Paid Hours: {attendance.paid_hours}h')
            self.stdout.write(f'Late: {attendance.is_late} ({attendance.late_minutes} min, ₱{attendance.late_penalty_amount})')
            self.stdout.write(f'Uniform Penalty: ₱{attendance.uniform_penalty_amount}')

        return issues

    def _fix_attendances(self, attendances, verbose, dry_run, recalculate_all):
        """Fix attendance calculations."""
        fixed = 0
        skipped = 0
        errors = []

        self.stdout.write('\n' + '-' * 80)

        for attendance in attendances:
            try:
                # Store old values
                old_type = attendance.attendance_type
                old_total_hours = attendance.total_hours
                old_paid_hours = attendance.paid_hours
                old_late_minutes = attendance.late_minutes
                old_late_penalty = attendance.late_penalty_amount
                old_uniform_penalty = attendance.uniform_penalty_amount

                self.stdout.write(
                    f'\nAttendance {attendance.id} ({attendance.employee.get_full_name()} - {attendance.date}):'
                )

                # Check if needs fixing
                needs_fix = recalculate_all or len(self._check_attendance(attendance, False)) > 0

                if not needs_fix:
                    self.stdout.write('  Status: No issues detected, skipping')
                    skipped += 1
                    continue

                self.stdout.write(f'  Old: {old_type}, {old_paid_hours}h paid, ₱{old_late_penalty} late, ₱{old_uniform_penalty} uniform')

                if not dry_run:
                    with transaction.atomic():
                        # Recalculate metrics
                        if attendance.clock_in:
                            attendance.calculate_lateness()

                        if attendance.clock_in and attendance.clock_out:
                            attendance.compute_attendance_metrics()

                        # Recalculate uniform penalty
                        attendance.calculate_uniform_penalty()

                        # Save without triggering signals again
                        attendance.save(update_fields=[
                            'attendance_type',
                            'total_hours',
                            'break_hours',
                            'paid_hours',
                            'is_late',
                            'late_minutes',
                            'late_penalty_amount',
                            'uniform_penalty_amount',
                            'updated_at',
                        ])

                        attendance.refresh_from_db()

                        self.stdout.write(self.style.SUCCESS(
                            f'  New: {attendance.attendance_type}, {attendance.paid_hours}h paid, '
                            f'₱{attendance.late_penalty_amount} late, ₱{attendance.uniform_penalty_amount} uniform'
                        ))

                        # Show changes
                        changes = []
                        if old_type != attendance.attendance_type:
                            changes.append(f'Type: {old_type} → {attendance.attendance_type}')
                        if old_paid_hours != attendance.paid_hours:
                            changes.append(f'Paid: {old_paid_hours}h → {attendance.paid_hours}h')
                        if old_late_minutes != attendance.late_minutes:
                            changes.append(f'Late: {old_late_minutes}min → {attendance.late_minutes}min')
                        if old_late_penalty != attendance.late_penalty_amount:
                            changes.append(f'Late ₱: {old_late_penalty} → {attendance.late_penalty_amount}')
                        if old_uniform_penalty != attendance.uniform_penalty_amount:
                            changes.append(f'Uniform ₱: {old_uniform_penalty} → {attendance.uniform_penalty_amount}')

                        if changes:
                            self.stdout.write(self.style.WARNING('  Changes:'))
                            for change in changes:
                                self.stdout.write(self.style.WARNING(f'    - {change}'))

                        if verbose:
                            self._show_attendance_breakdown(attendance)

                    fixed += 1
                else:
                    self.stdout.write('  Would recalculate attendance metrics')
                    fixed += 1

            except Exception as e:
                error_msg = f'Attendance {attendance.id}: {str(e)}'
                errors.append(error_msg)
                self.stdout.write(self.style.ERROR(f'  ❌ ERROR: {e}'))

            if verbose:
                self.stdout.write('-' * 80)

        # Summary
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('FIX SUMMARY'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(f'Total Processed: {fixed + skipped + len(errors)}')
        self.stdout.write(self.style.SUCCESS(f'Fixed: {fixed} ✅'))
        self.stdout.write(f'Skipped: {skipped}')
        self.stdout.write(self.style.ERROR(f'Errors: {len(errors)} ❌'))

        if errors:
            self.stdout.write(self.style.ERROR('\nErrors:'))
            for error in errors:
                self.stdout.write(self.style.ERROR(f'  - {error}'))

        if dry_run:
            self.stdout.write(self.style.WARNING('\n⚠️  This was a DRY RUN. No changes were made.'))
            self.stdout.write(self.style.WARNING('To apply fixes, run without --dry-run'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Fix applied to {fixed} attendance record(s).'))

        self.stdout.write(self.style.SUCCESS('=' * 80 + '\n'))

    def _show_attendance_breakdown(self, attendance):
        """Show detailed attendance breakdown."""
        self.stdout.write('  Breakdown:')
        self.stdout.write(f'    Clock In: {attendance.clock_in}')
        self.stdout.write(f'    Clock Out: {attendance.clock_out}')
        self.stdout.write(f'    Total Hours: {attendance.total_hours}h')
        self.stdout.write(f'    Break Hours: {attendance.break_hours}h')
        self.stdout.write(f'    Paid Hours: {attendance.paid_hours}h')
        self.stdout.write(f'    Late: {attendance.is_late} ({attendance.late_minutes} min)')
        self.stdout.write(f'    Late Penalty: ₱{attendance.late_penalty_amount}')
        self.stdout.write(f'    Uniform Penalties: ₱{attendance.uniform_penalty_amount}')
        if attendance.uniform_penalty_amount > 0:
            items = []
            if attendance.missing_uniform_shirt:
                items.append('Shirt')
            if attendance.missing_uniform_pants:
                items.append('Pants')
            if attendance.missing_uniform_shoes:
                items.append('Shoes')
            self.stdout.write(f'      Missing: {", ".join(items)}')
        self.stdout.write(f'    Auto-closed: {attendance.auto_closed}')
        self.stdout.write(f'    Status: {attendance.status}')

    def _round(self, value):
        """Round to 2 decimal places using ROUND_HALF_UP."""
        from decimal import ROUND_HALF_UP
        return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
