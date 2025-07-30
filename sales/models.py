import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from inventory.models import Stall, Item
from clients.models import Client
from users.models import CustomUser


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
    VOIDED = "voided", _("Voided")


class SalesTransaction(models.Model):
    stall = models.ForeignKey(Stall, on_delete=models.CASCADE)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True)
    sales_clerk = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_transactions",
    )

    manual_receipt_number = models.CharField(max_length=100, blank=True, null=True)
    system_receipt_number = models.UUIDField(default=uuid.uuid4, editable=False)

    payment_status = models.CharField(
        max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID
    )

    voided = models.BooleanField(default=False)
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(blank=True, null=True)

    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    change_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Sale #{self.id} - OR {self.manual_receipt_number or 'N/A'}"

    @property
    def total_items(self):
        return sum(item.quantity for item in self.items.all())

    @property
    def computed_total(self):
        return sum(item.line_total for item in self.items.all())

    @property
    def total_paid(self):
        return sum(payment.amount for payment in self.payments.all())

    def update_payment_status(self):
        if self.voided:
            self.payment_status = PaymentStatus.VOIDED
            self.change_amount = 0
        else:
            total = self.computed_total
            paid = self.total_paid

            if paid == 0:
                self.payment_status = PaymentStatus.UNPAID
            elif paid < total:
                self.payment_status = PaymentStatus.PARTIAL
            else:
                self.payment_status = PaymentStatus.PAID

            self.change_amount = max(paid - total, 0)

        self.save(update_fields=["payment_status", "change_amount"])

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()


class SalesPayment(models.Model):
    transaction = models.ForeignKey(
        SalesTransaction, related_name="payments", on_delete=models.CASCADE
    )
    payment_type = models.CharField(max_length=10, choices=PaymentType.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField(default=timezone.now)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Automatically update the related transaction's payment status
        self.transaction.update_payment_status()

    def __str__(self):
        return f"{self.payment_type}: {self.amount} on {self.payment_date.strftime('%Y-%m-%d')}"


class SalesItem(models.Model):
    transaction = models.ForeignKey(
        SalesTransaction, related_name="items", on_delete=models.CASCADE
    )
    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Leave blank for manual/labor/service line.",
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        help_text="For non-inventory charges like labor fees.",
    )

    quantity = models.PositiveIntegerField(default=1)
    final_price_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Actual unit price charged (auto-set from item if not provided)",
    )

    def save(self, *args, **kwargs):
        if self.aircon_unit:
            self.item = None
            self.description = str(self.aircon_unit.model)
            if self.final_price_per_unit is None:
                self.final_price_per_unit = self.aircon_unit.model.retail_price
        elif self.item and not self.description:
            self.description = self.item.name
            if self.final_price_per_unit is None:
                self.final_price_per_unit = self.item.retail_price

        super().save(*args, **kwargs)

        if self.aircon_unit:
            if self.aircon_unit.sale and self.aircon_unit.sale != self.transaction:
                raise ValueError(
                    "This aircon unit has already been sold in another transaction."
                )
            self.aircon_unit.sale = self.transaction
            self.aircon_unit.save(update_fields=["sale"])

    @property
    def line_total(self):
        return self.final_price_per_unit * self.quantity

    def __str__(self):
        label = self.description or (self.item.name if self.item else "Service Line")
        return f"{self.quantity} x {label} @ {self.final_price_per_unit}"
