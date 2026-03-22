"""WebSocket push for real-time inventory/stock updates."""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="inventory.Stock")
def push_stock_update(sender, instance, **kwargs):
    from analytics.ws_utils import push_dashboard_event

    push_dashboard_event("stock_updated", {
        "stock_id": instance.id,
        "item_id": instance.item_id,
        "quantity": instance.quantity,
    })


@receiver(post_save, sender="inventory.StockRoomStock")
def push_stockroom_update(sender, instance, **kwargs):
    from analytics.ws_utils import push_dashboard_event

    push_dashboard_event("stockroom_updated", {
        "stock_id": instance.id,
        "item_id": instance.item_id,
        "quantity": instance.quantity,
    })


@receiver(post_save, sender="inventory.StockRequest")
def push_stock_request_update(sender, instance, created, **kwargs):
    from analytics.ws_utils import push_dashboard_event

    push_dashboard_event(
        "stock_request_created" if created else "stock_request_updated",
        {
            "stock_request_id": instance.id,
            "status": instance.status,
        },
    )
