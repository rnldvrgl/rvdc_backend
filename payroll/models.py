from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class TimeEntry(models.Model):
    """
    A raw time entry for an employee (technician or any user).
    Captures a single continuous worked interval with an optional unpaid break.

    Hours are computed as:
        effective_hours = max((clock_out - clock_in) - unpaid_break_minutes, 0)
    """

    SOURCE_CHOICES = [
        ("manual", "Manual"),
        ("schedule", "From Schedule"),
        ("import", "Imported"),
    ]

    employee = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.CASCADE,
        related_name="time_entries",
    )
    clock_in = models.DateTimeField()
    clock_out = models.DateTimeField()
    unpaid_break_minutes = models.PositiveIntegerField(default=0)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="manual")
    approved = models.BooleanField(
        default=True,
        help_text="Only approved entries are included in payroll computations.",
    )
    notes = models.TextField(blank=True)
    auto_closed = models.BooleanField(
        default=False,
        help_text="True if the session was auto-closed at shift end due to missing clock_out.",
    )
    is_deleted = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["employee", "clock_in"]),
            models.Index(fields=["clock_in"]),
            models.Index(fields=["approved"]),
        ]
        ordering = ["-clock_in"]

    def __str__(self):
        return f"{self.employee_id} | {self.clock_in} — {self.clock_out}"

    def clean(self):
        super().clean()
        if self.clock_out and self.clock_in and self.clock_out <= self.clock_in:
            raise ValidationError({"clock_out": "clock_out must be after clock_in."})
        if self.unpaid_break_minutes and self.unpaid_break_minutes > 24 * 60:
            raise ValidationError(
                {"unpaid_break_minutes": "Break minutes exceed 24 hours."}
            )

    @property
    def effective_hours(self) -> Decimal:
        """
        Returns worked hours minus unpaid break, rounded to 4 decimal places.
        """
        if not self.clock_in or not self.clock_out:
            return Decimal("0.0")

        delta = self.clock_out - self.clock_in
        total_minutes = Decimal(delta.total_seconds()) / Decimal(60)
        effective_minutes = total_minutes - Decimal(self.unpaid_break_minutes or 0)
        hours = max(effective_minutes, Decimal("0")) / Decimal(60)
        return self._q(hours, places=4)

    @property
    def work_date(self) -> date:
        # Primary work date (based on clock_in local date)
        local_dt = (
            timezone.localtime(self.clock_in)
            if timezone.is_aware(self.clock_in)
            else self.clock_in
        )
        return local_dt.date()

    @staticmethod
    def _q(value: Decimal, places=2) -> Decimal:
        exp = Decimal(10) ** -places
        return value.quantize(exp, rounding=ROUND_HALF_UP)


class AdditionalEarning(models.Model):
    """
    Additional earnings for an employee within a given date.
    Can represent manual overtime pay, installation percentages, or any custom payout.
    These are included in weekly payroll computations if approved and within the week range.
    """

    EARNING_TYPES = [
        ("overtime", "Overtime"),
        ("installation_pct", "Installation Percentage"),
        ("custom", "Custom"),
    ]

    employee = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.CASCADE,
        related_name="additional_earnings",
    )
    earning_date = models.DateField()
    category = models.CharField(max_length=32, choices=EARNING_TYPES, default="custom")
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    description = models.TextField(blank=True)
    reference = models.CharField(max_length=100, blank=True)

    approved = models.BooleanField(
        default=True,
        help_text="Only approved additional earnings are included in payroll computations.",
    )
    is_deleted = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["employee", "earning_date"]),
            models.Index(fields=["earning_date"]),
            models.Index(fields=["approved"]),
        ]
        ordering = ["-earning_date"]

    def __str__(self):
        return f"{self.employee_id} | {self.category} | {self.earning_date} | {self.amount}"


