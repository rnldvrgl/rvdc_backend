from django.contrib.auth import get_user_model
from django.db import models, transaction
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
    StockRestockSerializer,
    StockRoomStockSerializer,
    StockWriteSerializer,
)
from inventory.models import (
    Item,
    ProductCategory,
    Stall,
    Stock,
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
    queryset = Item.objects.select_related('category').all()
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
        queryset = super().get_queryset().filter(is_deleted=False)
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
            .objects.filter(assigned_stall=stock.stall, role__in=["manager", "clerk"])
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
            .objects.filter(assigned_stall=stock.stall, role__in=["manager", "clerk"])
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
        qs = super().get_queryset().filter(is_deleted=False)
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
