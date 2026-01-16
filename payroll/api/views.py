from __future__ import annotations

import csv
import io
from decimal import Decimal
from typing import Dict, Optional

from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from payroll.api.filters import (
    AdditionalEarningFilter,
    HolidayFilter,
    TimeEntryFilter,
    WeeklyPayrollFilter,
)
from payroll.api.serializers import (
    AdditionalEarningSerializer,
    HolidaySerializer,
    OvertimeRequestApproveSerializer,
    OvertimeRequestSerializer,
    PayrollSettingsSerializer,
    TimeEntryBulkCreateSerializer,
    TimeEntrySerializer,
    WeeklyPayrollSerializer,
)
from payroll.models import (
    AdditionalEarning,
    Holiday,
    OvertimeRequest,
    PayrollSettings,
    TimeEntry,
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
        return filter_by_date_range(self.request, qs, "date")

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


    filterset_class = TimeEntryFilter

    search_fields = [
        "notes",
        "employee__username",
        "employee__first_name",
        "employee__last_name",
    ]
    ordering_fields = "__all__"



    def get_queryset(self):
        return filter_by_date_range(
            self.request, super().get_queryset(), "clock_in"
        )


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



class WeeklyPayrollListCreateView(generics.ListCreateAPIView):

    serializer_class = WeeklyPayrollSerializer

    permission_classes = [permissions.IsAuthenticated]

    queryset = WeeklyPayroll.objects.filter(is_deleted=False).select_related("employee")



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



    def get_queryset(self):
        return filter_by_date_range(
            self.request, super().get_queryset(), "week_start"
        )


    def perform_create(self, serializer: WeeklyPayrollSerializer) -> None:
        instance: WeeklyPayroll = serializer.save()
        # Recompute upon creation using approved entries in the period
        instance.compute_from_time_entries()


        instance.save(
            update_fields=[
                "regular_hours",
                "overtime_hours",
                "night_diff_hours",
                "approved_ot_hours",
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
                "night_diff_hours",
                "approved_ot_hours",
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
                "updated_at",
            ]
        )



    def perform_destroy(self, instance: WeeklyPayroll) -> None:
        # Soft delete
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted"])



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
        {"label": "OT Hours", "value": "overtime_hours"},
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
                "night_diff_hours",
                "approved_ot_hours",
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
                "updated_at",

            ]
        )



        data = WeeklyPayrollSerializer(payroll).data

        return Response(data, status=status.HTTP_200_OK)






class PayrollSettingsAdminView(APIView):
    permission_classes = [permissions.IsAdminUser]

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

class HolidayViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing holidays (admin only).
    Supports CRUD operations and provides filter options.
    """
    queryset = Holiday.objects.filter(is_deleted=False).order_by("-date")
    permission_classes = [permissions.IsAdminUser]
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
            {"label": "Name", "value": "name"},
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

    def perform_destroy(self, instance: Holiday) -> None:
        """Soft delete the holiday."""
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted"])


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
        return filter_by_date_range(
            self.request, super().get_queryset(), "clock_in"
        )


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
