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
from utils.inventory import (
    create_stall_with_initial_stocks,
    create_item_with_initial_stock,
)
from expenses.models import Expense


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
                "A category with this name already exists."
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
        return f"{obj.name} (Deleted)" if obj.is_deleted else obj.name

    def validate(self, data):
        category = data.get("category") or getattr(self.instance, "category", None)
        name = data.get("name") or getattr(self.instance, "name", None)
        qs = Item.objects.filter(name__iexact=name, category=category, is_deleted=False)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "An item with this name & category already exists."
            )
        return data

    def create(self, validated_data):
        return create_item_with_initial_stock(validated_data)


class StallSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stall
        exclude = ["updated_at", "is_deleted"]
        read_only_fields = ["inventory_enabled", "is_system"]

    def create(self, validated_data):
        return create_stall_with_initial_stocks(validated_data)


class StockReadSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    stall = StallSerializer(read_only=True)
    status = serializers.SerializerMethodField()
    stock_room_quantity = serializers.SerializerMethodField()
    stock_room_status = serializers.SerializerMethodField()
    reserved_quantity = serializers.IntegerField(read_only=True)
    available_quantity = serializers.SerializerMethodField()

    class Meta:
        model = Stock
        fields = [
            "id",
            "quantity",
            "reserved_quantity",
            "available_quantity",
            "low_stock_threshold",
            "item",
            "updated_at",
            "status",
            "stall",
            "track_stock",
            "stock_room_quantity",
            "stock_room_status",
        ]

    def get_status(self, obj):
        return obj.status()

    def get_stock_room_quantity(self, obj):
        stock_room_stock = StockRoomStock.objects.filter(item=obj.item).first()
        return stock_room_stock.quantity if stock_room_stock else 0

    def get_stock_room_status(self, obj):
        stock_room = StockRoomStock.objects.filter(item=obj.item).first()
        return stock_room.status() if stock_room else "no_stock"

    def get_available_quantity(self, obj):
        return obj.quantity - obj.reserved_quantity


class StockWriteSerializer(serializers.ModelSerializer):
    item_id = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.all(), source="item"
    )
    stall_id = serializers.PrimaryKeyRelatedField(
        queryset=Stall.objects.all(), source="stall"
    )

    class Meta:
        model = Stock
        fields = [
            "id",
            "quantity",
            "item_id",
            "stall_id",
            "low_stock_threshold",
            "track_stock",
        ]

    def validate(self, data):
        qs = Stock.objects.filter(item=data["item"], stall=data["stall"])
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        f"Stock for item '{data['item'].name}' at stall '{data['stall'].name}' already exists."
                    ]
                }
            )
        return data


class StockPatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stock
        fields = ["quantity", "low_stock_threshold", "is_deleted", "track_stock"]

    def update(self, instance, validated_data):
        instance.is_low_stock = instance.quantity <= instance.low_stock_threshold
        instance.save()

        return instance


class StockRoomStockSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = StockRoomStock
        fields = [
            "id",
            "item",
            "quantity",
            "low_stock_threshold",
            "created_at",
            "updated_at",
            "status",
        ]

    def get_status(self, obj):
        return obj.status()


class StockRestockSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be a positive integer.")
        return value


class StockTransferItemSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())

    class Meta:
        model = StockTransferItem
        fields = ["item", "quantity"]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep["item"] = ItemSerializer(instance.item).data
        return rep


