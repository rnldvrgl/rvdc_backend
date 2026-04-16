"""
Django management command to refresh payroll from updated attendance records.

This command recomputes existing payroll records based on current attendance data.
Useful after fixing attendance records to ensure payroll reflects the updates.

Usage:
    # Dry run (show what would be refreshed)
    python manage.py refresh_payroll_from_attendance --dry-run

    # Refresh all draft payrolls
    python manage.py refresh_payroll_from_attendance

    # Refresh specific payroll IDs
    python manage.py refresh_payroll_from_attendance --ids 1,2,3

    # Refresh payroll for date range
    python manage.py refresh_payroll_from_attendance --start-date 2024-01-01 --end-date 2024-01-31

    # Refresh specific employee's payroll
    python manage.py refresh_payroll_from_attendance --employee-id 5

    # Verify without refreshing
    python manage.py refresh_payroll_from_attendance --verify-only

    # Include all statuses (not just draft)
    python manage.py refresh_payroll_from_attendance --all-status
"""

from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from payroll.models import WeeklyPayroll


class Command(BaseCommand):
    help = 'Refresh payroll records from updated attendance data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be refreshed without making changes',
        )
        parser.add_argument(
            '--ids',
            type=str,
            help='Comma-separated list of payroll IDs to refresh',
        )
        parser.add_argument(
            '--employee-id',
            type=int,
            help='Refresh payroll for a specific employee',
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
            help='Refresh payrolls with any status (default: draft only)',
        )
        parser.add_argument(
            '--verify-only',
            action='store_true',
            help='Only verify without refreshing',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt (for non-interactive use like cron)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verify_only = options['verify_only']
        verbose = options['verbose']
        payroll_ids = options['ids']
        employee_id = options['employee_id']
        start_date = options['start_date']
        end_date = options['end_date']
        all_status = options['all_status']
        force = options['force']

        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('PAYROLL REFRESH FROM ATTENDANCE'))
        self.stdout.write(self.style.SUCCESS('=' * 80))

        # Get payrolls to process
        queryset = WeeklyPayroll.objects.filter(is_deleted=False)

        if payroll_ids:
            ids_list = [int(x.strip()) for x in payroll_ids.split(',')]
            queryset = queryset.filter(id__in=ids_list)
            self.stdout.write(f"Targeting specific payroll IDs: {ids_list}")
        else:
            if employee_id:
                queryset = queryset.filter(employee_id=employee_id)
                self.stdout.write(f"Targeting employee ID: {employee_id}")

            if start_date:
                start = datetime.strptime(start_date, '%Y-%m-%d').date()
                queryset = queryset.filter(week_start__gte=start)
                self.stdout.write(f"Start date: {start}")

            if end_date:
                end = datetime.strptime(end_date, '%Y-%m-%d').date()
                queryset = queryset.filter(week_start__lte=end)
                self.stdout.write(f"End date: {end}")

            if not all_status:
                queryset = queryset.filter(status='draft')
                self.stdout.write("Targeting draft payrolls only")
            else:
                self.stdout.write("Targeting all payroll statuses")

        payrolls = queryset.order_by('-week_start', 'employee__first_name')
        total_count = payrolls.count()

        if total_count == 0:
            self.stdout.write(self.style.WARNING('\nNo payroll records found to process.'))
            return

        self.stdout.write(f"\nFound {total_count} payroll record(s) to process")

        if verify_only:
            self.stdout.write(self.style.WARNING('\nMode: VERIFICATION ONLY'))
            self._verify_payrolls(payrolls, verbose)
        elif dry_run:
            self.stdout.write(self.style.WARNING('\nMode: DRY RUN (no changes will be made)'))
            self._refresh_payrolls(payrolls, verbose, dry_run=True)
        else:
            self.stdout.write(self.style.SUCCESS('\nMode: LIVE (will update records)'))
            if not force:
                try:
                    confirm = input('\nAre you sure you want to refresh these payroll records? (yes/no): ')
                except EOFError:
                    self.stdout.write(
                        self.style.WARNING(
                            'Non-interactive environment detected. Re-run with --force to skip confirmation.'
                        )
                    )
                    return
                if confirm.lower() != 'yes':
                    self.stdout.write(self.style.WARNING('Aborted.'))
                    return
            self._refresh_payrolls(payrolls, verbose, dry_run=False)

    def _verify_payrolls(self, payrolls, verbose):
        """Verify payroll records match attendance data."""
        from attendance.models import DailyAttendance

        passed = 0
        warned = 0
        issues = []

        self.stdout.write('\n' + '-' * 80)

        for payroll in payrolls:
            payroll_issues = []
            tolerance = Decimal('0.01')

            if verbose:
                self.stdout.write(f'\nPayroll ID: {payroll.id}')
                self.stdout.write(f'Employee: {payroll.employee.get_full_name()}')
                self.stdout.write(f'Week: {payroll.week_start} to {payroll.week_end}')
                self.stdout.write(f'Status: {payroll.status}')

            # Get attendance for this payroll period
            attendance_qs = DailyAttendance.objects.filter(
                employee=payroll.employee,
                date__gte=payroll.week_start,
                date__lte=payroll.week_end,
                is_deleted=False,
                status='APPROVED',
            )

            # Calculate expected hours from attendance
            expected_regular = Decimal('0.00')
            expected_overtime = Decimal('0.00')
            expected_late_penalties = Decimal('0.00')

            for attendance in attendance_qs:
                paid_hours = Decimal(attendance.paid_hours or 0)
                if paid_hours > Decimal('8.00'):
                    expected_regular += Decimal('8.00')
                    expected_overtime += (paid_hours - Decimal('8.00'))
                else:
                    expected_regular += paid_hours

                if attendance.late_penalty_amount:
                    expected_late_penalties += Decimal(attendance.late_penalty_amount)

            # Compare with stored values
            stored_regular = Decimal(str(payroll.regular_hours))
            stored_overtime = Decimal(str(payroll.overtime_hours))

            if abs(expected_regular - stored_regular) > tolerance:
                payroll_issues.append(
                    f'Regular hours mismatch: {expected_regular}h (attendance) vs '
                    f'{stored_regular}h (payroll)'
                )

            if abs(expected_overtime - stored_overtime) > tolerance:
                payroll_issues.append(
                    f'Overtime hours mismatch: {expected_overtime}h (attendance) vs '
                    f'{stored_overtime}h (payroll)'
                )

            # Check if late penalties are in deductions
            if expected_late_penalties > 0:
                # Check if late penalties exist in deduction records
                has_late_penalty = payroll.deduction_items.filter(
                    category='penalty'
                ).exists()

                if not has_late_penalty and expected_late_penalties > tolerance:
                    payroll_issues.append(
                        f'Missing late penalties: ₱{expected_late_penalties} expected'
                    )

            if verbose and not payroll_issues:
                self.stdout.write(f'Regular Hours: {stored_regular}h (matches attendance)')
                self.stdout.write(f'Overtime Hours: {stored_overtime}h (matches attendance)')
                if expected_late_penalties > 0:
                    self.stdout.write(f'Late Penalties: ₱{expected_late_penalties}')

            if payroll_issues:
                warned += 1
                issues.extend([f"Payroll {payroll.id}: {issue}" for issue in payroll_issues])
                if verbose:
                    self.stdout.write(self.style.WARNING('\n⚠️  Issues found:'))
                    for issue in payroll_issues:
                        self.stdout.write(self.style.WARNING(f'   - {issue}'))
            else:
                passed += 1
                if verbose:
                    self.stdout.write(self.style.SUCCESS('\n✅ OK'))

            if verbose:
                self.stdout.write('-' * 80)

        # Summary
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('VERIFICATION SUMMARY'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(f'Total Checked: {passed + warned}')
        self.stdout.write(self.style.SUCCESS(f'Passed: {passed} ✅'))
        self.stdout.write(self.style.WARNING(f'Need Refresh: {warned} ⚠️'))

        if issues:
            self.stdout.write(self.style.WARNING('\nIssues Found (need refresh):'))
            for issue in issues[:20]:  # Show first 20
                self.stdout.write(self.style.WARNING(f'  - {issue}'))
            if len(issues) > 20:
                self.stdout.write(f"  ... and {len(issues) - 20} more issues")

        if warned > 0:
            self.stdout.write('\n' + '=' * 80)
            self.stdout.write('RECOMMENDATION')
            self.stdout.write('=' * 80)
            self.stdout.write('Issues detected. To refresh payroll, run:')
            self.stdout.write('  python manage.py refresh_payroll_from_attendance --dry-run')
            self.stdout.write('\nThen apply refresh with:')
            self.stdout.write('  python manage.py refresh_payroll_from_attendance')
        else:
            self.stdout.write(self.style.SUCCESS('\n🎉 All payroll records match attendance!'))

        self.stdout.write(self.style.SUCCESS('=' * 80 + '\n'))

    def _refresh_payrolls(self, payrolls, verbose, dry_run):
        """Refresh payroll records from attendance."""
        refreshed = 0
        skipped = 0
        errors = []

        self.stdout.write('\n' + '-' * 80)

        for payroll in payrolls:
            try:
                # Store old values
                old_regular = payroll.regular_hours
                old_overtime = payroll.overtime_hours
                old_gross = payroll.gross_pay
                old_net = payroll.net_pay

                self.stdout.write(
                    f'\nPayroll {payroll.id} ({payroll.employee.get_full_name()} - '
                    f'{payroll.week_start} to {payroll.week_end}):'
                )
                self.stdout.write(f'  Status: {payroll.status}')
                self.stdout.write(
                    f'  Current: {old_regular}h regular, {old_overtime}h OT, '
                    f'₱{old_gross:,.2f} gross, ₱{old_net:,.2f} net'
                )

                if not dry_run:
                    with transaction.atomic():
                        # Recompute from attendance
                        payroll.compute_from_daily_attendance()

                        # Recreate deduction records (includes late penalties)
                        payroll.create_deduction_records()

                        # Save updated payroll
                        payroll.save()
                        payroll.refresh_from_db()

                        new_regular = payroll.regular_hours
                        new_overtime = payroll.overtime_hours
                        new_gross = payroll.gross_pay
                        new_net = payroll.net_pay

                        self.stdout.write(self.style.SUCCESS(
                            f'  Updated: {new_regular}h regular, {new_overtime}h OT, '
                            f'₱{new_gross:,.2f} gross, ₱{new_net:,.2f} net'
                        ))

                        # Show changes
                        changes = []
                        if old_regular != new_regular:
                            changes.append(f'Regular: {old_regular}h → {new_regular}h')
                        if old_overtime != new_overtime:
                            changes.append(f'Overtime: {old_overtime}h → {new_overtime}h')
                        if abs(old_gross - new_gross) > Decimal('0.01'):
                            changes.append(f'Gross: ₱{old_gross:,.2f} → ₱{new_gross:,.2f}')
                        if abs(old_net - new_net) > Decimal('0.01'):
                            changes.append(f'Net: ₱{old_net:,.2f} → ₱{new_net:,.2f}')

                        if changes:
                            self.stdout.write(self.style.WARNING('  Changes:'))
                            for change in changes:
                                self.stdout.write(self.style.WARNING(f'    - {change}'))
                        else:
                            self.stdout.write('  No changes (already up to date)')
                            skipped += 1
                            continue

                        if verbose:
                            self._show_payroll_breakdown(payroll)

                    refreshed += 1
                else:
                    self.stdout.write('  Would recompute from attendance and recreate deductions')
                    refreshed += 1

            except Exception as e:
                error_msg = f'Payroll {payroll.id}: {str(e)}'
                errors.append(error_msg)
                self.stdout.write(self.style.ERROR(f'  ❌ ERROR: {e}'))

            if verbose:
                self.stdout.write('-' * 80)

        # Summary
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('REFRESH SUMMARY'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(f'Total Processed: {refreshed + skipped + len(errors)}')
        self.stdout.write(self.style.SUCCESS(f'Refreshed: {refreshed} ✅'))
        self.stdout.write(f'Skipped (no changes): {skipped}')
        self.stdout.write(self.style.ERROR(f'Errors: {len(errors)} ❌'))

        if errors:
            self.stdout.write(self.style.ERROR('\nErrors:'))
            for error in errors:
                self.stdout.write(self.style.ERROR(f'  - {error}'))

        if dry_run:
            self.stdout.write(self.style.WARNING('\n⚠️  This was a DRY RUN. No changes were made.'))
            self.stdout.write(self.style.WARNING('To apply refresh, run without --dry-run'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Refresh applied to {refreshed} payroll record(s).'))

        self.stdout.write(self.style.SUCCESS('=' * 80 + '\n'))

    def _show_payroll_breakdown(self, payroll):
        """Show detailed payroll breakdown."""
        self.stdout.write('  Breakdown:')
        self.stdout.write(f'    Regular Hours: {payroll.regular_hours}h')
        self.stdout.write(f'    Overtime Hours: {payroll.overtime_hours}h')
        self.stdout.write(f'    Base Pay: ₱{payroll.gross_pay - payroll.allowances - payroll.additional_earnings_total:,.2f}')
        self.stdout.write(f'    Allowances: ₱{payroll.allowances:,.2f}')
        self.stdout.write(f'    Additional Earnings: ₱{payroll.additional_earnings_total:,.2f}')
        self.stdout.write(f'    Gross Pay: ₱{payroll.gross_pay:,.2f}')
        self.stdout.write(f'    Total Deductions: ₱{payroll.total_deductions:,.2f}')

        # Show deduction breakdown
        deductions = payroll.deduction_items.all()
        if deductions.exists():
            self.stdout.write('    Deductions:')
            for deduction in deductions:
                self.stdout.write(f'      - {deduction.name}: ₱{deduction.employee_share:,.2f}')

        self.stdout.write(f'    Net Pay: ₱{payroll.net_pay:,.2f}')
