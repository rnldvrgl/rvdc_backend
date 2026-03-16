from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.db.models import Q
from django.db.models.functions import Lower, Replace
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from inventory.api.filters import (
    ItemFilter,
    StockFilter,
    StockRoomFilter,
)
from inventory.api.serializers import (
    ItemSerializer,
    ProductCategorySerializer,
    StallSerializer,
    StockAuditSerializer,
    StockPatchSerializer,
    StockReadSerializer,
    StockRequestSerializer,
    StockRestockSerializer,
    StockRoomStockSerializer,
    StockWriteSerializer,
)
from inventory.models import (
    Item,
    ProductCategory,
    Stall,
    Stock,
    StockRequest,
    StockRoomStock,
)
from notifications.models import Notification
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from utils.filters.options import (
    get_product_category_options,
    get_stall_options,
    get_status_options,
    get_unit_of_measure_options,
)
from utils.filters.role_filters import get_role_based_filter_response
from utils.inventory import (
    user_can_manage_stall,
)
from utils.query import (
    filter_by_date_range,
    get_role_filtered_queryset,
)
from utils.soft_delete import SoftDeleteViewSetMixin


class ItemViewSet(SoftDeleteViewSetMixin, viewsets.ModelViewSet):
    queryset = Item.objects.select_related('category').prefetch_related('price_history').all()
    serializer_class = ItemSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = ItemFilter
    search_fields = ["name"]
    ordering_fields = "__all__"

    def get_queryset(self):
        qs = super().get_queryset().filter(is_deleted=False)
        return filter_by_date_range(self.request, qs)

    # (moved) explicit disallowed-method handlers belong to StallViewSet, not ItemViewSet.

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        filters_config = {
            "category": {
                "options": get_product_category_options,
            },
            "unit_of_measure": {
                "options": get_unit_of_measure_options,
            },
            "retail_price": {
                "options": lambda: [
                    {"label": "Is Zero", "value": "true"},
                    {"label": "Is Not Zero", "value": "false"},
                ],
            },
            "wholesale_price": {
                "options": lambda: [
                    {"label": "Is Zero", "value": "true"},
                    {"label": "Is Not Zero", "value": "false"},
                ],
            },
            "technician_price": {
                "options": lambda: [
                    {"label": "Is Zero", "value": "true"},
                    {"label": "Is Not Zero", "value": "false"},
                ],
            },
            "cost_price": {
                "options": lambda: [
                    {"label": "Is Zero", "value": "true"},
                    {"label": "Is Not Zero", "value": "false"},
                ],
            },
        }

        ordering_config = [
            {"label": "Name", "value": "name"},
            {"label": "Category", "value": "category__name"},
            {"label": "Unit", "value": "unit_of_measure"},
        ]

        return get_role_based_filter_response(
            request,
            filters_config,
            ordering_config,
        )

    @action(detail=False, methods=["get"], url_path="check-duplicates")
    def check_duplicates(self, request):
        """
        Check for potential duplicate items matching a given name.

        Query params:
            name  – the item name to check (required)
            category_id – optional category filter
            exclude_id  – optional item id to exclude (for edits)

        Returns a list of possible matches ranked by similarity:
            1. Exact (case-insensitive) match
            2. Normalized match (ignoring whitespace & case)
            3. Substring / contains match
            4. Token (word) overlap match — catches jumbled names
               e.g. "capacitor 10uf" vs "10uf capacitor"
        """
        import re

        raw_name = request.query_params.get("name", "").strip()
        category_id = request.query_params.get("category_id")
        exclude_id = request.query_params.get("exclude_id")

        if not raw_name or len(raw_name) < 2:
            return Response([])

        # Normalize: lowercase, collapse whitespace
        normalized = re.sub(r"\s+", " ", raw_name.strip().lower())
        tokens = set(normalized.split())

        qs = Item.objects.filter(is_deleted=False)
        if exclude_id:
            qs = qs.exclude(pk=exclude_id)

        # Annotate a normalized version of the stored name for comparison
        qs = qs.annotate(
            lower_name=Lower("name"),
        )

        # 1. Exact case-insensitive match
        exact = qs.filter(name__iexact=raw_name)
        if category_id:
            exact_cat = exact.filter(category_id=category_id)
        else:
            exact_cat = exact.none()

        # 2. Contains match (substring)
        contains = qs.filter(name__icontains=raw_name).exclude(
            pk__in=exact.values_list("pk", flat=True)
        )

        # 3. Token overlap — fetch candidates that contain ANY of the tokens
        token_q = Q()
        for token in tokens:
            if len(token) >= 2:  # skip very short tokens
                token_q |= Q(name__icontains=token)

        token_candidates = (
            qs.filter(token_q)
            .exclude(pk__in=exact.values_list("pk", flat=True))
            .exclude(pk__in=contains.values_list("pk", flat=True))
        )

        # Score token candidates by overlap ratio
        scored = []
        for item in token_candidates:
            item_tokens = set(item.name.lower().split())
            overlap = len(tokens & item_tokens)
            total = max(len(tokens | item_tokens), 1)
            ratio = overlap / total
            if ratio >= 0.4:  # at least 40% word overlap
                scored.append((item, ratio))
        scored.sort(key=lambda x: -x[1])

        # Build results
        results = []
        seen = set()

        def add(item, match_type):
            if item.pk not in seen:
                seen.add(item.pk)
                results.append({
                    "id": item.pk,
                    "name": item.name,
                    "sku": item.sku,
                    "category": item.category.name if item.category else None,
                    "category_id": item.category_id,
                    "match_type": match_type,
                })

        for item in exact_cat[:5]:
            add(item, "exact_same_category")
        for item in exact.exclude(pk__in=exact_cat.values_list("pk", flat=True))[:5]:
            add(item, "exact")
        for item in contains[:5]:
            add(item, "contains")
        for item, _ in scored[:5]:
            add(item, "similar")

        return Response(results)


