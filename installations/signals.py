from django.db.models.signals import post_delete
from django.dispatch import receiver

from installations.models import AirconInstallation


@receiver(post_delete, sender=AirconInstallation)
def clear_unit_installation(sender, instance, **kwargs):
    if hasattr(instance, "aircon_unit"):
        unit = instance.aircon_unit
        unit.installation = None
        unit.save(update_fields=["installation"])
