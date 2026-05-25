from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction

from inventory.models import Item, ProductCategory


class Command(BaseCommand):
    help = 'Seed inventory items with sample categories and pricing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=100,
            help='Number of items to seed (default: 100)',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Soft-delete existing items before seeding',
        )

    def handle(self, *args, **options):
        count = max(0, options['count'])
        if count == 0:
            self.stdout.write(self.style.WARNING('No items to seed because count is 0.'))
            return

        if options['clear']:
            self.stdout.write('Soft-deleting existing inventory items...')
            Item.all_objects.update(is_deleted=True)

        categories_data = [
            {
                'name': 'Aircon Parts',
                'description': 'Replacement parts, filters, and accessories for air conditioners.',
            },
            {
                'name': 'Electrical Supplies',
                'description': 'Wires, switches, sockets, and electrical accessories.',
            },
            {
                'name': 'Plumbing',
                'description': 'Pipes, fittings, valves, and plumbing consumables.',
            },
            {
                'name': 'Hardware',
                'description': 'General hardware, brackets, hinges, and fasteners.',
            },
            {
                'name': 'Cleaning Materials',
                'description': 'Detergents, solvents, cloths, and cleaning supplies.',
            },
            {
                'name': 'Fasteners',
                'description': 'Screws, bolts, nuts, anchors, and related fasteners.',
            },
            {
                'name': 'Tools & Equipment',
                'description': 'Hand tools, power tools, and equipment accessories.',
            },
            {
                'name': 'Packaging',
                'description': 'Boxes, tape, bubble wrap, and wrapping supplies.',
            },
            {
                'name': 'Lubricants',
                'description': 'Oils, greases, and lubricants for maintenance work.',
            },
            {
                'name': 'Safety Gear',
                'description': 'Gloves, goggles, masks, and protective equipment.',
            },
        ]

        categories = []
        for category_data in categories_data:
            category, created = ProductCategory.objects.update_or_create(
                name=category_data['name'],
                defaults={
                    'description': category_data['description'],
                    'is_deleted': False,
                },
            )
            categories.append(category)
            action = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(f'{action} category: {category.name}'))

        created = 0
        updated = 0

        with transaction.atomic():
            for index in range(count):
                category = categories[index % len(categories)]
                prefix = ''.join(ch for ch in category.name if ch.isalpha())[:3].upper() or 'ITM'
                sku = f'{prefix}-{index + 1:03d}'
                name = f'{category.name} Item {index + 1:03d}'
                retail_price = Decimal('100.00') + Decimal(index % 20) * Decimal('12.50')
                wholesale_price = (retail_price * Decimal('0.75')).quantize(Decimal('0.01'))
                technician_price = (retail_price * Decimal('0.60')).quantize(Decimal('0.01'))
                cost_price = (retail_price * Decimal('0.45')).quantize(Decimal('0.01'))
                unit_of_measure = ['pcs', 'ft', 'kg', 'roll', 'box'][index % 5]
                description = (
                    f'Sample inventory item for {category.name}. '
                    f'Ideal for store display and test data.'
                )

                item, item_created = Item.objects.update_or_create(
                    sku=sku,
                    defaults={
                        'name': name,
                        'category': category,
                        'description': description,
                        'unit_of_measure': unit_of_measure,
                        'retail_price': retail_price,
                        'wholesale_price': wholesale_price,
                        'technician_price': technician_price,
                        'cost_price': cost_price,
                        'is_tracked': True,
                        'is_deleted': False,
                    },
                )

                if item_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write('=' * 60)
        self.stdout.write(self.style.SUCCESS(f'Seeding complete: {created} created, {updated} updated.'))
        self.stdout.write(self.style.SUCCESS(f'Total inventory items seeded: {count}'))
        self.stdout.write('=' * 60)
