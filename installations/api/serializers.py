from rest_framework import serializers
from installations.models import AirconBrand, AirconModel, AirconUnit


class AirconBrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = AirconBrand
        fields = ["id", "name"]


class AirconModelSerializer(serializers.ModelSerializer):
    brand = AirconBrandSerializer(read_only=True)
    brand_id = serializers.PrimaryKeyRelatedField(
        queryset=AirconBrand.objects.all(), write_only=True, source="brand"
    )

    class Meta:
        model = AirconModel
        fields = [
            "id",
            "brand",
            "brand_id",
            "model_name",
            "retail_price",
            "aircon_type",
        ]


class AirconUnitSerializer(serializers.ModelSerializer):
    aircon_model = AirconModelSerializer(read_only=True)
    aircon_model_id = serializers.PrimaryKeyRelatedField(
        queryset=AirconModel.objects.all(), write_only=True, source="aircon_model"
    )
    warranty_end_date = serializers.ReadOnlyField()
    is_under_warranty = serializers.ReadOnlyField()
    warranty_status = serializers.ReadOnlyField()
    warranty_days_left = serializers.ReadOnlyField()

    class Meta:
        model = AirconUnit
        fields = [
            "id",
            "aircon_model",
            "aircon_model_id",
            "serial_number",
            "sale",
            "installation",
            "warranty_start_date",
            "warranty_period_months",
            "free_cleaning_redeemed",
            "created_at",
            "warranty_end_date",
            "is_under_warranty",
            "warranty_status",
            "warranty_days_left",
        ]