class StockTransferSerializer(serializers.ModelSerializer):
    items = StockTransferItemSerializer(many=True)
    is_paid = serializers.SerializerMethodField()
    paid_at = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = StockTransfer
        fields = [
            "id",
            "from_stall",
            "to_stall",
            "technician",
            "transferred_by",
            "transfer_date",
            "is_finalized",
            "finalized_at",
            "items",
            "is_paid",
            "paid_at",
            "total_price",
            "used_for",
        ]
        read_only_fields = [
            "transferred_by",
            "transfer_date",
            "is_finalized",
            "finalized_at",
            "total_price",
        ]

    def to_representation(self, instance):
        from users.api.serializers import TechnicianSerializer
        from inventory.api.serializers import StallSerializer

        rep = super().to_representation(instance)
        rep["from_stall"] = (
            StallSerializer(instance.from_stall).data if instance.from_stall else None
        )
        rep["to_stall"] = (
            StallSerializer(instance.to_stall).data if instance.to_stall else None
        )
        rep["technician"] = (
            TechnicianSerializer(instance.technician).data
            if instance.technician
            else None
        )
        return rep

    def get_total_price(self, obj):
        return sum(
            (item.item.retail_price or 0) * item.quantity for item in obj.items.all()
        )

    def get_is_paid(self, obj):
        try:
            return obj.expense.is_paid
        except Expense.DoesNotExist:
            return False

    def get_paid_at(self, obj):
        try:
            return obj.expense.paid_at
        except Expense.DoesNotExist:
            return None

    def _save_items(self, transfer, items_data):
        for item_data in items_data:
            StockTransferItem.objects.create(transfer=transfer, **item_data)
            self._adjust_stock(item_data, transfer)

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        self._check_stock_levels(items_data, validated_data.get("from_stall"))
        with transaction.atomic():
            transfer = StockTransfer.objects.create(**validated_data)
            self._save_items(transfer, items_data)
        return transfer

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        with transaction.atomic():
            instance.technician = validated_data.get("technician", instance.technician)
            instance.to_stall = validated_data.get("to_stall", instance.to_stall)
            instance.used_for = validated_data.get("used_for", instance.used_for)
            instance.save()

            if items_data is not None:
                for old_item in instance.items.all():
                    self._reverse_stock(old_item, instance)
                instance.items.all().delete()
                self._save_items(instance, items_data)
        return instance

    def _check_stock_levels(self, items_data, from_stall):
        for item_data in items_data:
            item, qty = item_data["item"], item_data["quantity"]
            stock = (
                Stock.objects.filter(stall=from_stall, item=item).first()
                if from_stall
                else StockRoomStock.objects.filter(item=item).first()
            )
            if not stock or stock.quantity < qty:
                location = from_stall.name if from_stall else "stock room"
                raise ValidationError(f"Not enough stock of {item.name} in {location}")

    def _adjust_stock(self, item_data, transfer):
        item, qty = item_data["item"], item_data["quantity"]
        if transfer.from_stall:
            stock = Stock.objects.get(stall=transfer.from_stall, item=item)
            stock.quantity -= qty
            stock.save()
        else:
            room_stock = StockRoomStock.objects.get(item=item)
            room_stock.quantity -= qty
            room_stock.save()

        # Only create/add quantity to the receiving stall if it is an inventory owner
        if transfer.to_stall and getattr(transfer.to_stall, "inventory_enabled", False):
            to_stock, _ = Stock.objects.get_or_create(
                stall=transfer.to_stall, item=item, defaults={"quantity": 0}
            )
            to_stock.quantity += qty
            to_stock.save()

    def _reverse_stock(self, transfer_item, transfer):
        item, qty = transfer_item.item, transfer_item.quantity
        if transfer.from_stall:
            stock = Stock.objects.get(stall=transfer.from_stall, item=item)
            stock.quantity += qty
            stock.save()
        else:
            room_stock = StockRoomStock.objects.get(item=item)
            room_stock.quantity += qty
            room_stock.save()

        # Only attempt to adjust receiver stock if it is an inventory owner
        if transfer.to_stall and getattr(transfer.to_stall, "inventory_enabled", False):
            to_stock = Stock.objects.get(stall=transfer.to_stall, item=item)
            if to_stock.quantity < qty:
                raise ValidationError(
                    f"Cannot rollback {qty} from {item.name} at {transfer.to_stall.name}, only {to_stock.quantity} available."
                )
            to_stock.quantity -= qty
            to_stock.save()
