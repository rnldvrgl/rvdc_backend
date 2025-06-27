from rest_framework import generics, permissions, filters, status
from django_filters.rest_framework import DjangoFilterBackend
from inventory.models import (
    Item,
    Stall,
    Stock,
    ProductCategory,
    StockRoomStock,
    StockTransfer,
)
from inventory.api.serializers import (
    ItemSerializer,
    StallSerializer,
    ProductCategorySerializer,
    StockWriteSerializer,
    StockReadSerializer,
    StockRoomStockSerializer,
    StockTransferSerializer,
)
from utils.mixins import LogCreateMixin, LogUpdateMixin, LogSoftDeleteMixin
from rest_framework.response import Response
from utils.logger import log_activity


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
        return (
            StockReadSerializer
            if self.request.method == "GET"
            else StockWriteSerializer
        )

    def create(self, request, *args, **kwargs):
        item_id = request.data.get("item")
        stall_id = request.data.get("stall")
        quantity_to_add = int(request.data.get("quantity", 0))

        existing_stock = Stock.objects.filter(
            item_id=item_id, stall_id=stall_id, is_deleted=False
        ).first()

        if existing_stock:
            existing_stock.quantity += quantity_to_add
            existing_stock.save()

            # Optional logging
            log_activity(
                user=request.user,
                instance=existing_stock,
                action="Updated Stock",
                note=f"Added {quantity_to_add} to stock for Item {item_id} at Stall {stall_id}.",
            )

            serializer = StockReadSerializer(existing_stock)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # No existing stock — create new
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


class StockRoomStockListCreateView(LogCreateMixin, generics.ListCreateAPIView):
    queryset = StockRoomStock.objects.all()
    serializer_class = StockRoomStockSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["item__name"]
    search_fields = ["item__name"]

    def create(self, request, *args, **kwargs):
        item_id = request.data.get("item")
        quantity_to_add = int(request.data.get("quantity", 0))

        existing_stock = StockRoomStock.objects.filter(item_id=item_id).first()

        if existing_stock:
            existing_stock.quantity += quantity_to_add
            existing_stock.save()

            log_activity(
                user=request.user,
                instance=existing_stock,
                action="Updated StockRoomStock",
                note=f"Added {quantity_to_add} to stock room for Item {item_id}.",
            )

            serializer = StockRoomStockSerializer(existing_stock)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # No existing stock — create new
        return super().create(request, *args, **kwargs)


class StockRoomStockDetailView(generics.RetrieveUpdateAPIView):
    queryset = StockRoomStock.objects.all()
    serializer_class = StockRoomStockSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["item__name"]
    search_fields = ["item__name", "quantity"]

    def perform_update(self, serializer):
        instance = serializer.save()
        log_activity(
            user=self.request.user,
            instance=instance,
            action="Updated StockRoomStock",
            note=f"Updated details for Stock Room Item {instance.item.name}.",
        )


class StockTransferCreateView(generics.CreateAPIView):
    queryset = StockTransfer.objects.all()
    serializer_class = StockTransferSerializer
    permission_classes = [permissions.IsAdminUser]

    def perform_create(self, serializer):
        transfer = serializer.save(transferred_by=self.request.user)

        for item in transfer.items.all():
            log_activity(
                user=self.request.user,
                instance=item,
                action="Item Transferred",
                note=f"Transferred {item.quantity} {item.item.unit_of_measure} of {item.item.name} "
                f"from {'stock room' if not transfer.from_stall else transfer.from_stall.name} "
                f"to {transfer.to_stall.name}.",
            )
