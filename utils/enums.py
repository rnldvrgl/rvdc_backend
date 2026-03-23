from django.db import models
from django.utils.translation import gettext_lazy as _


class AirconType(models.TextChoices):
    WINDOW = "window", _("Window Type")
    SPLIT = "split", _("Split Type")
    FLOOR_MOUNTED = "floor_mounted", _("Floor Mounted")
    CASSETTE = "cassette", _("Cassette Type")
    PORTABLE = "portable", _("Portable")
    CENTRALIZED = "centralized", _("Centralized")


class HorsePower(models.TextChoices):
    HP_0_5 = "0.5", _("0.5 HP (10-11 sqm)")
    HP_0_75 = "0.75", _("0.75 HP (10-17 sqm)")
    HP_0_8 = "0.8", _("0.8 HP (12-18 sqm)")
    HP_1_0 = "1.0", _("1.0 HP (15-22 sqm)")
    HP_1_5 = "1.5", _("1.5 HP (19-27 sqm)")
    HP_2_0 = "2.0", _("2.0 HP (23-40 sqm)")
    HP_2_5 = "2.5", _("2.5 HP (up to 54 sqm)")
    HP_3_0 = "3.0", _("3.0 HP (45-65 sqm)")
    HP_4_0 = "4.0", _("4.0 HP (60-85 sqm)")
    HP_5_0 = "5.0", _("5.0 HP (80-110 sqm)")
    HP_7_5 = "7.5", _("7.5 HP (110-160 sqm)")
    HP_10_0 = "10.0", _("10.0 HP (160-220 sqm)")


class ServiceType(models.TextChoices):
    REPAIR = "repair", _("Repair")
    DISMANTLE = "dismantle", _("Dismantle")
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
    PENDING = "pending", _("Pending")
    COMPLETED = "completed", _("Completed")
    CANCELLED = "cancelled", _("Cancelled")


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
    PORAC_BANK = "Porac Bank", "Porac Bank"


class CollectionType(models.TextChoices):
    PICKED_UP = "picked_up", "Picked Up by Staff"
    CLIENT_DELIVERED = "client_delivered", "Delivered by Client"


class ChequeStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    DEPOSITED = "deposited", "Deposited"
    ENCASHED = "encashed", "Encashed"
    RETURNED = "returned", "Returned"
    BOUNCED = "bounced", "Bounced"
    CANCELLED = "cancelled", "Cancelled"
