from rest_framework import serializers
from installations.models import (
    AirconBrand,
    AirconModel,
    AirconInstallation,
    AirconUnit,
    AirconItemUsed,
)
from services.models import Service


class AirconBrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = AirconBrand
        fields = ["id", "name"]

    def validate_name(self, value):
        if AirconBrand.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("This aircon brand already exists.")
        return value


class AirconModelSerializer(serializers.ModelSerializer):
    brand = AirconBrandSerializer(read_only=True)
    brand_id = serializers.PrimaryKeyRelatedField(
        source="brand", queryset=AirconBrand.objects.all(), write_only=True
    )
    has_discount = serializers.ReadOnlyField()

    class Meta:
        model = AirconModel
        fields = [
            "id",
            "brand",
            "brand_id",
            "name",
            "retail_price",
            "aircon_type",
            "discount_percentage",
            "is_inverter",
            "has_discount",
        ]

    def validate(self, data):
        brand = data.get("brand")
        name = data.get("name")

        # Exclude the current instance if updating
        qs = AirconModel.objects.filter(brand=brand, name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                f"Model '{name}' already exists under this brand."
            )
        return data


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

    def validate_serial_number(self, value):
        if AirconUnit.objects.filter(serial_number__iexact=value).exists():
            raise serializers.ValidationError("This serial number is already in use.")
        return value

    def validate_free_cleaning_redeemed(self, value):
        """
        Allow toggling free_cleaning_redeemed only if the unit is installed.
        """
        instance = self.instance  # available when updating
        if value and instance and not instance.installation:
            raise serializers.ValidationError(
                "Cannot redeem free cleaning before the unit is installed."
            )
        return value


class AirconItemUsedSerializer(serializers.ModelSerializer):
    class Meta:
        model = AirconItemUsed
        fields = "__all__"


class AirconInstallationSerializer(serializers.ModelSerializer):
    service_id = serializers.PrimaryKeyRelatedField(
        source="service", queryset=Service.objects.all()
    )
    aircon_unit = AirconUnitSerializer(many=True, read_only=True)

    class Meta:
        model = AirconInstallation
        fields = "__all__"

    def validate(self, data):
        service = data.get("service")
        unit = data.get("unit", None)

        if (
            unit
            and AirconInstallation.objects.filter(service=service, unit=unit).exists()
        ):
            raise serializers.ValidationError(
                f"Aircon unit '{unit}' is already linked to this service."
            )
        return data
