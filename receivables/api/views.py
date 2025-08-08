from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from utils.enums import ChequeStatus
from utils.filters.role_filters import get_role_based_filter_response
from utils.filters.options import get_user_options, get_bank_options
from receivables.models import ChequeCollection, CollectionType
from receivables.api.serializers import ChequeCollectionSerializer
from receivables.api.filters import ChequeCollectionFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from utils.query import filter_by_date_range


class ChequeCollectionViewSet(viewsets.ModelViewSet):
    queryset = ChequeCollection.objects.select_related(
        "client", "collected_by", "sales_transaction"
    )
    serializer_class = ChequeCollectionSerializer
    permission_classes = [IsAuthenticated]

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = ChequeCollectionFilter
    search_fields = [
        "cheque_number",
        "or_number",
        "bank_name",
        "deposit_bank",
        "issued_by",
        "client__name",
    ]
    ordering_fields = "__all__"
    ordering = ["-date_collected"]

    def get_queryset(self):
        return filter_by_date_range(
            self.request, super().get_queryset(), "date_collected"
        )

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        filters_config = {
            "bank_name": {"options": lambda: get_bank_options()},
            "deposit_bank": {"options": lambda: get_bank_options()},
            "collection_type": {
                "options": lambda: [
                    {"label": label, "value": value}
                    for value, label in CollectionType.choices
                ]
            },
            "collected_by": {
                "options": lambda: get_user_options(exclude_roles=["technician"])
            },
            "status": {
                "options": lambda: [
                    {"label": label, "value": value}
                    for value, label in ChequeStatus.choices
                ]
            },
        }

        ordering_config = [
            {"label": "Date Collected", "value": "date_collected"},
            {"label": "Cheque Date", "value": "cheque_date"},
            {"label": "Cheque Amount", "value": "cheque_amount"},
        ]

        return get_role_based_filter_response(request, filters_config, ordering_config)
