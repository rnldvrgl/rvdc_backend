from datetime import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound
from django_filters.rest_framework import DjangoFilterBackend
from django.core.exceptions import ValidationError

from sales.models import SalesPayment, SalesTransaction
from sales.api.serializers import SalesPaymentSerializer, SalesTransactionSerializer
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

    @action(detail=True, methods=["post"])
    def add_payment(self, request, pk=None):
        """
        Allows adding a payment (partial or full) to an existing sales transaction.
        Does NOT overwrite old payments — just adds a new SalesPayment.
        """
        transaction = self.get_object()
        serializer = SalesPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        SalesPayment.objects.create(
            transaction=transaction,
            payment_type=serializer.validated_data["payment_type"],
            amount=serializer.validated_data["amount"],
            payment_date=serializer.validated_data.get("payment_date")
            or timezone.now(),
        )

        # update the status (already done by SalesPayment.save(), but we can be explicit)
        transaction.update_payment_status()

        transaction_serializer = self.get_serializer(transaction)
        return Response(transaction_serializer.data, status=status.HTTP_201_CREATED)
