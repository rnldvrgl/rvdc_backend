from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class ActiveClientManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class Client(models.Model):
    full_name = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=15, null=True, blank=True, unique=True)
    province = models.CharField(max_length=50, blank=True, default="")
    city = models.CharField(max_length=50, blank=True, default="")
    barangay = models.CharField(max_length=50, null=True, blank=True)
    address = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    is_blocklisted = models.BooleanField(default=False)
    # Client fund balance — tracks available funds from deposits (remittable advances)
    fund_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Available client fund balance for service payments"
    )

    objects = ActiveClientManager()
    all_objects = models.Manager()

    def __str__(self):
        return f"{self.full_name} - {self.contact_number}"

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["full_name"]),
            models.Index(fields=["is_deleted"]),
            models.Index(fields=["is_deleted", "-created_at"]),
        ]


class ClientFundDeposit(models.Model):
    """Record of client fund deposits (advance payments that become remittable income)."""

    client = models.ForeignKey(
        Client, on_delete=models.PROTECT, related_name="fund_deposits"
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Amount deposited into client fund"
    )
    deposit_date = models.DateTimeField(
        default=lambda: __import__('django.utils.timezone', fromlist=['now']).now(),
        help_text="Date the fund was received (used for remittance recording)"
    )
    payment_method = models.CharField(
        max_length=10,
        choices=[
            ('cash', 'Cash'),
            ('gcash', 'GCash'),
            ('debit', 'Debit'),
            ('credit', 'Credit'),
            ('cheque', 'Cheque'),
        ],
        help_text="How the fund was received"
    )
    notes = models.TextField(
        blank=True,
        help_text="Notes about this fund deposit (e.g., 50% downpayment for pre-order #123)"
    )
    recorded_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='client_fund_deposits_recorded',
        help_text="User who recorded this fund deposit"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-deposit_date"]
        indexes = [
            models.Index(fields=["client", "-deposit_date"]),
            models.Index(fields=["deposit_date"]),
        ]

    def __str__(self):
        return f"Client Fund Deposit: {self.client.full_name} - ₱{self.amount} on {self.deposit_date.date()}"
