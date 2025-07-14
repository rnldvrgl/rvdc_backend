from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from django.db import transaction

from inventory.models import (
    Item,
    Stall,
    Stock,
    StockRoomStock,
    ProductCategory,
    StockTransfer,
    Restock,
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
from utils.inventory import (
    user_can_manage_stall,
    record_stock_movement,
)
from utils.logger import log_activity
from django_filters.rest_framework import DjangoFilterBackend


class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer


class StallViewSet(viewsets.ModelViewSet):
    queryset = Stall.objects.all()
    serializer_class = StallSerializer


class StockViewSet(viewsets.ModelViewSet):
    queryset = Stock.objects.all()
    permission_classes = [IsAuthenticated]  # assuming

    def get_serializer_class(self):
        if self.action in ["list", "retrieve"]:
            return StockReadSerializer
        elif self.action in ["partial_update", "update"]:
            return StockPatchSerializer
        elif self.action == "create":
            return StockWriteSerializer
        return StockReadSerializer

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

        restock_out = Restock.objects.create(
            item=stock.item,
            quantity=quantity,
            created_by=request.user,
        )

        record_stock_movement(
            item=stock.item,
            stall=None,
            quantity=-quantity,
            movement_type="transfer_out",
            related_object=restock_out,
            note=f"Stock room ➔ Stall '{stock.stall.name}': -{quantity} {stock.item.unit_of_measure} '{stock.item.name}'",
        )

        # Add to stall
        original_quantity = stock.quantity
        stock.quantity += quantity
        stock.save()

        restock_in = Restock.objects.create(
            item=stock.item,
            quantity=quantity,
            created_by=request.user,
        )

        record_stock_movement(
            item=stock.item,
            stall=stock.stall,
            quantity=quantity,
            movement_type="transfer_in",
            related_object=restock_in,
            note=f"Stock room ➔ Stall '{stock.stall.name}': +{quantity} {stock.item.unit_of_measure} '{stock.item.name}'",
        )

        log_activity(
            request.user,
            stock,
            "restock",
            f"Restocked '{stock.item.name}' at '{stock.stall.name}' from {original_quantity} to {stock.quantity}.",
        )

        return Response(
            {"detail": f"Restocked successfully. New quantity: {stock.quantity}"}
        )


class StockRoomStockViewSet(viewsets.ModelViewSet):
    queryset = StockRoomStock.objects.all()
    serializer_class = StockRoomStockSerializer

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    @transaction.atomic
    def restock(self, request, pk=None):
        stock_room_stock = self.get_object()

        serializer = StockRestockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quantity = serializer.validated_data["quantity"]

        original_quantity = stock_room_stock.quantity
        stock_room_stock.quantity += quantity
        stock_room_stock.save()

        restock = Restock.objects.create(
            item=stock_room_stock.item,
            quantity=quantity,
            created_by=request.user,
        )

        record_stock_movement(
            item=stock_room_stock.item,
            stall=None,
            quantity=quantity,
            movement_type="purchase",
            related_object=restock,
            note=f"Supplier ➔ Stock room: +{quantity} {stock_room_stock.item.unit_of_measure} '{stock_room_stock.item.name}'",
        )

        log_activity(
            request.user,
            stock_room_stock,
            "restock_stock_room",
            f"Restocked stock room for '{stock_room_stock.item.name}' from {original_quantity} to {stock_room_stock.quantity}.",
        )

        return Response(
            {
                "detail": f"Stock room restocked successfully. New quantity: {stock_room_stock.quantity}."
            }
        )


class ProductCategoryViewSet(viewsets.ModelViewSet):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer


class StockTransferViewSet(viewsets.ModelViewSet):
    queryset = StockTransfer.objects.all()
    serializer_class = StockTransferSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["from_stall", "to_stall"]
    search_fields = ["from_stall__name", "to_stall__name"]

    def get_queryset(self):
        user = self.request.user
        if user.role == "admin":
            return StockTransfer.objects.all()
        elif user.role in ["manager", "clerk"] and (user.assigned_stall is not None):
            return StockTransfer.objects.filter(from_stall=user.assigned_stall)
        return StockTransfer.objects.none()

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    @transaction.atomic
    def finalize(self, request, pk=None):
        transfer = self.get_object()
        if not transfer.can_be_finalized_by(request.user):
            return Response(
                {"detail": "You do not have permission to finalize this transfer."},
                status=status.HTTP_403_FORBIDDEN,
            )

        transfer.finalize(request.user)  # 🔥 FIXED

        return Response({"detail": "Stock transfer finalized."})

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    @transaction.atomic
    def mark_expense_as_paid(self, request, pk=None):
        transfer = self.get_object()
        transfer.mark_expense_as_paid()
        return Response({"detail": "Marked expense as paid."})
