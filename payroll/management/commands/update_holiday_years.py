"""
Django management command to update holiday years.

This command updates all holiday dates to the next year, maintaining the
same month and day. Useful for recurring holidays that need to be rolled
forward annually.

Usage:
    # Update all holidays to next year
    python manage.py update_holiday_years

    # Update to specific year
    python manage.py update_holiday_years --year 2025

    # Dry run (show what would be updated)
    python manage.py update_holiday_years --dry-run

    # Update only specific holidays
    python manage.py update_holiday_years --ids 1,2,3
"""

from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction
from payroll.models import Holiday


class Command(BaseCommand):
    help = 'Update holiday dates to the next year'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            help='Target year (default: next year)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )
        parser.add_argument(
            '--ids',
            type=str,
            help='Comma-separated list of holiday IDs to update',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verbose = options['verbose']
        target_year = options['year']
        holiday_ids = options['ids']

        current_year = date.today().year
        target_year = target_year or (current_year + 1)

        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('HOLIDAY YEAR UPDATE'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(f'\nTarget Year: {target_year}')

        # Get holidays to update
        queryset = Holiday.objects.filter(is_deleted=False)

        if holiday_ids:
            ids_list = [int(x.strip()) for x in holiday_ids.split(',')]
            queryset = queryset.filter(id__in=ids_list)
            self.stdout.write(f"Targeting specific holiday IDs: {ids_list}")
        else:
            # Update holidays from previous years
            queryset = queryset.filter(date__year__lt=target_year)
            self.stdout.write(f"Targeting holidays before {target_year}")

        holidays = queryset.order_by('date')
        total_count = holidays.count()

        if total_count == 0:
            self.stdout.write(self.style.WARNING('\nNo holidays found to update.'))
            self.stdout.write('All holidays are already in the target year or later.')
            return

        self.stdout.write(f"\nFound {total_count} holiday(s) to update")

        if dry_run:
            self.stdout.write(self.style.WARNING('\nMode: DRY RUN (no changes will be made)'))
            self._update_holidays(holidays, target_year, verbose, dry_run=True)
        else:
            self.stdout.write(self.style.SUCCESS('\nMode: LIVE (will update records)'))
            confirm = input(f'\nUpdate {total_count} holiday(s) to year {target_year}? (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.WARNING('Aborted.'))
                return
            self._update_holidays(holidays, target_year, verbose, dry_run=False)

    def _update_holidays(self, holidays, target_year, verbose, dry_run):
        """Update holiday dates to target year."""
        updated = 0
        skipped = 0
        errors = []

        self.stdout.write('\n' + '-' * 80)

        for holiday in holidays:
            try:
                old_date = holiday.date

                # Calculate new date (same month/day, new year)
                try:
                    new_date = old_date.replace(year=target_year)
                except ValueError:
                    # Handle Feb 29 in non-leap years
                    if old_date.month == 2 and old_date.day == 29:
                        new_date = date(target_year, 2, 28)
                        self.stdout.write(
                            self.style.WARNING(
                                f'  ⚠️  Feb 29 adjusted to Feb 28 for {target_year}'
                            )
                        )
                    else:
                        raise

                # Skip if already at target year
                if old_date.year == target_year:
                    if verbose:
                        self.stdout.write(f'\n{holiday.name}: Already in {target_year}, skipping')
                    skipped += 1
                    continue

                self.stdout.write(f'\n{holiday.name}:')
                self.stdout.write(f'  Old: {old_date} ({old_date.strftime("%A")})')
                self.stdout.write(f'  New: {new_date} ({new_date.strftime("%A")})')

                if not dry_run:
                    with transaction.atomic():
                        holiday.date = new_date
                        holiday.save(update_fields=['date', 'updated_at'])
                        self.stdout.write(self.style.SUCCESS('  ✅ Updated'))
                else:
                    self.stdout.write(self.style.WARNING('  Would update'))

                updated += 1

            except Exception as e:
                error_msg = f'{holiday.name} (ID {holiday.id}): {str(e)}'
                errors.append(error_msg)
                self.stdout.write(self.style.ERROR(f'  ❌ ERROR: {e}'))

            if verbose:
                self.stdout.write('-' * 80)

        # Summary
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('UPDATE SUMMARY'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(f'Total Processed: {updated + skipped + len(errors)}')
        self.stdout.write(self.style.SUCCESS(f'Updated: {updated} ✅'))
        self.stdout.write(f'Skipped: {skipped}')
        self.stdout.write(self.style.ERROR(f'Errors: {len(errors)} ❌'))

        if errors:
            self.stdout.write(self.style.ERROR('\nErrors:'))
            for error in errors:
                self.stdout.write(self.style.ERROR(f'  - {error}'))

        if dry_run:
            self.stdout.write(self.style.WARNING('\n⚠️  This was a DRY RUN. No changes were made.'))
            self.stdout.write(self.style.WARNING('To apply updates, run without --dry-run'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Updated {updated} holiday record(s) to year {target_year}.'))

        self.stdout.write(self.style.SUCCESS('=' * 80 + '\n'))
