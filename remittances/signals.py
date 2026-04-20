import logging
import threading

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from remittances.models import CashDenominationBreakdown, RemittanceRecord

logger = logging.getLogger(__name__)


def _queue_day_sync(stall_id: int, remittance_date):
    if not stall_id or not remittance_date:
        return

    dedupe_key = f"google_sheets_sync_remittance_day:{stall_id}:{remittance_date.isoformat()}"
    if not cache.add(dedupe_key, True, timeout=15):
        return

    def _run_sync():
        try:
            from sales.integrations.google_sheets import sync_sales_day_to_google_sheet

            sync_sales_day_to_google_sheet(stall_id, remittance_date)
        except Exception as exc:
            logger.exception("Failed Google Sheets remittance day sync: %s", exc)

    threading.Thread(target=_run_sync, daemon=True).start()


@receiver(post_save, sender=RemittanceRecord)
def remittance_saved(sender, instance: RemittanceRecord, **kwargs):
    _queue_day_sync(instance.stall_id, instance.remittance_date)


@receiver(post_delete, sender=RemittanceRecord)
def remittance_deleted(sender, instance: RemittanceRecord, **kwargs):
    _queue_day_sync(instance.stall_id, instance.remittance_date)


@receiver(post_save, sender=CashDenominationBreakdown)
def breakdown_saved(sender, instance: CashDenominationBreakdown, **kwargs):
    if instance.remittance_id:
        _queue_day_sync(instance.remittance.stall_id, instance.remittance.remittance_date)


@receiver(post_delete, sender=CashDenominationBreakdown)
def breakdown_deleted(sender, instance: CashDenominationBreakdown, **kwargs):
    if instance.remittance_id:
        _queue_day_sync(instance.remittance.stall_id, instance.remittance.remittance_date)
