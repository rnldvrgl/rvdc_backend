from django_filters import rest_framework as filters
from sales.models import SalesTransaction


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    """Supports comma-separated values, e.g. ?payment_status=unpaid,partial"""

    pass


class SalesTransactionFilter(filters.FilterSet):
    payment_status = CharInFilter(field_name="payment_status", lookup_expr="in")

    class Meta:
        model = SalesTransaction
        fields = ["stall", "client", "payment_status", "voided", "transaction_type"]
