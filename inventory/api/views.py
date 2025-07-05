from django.db import transaction
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
    StockTransferItemSerializer,
    StockRestockSerializer,
)
from utils.mixins import LogCreateMixin, LogSoftDeleteMixin, LogUpdateMixin
from utils.logger import log_activity
from utils.inventory import user_can_manage_stall
from django.shortcuts import get_object_or_404


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
    filter_backends = None

    def filter_queryset(self, queryset):
        return queryset


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
    queryset = Stock.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
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
        queryset = super().get_queryset()
        user = self.request.user
        if user.role == "admin":
            return queryset
        elif user.role == "manager" and user.assigned_stall:
            return queryset.filter(stall=user.assigned_stall)
        return queryset.none()


class StockDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Stock.objects.all()
    lookup_field = "pk"
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = None

    def get_serializer_class(self):
        return (
            StockPatchSerializer
            if self.request.method in ["PUT", "PATCH"]
            else StockReadSerializer
        )

    def filter_queryset(self, queryset):
        return queryset

    def delete(self, request, *args, **kwargs):
        stock = self.get_object()
        stock.is_deleted = True
        stock.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------
# STOCK ROOM CRUD
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
    lookup_field = "pk"
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
        user_stall_ids = Stall.objects.all().values_list("id", flat=True)
        return StockTransfer.objects.filter(to_stall_id__in=user_stall_ids)


# ---------------------------
# ADJUST STOCK QUANTITY
# ---------------------------
class StockRestockAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, stall_id, stock_id):
        stock = get_object_or_404(Stock, pk=stock_id, stall_id=stall_id)
        stall = stock.stall

        # Check permissions based on user role and assigned stall
        if not user_can_manage_stall(request.user, stall):
            return Response(
                {"detail": "You do not have permission to restock this stall."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Proceed with restocking
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
            f"Restocked '{stock.item.name}' at '{stock.stall.name}' "
            f"from {original_quantity} to {stock.quantity}.",
        )

        return Response(
            {"detail": f"Restocked successfully. New quantity: {stock.quantity}"},
            status=status.HTTP_200_OK,
        )


class StockAdjustAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
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

        return Response({"detail": log_msg}, status=status.HTTP_200_OK)


# ---------------------------
# SIMPLE CHOICES FOR FORMS (no pagination)
# ---------------------------


class ItemChoicesAPIView(generics.ListAPIView):
    queryset = Item.objects.filter(is_deleted=False)
    serializer_class = ItemSerializer
    pagination_class = None
    permission_classes = [permissions.IsAuthenticated]

    def filter_queryset(self, queryset):
        return queryset


class StallChoicesAPIView(generics.ListAPIView):
    queryset = Stall.objects.filter(is_deleted=False)
    serializer_class = StallSerializer
    pagination_class = None
    permission_classes = [permissions.IsAuthenticated]

    def filter_queryset(self, queryset):
        return queryset


class ProductCategoryChoicesAPIView(generics.ListAPIView):
    queryset = ProductCategory.objects.filter(is_deleted=False)
    serializer_class = ProductCategorySerializer
    pagination_class = None
    permission_classes = [permissions.IsAuthenticated]

    def filter_queryset(self, queryset):
        return queryset
