"""WebSocket push for real-time sales transaction updates."""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


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


@receiver(post_save, sender="sales.SalesPayment")
def push_sales_payment_update(sender, instance, created, **kwargs):
    from analytics.ws_utils import push_dashboard_event

    if created:
        push_dashboard_event("sales_payment_created", {
            "transaction_id": instance.transaction_id,
        })
