from decimal import Decimal

from rest_framework import serializers

from clients.api.serializers import ClientSerializer
from quotations.models import Quotation, QuotationItem, QuotationTermsTemplate


class QuotationTermsTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuotationTermsTemplate
        fields = [
            "id",
            "name",
            "category",
            "lines",
            "is_default",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class QuotationItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuotationItem
        fields = [
            "id",
            "description",
            "quantity",
            "unit_price",
            "total_price",
        ]
        read_only_fields = ["id", "total_price"]


class QuotationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""

    item_count = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Quotation
        fields = [
            "id",
            "client",
            "client_name",
            "client_contact",
            "quote_date",
            "valid_until",
            "project_description",
            "subtotal",
            "discount_amount",
            "total",
            "status",
            "item_count",
            "created_by_name",
            "is_deleted",
            "deleted_at",
            "created_at",
            "updated_at",
        ]

    def get_item_count(self, obj):
        return obj.items.count()

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None


class QuotationSerializer(serializers.ModelSerializer):
    """Full serializer with nested items for detail/create/update."""

    items = QuotationItemSerializer(many=True)
    client_data = ClientSerializer(source="client", read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Quotation
        fields = [
            "id",
            "client",
            "client_data",
            "client_name",
            "client_address",
            "client_contact",
            "quote_date",
            "valid_until",
            "project_description",
            "subtotal",
            "discount_amount",
            "total",
            "terms_conditions",
            "payment_terms",
            "status",
            "authorized_signature",
            "client_signature",
            "items",
            "created_by",
            "created_by_name",
            "is_deleted",
            "deleted_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "subtotal",
            "total",
            "created_by",
            "is_deleted",
            "created_at",
            "updated_at",
        ]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        quotation = Quotation(**validated_data)

        # Calculate totals from items
        subtotal = sum(
            Decimal(str(i["quantity"])) * Decimal(str(i["unit_price"]))
            for i in items_data
        )
        discount = Decimal(str(validated_data.get("discount_amount", 0)))
        quotation.subtotal = subtotal
        quotation.total = max(Decimal("0.00"), subtotal - discount)
        quotation.save()

        for item_data in items_data:
            QuotationItem.objects.create(quotation=quotation, **item_data)

        return quotation

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)

        # Update scalar fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if items_data is not None:
            # Replace all items
            instance.items.all().delete()
            for item_data in items_data:
                QuotationItem.objects.create(quotation=instance, **item_data)

        # Recalculate totals
        subtotal = sum(i.quantity * i.unit_price for i in instance.items.all())
        instance.subtotal = subtotal
        instance.total = max(Decimal("0.00"), subtotal - instance.discount_amount)
        instance.save()

        return instance
