from django.db import models, transaction
from users.models import CustomUser
from utils.logger import log_activity
from clients.models import Client
from sales.models import SalesTransaction

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

PAYMENT_METHODS = [
    ("cash", "Cash"),
    ("gcash", "GCash"),
    ("bank_transfer", "Bank Transfer"),
    ("card", "Credit/Debit Card"),
]

PAYMENT_STATUS = [
    ("unpaid", "Unpaid"),
    ("partial", "Partially Paid"),
    ("paid", "Fully Paid"),
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
    total_payment = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHODS, blank=True, null=True
    )
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS, default="unpaid"
    )
    payment_date = models.DateTimeField(blank=True, null=True)
    final_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    sales_transaction = models.OneToOneField(
        "sales.SalesTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_request",
    )
    sales_transaction = models.OneToOneField(
        SalesTransaction, on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self):
        return (
            f"{self.get_appliance_type_display()} ({self.brand}) - {self.service_type}"
        )

    def save(self, *args, **kwargs):
        user = kwargs.pop("user", None)

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
                    user=user,
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
        from inventory.models import Stock

        if not self.pk:
            # First-time creation: Deduct stock
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

                if not stock:
                    raise ValueError(
                        "Insufficient stock or invalid stall for deduction."
                    )

                stock.quantity -= self.quantity_used
                stock.save()
                super().save(*args, **kwargs)

                log_activity(
                    user=self.deducted_by,
                    instance=self,
                    action="deducted item",
                    note=f"Deducted {self.quantity_used} {self.item.unit_of_measure} of {self.item.name} from {self.deducted_from_stall.name}",
                )
                return

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from inventory.models import Stock

        with transaction.atomic():
            try:
                stock = Stock.objects.select_for_update().get(
                    item=self.item,
                    stall=self.deducted_from_stall,
                    is_deleted=False,
                )
                stock.quantity += self.quantity_used
                stock.save()
            except Stock.DoesNotExist:
                raise ValueError(
                    f"Cannot restore stock: Stock for item '{self.item}' in stall '{self.deducted_from_stall}' does not exist."
                )

            log_activity(
                user=self.deducted_by,
                instance=self,
                action="restored item",
                note=f"Restored {self.quantity_used} {self.item.unit_of_measure} of {self.item.name} to {self.deducted_from_stall.name} (due to item deletion)",
            )

        super().delete(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.quantity_used} {self.item.unit_of_measure} of {self.item.name} used"
        )
