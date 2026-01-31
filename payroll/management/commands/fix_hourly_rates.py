"""
Management command to fix incorrect hourly rates in existing payroll records.

This fixes payrolls created before the hourly rate calculation bug was fixed.
The bug calculated hourly_rate as basic_salary/40 instead of basic_salary/8.

Usage:
    python manage.py fix_hourly_rates
    python manage.py fix_hourly_rates --dry-run
    python manage.py fix_hourly_rates --status=draft
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from payroll.models import WeeklyPayroll


class Command(BaseCommand):
    help = 'Fix incorrect hourly rates in existing payroll records and recompute'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )
        parser.add_argument(
            '--status',
            type=str,
            default=None,
            help='Only fix payrolls with this status (e.g., draft, approved)',
        )
        parser.add_argument(
            '--payroll-id',
            type=int,
            default=None,
            help='Fix a specific payroll by ID',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        status_filter = options['status']
        payroll_id = options['payroll_id']

        # Build queryset
        queryset = WeeklyPayroll.objects.filter(is_deleted=False)

        if payroll_id:
            queryset = queryset.filter(id=payroll_id)
        elif status_filter:
            queryset = queryset.filter(status=status_filter)

        queryset = queryset.select_related('employee')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        total_count = 0
        fixed_count = 0
        skipped_count = 0
        error_count = 0

        for payroll in queryset:
            total_count += 1

            # Skip if employee has no basic_salary
            if not payroll.employee.basic_salary:
                self.stdout.write(
                    self.style.WARNING(
                        f'  Skipping payroll {payroll.id}: Employee {payroll.employee.get_full_name()} '
                        f'has no basic_salary'
                    )
                )
                skipped_count += 1
                continue

            # Calculate correct hourly rate (basic_salary is daily rate)
            daily_rate = Decimal(payroll.employee.basic_salary)
            correct_hourly_rate = daily_rate / Decimal('8.00')
            current_hourly_rate = Decimal(payroll.hourly_rate)

            # Check if it needs fixing
            if current_hourly_rate == correct_hourly_rate:
                skipped_count += 1
                continue

            # Show what will be fixed
            self.stdout.write(
                f'Payroll {payroll.id} - {payroll.employee.get_full_name()} '
                f'({payroll.week_start} to {payroll.week_end})'
            )
            self.stdout.write(f'  Status: {payroll.status}')
            self.stdout.write(f'  Daily Rate: ₱{daily_rate}')
            self.stdout.write(
                self.style.ERROR(f'  Current Hourly Rate: ₱{current_hourly_rate}')
            )
            self.stdout.write(
                self.style.SUCCESS(f'  Correct Hourly Rate: ₱{correct_hourly_rate}')
            )
            self.stdout.write(f'  Current Gross Pay: ₱{payroll.gross_pay}')

            if not dry_run:
                try:
                    # Update hourly rate
                    payroll.hourly_rate = correct_hourly_rate

                    # Recompute all payroll values based on new hourly rate
                    payroll.compute_from_daily_attendance()

                    # Save with all computed fields
                    payroll.save(
                        update_fields=[
                            'hourly_rate',
                            'regular_hours',
                            'night_diff_hours',
                            'approved_ot_hours',
                            'allowances',
                            'additional_earnings_total',
                            'gross_pay',
                            'night_diff_pay',
                            'approved_ot_pay',
                            'holiday_pay_regular',
                            'holiday_pay_special',
                            'holiday_pay_total',
                            'deductions',
                            'deduction_metadata',
                            'total_deductions',
                            'net_pay',
                            'updated_at',
                        ]
                    )

                    self.stdout.write(
                        self.style.SUCCESS(f'  New Gross Pay: ₱{payroll.gross_pay}')
                    )
                    self.stdout.write(self.style.SUCCESS('  ✓ Fixed and recomputed'))
                    fixed_count += 1

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'  ✗ Error fixing payroll: {str(e)}')
                    )
                    error_count += 1
            else:
                self.stdout.write(self.style.WARNING('  (Would be fixed in real run)'))
                fixed_count += 1

            self.stdout.write('')  # Blank line

        # Summary
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f'Total payrolls checked: {total_count}')
        self.stdout.write(
            self.style.SUCCESS(f'Fixed: {fixed_count}')
            if fixed_count > 0
            else f'Fixed: {fixed_count}'
        )
        self.stdout.write(f'Skipped (already correct or no data): {skipped_count}')
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))

        if dry_run and fixed_count > 0:
            self.stdout.write('')
            self.stdout.write(
                self.style.WARNING(
                    'This was a DRY RUN. Run without --dry-run to apply changes.'
                )
            )
