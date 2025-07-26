from django_filters import rest_framework as filters
from remittances.models import RemittanceRecord


class RemittanceRecordFilter(filters.FilterSet):
    class Meta:
        model = RemittanceRecord
        fields = ["stall", "is_remitted"]
