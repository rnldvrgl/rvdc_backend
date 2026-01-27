from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.timezone import get_current_timezone, make_aware


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



class OvertimeRequest(models.Model):
    """
    An employee-filed overtime request that must be approved by management
    before inclusion in salary computation.

    - time_start / time_end: precise datetime window of the OT.
    - approved: gate for payroll inclusion.
    """
    employee = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.CASCADE,
        related_name="overtime_requests",
    )
    date = models.DateField()
    time_start = models.DateTimeField()
    time_end = models.DateTimeField()
    reason = models.TextField(blank=True)
    approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        "users.CustomUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_overtime_requests",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["employee", "date"]),
            models.Index(fields=["approved"]),
        ]
        ordering = ["-date", "employee_id"]

    def __str__(self):
        return f"OT {self.employee_id} | {self.date} | {self.time_start}—{self.time_end}"


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

class WeeklyPayroll(models.Model):

    """
    A weekly payroll summary for an employee.

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
            earning_date__lt=self.week_end,
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
                is_deleted=False, date__gte=self.week_start, date__lt=self.week_end
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
        from attendance.models import DailyAttendance
        from collections import defaultdict
        
        start_dt = self._week_start_as_datetime(self.week_start)
        end_dt = self._week_start_as_datetime(self.week_end)
        
        # Get daily attendance records for this week
        attendance_qs = DailyAttendance.objects.filter(
            employee=self.employee,
            date__gte=self.week_start,
            date__lt=self.week_end,
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
            earning_date__lt=self.week_end,
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
                date__lt=self.week_end
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
        
        # Apply statutory deductions
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