class WeeklyPayroll(models.Model):
    """
    A weekly payroll summary for an employee.

    - week_start: The date representing the start of the payroll week (e.g., Monday).
    - Computation is weekly: regular up to overtime_threshold hours; remainder = overtime.
    - Deductions can include percent and flat components by name in the JSON field.

    Use compute_from_time_entries() to recompute based on approved TimeEntry rows.
    """

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("approved", "Approved"),
        ("paid", "Paid"),
    ]

    employee = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.CASCADE,
        related_name="weekly_payrolls",
    )
    week_start = models.DateField(
        help_text="Start date of the payroll week (recommended: Monday)."
    )

    # Configuration for this week
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)
    overtime_threshold = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("40.00")
    )
    overtime_multiplier = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("1.50")
    )

    # Hours snapshot
    regular_hours = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("0.00")
    )
    overtime_hours = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("0.00")
    )

    allowances = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    additional_earnings_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    gross_pay = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    # Deductions
    deductions = models.JSONField(
        default=dict,
        help_text='Map of deduction name -> amount. Example: {"Tax": 120.55, "Benefits": 35.00}',
    )
    total_deductions = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    # Final
    net_pay = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    notes = models.TextField(blank=True)

    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("employee", "week_start")
        indexes = [
            models.Index(fields=["employee", "week_start"]),
            models.Index(fields=["status"]),
        ]
        ordering = ["-week_start", "employee_id"]

    def __str__(self):
        return f"Payroll {self.employee_id} @ {self.week_start}"

    @property
    def week_end(self) -> date:
        # Exclusive end date (week_start + 7 days)
        return self.week_start + timedelta(days=7)

    @property
    def total_hours(self) -> Decimal:
        return (self.regular_hours or Decimal("0")) + (
            self.overtime_hours or Decimal("0")
        )

    def set_deduction(self, name: str, amount: Decimal):
        d = dict(self.deductions or {})
        d[name] = self._q(Decimal(amount or 0))
        self.deductions = d
        self.total_deductions = self._q(sum(Decimal(x) for x in d.values()))

    def remove_deduction(self, name: str):
        d = dict(self.deductions or {})
        d.pop(name, None)
        self.deductions = d
        self.total_deductions = self._q(sum(Decimal(x) for x in d.values()))

    def compute_from_time_entries(
        self,
        *,
        include_unapproved: bool = False,
        allowances: Decimal | None = None,
        extra_flat_deductions: dict[str, Decimal] | None = None,
        percent_deductions: dict[str, Decimal] | None = None,
    ):
        """
        Recompute hours and pay based on time entries within [week_start, week_end).

        - include_unapproved: include unapproved time entries if True.
        - allowances: override allowances for this computation (optional).
        - extra_flat_deductions: dict of additional flat deductions.
        - percent_deductions: dict of percentage rates to apply on gross (e.g., {'Tax': 0.12}).
        """
        start_dt = self._week_start_as_datetime(self.week_start)
        end_dt = self._week_start_as_datetime(self.week_end)

        entries = self.employee.time_entries.filter(
            is_deleted=False, clock_in__gte=start_dt, clock_in__lt=end_dt
        )
        if not include_unapproved:
            entries = entries.filter(approved=True)

        total_hours = sum((e.effective_hours for e in entries), Decimal("0"))
        total_hours = self._q(total_hours, places=2)

        reg_hours = min(total_hours, self.overtime_threshold or Decimal("40.00"))
        ot_hours = max(total_hours - reg_hours, Decimal("0"))

        self.regular_hours = self._q(reg_hours)
        self.overtime_hours = self._q(ot_hours)

        # Gross
        hr = Decimal(self.hourly_rate or 0)
        ot_mult = Decimal(self.overtime_multiplier or Decimal("1.50"))
        base = (self.regular_hours * hr) + (self.overtime_hours * hr * ot_mult)
        self.allowances = self._q(
            Decimal(allowances)
            if allowances is not None
            else Decimal(self.allowances or 0)
        )

        # Include approved AdditionalEarning within the week range
        add_qs = self.employee.additional_earnings.filter(
            is_deleted=False,
            earning_date__gte=self.week_start,
            earning_date__lt=self.week_end,
        )
        if not include_unapproved:
            add_qs = add_qs.filter(approved=True)

        additional_total = sum((Decimal(e.amount) for e in add_qs), Decimal("0"))
        self.additional_earnings_total = self._q(additional_total)
        self.gross_pay = self._q(
            base + self.allowances + self.additional_earnings_total
        )

        # Deductions
        deductions_map: dict[str, Decimal] = {
            k: Decimal(v) for k, v in (self.deductions or {}).items()
        }
        if percent_deductions:
            for name, rate in percent_deductions.items():
                deductions_map[name] = self._q(self.gross_pay * Decimal(rate or 0))
        if extra_flat_deductions:
            for name, amt in extra_flat_deductions.items():
                deductions_map[name] = self._q(Decimal(amt or 0))

        self.deductions = {k: self._q(v) for k, v in deductions_map.items()}
        self.total_deductions = self._q(sum(self.deductions.values()))
        self.net_pay = self._q(self.gross_pay - self.total_deductions)

    def _week_start_as_datetime(self, d: date) -> datetime:
        """
        Convert a date to a timezone-aware start-of-day datetime according to settings.TIME_ZONE.
        """
        dt = datetime.combine(d, time.min)
        if settings.USE_TZ:
            tz = timezone.get_current_timezone()
            return tz.localize(dt)
        return dt

    @staticmethod
    def _q(value: Decimal, places=2) -> Decimal:
        exp = Decimal(10) ** -places
        return Decimal(value).quantize(exp, rounding=ROUND_HALF_UP)


class PayrollSettings(models.Model):
    """
    Global payroll configuration for attendance classification, grace, auto-close, and holiday premiums.

    - shift_start / shift_end: Defines the standard daily shift window (e.g., 08:00–18:00).
    - grace_minutes: Threshold-only grace used for attendance classification (does not clip edges).
    - auto_close_enabled: If True, sessions missing clock_out are auto-closed at shift_end.
    - holiday_special_pct: Premium on base daily-rate for special non-working holiday (e.g., 0.30 = +30%).
    - holiday_regular_pct: Premium on base daily-rate for regular holiday (e.g., 1.00 = +100%).
    """

    shift_start = models.TimeField(default=time(8, 0))
    shift_end = models.TimeField(default=time(18, 0))

    grace_minutes = models.PositiveIntegerField(
        default=15,
        help_text="Threshold-only grace minutes for attendance classification.",
    )

    auto_close_enabled = models.BooleanField(
        default=True,
        help_text="Auto-close sessions missing clock_out at shift_end and mark as auto_closed.",
    )

    holiday_special_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.30"),
        help_text="Premium rate for special non-working holidays applied to base daily-rate portion.",
    )
    holiday_regular_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("1.00"),
        help_text="Premium rate for regular holidays applied to base daily-rate portion.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Payroll Settings"
        verbose_name_plural = "Payroll Settings"

    def __str__(self):
        return f"PayrollSettings ({self.shift_start}-{self.shift_end}, grace={self.grace_minutes}m)"
