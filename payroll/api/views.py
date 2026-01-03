from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Dict, Optional

from django.conf import settings
from django.db.models import QuerySet
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from payroll.api.serializers import (
    AdditionalEarningSerializer,
    OvertimeRequestApproveSerializer,
    OvertimeRequestSerializer,
    TimeEntryBulkCreateSerializer,
    TimeEntrySerializer,
    WeeklyPayrollSerializer,
)
from payroll.models import AdditionalEarning, OvertimeRequest, TimeEntry, WeeklyPayroll
from rest_framework import filters, generics, permissions, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

try:
    # If available in the project, you can use it in get_queryset overrides.
    from utils.query import filter_by_date_range  # type: ignore
except Exception:  # pragma: no cover - fallback if not present
    filter_by_date_range = None  # type: ignore


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except Exception:
        return None


def _start_of_day(dt: date) -> datetime:
    base = datetime.combine(dt, time.min)
    if settings.USE_TZ:
        tz = timezone.get_current_timezone()
        return tz.localize(base)
    return base


def _end_of_day(dt: date) -> datetime:
    base = datetime.combine(dt, time.max)
    if settings.USE_TZ:
        tz = timezone.get_current_timezone()
        return tz.localize(base)
    return base


def _apply_date_range(
    qs: QuerySet, request, *, field: str, is_date_field: bool = False
) -> QuerySet:
    """
    Apply inclusive date range filtering using start_date/end_date query params.
    - If field is DateTimeField: use [start_of_day, end_of_day]
    - If field is DateField: use [start_date, end_date]
    """
    start_param = request.query_params.get("start_date")
    end_param = request.query_params.get("end_date")

    start = _parse_date(start_param)
    end = _parse_date(end_param)

    if start and end and end < start:
        # Swap to avoid empty range on invalid ordering
        start, end = end, start

    if start:
        if is_date_field:
            qs = qs.filter(**{f"{field}__gte": start})
        else:
            qs = qs.filter(**{f"{field}__gte": _start_of_day(start)})
    if end:
        if is_date_field:
            qs = qs.filter(**{f"{field}__lte": end})
        else:
            qs = qs.filter(**{f"{field}__lte": _end_of_day(end)})

    return qs



# ------------------------------------------------------------------------------

# Overtime Requests
# ------------------------------------------------------------------------------

class OvertimeRequestListCreateView(generics.ListCreateAPIView):
    serializer_class = OvertimeRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = OvertimeRequest.objects.all().select_related("employee")

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_fields = [
        "employee",
        "approved",
        "date",
        "employee__assigned_stall",
    ]
    search_fields = [
        "reason",
        "employee__username",
        "employee__first_name",
        "employee__last_name",
    ]
    ordering_fields = "__all__"

    def get_queryset(self):
        qs = super().get_queryset()
        # inclusive date range filtering on 'date' field
        if filter_by_date_range is not None:
            qs = filter_by_date_range(self.request, qs, field="date", is_date_field=True)  # type: ignore
        else:
            qs = _apply_date_range(qs, self.request, field="date", is_date_field=True)
        return qs

    def perform_create(self, serializer: OvertimeRequestSerializer) -> None:
        instance: OvertimeRequest = serializer.save()
        # Newly created OT requests are unapproved by default; no extra actions needed.
        instance.save(update_fields=["updated_at"])


class OvertimeRequestDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = OvertimeRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = OvertimeRequest.objects.all().select_related("employee")

    def get_object(self) -> OvertimeRequest:
        try:
            obj = super().get_object()
            return obj
        except OvertimeRequest.DoesNotExist:
            raise NotFound(detail="Overtime request not found.")

    def perform_destroy(self, instance: OvertimeRequest) -> None:
        # Hard delete aligns with request lifecycle; change to soft-delete if policy requires.
        instance.delete()


