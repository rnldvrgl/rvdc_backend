"""
Django management command to fix overtime request date inconsistencies.

This command finds OvertimeRequest records where the 'date' field doesn't match
the date of 'time_start' field and updates them to be consistent.

Usage:
    python manage.py fix_overtime_dates --dry-run  # Preview changes
    python manage.py fix_overtime_dates             # Apply changes
"""

from django.core.management.base import BaseCommand

from attendance.models import OvertimeRequest


class Command(BaseCommand):
    help = "Fix overtime request date inconsistencies where date field doesn't match time_start date"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without applying them',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write(self.style.MIGRATE_HEADING('Fixing Overtime Request Date Inconsistencies'))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))

        if dry_run:
            self.stdout.write(self.style.WARNING('\n🔍 DRY RUN MODE - No changes will be saved\n'))
        else:
            self.stdout.write(self.style.WARNING('\n⚠️  LIVE MODE - Changes will be saved to database\n'))

        # Find all overtime requests
        all_overtime = OvertimeRequest.objects.all()
        total_count = all_overtime.count()
        self.stdout.write(f'📊 Total overtime requests: {total_count}\n')

        # Track statistics
        inconsistent_count = 0
        fixed_count = 0
        errors = []

        self.stdout.write(self.style.MIGRATE_LABEL('\n🔍 Checking for inconsistencies...\n'))

        for ot in all_overtime:
            # Get the date from time_start
            time_start_date = ot.time_start.date() if ot.time_start else None

            # Check if date field matches time_start date
            if ot.date and time_start_date and ot.date != time_start_date:
                inconsistent_count += 1

                self.stdout.write(
                    self.style.WARNING(
                        f'\n❌ Inconsistent data found (ID: {ot.id})'
                    )
                )
                self.stdout.write(f'   Employee: {ot.employee.get_full_name()} (ID: {ot.employee_id})')
                self.stdout.write(f'   Current date field: {ot.date}')
                self.stdout.write(f'   time_start: {ot.time_start}')
                self.stdout.write(f'   time_start date: {time_start_date}')
                self.stdout.write(f'   time_end: {ot.time_end}')
                self.stdout.write(f'   Approved: {ot.approved}')
                self.stdout.write(f'   Status: {"✅ Approved" if ot.approved else "⏳ Pending"}')

                if not dry_run:
                    try:
                        # Fix the date field
                        old_date = ot.date
                        ot.date = time_start_date
                        ot.save(update_fields=['date', 'updated_at'])

                        self.stdout.write(
                            self.style.SUCCESS(
                                f'   ✅ FIXED: Updated date from {old_date} → {time_start_date}'
                            )
                        )
                        fixed_count += 1
                    except Exception as e:
                        error_msg = f'ID {ot.id}: {str(e)}'
                        errors.append(error_msg)
                        self.stdout.write(
                            self.style.ERROR(f'   ❌ ERROR: {str(e)}')
                        )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'   🔄 WOULD FIX: Update date from {ot.date} → {time_start_date}'
                        )
                    )

        # Summary
        self.stdout.write(self.style.MIGRATE_HEADING('\n' + '=' * 80))
        self.stdout.write(self.style.MIGRATE_HEADING('Summary'))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80 + '\n'))

        self.stdout.write(f'Total overtime requests: {total_count}')
        self.stdout.write(f'Consistent records: {total_count - inconsistent_count}')

        if inconsistent_count > 0:
            self.stdout.write(
                self.style.WARNING(f'Inconsistent records found: {inconsistent_count}')
            )

            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        f'\n🔄 {inconsistent_count} record(s) would be fixed in live mode'
                    )
                )
                self.stdout.write(
                    self.style.MIGRATE_LABEL(
                        '\nRun without --dry-run to apply changes:\n'
                        '  python manage.py fix_overtime_dates'
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f'\n✅ Successfully fixed: {fixed_count} record(s)')
                )

                if errors:
                    self.stdout.write(
                        self.style.ERROR(f'\n❌ Errors encountered: {len(errors)}')
                    )
                    for error in errors:
                        self.stdout.write(self.style.ERROR(f'   - {error}'))
        else:
            self.stdout.write(
                self.style.SUCCESS('\n✅ All overtime request dates are consistent!')
            )

        self.stdout.write(self.style.MIGRATE_HEADING('\n' + '=' * 80))

        # Exit with appropriate code
        if not dry_run and errors:
            self.stdout.write(
                self.style.ERROR('\n⚠️  Command completed with errors')
            )
            return

        if dry_run and inconsistent_count > 0:
            self.stdout.write(
                self.style.WARNING('\n🔍 Dry run complete - review changes above')
            )
        elif not dry_run and fixed_count > 0:
            self.stdout.write(
                self.style.SUCCESS('\n✅ All fixes applied successfully!')
            )
            self.stdout.write(
                self.style.MIGRATE_LABEL(
                    '\nNext steps:\n'
                    '1. Verify the changes in Django admin\n'
                    '2. Recompute affected payrolls\n'
                    '3. Check that overtime now appears in payroll calculations'
                )
            )
