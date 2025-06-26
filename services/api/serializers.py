from rest_framework import serializers
from services.models import Client, ServiceRequest, ServiceStep, ServiceRequestItem


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
    client_name = serializers.CharField(source="client.name", read_only=True)
    technician_name = serializers.CharField(
        source="technician.get_full_name", read_only=True
    )
    used_items = ServiceRequestItemSerializer(many=True, read_only=True)
    steps = ServiceStepSerializer(many=True, read_only=True)

    class Meta:
        model = ServiceRequest
        fields = "__all__"
