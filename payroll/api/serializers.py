from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Mapping, Optional

from django.contrib.auth import get_user_model
from django.utils import timezone
from payroll.models import (
    AdditionalEarning,
    Holiday,
    OvertimeRequest,
    PayrollSettings,
    TimeEntry,
    WeeklyPayroll,
)
from rest_framework import serializers

User = get_user_model()


class MinimalUserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "full_name"]
        read_only_fields = fields

    def get_full_name(self, obj: User) -> str:
        # CustomUser defines get_full_name; if not, fallback to default formatting
        try:
            name = obj.get_full_name()
            return (
                name
                if name
                else f"{obj.first_name or ''} {obj.last_name or ''}".strip()
            )
        except Exception:
            return f"{obj.first_name or ''} {obj.last_name or ''}".strip()


class TimeEntrySerializer(serializers.ModelSerializer):
    effective_hours = serializers.SerializerMethodField(read_only=True)
    work_date = serializers.SerializerMethodField(read_only=True)
    employee_detail = MinimalUserSerializer(source="employee", read_only=True)

    employee = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), required=False, allow_null=False
    )

    class Meta:
        model = TimeEntry
        fields = [
            "id",
            "employee",
            "employee_detail",
            "clock_in",
            "clock_out",
            "unpaid_break_minutes",
            "source",
            "approved",
            "notes",
            "is_deleted",
            "created_at",
            "updated_at",
            "work_date",
            "effective_hours",
        ]
        read_only_fields = [
            "id",
            "is_deleted",
            "created_at",
            "updated_at",
            "work_date",
            "effective_hours",
        ]

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        clock_in = attrs.get("clock_in", getattr(self.instance, "clock_in", None))
        clock_out = attrs.get("clock_out", getattr(self.instance, "clock_out", None))
        unpaid_break_minutes = attrs.get(
            "unpaid_break_minutes", getattr(self.instance, "unpaid_break_minutes", 0)
        )

        if clock_in and clock_out and clock_out <= clock_in:
            raise serializers.ValidationError(
                {"clock_out": "clock_out must be after clock_in."}
            )

        if unpaid_break_minutes is not None and unpaid_break_minutes < 0:
            raise serializers.ValidationError(
                {"unpaid_break_minutes": "Must be non-negative."}
            )

        # Optional: ensure unpaid_break does not exceed total duration (soft check)
        if clock_in and clock_out and unpaid_break_minutes:
            total_minutes = (clock_out - clock_in).total_seconds() / 60.0
            if unpaid_break_minutes > max(total_minutes, 0):
                raise serializers.ValidationError(
                    {"unpaid_break_minutes": "Break minutes exceed worked duration."}
                )

        return attrs

    def create(self, validated_data: Dict[str, Any]) -> TimeEntry:
        # Default employee to current user if not provided
        if "employee" not in validated_data:
            request = self.context.get("request")
            if request and request.user and request.user.is_authenticated:
                validated_data["employee"] = request.user
        instance = super().create(validated_data)
        return instance

    def get_effective_hours(self, obj: TimeEntry) -> str:
        # Render with 4 decimal places as a string for precision and consistency
        try:
            return f"{obj.effective_hours}"
        except Exception:
            return "0.0"

    def get_work_date(self, obj: TimeEntry) -> str:
        try:
            dt = obj.clock_in
            local_dt = timezone.localtime(dt) if timezone.is_aware(dt) else dt
            return local_dt.date().isoformat()
        except Exception:
            return ""


