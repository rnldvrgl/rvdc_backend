from rest_framework import serializers
from installations.models import (
    AirconBrand,
    AirconModel,
    AirconInstallation,
    AirconUnit,
    AirconItemUsed,
)
from inventory.models import Item
from services.models import Service


class AirconBrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = AirconBrand
        fields = ["id", "name"]


class AirconModelSerializer(serializers.ModelSerializer):
    brand = AirconBrandSerializer(read_only=True)
    brand_id = serializers.PrimaryKeyRelatedField(
        source="brand", queryset=AirconBrand.objects.all(), write_only=True
    )

    class Meta:
        model = AirconModel
        fields = [
            "id",
            "brand",
            "brand_id",
            "name",
            "retail_price",
            "aircon_type",
            "is_inverter",
        ]


class AirconUnitSerializer(serializers.ModelSerializer):
    model = AirconModelSerializer(read_only=True)
    model_id = serializers.PrimaryKeyRelatedField(
        source="model", queryset=AirconModel.objects.all(), write_only=True
    )
    warranty_end_date = serializers.ReadOnlyField()
    warranty_status = serializers.ReadOnlyField()
    warranty_days_left = serializers.ReadOnlyField()
    is_reserved = serializers.ReadOnlyField()
    is_available_for_sale = serializers.ReadOnlyField()

    class Meta:
        model = AirconUnit
        fields = [
            "id",
            "model",
            "model_id",
            "serial_number",
            "sale",
            "installation",
            "reserved_by",
            "reserved_at",
            "warranty_start_date",
            "warranty_period_months",
            "free_cleaning_redeemed",
            "warranty_end_date",
            "warranty_status",
            "warranty_days_left",
            "is_reserved",
            "is_available_for_sale",
            "created_at",
        ]


class AirconItemUsedSerializer(serializers.ModelSerializer):
    class Meta:
        model = AirconItemUsed
        fields = "__all__"


class AirconInstallationSerializer(serializers.ModelSerializer):
    service_id = serializers.PrimaryKeyRelatedField(
        source="service", queryset=Service.objects.all()
    )
    aircon_unit = AirconUnitSerializer(read_only=True)
    aircon_unit = AirconUnitSerializer(many=True, read_only=True)

    class Meta:
        model = AirconInstallation
        fields = "__all__"
