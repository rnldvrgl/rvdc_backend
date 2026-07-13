"""
Django management command to add Philippine holidays.

This command adds all regular and special non-working holidays
for the Philippines for a specific year.

Usage:
    # Add holidays for current year
    python manage.py add_philippine_holidays

    # Add holidays for specific year
    python manage.py add_philippine_holidays --year 2026

    # Dry run (show what would be added)
    python manage.py add_philippine_holidays --dry-run

    # Skip holidays that already exist
    python manage.py add_philippine_holidays --skip-existing
"""

from datetime import date
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from payroll.models import Holiday


class Command(BaseCommand):
    help = 'Add Philippine regular and special non-working holidays for a specific year'

    # Philippine holidays (fixed dates)
    HOLIDAYS_BY_YEAR = {
    2026: [
        {"month": 1, "day": 1, "name": "New Year's Day"},
        {"month": 4, "day": 2, "name": "Maundy Thursday"},
        {"month": 4, "day": 3, "name": "Good Friday"},
        {"month": 4, "day": 9, "name": "Araw ng Kagitingan (Day of Valor)"},
        {"month": 5, "day": 1, "name": "Labor Day"},
        {"month": 6, "day": 12, "name": "Independence Day"},
        {"month": 8, "day": 31, "name": "National Heroes Day"},
        {"month": 11, "day": 30, "name": "Bonifacio Day"},
        {"month": 12, "day": 25, "name": "Christmas Day"},
        {"month": 12, "day": 30, "name": "Rizal Day"},
    ],

    2027: [
        {"month": 1, "day": 1, "name": "New Year's Day"},
        {"month": 3, "day": 25, "name": "Maundy Thursday"},
        {"month": 3, "day": 26, "name": "Good Friday"},
        {"month": 4, "day": 9, "name": "Araw ng Kagitingan (Day of Valor)"},
        {"month": 5, "day": 1, "name": "Labor Day"},
        {"month": 6, "day": 12, "name": "Independence Day"},
        {"month": 8, "day": 30, "name": "National Heroes Day"},
        {"month": 11, "day": 30, "name": "Bonifacio Day"},
        {"month": 12, "day": 25, "name": "Christmas Day"},
        {"month": 12, "day": 30, "name": "Rizal Day"},
    ],

    2028: [
        {"month": 1, "day": 1, "name": "New Year's Day"},
        {"month": 4, "day": 13, "name": "Maundy Thursday"},
        {"month": 4, "day": 14, "name": "Good Friday"},
        {"month": 4, "day": 9, "name": "Araw ng Kagitingan (Day of Valor)"},
        {"month": 5, "day": 1, "name": "Labor Day"},
        {"month": 6, "day": 12, "name": "Independence Day"},
        {"month": 8, "day": 28, "name": "National Heroes Day"},
        {"month": 11, "day": 30, "name": "Bonifacio Day"},
        {"month": 12, "day": 25, "name": "Christmas Day"},
        {"month": 12, "day": 30, "name": "Rizal Day"},
    ],

    2029: [
        {"month": 1, "day": 1, "name": "New Year's Day"},
        {"month": 3, "day": 29, "name": "Maundy Thursday"},
        {"month": 3, "day": 30, "name": "Good Friday"},
        {"month": 4, "day": 9, "name": "Araw ng Kagitingan (Day of Valor)"},
        {"month": 5, "day": 1, "name": "Labor Day"},
        {"month": 6, "day": 12, "name": "Independence Day"},
        {"month": 8, "day": 27, "name": "National Heroes Day"},
        {"month": 11, "day": 30, "name": "Bonifacio Day"},
        {"month": 12, "day": 25, "name": "Christmas Day"},
        {"month": 12, "day": 30, "name": "Rizal Day"},
    ],

    2030: [
        {"month": 1, "day": 1, "name": "New Year's Day"},
        {"month": 4, "day": 18, "name": "Maundy Thursday"},
        {"month": 4, "day": 19, "name": "Good Friday"},
        {"month": 4, "day": 9, "name": "Araw ng Kagitingan (Day of Valor)"},
        {"month": 5, "day": 1, "name": "Labor Day"},
        {"month": 6, "day": 12, "name": "Independence Day"},
        {"month": 8, "day": 26, "name": "National Heroes Day"},
        {"month": 11, "day": 30, "name": "Bonifacio Day"},
        {"month": 12, "day": 25, "name": "Christmas Day"},
        {"month": 12, "day": 30, "name": "Rizal Day"},
    ],

    2031: [
        {"month": 1, "day": 1, "name": "New Year's Day"},
        {"month": 4, "day": 10, "name": "Maundy Thursday"},
        {"month": 4, "day": 11, "name": "Good Friday"},
        {"month": 4, "day": 9, "name": "Araw ng Kagitingan (Day of Valor)"},
        {"month": 5, "day": 1, "name": "Labor Day"},
        {"month": 6, "day": 12, "name": "Independence Day"},
        {"month": 8, "day": 25, "name": "National Heroes Day"},
        {"month": 11, "day": 30, "name": "Bonifacio Day"},
        {"month": 12, "day": 25, "name": "Christmas Day"},
        {"month": 12, "day": 30, "name": "Rizal Day"},
    ],

    2032: [
        {"month": 1, "day": 1, "name": "New Year's Day"},
        {"month": 3, "day": 25, "name": "Maundy Thursday"},
        {"month": 3, "day": 26, "name": "Good Friday"},
        {"month": 4, "day": 9, "name": "Araw ng Kagitingan (Day of Valor)"},
        {"month": 5, "day": 1, "name": "Labor Day"},
        {"month": 6, "day": 12, "name": "Independence Day"},
        {"month": 8, "day": 30, "name": "National Heroes Day"},
        {"month": 11, "day": 30, "name": "Bonifacio Day"},
        {"month": 12, "day": 25, "name": "Christmas Day"},
        {"month": 12, "day": 30, "name": "Rizal Day"},
    ],

    2033: [
        {"month": 1, "day": 1, "name": "New Year's Day"},
        {"month": 4, "day": 14, "name": "Maundy Thursday"},
        {"month": 4, "day": 15, "name": "Good Friday"},
        {"month": 4, "day": 9, "name": "Araw ng Kagitingan (Day of Valor)"},
        {"month": 5, "day": 1, "name": "Labor Day"},
        {"month": 6, "day": 12, "name": "Independence Day"},
        {"month": 8, "day": 29, "name": "National Heroes Day"},
        {"month": 11, "day": 30, "name": "Bonifacio Day"},
        {"month": 12, "day": 25, "name": "Christmas Day"},
        {"month": 12, "day": 30, "name": "Rizal Day"},
    ],

    2034: [
        {"month": 1, "day": 1, "name": "New Year's Day"},
        {"month": 4, "day": 6, "name": "Maundy Thursday"},
        {"month": 4, "day": 7, "name": "Good Friday"},
        {"month": 4, "day": 9, "name": "Araw ng Kagitingan (Day of Valor)"},
        {"month": 5, "day": 1, "name": "Labor Day"},
        {"month": 6, "day": 12, "name": "Independence Day"},
        {"month": 8, "day": 28, "name": "National Heroes Day"},
        {"month": 11, "day": 30, "name": "Bonifacio Day"},
        {"month": 12, "day": 25, "name": "Christmas Day"},
        {"month": 12, "day": 30, "name": "Rizal Day"},
    ],

    2035: [
        {"month": 1, "day": 1, "name": "New Year's Day"},
        {"month": 3, "day": 22, "name": "Maundy Thursday"},
        {"month": 3, "day": 23, "name": "Good Friday"},
        {"month": 4, "day": 9, "name": "Araw ng Kagitingan (Day of Valor)"},
        {"month": 5, "day": 1, "name": "Labor Day"},
        {"month": 6, "day": 12, "name": "Independence Day"},
        {"month": 8, "day": 27, "name": "National Heroes Day"},
        {"month": 11, "day": 30, "name": "Bonifacio Day"},
        {"month": 12, "day": 25, "name": "Christmas Day"},
        {"month": 12, "day": 30, "name": "Rizal Day"},
    ],
}

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            default=date.today().year,
            help='Year to add holidays for (default: current year)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be added without making changes'
        )
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Skip holidays that already exist for the date'
        )

    def handle(self, *args, **options):
        year = options['year']
        dry_run = options['dry_run']
        skip_existing = options['skip_existing']

        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('ADD PHILIPPINE HOLIDAYS'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(f'\nYear: {year}')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made\n'))

        added_count = 0
        skipped_count = 0
        error_count = 0

        self.stdout.write('\n' + '-' * 80)

        for holiday_data in self.FIXED_HOLIDAYS:
            try:
                holiday_date = date(year, holiday_data['month'], holiday_data['day'])
                name = holiday_data['name']
                kind = holiday_data['kind']

                # Check if holiday already exists
                existing = Holiday.objects.filter(date=holiday_date).first()

                if existing:
                    if skip_existing:
                        self.stdout.write(
                            self.style.WARNING(
                                f'\n⏭️  SKIP: {name} ({holiday_date})\n'
                                f'   Already exists: {existing.name} ({existing.get_kind_display()})'
                            )
                        )
                        skipped_count += 1
                        continue
                    else:
                        self.stdout.write(
                            self.style.ERROR(
                                f'\n❌ ERROR: {name} ({holiday_date})\n'
                                f'   Date already has holiday: {existing.name}'
                            )
                        )
                        error_count += 1
                        continue

                # Display holiday info
                kind_display = 'Regular Holiday' if kind == 'regular' else 'Special Non-Working'
                day_name = holiday_date.strftime('%A')

                self.stdout.write(f'\n📅 {name}')
                self.stdout.write(f'   Date: {holiday_date} ({day_name})')
                self.stdout.write(f'   Type: {kind_display}')

                if not dry_run:
                    Holiday.objects.create(
                        date=holiday_date,
                        name=name,
                        kind=kind,
                        is_deleted=False
                    )
                    self.stdout.write(self.style.SUCCESS('   ✅ Added'))
                    added_count += 1
                else:
                    self.stdout.write(self.style.WARNING('   Would add'))
                    added_count += 1

            except IntegrityError as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'\n❌ ERROR: {holiday_data["name"]} ({holiday_date})\n'
                        f'   {str(e)}'
                    )
                )
                error_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'\n❌ ERROR: {holiday_data["name"]}\n'
                        f'   {str(e)}'
                    )
                )
                error_count += 1

        # Summary
        self.stdout.write('\n' + '-' * 80)
        self.stdout.write(f'\n📊 Summary:')
        self.stdout.write(f'   • Year: {year}')
        self.stdout.write(f'   • Total holidays: {len(self.FIXED_HOLIDAYS)}')

        if dry_run:
            self.stdout.write(f'   • Would add: {added_count}')
        else:
            self.stdout.write(f'   • Added: {added_count}')

        if skipped_count > 0:
            self.stdout.write(f'   • Skipped: {skipped_count}')
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'   • Errors: {error_count}'))

        self.stdout.write('\n')

        if dry_run:
            self.stdout.write(self.style.WARNING('⚠️  DRY RUN - No changes made'))
            self.stdout.write('Run without --dry-run to actually add holidays\n')
        elif added_count > 0:
            self.stdout.write(self.style.SUCCESS(f'✅ Successfully added {added_count} Philippine holidays for {year}!\n'))
        elif skipped_count == len(self.FIXED_HOLIDAYS):
            self.stdout.write(self.style.SUCCESS(f'✅ All {len(self.FIXED_HOLIDAYS)} holidays already exist for {year}!\n'))

        # Additional notes
        self.stdout.write(self.style.WARNING('\n📝 Note:'))
        self.stdout.write('   • Movable holidays (e.g., Eid al-Fitr, Eid al-Adha, Chinese New Year)')
        self.stdout.write('     are not included as they vary each year.')
        self.stdout.write('   • Add them manually or update this script with the correct dates.')
        self.stdout.write('   • Special holidays declared by proclamation should be added manually.\n')
