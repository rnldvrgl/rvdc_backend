"""
Signals for automatic revenue recalculation when service data changes.
"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from services.business_logic import RevenueCalculator
from services.models import ApplianceItemUsed, ServiceAppliance


@receiver(post_save, sender=ApplianceItemUsed)
def recalculate_revenue_on_item_save(sender, instance, **kwargs):
    """Recalculate service revenue when an item is added or updated."""
    service = instance.appliance.service
    RevenueCalculator.calculate_service_revenue(service, save=True)


@receiver(post_delete, sender=ApplianceItemUsed)
def recalculate_revenue_on_item_delete(sender, instance, **kwargs):
    """Recalculate service revenue when an item is deleted."""
    service = instance.appliance.service
    RevenueCalculator.calculate_service_revenue(service, save=True)


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
