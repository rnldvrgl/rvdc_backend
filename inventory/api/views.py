from django.db import transaction
from rest_framework import generics, status, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from inventory.models import Stock, StockRoomStock, StockTransfer, Stall, Item
from inventory.api.serializers import (
    StockReadSerializer,
    StockWriteSerializer,
    StockPatchSerializer,
    StockRoomStockSerializer,
    StockTransferSerializer,
    StockAdjustSerializer,
    ItemSerializer,
    StallSerializer,
)
from utils.mixins import LogCreateMixin, LogSoftDeleteMixin, LogUpdateMixin
from utils.logger import log_activity
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions
from inventory.models import ProductCategory
from inventory.api.serializers import ProductCategorySerializer


class ProductCategoryListCreateView(generics.ListCreateAPIView):
    queryset = ProductCategory.objects.filter(is_deleted=False)
    serializer_class = ProductCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["name"]
    search_fields = ["name"]


class ProductCategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = None

    def filter_queryset(self, queryset):
        return queryset


class ItemListCreateView(LogCreateMixin, generics.ListCreateAPIView):
    queryset = Item.objects.filter(is_deleted=False)
    serializer_class = ItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["name", "sku", "category__name"]
    search_fields = ["name", "sku", "category__name"]


class ItemDetailView(
    LogUpdateMixin, LogSoftDeleteMixin, generics.RetrieveUpdateDestroyAPIView
):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["name", "sku", "category__name"]
    search_fields = ["name", "sku", "category__name"]


class StallListCreateView(LogCreateMixin, generics.ListCreateAPIView):
    queryset = Stall.objects.filter(is_deleted=False)
    serializer_class = StallSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["name", "location"]
    search_fields = ["name", "location"]


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
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["item__name", "stall__name", "item__sku"]
    ordering_fields = ["quantity", "updated_at"]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return StockWriteSerializer
        return StockReadSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role == "admin":
            return qs  # see all
        elif user.role == "manager":
            # show only stocks for manager's assigned stall
            if user.assigned_stall:
                return qs.filter(stall=user.assigned_stall)
            else:
                return qs.none()
        else:
            return qs.none()


class StockDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Stock.objects.all()
    lookup_field = "pk"

    def get_serializer_class(self):
        if self.request.method in ["PUT", "PATCH"]:
            return StockPatchSerializer
        return StockReadSerializer


# ---------------------------
# STOCK ROOM CRUD
# ---------------------------


class StockRoomStockListCreateView(generics.ListCreateAPIView):
    queryset = StockRoomStock.objects.all()
    serializer_class = StockRoomStockSerializer


class StockRoomStockDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = StockRoomStock.objects.all()
    serializer_class = StockRoomStockSerializer
    lookup_field = "pk"


# ---------------------------
# STOCK TRANSFERS
# ---------------------------


class StockTransferCreateView(generics.CreateAPIView):
    queryset = StockTransfer.objects.all()
    serializer_class = StockTransferSerializer

    def perform_create(self, serializer):
        transfer = serializer.save(transferred_by=self.request.user)
        log_activity(
            self.request.user,
            f"Created transfer ID {transfer.id} from '{transfer.from_stall or 'Stock Room'}' to '{transfer.to_stall}'",
        )


class StockTransferListRelatedToMyStallView(generics.ListAPIView):
    serializer_class = StockTransferSerializer

    def get_queryset(self):
        user_stall_ids = Stall.objects.filter().values_list("id", flat=True)
        return StockTransfer.objects.filter(to_stall_id__in=user_stall_ids)


# ---------------------------
# ADJUST STOCK QUANTITY
# ---------------------------


class StockAdjustAPIView(APIView):
    """
    POST endpoint to adjust stock quantity at a stall.

    {
        "stock": 1,
        "quantity": 10,
        "action": "increase"
    }
    """

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
# SIMPLE CHOICES FOR FORMS
# ---------------------------


class ItemChoicesAPIView(generics.ListAPIView):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer
    pagination_class = None

    def filter_queryset(self, queryset):
        return queryset


class StallChoicesAPIView(generics.ListAPIView):
    queryset = Stall.objects.all()
    serializer_class = StallSerializer
    pagination_class = None

    def filter_queryset(self, queryset):
        return queryset


class ProductCategoryChoicesAPIView(generics.ListAPIView):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    pagination_class = None

    def filter_queryset(self, queryset):
        return queryset
