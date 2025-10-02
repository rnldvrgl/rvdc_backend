from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from services.models import (
    Service,
    ServiceAppliance,
    ApplianceItemUsed,
)
from inventory.models import (
    Stock,
)


# -------------------------------
# Appliance Item Used (Parts consumed)
# -------------------------------
class ApplianceItemUsedSerializer(serializers.ModelSerializer):
    stall_stock_id = serializers.PrimaryKeyRelatedField(
        queryset=Stock.objects.all(),
        source="stall_stock",
        write_only=True,
        required=True,
        help_text="Stall stock to consume from",
    )

    item_name = serializers.CharField(source="item.name", read_only=True)
    item_price = serializers.DecimalField(
        source="item.retail_price", read_only=True, max_digits=10, decimal_places=2
    )

    class Meta:
        model = ApplianceItemUsed
        fields = [
            "id",
            "appliance",
            "item",
            "item_name",
            "item_price",
            "quantity",
            "stall_stock_id",
        ]

    def validate(self, data):
        stock = data["stall_stock"]
        item = data["item"]
        qty = data["quantity"]

        if stock.item != item:
            raise ValidationError("Selected stall does not hold this item.")

        if qty > stock.quantity:
            raise ValidationError(
                f"Not enough stock of {item.name} in stall {stock.stall.name}. "
                f"Available: {stock.quantity}"
            )

        self._validated_stock = stock
        return data

    def create(self, validated_data):
        stock = self._validated_stock
        qty = validated_data["quantity"]

        with transaction.atomic():
            stock.quantity -= qty
            stock.save()

            aiu = super().create(validated_data)

        return aiu

    def update(self, instance, validated_data):
        stock = self._validated_stock
        old_qty = instance.quantity
        new_qty = validated_data.get("quantity", old_qty)
        diff = new_qty - old_qty

        with transaction.atomic():
            if diff > 0:  # need more stock
                if stock.quantity < diff:
                    raise ValidationError(
                        f"Not enough stock in {stock.stall.name}. "
                        f"Available: {stock.quantity}"
                    )
                stock.quantity -= diff
            elif diff < 0:  # return stock
                stock.quantity += abs(diff)
            stock.save()

            instance = super().update(instance, validated_data)

        return instance


# -------------------------------
# Service Appliance
# -------------------------------
class ServiceApplianceSerializer(serializers.ModelSerializer):
    items_used = ApplianceItemUsedSerializer(many=True, required=False)

    class Meta:
        model = ServiceAppliance
        fields = [
            "id",
            "service",
            "appliance_type",
            "serial_number",
            "issues_reported",
            "diagnosis",
            "items_used",
        ]

    def create(self, validated_data):
        items_data = validated_data.pop("items_used", [])
        with transaction.atomic():
            appliance = ServiceAppliance.objects.create(**validated_data)
            for item_data in items_data:
                item_data["appliance"] = appliance
                serializer = ApplianceItemUsedSerializer(
                    data=item_data, context=self.context
                )
                serializer.is_valid(raise_exception=True)
                serializer.save()
        return appliance

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items_used", None)
        with transaction.atomic():
            instance = super().update(instance, validated_data)

            if items_data is not None:
                # delete old items + restore stock
                for old in instance.items_used.all():
                    stock = Stock.objects.get(
                        stall=old.stall_stock.stall, item=old.item
                    )
                    stock.quantity += old.quantity
                    stock.save()

                    old.delete()

                # add new items
                for item_data in items_data:
                    item_data["appliance"] = instance
                    serializer = ApplianceItemUsedSerializer(
                        data=item_data, context=self.context
                    )
                    serializer.is_valid(raise_exception=True)
                    serializer.save()
        return instance


# -------------------------------
# Service
# -------------------------------
class ServiceSerializer(serializers.ModelSerializer):
    appliances = ServiceApplianceSerializer(many=True, required=False)

    class Meta:
        model = Service
        fields = [
            "id",
            "customer",
            "technician",
            "status",
            "scheduled_date",
            "completed_date",
            "remarks",
            "appliances",
        ]

    def create(self, validated_data):
        appliances_data = validated_data.pop("appliances", [])
        with transaction.atomic():
            service = Service.objects.create(**validated_data)
            for appliance_data in appliances_data:
                appliance_data["service"] = service
                serializer = ServiceApplianceSerializer(
                    data=appliance_data, context=self.context
                )
                serializer.is_valid(raise_exception=True)
                serializer.save()
        return service

    def update(self, instance, validated_data):
        appliances_data = validated_data.pop("appliances", None)
        with transaction.atomic():
            instance = super().update(instance, validated_data)

            if appliances_data is not None:
                for appliance_data in appliances_data:
                    appliance_id = appliance_data.get("id", None)
                    if appliance_id:
                        appliance = ServiceAppliance.objects.get(
                            id=appliance_id, service=instance
                        )
                        serializer = ServiceApplianceSerializer(
                            appliance, data=appliance_data, context=self.context
                        )
                        serializer.is_valid(raise_exception=True)
                        serializer.save()
                    else:
                        appliance_data["service"] = instance
                        serializer = ServiceApplianceSerializer(
                            data=appliance_data, context=self.context
                        )
                        serializer.is_valid(raise_exception=True)
                        serializer.save()
        return instance