class OvertimeRequestApproveView(generics.UpdateAPIView):
    serializer_class = OvertimeRequestApproveSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = OvertimeRequest.objects.all().select_related("employee")

    def get_object(self) -> OvertimeRequest:
        try:
            obj = super().get_object()
            return obj
        except OvertimeRequest.DoesNotExist:
            raise NotFound(detail="Overtime request not found.")

    def perform_update(self, serializer: OvertimeRequestApproveSerializer) -> None:
        # Only managers should approve; enforce via custom permission in production if needed.
        serializer.save()

# ------------------------------------------------------------------------------
# Time Entries
# ------------------------------------------------------------------------------



class TimeEntryListCreateView(generics.ListCreateAPIView):
    serializer_class = TimeEntrySerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = TimeEntry.objects.filter(is_deleted=False).select_related("employee")

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_fields = [
        "employee",
        "approved",
        "source",
        "employee__assigned_stall",
    ]
    search_fields = [
        "notes",
        "employee__username",
        "employee__first_name",
        "employee__last_name",
    ]
    ordering_fields = "__all__"

    def get_queryset(self):
        qs = super().get_queryset()
        # Prefer the project's filter_by_date_range if available
        if filter_by_date_range is not None:
            qs = filter_by_date_range(self.request, qs, field="clock_in")
        else:
            qs = _apply_date_range(
                qs, self.request, field="clock_in", is_date_field=False
            )
        return qs

    def perform_destroy(self, instance: TimeEntry) -> None:
        # Soft delete safeguard if destroy is ever called through this view
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted"])


class TimeEntryDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TimeEntrySerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = TimeEntry.objects.filter(is_deleted=False).select_related("employee")

    def get_object(self) -> TimeEntry:
        try:
            obj = super().get_object()
            if obj.is_deleted:
                raise NotFound(detail="Time entry not found.")
            return obj
        except TimeEntry.DoesNotExist:
            raise NotFound(detail="Time entry not found.")

    def perform_destroy(self, instance: TimeEntry) -> None:
        # Soft delete
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted"])


# ------------------------------------------------------------------------------

# Bulk Time Entries
# ------------------------------------------------------------------------------


class TimeEntryBulkCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = TimeEntryBulkCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        employee_ids = data["employee_ids"]
        clock_in = data["clock_in"]
        clock_out = data["clock_out"]
        unpaid_break_minutes = data.get("unpaid_break_minutes", 0)
        source = data.get("source", "manual")
        approved = data.get("approved", True)
        notes = data.get("notes", "")

        created = []
        for emp_id in employee_ids:
            entry = TimeEntry.objects.create(
                employee_id=emp_id,
                clock_in=clock_in,
                clock_out=clock_out,
                unpaid_break_minutes=unpaid_break_minutes,
                source=source,
                approved=approved,
                notes=notes,
            )
            created.append(entry)

        return Response(
            TimeEntrySerializer(created, many=True).data, status=status.HTTP_201_CREATED
        )


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
    filterset_fields = [
        "employee",
        "category",
        "approved",
        "employee__assigned_stall",
    ]
    search_fields = [
        "description",
        "reference",
        "employee__username",
        "employee__first_name",
        "employee__last_name",
    ]
    ordering_fields = "__all__"

    def get_queryset(self):
        qs = super().get_queryset()
        if filter_by_date_range is not None:
            qs = filter_by_date_range(self.request, qs, date_field="earning_date")
        else:
            qs = _apply_date_range(
                qs, self.request, field="earning_date", is_date_field=True
            )
        return qs

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


