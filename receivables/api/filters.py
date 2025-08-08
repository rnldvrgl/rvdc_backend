from django_filters import rest_framework as filters
from receivables.models import ChequeCollection


class ChequeCollectionFilter(filters.FilterSet):
    class Meta:
        model = ChequeCollection
        fields = [
            "bank_name",
            "deposit_bank",
            "collection_type",
            "status",
            "collected_by",
        ]
