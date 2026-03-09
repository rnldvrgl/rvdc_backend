from django_filters import rest_framework as filters
from sales.models import SalesTransaction


class SalesTransactionFilter(filters.FilterSet):
    class Meta:
        model = SalesTransaction
        fields = ["stall", "client", "payment_status", "voided"]
