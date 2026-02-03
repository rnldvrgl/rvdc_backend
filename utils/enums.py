from django.db import models
from django.utils.translation import gettext_lazy as _


class AirconType(models.TextChoices):
    WINDOW = "window", _("Window Type")
    SPLIT = "split", _("Split Type")
    FLOOR_MOUNTED = "floor_mounted", _("Floor Mounted")
    CASSETTE = "cassette", _("Cassette Type")
    PORTABLE = "portable", _("Portable")
    CENTRALIZED = "centralized", _("Centralized")


class ServiceType(models.TextChoices):
    REPAIR = "repair", _("Repair")
    INSTALLATION = "installation", _("Installation")
    MOTOR_REWIND = "motor_rewind", _("Motor Rewind")
    INSPECTION = "inspection", _("Inspection")
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
    IN_REPAIR = "in_repair", _("In Repair")
    COMPLETED = "completed", _("Completed")
    READY_FOR_PICKUP = "ready_for_pickup", _("Ready for Pickup")
    DELIVERED = "delivered", _("Delivered")


class ServiceMode(models.TextChoices):
    CARRY_IN = "carry_in", _("Carry-In")
    HOME_SERVICE = "home_service", _("Home Service")
    PULL_OUT = "pull_out", _("Pull-Out")


class BankChoices(models.TextChoices):
    BPI = "BPI", "BPI"
    BDO = "BDO", "BDO"
    METROBANK = "Metrobank", "Metrobank"
    LANDBANK = "Landbank", "Landbank"
    SECURITY_BANK = "Security Bank", "Security Bank"
    UNIONBANK = "UnionBank", "UnionBank"
    RCBC = "RCBC", "RCBC"
    PNB = "PNB", "PNB"
    EASTWEST_BANK = "EastWestBank", "EastWest Bank"
    CHINA_BANK = "ChinaBank", "China Bank"
    MAYBANK_PH = "Maybank Philippines", "Maybank Philippines"


class CollectionType(models.TextChoices):
    PICKED_UP = "picked_up", "Picked Up by Staff"
    CLIENT_DELIVERED = "client_delivered", "Delivered by Client"


class ChequeStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    DEPOSITED = "deposited", "Deposited"
    ENCAHSED = "encashed", "Encashed"
    RETURNED = "returned", "Returned"
    BOUNCED = "bounced", "Bounced"
    CANCELLED = "cancelled", "Cancelled"
