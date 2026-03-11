"""
Management command to fix service payments where a service-level discount
was not properly reflected in the Main stall SalesTransaction items.

Problem:
  When a service has a service_discount_amount or service_discount_percentage,
  the discount should only reduce the Main stall (labor) SalesTransaction items.
  However, existing services may have SalesTransaction items at full (undiscounted)
  prices, causing the payment split to be incorrect and both stalls to show as
  "partial" instead of "paid".

This command:
  1. Finds services with a service-level discount and related_transaction
  2. Applies the service discount to Main stall SalesItem.final_price_per_unit
  3. Deletes all existing SalesPayments on both main and sub stall transactions
  4. Replays all ServicePayments with correct proportional splits
  5. Updates payment_status on both transactions

Usage:
    python manage.py fix_service_discount_payments
    python manage.py fix_service_discount_payments --dry-run
    python manage.py fix_service_discount_payments --service-id 123
"""
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from sales.models import SalesPayment, SalesTransaction
from services.models import Service


class Command(BaseCommand):
    help = "Fix service payments where service-level discount was not applied to Main stall items"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be fixed without making changes",
        )
        parser.add_argument(
            "--service-id",
            type=int,
            help="Fix a specific service only",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        service_id = options.get("service_id")

        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY RUN MODE ===\n"))

        # Find services with a service-level discount and a related transaction
        qs = Service.objects.filter(
            related_transaction__isnull=False,
        ).filter(
            Q(service_discount_amount__gt=0) | Q(service_discount_percentage__gt=0)
        ).select_related(
            "related_transaction",
            "related_sub_transaction",
            "client",
        ).prefetch_related("payments")

        if service_id:
            qs = qs.filter(id=service_id)

        services = list(qs)

        if not services:
            self.stdout.write("No services with service-level discount found.")
            return

        self.stdout.write(f"Found {len(services)} service(s) with service-level discount.\n")

        fixed = 0
        skipped = 0
        errors = 0

        for service in services:
            try:
                result = self._fix_service(service, dry_run)
                if result:
                    fixed += 1
                else:
                    skipped += 1
            except Exception as e:
                errors += 1
                self.stdout.write(self.style.ERROR(
                    f"  ERROR Service #{service.id}: {e}"
                ))

        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(f"Total processed: {len(services)}")
        self.stdout.write(self.style.SUCCESS(f"Fixed: {fixed}"))
        self.stdout.write(f"Skipped (already correct): {skipped}")
        if errors:
            self.stdout.write(self.style.ERROR(f"Errors: {errors}"))
        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN — no changes were saved"))

    def _fix_service(self, service, dry_run):
        main_tx = service.related_transaction
        sub_tx = service.related_sub_transaction

        if main_tx.voided:
            return False

        # Calculate service discount amount
        main_subtotal = main_tx.subtotal or Decimal("0")
        sub_subtotal = (sub_tx.subtotal or Decimal("0")) if sub_tx else Decimal("0")
        combined = main_subtotal + sub_subtotal

        service_discount = Decimal("0")
        if service.service_discount_percentage and service.service_discount_percentage > 0:
            service_discount = (
                combined * service.service_discount_percentage / Decimal("100")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        elif service.service_discount_amount and service.service_discount_amount > 0:
            service_discount = service.service_discount_amount

        if service_discount <= 0:
            return False

        # Check if discount is already applied by comparing computed_total
        # to the expected discounted amount
        expected_main_total = max(main_subtotal - service_discount, Decimal("0"))
        current_main_total = main_tx.computed_total or Decimal("0")

        # Allow a small tolerance for rounding
        if abs(current_main_total - expected_main_total) < Decimal("0.02"):
            self.stdout.write(
                f"  Service #{service.id} ({service.client}) — "
                f"discount already applied (Main={current_main_total}). Skipping."
            )
            return False

        self.stdout.write(
            f"\nService #{service.id} — {service.client}"
            f"\n  Discount: {service_discount}"
            f"\n  Main TX #{main_tx.id}: subtotal={main_subtotal}, "
            f"computed_total={current_main_total} → expected {expected_main_total}"
        )
        if sub_tx:
            self.stdout.write(
                f"  Sub  TX #{sub_tx.id}: subtotal={sub_subtotal}, "
                f"computed_total={sub_tx.computed_total}"
            )

        if dry_run:
            # Show what would happen
            new_main_total = expected_main_total
            new_sub_total = sub_subtotal
            new_combined = new_main_total + new_sub_total
            self.stdout.write(
                f"  → Would set Main computed_total={new_main_total}, "
                f"Sub={new_sub_total}, Combined={new_combined}"
            )
            total_paid = sum(p.amount for p in service.payments.all())
            self.stdout.write(f"  → Would re-split {total_paid} in payments")
            return True

        with transaction.atomic():
            # Step 1: Apply discount to main stall items
            self._apply_discount_to_items(main_tx, service_discount, main_subtotal)

            # Step 2: Delete all existing SalesPayments on both transactions
            main_tx.payments.all().delete()
            if sub_tx:
                sub_tx.payments.all().delete()

            # Step 3: Replay ServicePayments with correct splits
            new_main_total = main_tx.computed_total or Decimal("0")
            new_sub_total = (sub_tx.computed_total or Decimal("0")) if sub_tx else Decimal("0")
            new_combined = new_main_total + new_sub_total

            self.stdout.write(
                f"  New split basis: Main={new_main_total}, "
                f"Sub={new_sub_total}, Combined={new_combined}"
            )

            for sp in service.payments.order_by("payment_date"):
                m_share, s_share = self._split_payment(
                    sp.amount, new_main_total, new_sub_total, new_combined
                )
                SalesPayment.objects.create(
                    transaction=main_tx,
                    payment_type=sp.payment_type,
                    amount=m_share,
                    payment_date=sp.payment_date,
                )
                if s_share > 0 and sub_tx:
                    SalesPayment.objects.create(
                        transaction=sub_tx,
                        payment_type=sp.payment_type,
                        amount=s_share,
                        payment_date=sp.payment_date,
                    )
                self.stdout.write(
                    f"  Payment {sp.amount} → Main={m_share}, Sub={s_share}"
                )

            # Step 4: Update payment status
            main_tx.update_payment_status()
            if sub_tx:
                sub_tx.update_payment_status()

            self.stdout.write(self.style.SUCCESS(
                f"  ✓ Fixed! Main status={main_tx.payment_status}, "
                f"Sub status={sub_tx.payment_status if sub_tx else 'N/A'}"
            ))

        return True

    @staticmethod
    def _apply_discount_to_items(sales_transaction, service_discount, main_subtotal):
        """Apply service discount proportionally to main stall items."""
        if main_subtotal <= 0:
            return

        items = list(sales_transaction.items.all())
        remaining_discount = service_discount

        for i, item in enumerate(items):
            if i == len(items) - 1:
                item_discount = remaining_discount
            else:
                item_discount = (
                    service_discount * item.line_total / main_subtotal
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            per_unit_discount = (item_discount / item.quantity).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            item.final_price_per_unit = max(
                Decimal("0"),
                item.final_price_per_unit - per_unit_discount,
            )
            item.save(update_fields=["final_price_per_unit"])
            remaining_discount -= item_discount

    @staticmethod
    def _split_payment(amount, main_total, sub_total, combined_total):
        """Split a payment amount proportionally between main and sub stall."""
        if combined_total <= 0 or sub_total <= 0:
            return amount, Decimal("0")
        sub_share = (amount * sub_total / combined_total).quantize(Decimal("0.01"))
        main_share = amount - sub_share
        return main_share, sub_share
