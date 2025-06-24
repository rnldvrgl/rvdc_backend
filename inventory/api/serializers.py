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


class StockSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    stall = StallSerializer(read_only=True)

    class Meta:
        model = Stock
        fields = ["id", "quantity", "item", "stall", "created_at", "updated_at"]


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ["id", "name"]
