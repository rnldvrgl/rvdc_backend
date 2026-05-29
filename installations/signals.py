from django.db.models.signals import post_delete
from django.dispatch import receiver

from services.models import Service
from installations.models import AirconUnit


@receiver(post_delete, sender=Service)
def clear_unit_installation_service(sender, instance, **kwargs):
    """When an installation service is deleted, clear the unit linkage and reservation."""
    if instance.service_type == 'installation':
        units = AirconUnit.objects.filter(installation_service=instance)
        units.update(
            installation_service=None,
            reserved_by=None,
            reserved_at=None,
        )
        units.filter(sale__isnull=True).update(is_sold=False)
