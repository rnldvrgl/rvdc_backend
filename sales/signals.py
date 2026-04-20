"""WebSocket push for real-time sales transaction updates."""

import logging
import threading

from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_save
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


@receiver(post_save, sender="sales.SalesPayment")
def push_sales_payment_update(sender, instance, created, **kwargs):
    from analytics.ws_utils import push_dashboard_event

    if created:
        push_dashboard_event("sales_payment_created", {
            "transaction_id": instance.transaction_id,
        })
