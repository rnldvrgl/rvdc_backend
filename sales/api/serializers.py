from rest_framework import serializers
from sales.models import SalesTransaction, SalesItem, SalesPayment
from inventory.models import Item


class SalesItemSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.all(), required=False, allow_null=True
    )
    description = serializers.CharField(required=False, allow_blank=True)
    line_total = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model = SalesItem
        fields = [
            "item",
            "description",
            "quantity",
            "final_price_per_unit",
            "line_total",
        ]


class SalesPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesPayment
        fields = ["payment_type", "amount", "payment_date"]


class SalesTransactionSerializer(serializers.ModelSerializer):
    items = SalesItemSerializer(many=True)
    payments = SalesPaymentSerializer(many=True, required=False)

    computed_total = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    total_paid = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    payment_status = serializers.CharField(read_only=True)

    class Meta:
        model = SalesTransaction
        fields = [
            "id",
            "stall",
            "client",
            "manual_receipt_number",
            "system_receipt_number",
            "computed_total",
            "total_paid",
            "payment_status",
            "items",
            "payments",
            "created_at",
            "voided",
            "void_reason",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "computed_total",
            "total_paid",
            "payment_status",
            "system_receipt_number",
        ]

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        payments_data = validated_data.pop("payments", [])

        transaction = SalesTransaction.objects.create(**validated_data)

        for item_data in items_data:
            SalesItem.objects.create(transaction=transaction, **item_data)

        for payment_data in payments_data:
            SalesPayment.objects.create(transaction=transaction, **payment_data)

        transaction.update_payment_status()
        return transaction
