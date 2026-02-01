from clients.models import Client
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from inventory.models import Item, Stock
from users.models import CustomUser
from utils.enums import ApplianceStatus, ServiceMode, ServiceStatus, ServiceType


# ----------------------------------
# Payment Enums
# ----------------------------------
class PaymentType(models.TextChoices):
    CASH = "cash", _("Cash")
    GCASH = "gcash", _("GCash")
    CREDIT = "credit", _("Credit")
    DEBIT = "debit", _("Debit")
    CHEQUE = "cheque", _("Cheque")


class PaymentStatus(models.TextChoices):
    UNPAID = "unpaid", _("Unpaid")
    PARTIAL = "partial", _("Partial")
    PAID = "paid", _("Paid")
    REFUNDED = "refunded", _("Refunded")


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
        "inventory.Stall",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="services",
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

    # Pull-out service fields (scheduling is handled by Schedule model)
    pickup_date = models.DateField(
        blank=True,
        null=True,
        help_text="Pickup date for pull-out services (set at service creation)"
    )
    delivery_date = models.DateField(
        blank=True,
        null=True,
        help_text="Delivery date for pull-out services (set when scheduling delivery after repair)"
    )

    # For carry-in services: track when unit was received
    received_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When customer dropped off unit (carry-in services)"
    )

    status = models.CharField(
        max_length=30, choices=ServiceStatus.choices, default=ServiceStatus.IN_PROGRESS
    )
    remarks = models.TextField(blank=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Revenue tracking for two-stall architecture
    main_stall_revenue = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Revenue attributed to Main stall (labor + aircon units)",
    )
    sub_stall_revenue = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Revenue attributed to Sub stall (parts)",
    )
    total_revenue = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Total service revenue (main + sub)",
    )

    # Payment tracking
    payment_status = models.CharField(
        max_length=10,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
        help_text="Payment status of this service",
    )

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        """Validate service data"""
        super().clean()

        # Motor Rewind services must use carry-in mode
        if self.service_type == ServiceType.MOTOR_REWIND:
            if self.service_mode != ServiceMode.CARRY_IN:
                raise ValidationError({
                    'service_mode': 'Motor Rewind services must use Carry-In mode.'
                })

        # Pull-out services must have pickup_date
        if self.service_mode == ServiceMode.PULL_OUT:
            if not self.pickup_date:
                raise ValidationError({
                    'pickup_date': 'Pull-out services must have a pickup date.'
                })

    def save(self, *args, **kwargs):
        """Override save to run validation"""
        if kwargs.pop('skip_validation', False):
            super().save(*args, **kwargs)
        else:
            self.full_clean()
            super().save(*args, **kwargs)

    def __str__(self):

        client_label = getattr(self.client, "name", None)
        if not client_label:
            client_label = str(self.client) if self.client is not None else "Unknown Client"
        return f"{client_label} - {self.get_service_type_display()} ({self.get_service_mode_display()})"


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
    def total_paid(self):
        """Total amount paid for this service across all payments."""
        return sum(payment.amount for payment in self.payments.all())

    @property
    def balance_due(self):
        """Remaining balance for this service."""
        return max(self.total_revenue - self.total_paid, 0)

    def update_payment_status(self):
        """Update payment status based on total paid vs total revenue."""
        total = self.total_revenue
        paid = self.total_paid

        if paid == 0:
            self.payment_status = PaymentStatus.UNPAID
        elif paid < total:
            self.payment_status = PaymentStatus.PARTIAL
        else:
            self.payment_status = PaymentStatus.PAID

        self.save(update_fields=["payment_status"])


# ----------------------------------
# Service Payment
# ----------------------------------
class ServicePayment(models.Model):
    """Payment record for a service."""

    service = models.ForeignKey(
        Service, related_name="payments", on_delete=models.CASCADE
    )
    payment_type = models.CharField(max_length=10, choices=PaymentType.choices)
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Amount paid in this transaction",
    )
    payment_date = models.DateTimeField(default=timezone.now)
    received_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_payments_received",
        help_text="User who received this payment",
    )
    notes = models.TextField(
        blank=True, help_text="Additional notes about this payment"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-payment_date"]
        verbose_name = "Service Payment"
        verbose_name_plural = "Service Payments"

    def __str__(self):
        return f"{self.payment_type}: ₱{self.amount} for Service #{self.service.id}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Automatically update the related service's payment status
        self.service.update_payment_status()


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
    labor_is_free = models.BooleanField(
        default=False, help_text="Mark labor for this appliance as free."
    )
    # Promo support - track original amount before discount
    labor_original_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Original labor fee before promo discount (e.g., free installation)",
    )

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
        Stock,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appliance_items_used",
    )
    is_free = models.BooleanField(
        default=False, help_text="Mark this part as free to the customer."
    )

    # Promo support - track free quantity for promotions (e.g., first 10ft copper tube free)
    free_quantity = models.PositiveIntegerField(
        default=0,
        help_text="Quantity given free as part of promotion",
    )
    promo_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Name of applied promotion (e.g., 'Free 10ft Copper Tube Promo')",
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
