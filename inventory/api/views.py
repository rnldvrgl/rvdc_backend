from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status, filters, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone

from expenses.models import Expense
from inventory.models import (
    Stock,
    StockRoomStock,
    StockTransfer,
    Stall,
    Item,
    ProductCategory,
)
from inventory.api.serializers import (
    StockReadSerializer,
    StockWriteSerializer,
    StockPatchSerializer,
    StockRoomStockSerializer,
    StockTransferSerializer,
    StockAdjustSerializer,
    ItemSerializer,
    StallSerializer,
    ProductCategorySerializer,
    StockRestockSerializer,
)
from utils.mixins import LogCreateMixin, LogSoftDeleteMixin, LogUpdateMixin
from utils.logger import log_activity
from utils.inventory import user_can_manage_stall, record_stock_movement

# ---------------------------
# PRODUCT CATEGORY
# ---------------------------


class ProductCategoryListCreateView(generics.ListCreateAPIView):
    queryset = ProductCategory.objects.filter(is_deleted=False)
    serializer_class = ProductCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["name"]
    search_fields = ["name"]
    ordering_fields = ["name"]
    ordering = ["name"]


class ProductCategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = ProductCategory.objects.filter(is_deleted=False)
    serializer_class = ProductCategorySerializer
    permission_classes = [permissions.IsAuthenticated]


# ---------------------------
# ITEM CRUD
# ---------------------------


class ItemListCreateView(LogCreateMixin, generics.ListCreateAPIView):
    queryset = Item.objects.filter(is_deleted=False)
    serializer_class = ItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["name", "sku", "category__name"]
    search_fields = ["name", "sku", "category__name"]
    ordering_fields = ["name", "sku"]
    ordering = ["name"]


class ItemDetailView(
    LogUpdateMixin, LogSoftDeleteMixin, generics.RetrieveUpdateDestroyAPIView
):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer
    permission_classes = [permissions.IsAuthenticated]


# ---------------------------
# STALL CRUD
# ---------------------------


class StallListCreateView(LogCreateMixin, generics.ListCreateAPIView):
    queryset = Stall.objects.filter(is_deleted=False)
    serializer_class = StallSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["name", "location"]
    search_fields = ["name", "location"]
    ordering_fields = ["name", "location"]
    ordering = ["name"]


class StallDetailView(
    LogUpdateMixin, LogSoftDeleteMixin, generics.RetrieveUpdateDestroyAPIView
):
    queryset = Stall.objects.all()
    serializer_class = StallSerializer
    permission_classes = [permissions.IsAuthenticated]


# ---------------------------
# STOCK CRUD
# ---------------------------


class StockListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["stall", "item"]  # allows ?stall=ID or ?item=ID
    search_fields = ["item__name", "stall__name", "item__sku"]
    ordering_fields = ["quantity", "updated_at"]
    ordering = ["-updated_at"]

    def get_serializer_class(self):
        return (
            StockWriteSerializer
            if self.request.method == "POST"
            else StockReadSerializer
        )

    def get_queryset(self):
        queryset = Stock.objects.all()
        user = self.request.user
        if user.role == "admin":
            return queryset
        elif user.role == ("manager", "clerk") and user.assigned_stall:
            return queryset.filter(stall=user.assigned_stall)
        return queryset.none()


class StockDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Stock.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        return (
            StockPatchSerializer
            if self.request.method in ["PUT", "PATCH"]
            else StockReadSerializer
        )

    def delete(self, request, *args, **kwargs):
        stock = self.get_object()
        stock.is_deleted = True
        stock.save()
        return Response(
            {"non_field_errors": "Deleted successfully."},
            status=status.HTTP_204_NO_CONTENT,
        )


# ---------------------------
# STOCK ROOM
# ---------------------------


class StockRoomStockListCreateView(generics.ListCreateAPIView):
    queryset = StockRoomStock.objects.all()
    serializer_class = StockRoomStockSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["item__name"]
    ordering_fields = ["quantity", "updated_at"]
    ordering = ["-updated_at"]


class StockRoomStockDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = StockRoomStock.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        return (
            StockPatchSerializer
            if self.request.method in ["PUT", "PATCH"]
            else StockRoomStockSerializer
        )


# ---------------------------
# STOCK TRANSFERS
# ---------------------------


