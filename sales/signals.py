"""WebSocket push for real-time sales transaction updates."""

import logging
import threading
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction
from django.db.models import Sum
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _queue_google_sheets_sync(transaction_id: int) -> None:
    # De-dupe noisy save chains (e.g. payment status recalculations) in a short window.
    dedupe_key = f"google_sheets_sync_sales_tx:{transaction_id}"
    if not cache.add(dedupe_key, True, timeout=15):
        return

    def _run_sync():
        from sales.integrations.google_sheets import sync_sales_transaction_to_google_sheet

        sync_sales_transaction_to_google_sheet(transaction_id)

    worker = threading.Thread(target=_run_sync, daemon=True)
    worker.start()


def _queue_google_sheets_day_sync(stall_id: int, target_date) -> None:
    if not stall_id or target_date is None:
        return

    dedupe_key = f"google_sheets_sync_day:{stall_id}:{target_date.isoformat()}"
    if not cache.add(dedupe_key, True, timeout=15):
        return

    def _run_sync():
        from sales.integrations.google_sheets import sync_sales_day_to_google_sheet

        sync_sales_day_to_google_sheet(stall_id, target_date)

    worker = threading.Thread(target=_run_sync, daemon=True)
    worker.start()


def _recalculate_open_remittance_for_day(stall_id: int, target_date) -> None:
    if not stall_id or target_date is None:
        return

    from expenses.models import Expense
    from remittances.models import RemittanceRecord
    from sales.models import PaymentStatus, SalesPayment, SalesTransaction

    remittance = RemittanceRecord.objects.filter(
        stall_id=stall_id,
        remittance_date=target_date,
        is_remitted=False,
        manually_adjusted=False,
    ).first()

    if not remittance:
        return

    def sum_sales(payment_type: str) -> Decimal:
        total_payments = (
            SalesPayment.objects.filter(
                transaction__stall_id=stall_id,
                payment_date__date=target_date,
                transaction__payment_status__in=[PaymentStatus.PAID, PaymentStatus.PARTIAL],
                transaction__voided=False,
                transaction__is_deleted=False,
                payment_type=payment_type,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )

        if payment_type == "cash":
            total_change = (
                SalesTransaction.objects.filter(
                    stall_id=stall_id,
                    payment_status__in=[PaymentStatus.PAID, PaymentStatus.PARTIAL],
                    voided=False,
                    is_deleted=False,
                    payments__payment_date__date=target_date,
                )
                .distinct()
                .aggregate(total=Sum("change_amount"))["total"]
                or Decimal("0")
            )
            return total_payments - total_change

        return total_payments

    sales = {pt: sum_sales(pt) for pt in ["cash", "gcash", "credit", "debit", "cheque"]}

    normal_expenses = (
        Expense.objects.filter(
            stall_id=stall_id,
            expense_date=target_date,
            is_deleted=False,
            is_reimbursement=False,
        ).aggregate(total=Sum("paid_amount"))["total"]
        or Decimal("0")
    )
    reimbursements = (
        Expense.objects.filter(
            stall_id=stall_id,
            expense_date=target_date,
            is_deleted=False,
            is_reimbursement=True,
        ).aggregate(total=Sum("paid_amount"))["total"]
        or Decimal("0")
    )

    remittance.total_sales_cash = sales["cash"]
    remittance.total_sales_gcash = sales["gcash"]
    remittance.total_sales_credit = sales["credit"]
    remittance.total_sales_debit = sales["debit"]
    remittance.total_sales_cheque = sales["cheque"]
    remittance.total_expenses = normal_expenses - reimbursements
    remittance.save(
        update_fields=[
            "total_sales_cash",
            "total_sales_gcash",
            "total_sales_credit",
            "total_sales_debit",
            "total_sales_cheque",
            "total_expenses",
            "updated_at",
        ]
    )


def _queue_remittance_recalculate(stall_id: int, target_date) -> None:
    if not stall_id or target_date is None:
        return

    dedupe_key = f"remittance_recalc_day:{stall_id}:{target_date.isoformat()}"
    if not cache.add(dedupe_key, True, timeout=8):
        return

    worker = threading.Thread(
        target=_recalculate_open_remittance_for_day,
        kwargs={"stall_id": stall_id, "target_date": target_date},
        daemon=True,
    )
    worker.start()


@receiver(post_save, sender="sales.SalesTransaction")
def push_sales_transaction_update(sender, instance, created, **kwargs):
    from analytics.ws_utils import push_dashboard_event

    push_dashboard_event(
        "sales_transaction_created" if created else "sales_transaction_updated",
        {
            "transaction_id": instance.id,
            "payment_status": instance.payment_status,
            "voided": instance.voided,
        },
    )

    # Sync only after commit so related items/payments and computed fields are final.
    transaction.on_commit(lambda: _queue_google_sheets_sync(instance.id))

    target_date = instance.transaction_date or (
        instance.created_at.date() if instance.created_at else None
    )
    transaction.on_commit(
        lambda: _queue_remittance_recalculate(instance.stall_id, target_date)
    )


@receiver(post_delete, sender="sales.SalesTransaction")
def push_sales_transaction_delete(sender, instance, **kwargs):
    if instance.stall_id and instance.transaction_date:
        transaction.on_commit(
            lambda: _queue_google_sheets_day_sync(instance.stall_id, instance.transaction_date)
        )
        transaction.on_commit(
            lambda: _queue_remittance_recalculate(instance.stall_id, instance.transaction_date)
        )


@receiver(post_save, sender="sales.SalesPayment")
def push_sales_payment_update(sender, instance, created, **kwargs):
    from analytics.ws_utils import push_dashboard_event

    if created:
        push_dashboard_event("sales_payment_created", {
            "transaction_id": instance.transaction_id,
        })

    # Payment edits can change per-day payment-method display.
    transaction.on_commit(lambda: _queue_google_sheets_sync(instance.transaction_id))
    payment_date = instance.payment_date.date() if instance.payment_date else None
    transaction.on_commit(
        lambda: _queue_remittance_recalculate(instance.transaction.stall_id, payment_date)
    )


@receiver(post_delete, sender="sales.SalesPayment")
def push_sales_payment_delete(sender, instance, **kwargs):
    transaction.on_commit(lambda: _queue_google_sheets_sync(instance.transaction_id))
    payment_date = instance.payment_date.date() if instance.payment_date else None
    transaction.on_commit(
        lambda: _queue_remittance_recalculate(instance.transaction.stall_id, payment_date)
    )


@receiver(post_save, sender="sales.SalesItem")
def push_sales_item_update(sender, instance, **kwargs):
    transaction.on_commit(lambda: _queue_google_sheets_sync(instance.transaction_id))


@receiver(post_delete, sender="sales.SalesItem")
def push_sales_item_delete(sender, instance, **kwargs):
    transaction.on_commit(lambda: _queue_google_sheets_sync(instance.transaction_id))
