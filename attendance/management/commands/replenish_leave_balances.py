"""
Django management command to replenish employee leave balances.

This command resets/replenishes leave balances for employees annually.
Typically run on January 1st to give employees their annual leave allocation.

Usage:
    # Replenish all employees
    python manage.py replenish_leave_balances

    # Replenish specific employee
    python manage.py replenish_leave_balances --employee-id 5

    # Dry run (show what would be replenished)
    python manage.py replenish_leave_balances --dry-run

    # Custom leave amounts
    python manage.py replenish_leave_balances --sick-leave 10 --emergency-leave 5
"""


from django.core.management.base import BaseCommand
from django.db import transaction
from datetime import date
from users.models import CustomUser

from attendance.models import LeaveBalance


class Command(BaseCommand):
    help = 'Replenish employee leave balances for the new year'

    def add_arguments(self, parser):
        parser.add_argument(
            '--employee-id',
            type=int,
            help='Replenish specific employee by ID',
        )
        parser.add_argument(
            '--sick-leave',
            type=int,
            default=7,
            help='Sick leave days to allocate (default: 7)',
        )
        parser.add_argument(
            '--emergency-leave',
            type=int,
            default=3,
            help='Emergency leave days to allocate (default: 3)',
        )
        parser.add_argument(
            '--year',
            type=int,
            default=date.today().year,
            help='Year for leave balance (default: current year)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be replenished without making changes',
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
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset to full allocation (overwrite existing)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verbose = options['verbose']
        employee_id = options['employee_id']
        sick_leave_days = options['sick_leave']
        emergency_leave_days = options['emergency_leave']
        year = options['year']
        reset = options['reset']
        force = options['force']

        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('LEAVE BALANCE REPLENISHMENT'))
        self.stdout.write(self.style.SUCCESS('=' * 80))

        self.stdout.write('\nAllocation:')
        self.stdout.write(f'  Year: {year}')
        self.stdout.write(f'  Sick Leave: {sick_leave_days} days')
        self.stdout.write(f'  Emergency Leave: {emergency_leave_days} days')
        self.stdout.write(f'  Mode: {"RESET (overwrite)" if reset else "REPLENISH (add)"}')

        # Get employees to process
        if employee_id:
            employees = CustomUser.objects.filter(id=employee_id, is_active=True)
            self.stdout.write(f'\nTargeting employee ID: {employee_id}')
        else:
            employees = CustomUser.objects.filter(is_active=True)
            self.stdout.write('\nTargeting all active employees')

        total_count = employees.count()

        if total_count == 0:
            self.stdout.write(self.style.WARNING('\nNo employees found to process.'))
            return

        self.stdout.write(f'Found {total_count} employee(s) to process')

        if dry_run:
            self.stdout.write(self.style.WARNING('\nMode: DRY RUN (no changes will be made)'))
            self._replenish_leaves(
                employees,
                sick_leave_days,
                emergency_leave_days,
                year,
                reset,
                verbose,
                dry_run=True
            )
        else:
            self.stdout.write(self.style.SUCCESS('\nMode: LIVE (will update records)'))
            if not force:
                confirm = input(f'\nReplenish leave balances for {total_count} employee(s)? (yes/no): ')
                if confirm.lower() != 'yes':
                    self.stdout.write(self.style.WARNING('Aborted.'))
                    return
            self._replenish_leaves(
                employees,
                sick_leave_days,
                emergency_leave_days,
                year,
                reset,
                verbose,
                dry_run=False
            )

    def _replenish_leaves(self, employees, sick_days, emergency_days, year, reset, verbose, dry_run):
        """Replenish leave balances for employees."""
        replenished = 0
        created = 0
        skipped = 0
        errors = []

        self.stdout.write('\n' + '-' * 80)

        for employee in employees:
            try:
                # Get or create leave balance
                balance, was_created = LeaveBalance.objects.get_or_create(
                    employee=employee,
                    year=year,
                    defaults={
                        'sick_leave_total': sick_days,
                        'sick_leave_used': 0,
                        'emergency_leave_total': emergency_days,
                        'emergency_leave_used': 0,
                    }
                )

                self.stdout.write(f'\n{employee.get_full_name()} (ID: {employee.id}):')

                if was_created:
                    if verbose:
                        self.stdout.write('  Old: No balance record (created new)')
                        self.stdout.write(f'  New: Sick {sick_days} days, Emergency {emergency_days} days')

                    if not dry_run:
                        self.stdout.write(self.style.SUCCESS('  ✅ Created new balance'))
                    else:
                        self.stdout.write(self.style.WARNING('  Would create new balance'))
                    created += 1
                else:
                    # Existing balance
                    old_sick_total = balance.sick_leave_total
                    old_sick_used = balance.sick_leave_used
                    old_emergency_total = balance.emergency_leave_total
                    old_emergency_used = balance.emergency_leave_used

                    if reset:
                        # Reset mode: Set to full allocation, clear used
                        new_sick_total = sick_days
                        new_sick_used = 0
                        new_emergency_total = emergency_days
                        new_emergency_used = 0
                    else:
                        # Replenish mode: Add to existing
                        new_sick_total = old_sick_total + sick_days
                        new_sick_used = old_sick_used
                        new_emergency_total = old_emergency_total + emergency_days
                        new_emergency_used = old_emergency_used

                    if verbose:
                        self.stdout.write(f'  Old Sick: {old_sick_total} total, {old_sick_used} used, {old_sick_total - old_sick_used} remaining')
                        self.stdout.write(f'  New Sick: {new_sick_total} total, {new_sick_used} used, {new_sick_total - new_sick_used} remaining')
                        self.stdout.write(f'  Old Emergency: {old_emergency_total} total, {old_emergency_used} used, {old_emergency_total - old_emergency_used} remaining')
                        self.stdout.write(f'  New Emergency: {new_emergency_total} total, {new_emergency_used} used, {new_emergency_total - new_emergency_used} remaining')

                    if not dry_run:
                        with transaction.atomic():
                            balance.sick_leave_total = new_sick_total
                            balance.sick_leave_used = new_sick_used
                            balance.emergency_leave_total = new_emergency_total
                            balance.emergency_leave_used = new_emergency_used
                            balance.save(update_fields=[
                                'sick_leave_total',
                                'sick_leave_used',
                                'emergency_leave_total',
                                'emergency_leave_used',
                                'updated_at'
                            ])
                            self.stdout.write(self.style.SUCCESS('  ✅ Replenished'))
                    else:
                        self.stdout.write(self.style.WARNING('  Would replenish'))

                    replenished += 1

            except Exception as e:
                error_msg = f'{employee.get_full_name()} (ID {employee.id}): {str(e)}'
                errors.append(error_msg)
                self.stdout.write(self.style.ERROR(f'  ❌ ERROR: {e}'))

            if verbose:
                self.stdout.write('-' * 80)

        # Summary
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('REPLENISHMENT SUMMARY'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(f'Total Processed: {replenished + created + skipped + len(errors)}')
        self.stdout.write(self.style.SUCCESS(f'Replenished: {replenished} ✅'))
        self.stdout.write(self.style.SUCCESS(f'Created: {created} ✅'))
        self.stdout.write(f'Skipped: {skipped}')
        self.stdout.write(self.style.ERROR(f'Errors: {len(errors)} ❌'))

        if errors:
            self.stdout.write(self.style.ERROR('\nErrors:'))
            for error in errors:
                self.stdout.write(self.style.ERROR(f'  - {error}'))

        if dry_run:
            self.stdout.write(self.style.WARNING('\n⚠️  This was a DRY RUN. No changes were made.'))
            self.stdout.write(self.style.WARNING('To apply changes, run without --dry-run'))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✅ Replenished leave balances for {replenished + created} employee(s).'
                )
            )

        self.stdout.write(self.style.SUCCESS('=' * 80 + '\n'))
