from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
import uuid

from inventory.models import Item
from clients.models import Client
from sales.models import SalesTransaction
from utils.enums import (
    ServiceType,
    ServiceStatus,
    ApplianceStatus,
)


# ----------------------------------
# BaseItemUsed (Abstract)
# ----------------------------------
class BaseItemUsed(models.Model):
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        abstract = True


# ----------------------------------
# ApplianceType
# ----------------------------------
class ApplianceType(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


# ----------------------------------
# Service
# ----------------------------------
class Service(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    service_type = models.CharField(max_length=30, choices=ServiceType.choices)
    related_transaction = models.ForeignKey(
        SalesTransaction, null=True, blank=True, on_delete=models.SET_NULL
    )
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=30, choices=ServiceStatus.choices, default=ServiceStatus.ONGOING
    )
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.client.name} - {self.get_service_type_display()}"


# ----------------------------------
# HomeServiceSchedule
# ----------------------------------
class HomeServiceSchedule(models.Model):
    service = models.OneToOneField(
        Service, on_delete=models.CASCADE, related_name="home_service_schedule"
    )
    scheduled_date = models.DateField()
    scheduled_time = models.TimeField(blank=True, null=True)

    # Overrides in case home service is not at client's saved address/contact
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
        return f"Home Service for {self.client.name} on {self.scheduled_date}"


# ----------------------------------
# AirconInstallation
# ----------------------------------
class AirconInstallation(models.Model):
    service = models.OneToOneField(
        Service,
        on_delete=models.CASCADE,
        related_name="aircon_installation",
    )
    source = models.CharField(
        max_length=30,
        choices=[
            ("inventory", "From Inventory"),
            ("client_provided", "Client Provided"),
        ],
    )

    class Meta:
        verbose_name = "Aircon Installation"
        verbose_name_plural = "Aircon Installations"

    def clean(self):
        # Ensure this is only linked to INSTALLATION-type services
        if self.service and self.service.service_type != ServiceType.INSTALLATION:
            raise ValidationError(
                "AirconInstallation must be linked to an INSTALLATION service."
            )

    def __str__(self):
        return f"Installation for {self.service}"


# ----------------------------------
# AirconItemUsed
# ----------------------------------
class AirconItemUsed(models.Model):
    installation = models.ForeignKey(
        AirconInstallation, on_delete=models.CASCADE, related_name="items_used"
    )
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True)

    # Total quantity used in feet (manual input)
    total_quantity_used = models.PositiveIntegerField()

    # Free copper feet manually input (up to 10ft per size)
    free_quantity = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Aircon Item Used"
        verbose_name_plural = "Aircon Items Used"

    def clean(self):
        if self.total_quantity_used < self.free_quantity:
            raise ValidationError("Free quantity cannot exceed total quantity used.")

        # Free allowance not allowed if unit was provided by the client
        if self.installation.source == "client_provided" and self.free_quantity > 0:
            raise ValidationError(
                "Free copper tube not allowed if unit is client provided."
            )

    @property
    def payable_quantity(self):
        # Payable = total - free
        return max(self.total_quantity_used - self.free_quantity, 0)

    def __str__(self):
        return f"{self.item.name} - {self.total_quantity_used}ft (Free: {self.free_quantity})"


# ----------------------------------
# ApplianceStatusHistory
# ----------------------------------
class ApplianceStatusHistory(models.Model):
    appliance = models.ForeignKey(
        "ServiceAppliance", on_delete=models.CASCADE, related_name="status_history"
    )
    status = models.CharField(max_length=30, choices=ApplianceStatus.choices)
    changed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.appliance} → {self.get_status_display()} @ {self.changed_at}"


# ----------------------------------
# ServiceAppliance
# ----------------------------------
class ServiceAppliance(models.Model):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="appliances"
    )

    # Optional FK to ApplianceType if you're using a separate model
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
        max_length=20,
        choices=ApplianceStatus.choices,
        default=ApplianceStatus.RECEIVED,
    )

    labor_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.appliance_type.name if self.appliance_type else 'Appliance'} ({self.brand or 'Unknown'})"


# ----------------------------------
# ApplianceItemUsed
# ----------------------------------
class ApplianceItemUsed(BaseItemUsed):
    appliance = models.ForeignKey(
        ServiceAppliance, on_delete=models.CASCADE, related_name="items_used"
    )


# ----------------------------------
# ServiceStatusHistory
# ----------------------------------
class ServiceStatusHistory(models.Model):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="status_history"
    )
    status = models.CharField(max_length=30, choices=ServiceStatus.choices)
    changed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.service} → {self.get_status_display()} @ {self.changed_at}"
