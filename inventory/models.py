import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


# =========== MANAGERS ===========
class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


# =========== CONSTANTS ===========

UNIT_CHOICES = [
    ("pcs", "Pieces"),
    ("ft", "Feet"),
    ("kg", "Kilogram"),
    ("roll", "Roll"),
    ("box", "Box"),
]

# =========== MODELS ===========


class ProductCategory(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name"],
                condition=models.Q(is_deleted=False),
                name="unique_active_productcategory_name",
            )
        ]

    def __str__(self):
        return self.name


class Item(models.Model):
    name = models.CharField(max_length=100)
    sku = models.CharField(max_length=50, unique=True, blank=True)
    category = models.ForeignKey(
        ProductCategory, on_delete=models.SET_NULL, null=True, blank=True
    )
    description = models.TextField(blank=True, null=True)
    unit_of_measure = models.CharField(
        max_length=10, choices=UNIT_CHOICES, default="pcs"
    )
    retail_price = models.DecimalField(max_digits=10, decimal_places=2)
    wholesale_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, null=True, blank=True
    )
    technician_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, null=True, blank=True
    )
    cost_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, null=True, blank=True
    )
    waste_tolerance_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Acceptable waste/loss % when dispensing (e.g. 5.00 = 5% tolerance for freon, copper tubes).",
    )
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.sku:
            prefix = (
                self.category.name[:3].ljust(3, "_") if self.category else "SKU"
            ).upper()
            unique = uuid.uuid4().hex[:5].upper()
            self.sku = f"{prefix}-{unique}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Stall(models.Model):
    STALL_TYPE_CHOICES = [
        ("main", "Main Stall"),
        ("sub", "Sub Stall"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=100)
    location = models.CharField(max_length=255)
    # Only stalls that are inventory owners should have Stock rows.
    # For this project we keep a single inventory owner (sub-stall).
    inventory_enabled = models.BooleanField(default=False)
    # Marks stalls that are system-configured (main/sub) and should not be
    # created/edited/deleted via public CRUD endpoints.
    is_system = models.BooleanField(default=False)
    # Identifies the type of stall in the two-stall architecture
    stall_type = models.CharField(
        max_length=10,
        choices=STALL_TYPE_CHOICES,
        default="other",
        help_text="Stall type: Main (services + aircon units), Sub (parts), or Other",
    )
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    def __str__(self):
        return self.name


class Stock(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="stocks")

    stall = models.ForeignKey(Stall, on_delete=models.CASCADE, related_name="stocks")

    quantity = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Total quantity in stock (supports decimals for kg, ft, etc.).",
    )

    reserved_quantity = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Quantity reserved for active services.",
    )

    low_stock_threshold = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Threshold below which stock is considered low.",
    )

    track_stock = models.BooleanField(default=True)

    is_deleted = models.BooleanField(default=False)

    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["item__name"]
        indexes = [
            models.Index(fields=["item", "stall"], name="stock_item_stall_idx"),
            models.Index(fields=["is_deleted"], name="stock_is_deleted_idx"),
        ]

    def clean(self):
        """
        Enforce single stockroom source of truth:
        - Only the Sub stall (Parts) may hold Stock rows.
        """
        if self.stall:
            # Require system-managed Sub stall as the only inventory owner
            if not getattr(self.stall, "is_system", False):
                raise ValidationError(
                    "Stock can only be associated with system-managed Sub stall."
                )
            if not getattr(self.stall, "inventory_enabled", False):
                raise ValidationError(
                    "Stock can only be associated with the Sub stall (inventory_enabled=True)."
                )
            if getattr(self.stall, "stall_type", None) != "sub":
                raise ValidationError("Stock must be in Sub stall only.")

    @property
    def available_quantity(self):
        """Quantity that can still be sold or used for new services."""
        return max(self.quantity - self.reserved_quantity, Decimal("0"))

    def status(self):
        # Check available quantity (not total) for status
        if self.available_quantity == 0:
            return "no_stock"
        elif self.available_quantity <= self.low_stock_threshold:
            return "low_stock"
        else:
            return "high_stock"

    def __str__(self):
        return (
            f"{self.item.name} @ {self.stall.name} - "
            f"{self.quantity} total / {self.available_quantity} available"
        )


class StockRoomStock(models.Model):
    item = models.OneToOneField(
        Item, on_delete=models.CASCADE, related_name="stockroom_stock"
    )

    quantity = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Total quantity in stockroom (supports decimals for kg, ft, etc.).",
    )

    low_stock_threshold = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Threshold below which stock is considered low.",
    )

    is_deleted = models.BooleanField(default=False)

    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        """
        Single source-of-truth validation:
        - quantity and low_stock_threshold must be non-negative
        - Only the Sub (Parts) stall may hold tracked Stock rows. If any other
          stall has tracked Stock for this item, raise an error.
        """
        if self.quantity < 0:
            raise ValueError("Stock room quantity cannot be negative.")
        if self.low_stock_threshold < 0:
            raise ValueError("Stock room low stock threshold cannot be negative.")

        # Ensure no tracked stock exists outside the Sub (Parts) stall
        # Note: Using in-file Stock class to avoid circular imports
        invalid_stall_stock_exists = (
            Stock.objects.filter(
                item=self.item,
                is_deleted=False,
                track_stock=True,
            )
            .exclude(stall__name="Sub", stall__location="Parts", stall__is_system=True)
            .exists()
        )

        if invalid_stall_stock_exists:
            raise ValueError(
                "Tracked Stock for this item exists outside the Sub (Parts) stall. "
                "Move quantities back to the stock room or the Sub stall to maintain a single source of truth."
            )

    def status(self):
        if self.quantity == 0:
            return "no_stock"
        elif self.quantity <= self.low_stock_threshold:
            return "low_stock"

        else:
            return "high_stock"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["item"], name="unique_item_stockroom")
        ]

        ordering = ["item__name"]

    def __str__(self):
        return f"{self.item.name} - {self.quantity} {self.item.unit_of_measure}"
