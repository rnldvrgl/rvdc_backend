from rest_framework import generics, permissions, filters, status
from django_filters.rest_framework import DjangoFilterBackend
from inventory.models import Item, Stall, Stock, ProductCategory
from inventory.api.serializers import (
    ItemSerializer,
    StallSerializer,
    ProductCategorySerializer,
    StockWriteSerializer,
    StockReadSerializer,
)
from utils.mixins import LogCreateMixin, LogUpdateMixin, LogSoftDeleteMixin
from rest_framework.response import Response


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


class StockListCreateView(LogCreateMixin, generics.ListCreateAPIView):
    queryset = Stock.objects.filter(is_deleted=False)
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["item__name", "stall__name"]
    search_fields = ["item__name", "stall__name"]

    def get_serializer_class(self):
        if self.request.method == "GET":
            return StockReadSerializer
        return StockWriteSerializer

    def create(self, request, *args, **kwargs):
        item = request.data.get("item")
        stall = request.data.get("stall")
        quantity = int(request.data.get("quantity", 0))

        existing_stock = Stock.objects.filter(
            item_id=item, stall_id=stall, is_deleted=False
        ).first()

        if existing_stock:
            existing_stock.quantity += quantity
            existing_stock.save()
            read_serializer = StockReadSerializer(existing_stock)
            return Response(read_serializer.data, status=status.HTTP_200_OK)

        return super().create(request, *args, **kwargs)


class StockDetailView(
    LogUpdateMixin, LogSoftDeleteMixin, generics.RetrieveUpdateDestroyAPIView
):
    queryset = Stock.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["item__name", "stall__name"]
    search_fields = ["item__name", "stall__name"]

    def get_serializer_class(self):
        if self.request.method == "GET":
            return StockReadSerializer
        return StockWriteSerializer


class ProductCategoryListCreateView(LogCreateMixin, generics.ListCreateAPIView):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["name"]
    search_fields = ["name"]
