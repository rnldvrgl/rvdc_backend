from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Mapping, Optional

from django.contrib.auth import get_user_model
from django.db import models
from payroll.models import (
    AdditionalEarning,
    EmployeeBenefitOverride,
    GovernmentBenefit,
    Holiday,
    ManualDeduction,
    PayrollSettings,
    PercentageDeduction,
    TaxBracket,
    WeeklyPayroll,
)
from rest_framework import serializers

User = get_user_model()


class MinimalUserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    daily_rate = serializers.SerializerMethodField()
    hourly_rate = serializers.SerializerMethodField()
    role = serializers.CharField()

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "full_name", "daily_rate", "hourly_rate", "role"]
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

    def get_daily_rate(self, obj: User) -> Optional[str]:
        """Return basic_salary as daily rate"""
        try:
            if obj.basic_salary:
                return str(obj.basic_salary.quantize(Decimal('0.01')))
            return None
        except Exception:
            return None

    def get_hourly_rate(self, obj: User) -> Optional[str]:
        """Calculate hourly rate from daily rate (basic_salary / 8 hours)"""
        try:
            if obj.basic_salary:
                hourly = obj.basic_salary / Decimal('8')
                return str(hourly.quantize(Decimal('0.01')))
            return None
        except Exception:
            return None

    def get_role(self, obj: User) -> str:
        try:
            return obj.role
        except Exception:
            return "N/A"


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
    week_end = serializers.DateField(required=False, allow_null=True)
    total_hours = serializers.SerializerMethodField(read_only=True)
    additional_earnings_details = serializers.SerializerMethodField(read_only=True)
    deductions = DeductionsField(required=False)
    employee = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), required=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

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
            "night_diff_hours",
            "approved_ot_hours",
            "total_hours",
            "allowances",
            "additional_earnings_total",
            "additional_earnings_details",
            "gross_pay",
            "night_diff_pay",
            "approved_ot_pay",
            "holiday_pay_regular",
            "holiday_pay_special",
            "holiday_pay_total",
            "deductions",
            "deduction_metadata",
            "total_deductions",
            "net_pay",
            "status",
            "status_display",
            "notes",
            "is_deleted",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "regular_hours",
            "night_diff_hours",
            "approved_ot_hours",
            "total_hours",
            "additional_earnings_total",
            "gross_pay",
            "night_diff_pay",
            "approved_ot_pay",
            "holiday_pay_regular",
            "holiday_pay_special",
            "holiday_pay_total",
            "total_deductions",
            "status_display",
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

    def get_total_hours(self, obj: WeeklyPayroll) -> float:
        try:
            # Total hours = regular hours + approved OT hours
            total = (obj.regular_hours or Decimal("0")) + (
                obj.approved_ot_hours or Decimal("0")
            )
            return float(total)
        except Exception:
            return 0.0

    def get_additional_earnings_details(self, obj: WeeklyPayroll) -> list:
        """Return list of additional earnings for this payroll period with their details."""
        try:
            earnings = obj.employee.additional_earnings.filter(
                is_deleted=False,
                approved=True,
                earning_date__gte=obj.week_start,
                earning_date__lte=obj.week_end,
            ).order_by('earning_date')
            
            return [
                {
                    'id': earning.id,
                    'date': earning.earning_date.isoformat(),
                    'category': earning.category,
                    'amount': str(earning.amount),
                    'description': earning.description or '',
                    'reference': earning.reference or '',
                }
                for earning in earnings
            ]
        except Exception:
            return []




class PayrollSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollSettings
        fields = [
            "id",
            "shift_start",
            "shift_end",
            "grace_minutes",
            "clock_out_tolerance_minutes",
            "auto_close_enabled",
            "holiday_day_hours",
            "holiday_regular_pct",
            "holiday_special_pct",
            "regular_holiday_no_work_pays",
            "special_holiday_no_work_pays",
            "overtime_multiplier",
            "night_diff_multiplier",
            "payroll_cutoff_day",
            "cash_ban_contribution_amount",
            "cash_ban_enabled",
            "updated_at",
        ]
        read_only_fields = ["id", "updated_at"]


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ["id", "date", "name", "kind", "is_deleted"]


