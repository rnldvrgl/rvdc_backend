from django.db import models
from django.core.exceptions import ValidationError
import uuid

from inventory.models import Item, AirconUnit
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
# Aircon Installation
# ----------------------------------
class AirconBrand(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class AirconModel(models.Model):
    brand = models.ForeignKey(AirconBrand, on_delete=models.CASCADE)
    model_name = models.CharField(max_length=100)
    retail_price = models.DecimalField(max_digits=10, decimal_places=2)

    aircon_type = models.CharField(
        max_length=30,
        choices=AirconType.choices,
        default=AirconType.WINDOW,
    )

    class Meta:
        unique_together = ("brand", "model_name")

    def __str__(self):
        return f"{self.brand.name} {self.model_name} ({self.get_aircon_type_display()})"


class AirconInstallation(models.Model):
    service = models.OneToOneField(
        Service, on_delete=models.CASCADE, related_name="aircon_installation"
    )
    notes = models.TextField(blank=True, null=True)

    def clean(self):
        if self.service.service_type != ServiceType.INSTALLATION:
            raise ValidationError(
                "AirconInstallation must be linked to an INSTALLATION service."
            )

    def __str__(self):
        return f"Installation for {self.service.client.name}"


class AirconUnit(models.Model):
    aircon_model = models.ForeignKey(AirconModel, on_delete=models.PROTECT)
    serial_number = models.CharField(max_length=100, unique=True)

    sale = models.ForeignKey(
        "sales.SalesTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="aircon_units_sold",
    )
    installation = models.OneToOneField(
        AirconInstallation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="aircon_unit",
    )

    warranty_start_date = models.DateField(blank=True, null=True)
    warranty_period_months = models.PositiveIntegerField(default=12)

    free_cleaning_redeemed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.installation:
            related_tx = self.installation.service.related_transaction
            if related_tx and self.sale != related_tx:
                raise ValidationError(
                    {
                        "sale": "The sale must match the transaction linked to the installation."
                    }
                )

        if self.installation and not self.sale:
            raise ValidationError({"sale": "Installed units must have a sale."})

        if self.warranty_start_date and not self.sale:
            raise ValidationError(
                {
                    "warranty_start_date": "Cannot set warranty start date without a sale."
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()

        if not self.warranty_start_date:
            sale_date = self.sale.created_at.date() if self.sale else None

            if sale_date:
                self.warranty_start_date = sale_date

        super().save(*args, **kwargs)

    @property
    def warranty_end_date(self):
        if self.warranty_start_date:
            return self.warranty_start_date + relativedelta(
                months=self.warranty_period_months
            )
        return None

    @property
    def is_under_warranty(self):
        if self.warranty_start_date:
            today = timezone.now().date()
            return today <= self.warranty_end_date
        return False

    def __str__(self):
        return f"{self.aircon_model} (SN: {self.serial_number})"

    @property
    def warranty_status(self):
        if not self.warranty_start_date:
            return "No Warranty"
        today = timezone.now().date()
        if today <= self.warranty_end_date:
            return "Under Warranty"
        return "Expired"

    @property
    def warranty_days_left(self):
        if self.is_under_warranty:
            return (self.warranty_end_date - timezone.now().date()).days
        return 0


class InstalledAirconUnit(models.Model):
    installation = models.ForeignKey(
        AirconInstallation, on_delete=models.CASCADE, related_name="units"
    )
    source = models.CharField(
        max_length=30,
        choices=[
            ("inventory", "From Inventory"),
            ("client_provided", "Client Provided"),
        ],
    )
    unit = models.OneToOneField(
        AirconUnit, on_delete=models.SET_NULL, null=True, blank=True
    )
    notes = models.TextField(blank=True, null=True)

    def clean(self):
        if self.source == "inventory" and not self.unit:
            raise ValidationError(
                "Aircon unit must be set for inventory-based installations."
            )

        if self.source == "client_provided" and self.unit:
            raise ValidationError(
                "Client-provided units should not be linked to an AirconUnit record."
            )

        if (
            self.unit
            and self.unit.installation
            and self.unit.installation != self.installation
        ):
            raise ValidationError(
                "This Aircon Unit is already linked to another installation."
            )

        if self.unit and self.unit.sale is None and self.source != "client_provided":
            raise ValidationError("Units from inventory must have a sale linked.")

    def __str__(self):
        if self.unit:
            return f"{self.unit} ({self.source})"
        return f"Client-provided unit ({self.source})"


class AirconItemUsed(models.Model):
    installation = models.ForeignKey(
        AirconInstallation, on_delete=models.CASCADE, related_name="items_used"
    )
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True)
    total_quantity_used = models.PositiveIntegerField()
    free_quantity = models.PositiveIntegerField(default=0)

    def clean(self):
        if self.total_quantity_used < self.free_quantity:
            raise ValidationError("Free quantity cannot exceed total quantity used.")
        if self.installation.source == "client_provided" and self.free_quantity > 0:
            raise ValidationError(
                "Free copper tube not allowed if unit is client provided."
            )

    @property
    def payable_quantity(self):
        return max(self.total_quantity_used - self.free_quantity, 0)

    def __str__(self):
        return f"{self.item.name} - {self.total_quantity_used}ft (Free: {self.free_quantity})"


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
        User, on_delete=models.CASCADE, limit_choices_to={"role": "technician"}
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
        ServiceAppliance, on_delete=models.CASCADE, related_name="status_history"
    )
    status = models.CharField(max_length=30, choices=ApplianceStatus.choices)
    changed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.appliance} → {self.get_status_display()} @ {self.changed_at}"


class ServiceStatusHistory(models.Model):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="status_history"
    )
    status = models.CharField(max_length=30, choices=ServiceStatus.choices)
    changed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.service} → {self.get_status_display()} @ {self.changed_at}"


# ----------------------------------
# Motor Rewind
# ----------------------------------
class MotorRewind(models.Model):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="motor_rewinds"
    )
    appliance_type = models.ForeignKey(
        ApplianceType, on_delete=models.SET_NULL, null=True
    )
    quantity = models.PositiveIntegerField(default=1)
    labor_fee = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.quantity} x {self.appliance_type.name if self.appliance_type else 'Motor'} Rewind"


class MotorRewindTechnician(models.Model):
    motor_rewind = models.ForeignKey(
        MotorRewind, on_delete=models.CASCADE, related_name="technicians"
    )
    technician = models.ForeignKey(
        User, on_delete=models.CASCADE, limit_choices_to={"role": "technician"}
    )
