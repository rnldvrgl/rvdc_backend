"""
Management command to fix sub stall payment splits.

Handles TWO cases:
  1. related_sub_transaction is NULL → find and link, then fix payments
  2. related_sub_transaction IS set but sub TX has no payments while
     main TX is overpaid → rebalance payments between main and sub

Uses ServicePayments as the source of truth.  Deletes all existing
SalesPayments on both stalls and rebuilds using waterfall allocation
(fill main stall first, then sub stall, overpayment → main as change).

Run with --dry-run first to preview changes:
    python manage.py fix_sub_stall_links --dry-run

Then apply:
    python manage.py fix_sub_stall_links
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from inventory.models import Stall
from sales.models import SalesPayment, SalesTransaction
from services.models import Service


def get_main_stall():
    return Stall.objects.get(name__icontains="main")


def get_sub_stall():
    return Stall.objects.get(name__icontains="sub")


class Command(BaseCommand):
    help = "Fix sub stall payment splits using waterfall allocation from ServicePayments."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying them.")

    def _rebuild_sales_payments(self, main_tx, sub_tx, svc, dry_run):
        """
        Delete all SalesPayments on both TXs and rebuild from ServicePayments
        using waterfall allocation (main first, then sub).
        Returns number of ServicePayments processed.
        """
        main_total = main_tx.computed_total or Decimal("0")
        sub_total = sub_tx.computed_total or Decimal("0")

        if main_total + sub_total <= 0:
            return 0

        service_payments = list(svc.payments.all().order_by("payment_date"))
        if not service_payments:
            return 0

        self.stdout.write(
            f"  Rebuilding from {len(service_payments)} ServicePayment(s) → "
            f"main (₱{main_total}) + sub (₱{sub_total})"
        )

        if not dry_run:
            with transaction.atomic():
                del_main = main_tx.payments.all().delete()[0]
                del_sub = sub_tx.payments.all().delete()[0]
                self.stdout.write(f"    Deleted {del_main} main + {del_sub} sub SalesPayment(s)")

        main_filled = Decimal("0")
        sub_filled = Decimal("0")
        processed = 0

        for sp in service_payments:
            amount = sp.amount

            # Waterfall: fill sub first, then main, overpayment → main
            sub_remaining = max(Decimal("0"), sub_total - sub_filled)
            s_share = min(amount, sub_remaining)
            main_remaining = max(Decimal("0"), main_total - main_filled)
            m_share = min(amount - s_share, main_remaining)
            m_share += amount - m_share - s_share  # overpayment to main

            self.stdout.write(
                f"    ServicePayment #{sp.id} ₱{sp.amount} {sp.payment_type}"
                f" → main ₱{m_share}, sub ₱{s_share}"
            )

            if not dry_run:
                with transaction.atomic():
                    if m_share > 0:
                        SalesPayment.objects.create(
                            transaction=main_tx,
                            payment_type=sp.payment_type,
                            amount=m_share,
                            payment_date=sp.payment_date,
                        )
                    if s_share > 0:
                        SalesPayment.objects.create(
                            transaction=sub_tx,
                            payment_type=sp.payment_type,
                            amount=s_share,
                            payment_date=sp.payment_date,
                        )

            main_filled += m_share
            sub_filled += s_share
            processed += 1

        return processed

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        sub_stall = get_sub_stall()

        linked = 0
        payments_fixed = 0

        # ── Phase 1: Services with missing sub TX link ──
        self.stdout.write(self.style.MIGRATE_HEADING("\n── Phase 1: Link missing sub transactions ──"))

        unlinked_services = Service.objects.filter(
            related_transaction__isnull=False,
            related_sub_transaction__isnull=True,
            is_deleted=False,
        ).select_related("related_transaction", "client")

        for svc in unlinked_services:
            main_tx = svc.related_transaction
            if not main_tx or main_tx.voided:
                continue

            # Find sub stall transaction by time proximity (60s window)
            sub_tx = SalesTransaction.objects.filter(
                stall=sub_stall,
                client=svc.client,
                voided=False,
                created_at__range=(
                    main_tx.created_at - timedelta(seconds=60),
                    main_tx.created_at + timedelta(seconds=60),
                ),
            ).exclude(id=main_tx.id).first()

            # Broader fallback: same-day lookup
            if not sub_tx:
                sub_tx = SalesTransaction.objects.filter(
                    stall=sub_stall,
                    client=svc.client,
                    voided=False,
                    created_at__date=main_tx.created_at.date(),
                ).exclude(id=main_tx.id).first()

            if not sub_tx:
                continue

            self.stdout.write(f"  Service #{svc.id}: linking sub tx #{sub_tx.id} (₱{sub_tx.computed_total})")
            linked += 1

            if not dry_run:
                svc.related_sub_transaction = sub_tx
                svc.save(update_fields=["related_sub_transaction"])

            # Rebuild payment split from ServicePayments
            if not sub_tx.payments.exists():
                payments_fixed += self._rebuild_sales_payments(main_tx, sub_tx, svc, dry_run)

        self.stdout.write(f"  Found {linked} unlinked sub transactions.")

        # ── Phase 2: Services with linked sub TX but missing sub payments ──
        self.stdout.write(self.style.MIGRATE_HEADING("\n── Phase 2: Fix linked but unpaid sub transactions ──"))

        linked_services = Service.objects.filter(
            related_transaction__isnull=False,
            related_sub_transaction__isnull=False,
            is_deleted=False,
        ).select_related("related_transaction", "related_sub_transaction", "client")

        phase2_fixed = 0
        for svc in linked_services:
            main_tx = svc.related_transaction
            sub_tx = svc.related_sub_transaction

            if not main_tx or main_tx.voided or not sub_tx or sub_tx.voided:
                continue

            sub_total = sub_tx.computed_total or Decimal("0")
            if sub_total <= 0:
                continue

            # Skip if sub TX already has payments
            if sub_tx.payments.exists():
                continue

            # Skip if main TX has no payments (nothing to rebalance)
            if not main_tx.payments.exists():
                continue

            main_total = main_tx.computed_total or Decimal("0")
            main_paid = main_tx.total_paid or Decimal("0")

            self.stdout.write(
                f"  Service #{svc.id} ({svc.client}): "
                f"main #{main_tx.id} (₱{main_total}, paid ₱{main_paid}), "
                f"sub #{sub_tx.id} (₱{sub_total}, paid ₱0)"
            )

            count = self._rebuild_sales_payments(main_tx, sub_tx, svc, dry_run)
            phase2_fixed += count
            payments_fixed += count

        self.stdout.write(f"  Found {phase2_fixed} payment(s) to rebalance.")

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"\n{prefix}Done. "
            f"Linked {linked} sub transactions, "
            f"fixed {payments_fixed} payment split(s)."
        ))
