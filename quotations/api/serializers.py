from decimal import Decimal

from rest_framework import serializers

from clients.api.serializers import ClientSerializer
from inventory.api.serializers import StallSerializer
from quotations.models import (
    Quotation,
    QuotationItem,
    QuotationPayment,
    QuotationTermsTemplate,
    QuotationPriceListTemplate,
)


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


class QuotationPriceListTemplateSerializer(serializers.ModelSerializer):
    aircon_model_count = serializers.SerializerMethodField()

    class Meta:
        model = QuotationPriceListTemplate
        fields = [
            "id",
            "name",
            "description",
            "aircon_models",
            "aircon_model_count",
            "is_active",
            "is_default",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_aircon_model_count(self, obj):
        return obj.aircon_models.count()


class QuotationItemSerializer(serializers.ModelSerializer):
    discounted_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
        help_text="Price after applying per-item discount",
    )

    class Meta:
        model = QuotationItem
        fields = [
            "id",
            "aircon_model",
            "aircon_unit",
            "description",
            "quantity",
            "unit_price",
            "promo_price",
            "total_price",
            "discount_amount",
            "discounted_price",
        ]
        read_only_fields = ["id", "total_price", "discounted_price"]


class QuotationPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuotationPayment
        fields = [
            "id",
            "label",
            "amount",
            "payment_method",
            "payment_date",
            "reference_number",
            "si_number",
        ]
        read_only_fields = ["id"]


class QuotationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""

    item_count = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    stall_data = StallSerializer(source="stall", read_only=True)

    class Meta:
        model = Quotation
        fields = [
            "id",
            "client",
            "stall",
            "stall_data",
            "client_name",
            "client_contact",
            "quote_date",
            "valid_until",
            "project_description",
            "quotation_type",
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
    payments = QuotationPaymentSerializer(many=True, required=False)
    client_data = ClientSerializer(source="client", read_only=True)
    stall_data = StallSerializer(source="stall", read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Quotation
        fields = [
            "id",
            "client",
            "client_data",
            "stall",
            "stall_data",
            "price_list_template",
            "client_name",
            "client_address",
            "client_contact",
            "quote_date",
            "valid_until",
            "project_description",
            "quotation_type",
            "subtotal",
            "discount_amount",
            "total",
            "terms_conditions",
            "payment_terms",
            "notes",
            "status",
            "authorized_signature",
            "client_signature",
            "authorized_name",
            "authorized_date",
            "client_acceptance_name",
            "client_acceptance_date",
            "items",
            "payments",
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
        payments_data = validated_data.pop("payments", [])
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

        for payment_data in payments_data:
            QuotationPayment.objects.create(quotation=quotation, **payment_data)

        return quotation

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        payments_data = validated_data.pop("payments", None)

        # Update scalar fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if items_data is not None:
            # Replace all items
            instance.items.all().delete()
            for item_data in items_data:
                QuotationItem.objects.create(quotation=instance, **item_data)

        if payments_data is not None:
            # Replace all payments
            instance.payments.all().delete()
            for payment_data in payments_data:
                QuotationPayment.objects.create(quotation=instance, **payment_data)

        # Recalculate totals
        subtotal = sum(i.quantity * i.unit_price for i in instance.items.all())
        instance.subtotal = subtotal
        instance.total = max(Decimal("0.00"), subtotal - instance.discount_amount)
        instance.save()

        return instance
