from rest_framework import viewsets, filters, status
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from utils.enums import ChequeStatus
from utils.filters.role_filters import get_role_based_filter_response
from utils.filters.options import get_user_options, get_bank_options
from receivables.models import ChequeCollection, CollectionType
from receivables.api.serializers import ChequeCollectionSerializer
from receivables.api.filters import ChequeCollectionFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from utils.permissions import IsAdminOrManager
from utils.query import filter_by_date_range


class ChequeCollectionViewSet(viewsets.ModelViewSet):
    queryset = ChequeCollection.objects.select_related(
        "client", "collected_by", "sales_transaction"
    )
    serializer_class = ChequeCollectionSerializer
    permission_classes = [IsAdminOrManager]

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

    def destroy(self, request, *args, **kwargs):
        """Block deletion of cheques that are linked to any payment."""
        cheque = self.get_object()
        if cheque.service_payments.exists() or cheque.sales_payments.exists():
            return Response(
                {"detail": "Cannot delete this cheque because it is linked to a payment. Remove the payment first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

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

    @action(detail=False, methods=["get"], url_path="choices")
    def get_choices(self, request):
        """Return cheques available for linking to payments."""
        queryset = self.get_queryset()

        # Filter by client if provided
        client_id = request.query_params.get("client")
        if client_id:
            queryset = queryset.filter(client_id=client_id)

        # Only show pending or deposited cheques (not encashed, returned, bounced, or cancelled)
        status_filter = request.query_params.getlist("status")
        if status_filter:
            queryset = queryset.filter(status__in=status_filter)
        else:
            queryset = queryset.filter(status__in=["pending", "deposited"])

        # Return simplified data for dropdown
        data = []
        for cheque in queryset:
            if cheque.remaining_amount <= 0:
                continue
            data.append(
                {
                    "id": cheque.id,
                    "cheque_number": cheque.cheque_number,
                    "cheque_amount": str(cheque.cheque_amount),
                    "billing_amount": str(cheque.billing_amount),
                    "allocated_amount": str(cheque.allocated_amount),
                    "remaining_amount": str(cheque.remaining_amount),
                    "client_name": cheque.client.full_name if cheque.client else "",
                    "bank_name": cheque.bank_name,
                    "cheque_date": cheque.cheque_date,
                }
            )

        return Response(data)
