from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.timezone import get_current_timezone, make_aware


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



class Holiday(models.Model):
    KIND_CHOICES = [
        ("regular", "Regular Holiday"),
        ("special_non_working", "Special Non-Working Holiday"),
    ]
    date = models.DateField(unique=True)
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["date", "kind"]),
        ]

    def __str__(self):
        return f"{self.date} - {self.name} ({self.kind})"


class ManualDeduction(models.Model):
    """
    Manual deductions that can be applied to employee payrolls.
    Three types:
    1. per_employee: Specific one-time or recurring deduction for a single employee
    2. recurring_all: Recurring deduction type that applies to all employees
    3. onetime_all: One-time deduction for all employees
    """

    DEDUCTION_TYPES = [
        ("per_employee", "Per Employee"),
        ("recurring_all", "Recurring for All"),
        ("onetime_all", "One-Time for All"),
    ]

    name = models.CharField(max_length=100, help_text="Deduction name (e.g., Loan, Uniform, Cash Advance)")
    description = models.TextField(blank=True)
    deduction_type = models.CharField(max_length=20, choices=DEDUCTION_TYPES)

    # For per_employee deductions only
    employee = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="manual_deductions",
        help_text="Required for per_employee deductions"
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    effective_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date when deduction becomes effective. Required for recurring deductions, optional for one-time (auto-applied to next payroll)"
    )
    end_date = models.DateField(null=True, blank=True, help_text="Optional end date for recurring deductions")
    is_active = models.BooleanField(default=True)

    # For one-time deductions tracking
    applied_date = models.DateField(null=True, blank=True, help_text="Date when onetime deduction was applied")

    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_deductions",
    )

    class Meta:
        indexes = [
            models.Index(fields=["deduction_type", "is_active"]),
            models.Index(fields=["employee", "is_active"]),
            models.Index(fields=["effective_date"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        if self.deduction_type == "per_employee":
            return f"{self.name} - {self.employee.get_full_name() if self.employee else 'N/A'} - ₱{self.amount}"
        return f"{self.name} ({self.get_deduction_type_display()}) - ₱{self.amount}"

    def clean(self):
        # Validate that per_employee deductions have an employee
        if self.deduction_type == "per_employee" and not self.employee:
            raise ValidationError("Per employee deductions must have an employee assigned.")
        # Validate that recurring_all and onetime_all don't have an employee
        if self.deduction_type in ["recurring_all", "onetime_all"] and self.employee:
            raise ValidationError("Recurring/One-time for all deductions cannot have a specific employee.")


class TaxBracket(models.Model):
    """
    Progressive tax brackets for withholding tax computation.
    Example: 0-20833 = 0%, 20834-33332 = 20%, etc.
    """

    min_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Minimum weekly income for this bracket (inclusive)"
    )
    max_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum weekly income for this bracket (inclusive). Null = no upper limit"
    )
    base_tax = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Base tax amount for this bracket"
    )
    rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        help_text="Tax rate as decimal (e.g., 0.20 for 20%)"
    )

    effective_start = models.DateField(help_text="Date this bracket becomes effective")
    effective_end = models.DateField(
        null=True,
        blank=True,
        help_text="Date this bracket stops being effective. Null = still active"
    )

    is_active = models.BooleanField(default=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_tax_brackets"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['min_income']
        indexes = [
            models.Index(fields=['effective_start', 'is_active']),
        ]

    def __str__(self):
        max_display = f"{self.max_income}" if self.max_income else "above"
        return f"₱{self.min_income} - {max_display}: {self.rate*100}%"

    @staticmethod
    def compute_tax(gross_income: Decimal, as_of_date: date) -> Decimal:
        """
        Compute progressive withholding tax for given gross income.
        """
        brackets = TaxBracket.objects.filter(
            is_active=True,
            effective_start__lte=as_of_date,
        ).filter(
            models.Q(effective_end__isnull=True) | models.Q(effective_end__gte=as_of_date)
        ).order_by('min_income')

        tax = Decimal("0.00")

        for bracket in brackets:
            # Check if income falls in this bracket
            if gross_income <= bracket.min_income:
                break

            # Calculate taxable amount in this bracket
            bracket_max = bracket.max_income if bracket.max_income else gross_income
            taxable_in_bracket = min(gross_income, bracket_max) - bracket.min_income

            if taxable_in_bracket > 0:
                tax = bracket.base_tax + (taxable_in_bracket * bracket.rate)

        return tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class PercentageDeduction(models.Model):
    """
    Percentage-based deductions like withholding tax, HDMF savings, etc.
    Applied as a percentage of gross pay during payroll computation.
    """

    DEDUCTION_TYPES = [
        ('withholding_tax', 'Withholding Tax'),
        ('hdmf_savings', 'HDMF Savings'),
        ('custom_percent', 'Custom Percentage'),
    ]

    name = models.CharField(max_length=100)
    deduction_type = models.CharField(max_length=30, choices=DEDUCTION_TYPES)
    rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        help_text="Rate as decimal (e.g., 0.05 for 5%)"
    )

    description = models.TextField(blank=True)

    effective_start = models.DateField()
    effective_end = models.DateField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_percentage_deductions"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['deduction_type', 'is_active']),
            models.Index(fields=['effective_start']),
        ]

    def __str__(self):
        return f"{self.name} - {self.rate*100}%"


