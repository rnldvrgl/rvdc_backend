from django.db import models
from django_filters import rest_framework as filters
from services.models import Service, TechnicianAssignment


class ServiceFilter(filters.FilterSet):
    client = filters.NumberFilter(field_name="client_id", lookup_expr="exact")
    technician = filters.NumberFilter(
        field_name="technician_assignments__technician_id", lookup_expr="exact"
    )
    status = filters.CharFilter(field_name="status", lookup_expr="iexact")
    service_type = filters.CharFilter(field_name="service_type", lookup_expr="iexact")

    class Meta:
        model = Service
        fields = [
            "client",
            "technician",
            "status",
            "service_type",
        ]


class TechnicianAssignmentFilter(filters.FilterSet):
    service = filters.NumberFilter(field_name="service_id", lookup_expr="exact")

    class Meta:
        model = TechnicianAssignment
        fields = ["technician", "service"]
