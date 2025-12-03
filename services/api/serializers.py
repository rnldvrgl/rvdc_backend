from django.db import transaction
from inventory.models import (
    Stock,
    StockTransfer,
    StockTransferItem,
)
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from sales.models import SalesItem, SalesTransaction
from services.models import (
    ApplianceItemUsed,
    Service,
    ServiceAppliance,
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
    line_discount_rate = serializers.DecimalField(
        write_only=True, required=False, max_digits=5, decimal_places=2, default=0
    )

    class Meta:
        model = ApplianceItemUsed
        fields = [
            "id",
            "appliance",
            "item",
            "item_name",
            "item_price",
            "line_discount_rate",
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
        line_disc = validated_data.get("line_discount_rate", 0)

        # Determine the appliance and its service
        appliance = validated_data.get("appliance")
        service = getattr(appliance, "service", None)
        request = self.context.get("request")
        user = getattr(request, "user", None)

        # Optional order-level rate passed in request
        order_rate = None
        if request is not None:
            try:
                order_rate = request.data.get("order_discount_rate", None)
                if order_rate is not None:
                    order_rate = float(order_rate)
            except Exception:
                order_rate = None

        with transaction.atomic():
            if service and service.stall and stock.stall != service.stall:
                # Cross-stall: create transfer and finalize
                transfer = StockTransfer.objects.create(
                    from_stall=stock.stall,
                    to_stall=service.stall,
                    transferred_by=user,
                    used_for=f"Service #{service.id}",
                )
                StockTransferItem.objects.create(
                    transfer=transfer, item=stock.item, quantity=qty
                )

                stock.quantity -= qty
                stock.save()

                transfer.finalize(user)

                aiu = super().create(validated_data)

                # Link created expense and stall stock
                try:
                    aiu.expense = transfer.expense
                    aiu.stall_stock = stock
                    aiu.save()
                except Exception:
                    pass

                # Ensure SalesTransaction exists and mirror discounts
                sales_txn = service.related_transaction
                if not sales_txn:
                    sales_txn = SalesTransaction.objects.create(
                        stall=service.stall, client=service.client, sales_clerk=user
                    )
                    service.related_transaction = sales_txn
                    service.save(update_fields=["related_transaction"])
                if order_rate is not None:
                    sales_txn.order_discount_rate = order_rate
                    sales_txn.save(update_fields=["order_discount_rate"])

                SalesItem.objects.create(
                    transaction=sales_txn,
                    item=aiu.item,
                    quantity=aiu.quantity,
                    final_price_per_unit=aiu.item.retail_price,
                    line_discount_rate=line_disc,
                )
            else:
                # Same-stall consumption
                stock.quantity -= qty
                stock.save()

                aiu = super().create(validated_data)

                sales_txn = service.related_transaction
                if not sales_txn:
                    sales_txn = SalesTransaction.objects.create(
                        stall=service.stall, client=service.client, sales_clerk=user
                    )
                    service.related_transaction = sales_txn
                    service.save(update_fields=["related_transaction"])
                if order_rate is not None:
                    sales_txn.order_discount_rate = order_rate
                    sales_txn.save(update_fields=["order_discount_rate"])

                SalesItem.objects.create(
                    transaction=sales_txn,
                    item=aiu.item,
                    quantity=aiu.quantity,
                    final_price_per_unit=aiu.item.retail_price,
                    line_discount_rate=line_disc,
                )

        return aiu

    def update(self, instance, validated_data):
        stock = self._validated_stock
        old_qty = instance.quantity
        new_qty = validated_data.get("quantity", old_qty)
        diff = new_qty - old_qty

        with transaction.atomic():
            appliance = instance.appliance
            service = getattr(appliance, "service", None)
            request = self.context.get("request")
            user = getattr(request, "user", None)

            if diff > 0:  # need more stock
                if stock.quantity < diff:
                    raise ValidationError(
                        f"Not enough stock in {stock.stall.name}. "
                        f"Available: {stock.quantity}"
                    )

                # If cross-stall (stock comes from different stall than service), create transfer for the diff
                if service and service.stall and stock.stall != service.stall:
                    transfer = StockTransfer.objects.create(
                        from_stall=stock.stall,
                        to_stall=service.stall,
                        transferred_by=user,
                        used_for=f"Service #{service.id}",
                    )
                    StockTransferItem.objects.create(
                        transfer=transfer, item=stock.item, quantity=diff
                    )

                    # decrement supplying stall stock
                    stock.quantity -= diff
                    stock.save()

                    transfer.finalize(user)

                    # attach expense if not set
                    if not instance.expense and getattr(transfer, "expense", None):
                        instance.expense = transfer.expense

                else:
                    stock.quantity -= diff
                    stock.save()

            elif diff < 0:  # return stock
                stock.quantity += abs(diff)
                stock.save()

            instance = super().update(instance, validated_data)

            # Ensure SalesTransaction exists and mirror order-level discount if provided
            sales_txn = service.related_transaction
            if not sales_txn:
                sales_txn = SalesTransaction.objects.create(
                    stall=service.stall, client=service.client, sales_clerk=user
                )
                service.related_transaction = sales_txn
                service.save(update_fields=["related_transaction"])

            if request is not None:
                try:
                    order_rate = request.data.get("order_discount_rate", None)
                    if order_rate is not None:
                        order_rate = float(order_rate)
                        sales_txn.order_discount_rate = order_rate
                        sales_txn.save(update_fields=["order_discount_rate"])
                except Exception:
                    pass

            # Update or create SalesItem line
            s_item = sales_txn.items.filter(item=instance.item).first()
            if s_item:
                s_item.quantity = s_item.quantity - old_qty + instance.quantity
                s_item.save()
            else:
                SalesItem.objects.create(
                    transaction=sales_txn,
                    item=instance.item,
                    quantity=instance.quantity,
                    final_price_per_unit=instance.item.retail_price,
                    line_discount_rate=validated_data.get("line_discount_rate", 0),
                )

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
