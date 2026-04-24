"""
Management command to fix installation unit revenue split retroactively.
Updates all installation unit sales from a given date to apply the new split logic.

Usage:
    python manage.py fix_installation_unit_revenue_split --date 2026-04-01
    python manage.py fix_installation_unit_revenue_split --date 2026-04-01 --dry-run
"""
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone
from decimal import Decimal

from services.models import Service
from services.business_logic import ServicePaymentManager
from utils.enums import ServiceStatus


class Command(BaseCommand):
    help = (
        "Fix installation unit revenue split retroactively for services from a given date. "
        "Regenerates sales transactions to apply the new configurable split logic."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            required=True,
            help='Date from which to fix services (format: YYYY-MM-DD). All services on/after this date will be processed.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--service-id',
            type=int,
            help='Fix only a specific service ID (for testing)',
        )

    def handle(self, *args, **options):
        date_str = options.get('date')
        dry_run = options.get('dry_run', False)
        service_id = options.get('service_id')

        # Parse the date
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d')
            # Convert to timezone-aware datetime at start of day
            target_date = timezone.make_aware(target_date)
        except ValueError:
            raise CommandError(f"Invalid date format: {date_str}. Use YYYY-MM-DD")

        # Build query for affected services
        query = Q(
            status=ServiceStatus.COMPLETED,
            created_at__gte=target_date,
        )

        # Add filter for services that have installation units
        query &= Q(aircon_installations__isnull=False)

        if service_id:
            query &= Q(id=service_id)

        services_to_fix = Service.objects.filter(query).distinct().order_by('id')
        count = services_to_fix.count()

        if count == 0:
            self.stdout.write(
                self.style.WARNING(
                    f"No completed installation services found from {date_str} onwards"
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(f"Found {count} services to process from {date_str} onwards")
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("Running in DRY-RUN mode (no changes will be saved)"))

        fixed_count = 0
        error_count = 0

        for idx, service in enumerate(services_to_fix, 1):
            try:
                self.stdout.write(
                    f"\n[{idx}/{count}] Processing Service #{service.id} "
                    f"({service.client.name if service.client else 'Unknown'}) "
                    f"- Created: {service.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
                )

                # Check for installation units
                units = service.aircon_installations.all()
                if not units.exists():
                    self.stdout.write(
                        self.style.WARNING(f"  ⊘ No aircon units found for this service")
                    )
                    continue

                self.stdout.write(f"  ℹ Found {units.count()} installation unit(s)")

                # Show current state before fix
                if service.related_transaction:
                    main_items = service.related_transaction.transaction_items.filter(
                        item_type='service',
                        appliance__isnull=False,
                    )
                    main_unit_revenue = sum(
                        item.amount for item in main_items
                    )
                    self.stdout.write(f"  ℹ Current Main stall unit revenue: ₱{main_unit_revenue}")

                if service.related_sub_transaction:
                    sub_items = service.related_sub_transaction.transaction_items.filter(
                        item_type='service',
                        appliance__isnull=False,
                    )
                    sub_unit_revenue = sum(
                        item.amount for item in sub_items
                    )
                    self.stdout.write(f"  ℹ Current Sub stall unit revenue: ₱{sub_unit_revenue}")

                # Regenerate transactions with new split logic
                if not dry_run:
                    new_transaction = ServicePaymentManager.recreate_sales_transaction(service)
                    if new_transaction:
                        # Show new state after fix
                        main_items = new_transaction.transaction_items.filter(
                            item_type='service',
                            appliance__isnull=False,
                        )
                        main_unit_revenue = sum(
                            item.amount for item in main_items
                        )
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  ✓ Regenerated Main stall transaction #{new_transaction.id} "
                                f"with unit revenue: ₱{main_unit_revenue}"
                            )
                        )

                        if service.related_sub_transaction:
                            sub_items = service.related_sub_transaction.transaction_items.filter(
                                item_type='service',
                                appliance__isnull=False,
                            )
                            sub_unit_revenue = sum(
                                item.amount for item in sub_items
                            )
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  ✓ Sub stall transaction #{service.related_sub_transaction.id} "
                                    f"with unit revenue: ₱{sub_unit_revenue}"
                                )
                            )
                        fixed_count += 1
                    else:
                        self.stdout.write(
                            self.style.ERROR(f"  ✗ Failed to regenerate transaction")
                        )
                        error_count += 1
                else:
                    # Dry-run: just report what would happen
                    self.stdout.write(
                        self.style.WARNING(
                            f"  ⊲ [DRY-RUN] Would regenerate sales transactions "
                            f"(Main: #{service.related_transaction.id if service.related_transaction else 'N/A'}, "
                            f"Sub: #{service.related_sub_transaction.id if service.related_sub_transaction else 'N/A'})"
                        )
                    )
                    fixed_count += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  ✗ Error processing Service #{service.id}: {str(e)}")
                )
                error_count += 1

        # Summary
        self.stdout.write("\n" + "=" * 70)
        if dry_run:
            self.stdout.write(self.style.WARNING("[DRY-RUN SUMMARY]"))
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully processed: {fixed_count}/{count} services"
            )
        )
        if error_count > 0:
            self.stdout.write(
                self.style.WARNING(f"Errors encountered: {error_count}/{count} services")
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"\nTo apply these changes, run without --dry-run:\n"
                    f"  python manage.py fix_installation_unit_revenue_split --date {date_str}"
                )
            )
