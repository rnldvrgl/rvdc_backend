from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional

from analytics import models
from django.db import IntegrityError, transaction
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from payroll.api.filters import (
    AdditionalEarningFilter,
    HolidayFilter,
    WeeklyPayrollFilter,
)
from payroll.api.serializers import (
    AdditionalEarningSerializer,
    EmployeeBenefitOverrideSerializer,
    GovernmentBenefitSerializer,
    HolidaySerializer,
    ManualDeductionSerializer,
    PayrollSettingsSerializer,
    PercentageDeductionSerializer,
    TaxBracketSerializer,
    WeeklyPayrollSerializer,
)
from payroll.models import (
    AdditionalEarning,
    Holiday,
    ManualDeduction,
    PayrollSettings,
    PercentageDeduction,
    TaxBracket,
    WeeklyPayroll,
)
from rest_framework import filters, generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView
from utils.filters.options import (
    get_user_options,
)
from utils.filters.role_filters import get_role_based_filter_response
from utils.query import filter_by_date_range
from utils.soft_delete import SoftDeleteViewSetMixin

# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------

def _apply_pending_cash_advance_movements(payroll: WeeklyPayroll):
    """
    Apply pending cash advance movements linked to this payroll.
    Called when payroll is approved.
    """
    try:
        from users.models import CashAdvanceMovement
        
        pending_movements = CashAdvanceMovement.objects.filter(
            reference=f'payroll-{payroll.id}',
            is_pending=True,
            is_deleted=False,
        )
        
        for movement in pending_movements:
            movement.apply_to_balance()
    except Exception as e:
        print(f"Error applying pending cash advance movements for payroll {payroll.id}: {e}")


def _add_cash_ban_contribution(payroll: WeeklyPayroll):
    """
    Add cash ban contribution to employee's balance when payroll is approved.
    Creates a CashAdvanceMovement CREDIT record for audit trail.
    """
    try:
        from users.models import CashAdvanceMovement

        settings = PayrollSettings.objects.first()
        if not settings or not settings.cash_ban_enabled:
            return
        
        employee = payroll.employee
        
        # Check if employee has cash ban enabled
        if not employee.has_cash_ban:
            return
        
        contribution_amount = settings.cash_ban_contribution_amount
        if contribution_amount <= 0:
            return
        
        # Create a CREDIT movement (this also updates the employee's balance)
        CashAdvanceMovement.objects.create(
            employee=employee,
            movement_type=CashAdvanceMovement.MovementType.CREDIT,
            amount=contribution_amount,
            date=payroll.week_start,
            description=f'Cash ban contribution from payroll ({payroll.week_start} to {payroll.week_end})',
            reference=f'payroll-{payroll.id}',
        )
    except Exception as e:
        # Log error but don't fail payroll approval
        print(f"Error adding cash ban contribution for payroll {payroll.id}: {e}")

# ------------------------------------------------------------------------------
# Additional Earnings
# ------------------------------------------------------------------------------


class AdditionalEarningListCreateView(generics.ListCreateAPIView):
    serializer_class = AdditionalEarningSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = AdditionalEarning.objects.filter(is_deleted=False).select_related(
        "employee"
    )


    filter_backends = [

        DjangoFilterBackend,

        filters.SearchFilter,

        filters.OrderingFilter,

    ]



    filterset_class = AdditionalEarningFilter


    search_fields = [
        "description",
        "reference",
        "employee__username",
        "employee__first_name",
        "employee__last_name",
    ]
    ordering_fields = "__all__"


    def get_queryset(self):
        return filter_by_date_range(
            self.request, super().get_queryset(), "earning_date"
        )


    def perform_destroy(self, instance: AdditionalEarning) -> None:
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted"])


class AdditionalEarningDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AdditionalEarningSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = AdditionalEarning.objects.filter(is_deleted=False).select_related(
        "employee"
    )

    def get_object(self) -> AdditionalEarning:
        try:
            obj = super().get_object()
            if obj.is_deleted:
                raise NotFound(detail="Additional earning not found.")
            return obj
        except AdditionalEarning.DoesNotExist:
            raise NotFound(detail="Additional earning not found.")

    def perform_destroy(self, instance: AdditionalEarning) -> None:
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted"])


# ------------------------------------------------------------------------------
# Weekly Payrolls
# ------------------------------------------------------------------------------



