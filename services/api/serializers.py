# from rest_framework import serializers
# from services.models import ServiceRequest, ServiceStep, ServiceRequestItem
# from inventory.models import Item, Stall
# from users.models import CustomUser


# class ServiceRequestItemSerializer(serializers.ModelSerializer):
#     item_name = serializers.CharField(source="item.name", read_only=True)

#     class Meta:
#         model = ServiceRequestItem
#         fields = [
#             "id",
#             "item",
#             "item_name",
#             "quantity_used",
#             "deducted_from_stall",
#             "deducted_by",
#             "deducted_at",
#         ]
#         read_only_fields = ["deducted_at", "item_name"]


# class ServiceStepSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = ServiceStep
#         fields = "__all__"


# class ServiceRequestSerializer(serializers.ModelSerializer):
#     client_name = serializers.CharField(source="client.full_name", read_only=True)
#     technician_names = serializers.SerializerMethodField()
#     used_items = ServiceRequestItemSerializer(many=True, required=False)
#     steps = ServiceStepSerializer(many=True, read_only=True)

#     class Meta:
#         model = ServiceRequest
#         fields = (
#             "id",
#             "client",
#             "client_name",
#             "technicians",
#             "technician_names",
#             "appliance_type",
#             "brand",
#             "unit_type",
#             "service_type",
#             "previous_service_type",
#             "status",
#             "remarks",
#             "date_received",
#             "date_completed",
#             "used_items",
#             "steps",
#             "payment_status",
#             "payment_method",
#             "total_payment",
#             "final_price",
#             "payment_date",
#         )

#     def get_technician_names(self, obj):
#         return [t.get_full_name() or t.username for t in obj.technicians.all()]

#     def create(self, validated_data):
#         used_items_data = self.initial_data.get("used_items", [])
#         technicians_data = validated_data.pop("technicians", None)

#         # Remove nested field to avoid errors during base model creation
#         validated_data.pop("used_items", None)

#         # Create the service request
#         service_request = ServiceRequest.objects.create(**validated_data)

#         # Add technicians if provided
#         if technicians_data is not None:
#             service_request.technicians.set(technicians_data)

#         # Create used items
#         for item_data in used_items_data:
#             try:
#                 item = Item.objects.get(pk=item_data["item"])
#                 stall = Stall.objects.get(pk=item_data["deducted_from_stall"])
#                 user = CustomUser.objects.get(pk=item_data["deducted_by"])

#                 ServiceRequestItem.objects.create(
#                     service_request=service_request,
#                     item=item,
#                     quantity_used=item_data["quantity_used"],
#                     deducted_from_stall=stall,
#                     deducted_by=user,
#                 )
#             except Exception as e:
#                 raise serializers.ValidationError(f"Error with used_items: {str(e)}")

#         return service_request
