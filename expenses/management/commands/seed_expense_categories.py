"""
Management command to seed default expense categories.

Usage:
    python manage.py seed_expense_categories

This will create common expense categories used in RVDC operations.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from expenses.models import ExpenseCategory


class Command(BaseCommand):
    help = 'Seed default expense categories for RVDC'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing categories before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing categories...')
            ExpenseCategory.objects.all().update(is_deleted=True)

        # Define default categories
        categories = [
            {
                'name': 'Utilities',
                'description': 'Electricity, water, internet, telephone',
                'monthly_budget': Decimal('10000.00'),
                'subcategories': [
                    {
                        'name': 'Electricity',
                        'description': 'Electrical power consumption',
                        'monthly_budget': Decimal('5000.00'),
                    },
                    {
                        'name': 'Water',
                        'description': 'Water consumption',
                        'monthly_budget': Decimal('2000.00'),
                    },
                    {
                        'name': 'Internet & Phone',
                        'description': 'Internet and telephone services',
                        'monthly_budget': Decimal('3000.00'),
                    },
                ]
            },
            {
                'name': 'Supplies',
                'description': 'Office and operational supplies',
                'monthly_budget': Decimal('8000.00'),
                'subcategories': [
                    {
                        'name': 'Office Supplies',
                        'description': 'Pens, paper, ink, etc.',
                        'monthly_budget': Decimal('2000.00'),
                    },
                    {
                        'name': 'Cleaning Supplies',
                        'description': 'Detergents, mops, cleaning materials',
                        'monthly_budget': Decimal('3000.00'),
                    },
                    {
                        'name': 'Tools & Equipment',
                        'description': 'Small tools and equipment',
                        'monthly_budget': Decimal('3000.00'),
                    },
                ]
            },
            {
                'name': 'Maintenance & Repairs',
                'description': 'Facility and equipment maintenance',
                'monthly_budget': Decimal('15000.00'),
                'subcategories': [
                    {
                        'name': 'Building Maintenance',
                        'description': 'Repairs to building and facilities',
                        'monthly_budget': Decimal('8000.00'),
                    },
                    {
                        'name': 'Equipment Repairs',
                        'description': 'Repairs to tools and equipment',
                        'monthly_budget': Decimal('7000.00'),
                    },
                ]
            },
            {
                'name': 'Transportation',
                'description': 'Vehicle fuel, maintenance, and transportation costs',
                'monthly_budget': Decimal('12000.00'),
                'subcategories': [
                    {
                        'name': 'Fuel',
                        'description': 'Gasoline and diesel for vehicles',
                        'monthly_budget': Decimal('8000.00'),
                    },
                    {
                        'name': 'Vehicle Maintenance',
                        'description': 'Vehicle repairs and maintenance',
                        'monthly_budget': Decimal('4000.00'),
                    },
                ]
            },
            {
                'name': 'Marketing & Advertising',
                'description': 'Marketing materials, advertising, promotions',
                'monthly_budget': Decimal('5000.00'),
            },
            {
                'name': 'Professional Fees',
                'description': 'Accounting, legal, consultancy fees',
                'monthly_budget': Decimal('3000.00'),
            },
            {
                'name': 'Permits & Licenses',
                'description': 'Business permits, licenses, regulatory fees',
                'monthly_budget': Decimal('2000.00'),
            },
            {
                'name': 'Insurance',
                'description': 'Business insurance, equipment insurance',
                'monthly_budget': Decimal('3000.00'),
            },
            {
                'name': 'Rent',
                'description': 'Office or facility rental',
                'monthly_budget': Decimal('20000.00'),
            },
            {
                'name': 'Miscellaneous',
                'description': 'Other expenses not categorized elsewhere',
                'monthly_budget': Decimal('5000.00'),
            },
        ]

        created_count = 0
        updated_count = 0

        for category_data in categories:
            subcategories_data = category_data.pop('subcategories', [])

            # Create or update parent category
            parent, created = ExpenseCategory.objects.update_or_create(
                name=category_data['name'],
                defaults={
                    'description': category_data['description'],
                    'monthly_budget': category_data['monthly_budget'],
                    'is_active': True,
                    'is_deleted': False,
                }
            )

            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Created category: {parent.name}')
                )
            else:
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(f'→ Updated category: {parent.name}')
                )

            # Create or update subcategories
            for subcat_data in subcategories_data:
                subcat, sub_created = ExpenseCategory.objects.update_or_create(
                    name=subcat_data['name'],
                    defaults={
                        'description': subcat_data['description'],
                        'monthly_budget': subcat_data['monthly_budget'],
                        'parent': parent,
                        'is_active': True,
                        'is_deleted': False,
                    }
                )

                if sub_created:
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✓ Created subcategory: {parent.name} > {subcat.name}')
                    )
                else:
                    updated_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'  → Updated subcategory: {parent.name} > {subcat.name}')
                    )

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(
            self.style.SUCCESS(
                f'\nSeeding complete!\n'
                f'Created: {created_count} categories\n'
                f'Updated: {updated_count} categories\n'
                f'Total: {created_count + updated_count} categories'
            )
        )
        self.stdout.write('=' * 60 + '\n')