class WeeklyPayrollGenerateView(APIView):
    """
    POST to generate a new payroll for an employee for a specific week.
    Request body:
    - employee_id: int (required)
    - week_start: string YYYY-MM-DD (required)
    - week_end: string YYYY-MM-DD (required)
    - notes: string (optional)
    - include_unapproved: bool (optional, default False)
    """
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, *args, **kwargs):
        from datetime import datetime, timedelta

        from django.contrib.auth import get_user_model

        User = get_user_model()

        # Validate input
        employee_id = request.data.get('employee_id')
        notes = request.data.get('notes', '')
        include_unapproved = request.data.get('include_unapproved', False)

        if not employee_id:
            return Response(
                {'employee_id': ['This field is required.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get payroll settings for cutoff day
        try:
            settings_obj = PayrollSettings.objects.first()
            if not settings_obj:
                settings_obj = PayrollSettings.objects.create()
        except Exception:
            settings_obj = None

        cutoff_day = getattr(settings_obj, 'payroll_cutoff_day', 4)  # Default Friday

        # Use provided dates or auto-calculate
        week_start_str = request.data.get('week_start')
        week_end_str = request.data.get('week_end')

        if week_start_str and week_end_str:
            try:
                week_start = datetime.strptime(str(week_start_str), '%Y-%m-%d').date()
                week_end = datetime.strptime(str(week_end_str), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                return Response(
                    {'detail': 'Invalid date format. Use YYYY-MM-DD.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if week_end < week_start:
                return Response(
                    {'detail': 'week_end must be on or after week_start.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        elif week_start_str:
            try:
                week_start = datetime.strptime(str(week_start_str), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                return Response(
                    {'detail': 'Invalid date format. Use YYYY-MM-DD.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            week_end = week_start + timedelta(days=6)
        else:
            # Auto-calculate from cutoff day
            today = datetime.now().date()
            current_weekday = today.weekday()
            days_since_cutoff = (current_weekday - cutoff_day) % 7
            if days_since_cutoff == 0 and datetime.now().time().hour < 23:
                days_since_cutoff = 7
            last_cutoff = today - timedelta(days=days_since_cutoff)
            week_start = last_cutoff - timedelta(days=6)
            week_end = week_start + timedelta(days=6)

        # Get employee
        try:
            employee = User.objects.get(id=employee_id, is_deleted=False, is_active=True)
        except User.DoesNotExist:
            return Response(
                {'employee_id': ['Employee not found or account is inactive.']},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if employee is included in payroll
        if not employee.include_in_payroll:
            return Response(
                {'employee_id': ['This employee is not included in payroll generation.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if employee has basic_salary
        if not employee.basic_salary or employee.basic_salary <= 0:
            return Response(
                {'employee_id': ['Employee does not have a valid basic salary configured.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Calculate hourly rate from basic_salary (daily rate) / 8 hours per day
        hourly_rate = Decimal(employee.basic_salary) / Decimal('8.00')

        # Check if payroll already exists
        existing = WeeklyPayroll.objects.filter(
            employee=employee,
            week_start=week_start,
            is_deleted=False
        ).first()

        if existing:
            return Response(
                {'detail': f'Payroll already exists for this employee and week (ID: {existing.id}).'},
                status=status.HTTP_409_CONFLICT
            )

        overtime_multiplier = Decimal(getattr(settings_obj, 'overtime_multiplier', Decimal('1.50')) or '1.50')

        # Create payroll
        try:
            with transaction.atomic():
                payroll = WeeklyPayroll.objects.create(
                    employee=employee,
                    week_start=week_start,
                    week_end=week_end,
                    hourly_rate=hourly_rate,
                    overtime_threshold=Decimal('40.00'),
                    overtime_multiplier=overtime_multiplier,
                    notes=notes,
                    status='draft'
                )

                # Compute from daily attendance
                payroll.compute_from_daily_attendance(
                    include_unapproved=include_unapproved
                )

                payroll.save(
                    update_fields=[
                        'week_end',
                        'regular_hours',
                        'night_diff_hours',
                        'approved_ot_hours',
                        'allowances',
                        'additional_earnings_total',
                        'gross_pay',
                        'night_diff_pay',
                        'approved_ot_pay',
                        'holiday_pay_regular',
                        'holiday_pay_special',
                        'holiday_pay_total',
                        'deductions',
                        'deduction_metadata',
                        'total_deductions',
                        'net_pay',
                        'updated_at',
                    ]
                )

                # Create structured deduction records
                payroll.create_deduction_records()
        except IntegrityError:
            # Race condition: payroll was created between check and creation
            existing = WeeklyPayroll.objects.filter(
                employee=employee,
                week_start=week_start,
                is_deleted=False
            ).first()
            return Response(
                {
                    'detail': f'Payroll already exists for this employee and week (ID: {existing.id if existing else "unknown"}).',
                    'error_code': 'PAYROLL_ALREADY_EXISTS',
                    'existing_payroll_id': existing.id if existing else None
                },
                status=status.HTTP_409_CONFLICT
            )

        serializer = WeeklyPayrollSerializer(payroll)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class WeeklyPayrollPreviewView(APIView):
    """
    POST to preview payroll calculation without saving.
    Request body:
    - employee_id: int (required)
    - include_unapproved: bool (optional, default False)

    Week is auto-calculated based on PayrollSettings.payroll_cutoff_day.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        from datetime import datetime, timedelta

        from attendance.models import DailyAttendance
        from django.contrib.auth import get_user_model

        User = get_user_model()

        # Validate input
        employee_id = request.data.get('employee_id')
        include_unapproved = request.data.get('include_unapproved', False)

        if not employee_id:
            return Response(
                {'employee_id': ['This field is required.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get payroll settings for cutoff day
        try:
            settings_obj = PayrollSettings.objects.first()
            if not settings_obj:
                settings_obj = PayrollSettings.objects.create()
        except Exception:
            settings_obj = None

        cutoff_day = getattr(settings_obj, 'payroll_cutoff_day', 4)  # Default Friday

        # Calculate most recent completed week
        today = datetime.now().date()
        current_weekday = today.weekday()

        days_since_cutoff = (current_weekday - cutoff_day) % 7
        if days_since_cutoff == 0 and datetime.now().time().hour < 23:
            days_since_cutoff = 7

        last_cutoff = today - timedelta(days=days_since_cutoff)
        week_start = last_cutoff - timedelta(days=6)
        week_end = last_cutoff  # Inclusive end date

        # Get employee
        try:
            employee = User.objects.get(id=employee_id, is_deleted=False, is_active=True)
        except User.DoesNotExist:
            return Response(
                {'employee_id': ['Employee not found or account is inactive.']},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if employee has basic_salary
        if not employee.basic_salary or employee.basic_salary <= 0:
            return Response(
                {'employee_id': ['Employee does not have a valid basic salary configured.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Calculate hourly rate from daily rate / 8 hours per day
        hourly_rate = Decimal(employee.basic_salary) / Decimal('8.00')

        # Get attendance records
        attendance_qs = DailyAttendance.objects.filter(
            employee=employee,
            date__gte=week_start,
            date__lte=week_end,
            is_deleted=False,
        )

        if not include_unapproved:
            attendance_qs = attendance_qs.filter(status='APPROVED')

        # Calculate hours and penalties
        regular_hours_total = Decimal('0.00')
        per_day_overtime_total = Decimal('0.00')
        late_penalties_total = Decimal('0.00')
        attendance_breakdown = []

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
            per_day_overtime_total += daily_overtime

            if attendance.late_penalty_amount:
                late_penalties_total += Decimal(attendance.late_penalty_amount)

            attendance_breakdown.append({
                'date': attendance.date,
                'attendance_type': attendance.attendance_type,
                'paid_hours': float(paid_hours),
                'regular_hours': float(daily_regular),
                'per_day_overtime': float(daily_overtime),
                'late_penalty': float(attendance.late_penalty_amount or 0),
            })

        overtime_multiplier = Decimal(getattr(settings_obj, 'overtime_multiplier', Decimal('1.50')) or '1.50')

        # Calculate pay (legacy per-day overtime calculation for preview)
        base_pay = (regular_hours_total * hourly_rate) + (per_day_overtime_total * hourly_rate * overtime_multiplier)

        # Get additional earnings
        add_qs = employee.additional_earnings.filter(
            is_deleted=False,
            earning_date__gte=week_start,
            earning_date__lte=week_end,
        )
        if not include_unapproved:
            add_qs = add_qs.filter(approved=True)

        additional_total = sum((Decimal(e.amount) for e in add_qs), Decimal('0'))

        # Calculate gross and net
        gross_pay = base_pay + additional_total

        # Basic deductions (late penalties)
        deductions_map = {}
        if late_penalties_total > 0:
            deductions_map['late_penalty'] = float(late_penalties_total)

        total_deductions = late_penalties_total
        net_pay = gross_pay - total_deductions

        preview_data = {
            'employee': {
                'id': employee.id,
                'full_name': employee.get_full_name(),
                'basic_salary': float(employee.basic_salary),
            },
            'week_start': week_start,
            'week_end': week_end,
            'hourly_rate': float(hourly_rate),
            'regular_hours': float(regular_hours_total),
            'per_day_overtime': float(per_day_overtime_total),
            'overtime_multiplier': float(overtime_multiplier),
            'base_pay': float(base_pay),
            'additional_earnings': float(additional_total),
            'gross_pay': float(gross_pay),
            'deductions': deductions_map,
            'total_deductions': float(total_deductions),
            'net_pay': float(net_pay),
            'attendance_breakdown': attendance_breakdown,
        }

        return Response(preview_data, status=status.HTTP_200_OK)


class WeeklyPayrollListCreateView(generics.ListCreateAPIView):

    serializer_class = WeeklyPayrollSerializer

    permission_classes = [permissions.IsAuthenticated]

    queryset = WeeklyPayroll.objects.filter(is_deleted=False).select_related("employee", "received_by")



    filterset_class = WeeklyPayrollFilter



    filter_backends = [

        DjangoFilterBackend,

        filters.SearchFilter,

        filters.OrderingFilter,

    ]



    # filterset_fields handled via WeeklyPayrollFilter


    search_fields = [
        "notes",
        "employee__username",
        "employee__first_name",
        "employee__last_name",
    ]
    ordering_fields = "__all__"

    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAdminUser()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        # Hide draft payrolls from regular employees
        user = self.request.user
        if not user.is_staff and user.role not in ['admin', 'manager']:
            qs = qs.exclude(status='draft')
        return filter_by_date_range(
            self.request, qs, "week_start"
        )


    def perform_create(self, serializer: WeeklyPayrollSerializer) -> None:
        instance: WeeklyPayroll = serializer.save()
        # Recompute upon creation using approved entries in the period
        instance.compute_from_daily_attendance()


        instance.save(
            update_fields=[
                "regular_hours",
                "night_diff_hours",
                "approved_ot_hours",
                "allowances",
                "additional_earnings_total",
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
                "updated_at",
            ]
        )




class WeeklyPayrollDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = WeeklyPayrollSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = WeeklyPayroll.objects.filter(is_deleted=False).select_related("employee", "received_by")

    def get_queryset(self):
        qs = super().get_queryset()
        # Hide draft payrolls from regular employees
        user = self.request.user
        if not user.is_staff and user.role not in ['admin', 'manager']:
            qs = qs.exclude(status='draft')
        return qs

    def get_object(self) -> WeeklyPayroll:
        try:
            obj = super().get_object()
            if obj.is_deleted:
                raise NotFound(detail="Payroll record not found.")
            return obj
        except WeeklyPayroll.DoesNotExist:
            raise NotFound(detail="Payroll record not found.")

    def perform_update(self, serializer: WeeklyPayrollSerializer) -> None:
        instance: WeeklyPayroll = serializer.save()
        # Keep figures in sync with daily attendance when key parameters change.
        instance.compute_from_daily_attendance()


        instance.save(
            update_fields=[
                "regular_hours",
                "night_diff_hours",
                "approved_ot_hours",
                "allowances",
                "additional_earnings_total",
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
                "updated_at",
            ]
        )



    def perform_destroy(self, instance: WeeklyPayroll) -> None:
        # Reverse any cash ban movements linked to this payroll
        try:
            from users.models import CashAdvanceMovement
            payroll_movements = CashAdvanceMovement.objects.filter(
                reference=f'payroll-{instance.id}',
                is_deleted=False,
            )
            for movement in payroll_movements:
                movement.is_deleted = True
                movement.save(update_fields=['is_deleted'])
                # Only reverse balance if movement was actually applied
                # (pending movements were never applied, so nothing to reverse)
                if not movement.is_pending:
                    if movement.movement_type == CashAdvanceMovement.MovementType.CREDIT:
                        movement.employee.cash_ban_balance -= movement.amount
                    else:
                        movement.employee.cash_ban_balance += movement.amount
                    movement.employee.save(update_fields=['cash_ban_balance'])
        except Exception as e:
            print(f"Error reversing cash ban movements for payroll {instance.id}: {e}")

        # Soft delete
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.save(update_fields=["is_deleted", "deleted_at"])


class WeeklyPayrollArchivedView(generics.ListAPIView):
    """List all archived (soft-deleted) weekly payroll records."""
    serializer_class = WeeklyPayrollSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_class = WeeklyPayrollFilter
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = [
        "notes",
        "employee__username",
        "employee__first_name",
        "employee__last_name",
    ]
    ordering_fields = "__all__"

    def get_queryset(self):
        return WeeklyPayroll.objects.filter(is_deleted=True).select_related("employee", "received_by")


class WeeklyPayrollRestoreView(APIView):
    """Restore an archived weekly payroll record."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        from django.shortcuts import get_object_or_404
        instance = get_object_or_404(WeeklyPayroll.objects.all(), pk=pk)
        if not instance.is_deleted:
            return Response(
                {"detail": "This record is not archived."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.is_deleted = False
        instance.deleted_at = None
        instance.save(update_fields=["is_deleted", "deleted_at"])
        serializer = WeeklyPayrollSerializer(instance)
        return Response(serializer.data)


class WeeklyPayrollDownloadPDFView(APIView):
    """Download a payslip as PDF."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, pk):
        from payroll.utils.pdf_generator import generate_payslip_pdf
        
        try:
            payroll = WeeklyPayroll.objects.select_related("employee").get(pk=pk, is_deleted=False)
            
            # Hide draft payrolls from regular employees
            user = request.user
            if not user.is_staff and user.role not in ['admin', 'manager']:
                if payroll.status == 'draft':
                    raise NotFound(detail="Payroll record not found.")
            
            return generate_payslip_pdf(payroll)
        except WeeklyPayroll.DoesNotExist:
            raise NotFound(detail="Payroll record not found.")


class WeeklyPayrollUpdateStatusView(APIView):
    """
    PATCH to update payroll status (draft -> approved -> paid).
    Request body:
    - status: string (required, one of: draft, approved, paid)
    """
    permission_classes = [permissions.IsAdminUser]

    def get_object(self, pk: int) -> WeeklyPayroll:
        try:
            return WeeklyPayroll.objects.get(pk=pk, is_deleted=False)
        except WeeklyPayroll.DoesNotExist:
            raise NotFound(detail="Payroll record not found.")

    def patch(self, request, pk: int, *args, **kwargs):
        payroll = self.get_object(pk)

        new_status = request.data.get('status')
        if not new_status:
            return Response(
                {'status': ['This field is required.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        if new_status not in ['draft', 'approved', 'paid']:
            return Response(
                {'status': ['Invalid status. Must be one of: draft, approved, paid.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Business rule: can only move forward (draft -> approved -> paid)
        status_order = {'draft': 0, 'approved': 1, 'paid': 2}
        current_order = status_order.get(payroll.status, 0)
        new_order = status_order.get(new_status, 0)

        if new_order < current_order:
            return Response(
                {'status': [f'Cannot move status backwards from {payroll.status} to {new_status}.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        old_status = payroll.status
        payroll.status = new_status
        payroll.save(update_fields=['status', 'updated_at'])

        # When approving payroll, finalize deductions (mark one-time deductions as applied)
        if old_status == 'draft' and new_status == 'approved':
            payroll.finalize_deductions()
            # Add cash ban contribution
            _add_cash_ban_contribution(payroll)
            # Apply pending cash advance movements
            _apply_pending_cash_advance_movements(payroll)

        serializer = WeeklyPayrollSerializer(payroll)
        return Response(serializer.data, status=status.HTTP_200_OK)



class WeeklyPayrollFiltersView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    filters_config = {
        "employee": {"options": lambda: get_user_options()},
        "status": {
            "options": lambda: [
                {"label": "Draft", "value": "draft"},
                {"label": "Approved", "value": "approved"},
                {"label": "Paid", "value": "paid"},
            ]
        },
    }

    ordering_config = [
        {"label": "Week Start", "value": "week_start"},
        {"label": "Regular Hours", "value": "regular_hours"},
        {"label": "Approved OT Hours", "value": "approved_ot_hours"},
        {"label": "Net Pay", "value": "net_pay"},
    ]

    def get(self, request, *args, **kwargs):
        return get_role_based_filter_response(
            request,
            self.filters_config,
            self.ordering_config,
        )

class WeeklyPayrollRecomputeView(APIView):

    """
    POST to recompute a WeeklyPayroll from daily attendance records.

    Request body (all optional):
    - include_unapproved: bool (include unapproved attendance records)
    - allowances: number
    - extra_flat_deductions: { name: number, ... }
    - percent_deductions: { name: number, ... }  # number is a rate (e.g., 0.12 for 12%)

    This endpoint recalculates:
    - Regular and overtime hours from daily attendance
    - Approved overtime requests (1.25× rate)
    - Holiday premiums
    - Night differential
    - All deductions
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk: int) -> WeeklyPayroll:
        try:
            obj = WeeklyPayroll.objects.select_related("employee").get(
                pk=pk, is_deleted=False
            )
            return obj
        except WeeklyPayroll.DoesNotExist:
            raise NotFound(detail="Payroll record not found.")

    def post(self, request, pk: int, *args, **kwargs):
        payroll = self.get_object(pk)

        # Prevent recomputing payrolls that have been paid
        if payroll.status == 'paid':
            return Response(
                {"detail": "Cannot recompute payroll that has been paid."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Refresh hourly_rate from employee's current basic_salary
        employee = payroll.employee
        if employee.basic_salary and employee.basic_salary > 0:
            payroll.hourly_rate = Decimal(employee.basic_salary) / Decimal('8.00')

        include_unapproved = bool(request.data.get("include_unapproved") or False)

        allowances = request.data.get("allowances", None)
        allowances_dec: Optional[Decimal]
        if allowances is None:
            allowances_dec = None
        else:
            try:
                allowances_dec = Decimal(str(allowances))
            except Exception:
                return Response(
                    {"allowances": ["Must be a valid number."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Extra flat deductions
        extra_flat_raw = request.data.get("extra_flat_deductions") or {}
        extra_flat: Dict[str, Decimal] = {}
        if not isinstance(extra_flat_raw, dict):
            return Response(
                {"extra_flat_deductions": ["Must be an object mapping."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for name, amt in extra_flat_raw.items():
            try:
                extra_flat[str(name)] = Decimal(str(amt))
            except Exception:
                return Response(
                    {"extra_flat_deductions": [f"Invalid amount for '{name}'."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Percentage deductions
        percent_raw = request.data.get("percent_deductions") or {}
        percent: Dict[str, Decimal] = {}
        if not isinstance(percent_raw, dict):
            return Response(
                {"percent_deductions": ["Must be an object mapping."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for name, rate in percent_raw.items():
            try:
                rate_dec = Decimal(str(rate))
                if rate_dec < 0:
                    return Response(
                        {
                            "percent_deductions": [
                                f"Rate for '{name}' cannot be negative."
                            ]
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                percent[str(name)] = rate_dec
            except Exception:
                return Response(
                    {"percent_deductions": [f"Invalid rate for '{name}'."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Compute and persist
        payroll.compute_from_daily_attendance(
            include_unapproved=include_unapproved,
            allowances=allowances_dec,
            extra_flat_deductions=extra_flat or None,
            percent_deductions=percent or None,
        )


        payroll.save(
            update_fields=[
                "hourly_rate",
                "regular_hours",
                "night_diff_hours",
                "approved_ot_hours",
                "allowances",
                "additional_earnings_total",
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
                "updated_at",
            ]
        )

        data = WeeklyPayrollSerializer(payroll).data

        return Response(data, status=status.HTTP_200_OK)


class WeeklyPayrollBulkGenerateView(APIView):
    """
    POST to generate payroll for all active employees for a specific week.
    Request body:
    - week_start: string YYYY-MM-DD (required)
    - week_end: string YYYY-MM-DD (required)
    - include_unapproved: bool (default False)
    - notes: string (optional)
    - employee_ids: list[int] (optional - if provided, only generate for these employees)

    Returns:
    - created: list of created payroll objects
    - skipped: list of {employee_id, employee_name, reason} for skipped employees
    - errors: list of {employee_id, employee_name, error} for failed generations
    """
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, *args, **kwargs):
        from users.models import CustomUser as User

        include_unapproved = bool(request.data.get('include_unapproved', False))
        notes = request.data.get('notes', '')
        employee_ids = request.data.get('employee_ids')

        # Get payroll settings for cutoff calculation
        try:
            settings_obj = PayrollSettings.objects.first()
            if not settings_obj:
                settings_obj = PayrollSettings.objects.create()
        except Exception:
            settings_obj = None

        cutoff_day = getattr(settings_obj, 'payroll_cutoff_day', 4)

        # Use provided dates or auto-calculate
        week_start_str = request.data.get('week_start')
        week_end_str = request.data.get('week_end')

        if week_start_str and week_end_str:
            try:
                week_start = datetime.strptime(str(week_start_str), '%Y-%m-%d').date()
                week_end = datetime.strptime(str(week_end_str), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                return Response(
                    {'detail': 'Invalid date format. Use YYYY-MM-DD.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if week_end < week_start:
                return Response(
                    {'detail': 'week_end must be on or after week_start.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        elif week_start_str:
            try:
                week_start = datetime.strptime(str(week_start_str), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                return Response(
                    {'detail': 'Invalid date format. Use YYYY-MM-DD.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            week_end = week_start + timedelta(days=6)
        else:
            # Auto-calculate from cutoff day
            today = datetime.now().date()
            current_weekday = today.weekday()
            days_since_cutoff = (current_weekday - cutoff_day) % 7
            if days_since_cutoff == 0 and datetime.now().time().hour < 23:
                days_since_cutoff = 7
            last_cutoff = today - timedelta(days=days_since_cutoff)
            week_start = last_cutoff - timedelta(days=6)
            week_end = week_start + timedelta(days=6)

        # Get employees (only those with include_in_payroll=True)
        employees_qs = User.objects.filter(is_deleted=False, is_active=True, include_in_payroll=True)
        if employee_ids:
            employees_qs = employees_qs.filter(id__in=employee_ids)

        created = []
        skipped = []
        errors = []

        for employee in employees_qs:
            # Check if employee has basic_salary
            if not employee.basic_salary or employee.basic_salary <= 0:
                skipped.append({
                    'employee_id': employee.id,
                    'employee_name': employee.get_full_name(),
                    'reason': 'No valid basic salary configured'
                })
                continue

            # Check if payroll already exists
            existing = WeeklyPayroll.objects.filter(
                employee=employee,
                week_start=week_start,
                is_deleted=False
            ).first()

            if existing:
                skipped.append({
                    'employee_id': employee.id,
                    'employee_name': employee.get_full_name(),
                    'reason': f'Payroll already exists (ID: {existing.id})'
                })
                continue

            try:
                hourly_rate = Decimal(employee.basic_salary) / Decimal('8.00')
                overtime_multiplier = Decimal(getattr(settings_obj, 'overtime_multiplier', Decimal('1.50')) or '1.50')

                with transaction.atomic():
                    payroll = WeeklyPayroll.objects.create(
                        employee=employee,
                        week_start=week_start,
                        week_end=week_end,
                        hourly_rate=hourly_rate,
                        overtime_threshold=Decimal('40.00'),
                        overtime_multiplier=overtime_multiplier,
                        notes=notes,
                        status='draft'
                    )

                    payroll.compute_from_daily_attendance(include_unapproved=include_unapproved)

                    payroll.save(update_fields=[
                        'week_end', 'regular_hours', 'night_diff_hours',
                        'approved_ot_hours', 'allowances', 'additional_earnings_total',
                        'gross_pay', 'night_diff_pay', 'approved_ot_pay',
                        'holiday_pay_regular', 'holiday_pay_special', 'holiday_pay_total',
                        'deductions', 'deduction_metadata', 'total_deductions', 'net_pay', 'updated_at'
                    ])

                    created.append(WeeklyPayrollSerializer(payroll).data)

            except IntegrityError:
                # Race condition: payroll was created between check and creation
                existing = WeeklyPayroll.objects.filter(
                    employee=employee,
                    week_start=week_start,
                    is_deleted=False
                ).first()
                skipped.append({
                    'employee_id': employee.id,
                    'employee_name': employee.get_full_name(),
                    'reason': f'Payroll already exists (ID: {existing.id if existing else "unknown"})'
                })
            except Exception as e:
                errors.append({
                    'employee_id': employee.id,
                    'employee_name': employee.get_full_name(),
                    'error': str(e)
                })

        return Response({
            'week_start': week_start,
            'week_end': week_end,
            'created_count': len(created),
            'skipped_count': len(skipped),
            'error_count': len(errors),
            'created': created,
            'skipped': skipped,
            'errors': errors
        }, status=status.HTTP_200_OK if not errors else status.HTTP_207_MULTI_STATUS)


class WeeklyPayrollBulkUpdateStatusView(APIView):
    """
    PATCH to update status for multiple payroll records.
    Request body:
    - payroll_ids: list[int] (required)
    - status: string (required, one of: draft, approved, paid)
    """
    permission_classes = [permissions.IsAdminUser]

    def patch(self, request, *args, **kwargs):
        payroll_ids = request.data.get('payroll_ids', [])
        new_status = request.data.get('status', '').strip()

        if not payroll_ids or not isinstance(payroll_ids, list):
            return Response(
                {'payroll_ids': ['Must provide a list of payroll IDs.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        if new_status not in ['draft', 'approved', 'paid']:
            return Response(
                {'status': ['Invalid status. Must be one of: draft, approved, paid.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get payrolls to update
        payrolls = WeeklyPayroll.objects.filter(
            id__in=payroll_ids,
            is_deleted=False
        )

        # Track which payrolls were draft before update (for finalization)
        draft_payroll_ids = list(payrolls.filter(status='draft').values_list('id', flat=True))

        # Update payrolls
        updated_count = payrolls.update(status=new_status)

        # If approving payrolls, finalize deductions for those that were draft
        if new_status == 'approved' and draft_payroll_ids:
            approved_payrolls = WeeklyPayroll.objects.filter(id__in=draft_payroll_ids)
            for payroll in approved_payrolls:
                payroll.finalize_deductions()
                # Add cash ban contribution
                _add_cash_ban_contribution(payroll)
                # Apply pending cash advance movements
                _apply_pending_cash_advance_movements(payroll)

        return Response({
            'updated_count': updated_count,
            'status': new_status
        }, status=status.HTTP_200_OK)


class PayrollSettingsAdminView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        """
        Allow authenticated users to read settings (needed for clock in/out),
        but only admins can modify.
        """
        if self.request.method == 'GET':
            return [permissions.IsAuthenticated()]
        return [permissions.IsAdminUser()]

    def get(self, request):
        settings = PayrollSettings.objects.first()
        if not settings:
            settings = PayrollSettings.objects.create()
        data = PayrollSettingsSerializer(settings).data
        return Response(data, status=status.HTTP_200_OK)

    def put(self, request):
        settings = PayrollSettings.objects.first()
        if not settings:
            settings = PayrollSettings.objects.create()
        serializer = PayrollSettingsSerializer(settings, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        settings = PayrollSettings.objects.first()
        if not settings:
            settings = PayrollSettings.objects.create()
        serializer = PayrollSettingsSerializer(settings, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

class HolidayViewSet(SoftDeleteViewSetMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing holidays (admin only).
    Supports CRUD operations and provides filter options.
    """
    allow_hard_delete = True
    queryset = Holiday.objects.filter(is_deleted=False).order_by("-date")
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = HolidaySerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter
    ]
    search_fields = ['name']
    filterset_class = HolidayFilter
    ordering_fields = ['date', 'name', 'kind']

    def get_queryset(self):
        """Apply date range filtering on the 'date' field."""
        return filter_by_date_range(
            self.request, super().get_queryset(), "date"
        )

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        """
        GET /holidays/filters/
        Returns filter and ordering configuration for the frontend.
        """
        filters_config = {
            "kind": {
                "options": lambda: [
                    {"label": "Regular Holidays", "value": "regular"},
                    {"label": "Special Non Working Holidays", "value": "special_non_working"},
                ]
            },
        }

        ordering_config = [
            {"label": "Date", "value": "date"},
            {"label": "Kind", "value": "kind"},
        ]

        return get_role_based_filter_response(request, filters_config, ordering_config)

    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"detail": "No file provided (field 'file')."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            decoded = file.read().decode("utf-8")
        except UnicodeDecodeError:
            return Response({"detail": "CSV must be UTF-8 encoded."}, status=status.HTTP_400_BAD_REQUEST)

        reader = csv.reader(io.StringIO(decoded))
        try:
            header = next(reader)
        except StopIteration:
            return Response({"detail": "CSV is empty."}, status=status.HTTP_400_BAD_REQUEST)
        header_norm = [h.strip().lower() for h in header]
        if len(header_norm) < 3 or header_norm[0] != "date" or header_norm[1] != "name" or header_norm[2] != "type":
            return Response({"detail": "Invalid CSV header. Expected: Date, Name, Type"}, status=status.HTTP_400_BAD_REQUEST)

        def normalize_kind(raw: str):
            s = (raw or "").strip().lower()
            if "regular holiday" in s:
                return "regular"
            if "special non-working holiday" in s:
                return "special_non_working"
            return None

        import re
        def validate_date(date_str: str) -> bool:
            return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", date_str or ""))

        errors = []
        imported_count = 0
        with transaction.atomic():
            line_no = 1
            for row in reader:
                line_no += 1
                cols = [(c or "").strip() for c in row]
                if len(cols) < 3:
                    errors.append({"line": line_no, "message": "Missing columns"})
                    continue
                date_str, name, type_raw = cols[0], cols[1], cols[2]
                if not date_str or not name or not type_raw:
                    errors.append({"line": line_no, "message": "Empty required field(s)"})
                    continue
                if not validate_date(date_str):
                    errors.append({"line": line_no, "message": "Invalid date format (YYYY-MM-DD)"})
                    continue
                kind = normalize_kind(type_raw)
                if kind not in ("regular", "special_non_working"):
                    errors.append({"line": line_no, "message": f"Unknown Type '{type_raw}'"})
                    continue

                payload = {"date": date_str, "name": name, "kind": kind}
                ser = HolidaySerializer(data=payload)
                if not ser.is_valid():
                    errors.append({"line": line_no, "message": ser.errors})
                    continue
                ser.save()
                imported_count += 1

        return Response({"imported_count": imported_count, "skipped_count": len(errors), "errors": errors}, status=status.HTTP_200_OK)

class ManualDeductionViewSet(SoftDeleteViewSetMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing manual deductions.
    Supports CRUD operations with role-based access control.
    """
    serializer_class = ManualDeductionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "amount", "effective_date", "created_at"]

    def get_queryset(self):
        """
        Admins see all deductions.
        Employees see only their own per_employee deductions.
        """
        queryset = ManualDeduction.objects.filter(is_deleted=False).select_related("employee", "created_by")

        user = self.request.user
        if not user.role or user.role not in ["admin"]:
            # Regular employees see only their own per_employee deductions
            queryset = queryset.filter(employee=user)

        # Apply filters
        deduction_type = self.request.query_params.get("deduction_type")
        if deduction_type:
            queryset = queryset.filter(deduction_type=deduction_type)

        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() in ["true", "1"])

        employee_id = self.request.query_params.get("employee")
        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        """Set created_by to current user"""
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        """Activate a deduction"""
        deduction = self.get_object()
        deduction.is_active = True
        deduction.save(update_fields=["is_active"])
        serializer = self.get_serializer(deduction)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, pk=None):
        """Deactivate a deduction"""
        deduction = self.get_object()
        deduction.is_active = False
        deduction.save(update_fields=["is_active"])
        serializer = self.get_serializer(deduction)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def company_wide(self, request):
        """Get all active company-wide deductions (recurring_all and onetime_all)"""
        qs = self.get_queryset().filter(
            deduction_type__in=['recurring_all', 'onetime_all'],
            is_active=True
        )
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def for_employee(self, request):
        """Get all active deductions for a specific employee"""
        from rest_framework import status

        employee_id = request.query_params.get('employee_id')
        if not employee_id:
            return Response(
                {'error': 'employee_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Per-employee deductions
        per_employee = self.get_queryset().filter(
            deduction_type='per_employee',
            employee_id=employee_id,
            is_active=True
        )

        # Company-wide recurring deductions
        recurring_all = self.get_queryset().filter(
            deduction_type='recurring_all',
            is_active=True
        )

        # Combine both
        combined = list(per_employee) + list(recurring_all)
        serializer = self.get_serializer(combined, many=True)
        return Response(serializer.data)


class TaxBracketViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing tax brackets.
    Admin-only access for CRUD operations.
    """
    serializer_class = TaxBracketSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    ordering_fields = ["min_income", "effective_start", "created_at"]

    def get_queryset(self):
        queryset = TaxBracket.objects.select_related("created_by").all()

        # Filter by bracket type
        bracket_type = self.request.query_params.get("bracket_type")
        if bracket_type:
            queryset = queryset.filter(bracket_type=bracket_type)

        # Filter by active status
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() in ["true", "1"])

        # Filter by effective date
        as_of_date = self.request.query_params.get("as_of_date")
        if as_of_date:
            from django.db.models import Q
            queryset = queryset.filter(
                effective_start__lte=as_of_date
            ).filter(
                Q(effective_end__isnull=True) | Q(effective_end__gte=as_of_date)
            )

        return queryset.order_by("bracket_type", "min_income")

    def perform_create(self, serializer):
        """Set created_by to current user"""
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=["get"])
    def active(self, request):
        """Get currently active tax brackets"""
        from django.utils import timezone
        today = timezone.now().date()

        # Allow filtering by bracket_type in active endpoint
        bracket_type = request.query_params.get("bracket_type")
        qs = self.get_queryset().filter(
            is_active=True,
            effective_start__lte=today,
        ).filter(
            models.Q(effective_end__isnull=True) | models.Q(effective_end__gte=today)
        )

        if bracket_type:
            qs = qs.filter(bracket_type=bracket_type)

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)


class PercentageDeductionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing percentage-based deductions.
    Admin-only access for CRUD operations.
    """
    serializer_class = PercentageDeductionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "rate", "effective_start", "created_at"]

    def get_queryset(self):
        queryset = PercentageDeduction.objects.select_related("created_by").all()

        # Filter by active status
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() in ["true", "1"])

        # Filter by deduction type
        deduction_type = self.request.query_params.get("deduction_type")
        if deduction_type:
            queryset = queryset.filter(deduction_type=deduction_type)

        # Filter by effective date
        as_of_date = self.request.query_params.get("as_of_date")
        if as_of_date:
            from django.db.models import Q
            queryset = queryset.filter(
                effective_start__lte=as_of_date
            ).filter(
                Q(effective_end__isnull=True) | Q(effective_end__gte=as_of_date)
            )

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        """Set created_by to current user"""
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=["get"])
    def active(self, request):
        """Get currently active percentage deductions"""
        from django.db.models import Q
        from django.utils import timezone
        today = timezone.now().date()

        qs = self.get_queryset().filter(
            is_active=True,
            effective_start__lte=today,
        ).filter(
            Q(effective_end__isnull=True) | Q(effective_end__gte=today)
        )

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)


# ------------------------------------------------------------------------------
# Government Benefits
# ------------------------------------------------------------------------------


class GovernmentBenefitViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing government benefits (SSS, PhilHealth, Pag-IBIG, BIR Tax).
    Supports CRUD operations and active benefit filtering.
    """

    serializer_class = GovernmentBenefitSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["benefit_type", "notes"]
    ordering_fields = ["effective_start", "benefit_type", "created_at"]
    ordering = ["-effective_start"]

    def get_queryset(self):
        from django.db.models import Q
        from payroll.models import GovernmentBenefit

        queryset = GovernmentBenefit.objects.all()

        # Filter by benefit type
        benefit_type = self.request.query_params.get("benefit_type")
        if benefit_type:
            queryset = queryset.filter(benefit_type=benefit_type)

        # Filter by active status
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        # Filter by effective date
        as_of_date = self.request.query_params.get("as_of_date")
        if as_of_date:
            queryset = queryset.filter(
                effective_start__lte=as_of_date
            ).filter(
                Q(effective_end__isnull=True) | Q(effective_end__gte=as_of_date)
            )

        return queryset

    def perform_create(self, serializer):
        """Set created_by to current user"""
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=["get"])
    def active(self, request):
        """Get currently active government benefits"""
        from django.db.models import Q
        from django.utils import timezone
        from payroll.models import GovernmentBenefit

        today = timezone.now().date()

        qs = GovernmentBenefit.objects.filter(
            is_active=True,
            effective_start__lte=today,
        ).filter(
            Q(effective_end__isnull=True) | Q(effective_end__gte=today)
        ).order_by("benefit_type")

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def by_type(self, request):
        """Get benefits grouped by type"""
        from django.db.models import Q
        from django.utils import timezone
        from payroll.models import GovernmentBenefit

        today = timezone.now().date()
        benefit_type = request.query_params.get("type")

        if not benefit_type:
            return Response(
                {"error": "benefit_type parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        qs = GovernmentBenefit.objects.filter(
            benefit_type=benefit_type,
            is_active=True,
            effective_start__lte=today,
        ).filter(
            Q(effective_end__isnull=True) | Q(effective_end__gte=today)
        ).order_by("-effective_start")

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)


class EmployeeBenefitOverrideViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing employee-specific benefit overrides.
    Allows setting custom benefit amounts for individual employees.
    """
    
    serializer_class = EmployeeBenefitOverrideSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['employee', 'benefit_type', 'is_active']
    search_fields = ['employee__first_name', 'employee__last_name', 'notes']
    ordering_fields = ['effective_start', 'created_at', 'employee']
    ordering = ['-effective_start']
    
    def get_queryset(self):
        from payroll.models import EmployeeBenefitOverride
        
        queryset = EmployeeBenefitOverride.objects.select_related('employee').all()
        
        # Admin sees all, others see their own only
        if not self.request.user.is_staff and self.request.user.role != 'admin':
            queryset = queryset.filter(employee=self.request.user)
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
