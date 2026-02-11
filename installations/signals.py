from django.db.models.signals import post_delete
from django.dispatch import receiver

from services.models import Service
from installations.models import AirconUnit


@receiver(post_delete, sender=Service)
def clear_unit_installation_service(sender, instance, **kwargs):
    """When an installation service is deleted, clear the reference from units."""
    if instance.service_type == 'installation':
        AirconUnit.objects.filter(installation_service=instance).update(
            installation_service=None
        )
