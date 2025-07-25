from django.db import models
from django_filters import rest_framework as filters
from inventory.models import Stock, StockRoomStock


class StatusFilterMixin:
    def filter_by_status(self, queryset, name, value):
        value = value.lower()
        if value == "no_stock":
            return queryset.filter(quantity=0)
        elif value == "low_stock":
            return queryset.filter(
                quantity__gt=0, quantity__lte=models.F("low_stock_threshold")
            )
        elif value == "high_stock":
            return queryset.filter(quantity__gt=models.F("low_stock_threshold"))
        return queryset.none()


class StockFilter(StatusFilterMixin, filters.FilterSet):
    status = filters.CharFilter(method="filter_by_status")

    class Meta:
        model = Stock
        fields = ["stall", "item", "status"]


class StockRoomFilter(StatusFilterMixin, filters.FilterSet):
    status = filters.CharFilter(method="filter_by_status")

    class Meta:
        model = StockRoomStock
        fields = ["item", "status"]
