from django_filters import rest_framework as filters
from django.db.models import Q
from installations.models import (
    AirconModel,
    AirconInstallation,
    AirconUnit,
)


class AirconModelFilter(filters.FilterSet):
    has_discount = filters.BooleanFilter(method="filter_has_discount")

    class Meta:
        model = AirconModel
        fields = ["brand", "aircon_type", "is_inverter", "has_discount"]

    def filter_has_discount(self, queryset, name, value):
        """
        Filters aircon models by whether they have a discount.
        True -> discount_percentage > 0
        False -> discount_percentage = 0
        """
        if value:
            return queryset.filter(discount_percentage__gt=0)
        return queryset.filter(
            Q(discount_percentage=0) | Q(discount_percentage__isnull=True)
        )


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
