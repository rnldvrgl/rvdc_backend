from django.db import models
from users.models import CustomUser
from clients.models import Client
from utils.logger import log_activity
from inventory.models import Stock
from django.db import transaction

SERVICE_TYPES = [
    ("installation", "Installation"),
    ("repair", "Repair"),
    ("cleaning", "Cleaning"),
    ("dismantle_reinstall", "Dismantle & Reinstall"),
    ("dismantle", "Dismantle Only"),
    ("checkup", "Check-up / Diagnosis"),
    ("maintenance", "Preventive Maintenance"),
    ("reinstallation", "Reinstallation"),
    ("rewind", "Rewinding Motor"),
    ("reprocess", "Reprocessing Refrigerant"),
]

STATUS_CHOICES = [
    ("pending", "Pending"),
    ("in_progress", "In Progress"),
    ("done", "Completed"),
    ("picked_up", "Picked Up"),
    ("delivered", "Delivered"),
    ("cancelled", "Cancelled"),
]

APPLIANCE_TYPES = [
    ("aircon", "Air Conditioner"),
    ("fan", "Electric Fan"),
    ("ref", "Refrigerator"),
    ("washing_machine", "Washing Machine"),
    ("water_dispenser", "Water Dispenser"),
    ("microwave", "Microwave"),
    ("freezer", "Freezer"),
]


class ServiceRequest(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    technicians = models.ManyToManyField(CustomUser, related_name="service_requests")
    appliance_type = models.CharField(max_length=30, choices=APPLIANCE_TYPES)
    brand = models.CharField(max_length=100)
    unit_type = models.CharField(max_length=100)
    service_type = models.CharField(max_length=30, choices=SERVICE_TYPES)
    previous_service_type = models.CharField(
        max_length=30, choices=SERVICE_TYPES, blank=True, null=True
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    remarks = models.TextField(blank=True, null=True)
    date_received = models.DateTimeField(auto_now_add=True)
    date_completed = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return (
            f"{self.get_appliance_type_display()} ({self.brand}) - {self.service_type}"
        )

    def save(self, *args, **kwargs):
        if self.pk:
            original = ServiceRequest.objects.get(pk=self.pk)
            changes = []

            if original.status != self.status:
                changes.append(
                    f"Status changed from '{original.status}' to '{self.status}'"
                )
            if original.service_type != self.service_type:
                changes.append(
                    f"Service type changed from '{original.service_type}' to '{self.service_type}'"
                )
            if original.previous_service_type != self.previous_service_type:
                changes.append(
                    f"Previous service type changed from '{original.previous_service_type}' to '{self.previous_service_type}'"
                )

            for change in changes:
                log_activity(
                    user=(
                        self.technicians.first() if self.technicians.exists() else None
                    ),
                    instance=self,
                    action="updated service request",
                    note=change,
                )
                ServiceStep.objects.create(
                    service_request=self, service_type=self.service_type, notes=change
                )

        super().save(*args, **kwargs)


class ServiceStep(models.Model):
    service_request = models.ForeignKey(
        ServiceRequest, on_delete=models.CASCADE, related_name="steps"
    )
    service_type = models.CharField(max_length=30, choices=SERVICE_TYPES)
    performed_on = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.service_request} - {self.service_type} on {self.performed_on}"


class ServiceRequestItem(models.Model):
    service_request = models.ForeignKey(
        ServiceRequest, on_delete=models.CASCADE, related_name="used_items"
    )
    item = models.ForeignKey("inventory.Item", on_delete=models.CASCADE)
    quantity_used = models.PositiveIntegerField()
    deducted_from_stall = models.ForeignKey(
        "inventory.Stall", on_delete=models.SET_NULL, null=True
    )
    deducted_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, related_name="item_deductions"
    )
    deducted_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):

        if not self.pk:
            with transaction.atomic():
                stock = (
                    Stock.objects.select_for_update()
                    .filter(
                        item=self.item,
                        stall=self.deducted_from_stall,
                        quantity__gte=self.quantity_used,
                        is_deleted=False,
                    )
                    .first()
                )

                if stock:
                    stock.quantity -= self.quantity_used
                    stock.save()

                    log_activity(
                        user=self.deducted_by,
                        instance=self,
                        action="deducted item",
                        note=f"Deducted {self.quantity_used} {self.item.unit_of_measure} of {self.item.name} from {self.deducted_from_stall.name}",
                    )
                else:
                    raise ValueError("Insufficient stock or invalid stall")

        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.quantity_used} {self.item.unit_of_measure} of {self.item.name} used"
        )
