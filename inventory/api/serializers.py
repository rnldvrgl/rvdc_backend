from rest_framework import serializers
from inventory.models import (
    Item,
    Stall,
    Stock,
    ProductCategory,
    StockRoomStock,
    StockTransfer,
)


class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = "__all__"


class StallSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stall
        fields = "__all__"


class StockReadSerializer(serializers.ModelSerializer):
    item = ItemSerializer()
    stall = StallSerializer()
    is_low_stock = serializers.SerializerMethodField()

    class Meta:
        model = Stock
        fields = [
            "id",
            "quantity",
            "item",
            "stall",
            "created_at",
            "updated_at",
            "low_stock_threshold",
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
        fields = ["id", "name"]


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

    def get_is_low_stock(self, obj):
        return obj.is_low_stock()


class StockTransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockTransfer
        fields = [
            "id",
            "item",
            "quantity",
            "to_stall",
            "transferred_by",
            "transfer_date",
        ]
        read_only_fields = ["transferred_by", "transfer_date"]

    def create(self, validated_data):
        item = validated_data["item"]
        quantity = validated_data["quantity"]
        to_stall = validated_data["to_stall"]
        user = self.context["request"].user

        # Decrease from stock room
        stock_room_entry, _ = StockRoomStock.objects.get_or_create(item=item)
        if stock_room_entry.quantity < quantity:
            raise serializers.ValidationError("Insufficient stock in stock room.")
        stock_room_entry.quantity -= quantity
        stock_room_entry.save()

        # Increase in stall stock
        stock_entry, created = Stock.objects.get_or_create(item=item, stall=to_stall)
        stock_entry.quantity += quantity
        stock_entry.save()

        validated_data["transferred_by"] = user
        return super().create(validated_data)
