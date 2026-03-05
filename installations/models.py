from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from services.models import Service
from utils.enums import AirconType, HorsePower, ServiceType


class AirconBrand(models.Model):
    name = models.CharField(max_length=100, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class AirconModel(models.Model):
    brand = models.ForeignKey(AirconBrand, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    retail_price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Dealer/purchase cost price of this aircon model.",
    )
    promo_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Manual promotional price. If set and less than retail, this is the selling price.",
    )
    aircon_type = models.CharField(
        max_length=30, choices=AirconType.choices, default=AirconType.WINDOW
    )
    horsepower = models.CharField(
        max_length=10,
        choices=HorsePower.choices,
        default=HorsePower.HP_1_0,
        help_text="Horsepower/capacity of the air conditioner"
    )
    is_inverter = models.BooleanField(
        default=False, help_text="Uses inverter technology."
    )

    # Warranty configuration per model
    parts_warranty_months = models.PositiveIntegerField(
        default=60,
        help_text="Parts (unit) warranty duration in months (default: 60 = 5 years)",
    )
    labor_warranty_months = models.PositiveIntegerField(
        default=12,
        help_text="Labor warranty duration in months (default: 12 = 1 year)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.brand.name} {self.name} ({self.get_aircon_type_display()})"

    @property
    def parts_warranty_years(self) -> float:
        """Parts warranty in years (for display)."""
        return round(self.parts_warranty_months / 12, 1)

    @property
    def labor_warranty_years(self) -> float:
        """Labor warranty in years (for display)."""
        return round(self.labor_warranty_months / 12, 1)

    @property
    def has_discount(self) -> bool:
        """Returns True if the model has a valid promo price set below retail."""
        return (
            self.promo_price is not None
            and self.promo_price > 0
            and self.promo_price < self.retail_price
        )

    @property
    def selling_price(self) -> Decimal:
        """Final selling price: promo_price if set and valid, else retail_price."""
        if self.has_discount:
            return self.promo_price
        return self.retail_price

    def save(self, *args, **kwargs):
        """Override save to track price changes in history."""
        track_history = kwargs.pop("track_history", True)
        is_new = self.pk is None
        old_retail = None
        old_promo = None

        if not is_new and track_history:
            try:
                old = AirconModel.objects.get(pk=self.pk)
                old_retail = old.retail_price
                old_promo = old.promo_price
            except AirconModel.DoesNotExist:
                pass

        super().save(*args, **kwargs)

        if track_history:
            if is_new:
                # Log initial price
                ModelPriceHistory.objects.create(
                    aircon_model=self,
                    retail_price=self.retail_price,
                    promo_price=self.promo_price,
                    change_type="initial",
                    notes="Initial price set on model creation",
                )
            elif old_retail is not None:
                price_changed = old_retail != self.retail_price
                promo_changed = old_promo != self.promo_price
                if price_changed or promo_changed:
                    change_type = "price_and_promo" if (price_changed and promo_changed) else ("price" if price_changed else "promo")
                    ModelPriceHistory.objects.create(
                        aircon_model=self,
                        retail_price=self.retail_price,
                        promo_price=self.promo_price,
                        old_retail_price=old_retail,
                        old_promo_price=old_promo,
                        change_type=change_type,
                    )


class ModelPriceHistory(models.Model):
    """Tracks price changes for aircon models."""

    CHANGE_TYPE_CHOICES = [
        ("initial", "Initial Price"),
        ("price", "Price Change"),
        ("promo", "Promo Price Change"),
        ("price_and_promo", "Price & Promo Change"),
    ]

    aircon_model = models.ForeignKey(
        AirconModel,
        on_delete=models.CASCADE,
        related_name="price_history",
    )
    retail_price = models.DecimalField(max_digits=10, decimal_places=2)
    promo_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Promo price at this point in history",
    )
    old_retail_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Previous retail price (null for initial)",
    )
    old_promo_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Previous promo price (null for initial)",
    )
    change_type = models.CharField(
        max_length=20, choices=CHANGE_TYPE_CHOICES, default="price"
    )
    notes = models.TextField(blank=True, default="")
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]
        verbose_name = "Price History"
        verbose_name_plural = "Price Histories"

    @property
    def effective_price(self) -> Decimal:
        """Effective selling price at this point in history."""
        if self.promo_price and self.promo_price > 0 and self.promo_price < self.retail_price:
            return self.promo_price
        return self.retail_price

    @property
    def price_change_amount(self):
        """Difference from old to new retail price."""
        if self.old_retail_price is not None:
            return self.retail_price - self.old_retail_price
        return None

    def __str__(self):
        return f"{self.aircon_model} - ₱{self.retail_price} (promo: {self.promo_price or 'N/A'}) ({self.change_type}) @ {self.changed_at}"


