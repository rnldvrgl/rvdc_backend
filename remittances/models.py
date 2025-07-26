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
    coins_remitted = models.BooleanField(default=False)

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
        unique_together = ("stall", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.stall.name} - {self.date}"

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
        if hasattr(self, "cash_breakdown") and not self.coins_remitted:
            expected -= self.cash_breakdown.cod_amount
        return expected

    @property
    def balance(self):
        return self.expected_remittance - self.remitted_amount


class CashDenominationBreakdown(models.Model):
    """
    Physical cash denomination count for a remittance.
    Splits actual remitted vs. cash on drawer (COD).
    """

    remittance = models.OneToOneField(
        RemittanceRecord, on_delete=models.CASCADE, related_name="cash_breakdown"
    )

    # Remitted denominations
    count_1000 = models.PositiveIntegerField(default=0)
    count_500 = models.PositiveIntegerField(default=0)
    count_100 = models.PositiveIntegerField(default=0)
    count_50 = models.PositiveIntegerField(default=0)

    # Coins (may be remitted or left as COD)
    count_20 = models.PositiveIntegerField(default=0)
    count_10 = models.PositiveIntegerField(default=0)
    count_5 = models.PositiveIntegerField(default=0)
    count_1 = models.PositiveIntegerField(default=0)

    coins_remitted = models.BooleanField(default=True)

    @staticmethod
    def compute_total_from_counts(data: dict, coins_remitted: bool = True):
        """
        Compute the total cash based on denomination counts,
        optionally including coins depending on remittance flag.
        """
        total = (
            data.get("count_1000", 0) * 1000
            + data.get("count_500", 0) * 500
            + data.get("count_100", 0) * 100
            + data.get("count_50", 0) * 50
        )
        if coins_remitted:
            total += (
                data.get("count_20", 0) * 20
                + data.get("count_10", 0) * 10
                + data.get("count_5", 0) * 5
                + data.get("count_1", 0) * 1
            )
        return total

    @property
    def total_remitted_amount(self):
        """
        Compute actual remitted amount including coins only if remitted.
        """
        base = (
            self.count_1000 * 1000
            + self.count_500 * 500
            + self.count_100 * 100
            + self.count_50 * 50
        )
        if self.coins_remitted:
            base += (
                self.count_20 * 20
                + self.count_10 * 10
                + self.count_5 * 5
                + self.count_1 * 1
            )
        return base

    @property
    def cod_amount(self):
        """
        Shows all coin amounts whether or not they were remitted,
        for record-keeping or discrepancy analysis.
        """
        return (
            self.count_20 * 20
            + self.count_10 * 10
            + self.count_5 * 5
            + self.count_1 * 1
        )

    @property
    def total_cash_declared(self):
        """
        Total physical cash declared (remitted + coins left as COD).
        """
        return self.total_remitted_amount + (
            0 if self.coins_remitted else self.cod_amount
        )

    def __str__(self):
        return f"Cash Breakdown for {self.remittance}"

    class Meta:
        verbose_name = "Cash Denomination Breakdown"
        verbose_name_plural = "Cash Denomination Breakdowns"
