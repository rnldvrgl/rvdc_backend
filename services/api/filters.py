from django_filters import rest_framework as filters
from services.models import Service, TechnicianAssignment


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
        ]


class TechnicianAssignmentFilter(filters.FilterSet):
    service = filters.NumberFilter(field_name="service_id", lookup_expr="exact")

    class Meta:
        model = TechnicianAssignment
        fields = ["technician", "service"]
