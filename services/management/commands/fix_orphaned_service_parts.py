"""
Management command to find and fix orphaned service parts (parts with reserved stock but no sale transaction).

This command identifies services where:
1. Parts were added (stock is reserved)
2. Service was completed (stock was consumed)
3. But no sale transaction was created (likely due to network error or transaction creation failure)

The command provides options to:
- List orphaned records
- Attempt to fix them by creating missing transactions
- Generate a report for manual review
"""

import logging
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
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

        # Get completed services from last N days
        cutoff_date = timezone.now() - timedelta(days=days)

        query = Service.objects.filter(
            status='completed',
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
        """Find services with parts but no sale transaction."""
        orphaned = []

        for service in queryset:
            # Check if service has parts with consumed stock
            has_parts = False
            missing_transaction = False

            # Check appliance items
            for appliance in service.appliances.all():
                for item_used in appliance.items_used.all():
                    # Check if stock was consumed (quantity was reduced)
                    if item_used.stall_stock and item_used.quantity > 0:
                        has_parts = True
                        break
                if has_parts:
                    break

            # Check service items
            if not has_parts:
                for item_used in service.service_items.all():
                    if item_used.stall_stock and item_used.quantity > 0:
                        has_parts = True
                        break

            # Check if sale transaction exists
            if has_parts:
                # For completed services, check if BOTH main and sub transactions exist (if expected)
                if not service.related_transaction and not service.related_sub_transaction:
                    missing_transaction = True
                # If parts exist but sub transaction is missing, it's orphaned
                elif not service.related_sub_transaction:
                    # Parts exist but no sub transaction was created
                    missing_transaction = True

            if has_parts and missing_transaction:
                orphaned.append({
                    'service': service,
                    'has_parts': has_parts,
                    'has_main_tx': bool(service.related_transaction),
                    'has_sub_tx': bool(service.related_sub_transaction),
                })

        return orphaned

    def _list_orphaned_services(self, orphaned_services):
        """Display list of orphaned services."""
        self.stdout.write('\n' + '=' * 100)
        self.stdout.write(
            f"{'ID':<6} {'Client':<25} {'Parts':<6} {'Main TX':<8} {'Sub TX':<8} {'Completed':<20}"
        )
        self.stdout.write('=' * 100)

        for record in orphaned_services:
            service = record['service']
            parts = self._count_parts(service)
            has_main = '✓' if record['has_main_tx'] else '✗'
            has_sub = '✓' if record['has_sub_tx'] else '✗'
            completed = service.completed_at or service.updated_at
            completed_str = completed.strftime('%Y-%m-%d %H:%M')

            self.stdout.write(
                f"{service.id:<6} {str(service.client)[:25]:<25} {parts:<6} {has_main:<8} "
                f"{has_sub:<8} {completed_str:<20}"
            )

        self.stdout.write('=' * 100)

    def _count_parts(self, service):
        """Count total parts in service."""
        count = 0
        for appliance in service.appliances.all():
            count += appliance.items_used.count()
        count += service.service_items.count()
        return count

    def _fix_orphaned_services(self, orphaned_services, dry_run):
        """Attempt to fix orphaned services by creating missing transactions."""
        fixed = 0
        failed = 0

        for record in orphaned_services:
            service = record['service']
            try:
                if dry_run:
                    self.stdout.write(
                        f"[DRY RUN] Would fix service #{service.id} ({service.client})"
                    )
                else:
                    with transaction.atomic():
                        self._create_missing_transactions(service)
                        self.stdout.write(
                            self.style.SUCCESS(f"✓ Fixed service #{service.id}")
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

    def _create_missing_transactions(self, service):
        """Create missing sale transactions for a service."""
        from services.business_logic import get_main_stall, get_sub_stall

        main_stall = get_main_stall()
        sub_stall = get_sub_stall()

        if not main_stall or not sub_stall:
            raise ValueError("System stalls not properly configured")

        # Collect all parts
        parts_to_sell = []

        # Process appliance items
        for appliance in service.appliances.all():
            for item_used in appliance.items_used.all():
                if item_used.item and item_used.quantity > 0:
                    charged_qty = item_used.quantity - item_used.free_quantity
                    if charged_qty > 0:
                        parts_to_sell.append({
                            'item': item_used.item,
                            'description': str(item_used.item),
                            'quantity': charged_qty,
                            'unit_price': item_used.discounted_price or item_used.item.retail_price,
                        })

        # Process service items
        for item_used in service.service_items.all():
            if item_used.item and item_used.quantity > 0:
                charged_qty = item_used.quantity - item_used.free_quantity
                if charged_qty > 0:
                    parts_to_sell.append({
                        'item': item_used.item,
                        'description': str(item_used.item),
                        'quantity': charged_qty,
                        'unit_price': item_used.discounted_price or item_used.item.retail_price,
                    })

        if not parts_to_sell:
            self.stdout.write(
                f"  Service #{service.id} has no chargeable parts to reconcile"
            )
            return

        # Create sub stall transaction
        sub_tx = SalesTransaction.objects.create(
            stall=sub_stall,
            client=service.client,
            sales_clerk=service.payments.first().received_by if service.payments.exists() else None,
            transaction_type=TransactionType.SERVICE,
            document_type=DocumentType.SALES_INVOICE,
            with_2307=False,
        )

        # Add all parts to transaction
        for part in parts_to_sell:
            SalesItem.objects.create(
                transaction=sub_tx,
                item=part['item'],
                description=part['description'],
                quantity=part['quantity'],
                final_price_per_unit=part['unit_price'],
            )

        # Link transaction to service
        service.related_sub_transaction = sub_tx
        service.save(update_fields=['related_sub_transaction'])

        self.stdout.write(
            f"  Created sub stall transaction #{sub_tx.id} with {len(parts_to_sell)} parts"
        )
