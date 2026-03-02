from django_filters import rest_framework as filters
from django.db.models import Q
from installations.models import (
    AirconModel,
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
    is_sold = filters.BooleanFilter(field_name="is_sold")
    is_installed = filters.BooleanFilter(method="filter_is_installed")
    is_available = filters.BooleanFilter(method="filter_is_available")
    # Internal filters — used programmatically by warranty / free cleaning tabs
    sale__client = filters.NumberFilter(field_name="sale__client")
    reserved_by = filters.NumberFilter(field_name="reserved_by")
    is_available_for_sale = filters.BooleanFilter(method="filter_is_available_for_sale")
    is_available_for_installation = filters.BooleanFilter(method="filter_is_available_for_installation")
    client = filters.NumberFilter(method="filter_by_client")

    class Meta:
        model = AirconUnit
        fields = [
            "model",
        ]

    def filter_is_installed(self, queryset, name, value):
        """Filter units whose installation service is completed."""
        from utils.enums import ServiceStatus
        if value:
            return queryset.filter(
                installation_service__isnull=False,
                installation_service__status=ServiceStatus.COMPLETED,
            )
        return queryset.exclude(
            installation_service__isnull=False,
            installation_service__status=ServiceStatus.COMPLETED,
        )

    def filter_is_available(self, queryset, name, value):
        """Available = no sale, no reservation, no installation."""
        if value:
            return queryset.filter(
                sale__isnull=True,
                reserved_by__isnull=True,
                installation_service__isnull=True,
                is_sold=False,
            )
        return queryset.exclude(
            sale__isnull=True,
            reserved_by__isnull=True,
            installation_service__isnull=True,
            is_sold=False,
        )

    def filter_is_available_for_sale(self, queryset, name, value):
        return queryset.filter(sale__isnull=value, reserved_by__isnull=value)

    def filter_is_available_for_installation(self, queryset, name, value):
        if value:
            return queryset.filter(installation_service__isnull=True)
        else:
            return queryset.filter(installation_service__isnull=False)

    def filter_by_client(self, queryset, name, value):
        """Filter units belonging to a client — via sale, reservation, or installation service."""
        return queryset.filter(
            Q(sale__client_id=value)
            | Q(reserved_by_id=value)
            | Q(installation_service__client_id=value)
        )
