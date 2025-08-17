from datetime import datetime, timedelta
from rest_framework import serializers
from services.models import (
    Service,
    ServiceAppliance,
    ApplianceItemUsed,
    TechnicianAssignment,
    ServiceStatusHistory,
    ApplianceStatusHistory,
)


# --------------------------
# Appliance Item Used
# --------------------------
class ApplianceItemUsedSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    item_price = serializers.DecimalField(
        source="item.price", read_only=True, max_digits=10, decimal_places=2
    )

    class Meta:
        model = ApplianceItemUsed
        fields = ["id", "appliance", "item", "item_name", "item_price", "quantity"]


# --------------------------
# Service Appliance
# --------------------------
class ServiceApplianceSerializer(serializers.ModelSerializer):
    items_used = ApplianceItemUsedSerializer(many=True, read_only=True)

    class Meta:
        model = ServiceAppliance
        fields = [
            "id",
            "service",
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
        appliance = super().create(validated_data)
        ApplianceStatusHistory.objects.create(
            service_appliance=appliance,
            status=appliance.status,
        )
        return appliance

    def update(self, instance, validated_data):
        old_status = instance.status
        appliance = super().update(instance, validated_data)
        if appliance.status != old_status:
            ApplianceStatusHistory.objects.create(
                service_appliance=appliance,
                status=appliance.status,
            )
        return appliance


# --------------------------
# Technician Assignment
# --------------------------
class TechnicianAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TechnicianAssignment
        fields = "__all__"

    def validate(self, data):
        technician = data.get("technician")
        service = data.get("service")

        if not service.scheduled_date or not service.scheduled_time:
            raise serializers.ValidationError(
                "Service must have a scheduled date and time before assigning a technician."
            )

        # Compute service datetime range
        service_start = datetime.combine(service.scheduled_date, service.scheduled_time)
        service_end = service_start + timedelta(minutes=service.estimated_duration)

        # Find technician's other assignments
        conflicts = TechnicianAssignment.objects.filter(technician=technician).exclude(
            service=service
        )

        for assignment in conflicts:
            other = assignment.service
            if not other.scheduled_date or not other.scheduled_time:
                continue

            other_start = datetime.combine(other.scheduled_date, other.scheduled_time)
            other_end = other_start + timedelta(minutes=other.estimated_duration)

            # Check overlap
            if service_start < other_end and other_start < service_end:
                raise serializers.ValidationError(
                    f"Technician {technician.get_full_name()} is already assigned "
                    f"to another service ({other.id}) that overlaps this schedule."
                )

        return data


# --------------------------
# Service
# --------------------------
class ServiceSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    appliances = ServiceApplianceSerializer(many=True, read_only=True)
    technician_assignments = TechnicianAssignmentSerializer(many=True, read_only=True)
    total_cost = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model = Service
        fields = [
            "id",
            "client",
            "client_name",
            "service_type",
            "service_mode",
            "description",
            "override_address",
            "override_contact_person",
            "override_contact_number",
            "scheduled_date",
            "scheduled_time",
            "pickup_date",
            "delivery_date",
            "status",
            "remarks",
            "notes",
            "created_at",
            "updated_at",
            "appliances",
            "technician_assignments",
            "total_cost",
            "estimated_duration",
        ]

    def create(self, validated_data):
        service = super().create(validated_data)
        ServiceStatusHistory.objects.create(
            service=service,
            status=service.status,
        )
        return service

    def update(self, instance, validated_data):
        old_status = instance.status
        service = super().update(instance, validated_data)
        if service.status != old_status:
            ServiceStatusHistory.objects.create(
                service=service,
                status=service.status,
            )
        return service
