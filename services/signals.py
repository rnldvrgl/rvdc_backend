"""
Signals for automatic revenue recalculation when service data changes,
and WebSocket push for real-time dashboard/service page updates.
"""
import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from services.business_logic import RevenueCalculator, ServicePaymentManager
from services.models import ApplianceItemUsed, ServiceAppliance

logger = logging.getLogger(__name__)


def _sync_sub_tx_if_completed(service):
    """Sync the sub-stall TX items when the service is already completed."""
    from utils.enums import ServiceStatus
    if service.status == ServiceStatus.COMPLETED and service.related_sub_transaction_id:
        ServicePaymentManager.sync_sub_sales_items(service)


@receiver(post_save, sender=ApplianceItemUsed)
def recalculate_revenue_on_item_save(sender, instance, **kwargs):
    """Recalculate service revenue when an item is added or updated."""
    service = instance.appliance.service
    RevenueCalculator.calculate_service_revenue(service, save=True)
    # Keep the sub-stall sales transaction in sync when parts change on a
    # completed service (e.g. technician adds a part after payment was taken).
    _sync_sub_tx_if_completed(service)


@receiver(post_delete, sender=ApplianceItemUsed)
def recalculate_revenue_on_item_delete(sender, instance, **kwargs):
    """Recalculate service revenue when an item is deleted."""
    service = instance.appliance.service
    RevenueCalculator.calculate_service_revenue(service, save=True)
    _sync_sub_tx_if_completed(service)


@receiver(post_save, sender=ServiceAppliance)
def recalculate_revenue_on_appliance_save(sender, instance, **kwargs):
    """Recalculate service revenue when an appliance is added or updated (for labor fees)."""
    service = instance.service
    RevenueCalculator.calculate_service_revenue(service, save=True)


@receiver(post_delete, sender=ServiceAppliance)
def recalculate_revenue_on_appliance_delete(sender, instance, **kwargs):
    """Recalculate service revenue when an appliance is deleted."""
    service = instance.service
    RevenueCalculator.calculate_service_revenue(service, save=True)


@receiver(post_save, sender="services.ServiceItemUsed")
def recalculate_revenue_on_service_item_save(sender, instance, **kwargs):
    """Recalculate service revenue when a service-level item is added or updated."""
    service = instance.service
    RevenueCalculator.calculate_service_revenue(service, save=True)
    _sync_sub_tx_if_completed(service)


@receiver(post_delete, sender="services.ServiceItemUsed")
def recalculate_revenue_on_service_item_delete(sender, instance, **kwargs):
    """Recalculate service revenue when a service-level item is deleted."""
    service = instance.service
    RevenueCalculator.calculate_service_revenue(service, save=True)
    _sync_sub_tx_if_completed(service)


# ------------------------------------------------------------------
# WebSocket push for service changes
# ------------------------------------------------------------------

@receiver(post_save, sender="services.Service")
def push_service_update(sender, instance, created, **kwargs):
    from analytics.ws_utils import push_dashboard_event

    push_dashboard_event(
        "service_created" if created else "service_updated",
        {
            "service_id": instance.id,
            "status": instance.status,
            "payment_status": instance.payment_status,
        },
    )


@receiver(post_save, sender="services.ServicePayment")
def push_service_payment_update(sender, instance, created, **kwargs):
    from analytics.ws_utils import push_dashboard_event

    if created:
        push_dashboard_event("service_payment_created", {
            "service_id": instance.service_id,
        })
