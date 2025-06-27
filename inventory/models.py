from django.db import models
from django.conf import settings
import uuid

UNIT_CHOICES = [
    ("pcs", "Pieces"),
    ("ft", "Feet"),
    ("kg", "Kilogram"),
    ("roll", "Roll"),
    ("box", "Box"),
]


class ProductCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Item(models.Model):
    name = models.CharField(max_length=100)
    sku = models.CharField(max_length=50, unique=True, blank=True)
    category = models.ForeignKey(
        ProductCategory, on_delete=models.SET_NULL, null=True, blank=True
    )
    description = models.TextField(blank=True, null=True)
    size_or_spec = models.CharField(max_length=50, blank=True, null=True)
    unit_of_measure = models.CharField(
        max_length=10,
        choices=UNIT_CHOICES,
        default="pcs",
    )
    srp = models.DecimalField(max_digits=10, decimal_places=2)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
        return f"{self.name} {self.size_or_spec or ''}".strip()


class Stall(models.Model):
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=255)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Stock(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    stall = models.ForeignKey(Stall, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=0)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("item", "stall")

    def is_low_stock(self):
        return self.quantity <= self.low_stock_threshold

    def __str__(self):
        return f"{self.item.name} @ {self.stall.name} - {self.quantity} {self.item.unit_of_measure}"


class StockRoomStock(models.Model):
    item = models.OneToOneField(Item, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_low_stock(self):
        return self.quantity <= self.low_stock_threshold

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["item"], name="unique_item_stockroom")
        ]
        ordering = ["item__name"]

    def __str__(self):
        return f"{self.item.name} - {self.quantity} {self.item.unit_of_measure}"


class StockTransfer(models.Model):
    from_stall = models.ForeignKey(
        Stall,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="outgoing_transfers",
    )
    to_stall = models.ForeignKey(
        Stall, on_delete=models.CASCADE, related_name="incoming_transfers"
    )
    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requested_transfers",
    )
    transferred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    transfer_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transfer to {self.to_stall.name} on {self.transfer_date.strftime('%Y-%m-%d')}"


class StockTransferItem(models.Model):
    transfer = models.ForeignKey(
        StockTransfer, on_delete=models.CASCADE, related_name="items"
    )
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.quantity} {self.item.unit_of_measure} of {self.item.name}"
