from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from rest_framework import  status

from rest_framework.response import Response

class DailyAttendance(models.Model):
    """
    Daily attendance record for an employee.
    
    Business Rules:
    - One attendance per employee per day
    - Default status is PENDING; only APPROVED attendance counts for payroll
    - Clock in/out managed by Admin and Manager only
    - Standard shift: 8:00 AM - 6:00 PM (10 hours with 2-hour break = 8 paid hours)
    - Break times: 12:00 PM and 3:00 PM (2 hours total, auto-deducted)
    
    Attendance Types:
    - FULL_DAY: ≥10 clock hours → 8 paid hours
    - HALF_DAY: 4-5 clock hours OR ≥30 min late → 4 paid hours
    - PARTIAL: 5-10 clock hours → actual hours minus breaks
    - ABSENT: No clock-in/out
    - LEAVE: Approved leave (unpaid)
    
    Late Policy:
    - 0-15 min late: grace period (no penalty)
    - 16-29 min late: ₱2 per minute penalty
    - ≥30 min late: automatic HALF_DAY classification
    """
    
    ATTENDANCE_TYPE_CHOICES = [
        ('FULL_DAY', 'Full Day'),
        ('HALF_DAY', 'Half Day'),
        ('PARTIAL', 'Partial Hours'),
        ('ABSENT', 'Absent'),
        ('LEAVE', 'On Leave'),
        ('INVALID', 'Invalid'),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]
    
    employee = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='daily_attendances',
    )
    date = models.DateField()
    
    # Clock times (nullable for ABSENT/LEAVE types)
    clock_in = models.DateTimeField(null=True, blank=True)
    clock_out = models.DateTimeField(null=True, blank=True)
    
    # Computed fields
    attendance_type = models.CharField(
        max_length=20,
        choices=ATTENDANCE_TYPE_CHOICES,
        default='PENDING',
    )
    total_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Total clock hours (clock_out - clock_in)',
    )
    break_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('2.00'),
        help_text='Unpaid break hours (auto-deducted)',
    )
    paid_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Hours counted for payroll',
    )
    
    # Late tracking
    is_late = models.BooleanField(default=False)
    late_minutes = models.PositiveIntegerField(
        default=0,
        help_text='Minutes late beyond grace period',
    )
    late_penalty_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Penalty: ₱2 per minute late',
    )

    # Absence tracking
    consecutive_absences = models.PositiveIntegerField(
        default=0,
        help_text='Counts consecutive absences without approved leave for AWOL monitoring',
    )
    is_awol = models.BooleanField(
        default=False,
        help_text='True if employee has 3+ consecutive absences (AWOL flag)',
    )
    
    auto_closed = models.BooleanField(
        default=False,
        help_text="True if the attendance was auto-closed due to missing clock_out",
    )
    auto_close_warning_count = models.PositiveIntegerField(
        default=0,
        help_text="Cumulative count of auto-close warnings (for repeated violations)",
    )
    
    # Uniform penalties (₱50 each)
    missing_uniform_shirt = models.BooleanField(
        default=False,
        help_text="Missing or incomplete shirt/uniform top",
    )
    missing_uniform_pants = models.BooleanField(
        default=False,
        help_text="Missing or incomplete pants/uniform bottom",
    )
    missing_uniform_shoes = models.BooleanField(
        default=False,
        help_text="Missing or incomplete shoes/footwear",
    )
    uniform_penalty_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Total uniform penalty: ₱50 per missing item',
    )
    
    # Approval workflow
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING',
    )
    approved_by = models.ForeignKey(
        'users.CustomUser',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_attendances',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    
    notes = models.TextField(blank=True)
    
    # Soft delete
    is_deleted = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('employee', 'date')
        indexes = [
            models.Index(fields=['employee', 'date']),
            models.Index(fields=['date']),
            models.Index(fields=['status']),
            models.Index(fields=['attendance_type']),
        ]
        ordering = ['-date', 'employee']
        verbose_name = 'Daily Attendance'
        verbose_name_plural = 'Daily Attendances'
    
    def __str__(self):
        return f"{self.employee.get_full_name()} - {self.date} ({self.get_attendance_type_display()})"
    
    def clean(self):
        super().clean()
        
        # Validate clock times
        if self.clock_in and self.clock_out:
            if self.clock_out <= self.clock_in:
                raise ValidationError({
                    'clock_out': 'Clock-out time must be after clock-in time.'
                })
        
        # LEAVE and ABSENT types should not have clock times
        if self.attendance_type in ['LEAVE', 'ABSENT']:
            if self.clock_in or self.clock_out:
                raise ValidationError(
                    'LEAVE and ABSENT attendance types should not have clock-in/out times.'
                )

    def mark_absent(self):
        """
        Marks the attendance as ABSENT if no approved leave and no clock in/out.
        Also updates consecutive absences and AWOL status.
        """
        # Check for approved leave
        leave_exists = LeaveRequest.objects.filter(
            employee=self.employee,
            status='APPROVED',
            date=self.date,
        ).exists()

        if leave_exists:
            self.attendance_type = 'LEAVE'
            self.consecutive_absences = 0
            self.is_awol = False
        else:
            self.attendance_type = 'ABSENT'
            # Get previous day's attendance
            yesterday = self.date - timedelta(days=1)
            prev_attendance = DailyAttendance.objects.filter(
                employee=self.employee,
                date=yesterday
            ).first()
            if prev_attendance and prev_attendance.attendance_type == 'ABSENT':
                self.consecutive_absences = prev_attendance.consecutive_absences + 1
            else:
                self.consecutive_absences = 1
            
            # Flag AWOL after 3 consecutive absences
            if self.consecutive_absences >= 3:
                self.is_awol = True
        
        self.total_hours = Decimal('0.00')
        self.paid_hours = Decimal('0.00')
        self.break_hours = Decimal('0.00')
        self.is_late = False
        self.late_minutes = 0
        self.late_penalty_amount = Decimal('0.00')

    def approve(self, approved_by_user):
        """Approve the attendance record."""
        self.status = 'APPROVED'
        self.approved_by = approved_by_user
        self.approved_at = timezone.now()
        self.save()
    
    def reject(self, rejected_by_user, reason=''):
        """Reject the attendance record."""
        self.status = 'REJECTED'
        self.approved_by = rejected_by_user
        self.approved_at = timezone.now()
        if reason:
            self.notes = f"{self.notes}\nRejected: {reason}".strip()
        self.save()
    
    @staticmethod
    def _round(value: Decimal, places=2) -> Decimal:
        """Round to specified decimal places using ROUND_HALF_UP."""
        exp = Decimal(10) ** -places
        return Decimal(value).quantize(exp, rounding=ROUND_HALF_UP)
    
    def calculate_uniform_penalty(self):
        """Calculate total uniform penalty: ₱50 per missing item."""
        penalty = Decimal('0.00')
        if self.missing_uniform_shirt:
            penalty += Decimal('50.00')
        if self.missing_uniform_pants:
            penalty += Decimal('50.00')
        if self.missing_uniform_shoes:
            penalty += Decimal('50.00')
        self.uniform_penalty_amount = penalty
    
    def save(self, *args, **kwargs):
        """
        Save method that calculates penalties and attendance metrics.
        
        IMPORTANT: Late penalty is calculated IMMEDIATELY when clock_in is recorded,
        NOT when clock_out happens.
        """
        # Calculate uniform penalties
        self.calculate_uniform_penalty()
        
        # Auto-mark as ABSENT if no clock in/out and not LEAVE
        if not self.clock_in and not self.clock_out and self.attendance_type not in ['LEAVE', 'ABSENT']:
            self.mark_absent()
        else:
            # Calculate LATENESS immediately when clock_in exists (even without clock_out)
            if self.clock_in and self.attendance_type not in ['LEAVE', 'ABSENT']:
                self.calculate_lateness()
            
            # Only compute full attendance metrics when BOTH clock_in and clock_out exist
            if self.clock_in and self.clock_out and self.attendance_type not in ['LEAVE', 'ABSENT']:
                self.compute_attendance_metrics()
        
        super().save(*args, **kwargs)

    def calculate_lateness(self):
        """
        Calculate late penalty IMMEDIATELY based on clock-in time.
        This runs as soon as employee clocks in, even before they clock out.
        
        RULES:
        - More than 60 minutes late → INVALID attendance + REJECTED status
        - 16-60 minutes late → Late penalty applies
        - 0-15 minutes late → Grace period, no penalty
        """
        from payroll.models import PayrollSettings
        
        # Load settings
        morning_start = time(8, 0)
        afternoon_start = time(13, 0)
        grace_minutes = 15
        
        try:
            settings = PayrollSettings.objects.first()
            if settings:
                morning_start = settings.shift_start or morning_start
                grace_minutes = settings.grace_minutes or grace_minutes
        except Exception:
            pass
        
        # Get timezone
        tz = timezone.get_current_timezone()
        
        # Ensure clock_in is timezone-aware
        clock_in_local = self.clock_in
        if not timezone.is_aware(clock_in_local):
            clock_in_local = timezone.make_aware(clock_in_local, tz)
        
        # Extract date from clock_in in LOCAL timezone
        local_date = clock_in_local.astimezone(tz).date()
        
        # Create shift start times
        morning_start_dt = datetime.combine(local_date, morning_start)
        afternoon_start_dt = datetime.combine(local_date, afternoon_start)
        
        # Make them timezone-aware
        morning_start_dt = timezone.make_aware(morning_start_dt, tz)
        afternoon_start_dt = timezone.make_aware(afternoon_start_dt, tz)
        
        # Determine which shift they're clocking in for
        if clock_in_local < afternoon_start_dt:
            # Morning shift - expected start is 8:00 AM (or configured time)
            expected_start = morning_start_dt
        else:
            # Afternoon shift - expected start is 1:00 PM
            expected_start = afternoon_start_dt
        
        # Calculate how late they are (in minutes)
        late_minutes = (clock_in_local - expected_start).total_seconds() / 60
        
        # Reset late fields first
        self.is_late = False
        self.late_minutes = 0
        self.late_penalty_amount = Decimal("0.00")
        
        # Determine if late and calculate penalty
        if late_minutes < 0:
            # Arrived EARLY - no penalty
            pass
        elif late_minutes <= grace_minutes:
            # Within grace period - no penalty
            pass
        else:
            # LATE beyond grace period
            self.is_late = True
            
            # Calculate actual late minutes (excluding grace period)
            actual_late_minutes = late_minutes - grace_minutes
            self.late_minutes = int(actual_late_minutes)
            hours = int(late_minutes) // 60
            minutes = int(late_minutes) % 60
            time_str = f"{hours} hours  & {minutes} minutes" if hours > 0 else f"{minutes} minutes" if minutes > 0 else '0 minute'
            
            # Check if MORE than 60 minutes late (INVALID)
            if late_minutes > 60:
                # Too late - mark as INVALID and REJECTED immediately
                self.attendance_type = "INVALID"
                self.status = 'REJECTED'
                self.paid_hours = Decimal("0.00")
                self.break_hours = Decimal("0.00")
                self.total_hours = Decimal("0.00")
                self.late_penalty_amount = Decimal("0.00")  # No penalty for invalid
                self.clock_out = self.clock_in
                self.notes = f"{self.notes}\nRejected: More than 60 minutes. Late (late by {time_str})".strip()
            else:
                # 16-60 minutes late - calculate penalty
                self.late_penalty_amount = self._round(
                    Decimal(self.late_minutes) * Decimal("2.00")
                )

    def compute_attendance_metrics(self):
        """
        Computes attendance type, paid hours, and break hours.

        NOTE: Lateness is already calculated in calculate_lateness().
        This method only determines attendance type and paid hours.
        
        RULES:
        - Less than 1 hour worked → INVALID + REJECTED
        """
        from payroll.models import PayrollSettings

        # Load settings
        morning_start = time(8, 0)
        afternoon_start = time(13, 0)
        shift_end = time(18, 0)
        grace_minutes = 15

        try:
            settings = PayrollSettings.objects.first()
            if settings:
                morning_start = settings.shift_start or morning_start
                grace_minutes = settings.grace_minutes or grace_minutes
                shift_end = settings.shift_end or shift_end
        except Exception:
            pass

        # Get timezone
        tz = timezone.get_current_timezone()

        # Ensure clock times are timezone-aware
        clock_in_local = self.clock_in
        clock_out_local = self.clock_out
        
        if not timezone.is_aware(clock_in_local):
            clock_in_local = timezone.make_aware(clock_in_local, tz)
        if clock_out_local and not timezone.is_aware(clock_out_local):
            clock_out_local = timezone.make_aware(clock_out_local, tz)

        # Extract date from clock_in in LOCAL timezone
        local_date = clock_in_local.astimezone(tz).date()
        
        # Create shift times on the SAME DATE as clock_in (in local timezone)
        morning_start_dt = datetime.combine(local_date, morning_start)
        afternoon_start_dt = datetime.combine(local_date, afternoon_start)
        shift_end_dt = datetime.combine(local_date, shift_end)

        # Make shift times timezone-aware
        morning_start_dt = timezone.make_aware(morning_start_dt, tz)
        afternoon_start_dt = timezone.make_aware(afternoon_start_dt, tz)
        shift_end_dt = timezone.make_aware(shift_end_dt, tz)

        # Auto-close if enabled
        if settings and settings.auto_close_enabled and clock_in_local and not clock_out_local:
            clock_out_local = shift_end_dt
            self.clock_out = clock_out_local
            self.auto_closed = True

        # Calculate hours
        delta = clock_out_local - clock_in_local
        total_hours = Decimal(delta.total_seconds()) / Decimal(3600)
        total_hours = self._round(total_hours)
        self.total_hours = total_hours

        # Don't reset attendance_type if already INVALID from late check
        if self.attendance_type != "INVALID":
            self.attendance_type = "INVALID"
            self.break_hours = Decimal("0.00")
            self.paid_hours = Decimal("0.00")

        # If already marked INVALID from lateness check, don't continue
        if self.status == 'REJECTED':
            return
        
        # INVALID (<1 hour worked) - Mark as REJECTED
        if total_hours < Decimal("1.00"):
            self.attendance_type = "INVALID"
            self.status = 'REJECTED'
            self.paid_hours = Decimal("0.00")
            self.break_hours = Decimal("0.00")
            self.notes = f"{self.notes}\nRejected: Less than 1 hour worked (total: {total_hours} hours)".strip()
            return

        # PARTIAL (1h - <4h worked)
        if total_hours < Decimal("4.00"):
            self.attendance_type = "PARTIAL"
            self.paid_hours = total_hours
            return

        # Determine which shift based on clock-in time
        if clock_in_local < afternoon_start_dt:
            expected_end = afternoon_start_dt  # 1:00 PM
            break_hours = Decimal("1.00")
        else:
            expected_end = shift_end_dt  # 6:00 PM
            break_hours = Decimal("1.00")

        # FULL DAY (clocked in morning, stayed until 6 PM, worked ≥10 hours)
        if clock_in_local <= morning_start_dt + timedelta(minutes=grace_minutes) \
        and clock_out_local >= shift_end_dt \
        and total_hours >= Decimal("10.00"):
            self.attendance_type = "FULL_DAY"
            self.break_hours = Decimal("2.00")
            self.paid_hours = Decimal("8.00")
            return

        # HALF DAY (worked ≥4h and stayed until expected shift end)
        if total_hours >= Decimal("4.00") and clock_out_local >= expected_end:
            self.attendance_type = "HALF_DAY"
            self.break_hours = break_hours
            self.paid_hours = Decimal("4.00")
            return

        # Fallback PARTIAL
        self.attendance_type = "PARTIAL"
        self.paid_hours = total_hours

class LeaveBalance(models.Model):
    """
    Annual leave balance for an employee.
    
    Business Rules:
    - Max 5 sick leave days per year
    - Max 5 emergency leave days per year
    - All leaves are unpaid
    - Balances reset on January 1 each year
    """
    
    employee = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='leave_balances',
    )
    year = models.PositiveIntegerField()
    
    # Sick Leave
    sick_leave_total = models.PositiveIntegerField(
        default=5,
        help_text='Total sick leave days allocated for the year',
    )
    sick_leave_used = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Sick leave days used (supports half-days)',
    )
    
    # Emergency Leave
    emergency_leave_total = models.PositiveIntegerField(
        default=5,
        help_text='Total emergency leave days allocated for the year',
    )
    emergency_leave_used = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Emergency leave days used (supports half-days)',
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('employee', 'year')
        indexes = [
            models.Index(fields=['employee', 'year']),
            models.Index(fields=['year']),
        ]
        ordering = ['-year', 'employee']
        verbose_name = 'Leave Balance'
        verbose_name_plural = 'Leave Balances'
    
    def __str__(self):
        return f"{self.employee.get_full_name()} - {self.year} Leave Balance"
    
    @property
    def sick_leave_remaining(self) -> Decimal:
        """Calculate remaining sick leave days."""
        return Decimal(self.sick_leave_total) - Decimal(self.sick_leave_used)
    
    @property
    def emergency_leave_remaining(self) -> Decimal:
        """Calculate remaining emergency leave days."""
        return Decimal(self.emergency_leave_total) - Decimal(self.emergency_leave_used)
    
    def can_take_leave(self, leave_type: str, days: Decimal = Decimal('1.00')) -> bool:
        """
        Check if employee has sufficient leave balance.
        
        Args:
            leave_type: 'SICK' or 'EMERGENCY'
            days: Number of days to take (supports 0.5 for half-day)
        
        Returns:
            True if sufficient balance exists
        """
        if leave_type == 'SICK':
            return self.sick_leave_remaining >= days
        elif leave_type == 'EMERGENCY':
            return self.emergency_leave_remaining >= days
        return False
    
    def deduct_leave(self, leave_type: str, days: Decimal = Decimal('1.00')):
        """
        Deduct leave from balance.
        
        Args:
            leave_type: 'SICK' or 'EMERGENCY'
            days: Number of days to deduct (supports 0.5 for half-day)
        
        Note:
            Validation should be done before calling this method
        """
        if leave_type == 'SICK':
            self.sick_leave_used += days
        elif leave_type == 'EMERGENCY':
            self.emergency_leave_used += days
        
        self.save()
    
    def restore_leave(self, leave_type: str, days: Decimal = Decimal('1.00')):
        """
        Restore leave to balance (when leave request is cancelled).
        
        Args:
            leave_type: 'SICK' or 'EMERGENCY'
            days: Number of days to restore
        """
        if leave_type == 'SICK':
            self.sick_leave_used = max(Decimal('0.00'), self.sick_leave_used - days)
        elif leave_type == 'EMERGENCY':
            self.emergency_leave_used = max(Decimal('0.00'), self.emergency_leave_used - days)
        
        self.save()

    def get_remaining_balance(self, leave_type: str) -> Decimal:
        """
        Get remaining leave balance for the specified leave type.
        
        Args:
            leave_type: 'SICK' or 'EMERGENCY'
        Returns:
            Remaining leave balance as Decimal
        """
        if leave_type == 'SICK':
            return self.sick_leave_remaining
        elif leave_type == 'EMERGENCY':
            return self.emergency_leave_remaining
        return Decimal('0.00')
