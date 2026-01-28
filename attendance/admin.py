from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import DailyAttendance, LeaveBalance, LeaveRequest


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
    
    actions = [
        'approve_attendance',
        'reject_attendance',
        'reset_auto_close_warnings',
        'clear_awol_flag',
    ]
    
    def approve_attendance(self, request, queryset):
        count = 0
        for attendance in queryset:
            if attendance.status == 'PENDING':
                attendance.approve(request.user)
                count += 1
        
        self.message_user(request, f'{count} attendance record(s) approved.')
    approve_attendance.short_description = 'Approve selected attendance'
    
    def reject_attendance(self, request, queryset):
        count = 0
        for attendance in queryset:
            if attendance.status == 'PENDING':
                attendance.reject(request.user, reason='Rejected via admin')
                count += 1
        
        self.message_user(request, f'{count} attendance record(s) rejected.')
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