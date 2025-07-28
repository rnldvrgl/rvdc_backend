from django.db import models
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from services.models import AirconInstallation
from utils.enums import (
    AirconType,
)
from django.core.exceptions import ValidationError


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
