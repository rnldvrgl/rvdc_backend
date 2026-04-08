"""
Maintenance command to fix two related service-payment bugs on existing records.

Problem 1 — Main TX missing SalesPayments (shows UNPAID despite service being paid)
-----------------------------------------------------------------------------
When a service was marked completed AFTER a payment was already recorded, the
main-stall SalesTransaction was created during completion but never received
SalesPayment mirror records.  The sub-stall TX already had payment mirrors so
the money appeared there while the main TX showed UNPAID.

Problem 2 — Sub TX line items out of sync with parts
------------------------------------------------------
When parts (ApplianceItemUsed / ServiceItemUsed) were added or changed on a
completed service, the sub-stall SalesTransaction items were never updated, so
the TX total no longer matched the service's sub_stall_revenue.

What this command does
-----------------------
For every completed/paid service that has both a related_transaction (main TX)
and has service-level payments recorded:

  Step 1 – Re-sync sub TX items
      Rebuild the sub-stall SalesTransaction line items from the current
      ApplianceItemUsed / ServiceItemUsed records so the TX total is accurate.

  Step 2 – Backfill missing SalesPayments on main TX
      Re-compute the correct waterfall split (sub TX first, then main TX) for
      all service payments. Delete any existing SalesPayment records on the
      main TX that are inconsistent, then create the right ones.

  Step 3 – Refresh payment_status
      Call update_payment_status() on both TXs and the service.

Run:
    python manage.py fix_service_payment_sync
    python manage.py fix_service_payment_sync --dry-run
    python manage.py fix_service_payment_sync --service-id 893
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction

from sales.models import SalesItem, SalesPayment
from services.business_logic import ServicePaymentManager
from services.models import Service


class Command(BaseCommand):
    help = "Fix main-TX missing payments and sub-TX out-of-sync items for completed services"

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

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        service_id = options["service_id"]

        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY RUN — no changes will be saved ===\n"))

        qs = (
            Service.objects.filter(
                related_transaction__isnull=False,
                payments__isnull=False,
            )
            .distinct()
            .select_related("related_transaction", "related_sub_transaction", "client")
            .prefetch_related(
                "payments",
                "appliances__items_used__item",
                "appliances__appliance_type",
                "service_items__item",
            )
        )

        if service_id:
            qs = qs.filter(pk=service_id)

        total_services = qs.count()
        self.stdout.write(f"Checking {total_services} service(s)…\n")

        fixed_sub_items = 0
        fixed_main_payments = 0
        skipped = 0

        for service in qs:
            main_tx = service.related_transaction
            sub_tx = service.related_sub_transaction if service.related_sub_transaction_id else None

            service_payments = list(service.payments.order_by("payment_date"))
            if not service_payments:
                continue

            total_svc_paid = sum(p.amount for p in service_payments)

            # ── Step 1: detect sub TX item mismatch ──────────────────────────
            sub_needs_rebuild = False
            if sub_tx and not sub_tx.voided:
                # Compute expected sub total from the service revenue model
                expected_sub_total = service.sub_stall_revenue or Decimal("0")
                current_sub_total = sub_tx.computed_total or Decimal("0")
                if abs(expected_sub_total - current_sub_total) > Decimal("0.01"):
                    sub_needs_rebuild = True
                    self.stdout.write(
                        f"  Service #{service.id}: sub TX #{sub_tx.id} total "
                        f"₱{current_sub_total} ≠ expected ₱{expected_sub_total} — will rebuild items"
                    )

            # ── Step 2: detect main TX missing payments ───────────────────────
            main_needs_fix = False
            if main_tx and not main_tx.voided:
                main_total = main_tx.computed_total or Decimal("0")
                main_currently_paid = sum(p.amount for p in main_tx.payments.all())

                # After the sub TX is filled, the rest should flow to main.
                sub_total = (sub_tx.computed_total or Decimal("0")) if (sub_tx and not sub_tx.voided) else Decimal("0")
                sub_actually_paid = sum(p.amount for p in sub_tx.payments.all()) if sub_tx else Decimal("0")

                # Expected payment to main = total paid – what belongs to sub
                expected_main_payment = max(total_svc_paid - sub_total, Decimal("0"))
                # Cap at what main TX actually requires
                expected_main_payment = min(expected_main_payment, main_total)

                if abs(expected_main_payment - main_currently_paid) > Decimal("0.01"):
                    main_needs_fix = True
                    self.stdout.write(
                        f"  Service #{service.id}: main TX #{main_tx.id} paid "
                        f"₱{main_currently_paid} but should be ₱{expected_main_payment} — will fix"
                    )

            if not sub_needs_rebuild and not main_needs_fix:
                skipped += 1
                continue

            if dry_run:
                if sub_needs_rebuild:
                    fixed_sub_items += 1
                if main_needs_fix:
                    fixed_main_payments += 1
                continue

            # ── Apply fixes atomically ─────────────────────────────────────────
            try:
                with db_transaction.atomic():
                    # Step 1 – Rebuild sub TX items
                    if sub_needs_rebuild and sub_tx:
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

                        sub_tx.update_payment_status()
                        fixed_sub_items += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  ✓ Service #{service.id}: rebuilt sub TX #{sub_tx.id} items"
                            )
                        )

                    # Step 2 – Fix main TX payments using waterfall split
                    if main_needs_fix and main_tx:
                        # Remove all existing SalesPayment rows on the main TX so we
                        # can recompute a clean waterfall from the service payments.
                        main_tx.payments.all().delete()

                        # Also refresh the sub TX payments reference after possible rebuild
                        if sub_tx:
                            sub_tx.refresh_from_db()

                        sub_total_now = (sub_tx.computed_total or Decimal("0")) if sub_tx else Decimal("0")
                        main_total_now = main_tx.computed_total or Decimal("0")

                        main_filled = Decimal("0")
                        sub_filled = Decimal("0")

                        # Re-snapshot sub TX payments (unchanged by this fix, keep as-is):
                        # We only recreate the main TX payments here.
                        sub_paid_snapshot = (
                            sum(p.amount for p in sub_tx.payments.all()) if sub_tx else Decimal("0")
                        )

                        for svc_payment in service_payments:
                            m_share, s_share = ServicePaymentManager._waterfall_split(
                                svc_payment.amount,
                                main_total_now - main_filled,
                                sub_total_now - sub_filled,
                            )
                            if m_share > 0:
                                SalesPayment.objects.create(
                                    transaction=main_tx,
                                    payment_type=svc_payment.payment_type,
                                    amount=m_share,
                                    payment_date=svc_payment.payment_date,
                                )
                            main_filled += m_share
                            sub_filled += s_share

                        main_tx.update_payment_status()
                        fixed_main_payments += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  ✓ Service #{service.id}: backfilled main TX #{main_tx.id} "
                                f"payments (₱{main_filled})"
                            )
                        )

                    # Step 3 – Refresh service payment status
                    service.update_payment_status()

            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(
                        f"  ✗ Service #{service.id}: error — {exc}"
                    )
                )

        self.stdout.write("")
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN complete. Would fix:\n"
                    f"  • {fixed_sub_items} sub TX(s) with out-of-sync items\n"
                    f"  • {fixed_main_payments} main TX(s) with missing payments\n"
                    f"  • {skipped} service(s) already correct (no changes needed)"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done.\n"
                    f"  • {fixed_sub_items} sub TX(s) rebuilt\n"
                    f"  • {fixed_main_payments} main TX(s) backfilled\n"
                    f"  • {skipped} service(s) already correct (skipped)"
                )
            )
