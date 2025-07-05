from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status, filters, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

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
from utils.inventory import user_can_manage_stall

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
        elif user.role == "manager" and user.assigned_stall:
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
            {"detail": "Deleted successfully."}, status=status.HTTP_204_NO_CONTENT
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
    serializer_class = StockRoomStockSerializer
    permission_classes = [permissions.IsAuthenticated]


# ---------------------------
# STOCK TRANSFERS
# ---------------------------


class StockTransferCreateView(generics.CreateAPIView):
    queryset = StockTransfer.objects.all()
    serializer_class = StockTransferSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        transfer = serializer.save(transferred_by=self.request.user)
        log_activity(
            self.request.user,
            f"Created transfer ID {transfer.id} from '{transfer.from_stall or 'Stock Room'}' to '{transfer.to_stall}'",
        )


class StockTransferListRelatedToMyStallView(generics.ListAPIView):
    serializer_class = StockTransferSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == "admin":
            return StockTransfer.objects.all()
        elif user.role == "manager" and user.assigned_stall:
            return StockTransfer.objects.filter(to_stall=user.assigned_stall)
        return StockTransfer.objects.none()


# ---------------------------
# STOCK ADJUST / RESTOCK
# ---------------------------


class StockRestockAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, stock_id):
        stock = get_object_or_404(Stock, pk=stock_id)
        if not user_can_manage_stall(request.user, stock.stall):
            return Response(
                {"detail": "You do not have permission to restock this stall."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = StockRestockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quantity = serializer.validated_data["quantity"]

        original_quantity = stock.quantity
        stock.quantity += quantity
        stock.save()

        log_activity(
            request.user,
            stock,
            "restock",
            f"Restocked '{stock.item.name}' at '{stock.stall.name}' from {original_quantity} to {stock.quantity}.",
        )

        return Response(
            {"detail": f"Restocked successfully. New quantity: {stock.quantity}"}
        )


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

        return Response({"detail": log_msg})


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


class ProductCategoryChoicesAPIView(generics.ListAPIView):
    queryset = ProductCategory.objects.filter(is_deleted=False)
    serializer_class = ProductCategorySerializer
    pagination_class = None
    permission_classes = [permissions.IsAuthenticated]