class ManualDeductionSerializer(serializers.ModelSerializer):
    employee_detail = MinimalUserSerializer(source="employee", read_only=True)
    created_by_detail = MinimalUserSerializer(source="created_by", read_only=True)
    deduction_type_display = serializers.CharField(source="get_deduction_type_display", read_only=True)

    class Meta:
        model = ManualDeduction
        fields = [
            "id",
            "name",
            "description",
            "deduction_type",
            "deduction_type_display",
            "employee",
            "employee_detail",
            "amount",
            "effective_date",
            "end_date",
            "is_active",
            "applied_date",
            "is_deleted",
            "created_by",
            "created_by_detail",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at", "applied_date"]

    def validate(self, attrs):
        # Validate per_employee deductions have employee
        deduction_type = attrs.get("deduction_type")
        employee = attrs.get("employee")

        if deduction_type == "per_employee" and not employee:
            raise serializers.ValidationError({
                "employee": "Per employee deductions must have an employee assigned."
            })

        if deduction_type in ["recurring_all", "onetime_all"] and employee:
            raise serializers.ValidationError({
                "employee": "Recurring/One-time for all deductions cannot have a specific employee."
            })

        # Auto-set effective_date to today for one-time per_employee deductions if not provided
        effective_date = attrs.get("effective_date")
        if deduction_type == "per_employee" and not effective_date:
            # One-time deduction - set to today so it applies to next payroll
            from django.utils import timezone
            attrs["effective_date"] = timezone.now().date()

        # Validate amount is positive
        amount = attrs.get("amount")
        if amount is not None and amount <= 0:
            raise serializers.ValidationError({
                "amount": "Amount must be greater than zero."
            })

        # Validate dates
        effective_date = attrs.get("effective_date")
        end_date = attrs.get("end_date")

        if end_date and effective_date and end_date < effective_date:
            raise serializers.ValidationError({
                "end_date": "End date must be on or after the effective date."
            })

        return attrs

class EmployeeBenefitOverrideSerializer(serializers.ModelSerializer):
    """Serializer for EmployeeBenefitOverride model."""
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)
    benefit_type_display = serializers.CharField(source='get_benefit_type_display', read_only=True)
    
    class Meta:
        model = EmployeeBenefitOverride
        fields = [
            'id',
            'employee',
            'employee_name',
            'benefit_type',
            'benefit_type_display',
            'employee_share_amount',
            'employer_share_amount',
            'effective_start',
            'effective_end',
            'is_active',
            'notes',
            'created_at',
            'updated_at',
            'created_by',
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'employee_name', 'benefit_type_display']
    
    def validate(self, attrs):
        """Validate benefit override data."""
        employee = attrs.get('employee')
        benefit_type = attrs.get('benefit_type')
        effective_start = attrs.get('effective_start')
        effective_end = attrs.get('effective_end')
        is_active = attrs.get('is_active', True)
        
        # Check for duplicate active overrides for same employee + benefit type
        if is_active and employee and benefit_type:
            existing_query = EmployeeBenefitOverride.objects.filter(
                employee=employee,
                benefit_type=benefit_type,
                is_active=True,
            )
            
            # Exclude current instance when updating
            if self.instance:
                existing_query = existing_query.exclude(pk=self.instance.pk)
            
            # Check for overlapping date ranges
            if existing_query.exists():
                overlapping = existing_query.filter(
                    models.Q(effective_end__isnull=True) | models.Q(effective_end__gte=effective_start)
                )
                
                if effective_end:
                    overlapping = overlapping.filter(effective_start__lte=effective_end)
                
                if overlapping.exists():
                    raise serializers.ValidationError({
                        'benefit_type': f'An active override for this benefit type already exists for this employee with overlapping dates.'
                    })
        
        # Validate date range
        if effective_end and effective_start and effective_end < effective_start:
            raise serializers.ValidationError({
                'effective_end': 'End date must be on or after start date.'
            })
        
        # Validate amounts are positive
        employee_share = attrs.get('employee_share_amount')
        if employee_share and employee_share < 0:
            raise serializers.ValidationError({
                'employee_share_amount': 'Amount must be positive.'
            })
        
        employer_share = attrs.get('employer_share_amount')
        if employer_share and employer_share < 0:
            raise serializers.ValidationError({
                'employer_share_amount': 'Amount must be positive.'
            })
        
        return attrs

