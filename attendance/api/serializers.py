from rest_framework import serializers
from attendance.models import DailyAttendance, LeaveBalance, LeaveRequest
from users.api.serializers import UserSerializer


class DailyAttendanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True)
    attendance_type_display = serializers.CharField(source='get_attendance_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = DailyAttendance
        fields = [
            'id',
            'employee',
            'employee_name',
            'date',
            'clock_in',
            'clock_out',
            'attendance_type',
            'attendance_type_display',
            'consecutive_absences',
            'is_awol',
            'total_hours',
            'break_hours',
            'paid_hours',
            'is_late',
            'late_minutes',
            'auto_closed',
            'auto_close_warning_count',
            'late_penalty_amount',
            'missing_uniform_shirt',
            'missing_uniform_pants',
            'missing_uniform_shoes',
            'uniform_penalty_amount',
            'status',
            'status_display',
            'approved_by',
            'approved_by_name',
            'approved_at',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'total_hours',
            'break_hours',
            'paid_hours',
            'attendance_type',
            'consecutive_absences',
            'is_awol',
            'is_late',
            'auto_closed',
            'auto_close_warning_count',
            'late_minutes',
            'late_penalty_amount',
            'uniform_penalty_amount',
            'approved_at',
            'created_at',
            'updated_at',
        ]


class ClockInSerializer(serializers.Serializer):
    """Serializer for clocking in an employee."""
    employee_id = serializers.IntegerField()
    date = serializers.DateField()
    clock_in = serializers.DateTimeField()
    notes = serializers.CharField(required=False, allow_blank=True)


class ClockOutSerializer(serializers.Serializer):
    """Serializer for clocking out an employee."""
    attendance_id = serializers.IntegerField()
    clock_out = serializers.DateTimeField()
    notes = serializers.CharField(required=False, allow_blank=True)


class ApproveAttendanceSerializer(serializers.Serializer):
    """Serializer for approving attendance records."""
    attendance_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False
    )


class RejectAttendanceSerializer(serializers.Serializer):
    """Serializer for rejecting attendance records."""
    attendance_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False
    )
    reason = serializers.CharField(required=False, allow_blank=True)


class LeaveBalanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)
    sick_leave_remaining = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    emergency_leave_remaining = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    
    class Meta:
        model = LeaveBalance
        fields = [
            'id',
            'employee',
            'employee_name',
            'year',
            'sick_leave_total',
            'sick_leave_used',
            'sick_leave_remaining',
            'emergency_leave_total',
            'emergency_leave_used',
            'emergency_leave_remaining',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True)
    leave_type_display = serializers.CharField(source='get_leave_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    days_count = serializers.DecimalField(max_digits=3, decimal_places=1, read_only=True)
    
    class Meta:
        model = LeaveRequest
        fields = [
            'id',
            'employee',
            'employee_name',
            'leave_type',
            'leave_type_display',
            'date',
            'is_half_day',
            'days_count',
            'reason',
            'status',
            'status_display',
            'approved_by',
            'approved_by_name',
            'approved_at',
            'rejection_reason',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'status',
            'approved_by',
            'approved_at',
            'created_at',
            'updated_at',
        ]


class ApproveLeaveSerializer(serializers.Serializer):
    """Serializer for approving leave requests."""
    leave_request_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False
    )


class RejectLeaveSerializer(serializers.Serializer):
    """Serializer for rejecting leave requests."""
    leave_request_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False
    )
    reason = serializers.CharField(required=False, allow_blank=True)
