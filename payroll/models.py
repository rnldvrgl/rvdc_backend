from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.timezone import get_current_timezone, make_aware


class AdditionalEarning(models.Model):
    """
    Additional earnings for an employee within a given date.
    Can represent installation percentages or any custom payout.
    These are included in weekly payroll computations if approved and within the week range.
    Note: Overtime pay is calculated automatically from attendance records, not added here.
    """

    EARNING_TYPES = [
        ("bonus", "Bonus"),
        ("commission", "Commission"),
        ("tip", "Customer Tip"),
        ("performance", "Performance Incentive"),
        ("installation_pct", "Installation %"),
        ("allowance", "Special Allowance"),
       ("other", "Other"),
    ]

    employee = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.CASCADE,
        related_name="additional_earnings",
    )
    earning_date = models.DateField()
    category = models.CharField(max_length=32, choices=EARNING_TYPES, default="other")
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
    deleted_at = models.DateTimeField(null=True, blank=True)

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
    deleted_at = models.DateTimeField(null=True, blank=True)

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
    deleted_at = models.DateTimeField(null=True, blank=True)
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
    Supports different bracket types (BIR, SSS, PhilHealth, Pag-IBIG, etc.)
    Example: 0-20833 = 0%, 20834-33332 = 20%, etc.
    """

    BRACKET_TYPES = [
        ("bir", "BIR Withholding Tax"),
        ("sss", "SSS Contribution"),
        ("philhealth", "PhilHealth Contribution"),
        ("pagibig", "Pag-IBIG Contribution"),
        ("custom", "Custom Tax/Contribution"),
    ]

    bracket_type = models.CharField(
        max_length=32,
        choices=BRACKET_TYPES,
        default="bir",
        help_text="Type of tax bracket (BIR, SSS, PhilHealth, Pag-IBIG, etc.)"
    )
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
        ordering = ['bracket_type', 'min_income']
        indexes = [
            models.Index(fields=['bracket_type', 'effective_start', 'is_active']),
            models.Index(fields=['effective_start', 'is_active']),
        ]

    def __str__(self):
        max_display = f"{self.max_income}" if self.max_income else "above"
        return f"₱{self.min_income} - {max_display}: {self.rate*100}%"

    @staticmethod
    def compute_tax(gross_income: Decimal, as_of_date: date, bracket_type: str = "bir") -> Decimal:
        """
        Compute progressive withholding tax for given gross income.
        Defaults to BIR withholding tax if bracket_type not specified.
        """
        brackets = TaxBracket.objects.filter(
            bracket_type=bracket_type,
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

    PERIOD_TYPES = [
        ('weekly', 'Weekly (amount as-is)'),
        ('monthly', 'Monthly (divide by 4 for weekly payroll)'),
    ]

    benefit_type = models.CharField(max_length=20, choices=BENEFIT_TYPES)
    name = models.CharField(max_length=100, help_text="Display name (e.g., 'SSS Contribution')")
    calculation_method = models.CharField(max_length=20, choices=CALCULATION_METHODS)

    # Period type for fixed amounts
    period_type = models.CharField(
        max_length=10,
        choices=PERIOD_TYPES,
        default='monthly',
        help_text="Whether the fixed amount is monthly (divide by 4) or weekly (as-is)"
    )

    # For fixed amount method
    employee_share_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Fixed employee contribution amount (monthly or weekly based on period_type)"
    )
    employer_share_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Fixed employer contribution amount (monthly or weekly based on period_type)"
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
        """
        Compute employee's share of this benefit.
        For fixed amounts with period_type='monthly', divides by 4 for weekly payroll.
        """
        if self.calculation_method == 'fixed':
            amount = Decimal(self.employee_share_amount or 0)
            # If monthly, divide by 4 for weekly payroll
            if self.period_type == 'monthly':
                amount = amount / Decimal('4.00')
            return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        elif self.calculation_method == 'percentage':
            return (gross_pay * Decimal(self.employee_share_rate or 0)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        elif self.calculation_method == 'progressive_tax':
            # For BIR tax, use TaxBracket computation
            return TaxBracket.compute_tax(gross_pay, self.effective_start)
        return Decimal("0.00")

    def compute_employer_share(self, gross_pay: Decimal) -> Decimal:
        """
        Compute employer's share of this benefit.
        For fixed amounts with period_type='monthly', divides by 4 for weekly payroll.
        """
        if self.calculation_method == 'fixed':
            amount = Decimal(self.employer_share_amount or 0)
            # If monthly, divide by 4 for weekly payroll
            if self.period_type == 'monthly':
                amount = amount / Decimal('4.00')
            return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        elif self.calculation_method == 'percentage':
            return (gross_pay * Decimal(self.employer_share_rate or 0)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        # Progressive tax has no employer share
        return Decimal("0.00")


class EmployeeBenefitOverride(models.Model):
    """
    Per-employee overrides for government benefit amounts.
    Takes precedence over GovernmentBenefit and TaxBracket calculations.
    Use for employees with custom arrangements (e.g., owners, contractors).
    """
    
    BENEFIT_TYPES = [
        ('sss', 'SSS'),
        ('philhealth', 'PhilHealth'),
        ('pagibig', 'Pag-IBIG / HDMF'),
        ('bir_tax', 'BIR Withholding Tax'),
    ]
    
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="benefit_overrides"
    )
    benefit_type = models.CharField(max_length=20, choices=BENEFIT_TYPES)
    
    # Fixed weekly amounts
    employee_share_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Fixed employee contribution amount per week"
    )
    employer_share_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Fixed employer contribution amount per week (for reporting)"
    )
    
    # Date effectiveness
    effective_start = models.DateField(help_text="Date this override becomes effective")
    effective_end = models.DateField(
        null=True,
        blank=True,
        help_text="Date this override ends (null = still active)"
    )
    
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, help_text="Reason for override or special notes")
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_benefit_overrides"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-effective_start', 'employee', 'benefit_type']
        indexes = [
            models.Index(fields=['employee', 'benefit_type', 'is_active']),
            models.Index(fields=['effective_start', 'effective_end']),
        ]
        # Ensure one active override per employee per benefit type per date range
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'benefit_type', 'effective_start'],
                name='unique_employee_benefit_start_date'
            )
        ]
    
    def __str__(self):
        return f"{self.employee.get_full_name()} - {self.get_benefit_type_display()} - ₱{self.employee_share_amount}"


class WeeklyPayroll(models.Model):

    """
    A weekly payroll summary for an employee.

    - week_start: The date representing the start of the payroll week (e.g., Saturday).
    - Computation is weekly: regular up to overtime_threshold hours; remainder = overtime.
    - Deductions can include percent and flat components by name in the JSON field.
    - Night differential: 22:00–06:00 hours × hourly_rate × 0.10
    - Approved OT: approved overtime requests × hourly_rate × 1.25

    Use compute_from_daily_attendance() to recompute based on approved DailyAttendance records.
    Legacy method compute_from_time_entries() exists for backward compatibility.
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
    week_end = models.DateField(
        help_text="End date of the payroll week (inclusive).",
        null=True,
        blank=True,
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
    deduction_metadata = models.JSONField(
        default=dict,
        help_text='Metadata for deductions including source info. Example: {"loan": {"source_type": "ManualDeduction", "source_id": 123, "category": "manual"}}',
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
    deleted_at = models.DateTimeField(null=True, blank=True)
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

    def get_week_end(self) -> date:
        """Return the stored week_end or fall back to week_start + 6 days."""
        if self.week_end:
            return self.week_end
        return self.week_start + timedelta(days=6)

    def save(self, *args, **kwargs):
        """Auto-populate week_end from week_start + 6 days if not set."""
        if not self.week_end and self.week_start:
            self.week_end = self.week_start + timedelta(days=6)
        super().save(*args, **kwargs)

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
        late_penalties_total = Decimal('0.00')

        for attendance in attendance_qs:
            paid_hours = Decimal(attendance.paid_hours or 0)

            # All hours count as regular hours - overtime must be approved via OvertimeRequest
            regular_hours_total += paid_hours

            # Accumulate late penalties
            if attendance.late_penalty_amount:
                late_penalties_total += Decimal(attendance.late_penalty_amount)

        self.regular_hours = self._q(regular_hours_total)

        # Compute base pay (regular hours only)
        hr = Decimal(self.hourly_rate or 0)
        base_pay = self.regular_hours * hr

        # Night differential - Calculate from DailyAttendance clock times
        night_diff_hours_total = Decimal('0.00')
        night_diff_rate = Decimal('0.10')  # 10% additional pay for night hours (22:00-06:00)

        try:
            from payroll.models import PayrollSettings
            settings = PayrollSettings.objects.first()
            if settings and settings.night_diff_multiplier:
                night_diff_rate = Decimal(settings.night_diff_multiplier)
        except (ImportError, LookupError, AttributeError):
            pass

        for attendance in attendance_qs:
            if attendance.clock_in and attendance.clock_out:
                # Calculate night differential hours (22:00 - 06:00)
                night_hours = self._calculate_night_diff_hours(
                    attendance.clock_in,
                    attendance.clock_out
                )
                night_diff_hours_total += night_hours

        # Note: night_diff_hours_total is updated both from DailyAttendance and OvertimeRequest
        # We'll set the final values after processing both sources

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
            from attendance.models import OvertimeRequest
            from django.db.models import Q

            # Create start and end datetime for the week
            start_dt = self._week_start_as_datetime(self.week_start)
            end_dt = self._week_start_as_datetime(self.week_end)
            # Add one day to end_dt to make it inclusive
            end_dt = end_dt + timedelta(days=1)

            # Query by date field OR by time_start date (fallback for inconsistent data)
            ot_req_qs = OvertimeRequest.objects.filter(
                employee=self.employee,
                approved=True,
            ).filter(
                Q(date__gte=self.week_start, date__lte=self.week_end) |
                Q(time_start__gte=start_dt, time_start__lt=end_dt)
            )

            approved_ot_hours_total = Decimal('0')
            for req in ot_req_qs:
                span = req.time_end - req.time_start
                approved_ot_hours_total += Decimal(span.total_seconds()) / Decimal(3600)

                # Also calculate night differential hours for this overtime request
                ot_night_hours = self._calculate_night_diff_hours(req.time_start, req.time_end)
                night_diff_hours_total += ot_night_hours

            self.approved_ot_hours = self._q(approved_ot_hours_total, places=2)
            self.approved_ot_pay = self._q(self.approved_ot_hours * hr * Decimal('1.25'))
        except (ImportError, LookupError, AttributeError):
            self.approved_ot_hours = Decimal('0.00')
            self.approved_ot_pay = Decimal('0.00')

        # Set final night differential values (after processing both attendance and OT)
        self.night_diff_hours = self._q(night_diff_hours_total)
        self.night_diff_pay = self._q(self.night_diff_hours * hr * night_diff_rate)

        # Holiday premiums (compute based on worked days from DailyAttendance)
        try:
            settings_obj = PayrollSettings.objects.first()
        except (ImportError, LookupError, AttributeError):
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
        except (ImportError, LookupError, AttributeError):
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
                    # Employee worked on holiday - always pay holiday premium for hours worked
                    add = daily_rate * reg_pct * fraction
                else:
                    # Employee didn't work - only pay if no_work_no_pay is disabled
                    add = (daily_rate * reg_pct) if reg_no_work else Decimal('0')
                self.holiday_pay_regular = self._q(self.holiday_pay_regular + add)
            elif h.kind == 'special_non_working':
                if worked > 0:
                    # Employee worked on holiday - always pay holiday premium for hours worked
                    add = daily_rate * spec_pct * fraction
                else:
                    # Employee didn't work - only pay if no_work_no_pay is disabled
                    add = (daily_rate * spec_pct) if spec_no_work else Decimal('0')
                self.holiday_pay_special = self._q(self.holiday_pay_special + add)

        self.holiday_pay_total = self._q(self.holiday_pay_regular + self.holiday_pay_special)

        # Gross pay = base + allowances + additional earnings + night diff + approved OT + holiday premiums
        self.gross_pay = self._q(
            base_pay + self.allowances + self.additional_earnings_total +
            self.night_diff_pay + self.approved_ot_pay + self.holiday_pay_total
        )

        # Deductions - Start fresh on recompute (don't use existing deductions)
        deductions_map: dict[str, Decimal] = {}
        deduction_metadata_map: dict[str, dict] = {}

        # Add late penalties as a deduction
        if late_penalties_total > 0:
            deductions_map['late_penalty'] = self._q(late_penalties_total)
            deduction_metadata_map['late_penalty'] = {
                'source_type': 'DailyAttendance',
                'category': 'late_penalty',
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
                        # Has effective_date: apply if effective_date falls within this payroll period
                        # and not yet applied
                        if (deduction.effective_date >= self.week_start and
                            deduction.effective_date <= self.week_end and
                            deduction.applied_date is None):
                            should_apply = True

                    if should_apply:
                        key = self._generate_deduction_key(deduction.name, deductions_map)
                        deductions_map[key] = self._q(Decimal(deduction.amount))
                        deduction_metadata_map[key] = {
                            'source_type': 'ManualDeduction',
                            'source_id': deduction.id,
                            'category': 'manual',
                        }
                        # Note: Don't mark as applied here - only mark when payroll is approved
                else:
                    # Recurring deduction: apply if within effective date range
                    if deduction.effective_date and deduction.effective_date <= self.week_end:
                        # Check if still within end_date range
                        if deduction.end_date >= self.week_start:
                            key = self._generate_deduction_key(deduction.name, deductions_map)
                            deductions_map[key] = self._q(Decimal(deduction.amount))
                            deduction_metadata_map[key] = {
                                'source_type': 'ManualDeduction',
                                'source_id': deduction.id,
                                'category': 'manual',
                            }

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
                deduction_metadata_map[key] = {
                    'source_type': 'ManualDeduction',
                    'source_id': deduction.id,
                    'category': 'manual',
                }

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
                    deduction_metadata_map[key] = {
                        'source_type': 'ManualDeduction',
                        'source_id': deduction.id,
                        'category': 'manual',
                    }
                    # Note: Don't mark as applied here - only mark when payroll is approved

        except Exception as e:
            # Log error but don't fail payroll computation
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error applying manual deductions: {e}")

        # Apply government benefits (SSS, PhilHealth, Pag-IBIG, BIR Tax)
        # Only apply benefits where employee has the corresponding flag set to True
        try:
            from payroll.models import EmployeeBenefitOverride, GovernmentBenefit, TaxBracket

            # Check individual government benefit flags per employee
            benefit_flag_map = {
                'sss': self.employee.has_sss,
                'philhealth': self.employee.has_philhealth,
                'pagibig': self.employee.has_pagibig,
                'bir_tax': self.employee.has_bir_tax,
            }
            
            benefit_types = ['sss', 'philhealth', 'pagibig', 'bir_tax']
                
            for benefit_type in benefit_types:
                # Skip this benefit if employee doesn't have this specific benefit enabled
                if not benefit_flag_map.get(benefit_type, False):
                    continue
                    
                employee_share = Decimal('0.00')
                source_type = None
                source_id = None
                
                # Priority 1: Check for employee-specific override first (highest priority)
                # Use week_end for effective_start check so overrides starting
                # mid-week are picked up (e.g. override starts Friday, week
                # starts Saturday prior).
                week_end_date = self.week_end or (self.week_start + timedelta(days=6))
                override = EmployeeBenefitOverride.objects.filter(
                    employee=self.employee,
                    benefit_type=benefit_type,
                    is_active=True,
                    effective_start__lte=week_end_date,
                ).filter(
                    models.Q(effective_end__isnull=True) | models.Q(effective_end__gte=self.week_start)
                ).order_by('-effective_start').first()
                
                if override:
                    # Use override amount (weekly fixed)
                    employee_share = override.employee_share_amount
                    source_type = 'EmployeeBenefitOverride'
                    source_id = override.id
                else:
                    # Priority 2: Check GovernmentBenefit configuration
                    govt_benefit = GovernmentBenefit.objects.filter(
                        benefit_type=benefit_type,
                        is_active=True,
                        effective_start__lte=week_end_date,
                    ).filter(
                        models.Q(effective_end__isnull=True) | models.Q(effective_end__gte=self.week_start)
                    ).order_by('-effective_start').first()
                    
                    if govt_benefit:
                        # Use GovernmentBenefit's calculation method
                        employee_share = govt_benefit.compute_employee_share(self.gross_pay)
                        source_type = 'GovernmentBenefit'
                        source_id = govt_benefit.id
                    else:
                        # Priority 3: Fall back to TaxBracket (legacy support)
                        employee_share = TaxBracket.compute_tax(
                            gross_income=self.gross_pay,
                            as_of_date=self.week_start,
                            bracket_type=benefit_type
                        )
                        source_type = 'TaxBracket'
                        # source_id is None for TaxBracket (multiple brackets may be used)
                
                # Add to deductions if amount is positive
                if employee_share > 0:
                    deductions_map[benefit_type] = self._q(employee_share)
                    
                    category = 'tax' if benefit_type == 'bir_tax' else 'government'
                    deduction_metadata_map[benefit_type] = {
                        'source_type': source_type,
                        'source_id': source_id,
                        'category': category,
                    }
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error applying government benefits: {e}")

        # Apply cash ban contribution deduction (if enabled for this employee)
        try:
            from payroll.models import PayrollSettings
            
            # Check if employee has cash ban enabled
            if getattr(self.employee, 'has_cash_ban', False):
                settings = PayrollSettings.objects.first()
                if settings and settings.cash_ban_enabled:
                    contribution_amount = Decimal(settings.cash_ban_contribution_amount or 0)
                    if contribution_amount > 0:
                        deductions_map['cash_ban'] = self._q(contribution_amount)
                        deduction_metadata_map['cash_ban'] = {
                            'source_type': 'PayrollSettings',
                            'category': 'deduction',
                            'description': 'Cash Ban Fund Contribution',
                        }
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error applying cash ban deduction: {e}")

        # Apply cash advance deductions (debit movements during this payroll period)
        try:
            from users.models import CashAdvanceMovement

            week_end_date = self.week_end or (self.week_start + timedelta(days=6))
            cash_advance_movements = CashAdvanceMovement.objects.filter(
                employee=self.employee,
                movement_type=CashAdvanceMovement.MovementType.DEBIT,
                is_deleted=False,
                date__gte=self.week_start,
                date__lte=week_end_date,
            )

            cash_advance_total = Decimal('0.00')
            cash_advance_ids = []
            for ca in cash_advance_movements:
                cash_advance_total += Decimal(ca.amount)
                cash_advance_ids.append(ca.id)

            if cash_advance_total > 0:
                deductions_map['cash_advance'] = self._q(cash_advance_total)
                deduction_metadata_map['cash_advance'] = {
                    'source_type': 'CashAdvanceMovement',
                    'category': 'deduction',
                    'description': 'Cash Advance Deduction',
                    'cash_advance_ids': cash_advance_ids,
                }
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error applying cash advance deduction: {e}")
        # Apply percentage-based deductions (HDMF savings, etc.) - Legacy
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
                    deduction_metadata_map[key] = {
                        'source_type': 'PercentageDeduction',
                        'source_id': pct_deduction.id,
                        'category': 'deduction',
                    }
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error applying percentage deductions: {e}")

        # Apply statutory deductions (fixed amounts) - Legacy fallback
        try:
            statutory_qs = DeductionRate.objects.filter(
                name__in=['sss', 'philhealth', 'pagibig'],
                effective_start__lte=self.week_start,
            ).filter(models.Q(effective_end__isnull=True) | models.Q(effective_end__gte=self.week_start))
            for rate in statutory_qs:
                if rate.name not in deductions_map:
                    deductions_map[rate.name] = self._q(Decimal(rate.amount or 0))
                    deduction_metadata_map[rate.name] = {
                        'source_type': 'DeductionRate',
                        'category': 'government',
                    }
        except Exception:
            pass

        if percent_deductions:
            for name, rate in percent_deductions.items():
                deductions_map[name] = self._q(self.gross_pay * Decimal(rate or 0))

        if extra_flat_deductions:
            for name, amt in extra_flat_deductions.items():
                deductions_map[name] = self._q(Decimal(amt or 0))

        self.deductions = {k: float(self._q(v)) for k, v in deductions_map.items()}
        self.deduction_metadata = deduction_metadata_map
        self.total_deductions = self._q(sum(self.deductions.values()))
        self.net_pay = self._q(self.gross_pay - self.total_deductions)

    def create_deduction_records(self):
        """
        DEPRECATED: No longer creates PayrollDeduction records.
        Metadata is now stored in deduction_metadata JSON field.
        This method is kept for backward compatibility but does nothing.
        """
        pass

    def create_deduction_records_legacy(self):
        """
        LEGACY METHOD - Use compute_from_daily_attendance instead.
        
        This method is deprecated. Deductions are now computed directly in
        compute_from_daily_attendance and stored in JSON fields (deductions, deduction_metadata).
        
        Kept for backward compatibility but does minimal work.
        """
        # Call the helper to get deduction records (without marking as applied)
        deductions_map = self._apply_all_deductions(mark_as_applied=False)

        # Update the payroll's deductions and total_deductions fields
        self.deductions = {k: float(self._q(v)) for k, v in deductions_map.items()}
        self.total_deductions = self._q(sum(deductions_map.values()))
        self.net_pay = self._q(self.gross_pay - self.total_deductions)
        self.save(update_fields=['deductions', 'total_deductions', 'net_pay'])

    def finalize_deductions(self):
        """
        Finalize deductions when payroll is approved.
        Marks one-time deductions as applied so they won't apply to future payrolls.
        Should be called when payroll status changes to 'approved'.
        """
        from payroll.models import ManualDeduction

        # Get deduction metadata to check which deductions are in this payroll
        deduction_metadata = self.deduction_metadata or {}

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
            # Check if this deduction is in the current payroll by checking deduction_metadata
            for key, metadata in deduction_metadata.items():
                if (metadata.get('source_type') == 'ManualDeduction' and
                    metadata.get('source_id') == deduction.id):
                    deduction.applied_date = self.week_start
                    deductions_to_mark.append(deduction)
                    break

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

            if should_mark:
                # Check if this deduction is in the current payroll by checking deduction_metadata
                for key, metadata in deduction_metadata.items():
                    if (metadata.get('source_type') == 'ManualDeduction' and
                        metadata.get('source_id') == deduction.id):
                        deduction.applied_date = self.week_start
                        onetime_to_mark.append(deduction)
                        break

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

    def _calculate_night_diff_hours(self, clock_in: datetime, clock_out: datetime) -> Decimal:
        """
        Calculate night differential hours (22:00 - 06:00) from clock in/out times.

        Args:
            clock_in: Clock in datetime
            clock_out: Clock out datetime

        Returns:
            Decimal hours worked during night shift (22:00 - 06:00)
        """
        if not clock_in or not clock_out:
            return Decimal('0.00')

        # Define night shift hours (10 PM to 6 AM)
        night_start_hour = 22  # 10:00 PM
        night_end_hour = 6     # 6:00 AM

        total_night_hours = Decimal('0.00')

        # Ensure both times are timezone-aware
        if clock_in.tzinfo is None:
            clock_in = make_aware(clock_in, timezone=get_current_timezone())
        if clock_out.tzinfo is None:
            clock_out = make_aware(clock_out, timezone=get_current_timezone())

        # Convert to local timezone for hour comparison
        clock_in_local = clock_in.astimezone(get_current_timezone())
        clock_out_local = clock_out.astimezone(get_current_timezone())

        # Handle shifts that span multiple days
        current_time = clock_in_local

        while current_time < clock_out_local:
            # Get the end of the current day or clock_out, whichever is earlier
            day_end = current_time.replace(hour=23, minute=59, second=59, microsecond=999999)
            segment_end = min(day_end, clock_out_local)

            # Calculate night hours for this day segment
            current_hour = current_time.hour + current_time.minute / 60.0 + current_time.second / 3600.0
            end_hour = segment_end.hour + segment_end.minute / 60.0 + segment_end.second / 3600.0

            # Check if any part of this segment falls in night hours
            # Night hours: 22:00-24:00 (same day) or 00:00-06:00 (next day)

            # Case 1: Work from 22:00 to midnight
            if current_hour < 24 and end_hour <= 24:
                # Within same day
                night_segment_start = max(current_hour, night_start_hour)
                night_segment_end = min(end_hour, 24)
                if night_segment_start < night_segment_end:
                    total_night_hours += Decimal(str(night_segment_end - night_segment_start))

            # Case 2: Work from midnight to 06:00
            if current_hour < night_end_hour or end_hour <= night_end_hour:
                night_segment_start = max(0, current_hour)
                night_segment_end = min(end_hour, night_end_hour)
                if night_segment_start < night_segment_end:
                    total_night_hours += Decimal(str(night_segment_end - night_segment_start))

            # Move to next day
            current_time = segment_end + timedelta(seconds=1)
            if current_time.date() > segment_end.date():
                current_time = current_time.replace(hour=0, minute=0, second=0, microsecond=0)

        return self._q(total_night_hours)

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
        Apply all applicable deductions and compute deductions map.
        This method computes deductions from all sources.

        Sources:
        1. Existing deductions from compute_from_daily_attendance (late penalties, statutory)
        2. Manual deductions (per_employee, recurring_all, onetime_all)
        3. Government benefits (SSS, PhilHealth, Pag-IBIG, BIR Tax)
        4. Legacy percentage deductions

        Args:
            mark_as_applied: If True, marks one-time deductions as applied immediately.
                           If False (default), deductions are only marked when payroll is approved.

        Returns: deductions_map dict
        """
        from payroll.models import (
            GovernmentBenefit,
            ManualDeduction,
            PercentageDeduction,
        )

        # Start with existing deductions computed by compute_from_daily_attendance
        # This includes late penalties and statutory deductions (SSS, PhilHealth, Pag-IBIG from DeductionRate)
        existing_deductions = self.deductions or {}
        deductions_map: dict[str, Decimal] = {
            k: self._q(Decimal(v)) for k, v in existing_deductions.items()
        }

        # Now overlay manual deductions and government benefits
        # These will override any duplicate keys from existing deductions

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
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error applying percentage deductions: {e}")

        return deductions_map




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

    clock_in_allowance_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Minutes BEFORE shift_start employees can clock in (e.g., 60 = can clock in at 7:00 AM for 8:00 AM shift). Paid hours count from shift_start, not early clock-in.",
    )

    clock_out_tolerance_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Grace minutes BEFORE shift_end that still counts as full day (e.g., 30 = clocking out at 5:30 PM still counts as full day when shift ends at 6:00 PM).",
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

    # Cash Ban contribution settings
    cash_ban_contribution_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("200.00"),
        help_text="Fixed amount to contribute to employee's cash ban fund per payroll period.",
    )
    cash_ban_enabled = models.BooleanField(
        default=True,
        help_text="Enable automatic cash ban contributions when approving payroll.",
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

    attendance_system_start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date when attendance system started. Absences will not be marked before this date.",
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
