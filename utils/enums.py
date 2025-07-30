from django.db import models
from django.utils.translation import gettext_lazy as _


class AirconType(models.TextChoices):
    WINDOW = "window", _("Window Type")
    SPLIT = "split", _("Split Type")
    FLOOR_MOUNTED = "floor_mounted", _("Floor Mounted")
    CASSETTE = "cassette", _("Cassette Type")
    PORTABLE = "portable", _("Portable")
    CENTRALIZED = "centralized", _("Centralized")
    OTHERS = "others", _("Others")


class ServiceType(models.TextChoices):
    REPAIR = "repair", _("Repair")
    INSTALLATION = "installation", _("Installation")
    MOTOR_REWIND = "motor_rewind", _("Motor Rewind")
    CHECK_UP = "check_up", _("Check-up")
    CLEANING = "cleaning", _("Cleaning")


class ServiceStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    IN_PROGRESS = "in_progress", _("In Progress")
    ON_HOLD = "on_hold", _("On Hold (Waiting for Parts)")
    COMPLETED = "completed", _("Completed")
    CANCELLED = "cancelled", _("Cancelled")


class ApplianceStatus(models.TextChoices):
    RECEIVED = "received", _("Received")
    DIAGNOSED = "diagnosed", _("Diagnosed")
    WAITING_PARTS = "waiting_parts", _("Waiting for Parts")
    UNDER_REPAIR = "under_repair", _("Under Repair")
    FIXED = "fixed", _("Fixed")
    DELIVERED = "delivered", _("Delivered")
    CANCELLED = "cancelled", _("Cancelled")


class ServiceMode(models.TextChoices):
    IN_SHOP = "in_shop", _("In-Shop")
    HOME_SERVICE = "home_service", _("Home Service")
    PICKUP = "pickup", _("Pickup and Return")
