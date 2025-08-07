from datetime import datetime, timedelta
from django.db.models import Q


def filter_by_date_range(request, queryset, date_field="created_at"):

    start = request.query_params.get("start_date")
    end = request.query_params.get("end_date")

    if start:
        queryset = queryset.filter(**{f"{date_field}__date__gte": start})

    if end:
        end_dt = datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1)
        queryset = queryset.filter(**{f"{date_field}__lt": end_dt})

    return queryset


def get_role_filtered_queryset(request, base_queryset):
    user = request.user

    if user.role == "admin":
        return filter_by_date_range(request, base_queryset)

    if user.role in ["manager", "clerk"] and user.assigned_stall:
        qs = base_queryset.filter(stall=user.assigned_stall)
        return filter_by_date_range(request, qs)

    return base_queryset.none()


def get_transfer_role_filtered_queryset(request, base_queryset):
    user = request.user

    if user.role == "admin":
        return filter_by_date_range(request, base_queryset)

    if user.role in ["manager", "clerk"] and user.assigned_stall:
        qs = base_queryset.filter(from_stall=user.assigned_stall)
        return filter_by_date_range(request, qs)

    return base_queryset.none()
