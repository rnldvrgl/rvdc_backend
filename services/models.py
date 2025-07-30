from django.db import models
from django.core.exceptions import ValidationError
import uuid

from inventory.models import Item
from clients.models import Client
from users.models import (
    CustomUser,
)  # Assumes technician users are in the custom User model
from utils.enums import (
    ServiceType,
    ServiceStatus,
    ApplianceStatus,
    ServiceMode,
    AirconType,
)

from dateutil.relativedelta import relativedelta
from django.utils import timezone


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
# Core Service Model
# ----------------------------------
class Service(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    service_type = models.CharField(max_length=30, choices=ServiceType.choices)
    service_mode = models.CharField(max_length=30, choices=ServiceMode.choices)
    related_transaction = models.ForeignKey(
        "sales.SalesTransaction", null=True, blank=True, on_delete=models.SET_NULL
    )
    description = models.TextField(blank=True)
    override_address = models.TextField(blank=True, null=True)
    override_contact_person = models.CharField(max_length=100, blank=True, null=True)
    override_contact_number = models.CharField(max_length=20, blank=True, null=True)
    scheduled_date = models.DateField(blank=True, null=True)
    scheduled_time = models.TimeField(blank=True, null=True)
    pickup_date = models.DateField(blank=True, null=True)
    delivery_date = models.DateField(blank=True, null=True)
    status = models.CharField(
        max_length=30, choices=ServiceStatus.choices, default=ServiceStatus.IN_PROGRESS
    )
    remarks = models.TextField(blank=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.client.name} - {self.get_service_type_display()} ({self.get_service_mode_display()})"


class ServiceTechnician(models.Model):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="technicians"
    )
    technician = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, limit_choices_to={"role": "technician"}
    )


class TechnicianAvailability(models.Model):
    technician = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, limit_choices_to={"role": "technician"}
    )
    date = models.DateField()
    time_start = models.TimeField()
    time_end = models.TimeField()
    is_available = models.BooleanField(default=True)

    class Meta:
        unique_together = ("technician", "date", "time_start", "time_end")

    def __str__(self):
        status = "Available" if self.is_available else "Unavailable"
        return f"{self.technician.get_full_name()} on {self.date} ({self.time_start}-{self.time_end}) - {status}"


# ----------------------------------
# Service Appliance
# ----------------------------------
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


class ApplianceTechnician(models.Model):
    appliance = models.ForeignKey(
        ServiceAppliance, on_delete=models.CASCADE, related_name="technicians"
    )
    technician = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, limit_choices_to={"role": "technician"}
    )


class ApplianceItemUsed(BaseItemUsed):
    appliance = models.ForeignKey(
        ServiceAppliance, on_delete=models.CASCADE, related_name="items_used"
    )


# ----------------------------------
# Status Histories
# ----------------------------------
class ApplianceStatusHistory(models.Model):
    appliance = models.ForeignKey(
        ServiceAppliance,
        on_delete=models.CASCADE,
        related_name="appliance_status_history",
    )
    status = models.CharField(max_length=30, choices=ApplianceStatus.choices)
    changed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.appliance} → {self.get_status_display()} @ {self.changed_at}"


class ServiceStatusHistory(models.Model):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="service_status_history"
    )
    status = models.CharField(max_length=30, choices=ServiceStatus.choices)
    changed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.service} → {self.get_status_display()} @ {self.changed_at}"
