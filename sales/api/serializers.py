from rest_framework import serializers
from django.db import transaction
from rest_framework.exceptions import ValidationError
from inventory.models import Stock
from sales.models import SalesTransaction, SalesItem, SalesPayment
from inventory.api.serializers import ItemSerializer, StallSerializer
from clients.api.serializers import ClientSerializer
from inventory.models import Item


class SalesItemSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
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
            "id",
            "item",
            "description",
            "quantity",
            "final_price_per_unit",
            "line_discount_rate",
            "line_total",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["item"] = ItemSerializer(instance.item).data if instance.item else None
        return data


class SalesPaymentSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    payment_date = serializers.DateTimeField(required=False, read_only=True)
    cheque_number = serializers.CharField(
        source="cheque_collection.cheque_number", read_only=True
    )

    class Meta:
        model = SalesPayment
        fields = ["id", "payment_type", "amount", "payment_date", "cheque_collection", "cheque_number"]
        read_only_fields = ["id", "payment_date"]


class SalesTransactionSerializer(serializers.ModelSerializer):
    items = SalesItemSerializer(many=True)
    payments = SalesPaymentSerializer(many=True, required=False)
    subtotal = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    computed_total = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    total_paid = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    payment_status = serializers.CharField(read_only=True)
    change_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model = SalesTransaction
        fields = [
            "id",
            "stall",
            "client",
            "manual_receipt_number",
            "system_receipt_number",
            "order_discount",
            "subtotal",
            "computed_total",
            "total_paid",
            "change_amount",
            "payment_status",
            "transaction_type",
            "note",
            "items",
            "payments",
            "created_at",
            "voided",
            "void_reason",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "subtotal",
            "computed_total",
            "total_paid",
            "payment_status",
            "system_receipt_number",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["client"] = (
            ClientSerializer(instance.client).data if instance.client else None
        )
        data["stall"] = StallSerializer(instance.stall).data if instance.stall else None
        return data

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        payments_data = validated_data.pop("payments", [])
        stall = validated_data.get("stall")

        if not stall:
            raise ValidationError("Stall is required for this sales transaction.")

        with transaction.atomic():
            # Check stock availability with row-level lock
            for item_data in items_data:
                item = item_data.get("item")
                if not item:
                    continue
                qty = item_data["quantity"]
                stock = Stock.objects.select_for_update().filter(
                    stall=stall, item=item
                ).first()
                # Skip validation for untracked stock
                if stock and not stock.track_stock:
                    continue
                if not stock or stock.quantity < qty:
                    raise ValidationError(
                        f"Not enough stock of {item.name} in {stall.name}. "
                        f"Available: {stock.quantity if stock else 0}, Needed: {qty}"
                    )

            sale_txn = SalesTransaction.objects.create(**validated_data)

            # Deduct stock & create sales items
            for item_data in items_data:
                item = item_data.get("item")
                qty = item_data["quantity"]

                if item:
                    stock = Stock.objects.select_for_update().get(stall=stall, item=item)
                    # Only deduct for tracked stock
                    if stock.track_stock:
                        stock.quantity -= qty
                        stock.save(update_fields=["quantity", "updated_at"])

                SalesItem.objects.create(transaction=sale_txn, **item_data)

            # Create payments if any
            for payment_data in payments_data:
                SalesPayment.objects.create(transaction=sale_txn, **payment_data)

            sale_txn.update_payment_status()

        return sale_txn

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        payments_data = validated_data.pop("payments", None)
        stall = validated_data.get("stall", instance.stall)

        with transaction.atomic():
            if items_data is not None:
                existing_items = {item.id: item for item in instance.items.all()}
                net_changes = {}

                sent_ids = []
                for item_data in items_data:
                    item_id = item_data.get("id")
                    item = item_data.get("item")
                    qty = item_data["quantity"]

                    if item_id and item_id in existing_items:
                        old_item = existing_items[item_id]
                        sent_ids.append(item_id)
                        if item:
                            delta_qty = qty - old_item.quantity
                            net_changes[item] = net_changes.get(item, 0) + delta_qty
                    else:
                        if item:
                            net_changes[item] = net_changes.get(item, 0) + qty

                for item_id, old_item in existing_items.items():
                    if item_id not in sent_ids and old_item.item:
                        net_changes[old_item.item] = (
                            net_changes.get(old_item.item, 0) - old_item.quantity
                        )

                # Validate before applying changes
                for item, change in net_changes.items():
                    if change > 0:
                        stock = Stock.objects.filter(stall=stall, item=item).first()
                        # Skip validation for untracked stock
                        if stock and not stock.track_stock:
                            continue
                        if not stock or stock.quantity < change:
                            raise ValidationError(
                                f"Not enough stock of {item.name} in {stall.name}. "
                                f"Available: {stock.quantity if stock else 0}, Needed additional: {change}"
                            )

                # Adjust stocks
                for item, change in net_changes.items():
                    if change != 0:
                        stock, _ = Stock.objects.get_or_create(
                            stall=stall, item=item, defaults={"quantity": 0}
                        )
                        # Only adjust tracked stock
                        if stock.track_stock:
                            stock.quantity -= change
                            stock.save()

            # Apply basic field updates
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

            if items_data is not None:
                existing_items = {item.id: item for item in instance.items.all()}
                sent_ids = []
                for item_data in items_data:
                    item_id = item_data.pop("id", None)
                    if item_id and item_id in existing_items:
                        item = existing_items[item_id]
                        for attr, value in item_data.items():
                            setattr(item, attr, value)
                        item.save()
                        sent_ids.append(item_id)
                    else:
                        SalesItem.objects.create(transaction=instance, **item_data)

                for item_id, item in existing_items.items():
                    if item_id not in sent_ids:
                        item.delete()

            if payments_data is not None:
                existing_payments = {p.id: p for p in instance.payments.all()}
                sent_payment_ids = []
                for payment_data in payments_data:
                    payment_id = payment_data.pop("id", None)
                    if payment_id and payment_id in existing_payments:
                        payment = existing_payments[payment_id]
                        for attr, value in payment_data.items():
                            setattr(payment, attr, value)
                        payment.save()
                        sent_payment_ids.append(payment_id)
                    else:
                        SalesPayment.objects.create(
                            transaction=instance, **payment_data
                        )

                for payment_id, payment in existing_payments.items():
                    if payment_id not in sent_payment_ids:
                        payment.delete()

            instance.update_payment_status()
        return instance
