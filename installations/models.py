from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from services.models import Service
from utils.enums import AirconType, ServiceType


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
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Discount percentage applied to retail price (0–100).",
    )
    aircon_type = models.CharField(
        max_length=30, choices=AirconType.choices, default=AirconType.WINDOW
    )
    is_inverter = models.BooleanField(
        default=False, help_text="Uses inverter technology."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.brand.name} {self.name} ({self.get_aircon_type_display()})"

    @property
    def has_discount(self) -> bool:
        """Returns True if the model has a valid discount applied."""
        return self.discount_percentage > 0

    @property
    def promo_price(self) -> Decimal:
        """Final price after applying discount, if any."""
        if self.has_discount:
            discount_fraction = self.discount_percentage / Decimal("100")
            discount_amount = self.retail_price * discount_fraction
            return self.retail_price - discount_amount
        return self.retail_price


class AirconInstallation(models.Model):
    service = models.OneToOneField(
        Service, on_delete=models.CASCADE, related_name="aircon_installation", null=True
    )
    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.service.service_type != ServiceType.INSTALLATION:
            raise ValidationError(
                "Installation must be linked to an INSTALLATION service."
            )

    def __str__(self):
        client = getattr(self.service.client, "full_name", "Unknown Client")
        return f"Installation for {client}"


class AirconUnit(models.Model):
    model = models.ForeignKey(AirconModel, on_delete=models.PROTECT, null=True)
    serial_number = models.CharField(max_length=100, unique=True)

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

    installation = models.OneToOneField(
        AirconInstallation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="aircon_unit",
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

        if self.installation:
            tx = self.installation.service.related_transaction
            if tx and self.sale != tx:
                raise ValidationError(
                    {"sale": "Sale must match the installation's transaction."}
                )
            if not self.sale:
                raise ValidationError({"sale": "Installed units must be sold first."})

        if self.warranty_start_date and not self.sale:
            raise ValidationError({"warranty_start_date": "Warranty requires a sale."})

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
        if self.installation and hasattr(self.installation, 'date_installed') and self.installation.date_installed:
            self.warranty_start_date = self.installation.date_installed
        elif self.sale and self.sale.created_at:
            self.warranty_start_date = self.sale.created_at.date()
        else:
            self.warranty_start_date = None  # Not yet started

        # Mark as sold and clear reservation once sold or installed
        if self.sale or self.installation:
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

    @property
    def is_available_for_sale(self):
        return self.sale is None and self.reserved_by is None and not self.is_sold

    @property
    def sale_price(self):
        """Get the actual sale price (promo price if available, else retail)."""
        if self.model:
            return self.model.promo_price
        return Decimal("0.00")

    def __str__(self):
        return f"{self.model} (SN: {self.serial_number})"


class AirconItemUsed(models.Model):
    unit = models.ForeignKey(
        AirconUnit, on_delete=models.CASCADE, related_name="items_used"
    )
    item = models.ForeignKey("inventory.Item", on_delete=models.SET_NULL, null=True)
    total_quantity_used = models.PositiveIntegerField()
    free_quantity = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.total_quantity_used < self.free_quantity:
            raise ValidationError("Free quantity cannot exceed total quantity used.")

    def __str__(self):
        return f"{self.item.name} x{self.total_quantity_used} for unit {self.unit.serial_number}"
