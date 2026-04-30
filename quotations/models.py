from decimal import Decimal

from django.db import models
from django.utils import timezone

from inventory.models import Stall


class QuotationTermsTemplate(models.Model):
    """Reusable templates for terms & conditions / payment terms."""

    class Category(models.TextChoices):
        TERMS_CONDITIONS = "terms_conditions", "Terms & Conditions"
        PAYMENT_TERMS = "payment_terms", "Payment Terms"

    name = models.CharField(max_length=100)  # e.g. "Installation", "Cleaning"
    category = models.CharField(max_length=30, choices=Category.choices)
    lines = models.JSONField(
        default=list,
        help_text="List of strings, each is one term/condition line.",
    )
    is_default = models.BooleanField(
        default=False,
        help_text="If true, auto-selected when creating a new quotation.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return f"{self.get_category_display()} — {self.name}"


class Quotation(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"

    class QuotationType(models.TextChoices):
        STANDARD = "standard", "Standard"
        PRICE_LIST = "price_list", "Price List"

    quotation_type = models.CharField(
        max_length=20,
        choices=QuotationType.choices,
        default=QuotationType.STANDARD,
    )

    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quotations",
    )
    client_name = models.CharField(max_length=255, blank=True)
    client_address = models.TextField(blank=True)
    client_contact = models.CharField(max_length=100, blank=True)

    stall = models.ForeignKey(
        Stall,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quotations",
    )

    price_list_template = models.ForeignKey(
        "quotations.QuotationPriceListTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quotations",
        help_text="Optional price list template (for price_list quotation type)",
    )

    quote_date = models.DateField(default=timezone.now)
    valid_until = models.DateField()
    project_description = models.TextField(blank=True)

    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    total = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    terms_conditions = models.TextField(blank=True)
    payment_terms = models.TextField(blank=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )

    notes = models.TextField(
        blank=True,
        help_text="Notes displayed below items before subtotal (e.g. warranty info)",
    )

    # E-signature data URLs (base64)
    authorized_signature = models.TextField(blank=True)
    client_signature = models.TextField(blank=True)

    # Printed name & date below signatures
    authorized_name = models.CharField(max_length=255, blank=True)
    authorized_date = models.DateField(null=True, blank=True)
    client_acceptance_name = models.CharField(max_length=255, blank=True)
    client_acceptance_date = models.DateField(null=True, blank=True)

    created_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="quotations_created",
    )

    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Quotation #{self.pk} - {self.client_name or 'No Client'}"

    @property
    def item_discount_total(self):
        return sum((i.discount_amount for i in self.items.all()), Decimal("0.00"))

    @property
    def total_discount_amount(self):
        return self.discount_amount + self.item_discount_total

    def save(self, *args, **kwargs):
        # Recalculate totals from items
        if self.pk:
            items = self.items.all()
            # Subtotal = sum of (quantity * unit_price) for all items
            item_total = sum(
                i.quantity * i.unit_price for i in items
            )
            # Subtotal before any discount
            self.subtotal = item_total
            # Total = subtotal - per-item discounts - overall discount
            self.total = max(
                Decimal("0.00"),
                item_total - self.total_discount_amount
            )
        super().save(*args, **kwargs)


class QuotationItem(models.Model):
    quotation = models.ForeignKey(
        Quotation, on_delete=models.CASCADE, related_name="items"
    )
    aircon_model = models.ForeignKey(
        "installations.AirconModel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Optional link to an aircon model for this line item",
    )
    aircon_unit = models.ForeignKey(
        "installations.AirconUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Optional link to a specific aircon unit from inventory",
    )
    description = models.CharField(max_length=500)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    promo_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Promotional / discounted price (used in price_list quotations)",
    )
    total_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Per-item discount amount",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.description} x{self.quantity}"

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    @property
    def discounted_price(self) -> Decimal:
        """Calculate price after applying per-item discount"""
        return max(Decimal("0.00"), self.total_price - self.discount_amount)


class QuotationPayment(models.Model):
    """Structured payment record for a quotation (e.g. downpayment, completion)."""

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        GCASH = "gcash", "GCash"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"

    quotation = models.ForeignKey(
        Quotation, on_delete=models.CASCADE, related_name="payments"
    )
    label = models.CharField(
        max_length=255,
        help_text="e.g. '50% Downpayment', '50% Upon Job Completion'",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(
        max_length=20, choices=PaymentMethod.choices, blank=True
    )
    payment_date = models.DateField(null=True, blank=True)
    reference_number = models.CharField(max_length=100, blank=True)
    si_number = models.CharField(
        max_length=100, blank=True, help_text="Sales Invoice / Receipt number"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.label} — ₱{self.amount}"


class QuotationPriceListTemplate(models.Model):
    """Template for managing aircon models and brands in price list quotations."""

    name = models.CharField(
        max_length=255,
        help_text="Template name (e.g., 'Standard Price List 2024')",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this price list template",
    )

    # Optionally link to specific aircon models to include
    aircon_models = models.ManyToManyField(
        "installations.AirconModel",
        blank=True,
        related_name="price_list_templates",
        help_text="Aircon models to include in this price list. Leave empty to include all.",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Whether this template is available for use",
    )
    is_default = models.BooleanField(
        default=False,
        help_text="If true, auto-selected when creating a new price list quotation",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "name"]

    def __str__(self):
        return f"Price List Template: {self.name}"