class AirconUnit(models.Model):
    model = models.ForeignKey(AirconModel, on_delete=models.PROTECT, null=True)
    serial_number = models.CharField(
        max_length=100, 
        unique=True,
        help_text="Indoor unit serial number"
    )
    outdoor_serial_number = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        help_text="Outdoor unit serial number (for split-type units)"
    )

    # Link to Main stall (owner of aircon units)
    stall = models.ForeignKey(
        "inventory.Stall",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="aircon_units",
        limit_choices_to={"stall_type": "main", "is_system": True},
        help_text="Main stall that owns this aircon unit",
    )

    sale = models.ForeignKey(
        "sales.SalesTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="aircon_units_sold",
    )

    installation_service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="installation_units",
        help_text="Installation service this unit is part of"
    )

    reserved_by = models.ForeignKey(
        "clients.Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reserved_aircon_units",
    )
    reserved_at = models.DateTimeField(null=True, blank=True)

    warranty_start_date = models.DateField(null=True, blank=True)
    warranty_period_months = models.PositiveIntegerField(default=12)
    free_cleaning_redeemed = models.BooleanField(default=False)
    free_cleaning_service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="free_cleaning_units",
        help_text="The cleaning service created when free cleaning was redeemed"
    )

    # Track if unit is sold (convenience field)
    is_sold = models.BooleanField(
        default=False,
        help_text="Marks if unit has been sold to customer",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        # Validate stall is Main stall
        if self.stall and self.stall.stall_type != "main":
            raise ValidationError(
                {"stall": "Aircon units can only be owned by Main stall."}
            )

        if self.installation_service:
            # Validate installation_service is actually an installation service
            if self.installation_service.service_type != ServiceType.INSTALLATION:
                raise ValidationError(
                    {"installation_service": "Service must be an INSTALLATION service."}
                )
            tx = self.installation_service.related_transaction
            if tx and self.sale and self.sale != tx:
                raise ValidationError(
                    {"sale": "Sale must match the installation's transaction."}
                )
            # Installation doesn't require sale - unit can be reserved

        if self.warranty_start_date and not (self.sale or self.installation_service):
            raise ValidationError({"warranty_start_date": "Warranty requires a sale or installation."})

    def save(self, *args, **kwargs):
        run_clean = kwargs.pop("clean", True)
        if run_clean:
            self.full_clean()

        # Auto-assign to Main stall if not set
        if not self.stall:
            from inventory.models import Stall
            main_stall = Stall.objects.filter(
                stall_type="main", is_system=True
            ).first()
            if main_stall:
                self.stall = main_stall

        # Determine warranty start logic
        # Warranty for direct sales (no installation) starts at sale date.
        # Warranty for installations is set by complete_installation() — NOT here.
        if self.sale and not self.installation_service and self.sale.created_at:
            self.warranty_start_date = self.sale.created_at.date()
        elif not self.sale and not self.installation_service:
            self.warranty_start_date = None  # Not yet started

        # Mark as sold and clear reservation once sold
        # Units with installation but no sale should remain reserved
        if self.sale:
            self.is_sold = True
            self.reserved_by = None
            self.reserved_at = None

        super().save(*args, **kwargs)

    @property
    def is_reserved(self):
        return self.reserved_by is not None

    @property
    def warranty_end_date(self):
        if self.warranty_start_date:
            return self.warranty_start_date + relativedelta(
                months=self.warranty_period_months
            )

    @property
    def is_under_warranty(self):
        return (
            self.warranty_end_date and timezone.now().date() <= self.warranty_end_date
        )

    @property
    def warranty_status(self):
        if self.warranty_period_months == 0:
            return "No Warranty"

        if not self.warranty_start_date:
            return "Warranty Not Started"

        return "Under Warranty" if self.is_under_warranty else "Expired"

    @property
    def warranty_days_left(self):
        return (
            max((self.warranty_end_date - timezone.now().date()).days, 0)
            if self.is_under_warranty
            else 0
        )

    # --- Per-type warranty properties (based on AirconModel's parts/labor warranty months) ---

    @property
    def parts_warranty_end_date(self):
        if self.warranty_start_date and self.model and self.model.parts_warranty_months:
            return self.warranty_start_date + relativedelta(months=self.model.parts_warranty_months)
        return None

    @property
    def labor_warranty_end_date(self):
        if self.warranty_start_date and self.model and self.model.labor_warranty_months:
            return self.warranty_start_date + relativedelta(months=self.model.labor_warranty_months)
        return None

    @property
    def parts_warranty_days_left(self):
        end = self.parts_warranty_end_date
        if end and timezone.now().date() <= end:
            return max((end - timezone.now().date()).days, 0)
        return 0

    @property
    def labor_warranty_days_left(self):
        end = self.labor_warranty_end_date
        if end and timezone.now().date() <= end:
            return max((end - timezone.now().date()).days, 0)
        return 0

    @property
    def parts_warranty_status(self):
        if not self.model or not self.model.parts_warranty_months:
            return "No Warranty"
        if not self.warranty_start_date:
            return "Not Started"
        return "Active" if self.parts_warranty_days_left > 0 else "Expired"

    @property
    def labor_warranty_status(self):
        if not self.model or not self.model.labor_warranty_months:
            return "No Warranty"
        if not self.warranty_start_date:
            return "Not Started"
        return "Active" if self.labor_warranty_days_left > 0 else "Expired"

    @property
    def free_cleaning_status(self):
        """Return the free cleaning status: available, pending, or redeemed.
        - available: Not yet redeemed
        - pending: Redeemed but service not completed
        - redeemed: Redeemed and service completed
        """
        if not self.free_cleaning_redeemed:
            return "available"
        if self.free_cleaning_service:
            from utils.enums import ServiceStatus
            if self.free_cleaning_service.status == ServiceStatus.COMPLETED:
                return "redeemed"
            if self.free_cleaning_service.status == ServiceStatus.CANCELLED:
                return "available"  # Cancelled cleaning = still available
            return "pending"  # Redeemed but not completed yet
        return "pending"  # Redeemed but no service record yet

    @property
    def free_cleaning_redemption_date(self):
        """Return the date when free cleaning was redeemed."""
        if self.free_cleaning_redeemed and self.free_cleaning_service:
            return self.free_cleaning_service.created_at
        return None

    @property
    def free_cleaning_service_id(self):
        """Return the service ID for free cleaning."""
        return self.free_cleaning_service_id if self.free_cleaning_service else None

    @property
    def is_available_for_sale(self):
        return self.sale is None and self.reserved_by is None and not self.is_sold

    @property
    def unit_status(self):
        """Computed status reflecting the full lifecycle of the unit."""
        from utils.enums import ServiceStatus
        if self.installation_service:
            if self.installation_service.status == ServiceStatus.COMPLETED:
                return "Installed"
            return "For Installation"
        if self.is_sold:
            return "Sold"
        if self.is_reserved:
            return "Reserved"
        return "Available"

    @property
    def sale_price(self):
        """Get the actual sale price.
        
        For installed units, returns the price from ServiceAppliance.unit_price (if overridden).
        Otherwise returns the model's selling price.
        """
        # If this unit is part of an installation service, check for price override
        if self.installation_service:
            # Find the matching ServiceAppliance by serial number
            matching_appliance = self.installation_service.appliances.filter(
                serial_number=self.serial_number
            ).first()
            
            if matching_appliance and matching_appliance.unit_price is not None:
                return matching_appliance.unit_price
        
        # Fall back to model's selling price
        if self.model:
            return self.model.selling_price
        return Decimal("0.00")

    def __str__(self):
        return f"{self.model} (SN: {self.serial_number})"


class WarrantyClaim(models.Model):
    """Tracks warranty claims for aircon units."""

    class ClaimStatus(models.TextChoices):
        PENDING = "pending", "Pending Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class ClaimType(models.TextChoices):
        REPAIR = "repair", "Repair"
        REPLACEMENT = "replacement", "Replacement"
        PARTS = "parts", "Parts Replacement"
        INSPECTION = "inspection", "Inspection"

    unit = models.ForeignKey(
        AirconUnit,
        on_delete=models.PROTECT,
        related_name="warranty_claims",
        help_text="Aircon unit this claim is for",
    )

    # Link to the service created for this warranty claim
    service = models.OneToOneField(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="warranty_claim",
        help_text="Service created to handle this warranty claim",
    )

    claim_type = models.CharField(
        max_length=20,
        choices=ClaimType.choices,
        default=ClaimType.REPAIR,
    )

    status = models.CharField(
        max_length=20,
        choices=ClaimStatus.choices,
        default=ClaimStatus.PENDING,
    )

    # Claim details
    issue_description = models.TextField(
        help_text="Description of the issue/defect reported by customer",
    )

    customer_notes = models.TextField(
        blank=True,
        help_text="Additional notes from customer",
    )

    # Internal assessment
    technician_assessment = models.TextField(
        blank=True,
        help_text="Technician's assessment of the issue",
    )

    is_valid_claim = models.BooleanField(
        default=True,
        help_text="Whether this is a valid warranty claim (not customer misuse, etc.)",
    )

    # Approval workflow
    reviewed_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_warranty_claims",
        help_text="Staff member who reviewed this claim",
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the claim was reviewed/approved/rejected",
    )

    rejection_reason = models.TextField(
        blank=True,
        help_text="Reason for rejection (if applicable)",
    )

    # Claim costs (if applicable)
    estimated_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Estimated cost of warranty repair/replacement",
    )

    actual_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Actual cost incurred (if completed)",
    )

    # Timestamps
    claim_date = models.DateTimeField(
        default=timezone.now,
        help_text="When the claim was submitted",
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the warranty service was completed",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-claim_date"]
        verbose_name = "Warranty Claim"
        verbose_name_plural = "Warranty Claims"

    def clean(self):
        """Validate warranty claim."""
        # Check if unit is under warranty
        if self.unit and not self.unit.is_under_warranty:
            raise ValidationError(
                {"unit": f"Unit {self.unit.serial_number} is not under warranty. "
                         f"Warranty status: {self.unit.warranty_status}"}
            )

        # Check if unit has been sold
        if self.unit and not self.unit.is_sold:
            raise ValidationError(
                {"unit": f"Unit {self.unit.serial_number} has not been sold yet."}
            )

        # If status is rejected, must have rejection reason
        if self.status == self.ClaimStatus.REJECTED and not self.rejection_reason:
            raise ValidationError(
                {"rejection_reason": "Rejection reason is required when rejecting a claim."}
            )

        # If status is approved/in_progress/completed, must be valid claim
        if self.status in [
            self.ClaimStatus.APPROVED,
            self.ClaimStatus.IN_PROGRESS,
            self.ClaimStatus.COMPLETED,
        ] and not self.is_valid_claim:
            raise ValidationError(
                {"is_valid_claim": "Cannot approve/process an invalid claim."}
            )

        # Service must be warranty service if linked
        if self.service:
            if self.service.service_type not in [ServiceType.REPAIR, ServiceType.INSPECTION]:
                raise ValidationError(
                    {"service": "Warranty claim service must be a repair or inspection service."}
                )

    def save(self, *args, **kwargs):
        run_clean = kwargs.pop("clean", True)
        if run_clean:
            self.full_clean()
        super().save(*args, **kwargs)

    @property
    def is_pending(self):
        """Check if claim is pending review."""
        return self.status == self.ClaimStatus.PENDING

    @property
    def is_approved(self):
        """Check if claim has been approved."""
        return self.status in [
            self.ClaimStatus.APPROVED,
            self.ClaimStatus.IN_PROGRESS,
            self.ClaimStatus.COMPLETED,
        ]

    @property
    def warranty_days_remaining_at_claim(self):
        """Get warranty days remaining when claim was submitted."""
        if not self.unit or not self.unit.warranty_end_date:
            return 0

        claim_date_only = self.claim_date.date()
        days_left = (self.unit.warranty_end_date - claim_date_only).days
        return max(days_left, 0)

    def __str__(self):
        return f"Warranty Claim #{self.id} - {self.unit.serial_number} ({self.get_status_display()})"