class TimeEntryBulkCreateSerializer(serializers.Serializer):
    """
    Bulk create time entries with the same time window for multiple employees.
    Accepts:
    - employee_ids: list[int]
    - clock_in: datetime
    - clock_out: datetime
    - unpaid_break_minutes: int (>= 0, default 0)
    - source: TimeEntry.SOURCE_CHOICES (default "manual")
    - approved: bool (default True)
    - notes: str
    """

    employee_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )
    clock_in = serializers.DateTimeField()
    clock_out = serializers.DateTimeField()
    unpaid_break_minutes = serializers.IntegerField(
        required=False, min_value=0, default=0
    )
    source = serializers.ChoiceField(
        choices=[c[0] for c in TimeEntry.SOURCE_CHOICES],
        required=False,
        default="manual",
    )
    approved = serializers.BooleanField(required=False, default=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        clock_in = attrs.get("clock_in")
        clock_out = attrs.get("clock_out")

        unpaid_break_minutes = attrs.get("unpaid_break_minutes", 0)

        if clock_in and clock_out and clock_out <= clock_in:
            raise serializers.ValidationError(
                {"clock_out": "clock_out must be after clock_in."}
            )

        if unpaid_break_minutes is not None and unpaid_break_minutes < 0:
            raise serializers.ValidationError(
                {"unpaid_break_minutes": "Must be non-negative."}
            )

        if clock_in and clock_out and unpaid_break_minutes:
            total_minutes = (clock_out - clock_in).total_seconds() / 60.0
            if unpaid_break_minutes > max(total_minutes, 0):
                raise serializers.ValidationError(
                    {"unpaid_break_minutes": "Break minutes exceed worked duration."}
                )

        if not attrs.get("employee_ids"):
            raise serializers.ValidationError(
                {"employee_ids": "At least one employee id is required."}
            )

        return attrs


class AdditionalEarningSerializer(serializers.ModelSerializer):
    employee_detail = MinimalUserSerializer(source="employee", read_only=True)
    employee = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), required=True
    )

    class Meta:
        model = AdditionalEarning
        fields = [
            "id",
            "employee",
            "employee_detail",
            "earning_date",
            "category",
            "amount",
            "description",
            "reference",
            "approved",
            "is_deleted",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_deleted", "created_at", "updated_at"]


class AdditionalEarningBulkCreateSerializer(serializers.Serializer):
    """
    Bulk create additional earnings for multiple employees with the same values.
    Accepts:
    - employee_ids: list[int]
    - earning_date: date (YYYY-MM-DD)
    - category: AdditionalEarning.EARNING_TYPES keys
    - amount: Decimal(12,2)
    - description: str (optional)
    - reference: str (optional)
    - approved: bool (default True)
    """

    employee_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )
    earning_date = serializers.DateField()
    category = serializers.ChoiceField(
        choices=[c[0] for c in AdditionalEarning.EARNING_TYPES], required=True
    )
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    description = serializers.CharField(required=False, allow_blank=True)
    reference = serializers.CharField(required=False, allow_blank=True, max_length=100)
    approved = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        if not attrs.get("employee_ids"):
            raise serializers.ValidationError(
                {"employee_ids": "At least one employee id is required."}
            )
        if attrs.get("amount") is not None and attrs["amount"] < 0:
            raise serializers.ValidationError({"amount": "Must be non-negative."})
        return attrs


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
        if time_start and time_end and time_end <= time_start:
            raise serializers.ValidationError({"time_end": "time_end must be after time_start."})
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

class DeductionsField(serializers.Field):
    """
    Validates a mapping of {string: number} and normalizes to {string: Decimal('0.00')}.

    """

    default_error_messages = {
        "invalid_type": "Deductions must be an object mapping of name to amount.",
        "invalid_amount": "Deduction for '{name}' must be a number.",
        "negative_amount": "Deduction for '{name}' cannot be negative.",
    }

    def to_internal_value(self, data: Any) -> Dict[str, Decimal]:
        if data in (None, {}):
            return {}
        if not isinstance(data, Mapping):
            self.fail("invalid_type")
        result: Dict[str, Decimal] = {}
        for k, v in data.items():
            if not isinstance(k, str):
                k = str(k)
            try:
                amount = Decimal(str(v))
            except Exception:
                self.fail("invalid_amount", name=k)
            if amount < 0:
                self.fail("negative_amount", name=k)
            # Quantize to 2 decimals in serializer layer
            result[k] = amount.quantize(Decimal("0.01"))
        return result

    def to_representation(self, value: Any) -> Dict[str, float]:
        if not value:
            return {}
        # Convert Decimals to float for JSON friendliness
        rep: Dict[str, float] = {}
        try:
            for k, v in dict(value).items():
                rep[str(k)] = float(v)
        except Exception:
            # As a fallback, return the original mapping
            return value
        return rep



