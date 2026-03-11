"""
Management command to recalculate sales totals on existing RemittanceRecords.

Run this AFTER fix_split_payments so that SalesPayments are on the correct
stall.  This command re-queries actual SalesPayment data for each remittance
date/stall and overwrites the stored totals with the corrected values.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from expenses.models import Expense
from remittances.models import RemittanceRecord
from sales.models import SalesPayment, SalesTransaction, PaymentStatus


def sum_sales(stall, date_val, payment_type):
    """Compute net sales for a stall/date/payment_type (matches serializer logic)."""
    total_payments = (
        SalesPayment.objects.filter(
            transaction__stall=stall,
            payment_date__date=date_val,
            transaction__payment_status__in=[PaymentStatus.PAID, PaymentStatus.PARTIAL],
            payment_type=payment_type,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )

    if payment_type == "cash":
        total_change = (
            SalesTransaction.objects.filter(
                stall=stall,
                payment_status__in=[PaymentStatus.PAID, PaymentStatus.PARTIAL],
                payments__payment_date__date=date_val,
            )
            .distinct()
            .aggregate(total=Sum("change_amount"))["total"]
            or Decimal("0")
        )
        return total_payments - total_change

    return total_payments


class Command(BaseCommand):
    help = "Recalculate sales totals on existing remittance records"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without saving",
        )
        parser.add_argument(
            "--include-manual",
            action="store_true",
            help="Also recalculate manually-adjusted records (skipped by default)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        include_manual = options["include_manual"]

        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY RUN MODE ===\n"))

        remittances = RemittanceRecord.objects.select_related("stall").order_by("created_at")
        if not include_manual:
            skipped = remittances.filter(manually_adjusted=True).count()
            remittances = remittances.filter(manually_adjusted=False)
            if skipped:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping {skipped} manually-adjusted record(s). "
                        "Use --include-manual to recalculate them too.\n"
                    )
                )
        updated_count = 0

        for rem in remittances:
            target_date = rem.created_at.date() if rem.created_at else None
            if not target_date or not rem.stall:
                continue

            new_totals = {
                pt: sum_sales(rem.stall, target_date, pt)
                for pt in ["cash", "gcash", "credit", "debit", "cheque"]
            }

            new_expenses = (
                Expense.objects.filter(
                    stall=rem.stall, created_at__date=target_date
                ).aggregate(total=Sum("paid_amount"))["total"]
                or Decimal("0")
            )

            # Check if anything changed
            old = {
                "cash": rem.total_sales_cash,
                "gcash": rem.total_sales_gcash,
                "credit": rem.total_sales_credit,
                "debit": rem.total_sales_debit,
                "cheque": rem.total_sales_cheque,
            }

            changed = (
                any(Decimal(str(new_totals[k])) != Decimal(str(old[k])) for k in old)
                or Decimal(str(new_expenses)) != Decimal(str(rem.total_expenses))
            )

            if not changed:
                continue

            updated_count += 1
            self.stdout.write(
                f"\nRemittance #{rem.id} — {rem.stall.name} — {target_date}"
            )

            for k in ["cash", "gcash", "credit", "debit", "cheque"]:
                old_val = Decimal(str(old[k]))
                new_val = Decimal(str(new_totals[k]))
                if old_val != new_val:
                    self.stdout.write(f"  {k:>8}: {old_val} → {new_val}")

            old_exp = Decimal(str(rem.total_expenses))
            new_exp = Decimal(str(new_expenses))
            if old_exp != new_exp:
                self.stdout.write(f"  expenses: {old_exp} → {new_exp}")

            if dry_run:
                self.stdout.write(self.style.WARNING("  → Would update"))
                continue

            with transaction.atomic():
                rem.total_sales_cash = new_totals["cash"]
                rem.total_sales_gcash = new_totals["gcash"]
                rem.total_sales_credit = new_totals["credit"]
                rem.total_sales_debit = new_totals["debit"]
                rem.total_sales_cheque = new_totals["cheque"]
                rem.total_expenses = new_expenses
                rem.save(update_fields=[
                    "total_sales_cash",
                    "total_sales_gcash",
                    "total_sales_credit",
                    "total_sales_debit",
                    "total_sales_cheque",
                    "total_expenses",
                ])

            self.stdout.write(self.style.SUCCESS("  ✓ Updated"))

        self.stdout.write("")
        if updated_count == 0:
            self.stdout.write(
                self.style.SUCCESS("All remittance records already have correct totals.")
            )
        else:
            verb = "Would update" if dry_run else "Updated"
            self.stdout.write(
                self.style.SUCCESS(f"{verb} {updated_count} remittance record(s).")
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\nRe-run without --dry-run to apply changes.")
            )
