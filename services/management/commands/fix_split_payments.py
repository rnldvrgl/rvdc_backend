"""
Management command to fix service payments that were incorrectly split
between main and sub stall SalesTransactions.

The old code allocated payments to sub stall first (for parts), which caused:
  - Main stall SalesTransaction to stay UNPAID (no SalesPayments)
  - Payments to disappear from remittance (which filters by PAID/PARTIAL)
  - Incorrect totals on sales, client details, and remittance pages

This command:
  1. Finds all services with a related_transaction
  2. Detects if payments were split to a sub stall SalesTransaction
  3. Deletes sub stall SalesPayments and moves them to main stall
  4. Updates payment_status on both transactions
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from sales.models import SalesPayment, SalesTransaction
from services.models import Service
from inventory.models import Stall


class Command(BaseCommand):
    help = "Fix service payments incorrectly split between main and sub stall"

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

        sub_stall = Stall.objects.filter(stall_type="sub", is_system=True).first()
        if not sub_stall:
            self.stdout.write(self.style.ERROR("Sub stall not found. Nothing to fix."))
            return

        # Find all services that have payments and a related transaction
        services = (
            Service.objects.filter(
                related_transaction__isnull=False,
                payments__isnull=False,
            )
            .distinct()
            .select_related("related_transaction", "client")
            .prefetch_related("payments")
        )

        fixed_count = 0
        total_amount_moved = Decimal("0")

        for service in services:
            main_tx = service.related_transaction
            if not main_tx or main_tx.voided:
                continue

            # Find the associated sub stall transaction (same logic the old code used)
            sub_tx = SalesTransaction.objects.filter(
                stall=sub_stall,
                client=service.client,
                created_at__range=(
                    main_tx.created_at - timedelta(seconds=5),
                    main_tx.created_at + timedelta(seconds=5),
                ),
                voided=False,
            ).first()

            if not sub_tx:
                continue

            # Check if sub stall transaction has SalesPayments (the bug)
            sub_payments = list(sub_tx.payments.all())
            if not sub_payments:
                continue

            sub_total = sum(p.amount for p in sub_payments)

            self.stdout.write(
                f"\nService #{service.id} — {service.client}"
                f"\n  Main TX #{main_tx.id}: {main_tx.total_paid} paid, status={main_tx.payment_status}"
                f"\n  Sub  TX #{sub_tx.id}: {sub_total} in {len(sub_payments)} payment(s) — MISPLACED"
            )

            if dry_run:
                self.stdout.write(self.style.WARNING("  → Would move payments to main stall"))
                fixed_count += 1
                total_amount_moved += sub_total
                continue

            with transaction.atomic():
                # Move each sub stall payment to main stall
                for sp in sub_payments:
                    SalesPayment.objects.create(
                        transaction=main_tx,
                        payment_type=sp.payment_type,
                        amount=sp.amount,
                        payment_date=sp.payment_date,
                    )
                    sp.delete()

                # Refresh payment statuses on both transactions
                main_tx.update_payment_status()
                sub_tx.update_payment_status()

            main_tx.refresh_from_db()
            sub_tx.refresh_from_db()

            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✓ Moved {len(sub_payments)} payment(s) (₱{sub_total}) to main TX #{main_tx.id}"
                    f"\n    Main: status={main_tx.payment_status}, paid={main_tx.total_paid}"
                    f"\n    Sub:  status={sub_tx.payment_status}, paid={sub_tx.total_paid}"
                )
            )

            fixed_count += 1
            total_amount_moved += sub_total

        self.stdout.write("")
        if fixed_count == 0:
            self.stdout.write(
                self.style.SUCCESS("No misplaced payments found. All data is clean.")
            )
        else:
            verb = "Would fix" if dry_run else "Fixed"
            self.stdout.write(
                self.style.SUCCESS(
                    f"{verb} {fixed_count} service(s), "
                    f"₱{total_amount_moved} in payments moved to main stall."
                )
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\nRe-run without --dry-run to apply changes.")
            )
