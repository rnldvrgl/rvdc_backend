from typing import Any, Dict

from django.utils import timezone
from rest_framework import serializers
from users.models import CustomUser as User

from attendance.models import (
    DailyAttendance,
    HalfDaySchedule,
    LeaveBalance,
    LeaveRequest,
    Offense,
    OvertimeRequest,
    WorkRequest,
)


class MinimalUserSerializer(serializers.ModelSerializer):
    """Minimal user details for nested serialization"""
    full_name = serializers.CharField(source='get_full_name', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'full_name']
        read_only_fields = fields


class DailyAttendanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True)
    attendance_type_display = serializers.CharField(source='get_attendance_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        instance = getattr(self, 'instance', None)

        attendance_type = attrs.get(
            'attendance_type',
            instance.attendance_type if instance else 'PENDING',
        )
        clock_in = attrs.get('clock_in', instance.clock_in if instance else None)
        clock_out = attrs.get('clock_out', instance.clock_out if instance else None)

        if clock_in and clock_out and clock_out <= clock_in:
            raise serializers.ValidationError({
                'clock_out': 'Clock-out time must be after clock-in time.'
            })

        if attendance_type in ['LEAVE', 'ABSENT', 'SHOP_CLOSED'] and (clock_in or clock_out):
            raise serializers.ValidationError(
                'LEAVE, ABSENT, and SHOP_CLOSED attendance types cannot have clock-in or clock-out values.'
            )

        return attrs

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
    shift_period_display = serializers.CharField(source='get_shift_period_display', read_only=True)
    days_count = serializers.DecimalField(max_digits=5, decimal_places=1, read_only=True)

    class Meta:
        model = LeaveRequest
        fields = [
            'id',
            'employee',
            'employee_name',
            'leave_type',
            'leave_type_display',
            'start_date',
            'end_date',
            'date',
            'is_half_day',
            'shift_period',
            'shift_period_display',
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
            'date',
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


class ValidateLeaveBalanceSerializer(serializers.Serializer):
    """Serializer for validating leave balance before submission."""
    employee = serializers.IntegerField(required=False, help_text='Employee ID (optional for admin, auto-set for others)')
    leave_type = serializers.ChoiceField(choices=['SICK', 'EMERGENCY', 'SPECIAL'])
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    is_half_day = serializers.BooleanField(default=False)

    def validate(self, data):
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        is_half_day = data.get('is_half_day', False)

        if end_date < start_date:
            raise serializers.ValidationError({'end_date': 'End date must be on or after start date.'})

        delta_days = (end_date - start_date).days + 1

        if is_half_day and delta_days > 1:
            raise serializers.ValidationError({'is_half_day': 'Half-day leave is only allowed for single-day requests.'})

        return data


class OffenseSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)
    employee_id_number = serializers.CharField(source='employee.id_number', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    offense_type_display = serializers.CharField(source='get_offense_type_display', read_only=True)
    severity_level_display = serializers.CharField(source='get_severity_level_display', read_only=True)
    offense_count = serializers.SerializerMethodField()

    class Meta:
        model = Offense
        fields = [
            'id',
            'employee',
            'employee_name',
            'employee_id_number',
            'offense_type',
            'offense_type_display',
            'severity_level',
            'severity_level_display',
            'date',
            'description',
            'penalty_days',
            'suspension_start_date',
            'suspension_end_date',
            'created_by',
            'created_by_name',
            'created_at',
            'updated_at',
            'notes',
            'offense_count',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'suspension_end_date', 'severity_level']

    def get_offense_count(self, obj):
        """Get total offense count for this employee"""
        return Offense.get_offense_count(obj.employee)

    def create(self, validated_data):
        """Auto-calculate severity level based on existing offense count"""
        employee = validated_data['employee']
        offense_count = Offense.get_offense_count(employee)

        # Determine severity based on offense count
        if offense_count == 0:
            validated_data['severity_level'] = 'WARNING'
        elif offense_count == 1:
            validated_data['severity_level'] = 'SUSPENSION'
        else:
            validated_data['severity_level'] = 'TERMINATION'

        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Prevent changing severity_level and offense_type when editing"""
        # Remove severity_level if present in validated_data
        validated_data.pop('severity_level', None)
        # Keep the original offense_type, don't allow changes
        validated_data.pop('offense_type', None)
        return super().update(instance, validated_data)


class OffenseStatisticsSerializer(serializers.Serializer):
    """Serializer for offense statistics"""
    employee_id = serializers.IntegerField()
    employee_name = serializers.CharField()
    total_offenses = serializers.IntegerField()
    awol_count = serializers.IntegerField()
    late_count = serializers.IntegerField()
    curfew_count = serializers.IntegerField()
    other_count = serializers.IntegerField()
    warning_count = serializers.IntegerField()
    suspension_count = serializers.IntegerField()
    termination_count = serializers.IntegerField()
    is_at_limit = serializers.BooleanField()
    last_offense_date = serializers.DateField(allow_null=True)


class OvertimeRequestSerializer(serializers.ModelSerializer):
    employee_detail = MinimalUserSerializer(source="employee", read_only=True)
    employee = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=True)

    class Meta:
        model = OvertimeRequest
        fields = [
            "id",
            "employee",
            "employee_detail",
            "date",
            "time_start",
            "time_end",
            "reason",
            "approved",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "approved",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        time_start = attrs.get("time_start", getattr(self.instance, "time_start", None))
        time_end = attrs.get("time_end", getattr(self.instance, "time_end", None))
        date = attrs.get("date", getattr(self.instance, "date", None))

        # Validate time_end is after time_start
        if time_start and time_end and time_end <= time_start:
            raise serializers.ValidationError({"time_end": "time_end must be after time_start."})

        # Validate date field matches time_start date
        if time_start and date:
            time_start_date = time_start.date() if hasattr(time_start, 'date') else time_start
            if date != time_start_date:
                raise serializers.ValidationError({
                    "date": f"Date field ({date}) must match the date of time_start ({time_start_date})."
                })

        return attrs


class OvertimeRequestApproveSerializer(serializers.ModelSerializer):
    approved = serializers.BooleanField(required=True)
    approved_by = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)

    class Meta:
        model = OvertimeRequest
        fields = ["id", "approved", "approved_by", "approved_at"]
        read_only_fields = ["id", "approved_at"]

    def update(self, instance: OvertimeRequest, validated_data: Dict[str, Any]) -> OvertimeRequest:
        approved = validated_data.get("approved", instance.approved)
        instance.approved = approved
        # Set approver from context request user if not explicitly provided
        request = self.context.get("request")
        approver = validated_data.get("approved_by")
        if not approver and request and getattr(request, "user", None) and request.user.is_authenticated:
            approver = request.user
        instance.approved_by = approver
        # Set timestamp when approved toggled to True
        if approved and not instance.approved_at:
            instance.approved_at = timezone.now()
        instance.save(update_fields=["approved", "approved_by", "approved_at", "updated_at"])
        return instance


class HalfDayScheduleSerializer(serializers.ModelSerializer):
    """Serializer for HalfDaySchedule model."""
    
    created_by_name = serializers.SerializerMethodField()
    schedule_type_display = serializers.CharField(source='get_schedule_type_display', read_only=True)
    
    class Meta:
        model = HalfDaySchedule
        fields = [
            'id',
            'date',
            'schedule_type',
            'schedule_type_display',
            'reason',
            'created_by',
            'created_by_name',
            'created_at',
            'updated_at',
            'is_deleted',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'created_by_name', 'schedule_type_display']
    
    def get_created_by_name(self, obj):
        """Get full name of the user who created the schedule."""
        if obj.created_by:
            return obj.created_by.get_full_name()
        return None
    
    def create(self, validated_data):
        """Set created_by to current user."""
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class WorkRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.get_full_name', read_only=True, default=None)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = WorkRequest
        fields = [
            'id',
            'employee',
            'employee_name',
            'date',
            'reason',
            'status',
            'status_display',
            'reviewed_by',
            'reviewed_by_name',
            'reviewed_at',
            'decline_reason',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'employee', 'employee_name', 'status', 'status_display',
            'reviewed_by', 'reviewed_by_name', 'reviewed_at',
            'decline_reason', 'created_at', 'updated_at',
        ]
