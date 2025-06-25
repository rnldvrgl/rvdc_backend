import django_filters
from sales.models import SalesTransaction


class VoidedSalesTransactionFilter(django_filters.FilterSet):
    created_at = django_filters.DateFromToRangeFilter()

    class Meta:
        model = SalesTransaction
        fields = [
            "sales_clerk__username",
            "client__full_name",
            "stall__name",
            "created_at",
        ]