class TaxBracketSerializer(serializers.ModelSerializer):
    created_by_detail = MinimalUserSerializer(source="created_by", read_only=True)

    class Meta:
        model = TaxBracket
        fields = [
            "id",
            "bracket_type",
            "min_income",
            "max_income",
            "base_tax",
            "rate",
            "effective_start",
            "effective_end",
            "is_active",
            "created_by",
            "created_by_detail",
            "created_at",
        ]
        read_only_fields = ["created_at", "created_by"]

    def validate(self, attrs):
        min_income = attrs.get("min_income")
        max_income = attrs.get("max_income")

        if max_income and min_income and max_income < min_income:
            raise serializers.ValidationError({
                "max_income": "Maximum income must be greater than or equal to minimum income."
            })

        effective_start = attrs.get("effective_start")
        effective_end = attrs.get("effective_end")

        if effective_end and effective_start and effective_end < effective_start:
            raise serializers.ValidationError({
                "effective_end": "End date must be on or after the start date."
            })

        return attrs


class PercentageDeductionSerializer(serializers.ModelSerializer):
    created_by_detail = MinimalUserSerializer(source="created_by", read_only=True)
    deduction_type_display = serializers.CharField(source="get_deduction_type_display", read_only=True)

    class Meta:
        model = PercentageDeduction
        fields = [
            "id",
            "name",
            "deduction_type",
            "deduction_type_display",
            "rate",
            "description",
            "effective_start",
            "effective_end",
            "is_active",
            "created_by",
            "created_by_detail",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at", "created_by"]

    def validate(self, attrs):
        rate = attrs.get("rate")
        if rate is not None and (rate < 0 or rate > 1):
            raise serializers.ValidationError({
                "rate": "Rate must be between 0 and 1 (e.g., 0.05 for 5%)."
            })

        effective_start = attrs.get("effective_start")
        effective_end = attrs.get("effective_end")

        if effective_end and effective_start and effective_end < effective_start:
            raise serializers.ValidationError({
                "effective_end": "End date must be on or after the start date."
            })

        return attrs

class GovernmentBenefitSerializer(serializers.ModelSerializer):
    """Serializer for GovernmentBenefit model."""

    class Meta:
        model = GovernmentBenefit
        fields = [
            'id',
            'benefit_type',
            'name',
            'calculation_method',
            'period_type',
            'employee_share_amount',
            'employee_share_rate',
            'employer_share_amount',
            'employer_share_rate',
            'effective_start',
            'effective_end',
            'is_active',
            'description',
            'created_at',
            'updated_at',
            'created_by',
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by']

    def validate(self, attrs):
        """Validate government benefit data."""
        calculation_method = attrs.get('calculation_method')
        benefit_type = attrs.get('benefit_type')

        # Validate calculation method matches benefit type
        if benefit_type == 'bir_tax' and calculation_method != 'progressive_tax':
            raise serializers.ValidationError({
                'calculation_method': 'BIR tax must use progressive_tax calculation method.'
            })

        # Ensure required fields are present for each calculation method
        if calculation_method == 'fixed':
            if not attrs.get('employee_share_amount'):
                raise serializers.ValidationError({
                    'employee_share_amount': 'Required for fixed calculation method.'
                })
        elif calculation_method == 'percentage':
            if not attrs.get('employee_share_rate'):
                raise serializers.ValidationError({
                    'employee_share_rate': 'Required for percentage calculation method.'
                })
        # Progressive tax uses TaxBracket.compute_tax() method, no additional field required

        # Validate date range
        effective_start = attrs.get('effective_start')
        effective_end = attrs.get('effective_end')
        if effective_end and effective_start and effective_end < effective_start:
            raise serializers.ValidationError({
                'effective_end': 'End date must be on or after start date.'
            })

        # Validate rates are between 0 and 1
        employee_rate = attrs.get('employee_share_rate')
        employer_rate = attrs.get('employer_share_rate')

        if employee_rate is not None and (employee_rate < 0 or employee_rate > 1):
            raise serializers.ValidationError({
                'employee_share_rate': 'Rate must be between 0 and 1 (e.g., 0.05 for 5%).'
            })

        if employer_rate is not None and (employer_rate < 0 or employer_rate > 1):
            raise serializers.ValidationError({
                'employer_share_rate': 'Rate must be between 0 and 1 (e.g., 0.05 for 5%).'
            })

        return attrs
