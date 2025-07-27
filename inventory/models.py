from django.db import models, transaction
from django.conf import settings
import uuid
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.contrib.contenttypes import fields, models as contenttypes_models


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


class AirconType(models.TextChoices):
    WINDOW = "window", _("Window Type")
    SPLIT = "split", _("Split Type")
    FLOOR_MOUNTED = "floor_mounted", _("Floor Mounted")
    CASSETTE = "cassette", _("Cassette Type")
    PORTABLE = "portable", _("Portable")
    CENTRALIZED = "centralized", _("Centralized")
    OTHERS = "others", _("Others")


# =========== MODELS ===========


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
        return self.name


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
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="stocks")
    low_stock_threshold = models.PositiveIntegerField(default=0)
    stall = models.ForeignKey(Stall, on_delete=models.CASCADE, related_name="stocks")
    quantity = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ["item__name"]

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
    item = models.OneToOneField(
        Item, on_delete=models.CASCADE, related_name="stockroom_stock"
    )
    quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=0)
    is_deleted = models.BooleanField(default=False)
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
        "inventory.Stall",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="outgoing_transfers",
    )
    to_stall = models.ForeignKey(
        "inventory.Stall", on_delete=models.CASCADE, related_name="incoming_transfers"
    )
    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requested_transfers",
    )
    used_for = models.CharField(max_length=100, blank=True, null=True)
    transferred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    transfer_date = models.DateTimeField(auto_now_add=True)
    is_finalized = models.BooleanField(default=False)
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-transfer_date"]

    def __str__(self):
        return f"Transfer to {self.to_stall.name} on {self.transfer_date.strftime('%Y-%m-%d')}"

    def can_be_finalized_by(self, user):
        if user.role == "admin":
            return True
        if user.role in ["manager", "clerk"] and user.assigned_stall == self.from_stall:
            return True
        return False

    def finalize(self, user):
        from notifications.models import Notification
        from utils.inventory import record_stock_movement
        from expenses.models import Expense, ExpenseItem

        if self.is_finalized:
            return

        with transaction.atomic():
            # 1. Mark as finalized
            self.is_finalized = True
            self.finalized_at = timezone.now()
            self.save()

            # 2. Create Expense record
            total_price = 0
            expense = Expense.objects.create(
                stall=self.to_stall,
                total_price=0,  # will update below
                description=f"Finalized stock transfer from {self.from_stall or 'Stock Room'}",
                created_by=user,
                source="transfer",
                transfer=self,
            )

            # 3. Create Expense Items & compute total
            for t_item in self.items.select_related("item"):
                item_total = t_item.item.retail_price * t_item.quantity
                total_price += item_total
                ExpenseItem.objects.create(
                    expense=expense,
                    item=t_item.item,
                    quantity=t_item.quantity,
                    total_price=item_total,
                )

                # 4. Create stock movements (audit only, do NOT adjust stocks)
                if self.from_stall:
                    record_stock_movement(
                        item=t_item.item,
                        stall=self.from_stall,
                        quantity=-t_item.quantity,
                        movement_type="transfer_out",
                        related_object=self,
                        note=f"Finalized transfer OUT: {t_item.quantity} {t_item.item.unit_of_measure} of {t_item.item.name}",
                    )
                else:
                    # from stock room
                    record_stock_movement(
                        item=t_item.item,
                        stall=None,
                        quantity=-t_item.quantity,
                        movement_type="transfer_out",
                        related_object=self,
                        note=f"Finalized transfer OUT from Stock Room",
                    )

                record_stock_movement(
                    item=t_item.item,
                    stall=self.to_stall,
                    quantity=t_item.quantity,
                    movement_type="transfer_in",
                    related_object=self,
                    note=f"Finalized transfer IN: {t_item.quantity} {t_item.item.unit_of_measure} of {t_item.item.name}",
                )

            # 5. Update expense total
            expense.total_price = total_price
            expense.save()

            # 6. Notify manager/clerk of to_stall
            manager_user = (
                get_user_model()
                .objects.filter(
                    assigned_stall=self.to_stall, role__in=["manager", "clerk"]
                )
                .first()
            )

            if manager_user:
                from_stall_name = (
                    self.from_stall.name if self.from_stall else "Stock Room"
                )
                to_stall_name = self.to_stall.name if self.to_stall else "Unknown"

                Notification.objects.create(
                    user=manager_user,
                    type="expense_created",
                    data={
                        "expense_id": expense.id,
                        "from_stall": from_stall_name,
                        "to_stall": to_stall_name,
                        "amount": float(total_price),
                    },
                    message=(
                        f"A stock transfer from {from_stall_name} to {to_stall_name} "
                        f"Total: ₱{total_price:,.2f}."
                    ),
                )


class StockTransferItem(models.Model):
    transfer = models.ForeignKey(
        StockTransfer, on_delete=models.CASCADE, related_name="items"
    )
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.quantity} {self.item.unit_of_measure} of {self.item.name}"


class Restock(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "users.CustomUser", on_delete=models.SET_NULL, null=True
    )


class StockMovement(models.Model):
    MOVEMENT_TYPE_CHOICES = [
        ("sale", "Sale"),
        ("purchase", "Purchase"),
        ("transfer_in", "Transfer In"),
        ("transfer_out", "Transfer Out"),
        ("adjustment", "Adjustment"),
        ("return", "Return"),
        ("restore_sale", "Restore Sale"),
        ("void_sale", "Void Sale"),
    ]

    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    stall = models.ForeignKey(Stall, on_delete=models.CASCADE, null=True, blank=True)
    quantity = models.IntegerField(
        help_text="Positive for stock in, negative for stock out"
    )
    movement_type = models.CharField(max_length=50, choices=MOVEMENT_TYPE_CHOICES)
    note = models.CharField(
        max_length=255, blank=True, help_text="Optional description / reason"
    )

    # The magic: link to ANY object
    content_type = models.ForeignKey(
        contenttypes_models.ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    related_object = fields.GenericForeignKey("content_type", "object_id")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        direction = "added" if self.quantity > 0 else "removed"
        return (
            f"{abs(self.quantity)} {self.item.unit_of_measure} {self.item.name} "
            f"{direction} in {self.stall.name if self.stall else 'stockroom'} "
            f"due to {self.movement_type}"
        )

    class Meta:
        ordering = ["-created_at"]


class AirconBrand(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class AirconModel(models.Model):
    brand = models.ForeignKey(AirconBrand, on_delete=models.CASCADE)
    model_name = models.CharField(max_length=100)

    aircon_type = models.CharField(
        max_length=30,
        choices=AirconType.choices,
        default=AirconType.WINDOW,
    )

    class Meta:
        unique_together = ("brand", "model_name")

    def __str__(self):
        return f"{self.brand.name} {self.model_name} ({self.get_aircon_type_display()})"


class ApplianceType(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class AirconUnit(models.Model):
    aircon_model = models.ForeignKey(AirconModel, on_delete=models.SET_NULL, null=True)
    serial_number = models.CharField(max_length=100, unique=True)
    is_installed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.aircon_model} - SN:{self.serial_number}"
