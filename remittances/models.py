from decimal import Decimal
from django.db import models
from django.utils.timezone import localdate
from datetime import timedelta

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
    declared_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    remitted_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True
    )
    is_remitted = models.BooleanField(default=False)
    manually_adjusted = models.BooleanField(default=False)

    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True, auto_now=True)
    remittance_date = models.DateField(null=True, blank=True, help_text="Business date for this remittance")

    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ("stall", "remittance_date")
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
    def balance(self):
        expected = self.expected_remittance
        try:
            declared = Decimal(self.cash_breakdown.total_cash_declared)
        except CashDenominationBreakdown.DoesNotExist:
            declared = Decimal("0")

        return declared - expected

    @property
    def expected_remittance(self):
        collected_cash = self.total_sales_cash or Decimal("0")
        expenses = self.total_expenses or Decimal("0")

        # Use THIS remittance's date to look up the previous day's COD
        remittance_date = self.created_at.date() if self.created_at else None
        if remittance_date:
            cod_info = RemittanceRecord.get_cod_for_date(self.stall, remittance_date)
        else:
            cod_info = RemittanceRecord.get_cod_for_today(self.stall)
        cod_yesterday = Decimal(cod_info.get("cod_amount", 0) or 0)

        return max(0, collected_cash + cod_yesterday - expenses)

    @classmethod
    def get_cod_for_date(cls, stall: Stall, target_date) -> dict:
        """
        Returns COD info for a given date based on the remittance of the day before.
        If no remittance was made the day before, fallback to that day's total_sales_cash.
        """
        previous_day = target_date - timedelta(days=1)

        try:
            remittance = cls.objects.get(stall=stall, remittance_date=previous_day)

            if hasattr(remittance, "cash_breakdown"):
                return {
                    "cod_amount": remittance.cash_breakdown.cod_amount,
                    "cod_breakdown": remittance.cash_breakdown.cod_breakdown,
                    "source": "remitted",
                    "date": str(previous_day),
                }
            else:
                return {
                    "cod_amount": 0,
                    "cod_breakdown": {},
                    "source": "remitted (no breakdown)",
                    "date": str(previous_day),
                }

        except cls.DoesNotExist:
            return {
                "cod_amount": 0,
                "cod_breakdown": None,
                "source": "no_remittance",
                "date": str(previous_day),
            }

    @classmethod
    def get_cod_for_today(cls, stall: Stall) -> dict:
        """
        Returns COD info for today based on the remittance of yesterday.
        If no remittance was made, fallback to yesterday's total_sales_cash.
        """
        today = localdate()
        return cls.get_cod_for_date(stall, today)


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
    count_200 = models.PositiveIntegerField(default=0)
    count_100 = models.PositiveIntegerField(default=0)
    count_50 = models.PositiveIntegerField(default=0)
    count_20 = models.PositiveIntegerField(default=0)
    count_10 = models.PositiveIntegerField(default=0)
    count_5 = models.PositiveIntegerField(default=0)
    count_1 = models.PositiveIntegerField(default=0)

    # Declared denominations (what the cashier actually has)
    declared_count_1000 = models.PositiveIntegerField(default=0)
    declared_count_500 = models.PositiveIntegerField(default=0)
    declared_count_200 = models.PositiveIntegerField(default=0)
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
            (200, "declared_count_200" if declared else "count_200"),
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
            + self.count_200 * 200
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
            + self.declared_count_200 * 200
            + self.declared_count_100 * 100
            + self.declared_count_50 * 50
            + self.declared_count_20 * 20
            + self.declared_count_10 * 10
            + self.declared_count_5 * 5
            + self.declared_count_1 * 1
        )

    @property
    def cod_amount(self) -> int:
        return sum(
            max(0, (getattr(self, f"declared_count_{d}") - getattr(self, f"count_{d}")))
            * d
            for d in [1000, 500, 200, 100, 50, 20, 10, 5, 1]
        )

    @property
    def cod_breakdown(self) -> dict:
        """
        Returns a dictionary with denomination as key and COD count as value,
        only including denominations where there is a difference.
        """
        breakdown = {}
        for denom in [1000, 500, 200, 100, 50, 20, 10, 5, 1]:
            declared = getattr(self, f"declared_count_{denom}")
            remitted = getattr(self, f"count_{denom}")
            diff = declared - remitted
            if diff > 0:
                breakdown[denom] = diff
        return breakdown

    def __str__(self):
        return f"Cash Breakdown for {self.remittance}"

    class Meta:
        verbose_name = "Cash Denomination Breakdown"
        verbose_name_plural = "Cash Denomination Breakdowns"
