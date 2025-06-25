from rest_framework import serializers
from inventory.models import Item, Stall, Stock, ProductCategory


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

    class Meta:
        model = Stock
        fields = ["id", "quantity", "item", "stall", "created_at", "updated_at"]


class StockWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stock
        fields = ["id", "quantity", "item", "stall"]


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ["id", "name"]
