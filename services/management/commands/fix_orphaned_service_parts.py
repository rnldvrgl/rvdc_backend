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
        """Find services where parts exist but are missing from sales transactions."""
        orphaned = []

        for service in queryset:
            missing_parts = []

            # Check appliance items
            for appliance in service.appliances.all():
                for item_used in appliance.items_used.all():
                    # Skip free items
                    if item_used.is_free:
                        continue
                    
                    # Calculate chargeable quantity
                    charged_qty = item_used.quantity - item_used.free_quantity
                    if charged_qty <= 0:
                        continue
                    
                    # Check if this item is in the sales transaction
                    if item_used.item_id and service.related_sub_transaction:
                        # Look for matching item in sales transaction
                        sales_item_exists = service.related_sub_transaction.items.filter(
                            item_id=item_used.item_id
                        ).exists()
                        
                        if not sales_item_exists:
                            missing_parts.append({
                                'item_id': item_used.item_id,
                                'item_name': item_used.item.name if item_used.item else 'Unknown',
                                'quantity': charged_qty,
                                'price': item_used.discounted_price or Decimal('0.00'),
                                'source': f'Appliance: {appliance}',
                            })
                    elif item_used.item_id and not service.related_sub_transaction:
                        # No sales transaction at all
                        missing_parts.append({
                            'item_id': item_used.item_id,
                            'item_name': item_used.item.name if item_used.item else 'Unknown',
                            'quantity': charged_qty,
                            'price': item_used.discounted_price or Decimal('0.00'),
                            'source': f'Appliance: {appliance}',
                        })

            # Check service items
            for item_used in service.service_items.all():
                # Skip free items
                if item_used.is_free:
                    continue
                
                # Calculate chargeable quantity
                charged_qty = item_used.quantity - item_used.free_quantity
                if charged_qty <= 0:
                    continue
                
                # Check if this item is in the sales transaction
                if item_used.item_id and service.related_sub_transaction:
                    # Look for matching item in sales transaction
                    sales_item_exists = service.related_sub_transaction.items.filter(
                        item_id=item_used.item_id
                    ).exists()
                    
                    if not sales_item_exists:
                        missing_parts.append({
                            'item_id': item_used.item_id,
                            'item_name': item_used.item.name if item_used.item else 'Unknown',
                            'quantity': charged_qty,
                            'price': item_used.discounted_price or Decimal('0.00'),
                            'source': 'Service Level',
                        })
                elif item_used.item_id and not service.related_sub_transaction:
                    # No sales transaction at all
                    missing_parts.append({
                        'item_id': item_used.item_id,
                        'item_name': item_used.item.name if item_used.item else 'Unknown',
                        'quantity': charged_qty,
                        'price': item_used.discounted_price or Decimal('0.00'),
                        'source': 'Service Level',
                    })

            # If there are missing parts, add to orphaned list
            if missing_parts:
                total_missing_value = sum(
                    Decimal(str(p['quantity'])) * Decimal(str(p['price'])) 
                    for p in missing_parts
                )
                orphaned.append({
                    'service': service,
                    'missing_parts': missing_parts,
                    'missing_count': len(missing_parts),
                    'missing_value': total_missing_value,
                    'has_sub_tx': bool(service.related_sub_transaction),

        return orphaned

    def _list_orphaned_services(self, orphaned_services):
        """Display list of orphaned services with details."""
        self.stdout.write('\n' + '=' * 120)
        self.stdout.write(
            f"{'ID':<6} {'Status':<12} {'Client':<25} {'Missing Parts':<20} {'Missing Value':<15}"
        )
        self.stdout.write('=' * 120)

        for record in orphaned_services:
            service = record['service']
            count = record['missing_count']
            missing_value = record['missing_value']
            
            self.stdout.write(
                f"{service.id:<6} {service.status:<12} {str(service.client)[:25]:<25} "
                f"{count} items{'':<7} ₱{missing_value:<13.2f}"
            )
            
            # Show details of missing parts
            for part in record['missing_parts']:
                line_total = Decimal(str(part['quantity'])) * Decimal(str(part['price']))
                self.stdout.write(
                    f"       └─ {part['item_name']:<40} x{part['quantity']:<5} @ ₱{part['price']:<8.2f} = ₱{line_total:<8.2f}"
                )
        self.stdout.write('=' * 120)

    def _fix_orphaned_services(self, orphaned_services, dry_run):
        """Attempt to fix orphaned services by adding missing parts to transactions."""
        fixed = 0
        failed = 0

        for record in orphaned_services:
            service = record['service']
            missing_parts = record['missing_parts']
            
            try:
                if dry_run:
                    self.stdout.write(
                        f"[DRY RUN] Would fix service #{service.id} ({service.client}): "
                        f"Add {record['missing_count']} missing parts (₱{record['missing_value']:.2f})"
                    )
                else:
                    with transaction.atomic():
                        self._add_missing_parts_to_transaction(service, missing_parts)
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✓ Fixed service #{service.id}: "
                                f"Added {record['missing_count']} missing parts (₱{record['missing_value']:.2f})"
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

def _add_missing_parts_to_transaction(self, service, missing_parts):
        """Add missing parts to the service's sales transaction."""
        from services.business_logic import get_sub_stall
        from inventory.models import Item

        sub_stall = get_sub_stall()
        if not sub_stall:
            raise ValueError("Sub stall not properly configured")

        # Get or create sub stall transaction
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
            self.stdout.write(f"  ✓ Created new sub stall transaction #{sub_tx.id}")
        else:
            self.stdout.write(f"  ✓ Using existing sub stall transaction #{sub_tx.id}")

        # Add missing parts to transaction
        added_count = 0
        for part in missing_parts:
            try:
                item = Item.objects.get(id=part['item_id'])
                
                # Check if this item already exists in the transaction
                existing = sub_tx.items.filter(item_id=part['item_id']).first()
                
                if existing:
                    self.stdout.write(
                        f"  ℹ️  Item {part['item_name']} already in transaction, skipping"
                    )
                else:
                    SalesItem.objects.create(
                        transaction=sub_tx,
                        item=item,
                        description=item.name,
                        quantity=part['quantity'],
                        final_price_per_unit=part['price'],
                    )
                    added_count += 1
                    self.stdout.write(
                        f"  ✓ Added {part['item_name']} x{part['quantity']} @ ₱{part['price']}"
                    )
            except Item.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"  ⚠️  Item #{part['item_id']} not found in inventory")
                )
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"  ⚠️  Error adding {part['item_name']}: {str(e)}")
                )

        self.stdout.write(f"  ✓ Added {added_count} parts to transaction")
