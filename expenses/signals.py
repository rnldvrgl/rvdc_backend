import logging
import threading

from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _queue_expense_day_sync(stall_id: int, target_date) -> None:
    if not stall_id or target_date is None:
        return

    dedupe_key = f"google_sheets_sync_expense_day:{stall_id}:{target_date.isoformat()}"
    if not cache.add(dedupe_key, True, timeout=15):
        return

    def _run_sync() -> None:
        try:
            from sales.integrations.google_sheets import sync_sales_day_to_google_sheet

            sync_sales_day_to_google_sheet(stall_id, target_date)
        except Exception as exc:
            logger.exception("Failed Google Sheets expense day sync: %s", exc)

    threading.Thread(target=_run_sync, daemon=True).start()


def _queue_expense_remittance_recalc(stall_id: int, target_date) -> None:
    if not stall_id or target_date is None:
        return

    dedupe_key = f"expense_remittance_recalc:{stall_id}:{target_date.isoformat()}"
    if not cache.add(dedupe_key, True, timeout=8):
        return

    def _run_recalc() -> None:
        try:
            from sales.signals import _recalculate_open_remittance_for_day

            _recalculate_open_remittance_for_day(stall_id, target_date)
        except Exception as exc:
            logger.exception("Failed expense remittance recalculation: %s", exc)

    threading.Thread(target=_run_recalc, daemon=True).start()


@receiver(post_save, sender="expenses.Expense")
def expense_saved(sender, instance, **kwargs):
    target_date = instance.expense_date
    transaction.on_commit(lambda: _queue_expense_day_sync(instance.stall_id, target_date))
    transaction.on_commit(
        lambda: _queue_expense_remittance_recalc(instance.stall_id, target_date)
    )


@receiver(post_delete, sender="expenses.Expense")
def expense_deleted(sender, instance, **kwargs):
    target_date = instance.expense_date
    transaction.on_commit(lambda: _queue_expense_day_sync(instance.stall_id, target_date))
    transaction.on_commit(
        lambda: _queue_expense_remittance_recalc(instance.stall_id, target_date)
    )
