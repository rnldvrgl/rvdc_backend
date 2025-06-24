from rest_framework import generics, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from inventory.models import Item, Stall, Stock, ProductCategory
from inventory.api.serializers import (
    ItemSerializer,
    StallSerializer,
    StockSerializer,
    ProductCategorySerializer,
)
from utils.logger import log_activity


class ItemListCreateView(generics.ListCreateAPIView):
    queryset = Item.objects.filter(is_deleted=False)
    serializer_class = ItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["name", "sku", "category__name"]
    search_fields = ["name", "sku", "category__name"]

    def perform_create(self, serializer):
        item = serializer.save()
        log_activity(
            user=self.request.user,
            instance=item,
            action="Created Item",
            note=f"Item '{item.name}' created.",
        )


class ItemDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_update(self, serializer):
        item = serializer.save()
        log_activity(
            user=self.request.user,
            instance=item,
            action="Updated Item",
            note=f"Item '{item.name}' updated.",
        )

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save()
        log_activity(
            user=self.request.user,
            instance=instance,
            action="Deleted Item",
            note=f"Item '{instance.name}' marked as deleted.",
        )


class StallListCreateView(generics.ListCreateAPIView):
    queryset = Stall.objects.filter(is_deleted=False)
    serializer_class = StallSerializer
    permission_classes = [permissions.IsAdminUser]

    def perform_create(self, serializer):
        stall = serializer.save()
        log_activity(
            user=self.request.user,
            instance=stall,
            action="Created Stall",
            note=f"Stall '{stall.name}' created.",
        )


class StallDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Stall.objects.all()
    serializer_class = StallSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_update(self, serializer):
        stall = serializer.save()
        log_activity(
            user=self.request.user,
            instance=stall,
            action="Updated Stall",
            note=f"Stall '{stall.name}' updated.",
        )

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save()
        log_activity(
            user=self.request.user,
            instance=instance,
            action="Deleted Stall",
            note=f"Stall '{instance.name}' marked as deleted.",
        )


class StockListCreateView(generics.ListCreateAPIView):
    queryset = Stock.objects.filter(is_deleted=False)
    serializer_class = StockSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        stock = serializer.save()
        log_activity(
            user=self.request.user,
            instance=stock,
            action="Created Stock",
            note=f"Stock for Item ID {stock.item_id} added with quantity {stock.quantity}.",
        )


class StockDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Stock.objects.all()
    serializer_class = StockSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_update(self, serializer):
        stock = serializer.save()
        log_activity(
            user=self.request.user,
            instance=stock,
            action="Updated Stock",
            note=f"Stock ID {stock.id} updated with quantity {stock.quantity}.",
        )

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save()
        log_activity(
            user=self.request.user,
            instance=instance,
            action="Deleted Stock",
            note=f"Stock ID {instance.id} marked as deleted.",
        )


class ProductCategoryListCreateView(generics.ListCreateAPIView):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    permission_classes = [permissions.IsAuthenticated]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter]

    filterset_fields = ["name"]
    search_fields = ["name"]

    def perform_create(self, serializer):
        category = serializer.save()
        log_activity(
            user=self.request.user,
            instance=category,
            action="Created Category",
            note=f"Product category '{category.name}' created.",
        )
