"""
Management command to update existing service-created sales transactions
to use the 'service' transaction type instead of the default 'sale'.

Identifies transactions linked via Service.related_transaction and
Service.related_sub_transaction foreign keys.

Usage:
    python manage.py fix_service_transaction_types
    python manage.py fix_service_transaction_types --dry-run
"""

from django.core.management.base import BaseCommand
from sales.models import SalesTransaction, TransactionType
from services.models import Service


class Command(BaseCommand):
    help = "Update service-linked sales transactions to use 'service' transaction type"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without saving",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be saved"))

        # Find all transaction IDs linked to services
        main_tx_ids = set(
            Service.objects.filter(
                related_transaction__isnull=False
            ).values_list("related_transaction_id", flat=True)
        )
        sub_tx_ids = set(
            Service.objects.filter(
                related_sub_transaction__isnull=False
            ).values_list("related_sub_transaction_id", flat=True)
        )

        all_service_tx_ids = main_tx_ids | sub_tx_ids

        if not all_service_tx_ids:
            self.stdout.write(self.style.WARNING("No service-linked transactions found."))
            return

        # Filter to only those still marked as 'sale'
        to_update = SalesTransaction.objects.filter(
            id__in=all_service_tx_ids,
            transaction_type=TransactionType.SALE,
        )

        count = to_update.count()

        if count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"All {len(all_service_tx_ids)} service-linked transactions already have correct type."
                )
            )
            return

        self.stdout.write(
            f"Found {count} service-linked transactions still marked as 'sale' "
            f"(out of {len(all_service_tx_ids)} total service transactions)."
        )

        if not dry_run:
            updated = to_update.update(transaction_type=TransactionType.SERVICE)
            self.stdout.write(
                self.style.SUCCESS(f"Updated {updated} transactions to 'service' type.")
            )
        else:
            self.stdout.write(
                self.style.WARNING(f"Would update {count} transactions to 'service' type.")
            )
