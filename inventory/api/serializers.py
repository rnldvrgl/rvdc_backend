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
from utils.logger import log_activity
from utils.inventory import (
    create_stall_with_initial_stocks,
    create_item_with_initial_stock,
)


class StockPatchSerializer(serializers.ModelSerializer):
    quantity_adjustment = serializers.DictField(
        child=serializers.CharField(), required=False
    )

    class Meta:
        model = Stock
        fields = [
            "quantity",
            "quantity_adjustment",
            "low_stock_threshold",
            "is_deleted",
        ]

    def validate(self, data):
        adj = data.get("quantity_adjustment")
        if adj:
            if not isinstance(adj, dict):
                raise serializers.ValidationError(
                    "quantity_adjustment must be an object."
                )
            if "action" not in adj or "amount" not in adj:
                raise serializers.ValidationError(
                    "quantity_adjustment needs 'action' and 'amount'"
                )
            if adj["action"] not in ["increase", "decrease"]:
                raise serializers.ValidationError(
                    "action must be 'increase' or 'decrease'"
                )
            try:
                adj["amount"] = int(adj["amount"])
            except ValueError:
                raise serializers.ValidationError("amount must be integer.")
            if adj["amount"] < 0:
                raise serializers.ValidationError("amount must be positive.")
        return data

    def update(self, instance, validated_data):
        user = self.context["request"].user
        adj = validated_data.pop("quantity_adjustment", None)
        original_quantity = instance.quantity
        original_threshold = instance.low_stock_threshold
        original_is_deleted = instance.is_deleted

        with transaction.atomic():
            # Handle quantity adjustment
            if adj:
                amount = adj["amount"]
                if adj["action"] == "increase":
                    instance.quantity += amount
                    log_activity(
                        user,
                        instance,
                        "increase_stock",
                        f"Incremented stock of '{instance.item.name}' by {amount} units.",
                    )
                elif adj["action"] == "decrease":
                    instance.quantity = max(instance.quantity - amount, 0)
                    log_activity(
                        user,
                        instance,
                        "decrease_stock",
                        f"Decremented stock of '{instance.item.name}' by {amount} units.",
                    )
            # Direct quantity update
            elif "quantity" in validated_data:
                new_quantity = validated_data.get("quantity", instance.quantity)
                if new_quantity != original_quantity:
                    instance.quantity = new_quantity
                    log_activity(
                        user,
                        instance,
                        "update_stock",
                        f"Updated stock of '{instance.item.name}' from {original_quantity} to {new_quantity} units.",
                    )

            # Threshold update
            if "low_stock_threshold" in validated_data:
                new_threshold = validated_data.get(
                    "low_stock_threshold", instance.low_stock_threshold
                )
                if new_threshold != original_threshold:
                    instance.low_stock_threshold = new_threshold
                    log_activity(
                        user,
                        instance,
                        "update_threshold",
                        f"Updated low stock threshold for '{instance.item.name}' from {original_threshold} to {new_threshold}.",
                    )

            # Handle soft delete
            if "is_deleted" in validated_data:
                new_is_deleted = validated_data.get("is_deleted")
                if new_is_deleted != original_is_deleted:
                    instance.is_deleted = new_is_deleted
                    action = "deleted_stock" if new_is_deleted else "restored_stock"
                    log_activity(
                        user,
                        instance,
                        action,
                        f"{'Deleted' if new_is_deleted else 'Restored'} stock of '{instance.item.name}' at stall '{instance.stall.name}'.",
                    )

            instance.is_low_stock = instance.quantity <= instance.low_stock_threshold
            instance.save()

        return instance


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ["id", "name", "description", "created_at", "updated_at"]
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


class ItemSerializer(serializers.ModelSerializer):
    category = ProductCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source="category", queryset=ProductCategory.objects.all(), write_only=True
    )
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = Item
        exclude = ["created_at", "updated_at", "is_deleted"]

    def get_display_name(self, obj):
        if obj.is_deleted:
            return f"{obj.name} (Deleted)"
        return obj.name

    def validate(self, data):
        category = data.get("category") or getattr(self.instance, "category", None)
        name = data.get("name") or getattr(self.instance, "name", None)
        size_or_spec = data.get("size_or_spec") or getattr(
            self.instance, "size_spec", None
        )

        qs = Item.objects.filter(
            name__iexact=name,
            category=category,
            size_or_spec=size_or_spec,
            is_deleted=False,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "An item with this name, category, and size/spec already exists."
            )
        return data

    def create(self, validated_data):
        user = self.context["request"].user
        return create_item_with_initial_stock(validated_data, user)


class StallSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stall
        exclude = ["updated_at", "is_deleted"]

    def create(self, validated_data):
        user = self.context["request"].user
        return create_stall_with_initial_stocks(validated_data, user)


class StockReadSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    stall = StallSerializer(read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = Stock
        fields = [
            "id",
            "quantity",
            "low_stock_threshold",
            "item",
            "updated_at",
            "status",
            "stall",
        ]

    def get_status(self, obj):
        return obj.status()


class StockWriteSerializer(serializers.ModelSerializer):
    item_id = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.all(), source="item"
    )
    stall_id = serializers.PrimaryKeyRelatedField(
        queryset=Stall.objects.all(), source="stall"
    )

    class Meta:
        model = Stock
        fields = ["id", "quantity", "item_id", "stall_id", "low_stock_threshold"]

    def validate(self, data):
        item = data.get("item")
        stall = data.get("stall")
        qs = Stock.objects.filter(item=item, stall=stall)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        f"Stock for item '{item.name}' and stall '{stall.name}' already exists. The combination of item and stall must be unique."
                    ]
                }
            )
        return data


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

        for item_data in items_data:
            item = item_data["item"]
            qty = item_data["quantity"]
            if from_stall:
                stock = Stock.objects.filter(stall=from_stall, item=item).first()
                if not stock or stock.quantity < qty:
                    raise ValidationError(
                        f"Not enough stock of {item.name} in {from_stall.name}"
                    )
            else:
                room_stock = StockRoomStock.objects.filter(item=item).first()
                if not room_stock or room_stock.quantity < qty:
                    raise ValidationError(
                        f"Not enough stock of {item.name} in stock room"
                    )

        with transaction.atomic():
            transfer = StockTransfer.objects.create(**validated_data)
            for item_data in items_data:
                StockTransferItem.objects.create(transfer=transfer, **item_data)
                self._adjust_stock(item_data, transfer)
        return transfer

    def _adjust_stock(self, item_data, transfer):
        item, qty = item_data["item"], item_data["quantity"]
        if transfer.from_stall:
            from_stock = Stock.objects.filter(
                stall=transfer.from_stall, item=item
            ).first()
            if from_stock:
                from_stock.quantity = max(from_stock.quantity - qty, 0)
                from_stock.save()
        else:
            room_stock = StockRoomStock.objects.filter(item=item).first()
            if room_stock:
                room_stock.quantity = max(room_stock.quantity - qty, 0)
                room_stock.save()

        to_stock, created = Stock.objects.get_or_create(
            stall=transfer.to_stall,
            item=item,
            defaults={"quantity": 0, "type": "transferred"},
        )
        if not created and to_stock.type != "transferred":
            to_stock.type = "transferred"
        to_stock.quantity += qty
        to_stock.save()


class StockAdjustSerializer(serializers.Serializer):
    stall_id = serializers.IntegerField()
    item_id = serializers.IntegerField()
    quantity = serializers.IntegerField()
    action = serializers.ChoiceField(
        choices=[("increase", "Increase"), ("decrease", "Decrease")]
    )

    def validate(self, data):
        stall_id = data["stall_id"]
        item_id = data["item_id"]
        action = data["action"]
        quantity = data["quantity"]

        stock = Stock.objects.filter(stall_id=stall_id, item_id=item_id).first()
        if not stock:
            raise serializers.ValidationError(
                "Stock record not found for this stall and item."
            )
        if action == "decrease" and stock.quantity < quantity:
            raise serializers.ValidationError(
                f"Not enough stock to decrease. Current: {stock.quantity}"
            )
        data["stock"] = stock
        return data


class StockRestockSerializer(serializers.Serializer):
    quantity = serializers.IntegerField()

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be positive.")
        return value