class GovernmentBenefit(models.Model):
    """
    Government-mandated benefits with employee and employer share tracking.
    Supports both fixed amounts and percentage-based calculations.
    Examples: SSS, PhilHealth, Pag-IBIG, BIR/Tax
    """

    BENEFIT_TYPES = [
        ('sss', 'SSS'),
        ('philhealth', 'PhilHealth'),
        ('pagibig', 'Pag-IBIG / HDMF'),
        ('bir_tax', 'BIR Withholding Tax'),
    ]

    CALCULATION_METHODS = [
        ('fixed', 'Fixed Amount'),
        ('percentage', 'Percentage of Gross'),
        ('progressive_tax', 'Progressive Tax Bracket'),
    ]

    benefit_type = models.CharField(max_length=20, choices=BENEFIT_TYPES)
    name = models.CharField(max_length=100, help_text="Display name (e.g., 'SSS Contribution')")
    calculation_method = models.CharField(max_length=20, choices=CALCULATION_METHODS)

    # For fixed amount method
    employee_share_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Fixed employee contribution amount (weekly)"
    )
    employer_share_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Fixed employer contribution amount (weekly)"
    )

    # For percentage method
    employee_share_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Employee percentage rate (e.g., 0.045 for 4.5%)"
    )
    employer_share_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Employer percentage rate (e.g., 0.08 for 8%)"
    )

    # Date effectiveness
    effective_start = models.DateField(help_text="Date this benefit configuration becomes effective")
    effective_end = models.DateField(
        null=True,
        blank=True,
        help_text="Date this benefit configuration ends (null = still active)"
    )

    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_government_benefits"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-effective_start', 'benefit_type']
        indexes = [
            models.Index(fields=['benefit_type', 'is_active']),
            models.Index(fields=['effective_start', 'effective_end']),
        ]

    def __str__(self):
        return f"{self.get_benefit_type_display()} - {self.name} ({self.effective_start})"

    def compute_employee_share(self, gross_pay: Decimal) -> Decimal:
        """Compute employee's share of this benefit"""
        if self.calculation_method == 'fixed':
            return Decimal(self.employee_share_amount or 0)
        elif self.calculation_method == 'percentage':
            return (gross_pay * Decimal(self.employee_share_rate or 0)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        elif self.calculation_method == 'progressive_tax':
            # For BIR tax, use TaxBracket computation
            return TaxBracket.compute_tax(gross_pay, self.effective_start)
        return Decimal("0.00")

    def compute_employer_share(self, gross_pay: Decimal) -> Decimal:
        """Compute employer's share of this benefit"""
        if self.calculation_method == 'fixed':
            return Decimal(self.employer_share_amount or 0)
        elif self.calculation_method == 'percentage':
            return (gross_pay * Decimal(self.employer_share_rate or 0)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        # Progressive tax has no employer share
        return Decimal("0.00")


class WeeklyPayroll(models.Model):

    """
    A weekly payroll summary for an emploee.

    - week_start: The date representing the start of the payroll week (e.g., Monday).
    - Computation is weekly: regular up to overtime_threshold hours; remainder = overtime.
    - Deductions can include percent and flat components by name in the JSON field.
    - Night differential: 22:00–06:00 hours × hourly_rate × 0.10
    - Approved OT: approved overtime requests × hourly_rate × 1.25

    Use compute_from_time_entries() to recompute based on approved TimeEntry rows.
    """

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("approved", "Approved"),
        ("paid", "Paid"),
        ("received", "Received"),
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
    # Night differential fields (computed)
    night_diff_hours = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("0.00")
    )
    night_diff_pay = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    # Approved overtime request aggregation (computed)
    approved_ot_hours = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("0.00")
    )
    approved_ot_pay = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    allowances = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    additional_earnings_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    # Holiday pay components (computed)
    holiday_pay_regular = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    holiday_pay_special = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    holiday_pay_total = models.DecimalField(
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

    # Received confirmation (employee confirms receipt after paid)
    received_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_payrolls",
    )

    # Dispute tracking (employee can dispute incorrect payroll)
    disputed = models.BooleanField(default=False)
    disputed_reason = models.TextField(blank=True)
    disputed_at = models.DateTimeField(null=True, blank=True)

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
        # Inclusive end date (week_start + 6 days)
        # For Saturday-Friday week: if week_start is Saturday, week_end is Friday
        return self.week_start + timedelta(days=6)

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

        Also computes:
        - Night differential hours (22:00–06:00) and pay at 10% of hourly rate.
        - Approved overtime request hours and pay at 1.25× hourly rate.
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

        # Night differential hours: compute overlap with 22:00–06:00 per TimeEntry
        def _overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> timedelta:
            start = max(a_start, b_start)
            end = min(a_end, b_end)
            return max(timedelta(0), end - start)

        night_hours_total = Decimal("0")
        for e in entries:
            # Iterate per day spanned by the entry
            cur_start = e.clock_in
            cur_end = e.clock_out
            # Normalize to aware datetimes
            a_start = timezone.localtime(cur_start) if timezone.is_aware(cur_start) else cur_start
            a_end = timezone.localtime(cur_end) if timezone.is_aware(cur_end) else cur_end
            cur = a_start
            while cur < a_end:
                day = cur.date()
                tz = timezone.get_current_timezone() if settings.USE_TZ else None
                # 22:00–24:00 of day
                night1_start = datetime.combine(day, time(22, 0))
                night1_end = datetime.combine(day, time(23, 59, 59)) + timedelta(seconds=1)
                # 00:00–06:00 of next day
                next_day = day + timedelta(days=1)
                night2_start = datetime.combine(next_day, time(0, 0))
                night2_end = datetime.combine(next_day, time(6, 0))
                # If using TZ, localize windows
                if settings.USE_TZ and tz:
                    night1_start = tz.localize(night1_start)
                    night1_end = tz.localize(night1_end)
                    night2_start = tz.localize(night2_start)
                    night2_end = tz.localize(night2_end)
                seg1 = _overlap(a_start, a_end, night1_start, night1_end)
                seg2 = _overlap(a_start, a_end, night2_start, night2_end)
                night_hours_total += Decimal(seg1.total_seconds() + seg2.total_seconds()) / Decimal(3600)
                # advance to next_day 06:00 to avoid infinite loop
                cur = night2_end

        self.night_diff_hours = self._q(night_hours_total, places=2)

        # Gross (regular + weekly overtime threshold)
        hr = Decimal(self.hourly_rate or 0)
        ot_mult = Decimal(self.overtime_multiplier or Decimal("1.50"))
        base = (self.regular_hours * hr) + (self.overtime_hours * hr * ot_mult)

        # Night diff pay: 10% of hourly rate per night hours
        self.night_diff_pay = self._q(self.night_diff_hours * hr * Decimal("0.10"))

        self.allowances = self._q(
            Decimal(allowances)
            if allowances is not None
            else Decimal(self.allowances or 0)
        )

        # Include approved AdditionalEarning within the week range
        add_qs = self.employee.additional_earnings.filter(
            is_deleted=False,
            earning_date__gte=self.week_start,
            earning_date__lte=self.week_end,
        )
        if not include_unapproved:
            add_qs = add_qs.filter(approved=True)

        additional_total = sum((Decimal(e.amount) for e in add_qs), Decimal("0"))
        self.additional_earnings_total = self._q(additional_total)

        # Approved Overtime Requests in range: compute hours and pay (1.25x)
        try:
            from payroll.models import (
                OvertimeRequest,  # local import to avoid circular issues during migrations
            )
            ot_req_qs = OvertimeRequest.objects.filter(
                employee=self.employee,
                approved=True,
                time_start__gte=start_dt,
                time_end__lt=end_dt,
            )
            approved_ot_hours_total = Decimal("0")
            for req in ot_req_qs:
                span = req.time_end - req.time_start
                approved_ot_hours_total += Decimal(span.total_seconds()) / Decimal(3600)
            self.approved_ot_hours = self._q(approved_ot_hours_total, places=2)
            self.approved_ot_pay = self._q(self.approved_ot_hours * hr * Decimal("1.25"))
        except Exception:
            # If model not ready yet (during initial migration), default to zero
            self.approved_ot_hours = self._q(Decimal("0"), places=2)
            self.approved_ot_pay = self._q(Decimal("0"))

        # Compute holiday premiums (regular and special non-working)
        # Build worked-hours-per-date map for this week
        from collections import defaultdict
        worked_hours_by_date: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
        for e in entries:
            a_start = timezone.localtime(e.clock_in) if timezone.is_aware(e.clock_in) else e.clock_in
            a_end = timezone.localtime(e.clock_out) if timezone.is_aware(e.clock_out) else e.clock_out
            cur = a_start
            while cur < a_end:
                day = cur.date()
                # Day window: [00:00, 24:00) local
                day_start = datetime.combine(day, time(0, 0))
                next_day = day + timedelta(days=1)
                day_end = datetime.combine(next_day, time(0, 0))
                if settings.USE_TZ:
                    tz = timezone.get_current_timezone()
                    day_start = tz.localize(day_start)
                    day_end = tz.localize(day_end)
                seg = _overlap(a_start, a_end, day_start, day_end)
                worked_hours_by_date[day] += max(Decimal("0"), Decimal(seg.total_seconds()) / Decimal(3600))
                cur = day_end

        # Default settings
        try:
            settings_obj = PayrollSettings.objects.first()
        except Exception:
            settings_obj = None

        day_hours = Decimal(getattr(settings_obj, "holiday_day_hours", Decimal("8.00")) or "8.00")
        reg_pct = Decimal(getattr(settings_obj, "holiday_regular_pct", Decimal("1.00")) or "1.00")
        spec_pct = Decimal(getattr(settings_obj, "holiday_special_pct", Decimal("0.30")) or "0.30")
        reg_no_work = bool(getattr(settings_obj, "regular_holiday_no_work_pays", True))
        spec_no_work = bool(getattr(settings_obj, "special_holiday_no_work_pays", False))

        daily_rate = hr * (day_hours or Decimal("0"))

        # Reset holiday fields
        self.holiday_pay_regular = self._q(Decimal("0"))
        self.holiday_pay_special = self._q(Decimal("0"))

        # Fetch holidays in range
        try:
            from payroll.models import Holiday
            holidays = Holiday.objects.filter(
                is_deleted=False, date__gte=self.week_start, date__lte=self.week_end
            )
        except Exception:
            holidays = []

        for h in holidays:
            d = h.date
            worked = worked_hours_by_date.get(d, Decimal("0"))
            fraction = Decimal("0")
            if day_hours and day_hours > 0:
                fraction = (worked / day_hours)
                if fraction > Decimal("1"):
                    fraction = Decimal("1")

            if h.kind == "regular":
                if worked > 0:
                    add = daily_rate * reg_pct * fraction
                else:
                    add = (daily_rate * reg_pct) if reg_no_work else Decimal("0")
                self.holiday_pay_regular = self._q(self.holiday_pay_regular + add)
            elif h.kind == "special_non_working":
                if worked > 0:
                    add = daily_rate * spec_pct * fraction
                else:
                    add = (daily_rate * spec_pct) if spec_no_work else Decimal("0")
                self.holiday_pay_special = self._q(self.holiday_pay_special + add)

        self.holiday_pay_total = self._q(self.holiday_pay_regular + self.holiday_pay_special)

        # Final gross = base + allowances + additional earnings + night diff + approved OT + holiday premiums
        self.gross_pay = self._q(
            base + self.allowances + self.additional_earnings_total + self.night_diff_pay + self.approved_ot_pay + self.holiday_pay_total
        )


        # Deductions

        deductions_map: dict[str, Decimal] = {

            k: Decimal(v) for k, v in (self.deductions or {}).items()

        }

        # Apply manual deductions
        try:
            from payroll.models import ManualDeduction

            # Get per_employee deductions for this employee
            per_employee_deductions = ManualDeduction.objects.filter(
                is_deleted=False,
                is_active=True,
                deduction_type='per_employee',
                employee=self.employee,
            )

            for deduction in per_employee_deductions:
                # Determine if this is one-time or recurring:
                # One-time: has effective_date but NO end_date (applied once)
                # Recurring: has effective_date AND end_date (applied multiple times)

                if deduction.end_date is None:
                    # One-time deduction: apply once if not yet applied
                    should_apply = False

                    if deduction.effective_date is None:
                        # No effective_date: apply to next payroll if not yet applied
                        if deduction.applied_date is None:
                            should_apply = True
                    else:
                        # Has effective_date: apply if effective_date <= week_end and not yet applied
                        if deduction.effective_date <= self.week_end and deduction.applied_date is None:
                            should_apply = True

                    if should_apply:
                        key = self._generate_deduction_key(deduction.name, deductions_map)
                        deductions_map[key] = self._q(Decimal(deduction.amount))
                        # Note: Don't mark as applied here - only mark when payroll is approved
                else:
                    # Recurring deduction: apply if within effective date range
                    if deduction.effective_date and deduction.effective_date <= self.week_end:
                        # Check if still within end_date range
                        if deduction.end_date >= self.week_start:
                            key = self._generate_deduction_key(deduction.name, deductions_map)
                            deductions_map[key] = self._q(Decimal(deduction.amount))

            # Get recurring_all deductions that apply to all employees
            recurring_all = ManualDeduction.objects.filter(
                is_deleted=False,
                is_active=True,
                deduction_type='recurring_all',
                effective_date__isnull=False,
                effective_date__lte=self.week_end,
            ).filter(
                models.Q(end_date__isnull=True) | models.Q(end_date__gte=self.week_start)
            )

            for deduction in recurring_all:
                key = self._generate_deduction_key(deduction.name, deductions_map)
                deductions_map[key] = self._q(Decimal(deduction.amount))

            # Get onetime_all deductions that haven't been applied yet
            # For onetime_all, if no effective_date, apply once in next payroll
            # If effective_date is set, apply in that specific week
            onetime_all = ManualDeduction.objects.filter(
                is_deleted=False,
                is_active=True,
                deduction_type='onetime_all',
            )

            for deduction in onetime_all:
                should_apply = False

                # If no effective_date, apply once if not yet applied
                if deduction.effective_date is None:
                    if deduction.applied_date is None:
                        should_apply = True
                else:
                    # If effective_date is set, apply only in the week containing that date
                    if (deduction.effective_date >= self.week_start and
                        deduction.effective_date < self.week_end):
                        if deduction.applied_date is None or deduction.applied_date == self.week_start:
                            should_apply = True

                if should_apply:
                    key = self._generate_deduction_key(deduction.name, deductions_map)
                    deductions_map[key] = self._q(Decimal(deduction.amount))
                    # Note: Don't mark as applied here - only mark when payroll is approved

        except Exception as e:
            # Log error but don't fail payroll computation
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error applying manual deductions: {e}")

        # Apply percentage-based deductions (HDMF savings, etc.)
        try:
            from payroll.models import PercentageDeduction

            percentage_deductions = PercentageDeduction.objects.filter(
                is_active=True,
                effective_start__lte=self.week_start,
            ).filter(
                models.Q(effective_end__isnull=True) | models.Q(effective_end__gte=self.week_start)
            )

            for pct_deduction in percentage_deductions:
                key = pct_deduction.name.lower().replace(' ', '_')
                if key not in deductions_map:
                    deductions_map[key] = self._q(self.gross_pay * Decimal(pct_deduction.rate))
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error applying percentage deductions: {e}")

        # Apply statutory weekly deductions based on DeductionRate effective for this week_start
        try:
            # Find active rates whose effective window covers this payroll week_start
            statutory_qs = DeductionRate.objects.filter(
                name__in=["sss", "philhealth", "pagibig"],
                effective_start__lte=self.week_start,
            ).filter(models.Q(effective_end__isnull=True) | models.Q(effective_end__gte=self.week_start))
            for rate in statutory_qs:
                # Do not overwrite if a manual value was already set for this name
                if rate.name not in deductions_map:
                    deductions_map[rate.name] = self._q(Decimal(rate.amount or 0))
        except Exception:
            # If anything fails, keep existing deductions_map intact
            pass

        if percent_deductions:
            for name, rate in percent_deductions.items():
                deductions_map[name] = self._q(self.gross_pay * Decimal(rate or 0))

        if extra_flat_deductions:

            for name, amt in extra_flat_deductions.items():

                deductions_map[name] = self._q(Decimal(amt or 0))



        self.deductions = {k: float(self._q(v)) for k, v in deductions_map.items()}

        self.total_deductions = self._q(sum(self.deductions.values()))

        self.net_pay = self._q(self.gross_pay - self.total_deductions)

    def compute_from_daily_attendance(
        self,
        *,
        include_unapproved: bool = False,
        allowances: Decimal | None = None,
        extra_flat_deductions: dict[str, Decimal] | None = None,
        percent_deductions: dict[str, Decimal] | None = None,
    ):
        """
        Recompute payroll based on DailyAttendance records (NEW ATTENDANCE SYSTEM).

        Business Rules:
        - Reads approved DailyAttendance records for the payroll week
        - Applies per-day overtime: any paid hours >8 per day = 1.5× rate
        - Includes late penalties (₱2 per minute) as deductions
        - Supports holiday premiums, night differential, approved OT requests

        Args:
            include_unapproved: Include unapproved attendance if True
            allowances: Override allowances for this computation
            extra_flat_deductions: Additional flat deductions
            percent_deductions: Percentage deductions on gross (e.g., {'Tax': 0.12})
        """
        from collections import defaultdict

        from attendance.models import DailyAttendance

        start_dt = self._week_start_as_datetime(self.week_start)
        end_dt = self._week_start_as_datetime(self.week_end)

        # Get daily attendance records for this week
        attendance_qs = DailyAttendance.objects.filter(
            employee=self.employee,
            date__gte=self.week_start,
            date__lte=self.week_end,
            is_deleted=False,
        )

        if not include_unapproved:
            attendance_qs = attendance_qs.filter(status='APPROVED')

        # Track hours and penalties per day
        regular_hours_total = Decimal('0.00')
        overtime_hours_total = Decimal('0.00')
        late_penalties_total = Decimal('0.00')

        for attendance in attendance_qs:
            paid_hours = Decimal(attendance.paid_hours or 0)

            # Per-day overtime: >8 paid hours = overtime at 1.5×
            if paid_hours > Decimal('8.00'):
                daily_regular = Decimal('8.00')
                daily_overtime = paid_hours - Decimal('8.00')
            else:
                daily_regular = paid_hours
                daily_overtime = Decimal('0.00')

            regular_hours_total += daily_regular
            overtime_hours_total += daily_overtime

            # Accumulate late penalties
            if attendance.late_penalty_amount:
                late_penalties_total += Decimal(attendance.late_penalty_amount)

        self.regular_hours = self._q(regular_hours_total)
        self.overtime_hours = self._q(overtime_hours_total)

        # Compute base pay
        hr = Decimal(self.hourly_rate or 0)
        ot_mult = Decimal(self.overtime_multiplier or Decimal('1.50'))
        base_pay = (self.regular_hours * hr) + (self.overtime_hours * hr * ot_mult)

        # Night differential (still computed from TimeEntry if needed for compatibility)
        # Or set to zero if you want to rely only on DailyAttendance
        self.night_diff_hours = Decimal('0.00')
        self.night_diff_pay = Decimal('0.00')

        # Allowances
        self.allowances = self._q(
            Decimal(allowances) if allowances is not None else Decimal(self.allowances or 0)
        )

        # Additional earnings (approved within week)
        add_qs = self.employee.additional_earnings.filter(
            is_deleted=False,
            earning_date__gte=self.week_start,
            earning_date__lte=self.week_end,
        )
        if not include_unapproved:
            add_qs = add_qs.filter(approved=True)

        additional_total = sum((Decimal(e.amount) for e in add_qs), Decimal('0'))
        self.additional_earnings_total = self._q(additional_total)

        # Approved overtime requests (from OvertimeRequest model)
        try:
            from payroll.models import OvertimeRequest
            ot_req_qs = OvertimeRequest.objects.filter(
                employee=self.employee,
                approved=True,
                time_start__gte=start_dt,
                time_end__lt=end_dt,
            )
            approved_ot_hours_total = Decimal('0')
            for req in ot_req_qs:
                span = req.time_end - req.time_start
                approved_ot_hours_total += Decimal(span.total_seconds()) / Decimal(3600)
            self.approved_ot_hours = self._q(approved_ot_hours_total, places=2)
            self.approved_ot_pay = self._q(self.approved_ot_hours * hr * Decimal('1.25'))
        except Exception:
            self.approved_ot_hours = Decimal('0.00')
            self.approved_ot_pay = Decimal('0.00')

        # Holiday premiums (compute based on worked days from DailyAttendance)
        try:
            settings_obj = PayrollSettings.objects.first()
        except Exception:
            settings_obj = None

        day_hours = Decimal(getattr(settings_obj, 'holiday_day_hours', Decimal('8.00')) or '8.00')
        reg_pct = Decimal(getattr(settings_obj, 'holiday_regular_pct', Decimal('1.00')) or '1.00')
        spec_pct = Decimal(getattr(settings_obj, 'holiday_special_pct', Decimal('0.30')) or '0.30')
        reg_no_work = bool(getattr(settings_obj, 'regular_holiday_no_work_pays', True))
        spec_no_work = bool(getattr(settings_obj, 'special_holiday_no_work_pays', False))

        daily_rate = hr * day_hours

        self.holiday_pay_regular = Decimal('0.00')
        self.holiday_pay_special = Decimal('0.00')

        # Build map of paid hours per date
        worked_hours_by_date: dict[date, Decimal] = defaultdict(lambda: Decimal('0'))
        for attendance in attendance_qs:
            worked_hours_by_date[attendance.date] += Decimal(attendance.paid_hours or 0)

        # Fetch holidays in range
        try:
            from payroll.models import Holiday
            holidays = Holiday.objects.filter(
                is_deleted=False,
                date__gte=self.week_start,
                date__lte=self.week_end
            )
        except Exception:
            holidays = []

        for h in holidays:
            d = h.date
            worked = worked_hours_by_date.get(d, Decimal('0'))
            fraction = Decimal('0')
            if day_hours and day_hours > 0:
                fraction = worked / day_hours
                if fraction > Decimal('1'):
                    fraction = Decimal('1')

            if h.kind == 'regular':
                if worked > 0:
                    add = daily_rate * reg_pct * fraction
                else:
                    add = (daily_rate * reg_pct) if reg_no_work else Decimal('0')
                self.holiday_pay_regular = self._q(self.holiday_pay_regular + add)
            elif h.kind == 'special_non_working':
                if worked > 0:
                    add = daily_rate * spec_pct * fraction
                else:
                    add = (daily_rate * spec_pct) if spec_no_work else Decimal('0')
                self.holiday_pay_special = self._q(self.holiday_pay_special + add)

        self.holiday_pay_total = self._q(self.holiday_pay_regular + self.holiday_pay_special)

        # Gross pay = base + allowances + additional earnings + night diff + approved OT + holiday premiums
        self.gross_pay = self._q(
            base_pay + self.allowances + self.additional_earnings_total +
            self.night_diff_pay + self.approved_ot_pay + self.holiday_pay_total
        )

        # Deductions
        deductions_map: dict[str, Decimal] = {
            k: Decimal(v) for k, v in (self.deductions or {}).items()
        }

        # Add late penalties as a deduction
        if late_penalties_total > 0:
            deductions_map['late_penalty'] = self._q(late_penalties_total)

        # Apply manual deductions
        try:
            from payroll.models import ManualDeduction

            # Get per_employee deductions for this employee
            per_employee_deductions = ManualDeduction.objects.filter(
                is_deleted=False,
                is_active=True,
                deduction_type='per_employee',
                employee=self.employee,
            )

            for deduction in per_employee_deductions:
                # Determine if this is one-time or recurring:
                # One-time: has effective_date but NO end_date (applied once)
                # Recurring: has effective_date AND end_date (applied multiple times)

                if deduction.end_date is None:
                    # One-time deduction: apply once if not yet applied
                    should_apply = False

                    if deduction.effective_date is None:
                        # No effective_date: apply to next payroll if not yet applied
                        if deduction.applied_date is None:
                            should_apply = True
                    else:
                        # Has effective_date: apply if effective_date <= week_end and not yet applied
                        if deduction.effective_date <= self.week_end and deduction.applied_date is None:
                            should_apply = True

                    if should_apply:
                        key = self._generate_deduction_key(deduction.name, deductions_map)
                        deductions_map[key] = self._q(Decimal(deduction.amount))
                        # Note: Don't mark as applied here - only mark when payroll is approved
                else:
                    # Recurring deduction: apply if within effective date range
                    if deduction.effective_date and deduction.effective_date <= self.week_end:
                        # Check if still within end_date range
                        if deduction.end_date >= self.week_start:
                            key = self._generate_deduction_key(deduction.name, deductions_map)
                            deductions_map[key] = self._q(Decimal(deduction.amount))

            # Get recurring_all deductions that apply to all employees
            recurring_all = ManualDeduction.objects.filter(
                is_deleted=False,
                is_active=True,
                deduction_type='recurring_all',
                effective_date__isnull=False,
                effective_date__lte=self.week_end,
            ).filter(
                models.Q(end_date__isnull=True) | models.Q(end_date__gte=self.week_start)
            )

            for deduction in recurring_all:
                key = self._generate_deduction_key(deduction.name, deductions_map)
                deductions_map[key] = self._q(Decimal(deduction.amount))

            # Get onetime_all deductions that haven't been applied yet
            # For onetime_all, if no effective_date, apply once in next payroll
            # If effective_date is set, apply in that specific week
            onetime_all = ManualDeduction.objects.filter(
                is_deleted=False,
                is_active=True,
                deduction_type='onetime_all',
            )

            for deduction in onetime_all:
                should_apply = False

                # If no effective_date, apply once if not yet applied
                if deduction.effective_date is None:
                    if deduction.applied_date is None:
                        should_apply = True
                else:
                    # If effective_date is set, apply only in the week containing that date
                    if (deduction.effective_date >= self.week_start and
                        deduction.effective_date < self.week_end):
                        if deduction.applied_date is None or deduction.applied_date == self.week_start:
                            should_apply = True

                if should_apply:
                    key = self._generate_deduction_key(deduction.name, deductions_map)
                    deductions_map[key] = self._q(Decimal(deduction.amount))
                    # Note: Don't mark as applied here - only mark when payroll is approved

        except Exception as e:
            # Log error but don't fail payroll computation
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error applying manual deductions: {e}")

        # Apply percentage-based deductions (HDMF savings, etc.)
        try:
            from payroll.models import PercentageDeduction

            percentage_deductions = PercentageDeduction.objects.filter(
                is_active=True,
                effective_start__lte=self.week_start,
            ).filter(
                models.Q(effective_end__isnull=True) | models.Q(effective_end__gte=self.week_start)
            )

            for pct_deduction in percentage_deductions:
                key = pct_deduction.name.lower().replace(' ', '_')
                if key not in deductions_map:
                    deductions_map[key] = self._q(self.gross_pay * Decimal(pct_deduction.rate))
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error applying percentage deductions: {e}")

        # Apply statutory deductions (fixed amounts)
        try:
            statutory_qs = DeductionRate.objects.filter(
                name__in=['sss', 'philhealth', 'pagibig'],
                effective_start__lte=self.week_start,
            ).filter(models.Q(effective_end__isnull=True) | models.Q(effective_end__gte=self.week_start))
            for rate in statutory_qs:
                if rate.name not in deductions_map:
                    deductions_map[rate.name] = self._q(Decimal(rate.amount or 0))
        except Exception:
            pass

        if percent_deductions:
            for name, rate in percent_deductions.items():
                deductions_map[name] = self._q(self.gross_pay * Decimal(rate or 0))

        if extra_flat_deductions:
            for name, amt in extra_flat_deductions.items():
                deductions_map[name] = self._q(Decimal(amt or 0))

        self.deductions = {k: float(self._q(v)) for k, v in deductions_map.items()}
        self.total_deductions = self._q(sum(self.deductions.values()))
        self.net_pay = self._q(self.gross_pay - self.total_deductions)

    def create_deduction_records(self):
        """
        Create structured PayrollDeduction records for this payroll.
        Should be called after save() to ensure payroll has an ID.
        Clears existing records and recreates them.
        Also updates the payroll's deductions and total_deductions fields.

        Note: Does NOT mark deductions as applied if payroll is still draft.
        """
        # Clear existing deduction records
        self.deduction_items.all().delete()

        # Call the helper to get deduction records (without marking as applied)
        deductions_map, deduction_records = self._apply_all_deductions(mark_as_applied=False)

        # Update the payroll's deductions and total_deductions fields
        self.deductions = {k: float(self._q(v)) for k, v in deductions_map.items()}
        self.total_deductions = self._q(sum(deductions_map.values()))
        self.net_pay = self._q(self.gross_pay - self.total_deductions)
        self.save(update_fields=['deductions', 'total_deductions', 'net_pay'])

        # Bulk create all deduction records
        if deduction_records:
            PayrollDeduction.objects.bulk_create(deduction_records)

    def finalize_deductions(self):
        """
        Finalize deductions when payroll is approved.
        Marks one-time deductions as applied so they won't apply to future payrolls.
        Should be called when payroll status changes to 'approved'.
        """
        from payroll.models import ManualDeduction

        # Get all manual deductions that should be marked as applied
        per_employee_deductions = ManualDeduction.objects.filter(
            is_deleted=False,
            is_active=True,
            deduction_type='per_employee',
            employee=self.employee,
            end_date__isnull=True,  # One-time deductions only
            applied_date__isnull=True,  # Not yet applied
        )

        # Mark deductions as applied
        deductions_to_mark = []
        for deduction in per_employee_deductions:
            # Check if this deduction is in the current payroll
            if self.deduction_items.filter(
                source_type='ManualDeduction',
                source_id=deduction.id
            ).exists():
                deduction.applied_date = self.week_start
                deductions_to_mark.append(deduction)

        if deductions_to_mark:
            ManualDeduction.objects.bulk_update(deductions_to_mark, ['applied_date'])

        # Also mark company-wide one-time deductions
        onetime_all = ManualDeduction.objects.filter(
            is_deleted=False,
            is_active=True,
            deduction_type='onetime_all',
            applied_date__isnull=True,
        )

        onetime_to_mark = []
        for deduction in onetime_all:
            # Check if should apply to this week
            should_mark = False
            if deduction.effective_date is None:
                should_mark = True
            elif deduction.effective_date >= self.week_start and deduction.effective_date < self.week_end:
                should_mark = True

            if should_mark and self.deduction_items.filter(
                source_type='ManualDeduction',
                source_id=deduction.id
            ).exists():
                deduction.applied_date = self.week_start
                onetime_to_mark.append(deduction)

        if onetime_to_mark:
            ManualDeduction.objects.bulk_update(onetime_to_mark, ['applied_date'])

    def _week_start_as_datetime(self, d: date) -> datetime:
        """
        Convert a date to a timezone-aware start-of-day datetime.
        """
        dt = datetime.combine(d, time.min)
        if settings.USE_TZ:
            # Use make_aware instead of tz.localize
            return make_aware(dt, timezone=get_current_timezone())
        return dt

    @staticmethod
    def _q(value: Decimal, places=2) -> Decimal:
        exp = Decimal(10) ** -places
        return Decimal(value).quantize(exp, rounding=ROUND_HALF_UP)

    def _generate_deduction_key(self, name: str, existing_keys: dict) -> str:
        """
        Generate a clean, unique deduction key from the deduction name.
        If the base name conflicts, append a number.

        Args:
            name: The deduction name
            existing_keys: Dictionary of existing deduction keys

        Returns:
            A unique key string
        """
        # Create base key from name
        base_key = name.lower().replace(' ', '_').replace('-', '_')

        # If no conflict, use as-is
        if base_key not in existing_keys:
            return base_key

        # If conflict, append number
        counter = 2
        while f"{base_key}_{counter}" in existing_keys:
            counter += 1

        return f"{base_key}_{counter}"

    def _apply_all_deductions(self, mark_as_applied=False):
        """
        Apply all applicable deductions and create PayrollDeduction records.
        This method computes deductions from all sources and creates structured records.

        Sources:
        1. Manual deductions (per_employee, recurring_all, onetime_all)
        2. Government benefits (SSS, PhilHealth, Pag-IBIG, BIR Tax)
        3. Legacy percentage deductions
        4. Late penalties (from attendance)
        5. Extra deductions passed via parameters

        Args:
            mark_as_applied: If True, marks one-time deductions as applied immediately.
                           If False (default), deductions are only marked when payroll is approved.

        Returns: tuple of (deductions_map, deduction_records_to_create)
        """
        from payroll.models import (
            GovernmentBenefit,
            ManualDeduction,
            PercentageDeduction,
        )

        deductions_map: dict[str, Decimal] = {}
        deduction_records = []

        # 1. Apply Manual Deductions (per_employee)
        try:
            per_employee_deductions = ManualDeduction.objects.filter(
                is_deleted=False,
                is_active=True,
                deduction_type='per_employee',
                employee=self.employee,
            )

            for deduction in per_employee_deductions:
                if deduction.end_date is None:
                    # One-time deduction
                    should_apply = False

                    if deduction.effective_date is None:
                        # No effective_date: apply to next payroll if not yet applied
                        if deduction.applied_date is None:
                            should_apply = True
                    else:
                        # Has effective_date: apply if effective_date <= week_end and not yet applied
                        if deduction.effective_date <= self.week_end and deduction.applied_date is None:
                            should_apply = True

                    if should_apply:
                        key = self._generate_deduction_key(deduction.name, deductions_map)
                        amount = self._q(Decimal(deduction.amount))
                        deductions_map[key] = amount

                        # Create structured record
                        deduction_records.append(PayrollDeduction(
                            payroll=self,
                            category='manual',
                            name=deduction.name,
                            description=deduction.description,
                            employee_share=amount,
                            employer_share=Decimal("0.00"),
                            source_type='ManualDeduction',
                            source_id=deduction.id,
                            calculation_method='fixed',
                        ))

                        # Only mark as applied if explicitly requested (when payroll is approved)
                        if mark_as_applied:
                            deduction.applied_date = self.week_start
                            deduction.save(update_fields=['applied_date'])
                else:
                    # Recurring deduction
                    if deduction.effective_date and deduction.effective_date <= self.week_end:
                        if deduction.end_date >= self.week_start:
                            key = self._generate_deduction_key(deduction.name, deductions_map)
                            amount = self._q(Decimal(deduction.amount))
                            deductions_map[key] = amount

                            deduction_records.append(PayrollDeduction(
                                payroll=self,
                                category='manual',
                                name=deduction.name,
                                description=deduction.description,
                                employee_share=amount,
                                employer_share=Decimal("0.00"),
                                source_type='ManualDeduction',
                                source_id=deduction.id,
                                calculation_method='fixed',
                            ))
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error applying manual deductions: {e}")

        # 2. Apply Company-wide Manual Deductions
        try:
            # Recurring for all
            recurring_all = ManualDeduction.objects.filter(
                is_deleted=False,
                is_active=True,
                deduction_type='recurring_all',
                effective_date__isnull=False,
                effective_date__lte=self.week_end,
            ).filter(
                models.Q(end_date__isnull=True) | models.Q(end_date__gte=self.week_start)
            )

            for deduction in recurring_all:
                key = self._generate_deduction_key(deduction.name, deductions_map)
                amount = self._q(Decimal(deduction.amount))
                deductions_map[key] = amount

                deduction_records.append(PayrollDeduction(
                    payroll=self,
                    category='manual',
                    name=deduction.name,
                    description=f"Company-wide: {deduction.description}",
                    employee_share=amount,
                    employer_share=Decimal("0.00"),
                    source_type='ManualDeduction',
                    source_id=deduction.id,
                    calculation_method='fixed',
                ))

            # One-time for all
            onetime_all = ManualDeduction.objects.filter(
                is_deleted=False,
                is_active=True,
                deduction_type='onetime_all',
            )

            for deduction in onetime_all:
                should_apply = False

                if deduction.effective_date is None:
                    if deduction.applied_date is None:
                        should_apply = True
                else:
                    if (deduction.effective_date >= self.week_start and
                        deduction.effective_date < self.week_end):
                        if deduction.applied_date is None or deduction.applied_date == self.week_start:
                            should_apply = True

                if should_apply:
                    key = self._generate_deduction_key(deduction.name, deductions_map)
                    amount = self._q(Decimal(deduction.amount))
                    deductions_map[key] = amount

                    deduction_records.append(PayrollDeduction(
                        payroll=self,
                        category='manual',
                        name=deduction.name,
                        description=f"One-time (all): {deduction.description}",
                        employee_share=amount,
                        employer_share=Decimal("0.00"),
                        source_type='ManualDeduction',
                        source_id=deduction.id,
                        calculation_method='fixed',
                    ))

                    # Only mark as applied if explicitly requested (when payroll is approved)
                    if mark_as_applied and not deduction.applied_date:
                        deduction.applied_date = self.week_start
                        deduction.save(update_fields=['applied_date'])
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error applying company-wide deductions: {e}")

        # 3. Apply Government Benefits
        try:
            gov_benefits = GovernmentBenefit.objects.filter(
                is_active=True,
                effective_start__lte=self.week_start,
            ).filter(
                models.Q(effective_end__isnull=True) | models.Q(effective_end__gte=self.week_start)
            )

            for benefit in gov_benefits:
                employee_share = benefit.compute_employee_share(self.gross_pay)
                employer_share = benefit.compute_employer_share(self.gross_pay)

                if employee_share > 0:
                    key = benefit.benefit_type
                    deductions_map[key] = employee_share

                    category = 'tax' if benefit.benefit_type == 'bir_tax' else 'government'

                    deduction_records.append(PayrollDeduction(
                        payroll=self,
                        category=category,
                        name=benefit.name,
                        description=benefit.description,
                        employee_share=employee_share,
                        employer_share=employer_share,
                        source_type='GovernmentBenefit',
                        source_id=benefit.id,
                        calculation_method=benefit.calculation_method,
                        basis_amount=self.gross_pay if benefit.calculation_method in ['percentage', 'progressive_tax'] else None,
                        rate=benefit.employee_share_rate if benefit.calculation_method == 'percentage' else None,
                    ))
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error applying government benefits: {e}")

        # 4. Apply Legacy Percentage Deductions (if any still exist)
        try:
            percentage_deductions = PercentageDeduction.objects.filter(
                is_active=True,
                effective_start__lte=self.week_start,
            ).filter(
                models.Q(effective_end__isnull=True) | models.Q(effective_end__gte=self.week_start)
            )

            for pct_deduction in percentage_deductions:
                key = pct_deduction.name.lower().replace(' ', '_')
                if key not in deductions_map:
                    amount = self._q(self.gross_pay * Decimal(pct_deduction.rate))
                    deductions_map[key] = amount

                    deduction_records.append(PayrollDeduction(
                        payroll=self,
                        category='other',
                        name=pct_deduction.name,
                        description=pct_deduction.description,
                        employee_share=amount,
                        employer_share=Decimal("0.00"),
                        source_type='PercentageDeduction',
                        source_id=pct_deduction.id,
                        calculation_method='percentage',
                        basis_amount=self.gross_pay,
                        rate=pct_deduction.rate,
                    ))
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error applying percentage deductions: {e}")

        return deductions_map, deduction_records


