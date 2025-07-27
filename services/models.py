import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _

from clients.models import Client
from inventory.models import Item, ApplianceType
from users.models import CustomUser
from sales.models import SalesTransaction


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


class Service(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    client = models.ForeignKey(
        Client, on_delete=models.SET_NULL, null=True, related_name="services"
    )

    service_type = models.CharField(
        max_length=20, choices=ServiceType.choices, default=ServiceType.REPAIR
    )
    mode = models.CharField(
        max_length=30, choices=ServiceMode.choices, default=ServiceMode.IN_SHOP
    )

    previous_service = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="followup_services",
        help_text="Link to previous service (e.g., a check-up before repair)",
    )

    was_converted_to_repair = models.BooleanField(
        default=False,
        help_text="Set to True if a follow-up repair was created for a check-up",
    )

    status = models.CharField(
        max_length=20, choices=ServiceStatus.choices, default=ServiceStatus.PENDING
    )

    assigned_technicians = models.ManyToManyField(
        CustomUser,
        blank=True,
        limit_choices_to={"role": "technician"},
        related_name="assigned_services",
    )

    remarks = models.TextField(blank=True, null=True)
    related_transaction = models.ForeignKey(
        SalesTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Auto-linked if transaction is created from this service",
        related_name="linked_services",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.service_type.title()} for {self.client}"


class HomeServiceSchedule(models.Model):
    service = models.OneToOneField(
        Service, on_delete=models.CASCADE, related_name="home_service_schedule"
    )
    scheduled_date = models.DateField()
    scheduled_time = models.TimeField(blank=True, null=True)

    override_address = models.TextField(blank=True, null=True)
    override_contact_person = models.CharField(max_length=100, blank=True, null=True)
    override_contact_number = models.CharField(max_length=20, blank=True, null=True)

    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def client(self):
        return self.service.client

    def __str__(self):
        return f"Home Service for {self.client} on {self.scheduled_date}"


class ServiceAppliance(models.Model):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="appliances"
    )
    appliance_type = models.ForeignKey(
        ApplianceType,
        on_delete=models.SET_NULL,
        null=True,
        related_name="used_in_services",
    )
    brand = models.CharField(max_length=100, blank=True, null=True)
    model = models.CharField(max_length=100, blank=True, null=True)

    issue_reported = models.TextField(blank=True, null=True)
    diagnosis_notes = models.TextField(blank=True, null=True)

    status = models.CharField(
        max_length=20, choices=ApplianceStatus.choices, default=ApplianceStatus.RECEIVED
    )

    labor_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.appliance_type.name if self.appliance_type else 'Appliance'} ({self.brand or 'Unknown'})"


class ApplianceItemUsed(models.Model):
    appliance = models.ForeignKey(
        ServiceAppliance, on_delete=models.CASCADE, related_name="items_used"
    )
    item = models.ForeignKey(
        Item, on_delete=models.SET_NULL, null=True, related_name="used_in_appliances"
    )
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.quantity} x {self.item.name}"


class AirconInstallation(models.Model):
    service = models.OneToOneField(
        Service, on_delete=models.CASCADE, related_name="aircon_installation"
    )
    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Aircon Installation for {self.service.client}"


class AirconItemUsed(models.Model):
    installation = models.ForeignKey(
        AirconInstallation, on_delete=models.CASCADE, related_name="items_used"
    )
    item = models.ForeignKey(
        Item, on_delete=models.SET_NULL, null=True, related_name="used_in_installations"
    )
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.quantity} x {self.item.name}"


class MotorRewind(models.Model):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="motor_rewinds"
    )
    appliance_type = models.ForeignKey(
        ApplianceType,
        on_delete=models.SET_NULL,
        null=True,
        help_text="Type of motor (e.g., Electric Fan, Aircon Compressor)",
        related_name="used_in_motor_rewinds",
    )
    quantity = models.PositiveIntegerField(default=1)
    labor_fee = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True, null=True)

    related_transaction = models.ForeignKey(
        SalesTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Optional transaction for billing this motor rewind",
        related_name="motor_rewind_services",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.quantity} x {self.appliance_type.name if self.appliance_type else 'Motor'} Rewind"


class ServiceStatusHistory(models.Model):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="status_history"
    )
    status = models.CharField(max_length=20, choices=ServiceStatus.choices)
    changed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.service} → {self.status} @ {self.changed_at}"


class ApplianceStatusHistory(models.Model):
    appliance = models.ForeignKey(
        ServiceAppliance, on_delete=models.CASCADE, related_name="status_history"
    )
    status = models.CharField(max_length=20, choices=ApplianceStatus.choices)
    changed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.appliance} → {self.status} @ {self.changed_at}"
