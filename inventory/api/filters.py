from django.db import models
from django_filters import rest_framework as filters
from inventory.models import Item, Stock, StockRoomStock, StockTransfer, ProductCategory
from users.models import CustomUser
from utils.filters.base import make_zero_filter


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
    track_stock = filters.BooleanFilter()

    class Meta:
        model = Stock
        fields = ["stall", "item", "status", "track_stock"]


class StockRoomFilter(StatusFilterMixin, filters.FilterSet):
    category = filters.NumberFilter(field_name="item__category_id", lookup_expr="exact")
    status = filters.CharFilter(method="filter_by_status")

    class Meta:
        model = StockRoomStock
        fields = ["status"]


class ItemFilter(filters.FilterSet):
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


class StockTransferFilter(filters.FilterSet):
    is_finalized = filters.BooleanFilter()
    is_paid = filters.BooleanFilter(method="filter_is_paid")
    technician = filters.ModelChoiceFilter(
        queryset=CustomUser.objects.filter(role="technician", is_deleted=False)
    )

    class Meta:
        model = StockTransfer
        fields = [
            "technician",
            "is_paid",
            "is_finalized",
        ]

    def filter_is_paid(self, queryset, name, value):
        if value:
            # Only transfers that have an expense and it's marked as paid
            return queryset.filter(expense__is_paid=True)
        else:
            # Either no expense yet (not finalized) or expense is unpaid
            return queryset.filter(
                models.Q(expense__isnull=True) | models.Q(expense__is_paid=False)
            )
