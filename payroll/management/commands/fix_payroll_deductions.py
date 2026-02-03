"""
Django management command to fix payroll deductions.

This command regenerates deduction records for existing payroll records
to ensure government benefits and all deductions are properly reflected.

Usage:
    # Dry run (show what would be fixed)
    python manage.py fix_payroll_deductions --dry-run

    # Fix all draft payrolls
    python manage.py fix_payroll_deductions

    # Fix specific payroll IDs
    python manage.py fix_payroll_deductions --ids 1,2,3

    # Fix all payrolls regardless of status
    python manage.py fix_payroll_deductions --all-status

    # Verify without fixing
    python manage.py fix_payroll_deductions --verify-only
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q, Sum
from payroll.models import GovernmentBenefit, WeeklyPayroll


class Command(BaseCommand):
    help = 'Fix payroll deductions by regenerating deduction records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )
        parser.add_argument(
            '--ids',
            type=str,
            help='Comma-separated list of payroll IDs to fix',
        )
        parser.add_argument(
            '--all-status',
            action='store_true',
            help='Fix payrolls with any status (default: draft only)',
        )
        parser.add_argument(
            '--verify-only',
            action='store_true',
            help='Only verify payrolls without fixing',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verify_only = options['verify_only']
        verbose = options['verbose']
        payroll_ids = options['ids']
        all_status = options['all_status']

        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('PAYROLL DEDUCTION FIX'))
        self.stdout.write(self.style.SUCCESS('=' * 80))

        # Get payrolls to process
        queryset = WeeklyPayroll.objects.filter(is_deleted=False)

        if payroll_ids:
            ids_list = [int(x.strip()) for x in payroll_ids.split(',')]
            queryset = queryset.filter(id__in=ids_list)
            self.stdout.write(f"Targeting specific payroll IDs: {ids_list}")
        elif not all_status:
            queryset = queryset.filter(status='draft')
            self.stdout.write("Targeting draft payrolls only")
        else:
            self.stdout.write("Targeting all payrolls")

        payrolls = queryset.order_by('-created_at')
        total_count = payrolls.count()

        if total_count == 0:
            self.stdout.write(self.style.WARNING('\nNo payrolls found to process.'))
            return

        self.stdout.write(f"\nFound {total_count} payroll record(s) to process")

        if verify_only:
            self.stdout.write(self.style.WARNING('\nMode: VERIFICATION ONLY'))
            self._verify_payrolls(payrolls, verbose)
        elif dry_run:
            self.stdout.write(self.style.WARNING('\nMode: DRY RUN (no changes will be made)'))
            self._fix_payrolls(payrolls, verbose, dry_run=True)
        else:
            self.stdout.write(self.style.SUCCESS('\nMode: LIVE (will update records)'))
            confirm = input('\nAre you sure you want to fix these payrolls? (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.WARNING('Aborted.'))
                return
            self._fix_payrolls(payrolls, verbose, dry_run=False)

    def _verify_payrolls(self, payrolls, verbose):
        """Verify payroll deductions without fixing."""
        passed = 0
        failed = 0
        issues = []

        self.stdout.write('\n' + '-' * 80)

        for payroll in payrolls:
            payroll_issues = self._check_payroll(payroll, verbose)

            if payroll_issues:
                failed += 1
                issues.extend([f"Payroll {payroll.id}: {issue}" for issue in payroll_issues])
                if verbose:
                    self.stdout.write(self.style.ERROR(f'\n❌ Payroll {payroll.id} - Issues found:'))
                    for issue in payroll_issues:
                        self.stdout.write(self.style.ERROR(f'   - {issue}'))
            else:
                passed += 1
                if verbose:
                    self.stdout.write(self.style.SUCCESS(f'\n✅ Payroll {payroll.id} - OK'))

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
            self.stdout.write(self.style.SUCCESS('\n🎉 All payroll records passed verification!'))

        self.stdout.write(self.style.SUCCESS('=' * 80 + '\n'))

    def _check_payroll(self, payroll, verbose):
        """Check a single payroll for issues."""
        issues = []
        tolerance = Decimal('0.01')

        if verbose:
            self.stdout.write(f'\nPayroll ID: {payroll.id}')
            self.stdout.write(f'Employee: {payroll.employee.get_full_name()}')
            self.stdout.write(f'Week: {payroll.week_start} to {payroll.week_end}')
            self.stdout.write(f'Gross Pay: ₱{payroll.gross_pay:,.2f}')

        # Check 1: Structured deduction records
        deduction_items = payroll.deduction_items.all()
        if verbose:
            self.stdout.write(f'Deduction records: {deduction_items.count()}')

        if deduction_items.count() == 0:
            issues.append('No structured deduction records')

        # Check 2: Government benefits
        gov_benefit_items = deduction_items.filter(category__in=['government', 'tax'])
        active_gov_benefits = GovernmentBenefit.objects.filter(
            is_active=True,
            effective_start__lte=payroll.week_start,
        ).filter(
            Q(effective_end__isnull=True) | Q(effective_end__gte=payroll.week_start)
        ).count()

        if active_gov_benefits > 0 and gov_benefit_items.count() == 0:
            issues.append(f'Missing government benefits (expected {active_gov_benefits})')

        # Check 3: Deductions JSON field
        if not payroll.deductions or len(payroll.deductions) == 0:
            issues.append('Empty deductions JSON field')

        # Check 4: Total calculations
        structured_total = deduction_items.aggregate(
            total=Sum('employee_share')
        )['total'] or Decimal('0.00')

        json_total = Decimal(str(sum(payroll.deductions.values()))) if payroll.deductions else Decimal('0.00')
        stored_total = Decimal(str(payroll.total_deductions))

        if abs(structured_total - stored_total) > tolerance:
            issues.append(f'Total mismatch: ₱{structured_total} (records) vs ₱{stored_total} (stored)')

        if abs(json_total - stored_total) > tolerance:
            issues.append(f'JSON mismatch: ₱{json_total} (JSON) vs ₱{stored_total} (stored)')

        # Check 5: Net pay
        calculated_net_pay = payroll.gross_pay - payroll.total_deductions
        stored_net_pay = Decimal(str(payroll.net_pay))

        if abs(calculated_net_pay - stored_net_pay) > tolerance:
            issues.append(f'Net pay mismatch: ₱{calculated_net_pay} (calc) vs ₱{stored_net_pay} (stored)')

        if verbose and not issues:
            self.stdout.write(f'Total Deductions: ₱{stored_total:,.2f}')
            self.stdout.write(f'Net Pay: ₱{stored_net_pay:,.2f}')

        return issues

    def _fix_payrolls(self, payrolls, verbose, dry_run):
        """Fix payroll deductions."""
        fixed = 0
        skipped = 0
        errors = []

        self.stdout.write('\n' + '-' * 80)

        for payroll in payrolls:
            try:
                old_total = payroll.total_deductions
                old_count = payroll.deduction_items.count()

                self.stdout.write(f'\nPayroll {payroll.id} ({payroll.employee.get_full_name()}):')
                self.stdout.write(f'  Current: {old_count} items, ₱{old_total:,.2f} total')

                if not dry_run:
                    with transaction.atomic():
                        # Regenerate deduction records
                        payroll.create_deduction_records()
                        payroll.refresh_from_db()

                        new_total = payroll.total_deductions
                        new_count = payroll.deduction_items.count()

                        self.stdout.write(self.style.SUCCESS(
                            f'  Updated: {new_count} items, ₱{new_total:,.2f} total'
                        ))

                        change_count = new_count - old_count
                        change_amount = new_total - old_total

                        if change_count != 0 or abs(change_amount) > Decimal('0.01'):
                            self.stdout.write(self.style.WARNING(
                                f'  Change: {change_count:+d} items, ₱{change_amount:+,.2f}'
                            ))

                        if verbose:
                            self._show_deduction_breakdown(payroll)

                    fixed += 1
                else:
                    self.stdout.write('  Would regenerate deduction records')
                    fixed += 1

            except Exception as e:
                error_msg = f'Payroll {payroll.id}: {str(e)}'
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
            self.stdout.write(self.style.SUCCESS(f'\n✅ Fix applied to {fixed} payroll record(s).'))

        self.stdout.write(self.style.SUCCESS('=' * 80 + '\n'))

    def _show_deduction_breakdown(self, payroll):
        """Show detailed deduction breakdown."""
        deduction_items = payroll.deduction_items.all().order_by('category', 'name')

        if deduction_items.exists():
            self.stdout.write('  Deductions:')
            for item in deduction_items:
                self.stdout.write(f'    [{item.category}] {item.name}: ₱{item.employee_share:,.2f}')
                if item.employer_share > 0:
                    self.stdout.write(f'      (Employer: ₱{item.employer_share:,.2f})')
