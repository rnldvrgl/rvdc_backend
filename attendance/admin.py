from django.contrib import admin
from django.contrib import messages
from django.db import transaction
from django.utils.html import format_html
from django.utils import timezone
from .models import DailyAttendance, LeaveBalance, LeaveRequest, Offense, OvertimeRequest


@admin.register(DailyAttendance)
class DailyAttendanceAdmin(admin.ModelAdmin):
    list_display = [
        'employee',
        'date',
        'attendance_type',
        'clock_in_display',
        'clock_out_display',
        'paid_hours',
        'late_penalty_display',
        'uniform_penalty_display',
        'auto_close_warning_display',
        'awol_flag_display',
        'status',
        'approved_by',
    ]
    list_filter = [
        'status',
        'attendance_type',
        'is_late',
        'auto_closed',
        'is_awol',
        'missing_uniform_shirt',
        'missing_uniform_pants',
        'missing_uniform_shoes',
        'date',
    ]
    search_fields = [
        'employee__first_name',
        'employee__last_name',
        'employee__username',
        'notes',
    ]
    readonly_fields = [
        'total_hours',
        'break_hours',
        'paid_hours',
        'is_late',
        'late_minutes',
        'late_penalty_amount',
        'uniform_penalty_amount',
        'consecutive_absences',
        'approved_at',
        'created_at',
        'updated_at',
    ]
    fieldsets = (
        ('Employee Information', {
            'fields': ('employee', 'date')
        }),
        ('Clock Times', {
            'fields': ('clock_in', 'clock_out', 'auto_closed')
        }),
        ('Computed Metrics', {
            'fields': (
                'attendance_type',
                'total_hours',
                'break_hours',
                'paid_hours',
            )
        }),
        ('Late Tracking', {
            'fields': (
                'is_late',
                'late_minutes',
                'late_penalty_amount',
            )
        }),
        ('Uniform Penalties', {
            'fields': (
                'missing_uniform_shirt',
                'missing_uniform_pants',
                'missing_uniform_shoes',
                'uniform_penalty_amount',
            ),
            'description': 'Mark missing uniform items. Each item incurs a ₱50 penalty.',
        }),
        ('Absence & AWOL Tracking', {
            'fields': (
                'consecutive_absences',
                'is_awol',
            )
        }),
        ('Auto-Close Warnings', {
            'fields': (
                'auto_close_warning_count',
            ),
            'description': 'Cumulative count of auto-close warnings for this employee.',
        }),
        ('Approval', {
            'fields': (
                'status',
                'approved_by',
                'approved_at',
                'notes',
            )
        }),
        ('System', {
            'fields': ('is_deleted', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def clock_in_display(self, obj):
        if obj.clock_in:
            # Check if USE_TZ is enabled in settings
            try:
                from django.conf import settings
                if settings.USE_TZ:
                    # Convert UTC to local timezone
                    local_tz = timezone.get_current_timezone()
                    local_time = obj.clock_in.astimezone(local_tz)
                    return local_time.strftime('%I:%M %p')
                else:
                    # Already in local timezone
                    return obj.clock_in.strftime('%I:%M %p')
            except:
                return obj.clock_in.strftime('%I:%M %p')
        return '-'
    clock_in_display.short_description = 'Clock In'
    
    def clock_out_display(self, obj):
        if obj.clock_out:
            # Check if USE_TZ is enabled in settings
            try:
                from django.conf import settings
                if settings.USE_TZ:
                    # Convert UTC to local timezone
                    local_tz = timezone.get_current_timezone()
                    local_time = obj.clock_out.astimezone(local_tz)
                    display = local_time.strftime('%I:%M %p')
                else:
                    # Already in local timezone
                    display = obj.clock_out.strftime('%I:%M %p')
            except:
                display = obj.clock_out.strftime('%I:%M %p')
            
            if obj.auto_closed:
                return format_html(
                    '<span style="color: orange;" title="Auto-closed">{} ⚠</span>',
                    display
                )
            return display
        return '-'
    clock_out_display.short_description = 'Clock Out'
    
    def late_penalty_display(self, obj):
        if obj.late_penalty_amount > 0:
            return format_html(
                '<span style="color: red;">-₱{}</span>',
                obj.late_penalty_amount
            )
        return '-'
    late_penalty_display.short_description = 'Late Penalty'
    
    def uniform_penalty_display(self, obj):
        if obj.uniform_penalty_amount > 0:
            items = []
            if obj.missing_uniform_shirt:
                items.append('Shirt')
            if obj.missing_uniform_pants:
                items.append('Pants')
            if obj.missing_uniform_shoes:
                items.append('Shoes')
            
            items_str = ', '.join(items) if items else 'Unknown'
            
            return format_html(
                '<span style="color: red;" title="Missing: {}">-₱{}</span>',
                items_str,
                obj.uniform_penalty_amount
            )
        return '-'
    uniform_penalty_display.short_description = 'Uniform Penalty'
    
    def auto_close_warning_display(self, obj):
        if obj.auto_close_warning_count > 0:
            color = 'orange' if obj.auto_close_warning_count < 3 else 'red'
            return format_html(
                '<span style="color: {}; font-weight: bold;">{} warning(s)</span>',
                color,
                obj.auto_close_warning_count
            )
        return '-'
    auto_close_warning_display.short_description = 'Auto-Close Warnings'
    
    def awol_flag_display(self, obj):
        if obj.is_awol:
            return format_html(
                '<span style="color: red; font-weight: bold;" title="{} consecutive absences">AWOL ⚠</span>',
                obj.consecutive_absences
            )
        return '-'
    awol_flag_display.short_description = 'AWOL Status'
    
    def save_model(self, request, obj, form, change):
        """
        Override save_model to handle transaction errors gracefully.
        Wraps the save operation in an atomic transaction with proper error handling.
        """
        try:
            with transaction.atomic():
                super().save_model(request, obj, form, change)
        except Exception as e:
            # Log the error and display a user-friendly message
            messages.error(
                request,
                f"Error saving attendance record: {str(e)}. "
                f"Please check the data and try again."
            )
            # Re-raise to prevent silent failures
            raise
    
    actions = [
        'approve_attendance',
        'reject_attendance',
        'reset_auto_close_warnings',
        'clear_awol_flag',
    ]
    
    def approve_attendance(self, request, queryset):
        count = 0
        errors = []
        
        for attendance in queryset:
            if attendance.status == 'PENDING':
                try:
                    with transaction.atomic():
                        attendance.approve(request.user)
                        count += 1
                except Exception as e:
                    errors.append(f"{attendance.employee.get_full_name()} ({attendance.date}): {str(e)}")
        
        if count:
            self.message_user(request, f'{count} attendance record(s) approved.')
        if errors:
            self.message_user(
                request,
                'Errors occurred: ' + '; '.join(errors),
                level=messages.ERROR
            )
    approve_attendance.short_description = 'Approve selected attendance'
    
    def reject_attendance(self, request, queryset):
        count = 0
        errors = []
        
        for attendance in queryset:
            if attendance.status == 'PENDING':
                try:
                    with transaction.atomic():
                        attendance.reject(request.user, reason='Rejected via admin')
                        count += 1
                except Exception as e:
                    errors.append(f"{attendance.employee.get_full_name()} ({attendance.date}): {str(e)}")
        
        if count:
            self.message_user(request, f'{count} attendance record(s) rejected.')
        if errors:
            self.message_user(
                request,
                'Errors occurred: ' + '; '.join(errors),
                level=messages.ERROR
            )
    reject_attendance.short_description = 'Reject selected attendance'
    
    def reset_auto_close_warnings(self, request, queryset):
        """Reset auto-close warning count to zero for selected records."""
        count = queryset.update(auto_close_warning_count=0)
        self.message_user(
            request,
            f'Reset auto-close warnings for {count} attendance record(s).'
        )
    reset_auto_close_warnings.short_description = 'Reset auto-close warning count'
    
    def clear_awol_flag(self, request, queryset):
        """Clear AWOL flag and reset consecutive absences."""
        count = queryset.filter(is_awol=True).update(
            is_awol=False,
            consecutive_absences=0
        )
        self.message_user(
            request,
            f'Cleared AWOL flag for {count} attendance record(s).'
        )
    clear_awol_flag.short_description = 'Clear AWOL flag'


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = [
        'employee',
        'year',
        'sick_leave_remaining_display',
        'emergency_leave_remaining_display',
        'created_at',
    ]
    list_filter = ['year']
    search_fields = [
        'employee__first_name',
        'employee__last_name',
        'employee__username',
    ]
    readonly_fields = [
        'sick_leave_remaining',
        'emergency_leave_remaining',
        'created_at',
        'updated_at',
    ]
    fieldsets = (
        ('Employee & Year', {
            'fields': ('employee', 'year')
        }),
        ('Sick Leave', {
            'fields': (
                'sick_leave_total',
                'sick_leave_used',
                'sick_leave_remaining',
            )
        }),
        ('Emergency Leave', {
            'fields': (
                'emergency_leave_total',
                'emergency_leave_used',
                'emergency_leave_remaining',
            )
        }),
        ('System', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def sick_leave_remaining_display(self, obj):
        remaining = obj.sick_leave_remaining
        color = 'green' if remaining >= 3 else 'orange' if remaining >= 1 else 'red'
        return format_html(
            '<span style="color: {};">{} / {} days</span>',
            color,
            remaining,
            obj.sick_leave_total
        )
    sick_leave_remaining_display.short_description = 'Sick Leave'
    
    def emergency_leave_remaining_display(self, obj):
        remaining = obj.emergency_leave_remaining
        color = 'green' if remaining >= 3 else 'orange' if remaining >= 1 else 'red'
        return format_html(
            '<span style="color: {};">{} / {} days</span>',
            color,
            remaining,
            obj.emergency_leave_total
        )
    emergency_leave_remaining_display.short_description = 'Emergency Leave'


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = [
        'employee',
        'leave_type',
        'date',
        'days_display',
        'status',
        'approved_by',
        'created_at',
    ]
    list_filter = [
        'status',
        'leave_type',
        'is_half_day',
        'date',
    ]
    search_fields = [
        'employee__first_name',
        'employee__last_name',
        'employee__username',
        'reason',
        'rejection_reason',
    ]
    readonly_fields = [
        'days_count',
        'approved_at',
        'created_at',
        'updated_at',
    ]
    fieldsets = (
        ('Leave Details', {
            'fields': (
                'employee',
                'leave_type',
                'date',
                'is_half_day',
                'days_count',
                'reason',
            )
        }),
        ('Approval', {
            'fields': (
                'status',
                'approved_by',
                'approved_at',
                'rejection_reason',
            )
        }),
        ('System', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def days_display(self, obj):
        return f"{obj.days_count} day(s)"
    days_display.short_description = 'Days'
    
    actions = ['approve_leave', 'reject_leave']
    
    def approve_leave(self, request, queryset):
        count = 0
        errors = []
        
        for leave in queryset:
            if leave.status == 'PENDING':
                try:
                    leave.approve(request.user)
                    count += 1
                except Exception as e:
                    errors.append(f"{leave.employee.get_full_name()} ({leave.date}): {str(e)}")
        
        if count:
            self.message_user(request, f'{count} leave request(s) approved.')
        if errors:
            self.message_user(request, 'Errors: ' + '; '.join(errors), level='error')
    approve_leave.short_description = 'Approve selected leave requests'
    
    def reject_leave(self, request, queryset):
        count = 0
        for leave in queryset:
            if leave.status == 'PENDING':
                try:
                    leave.reject(request.user, reason='Rejected via admin')
                    count += 1
                except Exception as e:
                    pass
        
        self.message_user(request, f'{count} leave request(s) rejected.')
    reject_leave.short_description = 'Reject selected leave requests'


@admin.register(Offense)
class OffenseAdmin(admin.ModelAdmin):
    list_display = [
        'employee',
        'offense_type',
        'severity_level',
        'date',
        'penalty_days',
        'suspension_period_display',
        'offense_count_display',
        'created_by',
        'created_at',
    ]
    list_filter = [
        'offense_type',
        'severity_level',
        'date',
        'created_at',
    ]
    search_fields = [
        'employee__first_name',
        'employee__last_name',
        'employee__username',
        'employee__id_number',
        'description',
        'notes',
    ]
    readonly_fields = [
        'created_at',
        'updated_at',
        'suspension_end_date',
        'offense_count_display',
    ]
    date_hierarchy = 'date'
    
    fieldsets = (
        ('Employee Information', {
            'fields': ('employee', 'offense_count_display')
        }),
        ('Offense Details', {
            'fields': ('offense_type', 'severity_level', 'date', 'description')
        }),
        ('Penalty Details', {
            'fields': ('penalty_days', 'suspension_start_date', 'suspension_end_date'),
            'classes': ('collapse',),
        }),
        ('Additional Information', {
            'fields': ('notes', 'created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    def suspension_period_display(self, obj):
        """Display suspension period if applicable"""
        if obj.suspension_start_date and obj.suspension_end_date:
            return f"{obj.suspension_start_date} to {obj.suspension_end_date}"
        return '-'
    suspension_period_display.short_description = 'Suspension Period'
    
    def offense_count_display(self, obj):
        """Display total offense count for employee"""
        if obj.employee:
            count = Offense.get_offense_count(obj.employee)
            is_at_limit = Offense.is_at_limit(obj.employee)
            
            if is_at_limit:
                return format_html(
                    '<span style="color: red; font-weight: bold;">{} offenses (AT LIMIT)</span>',
                    count
                )
            elif count >= 2:
                return format_html(
                    '<span style="color: orange; font-weight: bold;">{} offenses (WARNING)</span>',
                    count
                )
            return f"{count} offense(s)"
        return '-'
    offense_count_display.short_description = 'Total Offenses'
    
    def save_model(self, request, obj, form, change):
        """Auto-set created_by if creating new offense"""
        if not change:  # Creating new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(OvertimeRequest)
class OvertimeRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "employee",
        "date",
        "time_start",
        "time_end",
        "approved",
        "approved_by",
        "approved_at",
    )
    list_filter = ("approved", "date")
    search_fields = (
        "employee__username",
        "employee__first_name",
        "employee__last_name",
        "reason",
    )
    date_hierarchy = "date"
    ordering = ("-date", "employee")
