from datetime import datetime, time

from django.utils import timezone
from django.utils.dateparse import parse_date


def filter_by_date_range(request, queryset, date_field="created_at"):
    start = request.query_params.get("start_date")
    end = request.query_params.get("end_date")

    if not start and not end:
        return queryset

    filters = {}

    if start:
        start_date = parse_date(start)
        if start_date:
            start_dt = timezone.make_aware(
                datetime.combine(start_date, time.min)
            )
            filters[f"{date_field}__gte"] = start_dt

    if end:
        end_date = parse_date(end)
        if end_date:
            end_dt = timezone.make_aware(
                datetime.combine(end_date, time.max)
            )
            filters[f"{date_field}__lte"] = end_dt

    return queryset.filter(**filters)


def get_role_filtered_queryset(request, base_queryset, date_field="created_at", stall_field="stall"):
    """
    Filter queryset based on user role and assigned stall.

    Args:
        request: The HTTP request object
        base_queryset: The base queryset to filter
        date_field: Field name for date range filtering (default: "created_at")
        stall_field: Field name or lookup path for stall filtering (default: "stall")
                     Use "unit__stall" for models that have stall through a relationship
    """
    user = request.user

    if user.role == "admin":
        return filter_by_date_range(request, base_queryset, date_field)

    if user.role in ["manager", "clerk"] and user.assigned_stall:
        filter_kwargs = {stall_field: user.assigned_stall}
        qs = base_queryset.filter(**filter_kwargs)
        return filter_by_date_range(request, qs, date_field)

    return base_queryset.none()


def get_transfer_role_filtered_queryset(
    request, base_queryset, date_field="created_at"
):
    user = request.user

    if user.role == "admin":
        return filter_by_date_range(request, base_queryset, date_field)

    if user.role in ["manager", "clerk"] and user.assigned_stall:
        qs = base_queryset.filter(from_stall=user.assigned_stall)
        return filter_by_date_range(request, qs, date_field)

    return base_queryset.none()
