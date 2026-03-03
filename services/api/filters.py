from django_filters import rest_framework as filters
from services.models import Service, TechnicianAssignment


class ServiceFilter(filters.FilterSet):
    client = filters.NumberFilter(field_name="client_id", lookup_expr="exact")
    technician = filters.NumberFilter(
        field_name="technician_assignments__technician_id", lookup_expr="exact"
    )
    status = filters.CharFilter(field_name="status", lookup_expr="iexact")
    payment_status = filters.CharFilter(
        field_name="payment_status", lookup_expr="iexact"
    )
    service_type = filters.CharFilter(field_name="service_type", lookup_expr="iexact")
    service_mode = filters.CharFilter(field_name="service_mode", lookup_expr="iexact")
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
