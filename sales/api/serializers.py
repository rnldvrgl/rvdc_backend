from rest_framework import serializers
from sales.models import SalesTransaction, SalesItem
from inventory.models import Item, Stall
from clients.models import Client
from utils.logger import log_activity

# from utils.inventory import deduct_inventory
from django.core.exceptions import ValidationError


class SalesItemSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.all(), write_only=True
    )
    item_name = serializers.CharField(source="item.name", read_only=True)
    item_unit = serializers.CharField(source="item.unit", read_only=True)  # Optional

    retail_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    final_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model = SalesItem
        fields = [
            "item",  # for input
            "item_name",  # for display
            "item_unit",  # optional
            "quantity",
            "retail_price",
            "discount_amount",
            "final_price",
        ]


class SalesTransactionSerializer(serializers.ModelSerializer):
    items = SalesItemSerializer(many=True)
    total_price = serializers.SerializerMethodField()

    # display-only
    sales_clerk_name = serializers.CharField(
        source="sales_clerk.username", read_only=True
    )
    client_name = serializers.CharField(source="client.full_name", read_only=True)

    class Meta:
        model = SalesTransaction
        fields = [
            "id",
            "receipt_number",
            "sales_clerk_name",
            "client_name",
            "total_price",
            "total_payment",
            "items",
            "created_at",
            "voided",
            "void_reason",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "voided",
            "void_reason",
            "sales_clerk_name",
            "stall_name",
            "client_name",
            "total_price",
        ]

    def get_total_price(self, obj):
        return sum(item.quantity * item.final_price for item in obj.items.all())

    def query_set(self):
        user_stall = getattr(self.request.user, "assigned_stall", None)
        if user_stall:
            return SalesTransaction.objects.filter(stall=user_stall).order_by(
                "-created_at"
            )
        return SalesTransaction.objects.none()

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        stall = validated_data.pop("stall")

        transaction = SalesTransaction.objects.create(stall=stall, **validated_data)

        sales_items = []
        inventory_data = []

        for item_data in items_data:
            item_instance = item_data["item"]
            quantity = item_data["quantity"]
            discount = item_data.get("discount_amount", 0)
            retail_price = item_instance.retail_price
            final_price = retail_price - discount

            sales_items.append(
                SalesItem(
                    transaction=transaction,
                    item=item_instance,
                    quantity=quantity,
                    discount_amount=discount,
                    retail_price=retail_price,
                    final_price=final_price,
                )
            )
            inventory_data.append({"item": item_instance, "quantity": quantity})

        SalesItem.objects.bulk_create(sales_items)

        try:
            pass
            # deduct_inventory(inventory_data, stall)
        except ValidationError as e:
            raise serializers.ValidationError({"non_field_errors": [str(e)]})

        log_activity(
            user=transaction.sales_clerk,
            instance=transaction,
            action=f"Created Sale #{transaction.id}",
        )

        return transaction
