"""
Maintenance command to reconcile service-payment SalesTransaction records.

Syndromes fixed
---------------
1. Main TX shows UNPAID / £0 paid despite the service being fully paid.
   Cause: payment was recorded when no main TX existed yet, so the SalesPayment
   mirror was never created for the main TX.

2. Sub TX line items out of sync with actual parts used.
   Cause: parts (ApplianceItemUsed / ServiceItemUsed) were added/changed after
   the sub TX was already created.

3. Both main TX and sub TX have zero SalesPayments even though the service is paid.
   Cause: payment was recorded before any TX existed; mirrors were dropped silently.

Algorithm
---------
For every qualifying service:
  a) Find the main TX (service.related_transaction) and the sub TX
     (service.related_sub_transaction, or found by time-window fallback).
  b) Rebuild sub TX items if they don't match service.sub_stall_revenue.
  c) Delete every existing SalesPayment on BOTH TXs and recreate them from
     scratch using the correct waterfall split (sub first, then main) across
     all ServicePayment records.
  d) Call update_payment_status() on both TXs and the service.

Usage
-----
    python manage.py fix_service_payment_sync
    python manage.py fix_service_payment_sync --dry-run
    python manage.py fix_service_payment_sync --service-id 893
    python manage.py fix_service_payment_sync --all   # includes services without main TX
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction
from django.utils import timezone

from inventory.models import Stall
from sales.models import SalesItem, SalesPayment, SalesTransaction
from services.business_logic import ServicePaymentManager
from services.models import Service


class Command(BaseCommand):
    help = "Reconcile SalesPayment mirrors for all service-linked SalesTransactions"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing to the database",
        )
        parser.add_argument(
            "--service-id",
            type=int,
            default=None,
            help="Limit to a single service ID",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            dest="include_all",
            help="Also include services that only have a sub TX (no main TX linked)",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_sub_tx(self, service, main_tx, sub_stall):
        """Return the linked sub TX, falling back to a time-window search."""
        if service.related_sub_transaction_id:
            try:
                sub = service.related_sub_transaction
                if not sub.voided:
                    return sub
            except SalesTransaction.DoesNotExist:
                pass

        if main_tx:
            return (
                SalesTransaction.objects.filter(
                    stall=sub_stall,
                    client=service.client,
                    voided=False,
                    created_at__range=(
                        main_tx.created_at - timedelta(seconds=120),
                        main_tx.created_at + timedelta(seconds=120),
                    ),
                )
                .exclude(id=main_tx.id)
                .first()
            )
        return None

    @staticmethod
    def _waterfall(payments, main_total, sub_total):
        """
        Given a list of ServicePayment amounts, return how much should go to
        each TX in total (sub first, then main).
        """
        m_total = Decimal("0")
        s_total = Decimal("0")
        m_rem = main_total
        s_rem = sub_total
        for p in payments:
            m, s = ServicePaymentManager._waterfall_split(p.amount, m_rem, s_rem)
            m_total += m
            s_total += s
            m_rem -= m
            s_rem -= s
        return m_total, s_total

    def _rebuild_sub_items(self, service, sub_tx):
        """Rebuild the sub TX line items from current service parts."""
        sub_tx.items.all().delete()
        for appliance in service.appliances.all():
            for item_used in appliance.items_used.all():
                if item_used.is_free:
                    continue
                charged_qty = item_used.quantity - item_used.free_quantity
                if charged_qty > 0:
                    SalesItem.objects.create(
                        transaction=sub_tx,
                        item=item_used.item,
                        description="",
                        quantity=charged_qty,
                        final_price_per_unit=item_used.discounted_price,
                    )
        for item_used in service.service_items.all():
            if item_used.is_free:
                continue
            charged_qty = item_used.quantity - item_used.free_quantity
            if charged_qty > 0:
                SalesItem.objects.create(
                    transaction=sub_tx,
                    item=item_used.item,
                    description="",
                    quantity=charged_qty,
                    final_price_per_unit=item_used.discounted_price,
                )

    # ------------------------------------------------------------------
    # Main handler
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        service_id = options["service_id"]
        include_all = options["include_all"]

        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY RUN — no changes will be saved ===\n"))

        sub_stall = Stall.objects.filter(stall_type="sub", is_system=True).first()

        base_filter = Service.objects.filter(payments__isnull=False).distinct()
        if include_all:
            qs = base_filter
        else:
            qs = base_filter.filter(related_transaction__isnull=False)

        if service_id:
            qs = qs.filter(pk=service_id)

        qs = qs.select_related(
            "related_transaction", "related_sub_transaction", "client"
        ).prefetch_related(
            "payments",
            "appliances__items_used__item",
            "appliances__appliance_type",
            "service_items__item",
        )

        total_services = qs.count()
        self.stdout.write(f"Checking {total_services} service(s)…\n")

        fixed = 0
        skipped = 0
        errored = 0

        for service in qs:
            main_tx = service.related_transaction if service.related_transaction_id else None
            if main_tx and main_tx.voided:
                main_tx = None

            sub_tx = self._find_sub_tx(service, main_tx, sub_stall)

            service_payments = list(service.payments.order_by("payment_date"))
            if not service_payments:
                skipped += 1
                continue

            total_svc_paid = sum(p.amount for p in service_payments)

            # ── Determine correct distribution ─────────────────────────────
            main_total = (main_tx.computed_total or Decimal("0")) if main_tx else Decimal("0")
            sub_total = (sub_tx.computed_total or Decimal("0")) if sub_tx else Decimal("0")

            correct_main, correct_sub = self._waterfall(service_payments, main_total, sub_total)

            # ── Determine current distribution ─────────────────────────────
            current_main = (
                sum(p.amount for p in main_tx.payments.all()) if main_tx else Decimal("0")
            )
            current_sub = (
                sum(p.amount for p in sub_tx.payments.all()) if sub_tx else Decimal("0")
            )

            # ── Detect sub TX item mismatch ────────────────────────────────
            sub_items_need_rebuild = False
            if sub_tx:
                expected_sub_total = service.sub_stall_revenue or Decimal("0")
                if abs(expected_sub_total - sub_total) > Decimal("0.01"):
                    sub_items_need_rebuild = True

            # ── Detect payment mismatch ────────────────────────────────────
            payments_need_fix = (
                abs(correct_main - current_main) > Decimal("0.01")
                or abs(correct_sub - current_sub) > Decimal("0.01")
            )

            if not sub_items_need_rebuild and not payments_need_fix:
                skipped += 1
                continue

            # ── Report ─────────────────────────────────────────────────────
            if sub_items_need_rebuild:
                self.stdout.write(
                    f"  Service #{service.id}: sub TX #{sub_tx.id if sub_tx else 'N/A'} "
                    f"items total ₱{sub_total} ≠ expected ₱{service.sub_stall_revenue}"
                )
            if payments_need_fix:
                self.stdout.write(
                    f"  Service #{service.id}: "
                    + (f"main TX #{main_tx.id} paid ₱{current_main} → should be ₱{correct_main}  " if main_tx else "")
                    + (f"sub TX #{sub_tx.id} paid ₱{current_sub} → should be ₱{correct_sub}" if sub_tx else "")
                )

            if dry_run:
                fixed += 1
                continue

            # ── Apply fix ──────────────────────────────────────────────────
            try:
                with db_transaction.atomic():
                    # Step 1: rebuild sub TX items if needed
                    if sub_items_need_rebuild and sub_tx:
                        self._rebuild_sub_items(service, sub_tx)
                        # Recompute sub_total after rebuild
                        sub_total = sub_tx.computed_total or Decimal("0")
                        correct_main, correct_sub = self._waterfall(
                            service_payments, main_total, sub_total
                        )
                        self.stdout.write(
                            self.style.SUCCESS(f"  ✓ Rebuilt sub TX #{sub_tx.id} items")
                        )

                    # Step 2: delete ALL existing SalesPayments on both TXs
                    if payments_need_fix:
                        if main_tx:
                            main_tx.payments.all().delete()
                        if sub_tx:
                            sub_tx.payments.all().delete()

                        # Recreate using correct waterfall
                        m_rem = main_total
                        s_rem = sub_total
                        for svc_payment in service_payments:
                            m, s = ServicePaymentManager._waterfall_split(
                                svc_payment.amount, m_rem, s_rem
                            )
                            if m > 0 and main_tx:
                                SalesPayment.objects.create(
                                    transaction=main_tx,
                                    payment_type=svc_payment.payment_type,
                                    amount=m,
                                    payment_date=svc_payment.payment_date,
                                )
                            if s > 0 and sub_tx:
                                SalesPayment.objects.create(
                                    transaction=sub_tx,
                                    payment_type=svc_payment.payment_type,
                                    amount=s,
                                    payment_date=svc_payment.payment_date,
                                )
                            m_rem -= m
                            s_rem -= s

                        if main_tx:
                            main_tx.update_payment_status()
                        if sub_tx:
                            sub_tx.update_payment_status()

                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  ✓ Service #{service.id}: payments fixed "
                                + (f"main=₱{correct_main} " if main_tx else "")
                                + (f"sub=₱{correct_sub}" if sub_tx else "")
                            )
                        )

                    # Step 3: persist sub TX link if found via fallback
                    if sub_tx and not service.related_sub_transaction_id:
                        service.related_sub_transaction = sub_tx
                        service.save(update_fields=["related_sub_transaction"])

                    # Step 4: sync service payment_status
                    service.update_payment_status()

                fixed += 1

            except Exception as exc:
                errored += 1
                self.stdout.write(
                    self.style.ERROR(f"  ✗ Service #{service.id}: {exc}")
                )

        self.stdout.write("")
        label = "Would fix" if dry_run else "Fixed"
        self.stdout.write(
            self.style.SUCCESS(
                f"{label} {fixed} service(s). "
                f"Skipped {skipped} (already correct). "
                + (f"Errors: {errored}." if errored else "")
            )
        )
