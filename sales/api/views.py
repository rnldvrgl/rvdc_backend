from datetime import timezone, datetime, time as dt_time
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound
from django_filters.rest_framework import DjangoFilterBackend
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum, Count, F, Value, DecimalField, ExpressionWrapper, OuterRef, Subquery
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone as dj_timezone
from django.utils.dateparse import parse_date

from sales.models import SalesItem, SalesPayment, SalesTransaction, StallMonthlySheet
from sales.integrations.google_sheets import _get_google_sync_config, _share_sheet_with_email
from sales.api.serializers import (
    SalesPaymentSerializer,
    SalesTransactionSerializer,
    StallMonthlySheetSerializer,
)
from utils.sales import void_sales_transaction, unvoid_sales_transaction
from sales.api.filters import SalesTransactionFilter
from utils.permissions import IsAdminOrManager

from utils.filters.options import get_stall_options
from utils.filters.role_filters import get_role_based_filter_response
from utils.soft_delete import SoftDeleteViewSetMixin


class SalesTransactionViewSet(SoftDeleteViewSetMixin, viewsets.ModelViewSet):
    queryset = SalesTransaction.objects.select_related(
        'client', 'stall', 'sales_clerk'
    ).prefetch_related(
        'items__item__category',
        'payments',
    ).order_by(Coalesce("transaction_date", TruncDate("created_at")).desc(), "-created_at")
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
        "manual_receipt_number",
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
            # Use effective date (transaction_date if set, otherwise created_at date)
            # so backdated transactions appear on the correct day
            qs = qs.annotate(
                effective_date=Coalesce("transaction_date", TruncDate("created_at"))
            )
            date_q = Q()
            payment_q = Q()

            if start:
                start_date = parse_date(start)
                if start_date:
                    start_dt = dj_timezone.make_aware(datetime.combine(start_date, dt_time.min))
                    date_q &= Q(effective_date__gte=start_date)
                    payment_q &= Q(payments__payment_date__gte=start_dt)

            if end:
                end_date = parse_date(end)
                if end_date:
                    end_dt = dj_timezone.make_aware(datetime.combine(end_date, dt_time.max))
                    date_q &= Q(effective_date__lte=end_date)
                    payment_q &= Q(payments__payment_date__lte=end_dt)

            qs = qs.filter(date_q | payment_q).distinct()

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
            "has_receipt": {
                "options": lambda: [
                    {"label": "With Receipt #", "value": "with"},
                    {"label": "Without Receipt #", "value": "without"},
                ]
            },
            "receipt_type": {
                "options": lambda: [
                    {"label": "Official Receipt (OR)", "value": "or"},
                    {"label": "Sales Invoice (SI)", "value": "si"},
                ]
            },
        }

        ordering_config = [
            {"label": "Date", "value": "transaction_date"},
            {"label": "Created", "value": "created_at"},
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
        if (user.role == "admin"):
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

    @action(detail=False, methods=["get"], url_path="daily-summary")
    def daily_summary(self, request):
        """Return today's sales count and total amount for the current user's stall."""
        today = dj_timezone.localdate()
        qs = SalesTransaction.objects.filter(
            is_deleted=False, voided=False
        ).annotate(
            effective_date=Coalesce("transaction_date", TruncDate("created_at"))
        ).filter(effective_date=today)

        user = request.user
        if (user.role == "admin"):
            pass
        elif user.role in ("manager", "clerk") and getattr(user, "assigned_stall", None):
            qs = qs.filter(stall=user.assigned_stall)
        else:
            qs = qs.none()

        transaction_ids = qs.values_list("id", flat=True).distinct()

        line_total_expr = ExpressionWrapper(
            Coalesce(F("quantity"), Value(0))
            * Coalesce(F("final_price_per_unit"), Value(0))
            * (Value(1) - Coalesce(F("line_discount_rate"), Value(0))),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )

        item_total_subquery = (
            SalesItem.objects.filter(transaction_id=OuterRef("pk"))
            .annotate(line_total=line_total_expr)
            .values("transaction_id")
            .annotate(total=Sum("line_total"))
            .values("total")[:1]
        )

        totals_qs = SalesTransaction.objects.filter(id__in=transaction_ids).annotate(
            calculated_total=Coalesce(
                Subquery(
                    item_total_subquery,
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )

        agg = totals_qs.aggregate(
            count=Count("id", distinct=True),
            total=Sum("calculated_total"),
        )
        return Response({
            "count": agg["count"] or 0,
            "total": float(agg["total"] or 0),
        })

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
                or dj_timezone.now(),
            )

            transaction.update_payment_status()

        transaction_serializer = self.get_serializer(transaction)
        return Response(transaction_serializer.data, status=status.HTTP_201_CREATED)


class StallMonthlySheetViewSet(viewsets.ModelViewSet):
    queryset = StallMonthlySheet.objects.select_related("stall", "created_by").order_by(
        "-month_key", "stall__name"
    )
    serializer_class = StallMonthlySheetSerializer
    permission_classes = [IsAdminOrManager]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["stall", "month_key", "is_active"]
    ordering_fields = ["month_key", "created_at", "updated_at", "stall__name"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        stall = data["stall"]
        month_key = data["month_key"]
        spreadsheet_id = data["spreadsheet_id"]
        spreadsheet_url = (data.get("spreadsheet_url") or "").strip()
        is_active = data.get("is_active", True)

        instance = StallMonthlySheet.objects.filter(stall=stall, month_key=month_key).first()
        created = False

        if instance is None:
            instance = StallMonthlySheet.objects.create(
                stall=stall,
                month_key=month_key,
                spreadsheet_id=spreadsheet_id,
                spreadsheet_url=spreadsheet_url,
                is_active=is_active,
                created_by=request.user,
            )
            created = True
        else:
            previous_sheet_id = instance.spreadsheet_id
            instance.spreadsheet_id = spreadsheet_id
            instance.spreadsheet_url = spreadsheet_url
            instance.is_active = is_active
            if previous_sheet_id != spreadsheet_id:
                instance.shared_ok = False
                instance.shared_to_email = ""
                instance.shared_at = None
                instance.share_error = ""
            instance.save()

        share_email = (_get_google_sync_config().get("share_email") or "").strip()
        if share_email and instance.spreadsheet_id:
            shared_ok, share_error = _share_sheet_with_email(
                _get_google_sync_config(),
                instance.spreadsheet_id,
                share_email,
            )
            instance.shared_ok = bool(shared_ok)
            instance.shared_to_email = share_email if shared_ok else ""
            instance.shared_at = dj_timezone.now() if shared_ok else None
            instance.share_error = "" if shared_ok else (share_error or "Unknown share error")
            instance.save(update_fields=["shared_ok", "shared_to_email", "shared_at", "share_error", "updated_at"])

        output = self.get_serializer(instance)
        return Response(
            output.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
