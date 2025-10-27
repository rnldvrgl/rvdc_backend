from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from django.db import transaction
from notifications.models import Notification
from django.contrib.auth import get_user_model
from inventory.api.filters import (
    ItemFilter,
    StockFilter,
    StockRoomFilter,
    StockTransferFilter,
)

from inventory.models import (
    Item,
    Stall,
    Stock,
    StockRoomStock,
    ProductCategory,
    StockTransfer,
)
from inventory.api.serializers import (
    ItemSerializer,
    StallSerializer,
    StockRoomStockSerializer,
    ProductCategorySerializer,
    StockTransferSerializer,
    StockRestockSerializer,
    StockReadSerializer,
    StockWriteSerializer,
    StockPatchSerializer,
)

from utils.filters.role_filters import get_role_based_filter_response
from utils.filters.options import (
    get_status_options,
    get_unit_of_measure_options,
    get_stall_options,
    get_product_category_options,
    get_user_options,
)

from utils.query import filter_by_date_range, get_transfer_role_filtered_queryset
from utils.inventory import (
    user_can_manage_stall,
)
from django_filters.rest_framework import DjangoFilterBackend
from utils.query import get_role_filtered_queryset
from rest_framework.exceptions import ValidationError
from django.utils import timezone


class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all()
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
        return filter_by_date_range(self.request, super().get_queryset())

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


class StockViewSet(viewsets.ModelViewSet):
    queryset = Stock.objects.all()
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
        return get_role_filtered_queryset(self.request, super().get_queryset())

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        filters_config = {
            "stall": {
                "options": get_stall_options,
                "exclude_for": ["clerk", "manager"],
            },
            "status": {
                "options": get_status_options,
            },
            "track_stock": {
                "options": lambda: [
                    {"label": "Yes", "value": "true"},
                    {"label": "No", "value": "false"},
                ],
            },
        }

        ordering_config = [
            {"label": "Item Name", "value": "item__name"},
            {"label": "Quantity", "value": "quantity"},
        ]

        return get_role_based_filter_response(request, filters_config, ordering_config)

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
                type="restock",
                data={
                    "stall": stock.stall.name,
                    "item": stock.item.name,
                    "item_id": stock.item.id,
                    "stock_id": stock.id,
                    "quantity": quantity,
                    "new_total": stock.quantity,
                },
                message=f"{quantity} {stock.item.unit_of_measure} of '{stock.item.name}' restocked to {stock.stall.name}.",
            )

        return Response(
            {"detail": f"Restocked successfully. New quantity: {stock.quantity}"}
        )


class StockRoomStockViewSet(viewsets.ModelViewSet):
    queryset = StockRoomStock.objects.all()
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
        return filter_by_date_range(self.request, super().get_queryset())

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


class ProductCategoryViewSet(viewsets.ModelViewSet):
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
        return filter_by_date_range(self.request, super().get_queryset())


class StockTransferViewSet(viewsets.ModelViewSet):
    queryset = StockTransfer.objects.all()
    serializer_class = StockTransferSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = StockTransferFilter
    search_fields = ["from_stall__name", "to_stall__name"]

    def get_queryset(self):
        return get_transfer_role_filtered_queryset(
            self.request, super().get_queryset(), "transfer_date"
        )

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        filters_config = {
            "technician": {
                "options": lambda: get_user_options(include_roles=["technician"])
            },
            "is_finalized": {
                "options": lambda: [
                    {"label": "Finalized", "value": "true"},
                    {"label": "Not Finalized", "value": "false"},
                ],
            },
            "is_paid": {
                "options": lambda: [
                    {"label": "Paid", "value": "true"},
                    {"label": "Unpaid", "value": "false"},
                ],
            },
        }

        ordering_config = [
            {"label": "Transfer Date", "value": "transfer_date"},
            {"label": "From Stall", "value": "from_stall__name"},
            {"label": "To Stall", "value": "to_stall__name"},
        ]

        return get_role_based_filter_response(request, filters_config, ordering_config)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    @transaction.atomic
    def finalize(self, request, pk=None):
        transfer = self.get_object()
        if not transfer.can_be_finalized_by(request.user):
            return Response(
                {"detail": "You do not have permission to finalize this transfer."},
                status=status.HTTP_403_FORBIDDEN,
            )
        transfer.finalize(request.user)
        return Response({"detail": "Stock transfer finalized."})

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated],
        url_path="mark-expense-as-paid",
    )
    @transaction.atomic
    def mark_expense_as_paid(self, request, pk=None):
        stock_transfer = self.get_object()

        if not hasattr(stock_transfer, "expense") or stock_transfer.expense is None:
            raise ValidationError("This stock transfer has no linked expense.")

        stock_transfer.expense.is_paid = True
        stock_transfer.expense.paid_at = timezone.now()
        stock_transfer.expense.save()

        return Response({"detail": "Expense marked as paid."})
