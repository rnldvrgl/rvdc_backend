from rest_framework import serializers
from inventory.api.serializers import ItemSerializer
from clients.api.serializers import ClientSerializer
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
)
from inventory.models import AirconUnit, AirconModel, AirconBrand, Item, ApplianceType
from clients.models import Client
from users.models import CustomUser
from sales.models import SalesTransaction


class TechnicianSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ["id", "full_name", "email"]

    def get_full_name(self, obj):
        return obj.get_full_name()


class ApplianceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplianceType
        fields = ["id", "name"]


# Appliance Item Used
class ApplianceItemUsedSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)

    class Meta:
        model = ApplianceItemUsed
        fields = ["id", "item", "quantity"]


# Service Appliance
class ServiceApplianceSerializer(serializers.ModelSerializer):
    appliance_type = ApplianceTypeSerializer(read_only=True)
    items_used = ApplianceItemUsedSerializer(many=True, read_only=True)

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


# Home Service Schedule
class HomeServiceScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomeServiceSchedule
        fields = [
            "id",
            "scheduled_date",
            "scheduled_time",
            "override_address",
            "override_contact_person",
            "override_contact_number",
            "notes",
        ]


# Aircon Item Used
class AirconItemUsedSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)

    class Meta:
        model = AirconItemUsed
        fields = ["id", "item", "quantity"]


# Aircon Installation
class AirconInstallationSerializer(serializers.ModelSerializer):
    items_used = AirconItemUsedSerializer(many=True, read_only=True)

    class Meta:
        model = AirconInstallation
        fields = ["id", "notes", "created_at", "items_used"]


# Motor Rewind
class MotorRewindSerializer(serializers.ModelSerializer):
    appliance_type = ApplianceTypeSerializer(read_only=True)

    class Meta:
        model = MotorRewind
        fields = [
            "id",
            "appliance_type",
            "quantity",
            "labor_fee",
            "notes",
            "related_transaction",
            "created_at",
        ]


# Service Status History
class ServiceStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceStatusHistory
        fields = ["id", "status", "changed_at"]


# Appliance Status History
class ApplianceStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplianceStatusHistory
        fields = ["id", "status", "changed_at"]


# Main Service Serializer
class ServiceSerializer(serializers.ModelSerializer):
    client = ClientSerializer(read_only=True)
    assigned_technicians = TechnicianSerializer(many=True, read_only=True)
    appliances = ServiceApplianceSerializer(many=True, read_only=True)
    aircon_installation = AirconInstallationSerializer(read_only=True)
    motor_rewinds = MotorRewindSerializer(many=True, read_only=True)
    home_service_schedule = HomeServiceScheduleSerializer(read_only=True)
    status_history = ServiceStatusHistorySerializer(many=True, read_only=True)
    related_transaction = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Service
        fields = [
            "id",
            "client",
            "service_type",
            "mode",
            "previous_service",
            "was_converted_to_repair",
            "status",
            "assigned_technicians",
            "remarks",
            "related_transaction",
            "created_at",
            "updated_at",
            "appliances",
            "aircon_installation",
            "motor_rewinds",
            "home_service_schedule",
            "status_history",
        ]
