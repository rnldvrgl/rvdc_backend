from datetime import timezone, datetime, time as dt_time
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound
from django_filters.rest_framework import DjangoFilterBackend
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone as dj_timezone
from django.utils.dateparse import parse_date

from sales.models import SalesPayment, SalesTransaction
from sales.api.serializers import SalesPaymentSerializer, SalesTransactionSerializer
from utils.sales import void_sales_transaction, unvoid_sales_transaction
from sales.api.filters import SalesTransactionFilter

from utils.filters.options import get_stall_options
from utils.filters.role_filters import get_role_based_filter_response
from utils.soft_delete import SoftDeleteViewSetMixin


class SalesTransactionViewSet(SoftDeleteViewSetMixin, viewsets.ModelViewSet):
    queryset = SalesTransaction.objects.select_related(
        'client', 'stall', 'sales_clerk'
    ).prefetch_related(
        'items__item__category',
        'payments',
    ).order_by("-created_at")
    serializer_class = SalesTransactionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = SalesTransactionFilter
    search_fields = [
        "client__full_name",
        "stall__name",
        "payment_status",
        "client__contact_number",
    ]
    ordering_fields = "__all__"

    def get_queryset(self):
        qs = super().get_queryset().filter(is_deleted=False, voided=False)
        user = self.request.user

        # Custom date filtering: include transactions that were CREATED in the date
        # range OR have PAYMENTS in the date range (so service payments on old
        # receipts show up on the day the money was received)
        start = self.request.query_params.get("start_date")
        end = self.request.query_params.get("end_date")

        # Role-based stall filtering
        # When viewing a specific client's history, show all stalls
        # so both main and sub stall transactions are visible
        client_filter = self.request.query_params.get("client")
        if user.role == "admin":
            pass  # admin sees all stalls
        elif user.role in ("manager", "clerk") and getattr(user, "assigned_stall", None):
            if not client_filter:
                qs = qs.filter(stall=user.assigned_stall)
        else:
            return qs.none()

        if start or end:
            created_q = Q()
            payment_q = Q()

            if start:
                start_date = parse_date(start)
                if start_date:
                    start_dt = dj_timezone.make_aware(datetime.combine(start_date, dt_time.min))
                    created_q &= Q(created_at__gte=start_dt)
                    payment_q &= Q(payments__payment_date__gte=start_dt)

            if end:
                end_date = parse_date(end)
                if end_date:
                    end_dt = dj_timezone.make_aware(datetime.combine(end_date, dt_time.max))
                    created_q &= Q(created_at__lte=end_dt)
                    payment_q &= Q(payments__payment_date__lte=end_dt)

            qs = qs.filter(created_q | payment_q).distinct()

        return qs

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        filters_config = {
            "stall": {"options": get_stall_options},
            "payment_status": {
                "options": lambda: [
                    {"label": "Paid", "value": "paid"},
                    {"label": "Unpaid", "value": "unpaid"},
                    {"label": "Partial", "value": "partial"},
                ]
            },
            "transaction_type": {
                "options": lambda: [
                    {"label": "Sale", "value": "sale"},
                    {"label": "Replacement", "value": "replacement"},
                ]
            },
        }

        ordering_config = [
            {"label": "Date", "value": "created_at"},
            {"label": "Stall", "value": "stall__name"},
        ]

        return get_role_based_filter_response(request, filters_config, ordering_config)

    def create(self, request, *args, **kwargs):
        # Idempotency guard: prevent duplicate transactions from double-clicks
        # or slow connections. Uses Idempotency-Key header if provided,
        # otherwise falls back to a hash of the request body + user.
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            import hashlib, json
            body_hash = hashlib.sha256(
                json.dumps(request.data, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
            idempotency_key = f"{request.user.id}:{body_hash}"

        cache_key = f"sales_create_idempotency:{idempotency_key}"

        if cache.get(cache_key):
            return Response(
                {"detail": "Duplicate request detected. This transaction was already submitted."},
                status=status.HTTP_409_CONFLICT,
            )

        # Lock for 30 seconds to prevent duplicate within that window
        cache.set(cache_key, True, timeout=30)

        try:
            return super().create(request, *args, **kwargs)
        except Exception:
            # If creation fails, clear the lock so the user can retry
            cache.delete(cache_key)
            raise

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

    @action(detail=False, methods=["get"], url_path="voided")
    def voided_list(self, request):
        """List voided transactions (separate tab in UI)."""
        qs = SalesTransaction.objects.select_related(
            'client', 'stall', 'sales_clerk'
        ).prefetch_related(
            'items__item__category', 'payments',
        ).filter(is_deleted=False, voided=True).order_by('-created_at')

        user = request.user
        if user.role == 'admin':
            pass
        elif user.role in ('manager', 'clerk') and getattr(user, 'assigned_stall', None):
            qs = qs.filter(stall=user.assigned_stall)
        else:
            qs = qs.none()

        qs = self.filter_queryset(qs)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)



    @action(detail=True, methods=["post"])
    def add_payment(self, request, pk=None):
        """
        Allows adding a payment (partial or full) to an existing sales transaction.
        Does NOT overwrite old payments — just adds a new SalesPayment.
        """
        from django.db import transaction as db_transaction

        serializer = SalesPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with db_transaction.atomic():
            # Lock the transaction row to prevent concurrent overpayment
            transaction = SalesTransaction.objects.select_for_update().get(pk=pk)

            if transaction.voided:
                return Response(
                    {"detail": "Cannot add payment to a voided transaction."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            amount = serializer.validated_data["amount"]
            balance_due = transaction.computed_total - transaction.total_paid
            if balance_due <= 0:
                return Response(
                    {"detail": "Transaction is already fully paid."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            SalesPayment.objects.create(
                transaction=transaction,
                payment_type=serializer.validated_data["payment_type"],
                amount=amount,
                payment_date=serializer.validated_data.get("payment_date")
                or timezone.now(),
            )

            transaction.update_payment_status()

        transaction_serializer = self.get_serializer(transaction)
        return Response(transaction_serializer.data, status=status.HTTP_201_CREATED)