class LeaveRequest(models.Model):
    """
    Leave request submitted by employee or created by admin/manager.
    
    Business Rules:
    - Requires approval from admin/manager
    - Approved leave creates DailyAttendance with type=LEAVE
    - Deducts from employee's leave balance
    - Can be full-day (1.0) or half-day (0.5)
    """
    
    LEAVE_TYPE_CHOICES = [
        ('SICK', 'Sick Leave'),
        ('EMERGENCY', 'Emergency Leave'),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    SHIFT_PERIOD_CHOICES = [
        ('AM', 'Morning'),
        ('PM', 'Afternoon'),
        ('FULL', 'Full Day'),
    ]
    
    employee = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='leave_requests',
    )
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPE_CHOICES)
    date = models.DateField()
    
    is_half_day = models.BooleanField(
        default=False,
        help_text='True if half-day leave (0.5 days), False for full-day (1.0 days)',
    )
    
    shift_period = models.CharField(
        max_length=10,
        choices=SHIFT_PERIOD_CHOICES,
        default='FULL',
        help_text='AM, PM, or FULL day - determines which shift the leave applies to',
    )
    
    reason = models.TextField()
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING',
    )
    
    approved_by = models.ForeignKey(
        'users.CustomUser',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_leave_requests',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    
    rejection_reason = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['employee', 'date']),
            models.Index(fields=['date']),
            models.Index(fields=['status']),
            models.Index(fields=['leave_type']),
        ]
        ordering = ['-date', 'employee']
        verbose_name = 'Leave Request'
        verbose_name_plural = 'Leave Requests'
    
    def __str__(self):
        days_str = '0.5 days' if self.is_half_day else '1.0 day'
        return f"{self.employee.get_full_name()} - {self.get_leave_type_display()} on {self.date} ({days_str})"
    
    def clean(self):
        super().clean()
        # Validation moved to serializer for better error handling
    
    @property
    def days_count(self) -> Decimal:
        """Return the number of days this leave represents."""
        return Decimal('0.5') if self.is_half_day else Decimal('1.0')
    
    def save(self, skip_validation=False, *args, **kwargs):
        """
        Save the leave request.
        Balance deduction is now handled in the serializer.
        
        Args:
            skip_validation: If True, skips validation (used when called from serializer)
        """
        super().save(*args, **kwargs)
    
    def approve(self, approved_by_user):
        """
        Approve the leave request.
        - Balance already deducted on creation
        - Creates DailyAttendance record with type=LEAVE
        """
        if self.status != 'PENDING':
            raise ValidationError(
                f'Cannot approve leave request with status: {self.status}'
            )
        
        # Create DailyAttendance record
        DailyAttendance.objects.update_or_create(
            employee=self.employee,
            date=self.date,
            defaults={
                'attendance_type': 'LEAVE',
                'status': 'APPROVED',
                'paid_hours': Decimal('0.00'),
                'approved_by': approved_by_user,
                'approved_at': timezone.now(),
                'is_late': False,
                'late_minutes': 0,
                'late_penalty_amount': Decimal('0.00'),
                'notes': f'{self.get_leave_type_display()} ({self.get_shift_period_display()}) - {self.reason}',
            }
        )
        
        # Update leave request status
        self.status = 'APPROVED'
        self.approved_by = approved_by_user
        self.approved_at = timezone.now()
        self.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
    
    def reject(self, rejected_by_user, reason=''):
        """
        Reject the leave request and restore leave balance.
        """
        if self.status == 'REJECTED':
            raise ValidationError('Leave request is already rejected.')
        
        # Restore leave balance
        year = self.date.year
        try:
            leave_balance = LeaveBalance.objects.get(employee=self.employee, year=year)
            leave_balance.restore_leave(self.leave_type, self.days_count)
        except LeaveBalance.DoesNotExist:
            pass  # Balance doesn't exist, nothing to restore
        
        self.status = 'REJECTED'
        self.approved_by = rejected_by_user
        self.approved_at = timezone.now()
        self.rejection_reason = reason
        self.save(update_fields=['status', 'approved_by', 'approved_at', 'rejection_reason', 'updated_at'])
    
    def cancel(self):
        """
        Cancel a leave request (pending or approved).
        - For PENDING: Just marks as CANCELLED and restores balance
        - For APPROVED: Also deletes/marks DailyAttendance as deleted
        """
        if self.status not in ['PENDING', 'APPROVED']:
            raise ValidationError('Only pending or approved leave requests can be cancelled.')
        
        # Restore leave balance
        year = self.date.year
        try:
            leave_balance = LeaveBalance.objects.get(employee=self.employee, year=year)
            leave_balance.restore_leave(self.leave_type, self.days_count)
        except LeaveBalance.DoesNotExist:
            pass  # Balance doesn't exist, nothing to restore
        
        # If approved, remove DailyAttendance record
        if self.status == 'APPROVED':
            DailyAttendance.objects.filter(
                employee=self.employee,
                date=self.date,
                attendance_type='LEAVE'
            ).update(is_deleted=True)
        
        # Update status
        self.status = 'CANCELLED'
        self.save()


