from django_filters import rest_framework as filters
from installations.models import (
    AirconModel,
    AirconInstallation,
    AirconUnit,
)


class AirconModelFilter(filters.FilterSet):
    class Meta:
        model = AirconModel
        fields = ["brand", "aircon_type", "is_inverter"]


class AirconUnitFilter(filters.FilterSet):
    is_reserved = filters.BooleanFilter(method="filter_is_reserved")
    is_available_for_sale = filters.BooleanFilter(method="filter_is_available_for_sale")

    class Meta:
        model = AirconUnit
        fields = [
            "model",
            "sale",
            "installation",
            "reserved_by",
        ]

    def filter_is_reserved(self, queryset, name, value):
        return queryset.filter(reserved_by__isnull=not value)

    def filter_is_available_for_sale(self, queryset, name, value):
        return queryset.filter(sale__isnull=value, reserved_by__isnull=value)


class AirconInstallationFilter(filters.FilterSet):
    class Meta:
        model = AirconInstallation
        fields = ["service"]