class WeeklyPayrollListCreateView(generics.ListCreateAPIView):
    serializer_class = WeeklyPayrollSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = WeeklyPayroll.objects.filter(is_deleted=False).select_related("employee")

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_fields = [
        "employee",
        "status",
        "week_start",
        "employee__assigned_stall",
    ]
    search_fields = [
        "notes",
        "employee__username",
        "employee__first_name",
        "employee__last_name",
    ]
    ordering_fields = "__all__"

    def get_queryset(self):
        qs = super().get_queryset()
        # Prefer the project's filter_by_date_range if available
        if filter_by_date_range is not None:
            qs = filter_by_date_range(
                self.request, qs, field="week_start", is_date_field=True
            )  # type: ignore
        else:
            qs = _apply_date_range(
                qs, self.request, field="week_start", is_date_field=True
            )
        return qs

    def perform_create(self, serializer: WeeklyPayrollSerializer) -> None:
        instance: WeeklyPayroll = serializer.save()
        # Recompute upon creation using approved entries in the period
        instance.compute_from_time_entries()
        instance.save(
            update_fields=[
                "regular_hours",
                "overtime_hours",
                "allowances",
                "gross_pay",
                "deductions",
                "total_deductions",
                "net_pay",
                "updated_at",
            ]
        )


class WeeklyPayrollDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = WeeklyPayrollSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = WeeklyPayroll.objects.filter(is_deleted=False).select_related("employee")

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
        # Keep figures in sync with time entries when key parameters change.
        instance.compute_from_time_entries()
        instance.save(
            update_fields=[
                "regular_hours",
                "overtime_hours",
                "allowances",
                "gross_pay",
                "deductions",
                "total_deductions",
                "net_pay",
                "updated_at",
            ]
        )

    def perform_destroy(self, instance: WeeklyPayroll) -> None:
        # Soft delete
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted"])


class WeeklyPayrollRecomputeView(APIView):
    """
    POST to recompute a WeeklyPayroll from its time entries.

    Request body (all optional):
    - include_unapproved: bool
    - allowances: number
    - extra_flat_deductions: { name: number, ... }
    - percent_deductions: { name: number, ... }  # number is a rate (e.g., 0.12 for 12%)
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
        payroll.compute_from_time_entries(
            include_unapproved=include_unapproved,
            allowances=allowances_dec,
            extra_flat_deductions=extra_flat or None,
            percent_deductions=percent or None,
        )
        payroll.save(
            update_fields=[
                "regular_hours",
                "overtime_hours",
                "allowances",
                "gross_pay",
                "deductions",
                "total_deductions",
                "net_pay",
                "updated_at",
            ]
        )

        data = WeeklyPayrollSerializer(payroll).data

        return Response(data, status=status.HTTP_200_OK)


# ------------------------------------------------------------------------------
# Sessions Review (auto-closed entries)
# ------------------------------------------------------------------------------


class SessionsReviewListView(generics.ListAPIView):
    """
    List auto-closed time entries for manager review/correction.
    Supports start_date/end_date filters based on clock_in.
    """

    serializer_class = TimeEntrySerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = TimeEntry.objects.filter(
        is_deleted=False, auto_closed=True
    ).select_related("employee")

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_fields = [
        "employee",
        "employee__assigned_stall",
        "approved",
        "source",
    ]
    search_fields = [
        "notes",
        "employee__username",
        "employee__first_name",
        "employee__last_name",
    ]
    ordering_fields = "__all__"

    def get_queryset(self):
        qs = super().get_queryset()
        if filter_by_date_range is not None:
            qs = filter_by_date_range(self.request, qs, field="clock_in")
        else:
            qs = _apply_date_range(
                qs, self.request, field="clock_in", is_date_field=False
            )
        return qs


class SessionReviewDetailPatchView(generics.UpdateAPIView):
    """
    Patch a single auto-closed session to correct times, breaks, approval.
    Clearing auto_closed is automatic when a valid clock_out is present after correction.
    """

    serializer_class = TimeEntrySerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = TimeEntry.objects.filter(is_deleted=False).select_related("employee")

    def get_object(self) -> TimeEntry:
        obj = super().get_object()
        if obj.is_deleted:
            raise NotFound(detail="Time entry not found.")
        return obj

    def perform_update(self, serializer: TimeEntrySerializer) -> None:
        instance: TimeEntry = serializer.save()
        # If the session now has a valid clock_out, clear auto_closed flag.
        if instance.clock_out and instance.clock_out > instance.clock_in:
            if instance.auto_closed:
                instance.auto_closed = False
                instance.save(update_fields=["auto_closed", "updated_at"])
