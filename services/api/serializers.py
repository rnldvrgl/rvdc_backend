from rest_framework import serializers
from services.models import ServiceRequest, ServiceStep, ServiceRequestItem


class ServiceRequestItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = ServiceRequestItem
        fields = "__all__"
        read_only_fields = ["deducted_at"]


class ServiceStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceStep
        fields = "__all__"


class ServiceRequestSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.full_name", read_only=True)
    technician_names = serializers.SerializerMethodField()
    used_items = ServiceRequestItemSerializer(many=True, read_only=True)
    steps = ServiceStepSerializer(many=True, read_only=True)

    class Meta:
        model = ServiceRequest
        fields = (
            "id",
            "client",
            "client_name",
            "technicians",
            "technician_names",
            "appliance_type",
            "brand",
            "unit_type",
            "service_type",
            "previous_service_type",
            "status",
            "remarks",
            "date_received",
            "date_completed",
            "used_items",
            "steps",
        )

    def get_technician_names(self, obj):
        return [t.get_full_name() or t.username for t in obj.technicians.all()]
