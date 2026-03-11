"""
Management command to backfill related_sub_transaction on existing services
and fix payment splits for sub stall transactions.

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
from sales.models import SalesPayment, SalesTransaction, PaymentStatus
from services.models import Service


def get_main_stall():
    return Stall.objects.get(name__icontains="main")


def get_sub_stall():
    return Stall.objects.get(name__icontains="sub")


class Command(BaseCommand):
    help = "Backfill related_sub_transaction on services and fix sub stall payment splits."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying them.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        sub_stall = get_sub_stall()

        services = Service.objects.filter(
            related_transaction__isnull=False,
            related_sub_transaction__isnull=True,
            is_deleted=False,
        ).select_related("related_transaction", "client")

        linked = 0
        payments_fixed = 0

        for svc in services:
            main_tx = svc.related_transaction
            if not main_tx or main_tx.voided:
                continue

            # Find sub stall transaction by time proximity
            sub_tx = SalesTransaction.objects.filter(
                stall=sub_stall,
                client=svc.client,
                voided=False,
                created_at__range=(
                    main_tx.created_at - timedelta(seconds=5),
                    main_tx.created_at + timedelta(seconds=5),
                ),
            ).exclude(id=main_tx.id).first()

            if not sub_tx:
                continue

            self.stdout.write(f"Service #{svc.id}: linking sub tx #{sub_tx.id} (₱{sub_tx.computed_total})")
            linked += 1

            if not dry_run:
                svc.related_sub_transaction = sub_tx
                svc.save(update_fields=["related_sub_transaction"])

            # Fix payment split: if sub stall has no payments, split existing main stall payments
            sub_has_payments = sub_tx.payments.exists()
            if sub_has_payments:
                continue

            main_total = main_tx.computed_total or Decimal("0")
            sub_total = sub_tx.computed_total or Decimal("0")
            combined = main_total + sub_total
            if combined <= 0 or sub_total <= 0:
                continue

            # Get all current SalesPayments on main stall for this transaction
            main_payments = list(sub_tx.payments.none())  # empty qs
            main_payments = list(main_tx.payments.all().order_by("payment_date"))
            if not main_payments:
                continue

            self.stdout.write(f"  Splitting {len(main_payments)} payment(s) between main (₱{main_total}) and sub (₱{sub_total})")

            for sp in main_payments:
                sub_share = (sp.amount * sub_total / combined).quantize(Decimal("0.01"))
                main_share = sp.amount - sub_share

                if sub_share <= 0:
                    continue

                payments_fixed += 1
                self.stdout.write(
                    f"    Payment #{sp.id} ₱{sp.amount} → main ₱{main_share}, sub ₱{sub_share}"
                )

                if not dry_run:
                    with transaction.atomic():
                        # Reduce main stall payment
                        sp.amount = main_share
                        sp.save(update_fields=["amount"])

                        # Create sub stall payment
                        SalesPayment.objects.create(
                            transaction=sub_tx,
                            payment_type=sp.payment_type,
                            amount=sub_share,
                            payment_date=sp.payment_date,
                        )

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"\n{prefix}Done. Linked {linked} sub transactions, fixed {payments_fixed} payment splits."
        ))
