from django.db import models, transaction
from django.conf import settings
import uuid
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.contrib.contenttypes import fields, models as contenttypes_models
from django.utils.translation import gettext_lazy as _


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
    # Only stalls that are inventory owners should have Stock rows.
    # For this project we keep a single inventory owner (sub-stall).
    inventory_enabled = models.BooleanField(default=False)
    # Marks stalls that are system-configured (main/sub) and should not be
    # created/edited/deleted via public CRUD endpoints.
    is_system = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    def __str__(self):
        return self.name


class Stock(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="stocks")
    stall = models.ForeignKey(Stall, on_delete=models.CASCADE, related_name="stocks")
    quantity = models.PositiveIntegerField(default=0)
    reserved_quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=0)
    track_stock = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["item__name"]

    @property
    def available_quantity(self):
        """Quantity that can still be sold or used for new services."""
        return max(self.quantity - self.reserved_quantity, 0)

    def status(self):
        if self.quantity == 0:
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
        from expenses.models import Expense, ExpenseItem
        # Import sales models here to avoid circular imports at module import time
        from sales.models import SalesTransaction, SalesItem

        if self.is_finalized:
            return

        with transaction.atomic():
            # 1. Mark as finalized
            self.is_finalized = True
            self.finalized_at = timezone.now()
            self.save()

            # 2. Decrement stock on the from_stall (if present) and create a SalesTransaction
            #    for the from_stall so the supplying stall records a sale.
            sales_txn = None
            if self.from_stall:
                sales_txn = SalesTransaction.objects.create(
                    stall=self.from_stall,
                    client=None,
                    sales_clerk=user,
                )

            total_price = 0
            # 3. Create Expense record (for receiving stall) and SalesItem entries (for supplying stall)
            expense = Expense.objects.create(
                stall=self.to_stall,
                total_price=0,  # will update below
                description=f"Finalized stock transfer from {self.from_stall or 'Stock Room'}",
                created_by=user,
                source="transfer",
                transfer=self,
            )

            for t_item in self.items.select_related("item"):
                item_total = t_item.item.retail_price * t_item.quantity
                total_price += item_total

                # Create ExpenseItem for receiver
                ExpenseItem.objects.create(
                    expense=expense,
                    item=t_item.item,
                    quantity=t_item.quantity,
                    total_price=item_total,
                )

                # Decrement stock from the supplying stall (if recorded)
                if self.from_stall:
                    try:
                        stock = Stock.objects.get(stall=self.from_stall, item=t_item.item)
                        stock.quantity = max(stock.quantity - t_item.quantity, 0)
                        stock.save()
                    except Stock.DoesNotExist:
                        # If no stock row exists, skip - transfer records the movement
                        pass

                # Create SalesItem for the supplying stall's SalesTransaction
                if sales_txn:
                    SalesItem.objects.create(
                        transaction=sales_txn,
                        item=t_item.item,
                        quantity=t_item.quantity,
                        final_price_per_unit=t_item.item.retail_price,
                    )

            # 4. Update expense total
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