class StockTransferMarkExpensePaidView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        # Fetch the expense tied to this transfer
        expense = Expense.objects.filter(transfer_id=pk).first()
        if not expense:
            return Response(
                {"detail": "Expense not found for this transfer."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Mark as paid
        expense.paid_amount = expense.total_price
        expense.paid_at = timezone.now()
        expense.is_paid = True
        expense.save()

        return Response({"detail": "Expense marked as paid."})


class StockTransferCreateView(generics.CreateAPIView):
    queryset = StockTransfer.objects.all()
    serializer_class = StockTransferSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        transfer = serializer.save(transferred_by=self.request.user)
        log_activity(
            self.request.user,
            transfer,
            "Created Stock Transfer",
            f"Created transfer ID {transfer.id} from '{transfer.from_stall or 'Stock Room'}' to '{transfer.to_stall}'",
        )


class StockTransferDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = StockTransfer.objects.all()
    serializer_class = StockTransferSerializer
    permission_classes = [permissions.IsAuthenticated]


class StockTransferFinalizeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        transfer = get_object_or_404(StockTransfer, pk=pk)

        if transfer.is_finalized:
            return Response(
                {"detail": "Already finalized."}, status=status.HTTP_400_BAD_REQUEST
            )

        transfer.finalize(user=request.user)
        return Response({"detail": "Transfer finalized successfully."})


class StockTransferListRelatedToMyStallView(generics.ListAPIView):
    serializer_class = StockTransferSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["to_stall"]
    search_fields = ["to_stall__name"]

    def get_queryset(self):
        user = self.request.user
        if user.role == "admin":
            return StockTransfer.objects.all()
        elif user.role == ("manager", "clerk") and user.assigned_stall:
            return StockTransfer.objects.filter(from_stall=user.assigned_stall)
        return StockTransfer.objects.none()


# ---------------------------
# STOCK ADJUST / RESTOCK
# ---------------------------
class StockRoomRestockAPIView(APIView):
    permission_classes = [permissions.IsAdminUser]

    @transaction.atomic
    def post(self, request, stock_id):
        # Get stock room stock object
        stock_room_stock = get_object_or_404(StockRoomStock, pk=stock_id)

        # Validate data
        serializer = StockRestockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quantity = serializer.validated_data["quantity"]

        # Increase stock room quantity
        original_quantity = stock_room_stock.quantity
        stock_room_stock.quantity += quantity
        stock_room_stock.save()

        # Record stock movement
        record_stock_movement(
            item=stock_room_stock.item,
            stall=None,  # None indicates stock room
            qty=quantity,
            source="restock_stock_room",
        )

        # Log activity
        log_activity(
            request.user,
            stock_room_stock,
            "restock_stock_room",
            f"Restocked stock room for '{stock_room_stock.item.name}' "
            f"from {original_quantity} to {stock_room_stock.quantity}.",
        )

        return Response(
            {
                "non_field_errors": [
                    f"Stock room restocked successfully. New quantity: {stock_room_stock.quantity}."
                ]
            }
        )


class StockRestockAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, stock_id):
        stock = get_object_or_404(Stock, pk=stock_id)
        if not user_can_manage_stall(request.user, stock.stall):
            return Response(
                {
                    "non_field_errors": [
                        "You do not have permission to restock this stall."
                    ]
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = StockRestockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quantity = serializer.validated_data["quantity"]

        # Get stock room stock for the item
        try:
            stock_room_stock = StockRoomStock.objects.get(item=stock.item)
        except StockRoomStock.DoesNotExist:
            return Response(
                {"non_field_errors": ["No stock found in stock room for this item."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if enough in stock room
        if stock_room_stock.quantity < quantity:
            return Response(
                {
                    "non_field_errors": [
                        f"Not enough stock in stock room. Available: {stock_room_stock.quantity}."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Deduct from stock room
        stock_room_stock.quantity -= quantity
        stock_room_stock.save()

        # Add to stall stock
        original_quantity = stock.quantity
        stock.quantity += quantity
        stock.save()

        # Record stock movements
        record_stock_movement(
            item=stock.item,
            stall=None,  # stock room
            qty=-quantity,
            source="restock_to_stall",
        )
        record_stock_movement(
            item=stock.item,
            stall=stock.stall,
            qty=quantity,
            source="restock_from_stock_room",
        )

        # Log activity
        log_activity(
            request.user,
            stock,
            "restock",
            f"Restocked '{stock.item.name}' at '{stock.stall.name}' from {original_quantity} to {stock.quantity}.",
        )

        return Response(
            {
                "non_field_errors": [
                    f"Restocked successfully. New quantity: {stock.quantity}"
                ]
            }
        )


# TODO: ADD ADJUSTING OF STOCK (ADMIN)
class StockAdjustAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = StockAdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        stock = data["stock"]
        original_quantity = stock.quantity

        if data["action"] == "increase":
            stock.quantity += data["quantity"]
            log_msg = f"Increased '{stock.item.name}' at '{stock.stall.name}' from {original_quantity} to {stock.quantity}."
        else:
            stock.quantity = max(stock.quantity - data["quantity"], 0)
            log_msg = f"Decreased '{stock.item.name}' at '{stock.stall.name}' from {original_quantity} to {stock.quantity}."

        stock.save()
        log_activity(request.user, log_msg)

        return Response({"non_field_errors": [log_msg]})


# ---------------------------
# SIMPLE CHOICES
# ---------------------------


class ItemChoicesAPIView(generics.ListAPIView):
    queryset = Item.objects.filter(is_deleted=False)
    serializer_class = ItemSerializer
    pagination_class = None
    permission_classes = [permissions.IsAuthenticated]


class StallChoicesAPIView(generics.ListAPIView):
    queryset = Stall.objects.filter(is_deleted=False)
    serializer_class = StallSerializer
    pagination_class = None
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        exclude_id = self.request.query_params.get("exclude")
        if exclude_id:
            qs = qs.exclude(id=exclude_id)
        return qs


class ProductCategoryChoicesAPIView(generics.ListAPIView):
    queryset = ProductCategory.objects.filter(is_deleted=False)
    serializer_class = ProductCategorySerializer
    pagination_class = None
    permission_classes = [permissions.IsAuthenticated]
