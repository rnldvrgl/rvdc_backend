from clients.models import Client
from decimal import Decimal, ROUND_HALF_UP
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
    NOT_APPLICABLE = "n/a", _("N/A (Complementary)")


# ----------------------------------
# Abstract: BaseItemUsed
# ----------------------------------
class BaseItemUsed(models.Model):
    """Abstract base for any item used in a service or appliance repair."""

    STOCK_REQUEST_STATUS_CHOICES = [
        ("pending", "Pending Stock Request"),
        ("approved", "Stock Request Approved"),
        ("declined", "Stock Request Declined"),
    ]

    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True)
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
        help_text="Quantity used (supports decimals for kg, ft, etc.).",
    )
    stock_request_status = models.CharField(
        max_length=10,
        choices=STOCK_REQUEST_STATUS_CHOICES,
        null=True,
        blank=True,
        help_text="Set when item was added with insufficient stock. Null means no stock request needed.",
    )

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
    related_sub_transaction = models.ForeignKey(
        "sales.SalesTransaction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sub_stall_services",
        help_text="Sub stall sales transaction for parts revenue tracking",
    )
    description = models.TextField(blank=True)
    override_address = models.TextField(blank=True, null=True)
    override_contact_person = models.CharField(max_length=100, blank=True, null=True)
    override_contact_number = models.CharField(max_length=20, blank=True, null=True)

    # Pull-out service fields (scheduling is handled by Schedule model)
    pickup_date = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Pickup date and time for pull-out services (set at service creation)"
    )
    delivery_date = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Delivery date and time for pull-out services (set when scheduling delivery after repair)"
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

    # Cancellation tracking (for incomplete services)
    cancellation_reason = models.TextField(
        blank=True,
        null=True,
        help_text="Reason for service cancellation"
    )
    cancellation_date = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When service was cancelled"
    )
    
    # Refund tracking (for completed services)
    total_refunded = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Total amount refunded for this completed service"
    )
    last_refund_date = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Date of most recent refund"
    )
    
    # Service-level discounts
    service_discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Fixed discount amount for entire service"
    )
    service_discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Percentage discount for entire service (0.00 - 100.00)"
    )
    discount_reason = models.CharField(
        max_length=200,
        blank=True,
        help_text="Reason for discount (e.g., 'Senior Citizen', 'Loyalty Discount')"
    )
    
    # Complementary service tracking (free services: warranty, goodwill, etc.)
    is_complementary = models.BooleanField(
        default=False,
        help_text="Mark as complementary for free services (warranty, goodwill, promotional)"
    )
    complementary_reason = models.CharField(
        max_length=200,
        blank=True,
        help_text="Reason for complementary service (e.g., 'Warranty', 'Goodwill', 'Promotional')"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"], name="service_status_idx"),
            models.Index(fields=["payment_status"], name="service_payment_status_idx"),
            models.Index(fields=["created_at"], name="service_created_at_idx"),
            models.Index(fields=["service_type"], name="service_type_idx"),
            models.Index(fields=["is_deleted"], name="service_is_deleted_idx"),
        ]

    # Soft-delete fields
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

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
        """Sum labor fees and parts for all appliances + service-level items."""
        appliance_costs = sum(a.labor_fee for a in self.appliances.all())
        parts_costs = sum(
            iu.item.price * iu.quantity
            for a in self.appliances.all()
            for iu in a.items_used.all()
            if iu.item and iu.item.price
        )
        service_items_costs = sum(
            si.item.price * si.quantity
            for si in self.service_items.all()
            if si.item and si.item.price
        )
        return appliance_costs + parts_costs + service_items_costs

    @property
    def total_paid(self):
        """Total amount paid for this service across all payments."""
        return sum(payment.amount for payment in self.payments.all())

    @property
    def balance_due(self):
        """Remaining balance for this service, accounting for refunds."""
        net_paid = self.total_paid - (self.total_refunded or 0)
        return max(self.total_revenue - net_paid, 0)
    
    @property
    def net_revenue(self):
        """Revenue after refunds"""
        return self.total_paid - (self.total_refunded or 0)
    
    @property
    def has_refunds(self):
        """Check if service has any refunds"""
        return (self.total_refunded or 0) > 0

    def update_payment_status(self):
        """Update payment status based on net paid (paid minus refunded) vs total revenue."""
        from django.db.models import Sum

        # Complementary services don't require payment
        if self.is_complementary:
            self.payment_status = PaymentStatus.NOT_APPLICABLE
            self.save(update_fields=["payment_status"], skip_validation=True)
            return

        # Refresh total_revenue from DB to avoid stale in-memory values
        self.refresh_from_db(fields=["total_revenue", "total_refunded"])
        total = self.total_revenue

        # Use DB aggregate to bypass prefetch cache and get accurate total
        paid_result = ServicePayment.objects.filter(service_id=self.pk).aggregate(
            total=Sum("amount")
        )
        total_paid = paid_result["total"] or Decimal("0")
        net_paid = total_paid - (self.total_refunded or Decimal("0"))

        if net_paid <= 0:
            self.payment_status = PaymentStatus.UNPAID
        elif net_paid < total:
            self.payment_status = PaymentStatus.PARTIAL
        else:
            self.payment_status = PaymentStatus.PAID

        self.save(update_fields=["payment_status"], skip_validation=True)


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
    cheque_collection = models.ForeignKey(
        "receivables.ChequeCollection",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_payments",
        help_text="Linked cheque collection if payment type is cheque",
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
        # Fetch a fresh Service instance to avoid stale prefetch cache
        from services.models import Service
        fresh_service = Service.objects.get(pk=self.service_id)
        fresh_service.update_payment_status()


# ----------------------------------
# Service Refund
# ----------------------------------
class ServiceRefund(models.Model):
    """Track refunds for completed services"""
    
    REFUND_TYPE_CHOICES = [
        ('full', 'Full Refund'),
        ('partial', 'Partial Refund'),
    ]
    
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='refunds'
    )
    refund_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Amount refunded"
    )
    refund_type = models.CharField(
        max_length=10,
        choices=REFUND_TYPE_CHOICES,
        default='partial'
    )
    reason = models.TextField(help_text="Reason for refund")
    refund_date = models.DateTimeField(auto_now_add=True)
    processed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refunds_processed"
    )
    
    # Financial tracking
    refund_method = models.CharField(
        max_length=20,
        choices=[
            ('cash', 'Cash'),
            ('gcash', 'GCash'),
            ('bank_transfer', 'Bank Transfer'),
        ],
        default='cash'
    )
    
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-refund_date']
        verbose_name = "Service Refund"
        verbose_name_plural = "Service Refunds"
    
    def __str__(self):
        return f"Refund #{self.id} - Service #{self.service.id} - ₱{self.refund_amount}"


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
    serial_number = models.CharField(max_length=100, blank=True, null=True, help_text="Serial number of the appliance (optional)")
    issue_reported = models.TextField(blank=True, null=True)
    diagnosis_notes = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20, choices=ApplianceStatus.choices, default=ApplianceStatus.RECEIVED
    )
    
    # Technician assignment
    assigned_technician = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_appliances",
        help_text="Technician assigned to work on this appliance"
    )
    
    labor_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    labor_is_free = models.BooleanField(
        default=False, help_text="Mark labor for this appliance as free."
    )
    # Unit price for second-hand or custom-priced units
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Custom unit price (used for second-hand units or overrides)"
    )
    # Promo support - track original amount before discount
    labor_original_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Original labor fee before promo discount (e.g., free installation)",
    )
    
    # Labor discounts
    labor_discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Fixed discount amount for labor"
    )
    labor_discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Percentage discount for labor (0.00 - 100.00)"
    )
    labor_discount_reason = models.CharField(
        max_length=200,
        blank=True,
        help_text="Reason for labor discount"
    )
    
    # Warranty information
    labor_warranty_months = models.PositiveIntegerField(
        default=0,
        help_text="Labor warranty period in months (0 = no warranty)"
    )
    unit_warranty_months = models.PositiveIntegerField(
        default=0,
        help_text="Unit warranty period in months (0 = no warranty)"
    )
    warranty_notes = models.TextField(
        blank=True,
        help_text="Warranty details and notes (e.g., compressor warranty, parts coverage)"
    )
    warranty_start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date when warranty becomes active (set when installation is completed)"
    )
    labor_warranty_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date when labor warranty expires"
    )
    unit_warranty_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date when unit warranty expires"
    )
    
    @property
    def discounted_labor_fee(self):
        """Labor fee after item-level discount"""
        if self.labor_is_free:
            return Decimal('0.00')
        
        fee = Decimal(str(self.labor_fee))
        
        # Apply fixed discount
        fee = max(fee - Decimal(str(self.labor_discount_amount)), Decimal('0'))
        
        # Apply percentage discount
        if self.labor_discount_percentage > 0:
            discount_decimal = Decimal(str(self.labor_discount_percentage)) / Decimal('100')
            fee = fee * (Decimal('1') - discount_decimal)
        
        # Round to 2 decimal places
        return max(fee.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), Decimal('0.00'))

    def activate_warranties(self, start_date=None):
        """
        Activate warranties by setting start date and calculating end dates.
        Should be called when installation is completed.
        """
        from datetime import date
        from dateutil.relativedelta import relativedelta
        
        if start_date is None:
            start_date = date.today()
        
        self.warranty_start_date = start_date
        
        # Calculate labor warranty end date
        if self.labor_warranty_months > 0:
            self.labor_warranty_end_date = start_date + relativedelta(months=self.labor_warranty_months)
        else:
            self.labor_warranty_end_date = None
        
        # Calculate unit warranty end date
        if self.unit_warranty_months > 0:
            self.unit_warranty_end_date = start_date + relativedelta(months=self.unit_warranty_months)
        else:
            self.unit_warranty_end_date = None
        
        self.save(update_fields=['warranty_start_date', 'labor_warranty_end_date', 'unit_warranty_end_date'])
    
    @property
    def is_labor_warranty_active(self):
        """Check if labor warranty is currently active"""
        from datetime import date
        if not self.warranty_start_date or not self.labor_warranty_end_date:
            return False
        return self.warranty_start_date <= date.today() <= self.labor_warranty_end_date
    
    @property
    def is_unit_warranty_active(self):
        """Check if unit warranty is currently active"""
        from datetime import date
        if not self.warranty_start_date or not self.unit_warranty_end_date:
            return False
        return self.warranty_start_date <= date.today() <= self.unit_warranty_end_date

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
    
    # Item-level discounts
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Fixed discount amount for this item"
    )
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Percentage discount (0.00 - 100.00)"
    )
    discount_reason = models.CharField(
        max_length=200,
        blank=True,
        help_text="Reason for item discount"
    )
    
    # Cancellation tracking (only for cancelled services)
    is_cancelled = models.BooleanField(
        default=False,
        help_text="True if service was cancelled and part returned to stock"
    )
    cancelled_at = models.DateTimeField(blank=True, null=True)
    
    @property
    def discounted_price(self):
        """Calculate price per unit after discount"""
        if not self.item:
            return Decimal('0.00')
        
        base_price = Decimal(str(self.item.retail_price))
        
        # Apply fixed discount first
        price = max(base_price - Decimal(str(self.discount_amount)), Decimal('0'))
        
        # Then apply percentage discount
        if self.discount_percentage > 0:
            discount_decimal = Decimal(str(self.discount_percentage)) / Decimal('100')
            price = price * (Decimal('1') - discount_decimal)
        
        # Round to 2 decimal places
        return max(price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), Decimal('0.00'))
    
    @property
    def line_total(self):
        """Total for this line item after discounts"""
        if self.is_free:
            return Decimal('0.00')
        charged_qty = self.quantity - Decimal(str(self.free_quantity))
        result = self.discounted_price * charged_qty
        # Round to 2 decimal places
        return result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

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
# Service-Level Items (not tied to any appliance)
# ----------------------------------
class ServiceItemUsed(BaseItemUsed):
    """
    Items used at the service level, not tied to any appliance.
    
    Used for pre-installation work like chipping (copper pipe, insulation tube,
    etc.) where the AC unit hasn't been added yet, or general materials that
    don't belong to a specific appliance.
    """
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="service_items"
    )

    class Meta:
        verbose_name = "Service Item Used"
        verbose_name_plural = "Service Items Used"

    stall_stock = models.ForeignKey(
        Stock,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_items_used",
    )
    is_free = models.BooleanField(
        default=False, help_text="Mark this part as free to the customer."
    )
    free_quantity = models.PositiveIntegerField(
        default=0,
        help_text="Quantity given free as part of promotion",
    )
    promo_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Name of applied promotion",
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Fixed discount amount for this item"
    )
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Percentage discount (0.00 - 100.00)"
    )
    discount_reason = models.CharField(
        max_length=200,
        blank=True,
        help_text="Reason for item discount"
    )
    is_cancelled = models.BooleanField(
        default=False,
        help_text="True if service was cancelled and part returned to stock"
    )
    cancelled_at = models.DateTimeField(blank=True, null=True)

    expense = models.ForeignKey(
        "expenses.Expense",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_level_items",
    )

    @property
    def discounted_price(self):
        if not self.item:
            return Decimal('0.00')
        base_price = Decimal(str(self.item.retail_price))
        price = max(base_price - Decimal(str(self.discount_amount)), Decimal('0'))
        if self.discount_percentage > 0:
            discount_decimal = Decimal(str(self.discount_percentage)) / Decimal('100')
            price = price * (Decimal('1') - discount_decimal)
        return max(price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), Decimal('0.00'))

    @property
    def line_total(self):
        if self.is_free:
            return Decimal('0.00')
        charged_qty = self.quantity - Decimal(str(self.free_quantity))
        result = self.discounted_price * charged_qty
        return result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def __str__(self):
        return f"{self.item} x{self.quantity} (service #{self.service_id})"



