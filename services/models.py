from django.db import models
from users.models import CustomUser
from clients.models import Client

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
    technician = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
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

    def save(self, *args, **kwargs):
        if not self.pk:
            from inventory.models import Stock

            stock = Stock.objects.filter(
                item=self.item, quantity__gte=self.quantity_used, is_deleted=False
            ).first()
            if stock:
                stock.quantity -= self.quantity_used
                stock.save()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.quantity_used} {self.item.unit_of_measure} of {self.item.name} used"
        )
