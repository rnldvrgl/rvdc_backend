from rest_framework import serializers
from inventory.api.serializers import ItemSerializer
from clients.api.serializers import ClientSerializer
from sales.api.serializers import SalesTransactionSerializer
from services.models import (
    Service,
    HomeServiceSchedule,
    ServiceAppliance,
    ApplianceItemUsed,
    AirconInstallation,
    AirconItemUsed,
    MotorRewind,
    ServiceStatusHistory,
    ApplianceStatusHistory,
    ApplianceType,
)
from clients.models import Client
from users.models import CustomUser
from sales.models import SalesTransaction
from inventory.models import Item


# -- Technician --
class TechnicianSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ["id", "full_name", "email"]

    def get_full_name(self, obj):
        return obj.get_full_name()


# -- Appliance Type --
class ApplianceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplianceType
        fields = ["id", "name"]


# -- Base for any ItemUsed serializer (reused by Aircon & Appliance) --
class BaseItemUsedSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.all(),
        source="item",
        write_only=True,
    )

    class Meta:
        abstract = True
        fields = ["id", "item", "item_id"]


# -- Appliance Item Used --
class ApplianceItemUsedSerializer(BaseItemUsedSerializer):
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2)

    class Meta(BaseItemUsedSerializer.Meta):
        model = ApplianceItemUsed
        fields = BaseItemUsedSerializer.Meta.fields + ["quantity"]


# -- Aircon Item Used --
class AirconItemUsedSerializer(BaseItemUsedSerializer):
    total_quantity_used = serializers.DecimalField(max_digits=10, decimal_places=2)
    free_quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
    payable_quantity = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )

    class Meta(BaseItemUsedSerializer.Meta):
        model = AirconItemUsed
        fields = BaseItemUsedSerializer.Meta.fields + [
            "total_quantity_used",
            "free_quantity",
            "payable_quantity",
        ]


# -- Service Appliance --
class ServiceApplianceSerializer(serializers.ModelSerializer):
    items_used = ApplianceItemUsedSerializer(many=True)

    class Meta:
        model = ServiceAppliance
        fields = [
            "id",
            "appliance_type",
            "brand",
            "model",
            "issue_reported",
            "diagnosis_notes",
            "status",
            "labor_fee",
            "items_used",
        ]

    def create(self, validated_data):
        items_data = validated_data.pop("items_used", [])
        appliance = ServiceAppliance.objects.create(**validated_data)
        for item in items_data:
            ApplianceItemUsed.objects.create(appliance=appliance, **item)
        return appliance

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items_used", [])
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        instance.items_used.all().delete()
        for item in items_data:
            ApplianceItemUsed.objects.create(appliance=instance, **item)
        return instance


# -- Aircon Installation --
class AirconInstallationSerializer(serializers.ModelSerializer):
    items_used = AirconItemUsedSerializer(many=True)

    class Meta:
        model = AirconInstallation
        fields = ["source", "items_used"]

    def create(self, validated_data):
        items_data = validated_data.pop("items_used", [])
        installation = AirconInstallation.objects.create(**validated_data)
        for item in items_data:
            AirconItemUsed.objects.create(installation=installation, **item)
        return installation

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items_used", [])
        instance.source = validated_data.get("source", instance.source)
        instance.save()

        instance.items_used.all().delete()
        for item in items_data:
            AirconItemUsed.objects.create(installation=instance, **item)
        return instance


# -- Motor Rewind --
class MotorRewindSerializer(serializers.ModelSerializer):
    class Meta:
        model = MotorRewind
        exclude = ["service"]


# -- Home Service Schedule --
class HomeServiceScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomeServiceSchedule
        exclude = ["service"]


# -- Service Status History --
class ServiceStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceStatusHistory
        fields = ["id", "status", "changed_at"]


# -- Appliance Status History --
class ApplianceStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplianceStatusHistory
        fields = ["id", "status", "changed_at"]


# -- Main Service Serializer --
class ServiceSerializer(serializers.ModelSerializer):
    client = ClientSerializer(read_only=True)
    client_id = serializers.PrimaryKeyRelatedField(
        queryset=Client.objects.all(), source="client", write_only=True
    )

    related_transaction = SalesTransactionSerializer(read_only=True)
    related_transaction_id = serializers.PrimaryKeyRelatedField(
        queryset=SalesTransaction.objects.all(),
        source="related_transaction",
        write_only=True,
        allow_null=True,
        required=False,
    )

    home_service_schedule = HomeServiceScheduleSerializer(required=False)
    aircon_installation = AirconInstallationSerializer(required=False)
    appliances = ServiceApplianceSerializer(many=True, required=False)
    motor_rewinds = MotorRewindSerializer(many=True, required=False)

    class Meta:
        model = Service
        fields = [
            "id",
            "client",
            "client_id",
            "service_type",
            "related_transaction",
            "related_transaction_id",
            "description",
            "status",
            "remarks",
            "created_at",
            "home_service_schedule",
            "aircon_installation",
            "appliances",
            "motor_rewinds",
        ]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data):
        client = validated_data.pop("client")
        related_transaction = validated_data.pop("related_transaction", None)

        schedule_data = validated_data.pop("home_service_schedule", None)
        installation_data = validated_data.pop("aircon_installation", None)
        appliances_data = validated_data.pop("appliances", [])
        motor_rewinds_data = validated_data.pop("motor_rewinds", [])

        service = Service.objects.create(
            client=client, related_transaction=related_transaction, **validated_data
        )

        if schedule_data:
            HomeServiceSchedule.objects.create(service=service, **schedule_data)

        if installation_data:
            items = installation_data.pop("items_used", [])
            installation = AirconInstallation.objects.create(
                service=service, **installation_data
            )
            for item in items:
                AirconItemUsed.objects.create(installation=installation, **item)

        for appliance_data in appliances_data:
            items = appliance_data.pop("items_used", [])
            appliance = ServiceAppliance.objects.create(
                service=service, **appliance_data
            )
            for item in items:
                ApplianceItemUsed.objects.create(appliance=appliance, **item)

        for rewind_data in motor_rewinds_data:
            MotorRewind.objects.create(service=service, **rewind_data)

        return service

    def update(self, instance, validated_data):
        validated_data.pop("client", None)
        validated_data.pop("related_transaction", None)

        schedule_data = validated_data.pop("home_service_schedule", None)
        installation_data = validated_data.pop("aircon_installation", None)
        appliances_data = validated_data.pop("appliances", [])
        motor_rewinds_data = validated_data.pop("motor_rewinds", [])

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if schedule_data:
            HomeServiceSchedule.objects.update_or_create(
                service=instance, defaults=schedule_data
            )

        if installation_data:
            AirconInstallation.objects.filter(service=instance).delete()
            items = installation_data.pop("items_used", [])
            installation = AirconInstallation.objects.create(
                service=instance, **installation_data
            )
            for item in items:
                AirconItemUsed.objects.create(installation=installation, **item)

        instance.appliances.all().delete()
        for appliance_data in appliances_data:
            items = appliance_data.pop("items_used", [])
            appliance = ServiceAppliance.objects.create(
                service=instance, **appliance_data
            )
            for item in items:
                ApplianceItemUsed.objects.create(appliance=appliance, **item)

        instance.motor_rewinds.all().delete()
        for rewind_data in motor_rewinds_data:
            MotorRewind.objects.create(service=instance, **rewind_data)

        return instance
