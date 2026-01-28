from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


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
    
    def save(self, *args, **kwargs):
        # Auto-compute fields before saving
        if self.clock_in and self.clock_out and self.attendance_type not in ['LEAVE', 'ABSENT']:
            self.compute_attendance_metrics()
        
        super().save(*args, **kwargs)
    
    def compute_attendance_metrics(self):
        """
        Computes attendance type, hours, late penalties based on business rules.
        Must be called after clock_in and clock_out are set.
        """
        if not self.clock_in or not self.clock_out:
            return
        
        # Get payroll settings for shift times and grace period
        from payroll.models import PayrollSettings
        try:
            settings_obj = PayrollSettings.objects.first()
            shift_start = settings_obj.shift_start if settings_obj else time(8, 0)
            grace_minutes = settings_obj.grace_minutes if settings_obj else 15
        except Exception:
            shift_start = time(8, 0)
            grace_minutes = 15
        
        # Convert to local time
        clock_in_local = timezone.localtime(self.clock_in) if timezone.is_aware(self.clock_in) else self.clock_in
        clock_out_local = timezone.localtime(self.clock_out) if timezone.is_aware(self.clock_out) else self.clock_out
        
        # Calculate total hours
        delta = self.clock_out - self.clock_in
        total_hours = Decimal(delta.total_seconds()) / Decimal(3600)
        self.total_hours = self._round(total_hours)
        
        # Check if late
        expected_clock_in = datetime.combine(self.date, shift_start)
        if timezone.is_aware(self.clock_in):
            expected_clock_in = timezone.make_aware(expected_clock_in, timezone.get_current_timezone())
        
        late_delta = (self.clock_in - expected_clock_in).total_seconds() / 60
        
        if late_delta > grace_minutes:
            self.is_late = True
            self.late_minutes = int(late_delta - grace_minutes)
            
            # # ≥30 min late = automatic HALF_DAY
            # if late_delta >= 30:
            #     self.attendance_type = 'HALF_DAY'
            #     self.break_hours = Decimal('1.00')
            #     self.paid_hours = Decimal('4.00')
            #     self.late_penalty_amount = Decimal('0.00')  # No per-minute penalty if already half-day
            #     return
            
            # # 16-29 min late: ₱2 per minute penalty
            self.late_penalty_amount = self._round(Decimal(self.late_minutes) * Decimal('2.00'))
        else:
            self.is_late = False
            self.late_minutes = 0
            self.late_penalty_amount = Decimal('0.00')
        
        # Determine attendance type based on total hours
        if total_hours >= Decimal('10.00'):
            # FULL_DAY: ≥10 hours = 8 paid hours
            self.attendance_type = 'FULL_DAY'
            self.break_hours = Decimal('2.00')
            self.paid_hours = Decimal('8.00')
        
        elif total_hours >= Decimal('5.00') and total_hours < Decimal('10.00'):
            # PARTIAL: 5-10 hours = actual hours minus breaks
            self.attendance_type = 'PARTIAL'
            # Break deduction: if they worked during break times, deduct 2 hours
            # Simplified: assume 2-hour break if covering 12 PM - 3 PM range
            self.break_hours = Decimal('2.00')
            paid = max(total_hours - self.break_hours, Decimal('0.00'))
            self.paid_hours = self._round(paid)
        
        elif total_hours >= Decimal('4.00') and total_hours < Decimal('5.00'):
            # HALF_DAY: 4-5 hours = 4 paid hours
            self.attendance_type = 'HALF_DAY'
            self.break_hours = Decimal('1.00')
            self.paid_hours = Decimal('4.00')
        
        else:
            # Less than 4 hours: mark as PARTIAL with minimal pay
            self.attendance_type = 'PARTIAL'
            self.break_hours = Decimal('0.00')
            self.paid_hours = self._round(total_hours)
    
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
        
        Raises:
            ValidationError if insufficient balance
        """
        if not self.can_take_leave(leave_type, days):
            raise ValidationError(f'Insufficient {leave_type.lower()} leave balance.')
        
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
        
        # Prevent duplicate leave requests for the same date
        if self.pk is None:  # New instance
            existing = LeaveRequest.objects.filter(
                employee=self.employee,
                date=self.date,
                status__in=['PENDING', 'APPROVED']
            ).exists()
            
            if existing:
                raise ValidationError(
                    f'A leave request already exists for {self.date}.'
                )
    
    @property
    def days_count(self) -> Decimal:
        """Return the number of days this leave represents."""
        return Decimal('0.5') if self.is_half_day else Decimal('1.0')
    
    def approve(self, approved_by_user):
        """
        Approve the leave request.
        - Deducts from employee's leave balance
        - Creates DailyAttendance record with type=LEAVE
        """
        if self.status == 'APPROVED':
            raise ValidationError('Leave request is already approved.')
        
        # Get or create leave balance for the year
        year = self.date.year
        leave_balance, created = LeaveBalance.objects.get_or_create(
            employee=self.employee,
            year=year,
            defaults={
                'sick_leave_total': 5,
                'emergency_leave_total': 5,
            }
        )
        
        # Check if sufficient balance
        if not leave_balance.can_take_leave(self.leave_type, self.days_count):
            raise ValidationError(
                f'Insufficient {self.get_leave_type_display()} balance. '
                f'Remaining: {leave_balance.sick_leave_remaining if self.leave_type == "SICK" else leave_balance.emergency_leave_remaining} days.'
            )
        
        # Deduct from balance
        leave_balance.deduct_leave(self.leave_type, self.days_count)
        
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
                'notes': f'{self.get_leave_type_display()} - {self.reason}',
            }
        )
        
        # Update leave request status
        self.status = 'APPROVED'
        self.approved_by = approved_by_user
        self.approved_at = timezone.now()
        self.save()
    
    def reject(self, rejected_by_user, reason=''):
        """Reject the leave request."""
        if self.status == 'REJECTED':
            raise ValidationError('Leave request is already rejected.')
        
        self.status = 'REJECTED'
        self.approved_by = rejected_by_user
        self.approved_at = timezone.now()
        self.rejection_reason = reason
        self.save()
    
    def cancel(self):
        """
        Cancel an approved leave request.
        - Restores leave balance
        - Deletes or marks DailyAttendance as deleted
        """
        if self.status != 'APPROVED':
            raise ValidationError('Only approved leave requests can be cancelled.')
        
        # Restore leave balance
        year = self.date.year
        try:
            leave_balance = LeaveBalance.objects.get(employee=self.employee, year=year)
            leave_balance.restore_leave(self.leave_type, self.days_count)
        except LeaveBalance.DoesNotExist:
            pass  # Balance doesn't exist, nothing to restore
        
        # Remove DailyAttendance record
        DailyAttendance.objects.filter(
            employee=self.employee,
            date=self.date,
            attendance_type='LEAVE'
        ).update(is_deleted=True)
        
        # Update status
        self.status = 'CANCELLED'
        self.save()
