from django_filters import rest_framework as filters
from sales.models import SalesTransaction


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    """Supports comma-separated values, e.g. ?payment_status=unpaid,partial"""

    pass


class SalesTransactionFilter(filters.FilterSet):
    payment_status = CharInFilter(field_name="payment_status", lookup_expr="in")
    has_receipt = filters.CharFilter(method="filter_has_receipt")

    def filter_has_receipt(self, queryset, name, value):
        if value == "with":
            return queryset.exclude(
                manual_receipt_number__isnull=True
            ).exclude(manual_receipt_number="")
        elif value == "without":
            from django.db.models import Q
            return queryset.filter(
                Q(manual_receipt_number__isnull=True) | Q(manual_receipt_number="")
            )
        return queryset

    class Meta:
        model = SalesTransaction
        fields = [
            "stall",
            "client",
            "payment_status",
            "voided",
            "transaction_type",
        ]
