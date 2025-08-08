from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.timezone import now
from utils.enums import CollectionType, ChequeStatus, BankChoices


class ChequeCollection(models.Model):

    date_collected = models.DateTimeField()
    client = models.ForeignKey(
        "clients.Client", on_delete=models.CASCADE, related_name="cheque_collections"
    )
    issued_by = models.CharField(max_length=100)
    billing_amount = models.DecimalField(max_digits=12, decimal_places=2)
    cheque_amount = models.DecimalField(max_digits=12, decimal_places=2)
    cheque_number = models.CharField(max_length=50)
    cheque_date = models.DateTimeField(
        help_text="Date written on the cheque (can be post-dated)."
    )
    bank_name = models.CharField(
        max_length=100,
        help_text="Name of the bank that issued the cheque.",
        choices=BankChoices.choices,
    )
    deposit_bank = models.CharField(
        max_length=100,
        help_text="Name of the bank where the cheque will be deposited or encashed.",
        choices=BankChoices.choices,
        blank=True,
        null=True,
    )

    or_number = models.CharField(max_length=50, blank=True, null=True)

    sales_transaction = models.ForeignKey(
        "sales.SalesTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cheque_collections",
        help_text="Linked sales transaction, if available.",
    )

    collection_type = models.CharField(
        max_length=20,
        choices=CollectionType.choices,
        default=CollectionType.CLIENT_DELIVERED,
    )

    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        limit_choices_to={"role__in": ["manager", "clerk", "admin"]},
        null=True,
        blank=True,
        related_name="collected_cheques",
        help_text="Only required if Collection Type is 'Picked Up by Staff'.",
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=20,
        choices=ChequeStatus.choices,
        default=ChequeStatus.PENDING,
    )

    class Meta:
        ordering = ["-date_collected"]
        indexes = [
            models.Index(fields=["date_collected"]),
            models.Index(fields=["cheque_number"]),
            models.Index(fields=["collection_type"]),
            models.Index(fields=["cheque_date"]),
            models.Index(fields=["sales_transaction"]),
        ]

    def __str__(self):
        return (
            f"Cheque {self.cheque_number} - {self.client.name} ({self.date_collected})"
        )

    def save(self, *args, **kwargs):
        # Automatically determine collection type based on collected_by
        self.collection_type = (
            CollectionType.PICKED_UP
            if self.collected_by
            else CollectionType.CLIENT_DELIVERED
        )
        super().save(*args, **kwargs)

    def clean(self):
        today = now().date()

        # Require collected_by if picked up
        if self.collection_type == CollectionType.PICKED_UP and not self.collected_by:
            raise ValidationError(
                {
                    "collected_by": "Must be set if collection type is 'Picked Up by Staff'."
                }
            )

        # If cheque is marked deposited or encashed, enforce rules
        if self.status in [ChequeStatus.ENCAHSED, ChequeStatus.DEPOSITED]:
            # Cannot deposit/encash before cheque date
            if self.cheque_date > today:
                raise ValidationError(
                    {
                        "cheque_date": "Cannot mark cheque as deposited or encashed before its cheque date."
                    }
                )

            # Must have deposit bank specified
            if not self.deposit_bank:
                raise ValidationError(
                    {
                        "deposit_bank": "Must specify the bank where the cheque will be deposited or encashed."
                    }
                )

        # Require a reference (sales transaction or OR number) for non-pending cheques
        if self.status != ChequeStatus.PENDING and not (
            self.sales_transaction or self.or_number
        ):
            raise ValidationError(
                "Non-pending cheques must be linked to a Sales Transaction or have an OR number."
            )
