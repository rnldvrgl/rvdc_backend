import uuid

from clients.models import Client
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from inventory.models import Item, Stall
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


class DocumentType(models.TextChoices):
    OFFICIAL_RECEIPT = "or", _("Official Receipt")
    SALES_INVOICE = "si", _("Sales Invoice")


class TransactionType(models.TextChoices):
    SALE = "sale", _("Sale")
    REPLACEMENT = "replacement", _("Replacement")
    PULL_OUT = "pull_out", _("Pull Out")
    SERVICE = "service", _("Service")
    ASSET_SALE = "asset_sale", _("Asset Sale")


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

    receipt_book = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Receipt book number (e.g. '1', '2'). Same SI/OR # can exist in different books.",
    )
    manual_receipt_number = models.CharField(max_length=100, blank=True, null=True)
    system_receipt_number = models.UUIDField(default=uuid.uuid4, editable=False)

    document_type = models.CharField(
        max_length=2,
        choices=DocumentType.choices,
        default=DocumentType.SALES_INVOICE,
        help_text="OR for Main Stall, SI for Sub Stall.",
    )
    with_2307 = models.BooleanField(
        default=False,
        help_text="Whether this transaction has an associated BIR Form 2307. Only valid for OR (Main Stall).",
    )

    payment_status = models.CharField(
        max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID
    )
    order_discount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Order-level discount in peso amount.",
    )

    voided = models.BooleanField(default=False)
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(blank=True, null=True)

    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    transaction_date = models.DateField(
        null=True,
        blank=True,
        help_text="The date this transaction occurred. Defaults to creation date.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    change_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
        default=TransactionType.SALE,
    )
    note = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["payment_status"], name="sales_payment_status_idx"),
            models.Index(fields=["created_at"], name="sales_created_at_idx"),
            models.Index(fields=["stall", "created_at"], name="sales_stall_created_idx"),
            models.Index(fields=["is_deleted"], name="sales_is_deleted_idx"),
            models.Index(fields=["document_type"], name="sales_doc_type_idx"),
            models.Index(fields=["document_type", "with_2307"], name="sales_doc_type_2307_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(document_type="si", with_2307=True),
                name="si_cannot_have_2307",
            ),
        ]

    def __str__(self):
        doc_label = "OR" if self.document_type == DocumentType.OFFICIAL_RECEIPT else "SI"
        return f"Sale #{self.id} - {doc_label} {self.manual_receipt_number or 'N/A'}"

    @property
    def total_items(self):
        return sum(item.quantity for item in self.items.all())

    @property
    def subtotal(self):
        return sum(item.line_total for item in self.items.all())

    @property
    def computed_total(self):
        subtotal = self.subtotal
        discount = self.order_discount or 0
        return max(subtotal - discount, 0)

    @property
    def total_paid(self):
        return sum(payment.amount for payment in self.payments.all())

    def update_payment_status(self):
        # Clear prefetch cache to ensure fresh data from DB
        if hasattr(self, '_prefetched_objects_cache'):
            self._prefetched_objects_cache.pop('payments', None)
            self._prefetched_objects_cache.pop('items', None)

        if self.voided:
            self.payment_status = PaymentStatus.VOIDED
            self.change_amount = 0
        elif self.transaction_type in (
            TransactionType.REPLACEMENT,
            TransactionType.PULL_OUT,
        ):
            self.payment_status = PaymentStatus.PAID
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
    cheque_collection = models.ForeignKey(
        "receivables.ChequeCollection",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_payments",
        help_text="Linked cheque collection if payment type is cheque",
    )

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

    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
        help_text="Quantity sold (supports decimals for kg, ft, etc.)",
    )
    final_price_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Actual unit price charged (auto-set from item if not provided)",
    )

    line_discount_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Line-level discount rate (0.00 - 1.00).",
    )

    def save(self, *args, **kwargs):
        if self.item and not self.description:
            self.description = self.item.name
            if self.final_price_per_unit is None:
                self.final_price_per_unit = self.item.retail_price

        super().save(*args, **kwargs)

    @property
    def line_total(self):
        unit = self.final_price_per_unit or 0
        discount = self.line_discount_rate or 0
        return (unit * (1 - discount)) * self.quantity

    def __str__(self):
        label = self.description or (self.item.name if self.item else "Service Line")
        return f"{self.quantity} x {label} @ {self.final_price_per_unit}"


class StallMonthlySheet(models.Model):
    """Google Sheets configuration per stall and month for sync/audit purposes."""

    stall = models.ForeignKey(
        Stall,
        on_delete=models.CASCADE,
        related_name="monthly_google_sheets",
    )
    month_key = models.CharField(
        max_length=7,
        help_text="Month key in YYYY-MM format.",
    )
    spreadsheet_id = models.CharField(
        max_length=255,
        help_text="Spreadsheet ID from the Google Sheets URL.",
    )
    spreadsheet_url = models.URLField(
        blank=True,
        default="",
        help_text="Canonical spreadsheet URL. Auto-filled from spreadsheet_id when empty.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="When false, this month record is kept for history but not used for sync.",
    )
    shared_ok = models.BooleanField(default=False)
    shared_to_email = models.EmailField(blank=True, default="")
    shared_at = models.DateTimeField(null=True, blank=True)
    share_error = models.TextField(blank=True, default="")
    last_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_monthly_sheets",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-month_key", "stall_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["stall", "month_key"],
                name="unique_stall_monthly",
            )
        ]
        indexes = [
            models.Index(fields=["month_key"], name="sales_monthly_month_idx"),
            models.Index(fields=["stall", "month_key"], name="sales_monthly_stall_month_idx"),
            models.Index(fields=["is_active"], name="sales_monthly_active_idx"),
        ]

    def save(self, *args, **kwargs):
        self.month_key = (self.month_key or "").strip()
        self.spreadsheet_id = (self.spreadsheet_id or "").strip()
        if self.spreadsheet_id and not self.spreadsheet_url:
            self.spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.stall.name} {self.month_key}"
