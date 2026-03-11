"""
Management command to fix sub stall payment splits.

Handles TWO cases:
  1. related_sub_transaction is NULL → find and link, then fix payments
  2. related_sub_transaction IS set but sub TX has no payments while
     main TX is overpaid → rebalance payments between main and sub

Run with --dry-run first to preview changes:
    python manage.py fix_sub_stall_links --dry-run

Then apply:
    python manage.py fix_sub_stall_links
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from inventory.models import Stall
from sales.models import SalesPayment, SalesTransaction, PaymentStatus
from services.models import Service


def get_main_stall():
    return Stall.objects.get(name__icontains="main")


def get_sub_stall():
    return Stall.objects.get(name__icontains="sub")


class Command(BaseCommand):
    help = "Fix sub stall payment splits: link missing sub transactions and rebalance overpaid main stalls."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying them.")

    def _fix_payment_split(self, main_tx, sub_tx, svc, dry_run):
        """Rebalance payments from main TX to sub TX. Returns number of payments fixed."""
        main_total = main_tx.computed_total or Decimal("0")
        sub_total = sub_tx.computed_total or Decimal("0")
        combined = main_total + sub_total
        if combined <= 0 or sub_total <= 0:
            return 0

        main_payments = list(main_tx.payments.all().order_by("payment_date"))
        if not main_payments:
            return 0

        self.stdout.write(
            f"  Splitting {len(main_payments)} payment(s) between "
            f"main (₱{main_total}) and sub (₱{sub_total})"
        )

        fixed = 0
        for sp in main_payments:
            sub_share = (sp.amount * sub_total / combined).quantize(Decimal("0.01"))
            main_share = sp.amount - sub_share

            if sub_share <= 0:
                continue

            fixed += 1
            self.stdout.write(
                f"    Payment #{sp.id} ₱{sp.amount} → main ₱{main_share}, sub ₱{sub_share}"
            )

            if not dry_run:
                with transaction.atomic():
                    sp.amount = main_share
                    sp.save(update_fields=["amount"])

                    SalesPayment.objects.create(
                        transaction=sub_tx,
                        payment_type=sp.payment_type,
                        amount=sub_share,
                        payment_date=sp.payment_date,
                    )

        return fixed

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

            # Fix payment split if sub stall has no payments
            if not sub_tx.payments.exists():
                payments_fixed += self._fix_payment_split(main_tx, sub_tx, svc, dry_run)

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

            count = self._fix_payment_split(main_tx, sub_tx, svc, dry_run)
            phase2_fixed += count
            payments_fixed += count

        self.stdout.write(f"  Found {phase2_fixed} payment(s) to rebalance.")

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"\n{prefix}Done. "
            f"Linked {linked} sub transactions, "
            f"fixed {payments_fixed} payment split(s)."
        ))
