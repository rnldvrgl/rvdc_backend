from django_filters import rest_framework as filters
from services.models import Service, TechnicianAssignment
from django.db.models import Q


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    """Supports comma-separated values, e.g. ?payment_status=unpaid,partial"""

    pass


class ServiceFilter(filters.FilterSet):
    client = filters.NumberFilter(field_name="client_id", lookup_expr="exact")
    technician = filters.NumberFilter(
        field_name="technician_assignments__technician_id", lookup_expr="exact"
    )
    status = CharInFilter(field_name="status", lookup_expr="in")
    payment_status = CharInFilter(field_name="payment_status", lookup_expr="in")
    service_type = CharInFilter(field_name="service_type", lookup_expr="in")
    service_mode = CharInFilter(field_name="service_mode", lookup_expr="in")
    stall = filters.NumberFilter(field_name="stall_id", lookup_expr="exact")
    is_back_job = filters.BooleanFilter(field_name="is_back_job")
    has_receipt = filters.CharFilter(method="filter_has_receipt")
    receipt_type = filters.CharFilter(method="filter_receipt_type")

    def filter_has_receipt(self, queryset, name, value):
        receipt_q = Q(receipts__receipt_number__isnull=False) & ~Q(
            receipts__receipt_number=""
        )
        legacy_q = Q(manual_receipt_number__isnull=False) & ~Q(manual_receipt_number="")

        if value == "with":
            return queryset.filter(receipt_q | legacy_q).distinct()
        if value == "without":
            return queryset.exclude(receipt_q | legacy_q).distinct()
        return queryset

    def filter_receipt_type(self, queryset, name, value):
        values = [v.strip() for v in (value or "").split(",") if v.strip()]
        if not values:
            return queryset

        receipt_q = Q(receipts__document_type__in=values)
        legacy_q = Q(document_type__in=values) & Q(manual_receipt_number__isnull=False) & ~Q(
            manual_receipt_number=""
        )
        return queryset.filter(receipt_q | legacy_q).distinct()

    class Meta:
        model = Service
        fields = [
            "client",
            "technician",
            "status",
            "payment_status",
            "service_type",
            "service_mode",
            "stall",
            "is_back_job",
            "has_receipt",
            "receipt_type",
        ]


class TechnicianAssignmentFilter(filters.FilterSet):
    service = filters.NumberFilter(field_name="service_id", lookup_expr="exact")

    class Meta:
        model = TechnicianAssignment
        fields = ["technician", "service"]
