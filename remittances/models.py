from django.db import models
from django.utils import timezone

from users.models import CustomUser
from inventory.models import Stall


class RemittanceRecord(models.Model):
    """
    Aggregated financial report and remittance status for a stall per business day.
    """

    stall = models.ForeignKey(Stall, on_delete=models.CASCADE)

    # Sales totals by payment method
    total_sales_cash = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_sales_gcash = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_sales_credit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_sales_debit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_sales_cheque = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Expense deductions
    total_expenses = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Actual remittance details
    remitted_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    remitted_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True
    )
    is_remitted = models.BooleanField(default=False)

    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True, auto_now=True)

    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ("stall", "created_at")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.stall.name} - {self.created_at}"

    @property
    def total_collected(self):
        return (
            self.total_sales_cash
            + self.total_sales_gcash
            + self.total_sales_credit
            + self.total_sales_debit
            + self.total_sales_cheque
        )

    @property
    def expected_remittance(self):
        expected = self.total_collected - self.total_expenses
        if hasattr(self, "cash_breakdown"):
            expected -= self.cash_breakdown.cod_amount
        return expected

    @property
    def balance(self):
        return self.expected_remittance - self.remitted_amount


class CashDenominationBreakdown(models.Model):
    """
    Physical cash denomination count for a remittance.
    Tracks actual remitted vs. cash on drawer (COD).
    """

    remittance = models.OneToOneField(
        RemittanceRecord, on_delete=models.CASCADE, related_name="cash_breakdown"
    )

    # Remitted denominations
    count_1000 = models.PositiveIntegerField(default=0)
    count_500 = models.PositiveIntegerField(default=0)
    count_100 = models.PositiveIntegerField(default=0)
    count_50 = models.PositiveIntegerField(default=0)
    count_20 = models.PositiveIntegerField(default=0)
    count_10 = models.PositiveIntegerField(default=0)
    count_5 = models.PositiveIntegerField(default=0)
    count_1 = models.PositiveIntegerField(default=0)

    # Declared denominations (what the cashier actually has)
    declared_count_1000 = models.PositiveIntegerField(default=0)
    declared_count_500 = models.PositiveIntegerField(default=0)
    declared_count_100 = models.PositiveIntegerField(default=0)
    declared_count_50 = models.PositiveIntegerField(default=0)
    declared_count_20 = models.PositiveIntegerField(default=0)
    declared_count_10 = models.PositiveIntegerField(default=0)
    declared_count_5 = models.PositiveIntegerField(default=0)
    declared_count_1 = models.PositiveIntegerField(default=0)

    @staticmethod
    def compute_total_from_counts(data: dict, declared: bool = False) -> int:
        denom_map = [
            (1000, "declared_count_1000" if declared else "count_1000"),
            (500, "declared_count_500" if declared else "count_500"),
            (100, "declared_count_100" if declared else "count_100"),
            (50, "declared_count_50" if declared else "count_50"),
            (20, "declared_count_20" if declared else "count_20"),
            (10, "declared_count_10" if declared else "count_10"),
            (5, "declared_count_5" if declared else "count_5"),
            (1, "declared_count_1" if declared else "count_1"),
        ]
        total = 0
        for value, key in denom_map:
            count = data.get(key, 0) or 0
            total += count * value
        return total

    @property
    def total_remitted_amount(self) -> int:
        return (
            self.count_1000 * 1000
            + self.count_500 * 500
            + self.count_100 * 100
            + self.count_50 * 50
            + self.count_20 * 20
            + self.count_10 * 10
            + self.count_5 * 5
            + self.count_1 * 1
        )

    @property
    def total_cash_declared(self) -> int:
        return (
            self.declared_count_1000 * 1000
            + self.declared_count_500 * 500
            + self.declared_count_100 * 100
            + self.declared_count_50 * 50
            + self.declared_count_20 * 20
            + self.declared_count_10 * 10
            + self.declared_count_5 * 5
            + self.declared_count_1 * 1
        )

    @property
    def cod_amount(self):
        return sum(
            max(0, (getattr(self, f"declared_count_{d}") - getattr(self, f"count_{d}")))
            * d
            for d in [1000, 500, 100, 50, 20, 10, 5, 1]
        )

    def __str__(self):
        return f"Cash Breakdown for {self.remittance}"

    class Meta:
        verbose_name = "Cash Denomination Breakdown"
        verbose_name_plural = "Cash Denomination Breakdowns"
