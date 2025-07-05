from django.db import models
from django.conf import settings
import uuid


# ===========
# Managers
# ===========
class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


# ===========
# Constants
# ===========
UNIT_CHOICES = [
    ("pcs", "Pieces"),
    ("ft", "Feet"),
    ("kg", "Kilogram"),
    ("roll", "Roll"),
    ("box", "Box"),
]


# ===========
# Models
# ===========


class ProductCategory(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    is_deleted = models.BooleanField(default=False)
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
    size_or_spec = models.CharField(max_length=50, blank=True, null=True)
    unit_of_measure = models.CharField(
        max_length=10, choices=UNIT_CHOICES, default="pcs"
    )
    srp = models.DecimalField(max_digits=10, decimal_places=2)
    is_deleted = models.BooleanField(default=False)
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
        return f"{self.name} {self.size_or_spec or ''}".strip()


class Stall(models.Model):
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=255)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    def __str__(self):
        return self.name


class Stock(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    low_stock_threshold = models.PositiveIntegerField(default=0)
    stall = models.ForeignKey(Stall, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    def status(self):
        if self.quantity == 0:
            return "no_stock"
        elif self.quantity <= self.low_stock_threshold:
            return "low_stock"
        else:
            return "high_stock"

    def __str__(self):
        return f"{self.item.name} @ {self.stall.name} - {self.quantity} {self.item.unit_of_measure}"


class StockRoomStock(models.Model):
    item = models.OneToOneField(Item, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
    is_expense = models.BooleanField(default=False)

    class Meta:
        ordering = ["-transfer_date"]

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


class StockMovement(models.Model):
    SOURCE_CHOICES = [
        ("stock_room", "Stock Room"),
        ("bought", "Bought Outside"),
        ("transfer", "Transfer From Another Stall"),
    ]
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    stall = models.ForeignKey(Stall, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    related_transfer = models.ForeignKey(
        StockTransfer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        direction = "added" if self.quantity > 0 else "removed"
        return f"{abs(self.quantity)} {self.item.unit_of_measure} {self.item.name} {direction} in {self.stall.name} from {self.source}"