class WeeklyPayrollSerializer(serializers.ModelSerializer):

    employee_detail = MinimalUserSerializer(source="employee", read_only=True)
    employee_name = serializers.SerializerMethodField(read_only=True)
    week_end = serializers.SerializerMethodField(read_only=True)
    total_hours = serializers.SerializerMethodField(read_only=True)
    deductions = DeductionsField(required=False)
    employee = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), required=True
    )

    class Meta:
        model = WeeklyPayroll
        fields = [
            "id",
            "employee",
            "employee_detail",
            "employee_name",
            "week_start",
            "week_end",
            "hourly_rate",
            "overtime_threshold",
            "overtime_multiplier",
            "regular_hours",
            "overtime_hours",
            "night_diff_hours",
            "approved_ot_hours",
            "total_hours",
            "allowances",
            "gross_pay",
            "night_diff_pay",
            "approved_ot_pay",
            "holiday_pay_regular",
            "holiday_pay_special",
            "holiday_pay_total",
            "deductions",
            "total_deductions",
            "net_pay",
            "status",
            "notes",
            "is_deleted",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "regular_hours",
            "overtime_hours",
            "night_diff_hours",
            "approved_ot_hours",
            "total_hours",
            "gross_pay",
            "night_diff_pay",
            "approved_ot_pay",
            "holiday_pay_regular",
            "holiday_pay_special",
            "holiday_pay_total",
            "total_deductions",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        hourly_rate = attrs.get(
            "hourly_rate", getattr(self.instance, "hourly_rate", None)
        )
        overtime_threshold = attrs.get(
            "overtime_threshold", getattr(self.instance, "overtime_threshold", None)
        )
        overtime_multiplier = attrs.get(
            "overtime_multiplier", getattr(self.instance, "overtime_multiplier", None)
        )

        # Coerce to Decimal, ensure non-negative for sensible fields
        if hourly_rate is not None and Decimal(hourly_rate) < 0:
            raise serializers.ValidationError({"hourly_rate": "Must be non-negative."})
        if overtime_threshold is not None and Decimal(overtime_threshold) < 0:
            raise serializers.ValidationError(
                {"overtime_threshold": "Must be non-negative."}
            )
        if overtime_multiplier is not None and Decimal(overtime_multiplier) < 0:
            raise serializers.ValidationError(
                {"overtime_multiplier": "Must be non-negative."}
            )
        return attrs

    def get_employee_name(self, obj: WeeklyPayroll) -> str:
        try:
            # Prefer full_name from MinimalUserSerializer if available
            name = obj.employee.get_full_name()
            if name:
                return name
            # Fallback to first + last name
            return f"{obj.employee.first_name or ''} {obj.employee.last_name or ''}".strip()
        except Exception:
            return str(getattr(obj.employee, "username", ""))

    def get_week_end(self, obj: WeeklyPayroll) -> Optional[str]:
        try:
            return obj.week_end.isoformat()
        except Exception:
            return None

    def get_total_hours(self, obj: WeeklyPayroll) -> float:
        try:
            total = (obj.regular_hours or Decimal("0")) + (
                obj.overtime_hours or Decimal("0")
            )
            return float(total)
        except Exception:
            return 0.0




class PayrollSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollSettings
        fields = [
            "id",
            "shift_start",
            "shift_end",
            "grace_minutes",
            "auto_close_enabled",
            "holiday_day_hours",
            "holiday_regular_pct",
            "holiday_special_pct",
            "regular_holiday_no_work_pays",
            "special_holiday_no_work_pays",
            "overtime_multiplier",
            "night_diff_multiplier",
            "updated_at",
        ]
        read_only_fields = ["id", "updated_at"]


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ["id", "date", "name", "kind", "is_deleted"]
