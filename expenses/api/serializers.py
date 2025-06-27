from rest_framework import serializers
from expenses.models import Expense, ExpenseItem


class ExpenseItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = ExpenseItem
        fields = ["id", "item", "item_name", "quantity", "total_price"]


class ExpenseSerializer(serializers.ModelSerializer):
    items = ExpenseItemSerializer(many=True, read_only=True)

    class Meta:
        model = Expense
        fields = [
            "id",
            "stall",
            "total_price",
            "description",
            "created_by",
            "created_at",
            "source",
            "items",
        ]
        read_only_fields = ["created_by", "created_at", "source", "items"]