class PayrollDeduction(models.Model):
    """
    Individual deduction line item for a payroll period.
    Provides structured breakdown of all deductions with proper categorization.

    This model stores the COMPUTED deduction amounts for historical record keeping,
    but deductions are DERIVED from source models (ManualDeduction, GovernmentBenefit, etc.)
    during payroll generation.
    """

    DEDUCTION_CATEGORIES = [
        ('manual', 'Manual Deduction'),
        ('government', 'Government Benefit'),
        ('tax', 'Withholding Tax'),
        ('late_penalty', 'Late Penalty'),
        ('other', 'Other'),
    ]

    payroll = models.ForeignKey(
        WeeklyPayroll,
        on_delete=models.CASCADE,
        related_name='deduction_items'
    )

    category = models.CharField(max_length=20, choices=DEDUCTION_CATEGORIES)
    name = models.CharField(max_length=100, help_text="Deduction name (e.g., 'SSS', 'Loan Repayment')")
    description = models.TextField(blank=True)

    # Amount breakdown
    employee_share = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Amount deducted from employee's pay"
    )
    employer_share = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Amount paid by employer (for reporting, not deducted from employee)"
    )

    # Source tracking
    source_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Source model name (e.g., 'ManualDeduction', 'GovernmentBenefit')"
    )
    source_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="ID of the source record"
    )

    # Calculation metadata
    calculation_method = models.CharField(
        max_length=20,
        blank=True,
        help_text="How this was calculated (fixed, percentage, progressive_tax)"
    )
    basis_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Base amount used for calculation (e.g., gross pay for percentage deductions)"
    )
    rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Rate used for percentage calculations"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['category', 'name']
        indexes = [
            models.Index(fields=['payroll', 'category']),
            models.Index(fields=['source_type', 'source_id']),
        ]

    def __str__(self):
        return f"{self.payroll} - {self.name}: ₱{self.employee_share}"

    @property
    def total_amount(self) -> Decimal:
        """Total deduction (employee + employer share)"""
        return self.employee_share + self.employer_share


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



        # Central multipliers for OT and Night Differential
    overtime_multiplier = models.DecimalField(
            max_digits=4,
            decimal_places=2,
            default=Decimal("1.25"),
            help_text="Overtime pay multiplier applied to overtime hours (e.g., 1.25 = +25%).",
        )
    night_diff_multiplier = models.DecimalField(
            max_digits=4,
            decimal_places=2,
            default=Decimal("0.10"),
            help_text="Night differential additional multiplier applied to ND hours (e.g., 0.10 = +10%).",
        )

    updated_at = models.DateTimeField(auto_now=True)

    # Holiday computations: baseline daily hours and no-work-pay flags
    holiday_day_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("8.00"),
        help_text="Hours used to compute daily rate (hourly_rate * day_hours).",
    )
    regular_holiday_no_work_pays = models.BooleanField(
        default=True, help_text="Pay +100% daily even if no work on regular holiday."
    )
    special_holiday_no_work_pays = models.BooleanField(
        default=False, help_text="Pay +30% daily even if no work on special non-working holiday."
    )

    # Payroll cutoff configuration
    payroll_cutoff_day = models.PositiveIntegerField(
        default=4,  # Friday
        choices=[
            (0, "Monday"),
            (1, "Tuesday"),
            (2, "Wednesday"),
            (3, "Thursday"),
            (4, "Friday"),
            (5, "Saturday"),
            (6, "Sunday"),
        ],
        help_text="Last day of payroll week (0=Monday, 4=Friday). Week starts the day after this cutoff.",
    )

    class Meta:
        verbose_name = "Payroll Settings"
        verbose_name_plural = "Payroll Settings"

    def __str__(self):
        return f"PayrollSettings ({self.shift_start}-{self.shift_end}, grace={self.grace_minutes}m)"


