from decimal import Decimal

from django.db import models
from django.utils import timezone


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

    def save(self, *args, **kwargs):
        # Recalculate totals from items
        if self.pk:
            item_total = sum(
                i.quantity * i.unit_price for i in self.items.all()
            )
            self.subtotal = item_total
            self.total = max(Decimal("0.00"), item_total - self.discount_amount)
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
    total_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
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
