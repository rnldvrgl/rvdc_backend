"""
Django management command to archive or delete old payroll records.

This command helps manage database size by archiving or deleting payroll records
from previous years. Useful for annual cleanup while maintaining data integrity.

Usage:
    # Delete payrolls older than current year
    python manage.py archive_old_payrolls --delete

    # Delete payrolls from specific year
    python manage.py archive_old_payrolls --year 2023 --delete

    # Dry run (show what would be deleted)
    python manage.py archive_old_payrolls --dry-run

    # Export before deleting
    python manage.py archive_old_payrolls --export --delete

    # Keep last N years
    python manage.py archive_old_payrolls --keep-years 2 --delete
"""

import csv
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Sum
from payroll.models import WeeklyPayroll


class Command(BaseCommand):
    help = 'Archive or delete old payroll records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            help='Delete payrolls from specific year (default: years before current)',
        )
        parser.add_argument(
            '--keep-years',
            type=int,
            default=1,
            help='Number of recent years to keep (default: 1)',
        )
        parser.add_argument(
            '--delete',
            action='store_true',
            help='Actually delete records (default: soft delete)',
        )
        parser.add_argument(
            '--hard-delete',
            action='store_true',
            help='Permanently delete from database (cannot be undone!)',
        )
        parser.add_argument(
            '--export',
            action='store_true',
            help='Export to CSV before deleting',
        )
        parser.add_argument(
            '--export-path',
            type=str,
            default='/tmp/payroll_archive',
            help='Directory for export files (default: /tmp/payroll_archive)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without making changes',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )
        parser.add_argument(
            '--status',
            type=str,
            choices=['draft', 'approved', 'paid', 'all'],
            default='all',
            help='Delete only specific status (default: all)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verbose = options['verbose']
        year = options['year']
        keep_years = options['keep_years']
        delete = options['delete']
        hard_delete = options['hard_delete']
        export = options['export']
        export_path = options['export_path']
        status_filter = options['status']

        current_year = date.today().year

        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('PAYROLL ARCHIVE/DELETE'))
        self.stdout.write(self.style.SUCCESS('=' * 80))

        # Determine cutoff year
        if year:
            cutoff_year = year
            self.stdout.write(f'\nTargeting year: {year}')
        else:
            cutoff_year = current_year - keep_years
            self.stdout.write(f'\nCurrent year: {current_year}')
            self.stdout.write(f'Keep years: {keep_years}')
            self.stdout.write(f'Cutoff year: {cutoff_year} (delete before this)')

        # Get payrolls to process
        queryset = WeeklyPayroll.objects.filter(
            week_start__year__lt=cutoff_year
        )

        if status_filter != 'all':
            queryset = queryset.filter(status=status_filter)
            self.stdout.write(f'Status filter: {status_filter}')

        # Exclude already soft-deleted unless hard deleting
        if not hard_delete:
            queryset = queryset.filter(is_deleted=False)

        payrolls = queryset.order_by('week_start')
        total_count = payrolls.count()

        if total_count == 0:
            self.stdout.write(self.style.WARNING('\nNo payroll records found to archive/delete.'))
            self.stdout.write(f'All payrolls are from {cutoff_year} or later.')
            return

        # Show summary
        self.stdout.write(f'\nFound {total_count} payroll record(s) to process')

        # Get statistics
        stats = payrolls.aggregate(
            total_gross=Sum('gross_pay'),
            total_net=Sum('net_pay'),
            total_deductions=Sum('total_deductions'),
        )

        self.stdout.write('\nStatistics:')
        self.stdout.write(f"  Total Gross Pay: ₱{stats['total_gross'] or 0:,.2f}")
        self.stdout.write(f"  Total Net Pay: ₱{stats['total_net'] or 0:,.2f}")
        self.stdout.write(f"  Total Deductions: ₱{stats['total_deductions'] or 0:,.2f}")

        # Count by status
        status_counts = payrolls.values('status').annotate(count=Count('id'))
        self.stdout.write('\nBy Status:')
        for item in status_counts:
            self.stdout.write(f"  {item['status']}: {item['count']}")

        # Count by year
        year_counts = payrolls.values('week_start__year').annotate(count=Count('id'))
        self.stdout.write('\nBy Year:')
        for item in sorted(year_counts, key=lambda x: x['week_start__year']):
            self.stdout.write(f"  {item['week_start__year']}: {item['count']}")

        # Export if requested
        if export and not dry_run:
            self.stdout.write('\n' + '-' * 80)
            self._export_payrolls(payrolls, export_path, cutoff_year)

        # Process deletion
        if dry_run:
            self.stdout.write(self.style.WARNING('\nMode: DRY RUN (no changes will be made)'))
            self._show_deletion_plan(payrolls, hard_delete, verbose)
        elif delete or hard_delete:
            action = 'HARD DELETE' if hard_delete else 'SOFT DELETE'
            self.stdout.write(self.style.SUCCESS(f'\nMode: {action}'))

            if hard_delete:
                self.stdout.write(self.style.ERROR('\n⚠️  WARNING: HARD DELETE CANNOT BE UNDONE!'))

            confirm_msg = f'\n{action} {total_count} payroll record(s) from before {cutoff_year}? (yes/no): '
            confirm = input(confirm_msg)

            if confirm.lower() != 'yes':
                self.stdout.write(self.style.WARNING('Aborted.'))
                return

            self._delete_payrolls(payrolls, hard_delete, verbose)
        else:
            self.stdout.write(self.style.WARNING('\nNo --delete or --hard-delete flag provided.'))
            self.stdout.write('This was a preview. Add --delete to perform soft delete.')
            self.stdout.write('Or add --hard-delete to permanently remove records.')

    def _export_payrolls(self, payrolls, export_path, cutoff_year):
        """Export payrolls to CSV before deletion."""
        self.stdout.write(self.style.SUCCESS('\nExporting payrolls...'))

        # Create export directory
        Path(export_path).mkdir(parents=True, exist_ok=True)

        # Export main payroll data
        csv_file = f'{export_path}/payrolls_before_{cutoff_year}.csv'

        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            # Header
            writer.writerow([
                'ID', 'Employee', 'Week Start', 'Week End', 'Status',
                'Regular Hours', 'Overtime Hours', 'Hourly Rate',
                'Gross Pay', 'Total Deductions', 'Net Pay',
                'Created At', 'Approved At'
            ])

            # Data
            for payroll in payrolls:
                writer.writerow([
                    payroll.id,
                    payroll.employee.get_full_name(),
                    payroll.week_start,
                    payroll.week_end,
                    payroll.status,
                    payroll.regular_hours,
                    payroll.overtime_hours,
                    payroll.hourly_rate,
                    payroll.gross_pay,
                    payroll.total_deductions,
                    payroll.net_pay,
                    payroll.created_at,
                    payroll.approved_at,
                ])

        self.stdout.write(self.style.SUCCESS(f'✅ Exported to: {csv_file}'))

        # Export deductions separately
        deductions_file = f'{export_path}/deductions_before_{cutoff_year}.csv'

        with open(deductions_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            writer.writerow([
                'Payroll ID', 'Employee', 'Week Start', 'Category',
                'Name', 'Employee Share', 'Employer Share'
            ])

            for payroll in payrolls:
                for deduction in payroll.deduction_items.all():
                    writer.writerow([
                        payroll.id,
                        payroll.employee.get_full_name(),
                        payroll.week_start,
                        deduction.category,
                        deduction.name,
                        deduction.employee_share,
                        deduction.employer_share,
                    ])

        self.stdout.write(self.style.SUCCESS(f'✅ Exported deductions to: {deductions_file}'))

    def _show_deletion_plan(self, payrolls, hard_delete, verbose):
        """Show what would be deleted."""
        action = 'permanently delete' if hard_delete else 'soft delete (mark as deleted)'

        self.stdout.write(f'\nWould {action}:')
        self.stdout.write('-' * 80)

        if verbose:
            for payroll in payrolls[:20]:  # Show first 20
                self.stdout.write(
                    f'  ID {payroll.id}: {payroll.employee.get_full_name()} - '
                    f'{payroll.week_start} to {payroll.week_end} - '
                    f'{payroll.status} - ₱{payroll.net_pay:,.2f}'
                )

            if payrolls.count() > 20:
                self.stdout.write(f'  ... and {payrolls.count() - 20} more')
        else:
            self.stdout.write(f'  {payrolls.count()} payroll records')

        self.stdout.write('\nTo proceed, run without --dry-run and add --delete or --hard-delete')

    def _delete_payrolls(self, payrolls, hard_delete, verbose):
        """Delete payrolls (soft or hard)."""
        deleted = 0
        errors = []

        self.stdout.write('\n' + '-' * 80)

        if hard_delete:
            self.stdout.write('Permanently deleting payrolls...')

            for payroll in payrolls:
                try:
                    payroll_id = payroll.id
                    employee_name = payroll.employee.get_full_name()
                    week = f'{payroll.week_start} to {payroll.week_end}'

                    with transaction.atomic():
                        # Delete related deductions first
                        payroll.deduction_items.all().delete()

                        # Delete payroll
                        payroll.delete()

                        if verbose:
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'  ✅ Deleted: ID {payroll_id} - {employee_name} - {week}'
                                )
                            )

                    deleted += 1

                except Exception as e:
                    error_msg = f'Payroll {payroll.id}: {str(e)}'
                    errors.append(error_msg)
                    self.stdout.write(self.style.ERROR(f'  ❌ ERROR: {e}'))

        else:
            self.stdout.write('Soft deleting payrolls (marking as deleted)...')

            try:
                with transaction.atomic():
                    updated = payrolls.update(is_deleted=True)
                    deleted = updated

                    self.stdout.write(self.style.SUCCESS(f'✅ Soft deleted {updated} payroll(s)'))

                    if verbose:
                        for payroll in payrolls[:10]:
                            self.stdout.write(
                                f'  {payroll.id}: {payroll.employee.get_full_name()} - '
                                f'{payroll.week_start}'
                            )

            except Exception as e:
                errors.append(str(e))
                self.stdout.write(self.style.ERROR(f'❌ ERROR: {e}'))

        # Summary
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('DELETION SUMMARY'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(f'Total Deleted: {deleted} ✅')
        self.stdout.write(self.style.ERROR(f'Errors: {len(errors)} ❌'))

        if errors:
            self.stdout.write(self.style.ERROR('\nErrors:'))
            for error in errors:
                self.stdout.write(self.style.ERROR(f'  - {error}'))

        action = 'permanently deleted' if hard_delete else 'soft deleted'
        self.stdout.write(self.style.SUCCESS(f'\n✅ Successfully {action} {deleted} payroll record(s).'))
        self.stdout.write(self.style.SUCCESS('=' * 80 + '\n'))
