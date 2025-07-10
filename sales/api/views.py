from rest_framework import viewsets, status, filters
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound
from django_filters.rest_framework import DjangoFilterBackend
from django.core.exceptions import ValidationError

from sales.models import SalesTransaction
from sales.api.serializers import SalesTransactionSerializer
from utils.sales import void_sales_transaction, unvoid_sales_transaction


class SalesTransactionViewSet(viewsets.ModelViewSet):
    queryset = SalesTransaction.objects.all().order_by("-created_at")
    serializer_class = SalesTransactionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["client__full_name", "sales_clerk__username", "voided"]
    search_fields = ["client__full_name", "sales_clerk__username"]

    def perform_create(self, serializer):
        serializer.save(sales_clerk=self.request.user)

    def partial_update(self, request, pk=None):
        instance = self.get_object()
        is_voided = request.data.get("voided")
        reason = request.data.get("reason", "")

        if is_voided is not None:
            try:
                if is_voided:
                    instance = void_sales_transaction(pk, request.user, reason)
                else:
                    instance = unvoid_sales_transaction(pk, request.user)
            except ValidationError as e:
                return Response(
                    {"non_field_errors": [str(e)]}, status=status.HTTP_400_BAD_REQUEST
                )
            except NotFound as e:
                return Response(
                    {"non_field_errors": [str(e)]}, status=status.HTTP_404_NOT_FOUND
                )

        serializer = self.get_serializer(instance)
        return Response(serializer.data)