class DeductionRate(models.Model):
    """
    Statutory deduction rate with historical periods.
    - name: one of SSS, PhilHealth, Pag-IBIG
    - amount: weekly amount to deduct
    - effective_start/effective_end: period when this rate is in effect
    - is_active: flag to mark currently active records (for quick lookups)
    - created_by: admin who created the rate
    - created_at: timestamp
    Notes:
      - Historical records MUST remain immutable once effective_start is in the past.
      - Only one active rate should exist per name for any given date.
    """

    DEDUCTION_CHOICES = [
        ("sss", "SSS"),
        ("philhealth", "PhilHealth"),
        ("pagibig", "Pag-IBIG"),
    ]

    name = models.CharField(max_length=20, choices=DEDUCTION_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    effective_start = models.DateField(help_text="Date the rate becomes effective (inclusive).")
    effective_end = models.DateField(
        null=True,
        blank=True,
        help_text="Date the rate stops being effective (inclusive). Leave null if still active.",
    )

    is_active = models.BooleanField(default=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_deduction_rates",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["name", "effective_start"]),
            models.Index(fields=["name", "is_active"]),
        ]
        ordering = ["name", "-effective_start"]
        verbose_name = "Deduction Rate"
        verbose_name_plural = "Deduction Rates"

    def __str__(self):
        return f"{self.get_name_display()} @ {self.effective_start} -> {self.effective_end or 'present'} ({self.amount})"

    def clean(self):
        super().clean()
        if self.effective_end and self.effective_end < self.effective_start:
            raise ValidationError({"effective_end": "effective_end must be on or after effective_start."})
        if self.amount is not None and Decimal(self.amount) < 0:
            raise ValidationError({"amount": "Amount must be non-negative."})
