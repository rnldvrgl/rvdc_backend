from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from dateutil.relativedelta import relativedelta

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
    aircon_type = models.CharField(
        max_length=30, choices=AirconType.choices, default=AirconType.WINDOW
    )
    is_inverter = models.BooleanField(
        default=False, help_text="Uses inverter technology"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.brand.name} {self.name} ({self.get_aircon_type_display()})"


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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
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

        if self.sale and self.sale.created_at:
            self.warranty_start_date = self.sale.created_at.date()

        if self.sale or self.installation:
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
        if not self.warranty_start_date:
            return "No Warranty"
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
        return self.sale is None and self.reserved_by is None

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