class Offense(models.Model):
    """
    Track employee offenses for policy violations.
    
    Offense Types:
    - AWOL: Absent Without Leave (not part of DailyAttendance)
    - LATE: Accumulated late arrivals
    - CURFEW: Not at home by 10 PM (manually added by admin)
    - OTHER: Other policy violations
    
    Severity Levels (Based on Offense Count):
    - 1st offense: Warning
    - 2nd offense: Suspension (admin-defined days)
    - 3rd offense: Termination
    """
    
    OFFENSE_TYPE_CHOICES = [
        ('AWOL', 'Absent Without Leave'),
        ('LATE', 'Late Arrival'),
        ('CURFEW', 'Curfew Violation'),
        ('OTHER', 'Other Violation'),
    ]
    
    SEVERITY_LEVEL_CHOICES = [
        ('WARNING', '1st Offense - Warning'),
        ('SUSPENSION', '2nd Offense - Suspension'),
        ('TERMINATION', '3rd Offense - Termination'),
    ]
    
    employee = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='offenses'
    )
    offense_type = models.CharField(
        max_length=20,
        choices=OFFENSE_TYPE_CHOICES
    )
    severity_level = models.CharField(
        max_length=20,
        choices=SEVERITY_LEVEL_CHOICES
    )
    date = models.DateField(
        help_text='Date of the offense'
    )
    description = models.TextField(
        help_text='Detailed description of the offense'
    )
    penalty_days = models.IntegerField(
        default=0,
        help_text='Number of suspension days (for 2nd offense)'
    )
    suspension_start_date = models.DateField(
        null=True,
        blank=True,
        help_text='Start date of suspension (for 2nd offense)'
    )
    suspension_end_date = models.DateField(
        null=True,
        blank=True,
        help_text='End date of suspension (for 2nd offense)'
    )
    created_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        related_name='offenses_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(
        blank=True,
        help_text='Additional notes or comments'
    )
    
    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['employee', '-date']),
            models.Index(fields=['offense_type']),
            models.Index(fields=['severity_level']),
        ]
    
    def __str__(self):
        return f"{self.employee.user.get_full_name()} - {self.get_offense_type_display()} ({self.get_severity_level_display()}) - {self.date}"
    
    def save(self, *args, **kwargs):
        # Auto-calculate suspension end date if suspension_start_date and penalty_days are provided
        if self.suspension_start_date and self.penalty_days > 0 and not self.suspension_end_date:
            self.suspension_end_date = self.suspension_start_date + timedelta(days=self.penalty_days - 1)
        super().save(*args, **kwargs)
    
    @staticmethod
    def get_offense_count(employee):
        """Get total offense count for an employee"""
        return Offense.objects.filter(employee=employee).count()
    
    @staticmethod
    def get_offense_summary(employee):
        """Get summary of offenses by type for an employee"""
        from django.db.models import Count
        return Offense.objects.filter(employee=employee).values('offense_type').annotate(count=Count('id'))
    
    @staticmethod
    def is_at_limit(employee, threshold=3):
        """Check if employee is at or near offense limit"""
        count = Offense.get_offense_count(employee)
        return count >= threshold
    
    @staticmethod
    def is_employee_suspended(employee):
        """Check if employee is currently suspended"""
        from django.utils import timezone
        today = timezone.now().date()
        
        # Check for active suspensions
        active_suspension = Offense.objects.filter(
            employee=employee,
            severity_level='SUSPENSION',
            suspension_start_date__lte=today,
            suspension_end_date__gte=today
        ).exists()
        
        return active_suspension
