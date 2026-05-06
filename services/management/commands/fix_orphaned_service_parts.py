"""
Management command to find and fix orphaned service parts (parts with reserved/consumed stock but missing from sales transactions).

This command identifies services where:
1. Parts were added (ApplianceItemUsed or ServiceItemUsed records exist)
2. But these parts are missing or incomplete in sales transactions
3. This can happen at ANY service status due to network errors during transaction creation

The command provides options to:
- List orphaned records
- Attempt to fix them by creating/updating transactions
- Generate a report for manual review
"""

import logging
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum, F, Case, When, DecimalField
from django.utils import timezone
from services.models import Service, ApplianceItemUsed, ServiceItemUsed
from sales.models import SalesTransaction, SalesItem, TransactionType, DocumentType
from inventory.models import Stall
from datetime import timedelta

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Find and fix orphaned service parts with reserved/consumed stock but no sale transaction'

    def add_arguments(self, parser):
        parser.add_argument(
            '--list',
            action='store_true',
            help='List orphaned services',
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Attempt to fix orphaned services by creating missing transactions',
        )
        parser.add_argument(
            '--service-id',
            type=int,
            help='Limit to specific service ID',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Only check services from the last N days (default: 30)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        """Main command handler."""
        list_only = options['list']
        fix = options['fix']
        service_id = options['service_id']
        days = options['days']
        dry_run = options['dry_run']

        if not list_only and not fix:
            self.stdout.write(
                self.style.WARNING('Please specify --list or --fix')
            )
            return

        # Get services from last N days (ANY status, not just completed)
        cutoff_date = timezone.now() - timedelta(days=days)

        query = Service.objects.filter(
            updated_at__gte=cutoff_date,
            is_deleted=False,
        ).select_related(
            'client',
            'related_transaction',
            'related_sub_transaction',
        ).prefetch_related(
            'appliances__items_used__item',
            'appliances__items_used__stall_stock',
            'service_items__item',
            'service_items__stall_stock',
            'related_sub_transaction__items',
            'related_transaction__items',
        )

        if service_id:
            query = query.filter(id=service_id)

        orphaned_services = self._find_orphaned_services(query)

        if not orphaned_services:
            self.stdout.write(self.style.SUCCESS('✓ No orphaned services found'))
            return

        self.stdout.write(
            self.style.WARNING(f'\nFound {len(orphaned_services)} orphaned services:')
        )

        if list_only:
            self._list_orphaned_services(orphaned_services)
        elif fix:
            self._fix_orphaned_services(orphaned_services, dry_run)

    def _find_orphaned_services(self, queryset):
        """Find services where parts exist but are missing from or incomplete in sales transactions."""
        orphaned = []

        for service in queryset:
            # Calculate total parts value from all ApplianceItemUsed and ServiceItemUsed
            total_parts_value = Decimal('0.00')
            parts_records = []

            # Collect appliance items
            for appliance in service.appliances.all():
                for item_used in appliance.items_used.all():
                    if not item_used.is_free:
                        charged_qty = item_used.quantity - item_used.free_quantity
                        if charged_qty > 0:
                            line_total = charged_qty * (item_used.discounted_price or Decimal('0.00'))
                            total_parts_value += line_total
                            parts_records.append({
                                'item_id': item_used.item_id,
                                'qty': charged_qty,
                                'price': item_used.discounted_price or Decimal('0.00'),
                                'total': line_total,
                            })

            # Collect service items
            for item_used in service.service_items.all():
                if not item_used.is_free:
                    charged_qty = item_used.quantity - item_used.free_quantity
                    if charged_qty > 0:
                        line_total = charged_qty * (item_used.discounted_price or Decimal('0.00'))
                        total_parts_value += line_total
                        parts_records.append({
                            'item_id': item_used.item_id,
                            'qty': charged_qty,
                            'price': item_used.discounted_price or Decimal('0.00'),
                            'total': line_total,
                        })

            # If no parts in service, skip
            if not parts_records:
                continue

            # Calculate total parts value from sales transactions
            sales_parts_value = Decimal('0.00')

            # Check sub stall transaction (parts go here)
            if service.related_sub_transaction:
                for sales_item in service.related_sub_transaction.items.all():
                    # Only count items that are actual inventory items (not labor/units/extra charges)
                    if sales_item.item_id:
                        line_total = sales_item.quantity * (sales_item.final_price_per_unit or Decimal('0.00'))
                        sales_parts_value += line_total

            # Compare: if parts value in sales is less than total parts added, it's orphaned
            if sales_parts_value < total_parts_value:
                missing_value = total_parts_value - sales_parts_value
                orphaned.append({
                    'service': service,
                    'total_parts_value': total_parts_value,
                    'sales_parts_value': sales_parts_value,
                    'missing_value': missing_value,
                    'missing_count': len(parts_records),
                    'has_sub_tx': bool(service.related_sub_transaction),
                    'parts_records': parts_records,
                })

        return orphaned

    def _list_orphaned_services(self, orphaned_services):
        """Display list of orphaned services."""
        self.stdout.write('\n' + '=' * 120)
        self.stdout.write(
            f"{'ID':<6} {'Status':<12} {'Client':<25} {'Parts':<7} {'Expected':<12} {'In Sales':<12} {'Missing':<12}"
        )
        self.stdout.write('=' * 120)

        for record in orphaned_services:
            service = record['service']
            total_parts = record['total_parts_value']
            sales_parts = record['sales_parts_value']
            missing = record['missing_value']
            count = record['missing_count']

            self.stdout.write(
                f"{service.id:<6} {service.status:<12} {str(service.client)[:25]:<25} {count:<7} "
                f"₱{total_parts:<11.2f} ₱{sales_parts:<11.2f} ₱{missing:<11.2f}"
            )

        self.stdout.write('=' * 120)

    def _fix_orphaned_services(self, orphaned_services, dry_run):
        """Attempt to fix orphaned services by creating/updating missing transactions."""
        fixed = 0
        failed = 0

        for record in orphaned_services:
            service = record['service']
            try:
                if dry_run:
                    self.stdout.write(
                        f"[DRY RUN] Would fix service #{service.id} ({service.client}): "
                        f"Missing ₱{record['missing_value']:.2f} ({record['missing_count']} parts)"
                    )
                else:
                    with transaction.atomic():
                        self._create_missing_transactions(service, record)
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✓ Fixed service #{service.id}: "
                                f"Reconciled ₱{record['missing_value']:.2f} ({record['missing_count']} parts)"
                            )
                        )
                fixed += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"✗ Failed to fix service #{service.id}: {str(e)}")
                )
                logger.exception(f"Failed to fix service {service.id}", exc_info=e)
                failed += 1

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS(f'Fixed: {fixed}'))
        if failed > 0:
            self.stdout.write(self.style.ERROR(f'Failed: {failed}'))
        self.stdout.write('=' * 60)

    def _create_missing_transactions(self, service, record):
        """Create or update transactions to reconcile missing parts."""
        from services.business_logic import get_main_stall, get_sub_stall

        main_stall = get_main_stall()
        sub_stall = get_sub_stall()

        if not main_stall or not sub_stall:
            raise ValueError("System stalls not properly configured")

        parts_to_add = record['parts_records']

        # Get existing sub transaction or create new one
        sub_tx = service.related_sub_transaction

        if not sub_tx:
            # Create new sub stall transaction
            sub_tx = SalesTransaction.objects.create(
                stall=sub_stall,
                client=service.client,
                sales_clerk=service.payments.first().received_by if service.payments.exists() else None,
                transaction_type=TransactionType.SERVICE,
                document_type=DocumentType.SALES_INVOICE,
                with_2307=False,
            )
            service.related_sub_transaction = sub_tx
            service.save(update_fields=['related_sub_transaction'])
            self.stdout.write(f"  Created new sub stall transaction #{sub_tx.id}")
        else:
            self.stdout.write(f"  Using existing sub stall transaction #{sub_tx.id}")

        # Get item IDs already in the transaction
        existing_item_ids = set(
            sub_tx.items.filter(item_id__isnull=False).values_list('item_id', flat=True)
        )

        # Add missing parts to transaction
        added_count = 0
        for part in parts_to_add:
            # Only add if not already in transaction
            if part['item_id'] and part['item_id'] not in existing_item_ids:
                from inventory.models import Item
                try:
                    item = Item.objects.get(id=part['item_id'])
                    SalesItem.objects.create(
                        transaction=sub_tx,
                        item=item,
                        description=item.name,
                        quantity=part['qty'],
                        final_price_per_unit=part['price'],
                    )
                    added_count += 1
                    existing_item_ids.add(part['item_id'])
                except Item.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(f"  Warning: Item #{part['item_id']} not found")
                    )

        self.stdout.write(f"  Added {added_count} missing parts to transaction")