class StallViewSet(viewsets.ModelViewSet):
    queryset = Stall.objects.all()

    serializer_class = StallSerializer

    permission_classes = [IsAdminUser]

    # Disable create/update/delete through this viewset — stalls are system-managed.

    http_method_names = ["get", "head", "options"]

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_fields = ["name"]

    search_fields = ["name"]

    ordering_fields = "__all__"

    def get_queryset(self):
        return filter_by_date_range(self.request, super().get_queryset())

    # Explicit handlers to provide a clear message for disallowed methods on stalls
    def create(self, request, *args, **kwargs):
        return Response(
            {
                "detail": "Stalls are system-managed (read-only). Creation is not allowed."
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def update(self, request, *args, **kwargs):
        return Response(
            {
                "detail": "Stalls are system-managed (read-only). Updates are not allowed."
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def partial_update(self, request, *args, **kwargs):
        return Response(
            {
                "detail": "Stalls are system-managed (read-only). Updates are not allowed."
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def destroy(self, request, *args, **kwargs):
        return Response(
            {
                "detail": "Stalls are system-managed (read-only). Deletion is not allowed."
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class StockViewSet(SoftDeleteViewSetMixin, viewsets.ModelViewSet):
    queryset = Stock.objects.select_related(
        'item__category', 'item__stockroom_stock', 'stall'
    ).all()
    permission_classes = [IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = StockFilter
    search_fields = ["stall__name", "item__name"]
    ordering_fields = "__all__"

    def get_serializer_class(self):
        if self.action in ["list", "retrieve"]:
            return StockReadSerializer
        elif self.action in ["partial_update", "update"]:
            return StockPatchSerializer
        elif self.action == "create":
            return StockWriteSerializer
        return StockReadSerializer

    def get_queryset(self):
        queryset = super().get_queryset().filter(
            is_deleted=False,
            item__is_deleted=False,
        )
        # Annotate with available quantity for filtering
        queryset = queryset.annotate(
            available_expr=models.F('quantity') - models.F('reserved_quantity')
        )
        return filter_by_date_range(self.request, queryset)

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        filters_config = {
            "status": {
                "options": get_status_options,
            },
        }

        ordering_config = [
            {"label": "Item Name", "value": "item__name"},
            {"label": "Quantity", "value": "quantity"},
        ]

        return get_role_based_filter_response(request, filters_config, ordering_config)

    @action(detail=False, methods=["get"], url_path="status-counts")
    def status_counts(self, request):
        qs = self.get_queryset()
        no_stock = qs.filter(available_expr__lte=0).count()
        low_stock = qs.filter(
            available_expr__gt=0,
            available_expr__lte=models.F("low_stock_threshold"),
        ).count()
        high_stock = qs.filter(
            available_expr__gt=models.F("low_stock_threshold"),
        ).count()
        return Response({
            "no_stock": no_stock,
            "low_stock": low_stock,
            "high_stock": high_stock,
        })

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    @transaction.atomic
    def restock(self, request, pk=None):
        stock = self.get_object()
        if not user_can_manage_stall(request.user, stock.stall):
            return Response(
                {"detail": "You do not have permission to restock this stall."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = StockRestockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quantity = serializer.validated_data["quantity"]

        try:
            stock_room_stock = StockRoomStock.objects.get(item=stock.item)
        except StockRoomStock.DoesNotExist:
            return Response(
                {"detail": "No stock found in stock room for this item."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if stock_room_stock.quantity < quantity:
            return Response(
                {
                    "detail": f"Not enough stock in stock room. Available: {stock_room_stock.quantity}."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Deduct from stock room
        stock_room_stock.quantity -= quantity
        stock_room_stock.save()

        # Add to stall
        stock.quantity += quantity
        stock.save()

        manager_user = (
            get_user_model()
            .objects.filter(assigned_stall=stock.stall, role__in=["manager", "clerk"], is_active=True)
            .first()
        )

        if manager_user:
            Notification.objects.create(
                user=manager_user,
                type="stock_restocked",
                title="Stock Restocked",
                data={
                    "stall": stock.stall.name,
                    "item": stock.item.name,
                    "item_id": stock.item.id,
                    "stock_id": stock.id,
                    "quantity": float(quantity),
                    "new_total": float(stock.quantity),
                },
                message=f"{quantity} {stock.item.unit_of_measure} of '{stock.item.name}' restocked to {stock.stall.name}.",
            )

        return Response(
            {"detail": f"Restocked successfully. New quantity: {stock.quantity}"}
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    @transaction.atomic
    def add_stock(self, request, pk=None):
        """
        Temporary endpoint to directly add stock to stall without stock room.
        This bypasses the stock room process for quick inventory sync.
        """
        stock = self.get_object()
        
        # Check permissions
        if not (request.user.role == "admin" or user_can_manage_stall(request.user, stock.stall)):
            return Response(
                {"detail": "You do not have permission to add stock to this stall."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = StockRestockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quantity = serializer.validated_data["quantity"]

        # Directly add to stall stock
        stock.quantity += quantity
        stock.save()

        # Notify manager
        manager_user = (
            get_user_model()
            .objects.filter(assigned_stall=stock.stall, role__in=["manager", "clerk"], is_active=True)
            .first()
        )

        if manager_user:
            Notification.objects.create(
                user=manager_user,
                type="stock_restocked",
                title="Stock Added",
                data={
                    "stall": stock.stall.name,
                    "item": stock.item.name,
                    "item_id": stock.item.id,
                    "stock_id": stock.id,
                    "quantity": float(quantity),
                    "new_total": float(stock.quantity),
                },
                message=f"{quantity} {stock.item.unit_of_measure} of '{stock.item.name}' added to {stock.stall.name} (direct add).",
            )

        return Response(
            {
                "detail": f"Stock added successfully. New quantity: {stock.quantity}",
                "quantity": float(stock.quantity),
            }
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated], url_path="pull-out")
    @transaction.atomic
    def pull_out(self, request, pk=None):
        """
        Pull out / remove stock from stall (defective, damaged, etc.).
        Deducts quantity without creating a sales transaction.
        """
        stock = self.get_object()

        if not (request.user.role == "admin" or user_can_manage_stall(request.user, stock.stall)):
            return Response(
                {"detail": "You do not have permission to pull out stock from this stall."},
                status=status.HTTP_403_FORBIDDEN,
            )

        quantity = request.data.get("quantity")
        reason = request.data.get("reason", "")

        if quantity is None:
            return Response(
                {"detail": "Quantity is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            quantity = float(quantity)
        except (TypeError, ValueError):
            return Response(
                {"detail": "Quantity must be a number."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if quantity <= 0:
            return Response(
                {"detail": "Quantity must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if stock.available_quantity < quantity:
            return Response(
                {"detail": f"Not enough available stock. Available: {stock.available_quantity}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_quantity = stock.quantity
        stock.quantity -= quantity
        stock.save()

        return Response({
            "detail": f"Pulled out {quantity} {stock.item.unit_of_measure} of '{stock.item.name}' from {stock.stall.name}.",
            "item_name": stock.item.name,
            "quantity_removed": float(quantity),
            "old_quantity": float(old_quantity),
            "new_quantity": float(stock.quantity),
            "reason": reason,
        })

    @action(detail=True, methods=["get", "post"], permission_classes=[IsAdminUser], url_path="audit")
    @transaction.atomic
    def audit(self, request, pk=None):
        """
        Stock audit/reconciliation tool (admin only).
        
        GET: Returns the current stock breakdown and active reservations.
        POST: Accepts physical_count and adjusts system quantity to match,
              preserving reserved_quantity.
        """
        from services.models import ApplianceItemUsed, Service

        stock = self.get_object()

        # Gather active services that have reserved items from this stock
        active_statuses = ["pending", "in_progress", "on_hold"]
        reserved_items = (
            ApplianceItemUsed.objects.filter(
                stall_stock=stock,
                is_cancelled=False,
                appliance__service__status__in=active_statuses,
            )
            .select_related(
                "appliance__service__client",
                "item",
            )
            .order_by("-appliance__service__created_at")
        )

        reservations = []
        for aiu in reserved_items:
            service = aiu.appliance.service
            reservations.append({
                "service_id": service.id,
                "client_name": str(service.client) if service.client else "N/A",
                "service_type": service.service_type,
                "service_status": service.status,
                "item_name": aiu.item.name if aiu.item else "N/A",
                "quantity_used": float(aiu.quantity),
                "created_at": service.created_at.isoformat(),
            })

        breakdown = {
            "stock_id": stock.id,
            "item_name": stock.item.name,
            "item_unit": stock.item.unit_of_measure,
            "stall_name": stock.stall.name if stock.stall else "N/A",
            "system_quantity": float(stock.quantity),
            "reserved_quantity": float(stock.reserved_quantity),
            "available_quantity": float(stock.available_quantity),
            "reservations": reservations,
        }

        if request.method == "GET":
            return Response(breakdown)

        # POST - reconcile
        serializer = StockAuditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        physical_count = serializer.validated_data["physical_count"]

        old_quantity = stock.quantity
        # The physical count represents the TOTAL items physically present,
        # which includes items reserved for active services.
        # So system quantity should be set to the physical count.
        stock.quantity = physical_count

        # Ensure reserved_quantity doesn't exceed new quantity
        if stock.reserved_quantity > stock.quantity:
            stock.reserved_quantity = stock.quantity

        stock.save(update_fields=["quantity", "reserved_quantity", "updated_at"])

        discrepancy = float(physical_count) - float(old_quantity)

        return Response({
            **breakdown,
            "system_quantity": float(stock.quantity),
            "reserved_quantity": float(stock.reserved_quantity),
            "available_quantity": float(stock.available_quantity),
            "physical_count": float(physical_count),
            "old_quantity": float(old_quantity),
            "discrepancy": discrepancy,
            "adjusted": True,
        })


class StockRoomStockViewSet(SoftDeleteViewSetMixin, viewsets.ModelViewSet):
    queryset = StockRoomStock.objects.select_related('item__category').all()
    serializer_class = StockRoomStockSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = StockRoomFilter
    search_fields = ["item__name"]
    ordering_fields = "__all__"

    def get_queryset(self):
        qs = super().get_queryset().filter(
            is_deleted=False,
            item__is_deleted=False,
        )
        return filter_by_date_range(self.request, qs)

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        filters_config = {
            "category": {
                "options": get_product_category_options,
            },
            "status": {
                "options": get_status_options,
            },
        }

        ordering_config = [
            {"label": "Item Name", "value": "item__name"},
            {"label": "Quantity", "value": "quantity"},
            {"label": "Last Updated", "value": "updated_at"},
        ]

        return get_role_based_filter_response(request, filters_config, ordering_config)

    @action(detail=False, methods=["get"], url_path="status-counts")
    def status_counts(self, request):
        qs = self.get_queryset()
        no_stock = qs.filter(quantity=0).count()
        low_stock = qs.filter(
            quantity__gt=0,
            quantity__lte=models.F("low_stock_threshold"),
        ).count()
        high_stock = qs.filter(
            quantity__gt=models.F("low_stock_threshold"),
        ).count()
        return Response({
            "no_stock": no_stock,
            "low_stock": low_stock,
            "high_stock": high_stock,
        })

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    @transaction.atomic
    def restock(self, request, pk=None):
        stock_room_stock = self.get_object()

        serializer = StockRestockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quantity = serializer.validated_data["quantity"]

        stock_room_stock.quantity += quantity
        stock_room_stock.save()

        return Response(
            {
                "detail": f"Stock room restocked successfully. New quantity: {stock_room_stock.quantity}."
            }
        )

    @action(detail=True, methods=["get", "post"], permission_classes=[IsAdminUser], url_path="audit")
    @transaction.atomic
    def audit(self, request, pk=None):
        """
        Stock room audit/reconciliation tool (admin only).

        GET: Returns the current stock breakdown.
        POST: Accepts physical_count and adjusts system quantity to match.
        """
        stock = self.get_object()

        breakdown = {
            "stock_id": stock.id,
            "item_name": stock.item.name,
            "item_unit": stock.item.unit_of_measure,
            "system_quantity": float(stock.quantity),
        }

        if request.method == "GET":
            return Response(breakdown)

        # POST - reconcile
        serializer = StockAuditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        physical_count = serializer.validated_data["physical_count"]

        old_quantity = stock.quantity
        stock.quantity = physical_count
        stock.save(update_fields=["quantity", "updated_at"])

        discrepancy = float(physical_count) - float(old_quantity)

        return Response({
            **breakdown,
            "system_quantity": float(stock.quantity),
            "physical_count": float(physical_count),
            "old_quantity": float(old_quantity),
            "discrepancy": discrepancy,
            "adjusted": True,
        })


class ProductCategoryViewSet(SoftDeleteViewSetMixin, viewsets.ModelViewSet):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["name"]
    search_fields = ["name"]
    ordering_fields = "__all__"

    def get_queryset(self):
        qs = super().get_queryset().filter(is_deleted=False)
        return filter_by_date_range(self.request, qs)


class StockRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for managing stock requests.

    Clerks create stock requests implicitly when adding items with insufficient
    stock. Admins can list, approve, decline, or batch-approve requests.
    """

    queryset = StockRequest.objects.select_related(
        "item", "stall", "service", "requested_by", "approved_by",
        "appliance_item", "service_item",
    ).all()
    serializer_class = StockRequestSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["status", "source"]
    search_fields = ["item__name", "item__sku", "notes"]
    ordering_fields = ["created_at", "requested_quantity", "status"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role != "admin":
            qs = qs.filter(requested_by=self.request.user)
        return qs

    @action(detail=False, methods=["get"], url_path="pending-count")
    def pending_count(self, request):
        count = self.get_queryset().filter(status="pending").count()
        return Response({"count": count})

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    @transaction.atomic
    def approve(self, request, pk=None):
        """Approve a stock request: add stock and reserve for the service item."""
        from services.business_logic import StockReservationManager
        from django.db import transaction as db_transaction

        with db_transaction.atomic():
            # Lock the stock request row to prevent double-approval
            stock_request = StockRequest.objects.select_for_update().get(pk=pk)

            if stock_request.status != "pending":
                return Response(
                    {"detail": f"Cannot approve a request with status '{stock_request.status}'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            stock_record, _ = Stock.objects.get_or_create(
                item=stock_request.item,
                stall=stock_request.stall,
                is_deleted=False,
                defaults={"quantity": 0, "reserved_quantity": 0},
            )
            stock_record = Stock.objects.select_for_update().get(pk=stock_record.pk)
            stock_record.quantity += stock_request.requested_quantity
            stock_record.save(update_fields=["quantity", "updated_at"])

            item_usage = stock_request.appliance_item or stock_request.service_item
            if item_usage and item_usage.item:
                try:
                    StockReservationManager.reserve_stock(
                        item=item_usage.item,
                        quantity=item_usage.quantity,
                        stall_stock=stock_record,
                    )
                    if not item_usage.stall_stock_id:
                        item_usage.stall_stock = stock_record
                    item_usage.stock_request_status = "approved"
                    item_usage.save(update_fields=["stall_stock", "stock_request_status"])
                except Exception:
                    if item_usage.stock_request_status == "pending":
                        item_usage.stock_request_status = "approved"
                        item_usage.save(update_fields=["stock_request_status"])

            stock_request.status = "approved"
            stock_request.approved_by = request.user
            stock_request.approved_at = timezone.now()
            stock_request.save(update_fields=[
                "status", "approved_by", "approved_at", "updated_at",
            ])

            if stock_request.requested_by and stock_request.requested_by.is_active:
                Notification.objects.create(
                    user=stock_request.requested_by,
                    type="stock_request_approved",
                    title="Stock Request Approved",
                    message=(
                        f"Your stock request for {stock_request.requested_quantity} "
                        f"{stock_request.item.unit_of_measure} of '{stock_request.item.name}' "
                        f"has been approved."
                    ),
                    data={
                        "stock_request_id": stock_request.id,
                        "item_name": stock_request.item.name,
                        "quantity": float(stock_request.requested_quantity),
                        "service_id": stock_request.service_id,
                    },
                )

        return Response(StockRequestSerializer(stock_request).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    @transaction.atomic
    def decline(self, request, pk=None):
        """Decline a stock request."""
        stock_request = self.get_object()

        if stock_request.status != "pending":
            return Response(
                {"detail": f"Cannot decline a request with status '{stock_request.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        decline_reason = request.data.get("reason", "")

        item_usage = stock_request.appliance_item or stock_request.service_item
        if item_usage:
            item_usage.stock_request_status = "declined"
            item_usage.save(update_fields=["stock_request_status"])

        stock_request.status = "declined"
        stock_request.decline_reason = decline_reason
        stock_request.declined_at = timezone.now()
        stock_request.save(update_fields=[
            "status", "decline_reason", "declined_at", "updated_at",
        ])

        if stock_request.requested_by and stock_request.requested_by.is_active:
            msg = (
                f"Your stock request for {stock_request.requested_quantity} "
                f"{stock_request.item.unit_of_measure} of '{stock_request.item.name}' "
                f"has been declined."
            )
            if decline_reason:
                msg += f" Reason: {decline_reason}"

            Notification.objects.create(
                user=stock_request.requested_by,
                type="stock_request_declined",
                title="Stock Request Declined",
                message=msg,
                data={
                    "stock_request_id": stock_request.id,
                    "item_name": stock_request.item.name,
                    "service_id": stock_request.service_id,
                },
            )

        return Response(StockRequestSerializer(stock_request).data)

    @action(detail=False, methods=["post"], permission_classes=[IsAdminUser], url_path="batch-approve")
    @transaction.atomic
    def batch_approve(self, request):
        """Approve multiple stock requests at once."""
        from services.business_logic import StockReservationManager

        ids = request.data.get("ids", [])
        if not ids:
            return Response(
                {"detail": "No request IDs provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        requests_qs = StockRequest.objects.select_for_update().filter(
            id__in=ids, status="pending"
        ).select_related("item", "stall", "appliance_item", "service_item", "requested_by")

        approved_count = 0
        for sr in requests_qs:
            stock_record, _ = Stock.objects.get_or_create(
                item=sr.item, stall=sr.stall, is_deleted=False,
                defaults={"quantity": 0, "reserved_quantity": 0},
            )
            stock_record = Stock.objects.select_for_update().get(pk=stock_record.pk)
            stock_record.quantity += sr.requested_quantity
            stock_record.save(update_fields=["quantity", "updated_at"])

            item_usage = sr.appliance_item or sr.service_item
            if item_usage and item_usage.item:
                try:
                    StockReservationManager.reserve_stock(
                        item=item_usage.item,
                        quantity=item_usage.quantity,
                        stall_stock=stock_record,
                    )
                    if not item_usage.stall_stock_id:
                        item_usage.stall_stock = stock_record
                    item_usage.stock_request_status = "approved"
                    item_usage.save(update_fields=["stall_stock", "stock_request_status"])
                except Exception:
                    if item_usage.stock_request_status == "pending":
                        item_usage.stock_request_status = "approved"
                        item_usage.save(update_fields=["stock_request_status"])

            sr.status = "approved"
            sr.approved_by = request.user
            sr.approved_at = timezone.now()
            sr.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
            approved_count += 1

            if sr.requested_by and sr.requested_by.is_active:
                Notification.objects.create(
                    user=sr.requested_by,
                    type="stock_request_approved",
                    title="Stock Request Approved",
                    message=(
                        f"Your stock request for {sr.requested_quantity} "
                        f"{sr.item.unit_of_measure} of '{sr.item.name}' "
                        f"has been approved."
                    ),
                    data={
                        "stock_request_id": sr.id,
                        "item_name": sr.item.name,
                        "quantity": float(sr.requested_quantity),
                        "service_id": sr.service_id,
                    },
                )

        return Response({"approved_count": approved_count})
