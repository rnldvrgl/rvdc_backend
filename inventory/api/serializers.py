from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from inventory.models import (
    Item,
    Stall,
    Stock,
    ProductCategory,
    StockRoomStock,
    StockTransfer,
    StockTransferItem,
)


class ItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Item
        exclude = ["created_at", "updated_at", "is_deleted", "category"]


class StallSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stall
        exclude = ["created_at", "updated_at", "is_deleted"]


class StockReadSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    item_sku = serializers.CharField(source="item.sku", read_only=True)
    category_name = serializers.CharField(source="item.category.name", read_only=True)
    is_low_stock = serializers.SerializerMethodField()

    class Meta:
        model = Stock
        fields = [
            "id",
            "quantity",
            "item_name",
            "item_sku",
            "category_name",
            "updated_at",
            "is_low_stock",
        ]

    def get_is_low_stock(self, obj):
        return obj.is_low_stock()


class StockWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stock
        fields = ["id", "quantity", "item", "stall"]


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ["id", "name", "created_at", "updated_at", "is_deleted", "description"]
        read_only_fields = ["created_at", "updated_at"]

    def validate_name(self, value):
        qs = ProductCategory.objects.filter(name__iexact=value, is_deleted=False)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "A product category with this name already exists."
            )
        return value


class StockRoomStockSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    is_low_stock = serializers.SerializerMethodField()

    class Meta:
        model = StockRoomStock
        fields = [
            "id",
            "item",
            "item_name",
            "quantity",
            "low_stock_threshold",
            "created_at",
            "updated_at",
            "is_low_stock",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_is_low_stock(self, obj):
        return obj.is_low_stock()


class StockTransferItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = StockTransferItem
        fields = ["item", "item_name", "quantity"]


class StockTransferSerializer(serializers.ModelSerializer):
    items = StockTransferItemSerializer(many=True)

    class Meta:
        model = StockTransfer
        fields = [
            "id",
            "from_stall",
            "to_stall",
            "technician",
            "transferred_by",
            "transfer_date",
            "items",
        ]
        read_only_fields = ["transferred_by", "transfer_date"]

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        from_stall = validated_data.get("from_stall")

        # Check stock availability first
        for item_data in items_data:
            item = item_data["item"]
            quantity = item_data["quantity"]

            if from_stall:
                from_stock = Stock.objects.filter(
                    stall=from_stall, item=item, is_deleted=False
                ).first()
                if not from_stock or from_stock.quantity < quantity:
                    raise ValidationError(
                        f"Not enough stock of {item.name} in stall '{from_stall.name}'."
                    )
            else:
                room_stock = StockRoomStock.objects.filter(item=item).first()
                if not room_stock or room_stock.quantity < quantity:
                    raise ValidationError(
                        f"Not enough stock of {item.name} in stock room."
                    )

        # Use transaction to ensure atomicity
        with transaction.atomic():
            transfer = StockTransfer.objects.create(**validated_data)
            for item_data in items_data:
                StockTransferItem.objects.create(transfer=transfer, **item_data)
                self._update_stock(item_data, transfer)

        return transfer

    def _update_stock(self, item_data, transfer):
        item = item_data["item"]
        quantity = item_data["quantity"]

        if transfer.from_stall:
            from_stock = Stock.objects.filter(
                stall=transfer.from_stall, item=item
            ).first()
            if from_stock:
                from_stock.quantity = max(from_stock.quantity - quantity, 0)
                from_stock.save()
        else:
            room_stock = StockRoomStock.objects.filter(item=item).first()
            if room_stock:
                room_stock.quantity = max(room_stock.quantity - quantity, 0)
                room_stock.save()

        to_stock, _ = Stock.objects.get_or_create(
            stall=transfer.to_stall, item=item, defaults={"quantity": 0}
        )
        to_stock.quantity += quantity
        to_stock.save()
