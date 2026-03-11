"""
Management command to fix voided sales transactions that still show
payment_status as 'paid', 'partial', or 'unpaid' instead of 'voided'.

This happens because the void utility did not call update_payment_status().

Usage:
    python manage.py fix_voided_payment_status
    python manage.py fix_voided_payment_status --dry-run
"""
from django.core.management.base import BaseCommand
from sales.models import SalesTransaction


class Command(BaseCommand):
    help = "Fix voided transactions that have incorrect payment_status"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be fixed without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY RUN MODE ===\n"))

        broken = SalesTransaction.objects.filter(
            voided=True,
        ).exclude(payment_status="voided")

        count = broken.count()
        if count == 0:
            self.stdout.write("No voided transactions with wrong payment_status found.")
            return

        self.stdout.write(f"Found {count} voided transaction(s) with wrong payment_status:\n")

        for tx in broken:
            self.stdout.write(
                f"  TX #{tx.id} stall={tx.stall} client={tx.client} "
                f"status={tx.payment_status} → voided"
            )
            if not dry_run:
                tx.update_payment_status()

        if dry_run:
            self.stdout.write(self.style.WARNING(f"\nDRY RUN — {count} would be fixed"))
        else:
            self.stdout.write(self.style.SUCCESS(f"\nFixed {count} transaction(s)."))
