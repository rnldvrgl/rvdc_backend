from django.db import models
from datetime import datetime, timedelta

from inventory.models import Item, Stock
from clients.models import Client
from users.models import CustomUser
from utils.enums import ServiceType, ServiceStatus, ApplianceStatus, ServiceMode


# ----------------------------------
# Abstract: BaseItemUsed
# ----------------------------------
class BaseItemUsed(models.Model):
    """Abstract base for any item used in a service or appliance repair."""

    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        abstract = True


# ----------------------------------
# ApplianceType
# ----------------------------------
class ApplianceType(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = "Appliance Type"
        verbose_name_plural = "Appliance Types"
        ordering = ["name"]

    def __str__(self):
        return self.name


# ----------------------------------
# Service
# ----------------------------------
class Service(models.Model):
    client = models.ForeignKey(
        Client, on_delete=models.PROTECT, related_name="services"
    )
    # The stall handling this service (main stall). This is used to
    # determine which stall should be charged for labor and for which
    # expenses/sales transactions are created when items are added to the
    # service. Keep nullable for legacy records.
    stall = models.ForeignKey(
        "inventory.Stall", on_delete=models.SET_NULL, null=True, blank=True, related_name="services"
    )
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
    estimated_duration = models.PositiveIntegerField(default=60)  # minutes
    pickup_date = models.DateField(blank=True, null=True)
    delivery_date = models.DateField(blank=True, null=True)
    status = models.CharField(
        max_length=30, choices=ServiceStatus.choices, default=ServiceStatus.IN_PROGRESS
    )
    remarks = models.TextField(blank=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.client.name} - {self.get_service_type_display()} ({self.get_service_mode_display()})"

    @property
    def total_cost(self):
        """Sum labor fees and parts for all appliances in this service."""
        appliance_costs = sum(a.labor_fee for a in self.appliances.all())
        parts_costs = sum(
            iu.item.price * iu.quantity
            for a in self.appliances.all()
            for iu in a.items_used.all()
            if iu.item and iu.item.price
        )
        return appliance_costs + parts_costs

    @property
    def scheduled_end_time(self):
        """Calculate end time using start + estimated_duration (if available)."""
        if self.scheduled_date and self.scheduled_time:
            dt = datetime.combine(self.scheduled_date, self.scheduled_time)
            return (dt + timedelta(minutes=self.estimated_duration)).time()
        return None


# ----------------------------------
# Technician Assignment
# ----------------------------------
class TechnicianAssignment(models.Model):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="technician_assignments"
    )
    appliance = models.ForeignKey(
        "ServiceAppliance",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="technician_assignments",
    )
    technician = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, limit_choices_to={"role": "technician"}
    )
    # role/type of assignment: repair, pickup (pull-out), delivery, etc.
    class AssignmentType(models.TextChoices):
        REPAIR = "repair", "Repair"
        PICKUP = "pickup", "Pick-up (Pull-Out)"
        DELIVERY = "delivery", "Delivery/Return"
        INSPECT = "inspect", "Inspect/On-site"

    assignment_type = models.CharField(
        max_length=20, choices=AssignmentType.choices, default=AssignmentType.REPAIR
    )

    # optional free-text note to capture who pulled/delivered/repaired when needed
    note = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        verbose_name = "Technician Assignment"
        verbose_name_plural = "Technician Assignments"

    def __str__(self):
        target = self.appliance or self.service
        return f"{self.technician.get_full_name()} ({self.get_assignment_type_display()}) → {target}"


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
        related_name="service_appliances",
    )
    brand = models.CharField(max_length=100, blank=True, null=True)
    model = models.CharField(max_length=100, blank=True, null=True)
    issue_reported = models.TextField(blank=True, null=True)
    diagnosis_notes = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20, choices=ApplianceStatus.choices, default=ApplianceStatus.RECEIVED
    )
    labor_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ["appliance_type__name", "brand"]

    def __str__(self):
        appliance_type = (
            self.appliance_type.name if self.appliance_type else "Unknown Type"
        )
        brand = self.brand or "Unknown Brand"
        return f"{appliance_type} ({brand})"


# ----------------------------------
# Appliance Items Used
# ----------------------------------
class ApplianceItemUsed(BaseItemUsed):
    appliance = models.ForeignKey(
        ServiceAppliance, on_delete=models.CASCADE, related_name="items_used"
    )

    class Meta:
        verbose_name = "Appliance Item Used"
        verbose_name_plural = "Appliance Items Used"

    # Which stall stock was consumed for this item (if applicable).
    # This enables tracking items taken from a sub-stall when a main stall adds
    # parts to a service. The `services.api` layer already expects a
    # `stall_stock` writable field (see serializers). Keep this nullable to
    # support cases where parts are not taken from a stall-managed stock.
    stall_stock = models.ForeignKey(
        Stock, on_delete=models.SET_NULL, null=True, blank=True, related_name="appliance_items_used"
    )

    # Link to an Expense created automatically when items are consumed from
    # another stall (main stall incurs an expense for parts sourced from
    # sub-stall). Filled by business logic when creating the transfer/expense.
    expense = models.ForeignKey(
        "expenses.Expense",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_items",
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
    changed_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.appliance} → {self.get_status_display()} @ {self.changed_at}"


class ServiceStatusHistory(models.Model):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="status_history"
    )
    status = models.CharField(max_length=30, choices=ServiceStatus.choices)
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.service} → {self.get_status_display()} @ {self.changed_at}"
