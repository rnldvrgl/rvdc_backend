from decimal import Decimal

from inventory.models import (
    Item,
    ItemPriceHistory,
    ProductCategory,
    Stall,
    Stock,
    StockRequest,
    StockRoomStock,
)
from rest_framework import serializers
from utils.inventory import (
    create_item_with_initial_stock,
    create_stall_with_initial_stocks,
)


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ["id", "name", "created_at", "updated_at"]
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


class ItemPriceHistorySerializer(serializers.ModelSerializer):
    price_change_amount = serializers.ReadOnlyField()

    class Meta:
        model = ItemPriceHistory
        fields = [
            "id", "item", "retail_price", "wholesale_price",
            "technician_price", "cost_price",
            "old_retail_price", "old_wholesale_price",
            "old_technician_price", "old_cost_price",
            "price_change_amount", "change_type", "notes", "changed_at",
        ]
        read_only_fields = fields


class ItemSerializer(serializers.ModelSerializer):
    category = ProductCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source="category", queryset=ProductCategory.objects.all(), write_only=True
    )
    display_name = serializers.SerializerMethodField()
    price_history = ItemPriceHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Item
        exclude = ["created_at", "updated_at", "is_deleted", "description"]

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
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False, read_only=True)
    reserved_quantity = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False, read_only=True)
    low_stock_threshold = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False, read_only=True)
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
        # Use select_related stockroom_stock (OneToOne) to avoid N+1 queries
        stock_room_stock = getattr(obj.item, 'stockroom_stock', None)
        return float(stock_room_stock.quantity) if stock_room_stock else 0

    def get_stock_room_status(self, obj):
        # Use select_related stockroom_stock (OneToOne) to avoid N+1 queries
        stock_room_stock = getattr(obj.item, 'stockroom_stock', None)
        return stock_room_stock.status() if stock_room_stock else "no_stock"

    def get_available_quantity(self, obj):
        return float(obj.quantity - obj.reserved_quantity)


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
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False, read_only=True)
    low_stock_threshold = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False, read_only=True)

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
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be a positive number.")
        return value


class StockAuditSerializer(serializers.Serializer):
    physical_count = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0'))

    def validate_physical_count(self, value):
        if value < 0:
            raise serializers.ValidationError("Physical count cannot be negative.")
        return value


class StockRequestSerializer(serializers.ModelSerializer):
    """Serializer for stock requests with read-only context fields."""

    item_name = serializers.CharField(source="item.name", read_only=True)
    item_sku = serializers.CharField(source="item.sku", read_only=True)
    stall_name = serializers.CharField(source="stall.name", read_only=True)
    requested_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    service_id = serializers.IntegerField(source="service.id", read_only=True, default=None)
    available_stock = serializers.SerializerMethodField()

    class Meta:
        model = StockRequest
        fields = [
            "id",
            "item",
            "item_name",
            "item_sku",
            "stall",
            "stall_name",
            "requested_quantity",
            "status",
            "source",
            "service",
            "service_id",
            "appliance_item",
            "service_item",
            "notes",
            "requested_by",
            "requested_by_name",
            "approved_by",
            "approved_by_name",
            "approved_at",
            "decline_reason",
            "declined_at",
            "available_stock",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "item",
            "item_name",
            "item_sku",
            "stall",
            "stall_name",
            "requested_quantity",
            "status",
            "source",
            "service",
            "appliance_item",
            "service_item",
            "requested_by",
            "approved_by",
            "approved_at",
            "decline_reason",
            "declined_at",
            "created_at",
            "updated_at",
        ]

    def get_requested_by_name(self, obj):
        if obj.requested_by:
            return obj.requested_by.get_full_name() or obj.requested_by.username
        return None

    def get_approved_by_name(self, obj):
        if obj.approved_by:
            return obj.approved_by.get_full_name() or obj.approved_by.username
        return None

    def get_available_stock(self, obj):
        try:
            stock = Stock.objects.filter(
                item=obj.item, stall=obj.stall, is_deleted=False
            ).first()
            if stock:
                return float(stock.quantity - stock.reserved_quantity)
            return 0
        except Exception:
            return 0
