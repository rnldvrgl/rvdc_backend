from rest_framework import serializers
from expenses.models import Expense, ExpenseItem
from inventory.api.serializers import StockTransferSerializer


class ExpenseItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = ExpenseItem
        fields = ["id", "item", "item_name", "quantity", "total_price"]

    def validate(self, attrs):
        expense = self.instance.expense if self.instance else self.context["expense"]
        if expense.paid_amount > 0:
            raise serializers.ValidationError("Cannot edit items after payment.")
        return attrs


class ExpenseSerializer(serializers.ModelSerializer):
    items = ExpenseItemSerializer(many=True, read_only=True)
    transfer = StockTransferSerializer(read_only=True)

    class Meta:
        model = Expense
        fields = [
            "id",
            "stall",
            "total_price",
            "paid_amount",
            "paid_at",
            "description",
            "created_by",
            "created_at",
            "is_paid",
            "source",
            "transfer",
            "items",
        ]
        read_only_fields = [
            "created_by",
            "created_at",
            "items",
            "is_paid",
        ]


class ExpensePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = ["id", "paid_amount", "paid_at"]

    def update(self, instance, validated_data):
        instance.paid_amount = validated_data.get("paid_amount", instance.paid_amount)
        instance.paid_at = validated_data.get("paid_at", instance.paid_at)
        if instance.paid_amount >= instance.total_price:
            instance.is_paid = True
        instance.save()
        return instance
