from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
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
    filterset_fields = ["client__full_name", "stall__name", "payment_status", "voided"]
    search_fields = ["client__full_name", "stall__name"]

    def perform_create(self, serializer):
        serializer.save(sales_clerk=self.request.user)

    def partial_update(self, request, *args, **kwargs):
        """
        Standard PATCH for fields like client, payment_status etc.
        No voiding logic here anymore.
        """
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        reason = request.data.get("reason", "")
        try:
            instance = void_sales_transaction(pk, request.user, reason)
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

    @action(detail=True, methods=["post"])
    def unvoid(self, request, pk=None):
        try:
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
