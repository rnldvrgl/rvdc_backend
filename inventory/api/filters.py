from django.db import models
from django_filters import rest_framework as filters
from inventory.models import (
    Item,
    Stock,
    StockRoomStock,
)
from utils.filters.base import make_zero_filter

# --------------------------
# Status Filter Mixins
# --------------------------


class StatusFilterMixin:
    """
    For stall-level Stock.
    Uses available stock (quantity - reserved_quantity)
    to determine no_stock / low_stock / high_stock.
    """

    def filter_by_status(self, queryset, name, value):
        value = value.lower().strip()

        if value == "no_stock":
            # No available stock (available = 0)
            return queryset.filter(available_expr__lte=0)
        elif value == "low_stock":
            # Has stock but at or below threshold (0 < available <= threshold)
            return queryset.filter(
                available_expr__gt=0,
                available_expr__lte=models.F("low_stock_threshold"),
            )
        elif value == "high_stock":
            # Above threshold (available > threshold)
            return queryset.filter(available_expr__gt=models.F("low_stock_threshold"))
        return queryset.none()


class StockRoomStatusFilterMixin:
    """
    For stockroom-level StockRoomStock.
    Uses raw quantity (no reservations).
    """

    def filter_by_status(self, queryset, name, value):
        value = value.lower().strip()
        if value == "no_stock":
            return queryset.filter(quantity=0)
        elif value == "low_stock":
            return queryset.filter(
                quantity__gt=0, quantity__lte=models.F("low_stock_threshold")
            )
        elif value == "high_stock":
            return queryset.filter(quantity__gt=models.F("low_stock_threshold"))
        return queryset.none()


# --------------------------
# Filters
# --------------------------


class StockFilter(StatusFilterMixin, filters.FilterSet):
    """
    For stall-level stock management.
    Includes reserved quantity logic and tracking flag.
    """

    status = filters.CharFilter(method="filter_by_status")
    track_stock = filters.BooleanFilter()

    class Meta:
        model = Stock
        fields = ["stall", "item", "status", "track_stock"]


class StockRoomFilter(StockRoomStatusFilterMixin, filters.FilterSet):
    """
    For stock room inventory (no reserved qty concept).
    """

    category = filters.NumberFilter(field_name="item__category_id", lookup_expr="exact")
    status = filters.CharFilter(method="filter_by_status")

    class Meta:
        model = StockRoomStock
        fields = ["status", "category"]


class ItemFilter(filters.FilterSet):
    """
    Allows filtering items by price fields and category/unit.
    """

    wholesale_price = filters.BooleanFilter(method=make_zero_filter("wholesale_price"))
    technician_price = filters.BooleanFilter(
        method=make_zero_filter("technician_price")
    )
    cost_price = filters.BooleanFilter(method=make_zero_filter("cost_price"))
    retail_price = filters.BooleanFilter(method=make_zero_filter("retail_price"))

    class Meta:
        model = Item
        fields = [
            "category",
            "unit_of_measure",
            "wholesale_price",
            "technician_price",
            "cost_price",
            "retail_price",
        ]
