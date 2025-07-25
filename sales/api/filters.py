from django_filters import rest_framework as filters
from sales.models import SalesTransaction


class SalesTransactionFilter(filters.FilterSet):
    class Meta:
        model = SalesTransaction
        fields = ["stall", "payment_status", "voided"]
